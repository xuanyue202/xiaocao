from __future__ import annotations

import json
import importlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from xiaocao.live.account_risk import NAV_BASIS, NavObservation, evaluate_account_risk
from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account, write_book_b_live_settlement
from xiaocao.live.book_b_live_morning import BookBLiveMorningConfig, run_book_b_live_morning
from xiaocao.live.kol_policy import decision_sha256, publish_decision
from xiaocao.live.live_decision_support import (
    calendar_provider, digest, evaluate_live_risk, load_live_nav_history, plan_audit_path,
)
from xiaocao.live.trading_execution import BrokerReceipt, BrokerStatus, ExecutionReceipt, ExecutionState, ExecutionStore
from xiaocao.live.trading_runner import frozen_rows_digest

from tests.test_book_b_live_morning import _frozen_row, _live_allocation_payload, _ready_freeze
from tests.test_book_b_live_lifecycle import _plan, _record_fill, _snapshot, NOW


MORNING = datetime(2026, 8, 24, 1, 30, tzinfo=timezone.utc)


def _publish(root, now, *, scale=1.0, skips=(), exits=(), identifier="d1", runtime="live", lifetime=3600):
    stamp = now.isoformat()
    decision = {
        "schema_version": "kol-trading-decision.v1", "decision_id": identifier,
        "agent_id": "author", "book": "B", "runtime": runtime,
        "as_of": stamp, "valid_until": (now + timedelta(seconds=lifetime)).isoformat(),
        "buy_scale": scale, "skip_codes": list(skips), "exit_codes": list(exits),
        "rationale": "Reviewed test judgment", "invalidation_conditions": ["changed facts"],
        "source_refs": [{"report_id": "test-report", "content_sha256": "a" * 64,
                         "author_id": "test-kol", "source_published_at": stamp, "received_at": stamp}],
        "current_checks": [{"claim": "test context", "evidence_ref": "test-evidence",
                            "observed_at": stamp, "verdict": "supports"}],
    }
    review = {"status": "approved", "decision_sha256": decision_sha256(decision),
              "reviewer_agent_id": "reviewer", "reviewed_at": stamp,
              "coverage_complete": True, "source_fidelity": True,
              "applicability_checked": True, "counterevidence_checked": True}
    return publish_decision(root, decision, review, now)


def _risk(now=MORNING, nav=30000):
    row = NavObservation("2026-08-21", 30000, "live:B", 30000, 0, NAV_BASIS,
                         "settled", "2026-08-21T07:10:00+00:00", "a" * 64)
    current = replace(row, date=now.date().isoformat(), nav=nav, status="reconciled",
                      observed_at=now.isoformat())
    return evaluate_account_risk([row], asof=now, account_id="live:B", initial_capital=30000,
                                 expected_settlement_date=row.date, current_nav=current)


def _morning(tmp_path, *, rows=None, base_factor=1.0):
    rows = rows or [_frozen_row()]
    freeze = tmp_path / "freeze.jsonl"
    freeze.write_text("".join(json.dumps(row) + "\n" for row in rows))
    allocation = _live_allocation_payload()
    allocation.pop("allocation_capsule_sha256")
    allocation["deploy_factor"] = base_factor
    allocation["allocation_capsule_sha256"] = digest(allocation)
    path = tmp_path / "allocation.json"
    path.write_text(json.dumps(allocation))
    return BookBLiveMorningConfig(
        trade_date="2026-08-24", freeze_path=freeze, allocation_facts_path=path,
        state_dir=tmp_path / "state", policy_root=tmp_path / "policy",
        dated_freeze_receipt={**_ready_freeze(), "snapshot_sha256": frozen_rows_digest(rows),
                             "snapshot_row_count": len(rows)},
    )


def _execute_capture(seen):
    def execute(plan):
        seen.append(plan)
        return ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.CANCELLED,
                                remaining_shares=plan.shares, reason="FAKE_ZERO_FILL")
    return execute


@pytest.mark.parametrize("scale,risk_nav,base,expected_factor", [
    (0.5, 30000, 1.0, 0.5), (0.8, 27000, 1.0, 0.5), (1.0, 30000, 0.25, 0.25),
])
def test_buy_cap_keeps_capsule_freeze_and_independent_intent_audit(tmp_path, scale, risk_nav, base, expected_factor):
    config = _morning(tmp_path, base_factor=base)
    before = (config.freeze_path.read_bytes(), config.allocation_facts_path.read_bytes())
    published = _publish(config.policy_root, MORNING, scale=scale)
    seen = []
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen),
                now=lambda: MORNING, risk_provider=lambda now: _risk(now, risk_nav))
    assert receipt.status == "completed", receipt.reason
    assert len(seen) == 1
    plan = seen[0]
    assert plan.shares * plan.limit_price * 1.0001 <= 30000 * 0.5 * expected_factor
    audit = json.loads(plan_audit_path(config.state_dir, plan.plan_id).read_text())
    assert audit["effective_deploy_factor"] == expected_factor
    assert audit["decision_sha256"] == published["decision_sha256"]
    assert audit["plan_hash"] == plan.plan_hash
    assert before == (config.freeze_path.read_bytes(), config.allocation_facts_path.read_bytes())


