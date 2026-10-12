"""Current evidence, false-pause correction and hard-risk review boundaries."""
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from xiaocao.live.account_risk import NAV_BASIS, NavObservation, evaluate_account_risk
from xiaocao.live.live_decision_support import digest, evaluate_live_risk, load_live_nav_history
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account
from xiaocao.live.risk_history_repair import repair_false_pause
from xiaocao.live.book_b_live_morning import run_book_b_live_morning
from tests.test_book_b_available_capital import activate, project, with_cash
from tests.test_book_b_live_lifecycle import _snapshot, NOW
from tests.test_book_b_live_policy import _history, _morning, _risk, MORNING

pytestmark = pytest.mark.app_simulation


def dynamic_account(root):
    days = _history(root)
    activate(root)
    account = project(root, with_cash(_snapshot(shares=2000, sellable=2000, price=10), 100000))
    return days, account


def test_current_complete_mark_can_bridge_latest_settlement_but_not_forge_it(tmp_path):
    days, account = dynamic_account(tmp_path)
    latest = tmp_path / "settlements/2026-08-31.json"
    preserved = latest.read_bytes()
    latest.unlink()
    with pytest.raises(ValueError, match="LATEST_SETTLEMENT_REQUIRED"):
        load_live_nav_history(tmp_path, asof=NOW, trading_dates=days)
    result = evaluate_live_risk(tmp_path, now=NOW, account=account, trading_dates_provider=lambda _: days)
    assert result.status == "NORMAL", result.reasons
    assert "LATEST_SETTLEMENT_GAP_CURRENT_MARK_BASIS" in result.reasons
    assert not latest.exists()
    assert preserved
    event = json.loads((tmp_path / "account_risk/live_B.jsonl").read_text().splitlines()[-1])
    assert "2026-08-31" in event["history_coverage"]["history_gaps"]


def test_unclassified_asset_drop_blocks_without_latching_a_loss(tmp_path):
    days, account = dynamic_account(tmp_path)
    normal = evaluate_live_risk(tmp_path, now=NOW, account=account, trading_dates_provider=lambda _: days)
    stamp = NOW + timedelta(seconds=1)
    observed = project_book_b_live_account(tmp_path,
        with_cash(_snapshot(shares=2000, sellable=2000, price=10, observed_at=stamp), 1000),
        trade_date=stamp.date().isoformat(), now=stamp)
    assert observed.accounting["status"] == "cash_reconciliation_required"
    blocked = evaluate_live_risk(tmp_path, now=stamp, account=observed, trading_dates_provider=lambda _: days)
    assert blocked.status == "BLOCKED" and blocked.nav is None
    assert not blocked.pause_latched and blocked.high_water_mark == normal.high_water_mark
    assert "UNQUALIFIED_NAV_DRAWDOWN_UNPROVEN" in blocked.reasons


def test_unclassified_cash_bound_can_cap_risk_without_creating_a_new_peak():
    history = NavObservation("2026-08-28", 30000, "live:B", 30000, 0, NAV_BASIS,
        "settled", "2026-08-28T15:10:00+08:00", "a"*64)
    mark = replace(history, date=NOW.date().isoformat(), nav=40000,
        status="conservative_bound", observed_at=NOW.isoformat())
    result = evaluate_account_risk([history], asof=NOW, account_id="live:B", initial_capital=30000,
        expected_settlement_date="2026-08-31", current_nav=mark, allow_current_mark_gap=True)
    assert result.status == "NORMAL" and result.high_water_mark == 30000
    assert result.nav == 30000 and result.current_nav_lower_bound == 40000
    assert "CONSERVATIVE_NAV_BOUND_UNCLASSIFIED_CASH" in result.reasons


@pytest.mark.parametrize("nav,status", [(27000, "REDUCED"), (24000, "PAUSED")])
def test_settlement_gap_does_not_relax_real_loss_budget(nav, status):
    history = NavObservation("2026-08-28", 30000, "live:B", 30000, 0, NAV_BASIS,
        "settled", "2026-08-28T15:10:00+08:00", "a"*64)
    current = replace(history, date=NOW.date().isoformat(), nav=nav,
        status="reconciled", observed_at=NOW.isoformat())
    result = evaluate_account_risk([history], asof=NOW, account_id="live:B", initial_capital=30000,
        expected_settlement_date="2026-08-31", current_nav=current, allow_current_mark_gap=True)
    assert result.status == status
    if status == "PAUSED":
        recovered = evaluate_account_risk([history], asof=NOW, account_id="live:B", initial_capital=30000,
            expected_settlement_date="2026-08-31", current_nav=replace(current, nav=40000),
            previous_receipt=result, allow_current_mark_gap=True)
        assert recovered.pause_latched and recovered.status == "PAUSED"


