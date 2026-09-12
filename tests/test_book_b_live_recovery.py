from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from tests.test_book_b_live_morning import _frozen_row, _live_allocation_payload, _ready_freeze
from xiaocao.live.book_b_live_morning import (
    BookBLiveMorningConfig, read_durable_live_plan_intent, run_book_b_live_morning,
    reconcile_open_book_b_plans,
)
from xiaocao.live.book_b_live_recovery import run_book_b_live_recovery
from xiaocao.live.book_b_live_lifecycle import open_execution_plan_ids
from xiaocao.live.trading_execution import BrokerReceipt, BrokerStatus, ExecutionReceipt, ExecutionState, ExecutionStore

BEFORE = datetime(2026, 8, 24, 1, 29, tzinfo=timezone.utc)
OPEN = BEFORE + timedelta(minutes=1)


def _seed(tmp_path):
    freeze = tmp_path / "freeze.jsonl"
    freeze.write_text(json.dumps(_frozen_row()) + "\n")
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(_live_allocation_payload()))
    config = BookBLiveMorningConfig("2026-08-24", freeze, allocation, tmp_path / "state",
                                    dated_freeze_receipt=_ready_freeze(), opening_deadline=OPEN)
    first = run_book_b_live_morning(config, now=lambda: BEFORE,
        prepare_only=lambda _: BrokerReceipt(status=BrokerStatus.REJECTED, reason="TEST_AX_CLEAR_FAILURE"),
        execute=lambda _: pytest.fail("prepare failed; no execution"))
    payload = json.loads(next((config.state_dir / "plan_intents").glob("*.json")).read_text())
    return config, read_durable_live_plan_intent(payload), first


def _prepared(plan):
    return BrokerReceipt(status=BrokerStatus.PREPARED, account_binding="proven",
        echoed={"code": plan.code, "side": plan.side, "shares": plan.shares, "limit_price": plan.limit_price},
        field_readback={"submitted": False, "saved": False, "started": False, "form_cleared": True})


def test_repaired_plan_resumes_unchanged_and_preserves_original_failure(tmp_path):
    config, plan, first = _seed(tmp_path)
    original = (config.state_dir / "runs/2026-08-24.json").read_bytes()
    clock = [BEFORE + timedelta(seconds=30)]
    calls = []
    def execute(p):
        calls.append(p)
        return ExecutionStore(config.state_dir / "events.jsonl").append(plan=p,
            receipt=ExecutionReceipt(p.plan_id, p.plan_hash, ExecutionState.FILLED, filled_shares=p.shares))
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: clock[0],
        execute=execute, prepare_only=_prepared,
        wait_for_submit_window=lambda target: clock.__setitem__(0, target),
        review_rendezvous=lambda _: pytest.fail("recovery cannot open a review window"))
    assert result.status == "completed"
    assert len(calls) == 1 and calls[0].plan_hash == plan.plan_hash
    assert clock[0] == OPEN and result.stage_times["prepared"] < OPEN.isoformat()
    assert (config.state_dir / "runs/2026-08-24.json").read_bytes() == original
    assert not open_execution_plan_ids(config.state_dir)
    assert first.failed_stage == "prepare"


def test_late_repair_skips_and_closes_without_prepare_or_submit(tmp_path):
    config, plan, _ = _seed(tmp_path)
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: OPEN,
        prepare_only=lambda _: pytest.fail("already late"), execute=lambda _: pytest.fail("already late"))
    assert result.status == "skipped"
    assert not open_execution_plan_ids(config.state_dir)


def test_closure_is_idempotent_and_claimed_plan_can_only_reconcile(tmp_path):
    config, plan, _ = _seed(tmp_path)
    store = ExecutionStore(config.state_dir / "events.jsonl")
    claimed = store.append(plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash,
        ExecutionState.CLAIMED, submit_claim_id="claim", submit_chain_uncertain=True))
    with pytest.raises(ValueError, match="RECONCILE_ONLY"):
        run_book_b_live_recovery(config, plan_id=plan.plan_id, action="close")
    calls = []
    def reconcile(p):
        calls.append(p.plan_id)
        return store.append(plan=p, receipt=replace(claimed, state=ExecutionState.CANCELLED))
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: OPEN,
        execute=reconcile, prepare_only=lambda _: pytest.fail("claimed cannot prepare"))
    assert result.execution_receipts[0]["state"] == "cancelled" and len(calls) == 1
    run_book_b_live_recovery(config, plan_id=plan.plan_id, action="close")
    assert len(store.events(plan.plan_id)) == 2


