"""Economic task closure never fabricates original broker terminality."""
from dataclasses import replace
from pathlib import Path
import json

import pytest

from tests.test_book_b_live_lifecycle import (
    _prior_zero_fill_sell_after_independent_exit, _canonical_sha256, _plan, _bind_plan_intent, _snapshot)
from xiaocao.live.eod_reconciliation import historical_sell_resolutions, assess_eod
from xiaocao.live.book_b_live_lifecycle import (
    project_book_b_live_account, unresolved_prior_sell_codes, open_execution_plan_ids,
    write_book_b_live_settlement, load_latest_book_b_live_settlement)
from xiaocao.live.trading_execution import ExecutionState, ExecutionReceipt

pytestmark = pytest.mark.app_simulation


def test_disposed_lot_closes_task_without_changing_original_order(tmp_path):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    before = (tmp_path / "events.jsonl").read_bytes()
    result = historical_sell_resolutions(tmp_path, snapshot, now=now)
    assert [r["plan_id"] for r in result] == [old.plan_id]
    assert result[0]["status"] == "economically_closed"
    assert result[0]["disposal_order_ids"] == ["order-independent-exit"]
    assert store.current(old.plan_id).state == ExecutionState.UNKNOWN
    assert open_execution_plan_ids(tmp_path) == (old.plan_id,)
    assert old.code in unresolved_prior_sell_codes(tmp_path, trade_date=snapshot["trade_date"])
    assert (tmp_path / "events.jsonl").read_bytes() == before


@pytest.mark.parametrize("change", ["shares", "original_fill", "same_day", "buy", "contradictory_order", "new_same_code_order", "partial_state", "missing_remaining"])
def test_changed_economic_facts_reopen_or_retain_confirmation(tmp_path, change):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    assert historical_sell_resolutions(tmp_path, snapshot, now=now)
    if change == "shares":
        # Positive manual holdings are enough to keep the original order relevant.
        snapshot = _snapshot(shares=100, observed_at=now)
        snapshot["trade_date"] = "2026-09-04"
    elif change in {"contradictory_order", "new_same_code_order"}:
        snapshot["tables"]["today-orders"]["rows"] = [{"证券代码": "000001", "委托编号":
            "6007019" if change == "contradictory_order" else "different-buy"}]
        snapshot["tables"]["today-orders"]["row_count"] = 1
    elif change in {"partial_state", "missing_remaining"}:
        store.append(plan=old, receipt=replace(receipt, **(
            {"state": ExecutionState.PARTIAL} if change == "partial_state" else {"remaining_shares": 0})))
    elif change == "original_fill":
        # A new broker fill without ownership must fail closed, never be ignored.
        store.append(plan=old, receipt=replace(receipt, filled_shares=1, remaining_shares=99))
        with pytest.raises(ValueError, match="EXECUTION_FILL_NOT_OWNED"):
            historical_sell_resolutions(tmp_path, snapshot, now=now)
        return
    elif change == "same_day":
        snapshot["trade_date"] = old.trade_date
    else:
        buy = _bind_plan_intent(tmp_path, replace(_plan(trade_date="2026-09-01"), plan_id="old-unknown-buy"))
        store.append(plan=buy, receipt=ExecutionReceipt(buy.plan_id, buy.plan_hash, ExecutionState.UNKNOWN))
        account = project_book_b_live_account(tmp_path, snapshot, trade_date=snapshot["trade_date"], now=now)
        review = assess_eod(tmp_path, account.as_dict(), snapshot, now=now)
        assert buy.plan_id in review["active_plan_ids"]
        return
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)
    if change == "same_day":
        # Wrong-date table clocks also invalidate evidence before closure.
        with pytest.raises(ValueError):
            historical_sell_resolutions(tmp_path, snapshot, now=now)
    else:
        assert historical_sell_resolutions(tmp_path, snapshot, now=now) == []


def test_all_blockers_and_archived_history_are_reported_together(tmp_path):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    account = project_book_b_live_account(tmp_path, snapshot, trade_date=snapshot["trade_date"], now=now)
    data = account.as_dict()
    data["accounting"] = {**data["accounting"], "status": "cash_reconciliation_required"}
    # Without a fresh snapshot no historical exemption is possible.
    review = assess_eod(tmp_path, data, now=now)
    assert {r["kind"] for r in review["blockers"]} == {"execution", "cash", "fees"}
    review = assess_eod(tmp_path, data, snapshot, now=now, persist=True)
    assert {r["kind"] for r in review["blockers"]} == {"cash", "fees"}
    assert review["active_plan_ids"] == [] and review["status"] == "accounting_pending"
    assert json.loads(Path(review["review_path"]).read_text())["broker_snapshot"] == snapshot