@pytest.mark.parametrize("fault", ["no_current", "no_history", "stale", "bad_account", "bad_history"])
def test_gap_requires_qualified_current_and_prior_evidence(fault):
    history = NavObservation("2026-08-28", 30000, "live:B", 30000, 0, NAV_BASIS,
        "settled", "2026-08-28T15:10:00+08:00", "a"*64)
    current = replace(history, date=NOW.date().isoformat(), status="reconciled", observed_at=NOW.isoformat())
    rows = [history]
    if fault == "no_current": current = None
    if fault == "no_history": rows = []
    if fault == "stale": current = replace(current, observed_at=(NOW-timedelta(seconds=301)).isoformat())
    if fault == "bad_account": current = replace(current, account_id="paper:B")
    if fault == "bad_history": rows = [replace(history, evidence_digest="damaged")]
    result = evaluate_account_risk(rows, asof=NOW, account_id="live:B", initial_capital=30000,
        expected_settlement_date="2026-08-31", current_nav=current, allow_current_mark_gap=True)
    assert result.status == "BLOCKED" and result.deploy_factor == 0


def old_false_pause(root):
    days, account = dynamic_account(root)
    anchor = evaluate_live_risk(root, now=NOW, account=account, trading_dates_provider=lambda _: days)
    path = root / "account_risk/live_B.jsonl"
    stamp = NOW + timedelta(seconds=1)
    damaged_snapshot = with_cash(_snapshot(shares=2000, sellable=2000, price=10, observed_at=stamp,
            broker_fills=[("unbound", "600001.XSHG", "BUY", 100, 10)]), 1000)
    damaged_snapshot["tables"]["today-orders"]["rows"][0]["状态说明"] = "未知状态"
    damaged_snapshot.pop("snapshot_sha256")
    damaged_snapshot["snapshot_sha256"] = digest(damaged_snapshot)
    damaged = project_book_b_live_account(root, damaged_snapshot, trade_date=stamp.date().isoformat(), now=stamp)
    mark = NavObservation(stamp.date().isoformat(), float(damaged.accounting["conservative_risk_nav"]),
        "live:B", 30000, 0, NAV_BASIS, "reconciled", stamp.isoformat(), digest(damaged.as_dict()))
    history = load_live_nav_history(root, asof=stamp, trading_dates=days)
    # Replay the old adapter's exact mistake: label an incomplete mark reconciled.
    bad = evaluate_account_risk(history, asof=stamp, account_id="live:B", initial_capital=30000,
        expected_settlement_date="2026-08-31", current_nav=mark, previous_receipt=anchor)
    assert bad.pause_latched
    head = json.loads(path.read_text().splitlines()[-1])["event_hash"]
    event = {"receipt": bad.as_dict(), "previous_hash": head, "history_coverage": {},
        "capital_basis": {"capital_flow_head_sha256": damaged.capital_flow_head_sha256}}
    event["event_hash"] = digest(event)
    with path.open("a") as stream: stream.write(json.dumps(event)+"\n")
    return path, event


def test_false_pause_correction_is_append_only_and_requires_new_complete_nav(tmp_path):
    path, original = old_false_pause(tmp_path)
    before = path.read_bytes()
    args = dict(expected_head=original["event_hash"], now=NOW+timedelta(seconds=2))
    preview = repair_false_pause(tmp_path, path, **args)
    assert path.read_bytes() == before and preview["status"] == "reviewable"
    result = repair_false_pause(tmp_path, path, apply=True, **args)
    assert path.read_bytes().startswith(before)
    assert result["receipt"]["status"] == "BLOCKED" and result["receipt"]["nav"] is None
    assert not result["receipt"]["pause_latched"]
    assert result["receipt"]["high_water_mark"] == original["receipt"]["high_water_mark"]
    after = path.read_bytes()
    assert repair_false_pause(tmp_path, path, apply=True, **args)["status"] == "already_corrected"
    assert path.read_bytes() == after