def test_checkpoint_expires_unclaimed_opening_plan_without_broker_access(tmp_path):
    config, plan, _ = _seed(tmp_path)
    result = reconcile_open_book_b_plans(config.state_dir, trade_date=config.trade_date,
        now=OPEN + timedelta(minutes=5), execute=lambda _: pytest.fail("local unclaimed closure"))
    assert result[0]["state"] == "skipped" and not open_execution_plan_ids(config.state_dir)


def test_prepare_crossing_opening_deadline_never_submits(tmp_path):
    config, plan, _ = _seed(tmp_path)
    clock = [BEFORE]
    def slow_prepare(p):
        clock[0] = OPEN
        return _prepared(p)
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: clock[0],
        prepare_only=slow_prepare, execute=lambda _: pytest.fail("late prepare"))
    assert result.status == "skipped" and result.failed_stage == "prepare"
    assert not open_execution_plan_ids(config.state_dir)


def test_corrupt_history_cannot_be_treated_as_unsubmitted(tmp_path):
    config, plan, _ = _seed(tmp_path)
    (config.state_dir / "events.jsonl").write_text('{"plan_id":')
    with pytest.raises(ValueError):
        run_book_b_live_recovery(config, plan_id=plan.plan_id, action="close")


def test_persisted_deadline_cannot_be_removed_by_resume_caller(tmp_path):
    config, plan, _ = _seed(tmp_path)
    result = run_book_b_live_recovery(replace(config, opening_deadline=None), plan_id=plan.plan_id,
        now=lambda: OPEN, execute=lambda _: pytest.fail("intent deadline still applies"))
    assert result.status == "skipped" and not open_execution_plan_ids(config.state_dir)


def test_failed_query_preserves_claim_and_recovery_receipt(tmp_path):
    config, plan, _ = _seed(tmp_path)
    store = ExecutionStore(config.state_dir / "events.jsonl")
    store.append(plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash,
        ExecutionState.UNKNOWN, submit_claim_id="claim", submit_chain_uncertain=True))
    def failed_query(_):
        raise RuntimeError("READBACK_TIMEOUT")
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: OPEN,
        execute=failed_query, prepare_only=lambda _: pytest.fail("never prepare"))
    assert result.status == "blocked" and result.failed_stage == "reconcile"
    assert result.execution_receipts[0]["state"] == "unknown"
    assert plan.plan_id in open_execution_plan_ids(config.state_dir)
    assert (config.state_dir / "runs/history" / f"{result.run_id}.json").is_file()


def test_partial_materialization_reports_persisted_intent(tmp_path, monkeypatch):
    import xiaocao.live.book_b_live_morning as morning
    config, plan, _ = _seed(tmp_path)
    next((config.state_dir / "plan_intents").glob("*.json")).unlink()
    original = morning._materialize_or_restore_plans
    def persist_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("AFTER_INTENT_PERSIST")
    monkeypatch.setattr(morning, "_materialize_or_restore_plans", persist_then_fail)
    result = run_book_b_live_morning(config, now=lambda: BEFORE,
        execute=lambda _: pytest.fail("builder failed"))
    assert result.plan_count == 1 and result.persisted_plan_ids == (plan.plan_id,)
    assert result.reason == "AFTER_INTENT_PERSIST" and result.failed_stage == "materialize"


def test_opening_cannot_submit_without_completed_readonly_prepare(tmp_path):
    config, plan, _ = _seed(tmp_path)
    result = run_book_b_live_recovery(config, plan_id=plan.plan_id, now=lambda: BEFORE,
        execute=lambda _: pytest.fail("readonly preparation required"))
    assert result.status == "skipped" and result.reason == "LIVE_OPENING_NOT_PREPARED"
    assert not open_execution_plan_ids(config.state_dir)