@pytest.mark.parametrize("kind", ["skip", "zero", "malformed", "risk_pause"])
def test_all_skipped_buy_is_no_action_without_wait_or_intents(tmp_path, kind):
    config = _morning(tmp_path)
    if kind == "malformed":
        config.policy_root.mkdir()
        (config.policy_root / "bad.json").write_text("{")
    else:
        _publish(config.policy_root, MORNING, scale=0 if kind == "zero" else 1,
                 skips=["000001.XSHE"] if kind == "skip" else [])
    seen = []
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING,
        risk_provider=lambda now: _risk(now, 24000 if kind == "risk_pause" else 30000),
        wait_for_submit_window=lambda _: pytest.fail("empty plans must not wait"))
    assert receipt.status == "no_action", receipt.reason
    assert receipt.plan_count == 0 and not seen
    assert not list((config.state_dir / "plan_intents").glob("*.json"))


@pytest.mark.parametrize("kind", ["expired", "absent", "paper"])
def test_neutral_policy_keeps_eligible_live_buy(tmp_path, kind):
    config = _morning(tmp_path)
    if kind != "absent":
        _publish(config.policy_root, MORNING - timedelta(minutes=2), scale=0,
                 lifetime=60 if kind == "expired" else 3600, runtime="paper" if kind == "paper" else "live")
    seen = []
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING,
                                    risk_provider=_risk)
    assert receipt.status == "completed", receipt.reason
    assert len(seen) == 1


def test_skip_does_not_promote_another_mode_or_redistribute_slot(tmp_path):
    rows = [_frozen_row(), {**_frozen_row(), "code": "000002.XSHE", "mode": "mode-b"}]
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    config = _morning(baseline_dir, rows=rows)
    baseline = []
    run_book_b_live_morning(config, execute=_execute_capture(baseline), now=lambda: MORNING, risk_provider=_risk)
    selected_dir = tmp_path / "selected"
    selected_dir.mkdir()
    selected = _morning(selected_dir, rows=rows)
    _publish(selected.policy_root, MORNING, skips=["000001.XSHE"])
    seen = []
    receipt = run_book_b_live_morning(selected, execute=_execute_capture(seen), now=lambda: MORNING, risk_provider=_risk)
    assert receipt.status == "completed", receipt.reason
    assert [(p.code, p.shares) for p in seen] == [(p.code, p.shares) for p in baseline if p.code != "000001.XSHE"]


@pytest.mark.parametrize("tightening", ["scale", "risk_pause", "new_skip"])
def test_prepared_plan_is_blocked_when_policy_tightens_during_wait(tmp_path, tightening):
    config = _morning(tmp_path)
    clock = [MORNING - timedelta(minutes=5)]
    _publish(config.policy_root, clock[0])
    seen = []
    prepared = []
    risk_nav = [30000]

    def prepare(plan):
        prepared.append(plan)
        ExecutionStore(config.state_dir / "events.jsonl").append(
            plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PREPARED),
            kind="prepare_receipt",
        )
        return BrokerReceipt(status=BrokerStatus.PREPARED, account_binding="proven",
            echoed={"code": plan.code, "side": plan.side, "shares": plan.shares, "limit_price": plan.limit_price},
            field_readback={"submitted": False, "saved": False, "started": False, "form_closed": True})

    def wait(_):
        clock[0] = MORNING
        if tightening == "risk_pause":
            risk_nav[0] = 24000
        else:
            _publish(config.policy_root, MORNING, scale=0.5 if tightening == "scale" else 1,
                     skips=["000001.XSHE"] if tightening == "new_skip" else [], identifier="d2")

    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: clock[0],
                                    risk_provider=lambda now: _risk(now, risk_nav[0]),
                                    wait_for_submit_window=wait, prepare_only=prepare)
    assert receipt.status == "no_action", receipt.reason
    assert not seen and len(prepared) == 1
    intents = list((config.state_dir / "plan_intents").glob("*.json"))
    assert len(intents) == 1
    original = intents[0].read_bytes()
    run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: clock[0],
                           risk_provider=lambda now: _risk(now, risk_nav[0]))
    assert not seen and intents[0].read_bytes() == original


