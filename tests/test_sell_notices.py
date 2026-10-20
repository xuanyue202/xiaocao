"""Sale notices distinguish committed fills from signals; all transport is fake."""
import json
from functools import partial

import pytest

from scripts import live_monitor as monitor
from xiaocao.live import incident_delivery, sell_notices as notices


@pytest.fixture(autouse=True)
def no_real_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("real notification/HTTP transport is forbidden")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("xiaocao.live.notify.macos_notify", forbidden)
    monkeypatch.setattr(monitor, "_notify", forbidden, raising=False)
    monkeypatch.setattr(notices, "notify_detailed", forbidden)


@pytest.fixture
def delivery(monkeypatch):
    calls, responses = [], []
    def sender(title, body, **kwargs):
        calls.append((title, body))
        return responses.pop(0) if responses else {"wecom": "ok"}
    monkeypatch.setattr(notices, "notify_detailed", sender)
    monkeypatch.setattr(notices, "deliver_pending", partial(incident_delivery.deliver_pending,
        readiness=lambda **kwargs: {"status": "configured"}))
    return calls, responses


def alert():
    return {"book": "B", "code": "300107.XSHE", "name": "建新股份",
            "entry_date": "2026-10-16", "sell_reason": "TRAILING_STOP"}


def closed_position(**changes):
    return {**alert(), "status": "closed", "exit_date": "2026-10-19",
            "entry_price": 8.08, "entry_cash_out": 12929, "shares": 1600,
            "exit_price": 8.23, "realized_pnl": 237.68, **changes}


def paper(rows, execute=True, book="B"):
    return notices.paper_sell_notice(alert(), rows, book=book,
        trade_date="2026-10-19", execute_requested=execute)


def test_paper_result_uses_committed_profit_and_exact_cost_not_trigger_price():
    result = paper([closed_position(), closed_position(book="T", realized_pnl=9999)])
    assert "纸面B" in result.title and "已全部卖出" in result.title
    assert "1600 股" in result.body and "8.23 元" in result.body
    assert "237.68 元（+1.84%）" in result.body
    assert "9999" not in result.body and "TRAILING_STOP" not in result.body


def test_loss_and_missing_cost_do_not_become_positive_or_invented_returns():
    assert "亏损：100.00 元（-1.00%）" in paper([
        closed_position(realized_pnl=-100, entry_cash_out=10000)]).body
    assert "待核算" in paper([closed_position(entry_cash_out=None)]).body


def test_sale_price_preserves_fractional_tick_precision():
    assert "8.235 元" in paper([closed_position(exit_price=8.235)]).body


@pytest.mark.parametrize("execute", [False, True])
def test_open_paper_lot_is_not_a_sale_even_with_a_trigger(execute):
    result = paper([closed_position(status="open")], execute)
    assert "状态：未卖出" in result.body
    assert "无已确认成交" in result.body and "237.68" not in result.body


def test_missing_or_pending_paper_evidence_cannot_claim_a_fill():
    assert "卖出未确认" in paper([]).title
    assert "卖出未确认" in paper([closed_position(entry_date="2026-10-15")]).title


def app_data():
    intent = {"plan_id": "sell-plan", "side": "SELL", "owned_lot_id": "buy-lot",
              "code": "300107.XSHE", "name": "建新股份", "trade_date": "2026-10-19",
              "shares": 1100, "sell_reason": "TRAILING_STOP"}
    receipt = {"plan_id": "sell-plan", "plan_hash": notices._sha256(intent),
               "broker_order_id": "6005007", "account_binding": "proven",
               "receipt_mapping": True, "state": "filled", "filled_shares": 1100,
               "remaining_shares": 0, "fill_price": 8.22}
    posted = {"source_sha256": "exact-fill-hash", "owned_lot_id": "buy-lot",
              "kind": "SELL", "shares": 1100, "cost_change": "-8965.90",
              "realized_pnl": "75.20", "fee_basis": "estimated_plan_rate",
              "final_realized_pnl": "75.20", "final_cost_change": "-8965.90"}
    return receipt, intent, posted


@pytest.mark.app_simulation
def test_app_result_profit_is_explicitly_provisional_and_separate_from_paper():
    receipt, intent, posted = app_data()
    posted.update(final_realized_pnl=None, final_cost_change=None, gross_pnl="77.00", gross_sold_cost="8965.00")
    result = notices.app_sell_notice(receipt, intent, [posted])
    assert "APP仿真B" in result.title and "已全部卖出" in result.title
    assert "1100 / 1100 股" in result.body and "8.22 元" in result.body
    assert "75.20" not in result.body and "待核对实际手续费" in result.body
    assert "+77.00 元（+0.86%）" in result.body


