"""Owner audit and exact claimed-order continuation; no real APP calls."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from xiaocao.live.morning_checklist import MorningChecklist
from xiaocao.live.morning_kol_inputs import acknowledge_inputs
from xiaocao.live.morning_order_wait import await_orders
from xiaocao.live.morning_notifications import message
from xiaocao.live.trading_execution import ExecutionState
from xiaocao.runner_recovery import _hash

pytestmark = pytest.mark.app_simulation
NOW = datetime(2026, 10, 14, 1, 24, tzinfo=timezone.utc)


def checklist(tmp_path):
    return MorningChecklist.create(tmp_path, {"trade_date": "2026-10-14", "owner_thread_id": "owner"})


def test_checklist_preserves_boundary_proof_and_exposes_expiry(tmp_path):
    check = checklist(tmp_path)
    check.record("app_boundary", "passed", evidence={"account_binding": "proven"},
                 observed_at=NOW, valid_until=NOW + timedelta(seconds=60))
    first = check.read()["items"]["app_boundary"]["observation_path"]
    check.record("app_boundary", "passed", evidence={"second": True}, observed_at=NOW+timedelta(seconds=30),
                 valid_until=NOW + timedelta(seconds=90))
    item = check.read(now=NOW+timedelta(seconds=91))["items"]["app_boundary"]
    assert item["status"] == "stale"
    assert item["first_observed_at"] == NOW.isoformat()
    assert json.loads(Path(first).read_text())["evidence"] == {"account_binding": "proven"}
    assert check.read()["items"]["app_boundary"]["status"] == "passed"


def test_checklist_never_marks_passed_without_evidence(tmp_path):
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        checklist(tmp_path).record("app_ready", "passed")


def test_warm_inputs_reject_partial_or_changed_coverage(tmp_path):
    check = checklist(tmp_path)
    path = tmp_path / "inputs.json"
    payload = {"binding": check.binding, "viewpoint_ids": ["a", "b"], "source_fingerprint": "fp", "rules": []}
    path.write_text(json.dumps(payload))
    check.record("kol_projection", "passed", evidence={"input_path": str(path.resolve()), "input_sha256": _hash(payload)})
    dispatch_path = tmp_path / "dispatch.json"
    dispatch_path.write_text(json.dumps({"worker_id": "worker", "accepted": True, "model": "gpt-6-sol",
        "reasoning_effort": "xhigh", "dispatched_at": "2026-10-14T09:05:00+08:00",
        "binding": check.binding, "input_sha256": _hash(payload),
        "tool_arguments": {"model": "gpt-6-sol", "reasoning_effort": "xhigh", "fork_turns": "none"},
        "tool_result": {"task_name": "worker"}}))
    loaded_path = tmp_path / "loaded.json"
    loaded_path.write_text(json.dumps({"worker_id": "worker", "loaded_viewpoint_ids": ["b", "a"],
                                       "dispatch_path": str(dispatch_path)}))
    with pytest.raises(ValueError, match="COVERAGE_MISMATCH"):
        acknowledge_inputs(check, path, worker_id="worker", loaded_ids=["a"], loaded_receipt_path=loaded_path)
    assert acknowledge_inputs(check, path, worker_id="worker", loaded_ids=["b", "a"], loaded_receipt_path=loaded_path)["loaded_count"] == 2
    payload["source_fingerprint"] = "changed"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="COVERAGE_MISMATCH"):
        acknowledge_inputs(check, path, worker_id="worker", loaded_ids=["a", "b"], loaded_receipt_path=loaded_path)


def order(state=ExecutionState.ACKNOWLEDGED, claim="claim"):
    return SimpleNamespace(plan_id="p", plan_hash="hash", submit_claim_id=claim,
                           state=state, submit_chain_uncertain=False, cancel_chain_uncertain=False)


def test_await_orders_waits_until_auction_then_reconciles_same_claim():
    clock = [NOW.replace(minute=27)]
    reads = []
    rows = [order()]
    plan = SimpleNamespace(plan_id="p", plan_hash="hash", trade_date="2026-10-14")
    def reconcile(plan):
        reads.append(clock[0])
        return order(ExecutionState.FILLED)
    await_orders([plan], rows, reconcile=reconcile, deadline=clock[0]+timedelta(minutes=8),
        now=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0]+timedelta(seconds=seconds)),
        on_progress=lambda rows: None)
    assert reads == [NOW.replace(minute=30)]
    assert rows[0].state == ExecutionState.FILLED
    assert rows[0].submit_claim_id == "claim"


def test_await_orders_keeps_original_deadline_and_does_not_query_before_it():
    rows = [order()]
    clock = [NOW.replace(minute=27)]
    plan = SimpleNamespace(plan_id="p", plan_hash="hash", trade_date="2026-10-14")
    calls = []
    deadline = clock[0] + timedelta(seconds=15)
    await_orders([plan], rows, reconcile=lambda plan: calls.append(plan), deadline=deadline,
        now=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0]+timedelta(seconds=seconds)),
        on_progress=lambda rows: None)
    assert not calls and clock[0] == deadline
    assert rows[0].state == ExecutionState.ACKNOWLEDGED


def test_await_orders_rejects_missing_or_changed_submit_claim():
    plan = SimpleNamespace(plan_id="p", plan_hash="hash", trade_date="2026-10-14")
    with pytest.raises(ValueError, match="CLAIM_UNPROVEN"):
        await_orders([plan], [order(claim=None)], reconcile=lambda plan: None,
                     deadline=NOW+timedelta(minutes=8), now=lambda: NOW, sleep=lambda n: None, on_progress=lambda rows: None)
    with pytest.raises(ValueError, match="MAPPING_CHANGED"):
        await_orders([plan], [order()], reconcile=lambda plan: order(claim="new-claim"),
                     deadline=NOW+timedelta(minutes=8), now=lambda: NOW.replace(minute=30),
                     sleep=lambda n: None, on_progress=lambda rows: None)


def test_pending_notice_includes_known_order_without_fabricating_fills():
    facts = {"status": "unresolved", "orders": [{"state": "acknowledged", "broker_order_id": "6000110",
        "submit_chain_uncertain": False, "cancel_chain_uncertain": False, "filled_shares": 0,
        "fill_quantity_proven": False}]}
    title, body = message("result", "2026-10-14", facts)
    assert "等待成交" in title and "受阻" not in title
    assert "成交数量待核对" in body and "6000110" in body
    _, body = message("golden-window", "2026-10-14", facts)
    assert "6000110" in body and "成交数量待核对" in body