def test_unknown_old_intent_reconciles_before_broken_policy_and_history(tmp_path):
    config = _morning(tmp_path)
    seen = []
    run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING, risk_provider=_risk)
    plan = seen[0]
    store = ExecutionStore(config.state_dir / "events.jsonl")
    store.append(plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.UNKNOWN,
                 remaining_shares=plan.shares, next_action="reconcile_only"), kind="submit_receipt")
    intents = list((config.state_dir / "plan_intents").glob("*.json"))
    before = intents[0].read_bytes()
    config.policy_root.mkdir(exist_ok=True)
    (config.policy_root / "broken.json").write_text("{")
    calls = []

    def reconcile(original):
        calls.append(original)
        assert original.plan_hash == plan.plan_hash
        return store.append(plan=original, receipt=ExecutionReceipt(original.plan_id, original.plan_hash,
                 ExecutionState.UNKNOWN, remaining_shares=original.shares, next_action="reconcile_only"),
                 kind="reconcile_receipt")

    receipt = run_book_b_live_morning(config, execute=reconcile, now=lambda: MORNING,
        risk_provider=lambda _: pytest.fail("risk must not preempt UNKNOWN reconcile"),
        read_allocation_facts=lambda: pytest.fail("allocation must not preempt UNKNOWN reconcile"),
        prepare_only=lambda _: pytest.fail("UNKNOWN must not prepare"))
    assert receipt.status == "blocked" and "RECONCILE_REQUIRED" in receipt.reason
    assert len(calls) == 1 and intents[0].read_bytes() == before


def _dated_snapshot(day, stamp, **kwargs):
    snapshot = _snapshot(observed_at=stamp, **kwargs)
    snapshot.pop("snapshot_sha256")
    snapshot["trade_date"] = day
    snapshot["snapshot_sha256"] = digest(snapshot)
    return snapshot


def _history(tmp_path):
    buy = replace(_plan(trade_date="2026-08-28"), shares=2000)
    _record_fill(tmp_path, buy, price=10, event_id="buy-fill")
    for day in ("2026-08-28", "2026-08-31"):
        stamp = datetime.fromisoformat(day + "T07:10:00+00:00")
        snapshot = _dated_snapshot(day, stamp, shares=2000, sellable=2000,
             price=10, broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 2000, 10),) if day == "2026-08-28" else ())
        account = project_book_b_live_account(tmp_path, snapshot, trade_date=day, now=stamp)
        write_book_b_live_settlement(tmp_path, account, now=stamp)
    return ["2026-08-28", "2026-08-31", "2026-09-01"]


def _mark(tmp_path, nav, now=NOW):
    cash = 9998
    price = (nav - cash) / (2000 * 0.9999)
    snapshot = _snapshot(shares=2000, sellable=2000, price=price, observed_at=now)
    return project_book_b_live_account(tmp_path, snapshot, trade_date="2026-09-01", now=now)


def test_live_history_risk_drawdown_and_latched_intraday_highwater(tmp_path):
    days = _history(tmp_path)
    receipt = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 30000), trading_dates_provider=lambda _: days)
    assert receipt.status == "NORMAL", receipt.reasons
    peak = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 40000), trading_dates_provider=lambda _: days)
    assert peak.high_water_mark == 40000
    half = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 36000), trading_dates_provider=lambda _: days)
    assert half.status == "REDUCED" and half.deploy_factor == 0.5, half.reasons
    paused = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 32000), trading_dates_provider=lambda _: days)
    assert paused.status == "PAUSED" and paused.pause_latched
    rebound = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 42000), trading_dates_provider=lambda _: days)
    assert rebound.status == "PAUSED" and rebound.high_water_mark == 42000


@pytest.mark.parametrize("fault", ["old_hash", "wrong_account", "wrong_date", "future", "flow"])
def test_history_adapter_verifies_every_file_not_only_latest(tmp_path, fault):
    days = _history(tmp_path)
    path = tmp_path / "settlements" / "2026-08-28.json"
    payload = json.loads(path.read_text())
    payload.pop("settlement_sha256")
    if fault == "old_hash":
        payload["settled_nav"] += 1
    elif fault == "wrong_account":
        payload["logical_account_id"] = "other"
    elif fault == "wrong_date":
        payload["trade_date"] = "2026-08-27"
    elif fault == "future":
        payload["settled_at"] = "2026-09-02T07:10:00+00:00"
    elif fault == "flow":
        payload["cash"] += 1000
        payload["settled_nav"] += 1000
    payload["settlement_sha256"] = "a" * 64 if fault == "old_hash" else digest(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="LIVE_RISK_"):
        load_live_nav_history(tmp_path, asof=NOW, trading_dates=days)
    receipt = evaluate_live_risk(tmp_path, now=NOW, trading_dates_provider=lambda _: days)
    assert receipt.status == "BLOCKED" and receipt.deploy_factor == 0


def test_calendar_freshness_cannot_be_self_certified_by_latest_file(tmp_path):
    days = _history(tmp_path)
    (tmp_path / "settlements" / "2026-08-31.json").unlink()
    receipt = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 30000), trading_dates_provider=lambda _: days)
    assert receipt.status == "BLOCKED"
    assert receipt.expected_settlement_date == "2026-08-31"
    assert "LIVE_RISK_LATEST_SETTLEMENT_REQUIRED:2026-08-31" in receipt.reasons


