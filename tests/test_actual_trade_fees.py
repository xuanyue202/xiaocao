"""Actual fee accounting contracts; temporary ledgers, no APP or transport."""
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import json
import sqlite3

import pytest

from xiaocao.live import book_b_accounting as ledger
from xiaocao.live.book_b_capital import digest, flows, verify_account
from xiaocao.live.book_b_live_lifecycle import write_book_b_live_settlement
from tests.book_b_fee_fixtures import fee_proof
from tests.test_book_b_accounting import observed
from tests.test_book_b_available_capital import activate, project, with_cash
from tests.test_book_b_live_lifecycle import _plan, _record_fill, _snapshot, NOW, EOD_NOW

pytestmark = pytest.mark.app_simulation


@pytest.fixture(autouse=True)
def no_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("fee accounting must not access HTTP/notifications")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("xiaocao.live.notify.macos_notify", forbidden)
    monkeypatch.setattr("xiaocao.live.trading_execution._utcnow", lambda: NOW)




def import_fees(root, proof):
    return ledger.record_trade_fees(root, proof,
        now=datetime.fromisoformat(proof["broker_snapshot"]["observed_at"]))


def scenario(root):
    activate(root)
    project(root, with_cash(_snapshot(), 100000))
    buy = _record_fill(root, replace(_plan(), shares=300), price=10, event_id="buy")
    _record_fill(root, _plan(side="SELL", lot_id=buy.plan_id), price=11, event_id="sell1")
    fills = (("order-buy", buy.code, "BUY", 300, 10), ("order-sell1", buy.code, "SELL", 100, 11))
    snapshot = with_cash(_snapshot(shares=200, price=11, broker_fills=fills,
                                  observed_at=NOW+timedelta(seconds=1)), 98089.45)
    return buy, fills, snapshot


def journal_entries(root):
    with sqlite3.connect(root / ledger.DATABASE) as db:
        return ledger._entries(db)


def test_actual_fees_correct_buy_cost_partial_sale_and_preserve_history(tmp_path):
    buy, fills, snapshot = scenario(tmp_path)
    before = observed(tmp_path, snapshot).accounting
    originals = journal_entries(tmp_path)
    capital = (tmp_path / "capital_flows.jsonl").read_bytes()
    proof = fee_proof(tmp_path, snapshot, "order-buy", "5.00")
    first = import_fees(tmp_path, proof)
    assert import_fees(tmp_path, proof) == first
    import_fees(tmp_path, fee_proof(tmp_path, snapshot, "order-sell1", "5.55"))
    account = observed(tmp_path, snapshot)
    result = account.accounting
    assert result["fee_status"] == "actual_fees_complete" and result["pending_fee_orders"] == []
    assert result["ledger_cash"] == result["cash"] == "98089.45"
    assert result["remaining_cost"] == result["lots"][0]["remaining_cost"] == "2003.33"
    assert result["realized_pnl"] == "92.78" and result["unrealized_pnl"] == "196.67"
    assert result["cumulative_pnl"] == "289.45" and result["estimated_exit_fee"] == "0.22"
    assert journal_entries(tmp_path)[:len(originals)] == originals
    assert ledger.verify_observation(tmp_path, before) == before
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        ledger.verify_observation(tmp_path, before, current=True)
    assert (tmp_path / "capital_flows.jsonl").read_bytes() == capital
    assert len(flows(tmp_path)) == 1 and verify_account(tmp_path, account.as_dict()) > 0
    rows = ledger.details(tmp_path)
    sold = next(r for r in rows if r["kind"] == "SELL")
    assert sold["final_realized_pnl"] == "92.78" and sold["actual_fee"] == "5.55"
    assert sold["gross_pnl"] == "100.00"
    count = len(journal_entries(tmp_path))
    ledger.sync_journal(tmp_path)
    assert len(journal_entries(tmp_path)) == count
    # Later disposal uses the remaining actual cost, including its last cent.
    last = replace(_plan(side="SELL", lot_id=buy.plan_id), shares=200,
                   plan_id="book-b:2026-09-01:000001.XSHE:SELL:last")
    _record_fill(tmp_path, last, price=11, event_id="sell2")
    final_snapshot = with_cash(_snapshot(broker_fills=fills + (("order-sell2", buy.code, "SELL", 200, 11),),
        observed_at=NOW+timedelta(seconds=2)), 100283.90)
    import_fees(tmp_path, fee_proof(tmp_path, final_snapshot, "order-sell2", "5.55"))
    final = observed(tmp_path, final_snapshot).accounting
    assert final["remaining_cost"] == "0.00" and final["lots"] == []
    assert final["realized_pnl"] == final["cumulative_pnl"] == "283.90"