@pytest.mark.app_simulation
@pytest.mark.parametrize("change", [
    {"state": "unknown", "filled_shares": 0}, {"account_binding": "unproven"},
    {"receipt_mapping": False}, {"submit_chain_uncertain": True},
])
def test_ack_unknown_or_uncertain_mapping_is_not_reported_as_completed(change):
    receipt, intent, posted = app_data()
    result = notices.app_sell_notice({**receipt, **change}, intent, [posted])
    assert "结果待确认" in result.title
    assert "75.20" not in result.body and "已全部卖出" not in result.body


@pytest.mark.app_simulation
def test_partial_sale_uses_only_the_allocated_sold_cost():
    receipt, intent, posted = app_data()
    receipt.update(state="partial", filled_shares=100, remaining_shares=1000)
    posted.update(shares=100, final_cost_change="-815.09", final_realized_pnl="6.83")
    result = notices.app_sell_notice(receipt, intent, [posted])
    assert "部分卖出" in result.title and "100 / 1100 股" in result.body
    assert "6.83 元（+0.84%）" in result.body and "仅对应已成交部分" in result.body


@pytest.mark.app_simulation
def test_broker_fill_without_exact_postings_keeps_price_and_marks_profit_unknown():
    receipt, intent, posted = app_data()
    for rows in [[], [{**posted, "shares": 100}]]:
        result = notices.app_sell_notice(receipt, intent, rows)
        assert "已全部卖出" in result.title and "8.22 元" in result.body
        assert "盈亏：待核算" in result.body and "75.20" not in result.body


def test_shared_send_claim_deduplicates_same_result(tmp_path, delivery):
    calls, _ = delivery
    notice = paper([closed_position()])
    outbox = tmp_path / "sell_result_notices.jsonl"
    assert notices.deliver_sell_notice(outbox, notice)[0]["delivery"] == "delivered"
    assert notices.deliver_sell_notice(outbox, notice) == []
    assert len(calls) == 1


def test_uncertain_delivery_is_not_sent_again(tmp_path, delivery):
    calls, responses = delivery
    responses.append({"wecom": "failed", "wecom_recipients": {
        "user": {"status": "failed", "failure_phase": "response", "retry_safety": "uncertain"}}})
    notice = paper([closed_position()]); outbox = tmp_path / "sell_result_notices.jsonl"
    notices.deliver_sell_notice(outbox, notice)
    assert notices.deliver_sell_notice(outbox, notice)[0]["delivery"] == "pending_reconcile"
    assert len(calls) == 1


@pytest.mark.app_simulation
def test_app_postings_match_exact_intent_order_and_owned_fill(tmp_path, monkeypatch, delivery):
    receipt, intent, posted = app_data()
    monkeypatch.setattr(notices, "_load_intent_index", lambda _: {"sell-plan": intent})
    monkeypatch.setattr(notices, "_read_jsonl_strict", lambda _: [])
    ownership = [{"event_hash": "exact-fill-hash", "plan_id": "sell-plan",
                  "plan_hash": receipt["plan_hash"], "broker_order_id": "6005007"},
                 {"event_hash": "unrelated-hash", "plan_id": "other-plan",
                  "plan_hash": "other-hash", "broker_order_id": "6005007"}]
    monkeypatch.setattr(notices, "_validate_ownership_chain", lambda _: (ownership, None))
    monkeypatch.setattr(notices.book_b_accounting, "details", lambda _: [posted,
        {**posted, "source_sha256": "unrelated-hash", "realized_pnl": "9999"}])
    payload = {"execution_receipts": [receipt]}
    notices.notify_app_sells(payload, state_dir=tmp_path, outbox=tmp_path / "outbox.jsonl")
    assert "75.20 元" in delivery[0][0][1] and "9999" not in delivery[0][0][1]
    receipt["plan_hash"] = "wrong"
    with pytest.raises(ValueError, match="INTENT_HASH_MISMATCH"):
        notices.notify_app_sells(payload, state_dir=tmp_path, outbox=tmp_path / "outbox.jsonl")


@pytest.mark.app_simulation
def test_replacement_order_notice_includes_predecessor_fill_postings(tmp_path, monkeypatch, delivery):
    receipt, intent, posted = app_data()
    intent["shares"] = 200
    receipt.update(plan_hash=notices._sha256(intent), filled_shares=200)
    first = {**posted, "source_sha256": "first-order-fill", "shares": 100,
             "final_cost_change": "-800", "final_realized_pnl": "20"}
    second = {**posted, "shares": 100, "final_cost_change": "-800", "final_realized_pnl": "20"}
    ownership = [{"event_hash": p["source_sha256"], "plan_id": "sell-plan",
                  "plan_hash": receipt["plan_hash"], "broker_order_id": order}
                 for p, order in [(first, "old-order"), (second, "6005007")]]
    monkeypatch.setattr(notices, "_load_intent_index", lambda _: {"sell-plan": intent})
    monkeypatch.setattr(notices, "_read_jsonl_strict", lambda _: [])
    monkeypatch.setattr(notices, "_validate_ownership_chain", lambda _: (ownership, None))
    monkeypatch.setattr(notices.book_b_accounting, "details", lambda _: [first, second])
    notices.notify_app_sells({"execution_receipts": [receipt]}, state_dir=tmp_path,
                            outbox=tmp_path / "outbox.jsonl")
    assert "40.00 元（+2.50%）" in delivery[0][0][1]