def test_no_settlements_never_fabricates_seed_or_reads_paper(tmp_path, monkeypatch):
    forbidden = {"paper_account.json", "paper_holdings.json", "positions.jsonl", "paper_trades.jsonl"}
    original = Path.open

    def guarded(path, *args, **kwargs):
        if path.name in forbidden:
            pytest.fail("live adapter read paper state")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    receipt = evaluate_live_risk(tmp_path, now=NOW,
             account_snapshot_provider=lambda: _snapshot(), trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    assert receipt.status == "BLOCKED"
    assert "LIVE_RISK_HISTORY_OR_EXPLICIT_SEED_PROOF_REQUIRED" in receipt.reasons
    assert not list((tmp_path / "settlements").glob("*.json"))


def test_calendar_adapter_reads_exchange_once_per_date():
    calls = []

    class Calendar:
        def get_trade_cal(self, *args):
            calls.append(args)
            return [{"calDate": "20260831", "isOpen": 1}, {"calDate": "20260901", "isOpen": 1}]

    read = calendar_provider(Calendar())
    assert read(NOW) == read(NOW) == ["2026-08-31", "2026-09-01"]
    assert len(calls) == 1


def _exit_run(tmp_path, *, policy_kind="valid", reason="KOL_DISCRETIONARY_EXIT", entry_date="2026-08-31", status_changes=None):
    buy = _plan(trade_date=entry_date)
    _record_fill(tmp_path, buy, price=10, event_id="buy-fill")
    root = tmp_path / "policy"
    if policy_kind == "malformed":
        root.mkdir()
        (root / "bad.json").write_text("{")
    elif policy_kind != "absent":
        _publish(root, NOW - timedelta(minutes=2), exits=["000002.XSHE" if policy_kind == "other_code" else "000001.XSHE"],
                 lifetime=60 if policy_kind == "expired" else 3600)
    seen = []
    status = {"owned_lot_id": buy.plan_id, "triggered": True, "sell_reason": reason,
              "decision_phase": "kol_discretionary", "latest_price": 9.2,
              "market_guard_status": "ok", "market_guard_observed_at": NOW,
              "market_guard_down_price": 9.0, **(status_changes or {})}
    receipt = run_book_b_live_intraday(state_dir=tmp_path, freeze_dir=tmp_path,
        trade_date="2026-09-01", phase="precheck", now=lambda: NOW,
        account_snapshot_provider=lambda: _snapshot(shares=100, sellable=100, price=9.2,
            broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10),) if entry_date == "2026-09-01" else ()),
        status_provider=lambda _: [status], execute=_execute_capture(seen), policy_root=root,
        trading_dates_provider=lambda _: ["2026-08-31", "2026-09-01"])
    return receipt, seen


def test_kol_exit_has_exact_decision_hash_and_owned_lot_audit_despite_missing_risk_history(tmp_path):
    receipt, seen = _exit_run(tmp_path)
    assert receipt.status == "executed"
    assert receipt.risk_receipt["status"] == "BLOCKED"
    assert len(seen) == 1 and seen[0].sell_reason == "KOL_DISCRETIONARY_EXIT"
    decision = receipt.decisions[0]
    audit = json.loads(plan_audit_path(tmp_path, seen[0].plan_id).read_text())
    assert audit["decision_sha256"] == decision["kol_decision_sha256"]
    assert audit["decision_id"] == decision["kol_decision_id"]
    assert audit["owned_lot_id"] == seen[0].owned_lot_id


@pytest.mark.parametrize("kind", ["expired", "malformed", "absent", "other_code"])
def test_status_provider_cannot_invent_kol_sell_authority(tmp_path, kind):
    receipt, seen = _exit_run(tmp_path, policy_kind=kind)
    assert not seen and not receipt.decisions[0]["sell_authorized"]


@pytest.mark.parametrize("changes", [{"t1_blocked": True}, {"sell_block_reason": "LIMIT_DOWN_NO_BID"}])
def test_kol_exit_keeps_sell_blocks(tmp_path, changes):
    receipt, seen = _exit_run(tmp_path, status_changes=changes)
    assert not seen and not receipt.decisions[0]["sell_authorized"]


def test_kol_exit_entry_day_is_t1_blocked_even_with_broker_sellable(tmp_path):
    receipt, seen = _exit_run(tmp_path, entry_date="2026-09-01")
    assert not seen and receipt.decisions[0]["sellable_shares"] == 0


def test_bad_policy_and_risk_history_do_not_block_hard_sell(tmp_path):
    receipt, seen = _exit_run(tmp_path, policy_kind="malformed", reason="HARD_STOP")
    assert len(seen) == 1 and seen[0].sell_reason == "HARD_STOP"
    assert receipt.risk_receipt["status"] == "BLOCKED"


