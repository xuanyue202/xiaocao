"""Accounting effects and recovery, with the existing proved-fill fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
import json
import csv
from pathlib import Path
import sqlite3

import pytest

from xiaocao.live import book_b_accounting as ledger
from xiaocao.live.book_b_capital import digest, flows, verify_account
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account, write_book_b_live_settlement
from tests.test_book_b_available_capital import activate, with_cash, project
from tests.test_book_b_live_lifecycle import _plan, _record_fill, _snapshot, NOW, EOD_NOW

pytestmark = pytest.mark.app_simulation


def observed(root, snapshot):
    return project_book_b_live_account(root, snapshot, trade_date=snapshot["trade_date"],
        now=datetime.fromisoformat(snapshot["observed_at"]))


def cash_proof(snapshot, *, kind="FEE", amount="-5.00", event_id="cash-1"):
    event = {"event_id": event_id, "kind": kind, "amount": amount,
             "fee_basis": "additional_non_trade_charge"}
    statement = {"schema_version": "foundersc-native-cash-statement.v1",
        "source": "foundersc_native_app", "account_binding": "proven",
        "fund_account_binding_sha256": snapshot["fund_account_binding_sha256"],
        "observed_at": snapshot["observed_at"], "rows": [event]}
    statement["receipt_sha256"] = digest(statement)
    return {"event_id": event_id, "statement": statement, "broker_snapshot": snapshot}


def test_owned_partial_sales_allocate_fee_cost_and_residual_cents(tmp_path):
    buy = _record_fill(tmp_path, replace(_plan(), shares=300), price=10, event_id="buy")
    _record_fill(tmp_path, _plan(side="SELL", lot_id=buy.plan_id), price=11, event_id="sell1")
    first = ledger.sync_journal(tmp_path)
    assert first["ledger_cash"] == "28099.59"
    assert first["realized_pnl"] == "99.79"
    book = ledger.replay_owned(tmp_path)
    assert book.lots[buy.plan_id]["cost_cents"] == 200020
    detail = ledger.details(tmp_path)[1]
    assert ledger.details(tmp_path)[0]["confirmation_status"] == "legacy_strategy_seed"
    assert detail["owned_lot_id"] == buy.plan_id and detail["source_execution_event_id"]
    assert ledger.number(detail["fill_price"]) == 10 and ledger.number(detail["fill_notional"]) == 3000
    assert detail["native_trade_id"] is None
    last = replace(_plan(side="SELL", lot_id=buy.plan_id), shares=200, plan_id="book-b:2026-09-01:000001.XSHE:SELL:last")
    _record_fill(tmp_path, last, price=11, event_id="sell2")
    final = ledger.sync_journal(tmp_path)
    assert final["ledger_cash"] == "30299.37" and final["realized_pnl"] == "299.37"
    assert ledger.replay_owned(tmp_path).lots[buy.plan_id]["cost_cents"] == 0
    assert sum(int(round(float(r["realized_pnl"])*100)) for r in ledger.details(tmp_path)) == 29937


def test_open_buy_cost_is_not_realized_loss_and_nav_excludes_future_exit_fee(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    buy = _record_fill(tmp_path, replace(_plan(), shares=6000), price=10, event_id="large")
    account = observed(tmp_path, with_cash(_snapshot(shares=6000, price=11,
        broker_fills=(("order-large", buy.code, "BUY", 6000, 10),)), 39994))
    report = account.accounting
    assert report["realized_pnl"] == "0.00"
    assert report["unrealized_pnl"] == report["cumulative_pnl"] == "5994.00"
    assert report["marked_nav"] == "105994.00"
    assert report["estimated_exit_fee"] == "6.60"
    assert report["liquidation_nav"] == "105987.40"
    assert account.realized_cash_delta == -60006  # retained legacy compatibility


@pytest.mark.parametrize("cash,risk", [(100005, "30000.000000"), (99995, "29998.500000")])
def test_unexplained_cash_is_not_capital_profit_or_risk_reset(tmp_path, cash, risk):
    activate(tmp_path)
    first = project(tmp_path, with_cash(_snapshot(), 100000))
    original = (tmp_path/"capital_flows.jsonl").read_bytes()
    account = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), cash))
    assert account.cash == min(cash, 100000) and account.net_external_flow_total == 70000
    assert account.capital_flow_head_sha256 == first.capital_flow_head_sha256
    assert account.capital_unit_factor == first.capital_unit_factor
    assert account.accounting["cumulative_pnl"] is None
    assert account.accounting["status"] == "cash_discrepancy_tolerated"
    assert account.accounting["observed_cash"] == f"{cash:.2f}"
    assert account.accounting["cash_difference"] == f"{cash-100000:.2f}"
    assert str(verify_account(tmp_path, account.as_dict())) == risk
    assert (tmp_path/"capital_flows.jsonl").read_bytes() == original


def test_cash_statement_fee_is_loss_and_exactly_once(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    snapshot = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995)
    proof = cash_proof(snapshot)
    first = ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=1))
    assert ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=1)) == first
    account = observed(tmp_path, snapshot)
    assert account.accounting["realized_pnl"] == account.accounting["cumulative_pnl"] == "-5.00"
    assert account.net_external_flow_total == 70000 and len(flows(tmp_path)) == 1
    # A later explicitly approved capital movement uses the fee-reconciled NAV.
    topped = project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=2)), 109995))
    assert topped.accounting["net_contributed_capital"] == "110000.00"
    assert topped.accounting["cumulative_pnl"] == "-5.00"
    assert verify_account(tmp_path, topped.as_dict()) == verify_account(tmp_path, account.as_dict())


def test_income_requires_owned_entitlement_or_owned_interest_period(tmp_path, monkeypatch):
    from xiaocao.live import trading_execution
    monkeypatch.setattr(trading_execution, "_utcnow", lambda: NOW)
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    buy = _record_fill(tmp_path, _plan(), price=10, event_id="owned")
    entitlement = with_cash(_snapshot(shares=100, price=10,
        broker_fills=(("order-owned", buy.code, "BUY", 100, 10),)), 98999.90)
    observed(tmp_path, entitlement)
    paid = with_cash(_snapshot(shares=100, price=10, observed_at=NOW+timedelta(seconds=1),
        broker_fills=(("order-owned", buy.code, "BUY", 100, 10),)), 99004.90)
    proof = cash_proof(paid, kind="DIVIDEND", amount="5.00", event_id="dividend")
    event = proof["statement"]["rows"][0]
    event.update(code=buy.code, owned_lot_id=buy.plan_id, entitlement_trade_date=entitlement["trade_date"])
    proof["entitlement_snapshot"] = entitlement
    proof["statement"].pop("receipt_sha256")
    proof["statement"]["receipt_sha256"] = digest(proof["statement"])
    ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=1))
    assert observed(tmp_path, paid).accounting["realized_pnl"] == "5.00"
    changed = dict(proof, entitlement_snapshot=with_cash(_snapshot(shares=200, price=10), 98000))
    with pytest.raises(ValueError, match="DIVIDEND_OWNERSHIP_UNPROVEN"):
        ledger.record_cash_event(tmp_path, changed, now=NOW+timedelta(seconds=1))
    # A total-account interest row needs a period wholly after cash-policy approval.
    policy_path = tmp_path/"capital_policy.json"
    cfg = json.loads(policy_path.read_text())
    cfg.pop("policy_sha256")
    cfg["approved_at"] = (NOW-timedelta(days=1)).isoformat()
    cfg["policy_sha256"] = digest(cfg)
    policy_path.write_text(json.dumps(cfg))
    interest = cash_proof(with_cash(_snapshot(shares=100, price=10,
        observed_at=NOW+timedelta(seconds=2),
        broker_fills=(("order-owned", buy.code, "BUY", 100, 10),)), 99005.90),
        kind="INTEREST", amount="1.00", event_id="interest")
    event = interest["statement"]["rows"][0]
    event.update(interest_basis="available_cash", period_start=NOW.isoformat(),
                 period_end=(NOW+timedelta(seconds=1)).isoformat())
    interest["statement"].pop("receipt_sha256")
    interest["statement"]["receipt_sha256"] = digest(interest["statement"])
    ledger.record_cash_event(tmp_path, interest, now=NOW+timedelta(seconds=2))
    assert observed(tmp_path, interest["broker_snapshot"]).accounting["realized_pnl"] == "6.00"


def test_current_observation_rejects_later_cash_event_but_historical_proof_survives(tmp_path):
    activate(tmp_path)
    account = project(tmp_path, with_cash(_snapshot(), 100000))
    paid = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995)
    ledger.record_cash_event(tmp_path, cash_proof(paid), now=NOW+timedelta(seconds=1))
    assert ledger.verify_observation(tmp_path, account.accounting) == account.accounting
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        ledger.verify_observation(tmp_path, account.accounting, current=True)


def test_statement_export_shares_journal_and_does_not_mix_stale_mark(tmp_path):
    from scripts.book_b_accounting import export_statement
    activate(tmp_path)
    account = project(tmp_path, with_cash(_snapshot(), 100000))
    first = export_statement(tmp_path, tmp_path/"reports")
    assert first["marked_nav"] == "100000.00" and first["cumulative_pnl"] == "0.00"
    original = Path(first["report_path"]).read_bytes()
    proof = cash_proof(with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995))
    ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=1))
    stale = export_statement(tmp_path, tmp_path/"reports")
    assert stale["status"] == "stale_or_missing_mark" and stale["marked_nav"] is None
    assert stale["cumulative_pnl"] is None
    assert stale["report_path"] != first["report_path"]
    assert Path(first["report_path"]).read_bytes() == original
    saved = json.loads(Path(stale["report_path"]).read_text())
    assert saved["valuation"] == account.accounting
    observed(tmp_path, proof["broker_snapshot"])
    current = export_statement(tmp_path, tmp_path/"reports")
    assert current["realized_pnl"] == current["cumulative_pnl"] == "-5.00"
    with Path(current["details_path"]).open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len([row for row in rows if row["kind"] == "FEE"]) == 1
    assert rows[-1]["source_event_id"] == "cash-1"


def test_out_of_order_cash_snapshot_cannot_poison_capital_or_create_observation(tmp_path):
    from xiaocao.live.book_b_capital import allocate_cash
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    newer = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=2)), 99995)
    ledger.record_cash_event(tmp_path, cash_proof(newer), now=NOW+timedelta(seconds=2))
    older = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 110000)
    original = (tmp_path/"capital_flows.jsonl").read_bytes()
    with pytest.raises(ValueError, match="CASH_SNAPSHOT_REGRESSION"):
        observed(tmp_path, older)
    with pytest.raises(ValueError, match="CASH_SNAPSHOT_REGRESSION"):
        allocate_cash(tmp_path, base_cash=ledger.replay_owned(tmp_path).cash, liquidation=0,
            ownership_head=None, snapshot=older, allocation_reference="explicit-current-capital")
    assert (tmp_path/"capital_flows.jsonl").read_bytes() == original and len(flows(tmp_path)) == 1
    recovered = project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=3)), 109995))
    assert recovered.accounting["cumulative_pnl"] == "-5.00" and len(flows(tmp_path)) == 2


def test_intent_only_buy_does_not_certify_cash_or_profit_reconciliation(tmp_path):
    from tests.test_book_b_live_lifecycle import _bind_plan_intent
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    _bind_plan_intent(tmp_path, _plan())
    account = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995))
    assert account.accounting["status"] == "cash_reserve_reconciliation_required"
    assert account.accounting["cash_difference"] is None and account.accounting["cumulative_pnl"] is None
    assert account.accounting["broker_available_cash"] == "99995.00"
    # A bare intent has no broker effect, but another negative cash difference
    # must still reduce risk NAV even while PnL classification stays pending.
    assert str(verify_account(tmp_path, account.as_dict())) == "29998.500000"
    assert len(flows(tmp_path)) == 1


def test_claimed_buy_reserve_is_not_counted_as_cash_loss(tmp_path):
    from tests.test_book_b_live_lifecycle import _bind_plan_intent
    from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionState, ExecutionStore

    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    plan = _plan()
    plan = _bind_plan_intent(tmp_path, plan)
    ExecutionStore(tmp_path / "events.jsonl").append(plan=plan,
        receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.CLAIMED,
            remaining_shares=plan.shares, submit_claim_id="claim-1"), kind="durable_claim")
    account = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995))
    assert account.accounting["status"] == "cash_reserve_reconciliation_required"
    assert account.accounting["broker_available_cash"] == "99995.00"
    assert account.accounting["cumulative_pnl"] is None
    assert str(verify_account(tmp_path, account.as_dict())) == "30000.000000"


def test_intent_only_buy_allows_conservative_risk_mark_until_execution_event(tmp_path, monkeypatch):
    from xiaocao.live.account_risk import NavObservation
    from xiaocao.live.book_b_capital import has_open_buy_with_possible_effect
    from xiaocao.live.live_decision_support import evaluate_live_risk
    from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionState, ExecutionStore
    import xiaocao.live.live_decision_support as support
    from tests.test_book_b_live_lifecycle import _bind_plan_intent

    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    plan = _plan()
    plan = _bind_plan_intent(tmp_path, plan)
    stamp = NOW + timedelta(seconds=1)
    snapshot = with_cash(_snapshot(observed_at=stamp), 100000)
    account = observed(tmp_path, snapshot)
    assert account.accounting["status"] == "cash_reserve_reconciliation_required"
    assert account.accounting["cumulative_pnl"] is None
    assert has_open_buy_with_possible_effect(tmp_path) is False

    settled = NavObservation("2026-08-31", 30000, "live:B", 30000, 0,
        "book_b_cash_plus_liquidation_after_exit_fee", "settled",
        "2026-08-31T15:05:00+08:00", "a" * 64)
    monkeypatch.setattr(support, "expected_settlement_date", lambda *_: "2026-08-31")
    monkeypatch.setattr(support, "load_live_nav_history", lambda *_args, **_kwargs: [settled])
    allowed = evaluate_live_risk(tmp_path, now=stamp, account=account,
        trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert allowed.status == "NORMAL" and allowed.nav is not None
    assert account.accounting["cumulative_pnl"] is None

    store = ExecutionStore(tmp_path / "events.jsonl")
    store.append(plan=plan,
        receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PLANNED,
            remaining_shares=plan.shares), kind="plan_created")
    store.append(plan=plan,
        receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PREPARED,
            remaining_shares=plan.shares), kind="transition")
    assert has_open_buy_with_possible_effect(tmp_path) is False
    prepared_risk = evaluate_live_risk(tmp_path, now=stamp, account=account,
        trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert prepared_risk.status == "NORMAL" and prepared_risk.nav is not None

    store.append(plan=plan,
        receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.UNKNOWN,
            reason="possible_submit", remaining_shares=plan.shares,
            submit_claim_id="claim-1", next_action="reconcile_only"),
        kind="possible_submit")
    assert has_open_buy_with_possible_effect(tmp_path) is True
    blocked = evaluate_live_risk(tmp_path, now=stamp, account=account,
        trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert blocked.status == "BLOCKED" and blocked.nav is None


def test_proved_cash_reversal_preserves_original_and_all_cash_consumers(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    paid = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 99995)
    fee = ledger.record_cash_event(tmp_path, cash_proof(paid), now=NOW+timedelta(seconds=1))
    returned = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=2)), 100000)
    proof = cash_proof(returned, kind="REVERSAL", amount="5.00", event_id="correction")
    proof["statement"]["rows"][0]["reverses_entry_sha256"] = fee["entry_sha256"]
    proof["statement"].pop("receipt_sha256")
    proof["statement"]["receipt_sha256"] = digest(proof["statement"])
    result = ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=2))
    assert ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=2)) == result
    report = observed(tmp_path, returned).accounting
    assert report["cumulative_pnl"] == report["realized_pnl"] == "0.00"
    assert ledger.cash_adjustment(tmp_path) == 0 and len(flows(tmp_path)) == 1
    assert ledger.details(tmp_path)[-1]["reverses_entry_sha256"] == fee["entry_sha256"]
    invalid = cash_proof(returned, kind="REVERSAL", amount="-5.00", event_id="reverse-reversal")
    invalid["statement"]["rows"][0]["reverses_entry_sha256"] = result["entry_sha256"]
    invalid["statement"].pop("receipt_sha256")
    invalid["statement"]["receipt_sha256"] = digest(invalid["statement"])
    with pytest.raises(ValueError, match="REVERSAL_UNPROVEN"):
        ledger.record_cash_event(tmp_path, invalid, now=NOW+timedelta(seconds=2))
    proof["event_id"] = proof["statement"]["rows"][0]["event_id"] = "duplicate-correction"
    proof["statement"].pop("receipt_sha256")
    proof["statement"]["receipt_sha256"] = digest(proof["statement"])
    with pytest.raises(ValueError, match="REVERSAL_ALREADY_POSTED"):
        ledger.record_cash_event(tmp_path, proof, now=NOW+timedelta(seconds=2))


@pytest.mark.parametrize("fault", ["read", "write"])
@pytest.mark.parametrize("filled", [False, True])
def test_accounting_storage_failure_does_not_block_protective_sell(tmp_path, monkeypatch, fault, filled):
    from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
    from xiaocao.live.book_b_live_morning import load_book_b_live_capital_basis
    from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionState, ExecutionStore
    from xiaocao.live.live_decision_support import evaluate_live_risk
    buy = _record_fill(tmp_path, _plan(trade_date="2026-08-31"), price=10, event_id="owned")
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("attempt to write a readonly database")
    monkeypatch.setattr(ledger, "cash_adjustment" if fault == "read" else "observe_account", unavailable)
    snapshot = _snapshot(shares=100, sellable=100, price=9.2)
    with pytest.raises(sqlite3.OperationalError):
        observed(tmp_path, snapshot)
    degraded = project_book_b_live_account(tmp_path, snapshot, trade_date="2026-09-01", now=NOW,
        allow_accounting_unavailable=True)
    assert degraded.accounting["status"] == "unavailable" and degraded.as_dict()["cash"] is None
    assert degraded.as_dict()["settled_nav"] is None
    with pytest.raises(ValueError, match="CURRENT_ACCOUNTING_UNAVAILABLE"):
        load_book_b_live_capital_basis(tmp_path, trade_date="2026-09-01", current_account=degraded)
    with pytest.raises(ValueError, match="SETTLEMENT_ACCOUNTING_UNAVAILABLE"):
        write_book_b_live_settlement(tmp_path, degraded, now=EOD_NOW)
    seen = []
    def execute(plan):
        seen.append(plan)
        if filled:
            _record_fill(tmp_path, plan, price=9.19, event_id="protective")
            return ExecutionStore(tmp_path/"events.jsonl").current(plan.plan_id)
        return ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.REJECTED,
            reason="TEST_NO_APP_WRITE", remaining_shares=plan.shares)
    def snapshot_provider():
        return (_snapshot(broker_fills=(("order-protective", buy.code, "SELL", 100, 9.19),))
                if filled and seen else snapshot)
    result = run_book_b_live_intraday(state_dir=tmp_path, freeze_dir=tmp_path,
        trade_date="2026-09-01", phase="precheck", account_snapshot_provider=snapshot_provider,
        status_provider=lambda lots: [{"owned_lot_id": buy.plan_id, "triggered": True,
            "sell_reason": "HARD_STOP", "decision_phase": "risk_floor", "latest_price": 9.2,
            "market_guard_status": "ok", "market_guard_observed_at": NOW,
            "market_guard_down_price": 9., "best_bid_price": 9.19, "best_bid_volume": 1000}],
        execute=execute, now=lambda: NOW, strategy_sha="a"*40, policy_root=tmp_path/"policy",
        trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert len(seen) == 1 and seen[0].side == "SELL"
    assert result.execution_receipts and result.account["accounting"]["status"] == "unavailable"
    assert result.risk_receipt["status"] == "BLOCKED" and result.risk_receipt["nav"] is None
    if filled:
        assert result.execution_receipts[0]["filled_shares"] == 100
    risk = evaluate_live_risk(tmp_path, now=NOW, account=degraded,
        account_snapshot_provider=lambda: snapshot, trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert risk.status == "BLOCKED" and risk.nav is None
    risk_event = json.loads((tmp_path/"account_risk"/"live_B.jsonl").read_text().splitlines()[-1])
    assert risk_event["capital_basis"] is None
    assert risk_event["receipt"]["strategy_nav"] is None
    # Original source corruption remains fatal even on the protective path.
    with (tmp_path/"book_b_ownership_evidence.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError):
        project_book_b_live_account(tmp_path, snapshot, trade_date="2026-09-01", now=NOW,
            allow_accounting_unavailable=True)


def test_protective_accounting_fallback_cannot_hide_capital_account_mismatch(tmp_path, monkeypatch):
    activate(tmp_path, binding="b"*64)
    _record_fill(tmp_path, _plan(trade_date="2026-08-31"), price=10, event_id="owned")
    def unavailable(*args, **kwargs):
        pytest.fail("capital account binding must be checked before accounting storage")
    monkeypatch.setattr(ledger, "cash_adjustment", unavailable)
    with pytest.raises(ValueError, match="BOOK_B_CAPITAL_ACCOUNT_MISMATCH"):
        project_book_b_live_account(tmp_path, _snapshot(shares=100, sellable=100),
            trade_date="2026-09-01", now=NOW, allow_accounting_unavailable=True)


@pytest.mark.parametrize("fault", ["binding", "hash", "duplicate", "commission_total", "manual_dividend"])
def test_cash_statement_rejects_unproved_or_mixed_account_events(tmp_path, fault):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    proof = cash_proof(with_cash(_snapshot(), 99995))
    statement = proof["statement"]
    if fault == "binding": statement["fund_account_binding_sha256"] = "b"*64
    if fault == "duplicate": statement["rows"] *= 2
    if fault == "commission_total": statement["rows"][0]["fee_basis"] = "total_trade_commission"
    if fault == "manual_dividend": statement["rows"][0].update(kind="DIVIDEND", amount="5.00", owned_lot_id="manual")
    statement.pop("receipt_sha256")
    statement["receipt_sha256"] = digest(statement)
    if fault == "hash": statement["rows"][0]["amount"] = "-7.00"
    before = ledger.sync_journal(tmp_path)
    with pytest.raises(ValueError):
        ledger.record_cash_event(tmp_path, proof, now=NOW)
    assert ledger.sync_journal(tmp_path) == before


def test_import_atomic_rollback_and_retry(tmp_path, monkeypatch):
    _record_fill(tmp_path, _plan(), price=10, event_id="buy")
    post = ledger._post
    def interrupted(db, body):
        result = post(db, body)
        if body["kind"] == "BUY": raise RuntimeError("interrupted after postings")
        return result
    monkeypatch.setattr(ledger, "_post", interrupted)
    with pytest.raises(RuntimeError): ledger.sync_journal(tmp_path)
    with sqlite3.connect(tmp_path/ledger.DATABASE) as db:
        assert db.execute("SELECT count(*) FROM entries").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM postings").fetchone()[0] == 0
    monkeypatch.setattr(ledger, "_post", post)
    assert ledger.sync_journal(tmp_path)["entry_count"] == 2


def test_parallel_import_and_backup_restore_preserve_unique_postings(tmp_path):
    _record_fill(tmp_path, _plan(), price=10, event_id="buy")
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda _: ledger.sync_journal(tmp_path), range(8)))
    assert all(r == result[0] for r in result)
    backup = tmp_path/"restored"/ledger.DATABASE
    proof = ledger.backup(tmp_path, backup)
    assert proof["journal_head_sha256"] == result[0]["journal_head_sha256"]
    assert ledger.details(tmp_path/"restored") == ledger.details(tmp_path)
    with sqlite3.connect(backup) as db:
        with pytest.raises(sqlite3.IntegrityError): db.execute("UPDATE postings SET amount_cents=1")


def test_source_regression_and_saved_observation_tamper_are_rejected(tmp_path):
    activate(tmp_path)
    account = project(tmp_path, with_cash(_snapshot(), 100000))
    forged = dict(account.accounting, cash="200000.00")
    forged.pop("receipt_sha256"); forged["receipt_sha256"] = digest(forged)
    with pytest.raises(ValueError): ledger.verify_observation(tmp_path, forged)
    (tmp_path/"capital_flows.jsonl").write_text("")
    with pytest.raises(ValueError, match="SOURCE_REGRESSION"): ledger.sync_journal(tmp_path)


def test_settlement_rejects_unexplained_cash_and_changed_observation_date(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    account = observed(tmp_path, with_cash(_snapshot(observed_at=EOD_NOW), 100010))
    with pytest.raises(ValueError, match="CASH_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    changed = replace(account, broker_snapshot_observed_at=(EOD_NOW+timedelta(days=1)).isoformat())
    with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
        write_book_b_live_settlement(tmp_path, changed, now=EOD_NOW)


@pytest.mark.parametrize("difference", ["-9.99", "-0.01", "0.01", "2.00", "9.99"])
def test_small_cash_difference_settles_conservatively_without_posting(tmp_path, difference):
    activate(tmp_path)
    first = project(tmp_path, with_cash(_snapshot(), 100000))
    source = (tmp_path / "capital_flows.jsonl").read_bytes()
    journal = ledger.sync_journal(tmp_path)
    amount = ledger.number(difference)
    snapshot = with_cash(_snapshot(observed_at=EOD_NOW), float(100000 + amount))
    account = observed(tmp_path, snapshot)
    assert observed(tmp_path, snapshot) == account
    assert account.cash == float(100000 + min(amount, 0))
    assert account.settled_nav == account.cash
    assert account.accounting["cash_difference"] == difference
    assert account.accounting["status"] == "cash_discrepancy_tolerated"
    assert account.accounting["cumulative_pnl"] is None
    assert account.capital_flow_head_sha256 == first.capital_flow_head_sha256
    assert account.capital_unit_factor == first.capital_unit_factor
    settled = write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    assert settled["accounting"]["status"] == "cash_discrepancy_tolerated"
    assert settled["accounting"]["cumulative_pnl"] is None
    assert settled["settled_nav"] == account.cash
    assert ledger.sync_journal(tmp_path) == journal
    assert (tmp_path / "capital_flows.jsonl").read_bytes() == source


@pytest.mark.parametrize("difference", [-10, 10, -10.01, 10.01])
def test_ten_yuan_or_larger_does_not_settle(tmp_path, difference):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    account = observed(tmp_path, with_cash(_snapshot(observed_at=EOD_NOW), 100000 + difference))
    assert account.accounting["status"] == "cash_reconciliation_required"
    with pytest.raises(ValueError, match="CASH_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


def test_small_observations_cannot_split_a_larger_cash_difference(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    first = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 100006))
    assert first.accounting["status"] == "cash_discrepancy_tolerated"
    second = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=2)), 100012))
    assert second.accounting["status"] == "cash_reconciliation_required"
    assert second.accounting["cash_difference"] == "12.00"
    assert ledger.sync_journal(tmp_path)["ledger_cash"] == "100000.00"


def test_approved_two_yuan_flow_is_counted_once_before_tolerance(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    topped = project(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 100002))
    repeated = observed(tmp_path, with_cash(_snapshot(observed_at=NOW+timedelta(seconds=2)), 100002))
    assert repeated.cash == 100002
    assert repeated.accounting["cash_difference"] == "0.00"
    assert repeated.accounting["cumulative_pnl"] == "0.00"
    assert repeated.net_external_flow_total == topped.net_external_flow_total == 70002
    assert len(flows(tmp_path)) == 2


def test_tiny_delta_cannot_override_unresolved_sell(tmp_path):
    from tests.test_book_b_live_lifecycle import _bind_plan_intent
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    _bind_plan_intent(tmp_path, _plan(side="SELL", lot_id="unresolved-lot"))
    account = observed(tmp_path, with_cash(_snapshot(observed_at=EOD_NOW), 100002))
    assert account.accounting["status"] == "cash_reconciliation_required"
    assert account.accounting["cash_integrity_proven"] is False
    with pytest.raises(ValueError, match="OPEN_EXECUTION_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


@pytest.mark.parametrize("fault", ["stale", "hash", "binding"])
def test_tiny_delta_cannot_override_invalid_snapshot(tmp_path, fault):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    snapshot = with_cash(_snapshot(observed_at=NOW+timedelta(seconds=1)), 100002)
    current = NOW+timedelta(seconds=1)
    if fault == "stale":
        current += timedelta(seconds=301)
    elif fault == "hash":
        snapshot["funds_summary"]["available_cash"] = 100003
    else:
        snapshot.pop("snapshot_sha256")
        snapshot["fund_account_binding_sha256"] = "b" * 64
        snapshot["snapshot_sha256"] = digest(snapshot)
    with pytest.raises(ValueError):
        project_book_b_live_account(tmp_path, snapshot, trade_date=snapshot["trade_date"], now=current)


@pytest.mark.parametrize("fault", ["duplicate_trade", "missing_trade", "duplicate_order", "missing_ownership"])
def test_tiny_delta_cannot_hide_bad_fill_evidence(tmp_path, fault):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    buy = _record_fill(tmp_path, _plan(), price=10, event_id="owned")
    snapshot = with_cash(_snapshot(shares=100, price=10, observed_at=EOD_NOW,
        broker_fills=(("order-owned", buy.code, "BUY", 100, 10),)), 99001.90)
    snapshot.pop("snapshot_sha256")
    if fault == "duplicate_trade":
        table = snapshot["tables"]["today-trades"]
        table["rows"].append(dict(table["rows"][0]))
        table["row_count"] += 1
    elif fault == "missing_trade":
        snapshot["tables"]["today-trades"].update(rows=[], row_count=0)
    elif fault == "duplicate_order":
        table = snapshot["tables"]["today-orders"]
        table["rows"].append(dict(table["rows"][0]))
        table["row_count"] += 1
    else:
        (tmp_path / "book_b_ownership_evidence.jsonl").write_text("")
    snapshot["snapshot_sha256"] = digest(snapshot)
    with pytest.raises(ValueError):
        observed(tmp_path, snapshot)


def test_tiny_delta_does_not_use_a_retimed_stale_table(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    snapshot = with_cash(_snapshot(observed_at=EOD_NOW), 100002)
    snapshot.pop("snapshot_sha256")
    snapshot["tables"]["today-trades"]["observed_at"] = (EOD_NOW-timedelta(minutes=6)).isoformat()
    snapshot["snapshot_sha256"] = digest(snapshot)
    account = observed(tmp_path, snapshot)
    assert account.accounting["status"] == "cash_reconciliation_required"
    assert account.accounting["cash_integrity_proven"] is False
    with pytest.raises(ValueError, match="CASH_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


def test_tolerated_observation_must_still_be_fresh_when_settled(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    account = observed(tmp_path, with_cash(_snapshot(observed_at=EOD_NOW), 100002))
    with pytest.raises(ValueError, match="CASH_OBSERVATION_STALE"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW+timedelta(seconds=301))