@pytest.mark.app_simulation
@pytest.mark.parametrize("uncertain_first", [False, True])
def test_later_posted_profit_is_a_new_revision_without_resending_old_claim(
        tmp_path, monkeypatch, delivery, uncertain_first):
    receipt, intent, posted = app_data()
    ownership = [{"event_hash": posted["source_sha256"], "plan_id": "sell-plan",
                  "plan_hash": receipt["plan_hash"], "broker_order_id": "6005007"}]
    monkeypatch.setattr(notices, "_load_intent_index", lambda _: {"sell-plan": intent})
    monkeypatch.setattr(notices, "_read_jsonl_strict", lambda _: [])
    monkeypatch.setattr(notices, "_validate_ownership_chain", lambda _: (ownership, None))
    rows = []
    monkeypatch.setattr(notices.book_b_accounting, "details", lambda _: rows)
    calls, responses = delivery
    if uncertain_first:
        responses.append({"wecom": "failed", "wecom_recipients": {"private": {
            "status": "failed", "failure_phase": "response", "retry_safety": "uncertain"}}})
    outbox = tmp_path / "outbox.jsonl"
    payload = {"execution_receipts": [receipt]}
    notices.notify_app_sells(payload, state_dir=tmp_path, outbox=outbox)
    rows.append(posted)
    notices.notify_app_sells(payload, state_dir=tmp_path, outbox=outbox)
    notices.notify_app_sells(payload, state_dir=tmp_path, outbox=outbox)
    assert len(calls) == 2 and "待核算" in calls[0][1] and "75.20 元" in calls[1][1]
    assert len(incident_delivery.pending_notices(outbox)) == int(uncertain_first)


def test_paper_cli_only_notifies_after_the_real_isolated_ledger_commit(tmp_path, monkeypatch, delivery):
    position = closed_position(status="open")
    positions = tmp_path / "positions.jsonl"; positions.write_text(json.dumps(position) + "\n")
    account = tmp_path / "account.json"; account.write_text(json.dumps({
        "initial_capital": 100000, "cash": 87071, "realized_pnl": 0, "fee_rate": .0001}))
    for attr, value in {"OUT_DIR": tmp_path, "POSITIONS_FILE": positions,
                        "ACCOUNT_FILE": account, "TRADES_FILE": tmp_path / "trades.jsonl",
                        "ALERTS_FILE": tmp_path / "alerts.jsonl"}.items():
        monkeypatch.setattr(monitor, attr, value)
    status = {**alert(), "profile": "v5", "triggered": True, "entry_price": 8.08,
              "peak": 8.41, "latest_price": 8.23, "dd_pct": 2.14,
              "dd_threshold_pct": 2, "ret_pct": 1.86, "net_ret_pct": 1.84,
              "fee_rate": .0001, "hold_days": 1, "composite_score": -.03,
              "market_score": 0, "stock_sentiment_score": 0, "realtime_score": 0,
              "kronos_score": 0, "t1_blocked": False, "decision_phase": "eod_discipline"}
    monkeypatch.setattr(monitor, "_client", lambda: object())
    monkeypatch.setattr(monitor, "_is_trading_day", lambda *a: (True, "2026-10-19"))
    monkeypatch.setattr(monitor, "_market_sentiment_context", lambda _: {})
    monkeypatch.setattr(monitor, "_load_stock_sentiment_map", lambda _: {})
    monkeypatch.setattr(monitor, "_load_signal_snapshot_map", lambda: {})
    monkeypatch.setattr(monitor, "_compute_status", lambda *a, **k: status)
    monkeypatch.setattr(monitor, "_realtime_detail", lambda *a: {"trade": 8.23, "buyVol1": 100})
    monkeypatch.setattr(monitor.kol_policy, "load_decision", lambda *a, **k: {})
    monkeypatch.setattr(monitor, "_record_paper_account_risk", lambda *a, **k: {})
    monkeypatch.setattr(monitor, "_write_holdings_snapshot", lambda *a, **k: {
        "cash": 100, "liquidation_value_after_fee": 0, "total_equity_after_exit_fee": 100,
        "open_positions": 0})
    monkeypatch.setattr(monitor.journal, "append_decision", lambda **k: None)
    original_sender = notices.notify_detailed
    def sender(title, body, **kwargs):
        assert json.loads(positions.read_text())["status"] == "closed"
        assert (tmp_path / "trades.jsonl").exists()
        return original_sender(title, body, **kwargs)
    monkeypatch.setattr(notices, "notify_detailed", sender)
    monkeypatch.setattr("sys.argv", ["live_monitor.py", "--execute-sells"])
    monitor.main()
    assert len(delivery[0]) == 1
    assert "已全部卖出" in delivery[0][0][0] and "237.68 元" in delivery[0][0][1]
