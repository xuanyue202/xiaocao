import hashlib
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from xiaocao.live.history_query_evidence import history_query_evidence
from xiaocao.live.trading_execution import (BrokerStatus, ExecutionReceipt, ExecutionState,
                                          InMemoryExecutionStore, TradingExecution)
from tests.test_foundersc_native_broker import FakeNative, _adapter, _plan

pytestmark = pytest.mark.app_simulation
DATE = "2026-08-30"
TIME = "2026-08-30T12:39:09.550Z"


def capture():
    return {
        "kind": "history-orders", "rows": [], "row_count": 0, "observed_at": TIME,
        "history_scope": {
            "schema_version": "native-history-scope.v1", "kind": "history-orders",
            "start_date": DATE, "end_date": DATE, "date_controls_proven": True,
            "all_pages_captured": True, "total_row_count": 0, "observed_at": TIME,
        },
    }


@pytest.mark.parametrize("change,reason", [
    ({"history_scope": None}, "SCOPE_UNPROVEN"),
    ({"date_controls_proven": False}, "SCOPE_UNPROVEN"),
    ({"start_date": "2026-08-29"}, "DATE_RANGE_MISMATCH"),
    ({"all_pages_captured": False}, "CAPTURE_INCOMPLETE"),
    ({"total_row_count": 1}, "CAPTURE_INCOMPLETE"),
    ({"total_row_count": False}, "CAPTURE_INCOMPLETE"),
    ({"observed_at": "2026-08-30T12:38:09Z"}, "CAPTURE_BINDING_UNPROVEN"),
    ({"observed_at": "2026-08-30T12:39:09"}, "CAPTURE_BINDING_UNPROVEN"),
])
def test_empty_visible_table_is_not_absence_without_bound_complete_scope(change, reason):
    data = capture()
    if "history_scope" in change:
        data.update(change)
    else:
        data["history_scope"].update(change)
    proof = history_query_evidence(data, kind="history-orders", trade_date=DATE)
    assert proof["complete"] is False
    assert proof["reason"] == "NATIVE_HISTORY_QUERY_" + reason
    assert proof["requested_start"] == DATE
    assert len(proof["normalized_capture_sha256"]) == 64


def test_complete_scope_checks_every_row_date_and_preserves_capture_identity():
    data = capture()
    proof = history_query_evidence(data, kind="history-orders", trade_date=DATE)
    assert proof["complete"] is True
    data["rows"] = [{"委托日期": "20260829"}]
    data["row_count"] = data["history_scope"]["total_row_count"] = 1
    changed = history_query_evidence(data, kind="history-orders", trade_date=DATE)
    assert changed["reason"] == "NATIVE_HISTORY_QUERY_ROWS_OUTSIDE_PROVEN_RANGE"
    assert changed["normalized_capture_sha256"] != proof["normalized_capture_sha256"]


