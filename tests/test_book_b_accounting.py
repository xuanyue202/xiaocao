"""Accounting effects and recovery, with the existing proved-fill fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
import json
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
    assert account.cash == cash and account.net_external_flow_total == 70000
    assert account.capital_flow_head_sha256 == first.capital_flow_head_sha256
    assert account.capital_unit_factor == first.capital_unit_factor
    assert account.accounting["cumulative_pnl"] is None
    assert account.accounting["status"] == "cash_reconciliation_required"
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
    assert Path(current["details_path"]).read_text(encoding="utf-8-sig").count("cash-1") == 1


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
    account = observed(tmp_path, with_cash(_snapshot(observed_at=EOD_NOW), 100005))
    with pytest.raises(ValueError, match="CASH_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    changed = replace(account, broker_snapshot_observed_at=(EOD_NOW+timedelta(days=1)).isoformat())
    with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
        write_book_b_live_settlement(tmp_path, changed, now=EOD_NOW)