def test_kol_cannot_open_soft_exit_window(tmp_path):
    receipt, seen = _exit_run(tmp_path, reason="TRAILING_STOP")
    assert not seen and not receipt.decisions[0]["sell_authorized"]


def test_stale_quote_cannot_sell_on_valid_kol_decision(tmp_path):
    with pytest.raises(ValueError, match="MARKET_GUARD_UNPROVEN"):
        _exit_run(tmp_path, status_changes={"market_guard_observed_at": NOW - timedelta(minutes=6)})


def test_needs_refresh_is_neutral_with_original_decision_id(tmp_path):
    config = _morning(tmp_path)
    _publish(config.policy_root, MORNING - timedelta(minutes=16), scale=0)
    seen = []
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING, risk_provider=_risk)
    assert receipt.status == "completed" and len(seen) == 1
    assert receipt.policy_consumptions[0]["decision_id"] == "d1"
    assert receipt.policy_consumptions[0]["reason"] == "KOL_POLICY_NEEDS_REFRESH"


def test_recovery_of_scaled_intent_keeps_original_hash_when_policy_relaxes(tmp_path):
    config = _morning(tmp_path)
    _publish(config.policy_root, MORNING, scale=0.5)
    seen = []
    run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING, risk_provider=_risk)
    original = seen[0]
    audit_before = plan_audit_path(config.state_dir, original.plan_id).read_bytes()
    later = MORNING + timedelta(seconds=1)
    _publish(config.policy_root, later, scale=1, identifier="d2")
    recovered = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: later, risk_provider=_risk)
    assert len(seen) == 2, recovered.reason
    assert seen[1].plan_hash == original.plan_hash and seen[1].shares == original.shares
    assert plan_audit_path(config.state_dir, original.plan_id).read_bytes() == audit_before


def test_review_request_only_new_candidates_and_bounded_by_entry_window(tmp_path):
    config = _morning(tmp_path)
    requests = []
    seen = []
    clock = MORNING.replace(hour=3, minute=29)

    def review(request):
        requests.append(request)
        assert not list((config.state_dir / "plan_intents").glob("*.json"))
        return {"status": "timed_out", "fallback": "neutral", "request_sha256": digest(request)}

    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: clock,
                                    risk_provider=_risk, review_rendezvous=review)
    assert receipt.review_rendezvous["status"] == "timed_out"
    assert requests[0]["max_wait_seconds"] == 60
    assert requests[0]["freeze_sha256"] == config.dated_freeze_receipt["snapshot_sha256"]
    assert [row["code"] for row in requests[0]["candidates"]] == ["000001.XSHE"]
    recovered = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: clock,
                           risk_provider=_risk, review_rendezvous=lambda _: pytest.fail("existing intent must not rendezvous"))
    assert len(seen) == 2, recovered.reason
    assert seen[0].plan_hash == seen[1].plan_hash


def test_pause_survives_invalid_history_then_repair(tmp_path):
    days = _history(tmp_path)
    paused = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 24000), trading_dates_provider=lambda _: days)
    assert paused.pause_latched
    path = tmp_path / "settlements" / "2026-08-28.json"
    original = path.read_bytes()
    path.write_text("{")
    blocked = evaluate_live_risk(tmp_path, now=NOW, trading_dates_provider=lambda _: days)
    assert blocked.status == "BLOCKED" and blocked.pause_latched
    path.write_bytes(original)
    repaired = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 31000), trading_dates_provider=lambda _: days)
    assert repaired.status == "PAUSED" and repaired.pause_latched


def test_corrupt_risk_receipt_does_not_reset_highwater_or_pause(tmp_path):
    days = _history(tmp_path)
    evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 24000), trading_dates_provider=lambda _: days)
    path = tmp_path / "account_risk" / "live_B.jsonl"
    path.write_text(path.read_text().replace('"pause_latched": true', '"pause_latched": false'))
    before = path.read_bytes()
    receipt = evaluate_live_risk(tmp_path, now=NOW, account=_mark(tmp_path, 40000), trading_dates_provider=lambda _: days)
    assert receipt.status == "BLOCKED" and "PREVIOUS_RECEIPT_INVALID" in receipt.reasons
    assert path.read_bytes() == before


def test_risk_calendar_read_happens_after_hard_sell_handoff(tmp_path, monkeypatch):
    import xiaocao.live.book_b_live_intraday as intraday

    ordering = []
    original = intraday.evaluate_live_risk

    def risk(*args, **kwargs):
        ordering.append("risk")
        return original(*args, **kwargs)

    original_capture = _execute_capture

    def capture(seen):
        execute = original_capture(seen)

        def wrapped(plan):
            ordering.append("sell")
            return execute(plan)

        return wrapped

    monkeypatch.setattr(intraday, "evaluate_live_risk", risk)
    monkeypatch.setitem(globals(), "_execute_capture", capture)
    _exit_run(tmp_path, reason="HARD_STOP")
    assert ordering == ["sell", "risk"]