def test_matching_estimated_cash_never_certifies_actual_profit_or_settlement(tmp_path):
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    buy = _record_fill(tmp_path, _plan(), price=10, event_id="buy")
    snapshot = with_cash(_snapshot(shares=100, sellable=100, price=10,
        observed_at=EOD_NOW, broker_fills=(("order-buy", buy.code, "BUY", 100, 10),)), 98999.90)
    account = observed(tmp_path, snapshot)
    assert account.cash == 98999.9 and account.accounting["status"] == "reconciled"
    assert account.accounting["fee_status"] == "actual_fees_pending"
    assert account.accounting["realized_pnl"] is account.accounting["cumulative_pnl"] is None
    assert account.accounting["pending_fee_orders"][0]["broker_order_id"] == "order-buy"
    with pytest.raises(ValueError, match="ACTUAL_FEES_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    with pytest.raises(ValueError, match="ACTUAL_FEES_REQUIRED"):
        write_book_b_live_settlement(tmp_path, replace(account, accounting=None), now=EOD_NOW)
    from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
    receipt = run_book_b_live_intraday(state_dir=tmp_path, trade_date=snapshot["trade_date"],
        phase="eod", account_snapshot_provider=lambda: snapshot,
        status_provider=lambda _: pytest.fail("EOD must not evaluate exits"),
        execute=lambda _: pytest.fail("fee reconciliation cannot submit orders"),
        now=lambda: EOD_NOW, execute_sells=False)
    assert receipt.status == "observed" and receipt.reason == "EOD_RECONCILED_ACCOUNTING_PENDING"
    assert receipt.settlement is None
    assert any(row["code"] == "LIVE_BOOK_B_SETTLEMENT_ACTUAL_FEES_REQUIRED"
               for row in receipt.eod_review["blockers"])
    assert receipt.broker_snapshot == snapshot and receipt.settlement is None
    # An explicitly proved zero or a fee equal to the old estimate is valid.
    import_fees(tmp_path, fee_proof(tmp_path, snapshot, "order-buy", ".10"))
    exact = observed(tmp_path, snapshot)
    assert exact.accounting["fee_status"] == "actual_fees_complete"
    assert write_book_b_live_settlement(tmp_path, exact, now=EOD_NOW)["status"] == "settled"


def test_explicit_fee_revision_is_append_only_and_zero_is_not_missing(tmp_path):
    _, _, snapshot = scenario(tmp_path)
    old = import_fees(tmp_path, fee_proof(tmp_path, snapshot, "order-buy", "5"))
    prefix = journal_entries(tmp_path)
    revised = fee_proof(tmp_path, snapshot, "order-buy", "0", identifier="corrected-buy",
                        replaces=old["entry_sha256"])
    import_fees(tmp_path, revised)
    assert journal_entries(tmp_path)[:len(prefix)] == prefix
    sold = next(r for r in ledger.details(tmp_path) if r["kind"] == "BUY")
    assert sold["actual_fee"] == "0.00"
    state = ledger.sync_journal(tmp_path)
    assert len(state["pending_fee_orders"]) == 1
    assert state["pending_fee_orders"][0]["broker_order_id"] == "order-sell1"
    with pytest.raises(ValueError, match="REVISION_UNPROVEN"):
        import_fees(tmp_path, fee_proof(tmp_path, snapshot, "order-buy", "2", identifier="duplicate-order"))


@pytest.mark.parametrize("fault", ["account", "hash", "order", "date", "side", "code", "coverage",
    "shares", "source_hash", "gross", "missing_component", "negative", "fraction", "net_cash", "estimate"])
def test_unproved_or_mismatched_fee_never_posts(tmp_path, fault):
    _, _, snapshot = scenario(tmp_path)
    ledger.sync_journal(tmp_path)
    prefix = journal_entries(tmp_path)
    proof = fee_proof(tmp_path, snapshot, "order-buy", "5")
    statement, row = proof["statement"], proof["statement"]["rows"][0]
    if fault == "account": statement["fund_account_binding_sha256"] = "b"*64
    if fault == "order": row["broker_order_id"] = "foreign-order"
    if fault == "date": row["trade_date"] = "2026-09-02"
    if fault == "side": row["side"] = "SELL"
    if fault == "code": row["code"] = "300107.XSHE"
    if fault == "coverage": row["coverage"] = "partial"
    if fault == "shares": row["shares"] -= 1
    if fault == "source_hash": row["ownership_event_hashes"] = ["f"*64]
    if fault == "gross": row["gross_notional"] = "2999"
    if fault == "missing_component": row["fees"].pop("stamp_duty")
    if fault == "negative": row["fees"]["commission"] = "-5"
    if fault == "fraction": row["fees"]["commission"] = ".001"
    if fault == "net_cash": row["net_cash_change"] = "-21.52"
    if fault == "estimate": row["fee_basis"] = "estimated_plan_rate"
    statement["receipt_sha256"] = digest({k:v for k,v in statement.items() if k != "receipt_sha256"})
    if fault == "hash": statement["receipt_sha256"] = "f"*64
    with pytest.raises(ValueError):
        import_fees(tmp_path, proof)
    assert journal_entries(tmp_path) == prefix


def test_fresh_broker_fill_contradiction_cannot_certify_fee_coverage(tmp_path):
    buy, fills, _ = scenario(tmp_path)
    snapshot = with_cash(_snapshot(shares=300, price=11,
        broker_fills=(("order-buy", buy.code, "BUY", 400, 10), fills[1]),
        observed_at=NOW+timedelta(seconds=1)), 97089.45)
    with pytest.raises(ValueError, match="FILL|COVERAGE|OWNERSHIP"):
        import_fees(tmp_path, fee_proof(tmp_path, snapshot, "order-buy", "5"))


def test_multiple_orders_with_late_fills_recover_atomically_and_allocate_fee_cents(tmp_path):
    from xiaocao.live.trading_execution import ExecutionStore, ExecutionReceipt, ExecutionState, BookBOwnershipEvidence
    from tests.test_book_b_live_lifecycle import _bind_plan_intent
    activate(tmp_path)
    project(tmp_path, with_cash(_snapshot(), 100000))
    plans = [_bind_plan_intent(tmp_path, replace(_plan(),
        plan_id=_plan().plan_id + suffix)) for suffix in (":a", ":b")]
    store = ExecutionStore(tmp_path / "events.jsonl")
    ownership = BookBOwnershipEvidence(tmp_path / "book_b_ownership_evidence.jsonl")
    def fill(plan, qty):
        receipt = store.append(plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash,
            ExecutionState.FILLED if qty == 100 else ExecutionState.PARTIAL,
            filled_shares=qty, remaining_shares=100-qty, broker_order_id=plan.plan_id[-1],
            fill_price=10, observed_at=NOW), kind="broker_receipt")
        ownership.record(plan, receipt)
    for plan in plans:
        fill(plan, 20)
    snapshot = with_cash(_snapshot(shares=40, price=10, observed_at=NOW+timedelta(seconds=1),
        broker_fills=tuple((p.plan_id[-1], p.code, "BUY", 20, 10) for p in plans)), 99599.94)
    observed(tmp_path, snapshot)
    previous = {p.plan_id: import_fees(tmp_path, fee_proof(tmp_path, snapshot, p.plan_id[-1], ".03"))
                for p in plans}
    for qty in (40, 60, 80, 100):
        for plan in plans:
            fill(plan, qty)
    current = with_cash(_snapshot(shares=200, price=10, observed_at=NOW+timedelta(seconds=2),
        broker_fills=tuple((p.plan_id[-1], p.code, "BUY", 100, 10) for p in plans)), 97999.94)
    proofs = [fee_proof(tmp_path, current, p.plan_id[-1], ".03", identifier="revised-" + p.plan_id[-1],
                       replaces=previous[p.plan_id]["entry_sha256"]) for p in plans]
    with pytest.raises(ValueError, match="COVERAGE_CHANGED"):
        import_fees(tmp_path, proofs[0])
    prefix = journal_entries(tmp_path)
    invalid = json.loads(json.dumps(proofs))
    invalid[1]["statement"]["receipt_sha256"] = "f"*64
    with pytest.raises(ValueError, match="STATEMENT_UNPROVEN"):
        ledger.record_trade_fees(tmp_path, {"fee_receipts": invalid}, now=NOW+timedelta(seconds=2))
    assert journal_entries(tmp_path) == prefix
    result = ledger.record_trade_fees(tmp_path, {"fee_receipts": proofs}, now=NOW+timedelta(seconds=2))
    assert len(result["entries"]) == 2
    account = observed(tmp_path, current)
    assert account.accounting["fee_status"] == "actual_fees_complete"
    assert account.accounting["ledger_cash"] == "97999.94"
    fees = [Decimal(r["actual_fee"]) for r in ledger.details(tmp_path) if r["kind"] == "BUY"]
    assert min(fees) >= 0 and sum(fees) == Decimal(".06")


