"""Blocked EOD delivery preserves its source and never repeats uncertain sends."""
import json
import hashlib
from pathlib import Path

import pytest

from scripts.book_b_eod_alert import notify_eod_blocker
from xiaocao.live.eod_automation_gate import claim_eod_slot

pytestmark = pytest.mark.app_simulation


@pytest.fixture
def original(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_AUTOMATION_ID", "xiaocao-daily-eod")
    monkeypatch.setenv("CODEX_THREAD_ID", "eod-owner")
    identity = claim_eod_slot(tmp_path, "app", "2026-10-09")
    path = tmp_path / "state/runs/intraday/archive/original-eod.json"
    path.parent.mkdir(parents=True)
    payload = {"trade_date": "2026-10-09", "phase": "eod", "status": "blocked",
        "reason": "NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:client_login_required",
        "route": "native-app", "execute_sells_requested": False,
        "run_id": "original-eod", "run_receipt_path": str(path), "automation_identity": identity}
    path.write_text(json.dumps(payload))
    return tmp_path, path, payload


def configured(**kwargs):
    assert kwargs == {"audience": "trading"}
    return {"status": "configured"}


def test_original_blocker_delivered_once_and_archive_unchanged(original):
    root, path, _ = original
    raw = path.read_bytes()
    sent = []

    def sender(title, body, **kwargs):
        sent.append((title, body, kwargs))
        return {"wecom": "ok"}

    first = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    second = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    assert first["delivery"] == "delivered" and second["delivery"] == "already_delivered"
    assert first["pending_count"] == 0 and len(sent) == 1
    assert path.read_bytes() == raw


def test_uncertain_transport_is_not_resent(original):
    root, path, _ = original
    sent = []

    def sender(*args, **kwargs):
        sent.append(1)
        raise TimeoutError("uncertain")

    first = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    second = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    assert first["delivery"] == "pending_error"
    assert second["delivery"] == "pending_reconcile"
    assert len(sent) == 1 and second["pending_count"] == 1


@pytest.mark.parametrize("field,value", [("CODEX_THREAD_ID", "peer"),
    ("CODEX_AUTOMATION_ID", "xiaocao-intraday-monitor-1455")])
def test_peer_identity_rejected_before_send(original, monkeypatch, field, value):
    root, path, _ = original
    monkeypatch.setenv(field, value)
    with pytest.raises(ValueError, match="OWNER_MISMATCH"):
        notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("sent"))
    assert not (root / "output/live/book_b_eod_incident_notices.jsonl").exists()


def test_slot_mismatch_rejected_before_send(original):
    root, path, payload = original
    payload["automation_identity"]["pid"] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="SLOT_MISMATCH"):
        notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("sent"))


@pytest.mark.parametrize("status,reason", [("no_action", "NON_TRADING_DAY"),
    ("blocked", "LIVE_BOOK_B_CALENDAR_UNPROVEN"),
    ("blocked", "LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING")])
def test_no_action_calendar_gap_and_collision_do_not_send(original, status, reason):
    root, path, payload = original
    payload.update(status=status, reason=reason)
    path.write_text(json.dumps(payload))
    result = notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("sent"))
    assert result["status"] == "not_applicable"


def test_proved_presend_failure_can_retry(original):
    root, path, _ = original
    sent = []

    def sender(*args, **kwargs):
        sent.append(1)
        if len(sent) == 1:
            return {"wecom": "failed", "wecom_recipients": {
                "fixture": {"retry_safety": "safe", "failure_phase": "connect"}}}
        return {"wecom": "ok"}

    first = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    second = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    assert first["delivery"] == "pending_unproven" and second["delivery"] == "delivered"
    assert len(sent) == 2


def test_clock_only_change_does_not_create_new_notification(original):
    root, path, payload = original
    sent = []
    sender = lambda *a, **k: sent.append(a) or {"wecom": "ok"}
    first = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    payload["audit_clock"] = "later observation of unchanged problem"
    path.write_text(json.dumps(payload))
    second = notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    assert first["incident_id"] == second["incident_id"]
    assert len(sent) == 1