def test_live_september_migration_shape_warns_for_middle_gap_but_requires_latest(tmp_path):
    seed_time = datetime.fromisoformat("2026-09-01T07:10:00+00:00")
    seed = project_book_b_live_account(tmp_path, _snapshot(observed_at=seed_time),
                                      trade_date="2026-09-01", now=seed_time)
    write_book_b_live_settlement(tmp_path, seed, now=seed_time)
    buy = replace(_plan(trade_date="2026-09-02"), shares=800, limit_price=17.39, basket_price=17.6683)
    _record_fill(tmp_path, buy, price=17.06, event_id="buy-fill")
    mark_time = datetime.fromisoformat("2026-09-03T07:10:00+00:00")
    marked = project_book_b_live_account(tmp_path,
        _dated_snapshot("2026-09-03", mark_time, shares=800, sellable=800, price=16.48),
        trade_date="2026-09-03", now=mark_time)
    write_book_b_live_settlement(tmp_path, marked, now=mark_time)
    sell = replace(_plan(side="SELL", lot_id=buy.plan_id, trade_date="2026-09-04"), shares=800,
                   limit_price=16.66)
    _record_fill(tmp_path, sell, price=16.66, event_id="sell-fill")
    final_time = datetime.fromisoformat("2026-09-04T07:10:00+00:00")
    snapshot = _dated_snapshot("2026-09-04", final_time,
                              broker_fills=(("order-sell-fill", "000001.XSHE", "SELL", 800, 16.66),))
    final = project_book_b_live_account(tmp_path, snapshot, trade_date="2026-09-04", now=final_time)
    write_book_b_live_settlement(tmp_path, final, now=final_time)
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    receipt = evaluate_live_risk(tmp_path, now=final_time, account=final, trading_dates_provider=lambda _: days)
    assert receipt.status == "NORMAL", receipt.reasons
    assert receipt.high_water_mark == 30000 and receipt.deploy_factor == 1
    assert "HISTORICAL_SETTLEMENT_GAPS:2026-09-02" in receipt.reasons
    event = json.loads((tmp_path / "account_risk" / "live_B.jsonl").read_text().splitlines()[-1])
    assert event["history_coverage"]["supporting_health"] == "degraded"
    assert event["history_coverage"]["missing_historical_high_water"] is True
    assert not (tmp_path / "settlements" / "2026-09-02.json").exists()
    (tmp_path / "settlements" / "2026-09-04.json").unlink()
    missing_latest = evaluate_live_risk(tmp_path, now=final_time, account=final, trading_dates_provider=lambda _: days)
    assert missing_latest.status == "BLOCKED"
    assert "LIVE_RISK_LATEST_SETTLEMENT_REQUIRED:2026-09-04" in missing_latest.reasons
    assert missing_latest.high_water_mark == 30000


def test_morning_snapshot_cache_invalidates_after_actor_order_and_observes_pause(tmp_path, monkeypatch):
    import xiaocao.live.book_b_live_morning as morning

    config = _morning(tmp_path, rows=[_frozen_row(), {**_frozen_row(), "code": "000002.XSHE", "mode": "mode-b"}])
    reads = []
    seen = []
    risk_results = []

    def snapshot():
        reads.append(len(seen))
        return _dated_snapshot("2026-08-24", MORNING)

    def risk(_root, *, now, account_snapshot_provider, **_):
        account_snapshot_provider()
        result = _risk(now, 24000 if seen else 30000)
        risk_results.append(result)
        return result

    monkeypatch.setattr(morning, "evaluate_live_risk", risk)
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: MORNING,
                                    account_snapshot_provider=snapshot)
    assert len(seen) == 1
    assert reads == [0, 1]  # three pre-intent/action evaluations share the first snapshot
    assert risk_results[-1].status == "PAUSED"
    assert receipt.policy_consumptions[-1]["risk_receipt"]["pause_latched"] is True


def test_morning_snapshot_cache_expires_before_submit(tmp_path, monkeypatch):
    import xiaocao.live.book_b_live_morning as morning

    config = _morning(tmp_path)
    clock = [MORNING - timedelta(minutes=6)]
    reads = []
    seen = []

    def snapshot():
        reads.append(clock[0])
        return _dated_snapshot("2026-08-24", clock[0])

    def risk(_root, *, now, account_snapshot_provider, **_):
        account_snapshot_provider()
        return _risk(now, 24000 if now == MORNING else 30000)

    monkeypatch.setattr(morning, "evaluate_live_risk", risk)
    receipt = run_book_b_live_morning(config, execute=_execute_capture(seen), now=lambda: clock[0],
        account_snapshot_provider=snapshot, wait_for_submit_window=lambda _: clock.__setitem__(0, MORNING))
    assert len(reads) == 2 and not seen
    assert receipt.policy_consumptions[-1]["risk_receipt"]["status"] == "PAUSED"


