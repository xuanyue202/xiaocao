"""Blocked EOD delivery preserves its source and never repeats uncertain sends."""
import json
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