@pytest.mark.parametrize("contradiction", [None, "working", "buy_order", "buy_trade"])
def test_today_exact_full_disposal_supports_closure_without_contradictions(tmp_path, contradiction):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    today = now.replace(day=3)
    snapshot = _snapshot(observed_at=today, broker_fills=[
        ("order-independent-exit", old.code, "SELL", 100, 11)])
    snapshot["trade_date"] = "2026-09-03"
    if contradiction == "working":
        snapshot["tables"]["today-orders"]["rows"][0]["状态说明"] = "已报"
    elif contradiction:
        table = snapshot["tables"]["today-orders" if contradiction == "buy_order" else "today-trades"]
        table["rows"].append({**table["rows"][0], "买卖标志": "买入"})
        table["row_count"] += 1
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)
    assert bool(historical_sell_resolutions(tmp_path, snapshot, now=today)) is (contradiction is None)


def test_formal_settlement_accepts_proved_disposal_only_after_cash_and_fees_complete(tmp_path):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    from tests.book_b_fee_fixtures import proved_fee_account
    account = proved_fee_account(tmp_path, snapshot)
    settled = write_book_b_live_settlement(tmp_path, account, now=now, broker_snapshot=snapshot)
    assert settled["eod_review"]["active_plan_ids"] == []
    assert settled["eod_review"]["historical_order_resolutions"][0]["plan_id"] == old.plan_id
    assert load_latest_book_b_live_settlement(tmp_path)["settlement_sha256"] == settled["settlement_sha256"]
    assert store.current(old.plan_id).state == ExecutionState.UNKNOWN


def test_later_terminal_confirmation_keeps_dated_settlement_readable(tmp_path):
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    from tests.book_b_fee_fixtures import proved_fee_account
    settled = write_book_b_live_settlement(tmp_path, proved_fee_account(tmp_path, snapshot),
        now=now, broker_snapshot=snapshot)
    store.append(plan=old, receipt=replace(receipt, state=ExecutionState.CANCELLED,
        submit_chain_uncertain=False, cancel_chain_uncertain=False))
    assert historical_sell_resolutions(tmp_path, snapshot, now=now) == []
    assert load_latest_book_b_live_settlement(tmp_path)["settlement_sha256"] == settled["settlement_sha256"]
    # A valid later append is allowed; alteration of the sealed prefix is not.
    path = tmp_path / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["receipt"]["broker_order_id"] = "altered"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ValueError, match="EOD_REVIEW_EXECUTION_PREFIX_CHANGED"):
        load_latest_book_b_live_settlement(tmp_path)


@pytest.mark.parametrize("fault", [None, "owner", "slot", "snapshot", "changed_ownership"])
def test_original_archive_review_has_no_business_effects_and_checks_source(tmp_path, monkeypatch, fault):
    from scripts.book_b_eod_review import review_original_receipt
    from xiaocao.live.eod_automation_gate import claim_eod_slot
    from tests.book_b_fee_fixtures import proved_fee_account
    old, now, store, receipt, snapshot = _prior_zero_fill_sell_after_independent_exit(tmp_path)
    account = proved_fee_account(tmp_path, snapshot).as_dict()
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-eod")
    monkeypatch.setenv("CODEX_THREAD_ID", "original-owner")
    identity = claim_eod_slot(tmp_path, "app", snapshot["trade_date"])
    path = tmp_path / "runs/intraday/archive/original.json"
    path.parent.mkdir(parents=True)
    body = {"phase": "eod", "route": "native-app", "execute_sells_requested": False,
        "trade_date": snapshot["trade_date"], "run_id": "original", "run_receipt_path": str(path),
        "automation_identity": identity, "account": account, "broker_snapshot": snapshot}
    if fault == "owner":
        monkeypatch.setenv("CODEX_THREAD_ID", "peer")
    elif fault == "slot":
        body["automation_identity"] = {**identity, "branch": "paper"}
    elif fault == "snapshot":
        body["account"]["broker_snapshot_sha256"] = "wrong"
    elif fault == "changed_ownership":
        from tests.test_book_b_live_lifecycle import _record_fill
        _record_fill(tmp_path, replace(_plan(trade_date="2026-09-04"), plan_id="later-buy"),
            price=10, event_id="later-buy")
    path.write_text(json.dumps(body))
    before = {p: (tmp_path / p).read_bytes() for p in ["events.jsonl", "book_b_ownership_evidence.jsonl"]}
    if fault:
        with pytest.raises(ValueError):
            review_original_receipt(path, tmp_path, root=tmp_path)
        assert not (tmp_path / "eod_reviews").exists()
    else:
        result = review_original_receipt(path, tmp_path, root=tmp_path)
        assert result["eod_review"]["active_plan_ids"] == []
        assert result["evidence_status"] == "dated_original_observation"
        assert result["app_queries"] == result["orders_created"] == 0
        assert result["settlement_written"] is False
    assert all((tmp_path / p).read_bytes() == data for p, data in before.items())
    assert not (tmp_path / "settlements").exists()