def test_risk_asof_uses_native_read_completion_clock(tmp_path):
    days = _history(tmp_path)
    clock = [NOW]

    def read():
        clock[0] += timedelta(seconds=5)
        return _snapshot(shares=2000, sellable=2000, price=10, observed_at=clock[0])

    receipt = evaluate_live_risk(tmp_path, now=NOW, account_snapshot_provider=read,
        trading_dates_provider=lambda _: days, now_provider=lambda: clock[0])
    assert receipt.status == "NORMAL", receipt.reasons
    assert receipt.asof == clock[0].isoformat()


def _morning_cli(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("scripts.book_b_live_morning")


def _review_request(tmp_path, *, budget=120, deadline_seconds=600):
    return {"schema_version": "book-b-live-review-request.v1", "book": "B", "runtime": "live",
        "trade_date": "2026-08-24", "freeze_path": str(tmp_path / "freeze.jsonl"),
        "freeze_sha256": "a" * 64, "strategy_sha": "b" * 40,
        "policy_root": str(tmp_path / "kol_policy" / "decisions"),
        "candidates": [_frozen_row()], "requested_at": MORNING.isoformat(),
        "entry_deadline": (MORNING + timedelta(seconds=deadline_seconds)).isoformat(),
        "max_wait_seconds": budget}


def test_cli_rendezvous_waits_for_new_reviewed_policy_and_flushes_request(tmp_path, monkeypatch, capsys):
    cli = _morning_cli(monkeypatch)
    request = _review_request(tmp_path)
    root = Path(request["policy_root"])
    _publish(root, MORNING - timedelta(seconds=1), scale=0)
    elapsed = [0.0]
    flushed = []
    real_print = print

    def emit(*args, **kwargs):
        flushed.append(kwargs.get("flush"))
        real_print(*args, **kwargs)

    def sleep(seconds):
        elapsed[0] += seconds
        if elapsed[0] == 2:
            _publish(root, MORNING + timedelta(seconds=2), identifier="new-review", scale=0.5)

    monkeypatch.setattr(cli, "print", emit, raising=False)
    receipt = cli._review_rendezvous(request, now=lambda: MORNING + timedelta(seconds=elapsed[0]),
                                    sleep=sleep, monotonic=lambda: elapsed[0])
    assert receipt["status"] == "validated" and receipt["decision_id"] == "new-review"
    assert receipt["waited_seconds"] == 2 and receipt["supporting_health"] == "healthy"
    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "book_b_live_review_requested" and flushed == [True]
    artifact = json.loads(Path(event["request_path"]).read_text())
    assert artifact["freeze_sha256"] == request["freeze_sha256"]
    assert artifact["request_sha256"] == digest({k: v for k, v in artifact.items() if k not in ("request_id", "request_sha256")})
    assert json.loads(Path(receipt["receipt_path"]).read_text()) == receipt
    assert Path(receipt["request_path"]).parent == root.parent / "context" / "live_review_requests"
    replay = cli._review_rendezvous(request, now=lambda: MORNING + timedelta(seconds=3),
        sleep=lambda _: pytest.fail("immutable completed rendezvous must not wait again"), monotonic=lambda: 3)
    assert replay == receipt


@pytest.mark.parametrize("budget,entry_seconds,expected", [(300, 600, 120), (120, 4, 4), (0, 600, 0)])
def test_cli_rendezvous_timeout_is_bounded_and_degraded(tmp_path, monkeypatch, budget, entry_seconds, expected):
    cli = _morning_cli(monkeypatch)
    request = _review_request(tmp_path, budget=budget, deadline_seconds=entry_seconds)
    elapsed = [0.0]
    receipt = cli._review_rendezvous(request, now=lambda: MORNING + timedelta(seconds=elapsed[0]),
        sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds), monotonic=lambda: elapsed[0])
    assert elapsed[0] == expected
    assert receipt["status"] == "timed_out" and receipt["fallback"] == "neutral"
    assert receipt["supporting_health"] == "degraded" and receipt["max_wait_seconds"] <= 120
    assert not Path(request["policy_root"]).exists()  # only context artifacts, never a decision publication


def test_cli_rendezvous_corrupt_policy_stays_blocked(tmp_path, monkeypatch):
    cli = _morning_cli(monkeypatch)
    request = _review_request(tmp_path)
    root = Path(request["policy_root"])
    root.mkdir(parents=True)
    (root / "broken.json").write_text("{")
    receipt = cli._review_rendezvous(request, now=lambda: MORNING, monotonic=lambda: 0,
        sleep=lambda _: pytest.fail("malformed policy must block without waiting"))
    assert receipt["status"] == "blocked" and receipt["fallback"] is None