@pytest.mark.parametrize("fault", ["head", "witness", "real_loss", "changed_peak", "other_path"])
def test_pause_repair_rejects_unproved_or_subsequent_economic_state(tmp_path, fault):
    path, event = old_false_pause(tmp_path)
    expected = event["event_hash"]
    if fault in {"witness", "real_loss", "changed_peak"}:
        if fault == "witness": event["receipt"]["nav_observed_at"] = (NOW+timedelta(seconds=9)).isoformat()
        if fault == "real_loss": event["receipt"]["nav"] -= 1
        if fault == "changed_peak": event["receipt"]["high_water_mark"] += 1
        event.pop("event_hash")
        event["event_hash"] = digest(event)
        lines = path.read_text().splitlines(); lines[-1] = json.dumps(event)
        path.write_text("\n".join(lines)+"\n"); expected = event["event_hash"]
    if fault == "head": expected = "f"*64
    target = tmp_path / "unrelated.jsonl" if fault == "other_path" else path
    before = path.read_bytes()
    with pytest.raises(ValueError):
        repair_false_pause(tmp_path, target, expected_head=expected, now=NOW+timedelta(seconds=3), apply=True)
    assert path.read_bytes() == before


def test_risk_zero_does_not_start_supporting_review_wait(tmp_path):
    config = _morning(tmp_path)
    result = run_book_b_live_morning(config, execute=lambda _: pytest.fail("risk cannot trade"),
        now=lambda: MORNING, risk_provider=lambda _: replace(_risk(MORNING), status="BLOCKED", deploy_factor=0),
        review_rendezvous=lambda _: pytest.fail("risk-zero model wait must be deferred"))
    assert result.status == "no_action"
    assert result.review_rendezvous["reason"] == "ACCOUNT_RISK_BLOCKS_NEW_BUY"


@pytest.mark.parametrize("nav,integrity", [(20000, True), (50000, True), (50000, False)])
def test_later_blocked_receipt_cannot_hide_complete_loss_or_new_peak(tmp_path, nav, integrity):
    import sqlite3
    path, original = old_false_pause(tmp_path)
    database = tmp_path / "accounting.sqlite3"
    with sqlite3.connect(database) as db:
        report = json.loads(db.execute("SELECT body FROM observations ORDER BY observed_at LIMIT 1").fetchone()[0])
        report.update(status="reconciled", cash_integrity_proven=integrity,
            liquidation_nav=str(nav), conservative_risk_nav=str(nav), risk_unit_factor="1",
            observed_at=(NOW+timedelta(seconds=2)).isoformat())
        report.pop("receipt_sha256")
        report["receipt_sha256"] = digest(report)
        db.execute("INSERT INTO observations VALUES(?,?,?)", (report["receipt_sha256"], report["observed_at"], json.dumps(report)))
    event = {"receipt": {**original["receipt"], "status": "BLOCKED", "nav": None, "drawdown_pct": None,
        "asof": (NOW+timedelta(seconds=3)).isoformat()}, "previous_hash": original["event_hash"],
        "history_coverage": {}, "capital_basis": {"raw_strategy_nav": nav, "unit_factor": "1",
            "capital_flow_head_sha256": report["capital_flow_head_sha256"]}}
    event["event_hash"] = digest(event)
    with path.open("a") as stream: stream.write(json.dumps(event)+"\n")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="SUBSEQUENT_ECONOMIC_STATE"):
        repair_false_pause(tmp_path, path, expected_head=event["event_hash"], now=NOW+timedelta(seconds=4), apply=True)
    assert path.read_bytes() == before


def test_legacy_unrelated_prior_sell_day_cannot_bridge_missing_latest(tmp_path, monkeypatch):
    import xiaocao.live.live_decision_support as support
    from tests.test_book_b_live_policy import _mark
    days = _history(tmp_path)
    (tmp_path / "settlements/2026-08-31.json").unlink()
    monkeypatch.setattr(support, "proven_prior_day_zero_fill_sell_ids", lambda *a, **k: ("unrelated",))
    monkeypatch.setattr(support, "_load_intent_index", lambda *a: {"unrelated": {"trade_date": "2026-08-28"}})
    receipt = support.evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 30000), trading_dates_provider=lambda _: days)
    assert receipt.status == "BLOCKED" and receipt.deploy_factor == 0
    assert "LIVE_RISK_LATEST_SETTLEMENT_REQUIRED:2026-08-31" in receipt.reasons