def test_current_new_order_and_all_blockers_remain_visible(original):
    root, path, payload = original
    sent = []
    sender = lambda *a, **k: sent.append(a) or {"wecom": "ok"}
    payload.update(reason="LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED",
        eod_review={"active_plan_ids": ["current"], "blockers": [
            {"kind": "execution"}, {"kind": "cash"}, {"kind": "fees"}]},
        reconciliation_receipts=[{"plan_id": "current", "broker_order_id": "new-order", "state": "unknown"},
                                 {"plan_id": "closed-history", "broker_order_id": "old-order", "state": "unknown"}])
    path.write_text(json.dumps(payload))
    notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    body = sent[0][1]
    assert "new-order" in body and "old-order" not in body
    assert all(word in body for word in ["资金归属", "实际费用", "委托状态"])
    payload["reconciliation_receipts"][0]["broker_order_id"] = "another-order"
    path.write_text(json.dumps(payload))
    notify_eod_blocker(path, root=root, sender=sender, readiness=configured)
    assert len(sent) == 2


def test_historical_closure_and_accounting_pending_do_not_send(original):
    root, path, payload = original
    payload["eod_review"] = {"active_plan_ids": [], "status": "accounting_pending",
        "historical_order_resolutions": [{"broker_order_id": "6007019"}],
        "blockers": [{"kind": "cash"}, {"kind": "fees"}]}
    path.write_text(json.dumps(payload))
    result = notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("sent"))
    assert result["status"] == "not_actionable"


@pytest.mark.parametrize("delivered", [True, False])
def test_exact_legacy_archive_preserves_delivery_and_uncertainty(original, delivered):
    from xiaocao.live.incident_delivery import enqueue_notice, deliver_pending
    root, path, payload = original
    outbox = root / "output/live/book_b_eod_incident_notices.jsonl"
    identifier = hashlib.sha256(b"book-b-eod\0" + path.read_bytes()).hexdigest()
    enqueue_notice(outbox, identifier=identifier, title="legacy", body="original text")
    def old_sender(*a, **k):
        if not delivered:
            raise TimeoutError("uncertain legacy send")
        return {"wecom": "ok"}
    deliver_pending(outbox, sender=old_sender, readiness=configured)
    before = outbox.read_bytes()
    result = notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("resent legacy"))
    assert result["delivery"] == ("already_delivered" if delivered else "pending_reconcile")
    assert outbox.read_bytes() == before


@pytest.mark.parametrize("delivered", [True, False])
def test_mixed_legacy_history_does_not_replay_unchanged_current_incident(original, delivered):
    from xiaocao.live.incident_delivery import enqueue_notice, deliver_pending
    root, path, payload = original
    payload.update(reason="LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED",
        reconciliation_receipts=[{"plan_id": "history", "broker_order_id": "old", "state": "unknown"},
            {"plan_id": "current", "broker_order_id": "current-order", "state": "unknown"}])
    path.write_text(json.dumps(payload))
    legacy_path = path.with_name("legacy.json")
    legacy_path.write_bytes(path.read_bytes())
    outbox = root / "output/live/book_b_eod_incident_notices.jsonl"
    identifier = hashlib.sha256(b"book-b-eod\0" + legacy_path.read_bytes()).hexdigest()
    enqueue_notice(outbox, identifier=identifier, title="legacy", body="unchanged current problem")
    def old_sender(*a, **k):
        if not delivered:
            raise TimeoutError("uncertain")
        return {"wecom": "ok"}
    deliver_pending(outbox, sender=old_sender, readiness=configured)
    before = outbox.read_bytes()
    payload["eod_review"] = {"active_plan_ids": ["current"], "historical_order_resolutions": [
        {"plan_id": "history", "status": "economically_closed"}], "blockers": [{"kind": "execution"}]}
    path.write_text(json.dumps(payload))
    result = notify_eod_blocker(path, root=root, sender=lambda *a, **k: pytest.fail("resent"))
    assert result["delivery"] == ("already_delivered" if delivered else "pending_reconcile")
    assert outbox.read_bytes() == before
    payload["reconciliation_receipts"][1]["filled_shares"] = 1
    path.write_text(json.dumps(payload))
    assert notify_eod_blocker(path, root=root, sender=lambda *a, **k: {"wecom": "ok"},
        readiness=configured)["delivery"] == "delivered"