def test_cli_review_artifacts_are_immutable(tmp_path, monkeypatch):
    cli = _morning_cli(monkeypatch)
    path = tmp_path / "request.json"
    cli._write_review_immutable(path, {"request": 1})
    before = path.read_bytes()
    with pytest.raises(ValueError, match="IMMUTABILITY_VIOLATION"):
        cli._write_review_immutable(path, {"request": 2})
    assert path.read_bytes() == before and not list(tmp_path.glob(".review-*"))


def test_review_timeout_ignores_old_decision_but_does_not_ignore_fresh_skip(tmp_path):
    config = _morning(tmp_path)
    _publish(config.policy_root, MORNING - timedelta(seconds=1), scale=0)
    seen = []
    receipt = run_book_b_live_morning(config, now=lambda: MORNING, risk_provider=_risk,
        execute=_execute_capture(seen), review_rendezvous=lambda _: {"status": "timed_out", "fallback": "neutral"})
    assert len(seen) == 1 and receipt.policy_consumptions[0]["reason"] == "LIVE_REVIEW_TIMEOUT_NEUTRAL_FALLBACK"
    other = tmp_path / "fresh"
    other.mkdir()
    config = _morning(other)

    def timeout(_):
        _publish(config.policy_root, MORNING, skips=["000001.XSHE"])
        return {"status": "timed_out", "fallback": "neutral"}

    seen = []
    run_book_b_live_morning(config, now=lambda: MORNING, risk_provider=_risk,
                          execute=_execute_capture(seen), review_rendezvous=timeout)
    assert not seen


def test_entry_deadline_after_rendezvous_creates_no_intent(tmp_path):
    config = _morning(tmp_path)
    clock = [MORNING.replace(hour=3, minute=29)]

    def review(request):
        clock[0] = datetime.fromisoformat(request["entry_deadline"])
        return {"status": "timed_out", "fallback": "neutral"}

    receipt = run_book_b_live_morning(config, now=lambda: clock[0], risk_provider=_risk,
        execute=lambda _: pytest.fail("entry window closed"), review_rendezvous=review)
    assert receipt.reason == "LIVE_REVIEW_ENTRY_WINDOW_CLOSED"
    assert not list((config.state_dir / "plan_intents").glob("*.json"))


def test_production_morning_cli_passes_real_rendezvous_callback(tmp_path, monkeypatch):
    cli = _morning_cli(monkeypatch)
    from xiaocao.live.book_b_live_morning import BookBLiveMorningReceipt

    monkeypatch.setattr(cli, "KeychainCapitalRuntime", lambda: SimpleNamespace(
        preflight=lambda: {"status": "ready"}, safety_env=lambda: {}))
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", lambda: SimpleNamespace(
        run=lambda **_: {key: True for key in ("trade_item_present", "trade_account_present",
                                               "trade_secret_readable", "trade_secret_nonempty")},
        trade_account_fingerprint=lambda: "fake-only"))
    monkeypatch.setattr(cli, "build_foundersc_native_execution", lambda *a, **k: (object(), object()))
    monkeypatch.setattr(cli, "load_settings", lambda _: SimpleNamespace(base_url="fake", timeout=1, retries=0))
    monkeypatch.setattr(cli, "XiaocaoClient", lambda **_: object())
    monkeypatch.setattr(cli, "write_book_b_live_morning_receipt", lambda *args: None)
    seen = []

    def rendezvous(request, **kwargs):
        seen.append((request, kwargs))
        return {"status": "timed_out", "supporting_health": "degraded", "fallback": "neutral"}

    def core(config, **kwargs):
        assert config.policy_root == Path("output/live/kol_policy/decisions")
        review = kwargs["review_rendezvous"]({"test": "production-wiring"})
        return BookBLiveMorningReceipt(config.trade_date, "no_action", "FAKE_ONLY", 0, (), (),
            str(config.freeze_path), str(config.allocation_facts_path), str(config.state_dir), review_rendezvous=review)

    monkeypatch.setattr(cli, "_review_rendezvous", rendezvous)
    monkeypatch.setattr(cli, "run_book_b_live_morning", core)
    assert cli.main(["--date", "2026-08-24", "--state-dir", str(tmp_path)]) == 0
    assert seen == [({"test": "production-wiring"}, {"poll_seconds": 1.0})]


def test_rendezvous_does_not_accept_a_policy_read_that_finishes_after_timeout(tmp_path, monkeypatch):
    cli = _morning_cli(monkeypatch)
    request = _review_request(tmp_path, budget=2)
    root = Path(request["policy_root"])
    _publish(root, MORNING)
    elapsed = [0.0]
    original = cli.read_policy

    def slow_read(*args):
        result = original(*args)
        elapsed[0] = 3
        return result

    monkeypatch.setattr(cli, "read_policy", slow_read)
    receipt = cli._review_rendezvous(request, now=lambda: MORNING + timedelta(seconds=elapsed[0]),
        monotonic=lambda: elapsed[0], sleep=lambda _: pytest.fail("read already exhausted the wait budget"))
    assert receipt["status"] == "timed_out" and receipt["supporting_health"] == "degraded"