def test_new_export_cannot_expose_legacy_estimated_profit_as_final(tmp_path):
    from scripts.book_b_accounting import export_statement
    buy, _, snapshot = scenario(tmp_path)
    report = observed(tmp_path, snapshot).accounting
    legacy = {k:v for k,v in report.items() if k not in {"receipt_sha256", "fee_status",
        "pending_fee_orders", "provisional_realized_pnl", "provisional_unrealized_pnl"}}
    legacy.update(fee_basis="estimated_plan_rate", realized_pnl=report["provisional_realized_pnl"],
                  unrealized_pnl=report["provisional_unrealized_pnl"], cumulative_pnl="299.59")
    legacy["receipt_sha256"] = digest(legacy)
    with sqlite3.connect(tmp_path / ledger.DATABASE) as db:
        db.execute("INSERT INTO observations VALUES(?,?,?)", (legacy["receipt_sha256"],
            snapshot["observed_at"], json.dumps(legacy)))
    ledger.verify_observation(tmp_path, legacy)
    result = export_statement(tmp_path, tmp_path / "statements", receipt={"account": {"accounting": legacy},
                                                                       "snapshot": snapshot})
    exported = json.loads(open(result["report_path"]).read())
    assert exported["source_observation"] == legacy
    assert exported["valuation"]["fee_status"] == "actual_fees_pending"
    assert exported["valuation"]["realized_pnl"] is exported["valuation"]["cumulative_pnl"] is None