def test_legacy_native_history_is_explicitly_incomplete_without_missing_order_claim(tmp_path):
    class LegacyNative(FakeNative):
        def read_query(self, **kwargs):
            receipt = super().read_query(**kwargs).as_dict()
            receipt["query_readback"].pop("history_scope", None)
            return self._receipt(**receipt)
    native = LegacyNative()
    receipt = _adapter(native)._reconcile_prior_day_rows(
        _plan(), requested_shares=100, expected_order_id="6004811")
    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.reason == "NATIVE_HISTORY_QUERY_SCOPE_UNPROVEN"
    assert receipt.retry_allowed is False and receipt.receipt_mapping is False
    assert "exact_order_match_count" not in receipt.locator_proof
    assert receipt.locator_proof["current_observation"]["history-orders"]["complete"] is False
    assert native.query_calls == ["history-orders"]
    assert native.submit_calls == native.cancel_calls == native.unlock_calls == 0
    plan = _plan()
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    previous = ExecutionReceipt(plan_id=plan.plan_id, plan_hash=plan.plan_hash,
                                state=ExecutionState.UNKNOWN)
    execution = TradingExecution(broker=_adapter(native), store=store)
    current = execution._receipt_from_broker(plan, previous, receipt, ExecutionState.UNKNOWN, 100)
    recorded = store.append(plan=plan, receipt=current)
    reloaded = store.current(plan.plan_id)
    assert reloaded.event_id == recorded.event_id
    ref = reloaded.locator_proof["current_capture_refs"][0]
    payload = Path(ref["path"]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == ref["document_sha256"]
    document = json.loads(payload)
    assert document["native_readback"]["rows"] == receipt.locator_proof["history_capture_documents"][0]["native_readback"]["rows"]
    assert document["normalized_readback"]["observed_at"] == ref["observed_at"]
    canonical = json.dumps(document["normalized_readback"], ensure_ascii=False,
                           sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == ref["normalized_readback_sha256"]
    assert ref["normalized_readback_sha256"] == reloaded.locator_proof["current_observation"]["history-orders"]["normalized_capture_sha256"]
    assert "history_capture_documents" not in reloaded.locator_proof


def test_capture_archive_keeps_all_rows_but_removes_credentials(tmp_path):
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    readback = {"rows": [{"委托编号": str(n)} for n in range(200)],
                "password": "must-not-persist", "metadata": {"token": "secret", "scope": "history"}}
    document = {"kind": "history-orders", "observed_at": TIME,
                "native_readback": readback, "normalized_readback": readback}
    ref = store.archive_history_capture(document)
    stored = json.loads(Path(ref["path"]).read_text())
    assert len(stored["native_readback"]["rows"]) == 200
    assert "password" not in stored["native_readback"]
    assert stored["native_readback"]["metadata"] == {"scope": "history"}
    assert store.archive_history_capture(document) == ref


def test_failed_second_history_query_preserves_both_full_captures_after_reload(tmp_path):
    native = FakeNative()
    native.history_orders = [{**native.orders[0], "委托日期": DATE.replace("-", "")}]
    native.history_trades = [{"证券代码": "malformed", "成交日期": DATE.replace("-", ""),
                             "委托编号": str(n)} for n in range(200)]
    adapter = _adapter(native)
    receipt = adapter.reconcile(_plan(), {"broker_order_id": "6004811", "requested_shares": 100})
    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.error_code == "NATIVE_RECONCILE_FAILED_NO_RETRY"
    store = InMemoryExecutionStore(tmp_path / "events.jsonl")
    plan = _plan()
    previous = ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.UNKNOWN)
    current = TradingExecution(broker=adapter, store=store)._receipt_from_broker(
        plan, previous, receipt, ExecutionState.UNKNOWN, 100)
    store.append(plan=plan, receipt=current)
    refs = store.current(plan.plan_id).locator_proof["current_capture_refs"]
    captures = {ref["kind"]: json.loads(Path(ref["path"]).read_bytes()) for ref in refs}
    assert captures["history-orders"]["normalized_readback"]["rows"] == native.history_orders
    assert len(captures["history-trades"]["native_readback"]["rows"]) == 200
    assert captures["history-trades"]["native_readback"]["rows"] == native.history_trades
    assert captures["history-trades"]["normalized_readback"] is None
    assert next(ref for ref in refs if ref["kind"] == "history-trades")["normalization_available"] is False
    for ref in refs:
        assert hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest() == ref["document_sha256"]
    assert native.submit_calls == native.cancel_calls == native.unlock_calls == 0


def test_reused_adapter_does_not_attach_prior_history_to_current_query_failure(monkeypatch):
    adapter = _adapter(FakeNative())
    adapter._reconcile_prior_day_rows(_plan(), requested_shares=100, expected_order_id="6004811")
    assert "history-orders" in adapter.last_query_readbacks
    assert adapter._failed_read_evidence(None)["history_capture_documents"] == []
    def fail_current_query(*args, **kwargs):
        raise RuntimeError("fixture current query failure")
    monkeypatch.setattr(adapter, "_reconcile_rows", fail_current_query)
    current_plan = replace(_plan(), trade_date=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat())
    receipt = adapter.reconcile(current_plan, {"broker_order_id": "6004811"})
    assert receipt.normalized_status() == BrokerStatus.UNKNOWN
    assert receipt.locator_proof["history_capture_documents"] == []
    assert receipt.locator_proof["failed_native_readbacks"] == {}
    assert receipt.locator_proof["failed_native_rows"] == []
