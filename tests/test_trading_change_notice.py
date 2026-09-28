from pathlib import Path

from scripts.trading_change_notice import deliver_pending, pending_notices, enqueue_notice
from xiaocao.live.trading_execution import TradingIncidentOutbox


def test_failed_delivery_stays_pending_and_later_retries_once(tmp_path: Path) -> None:
    path = tmp_path / "notices.jsonl"
    outbox = TradingIncidentOutbox(path)
    enqueue_notice(path, identifier="change-1", title="策略变更", body="证据、验证和回滚")
    unavailable = lambda **kwargs: {"status": "unconfigured", "missing": ["relay"]}
    assert deliver_pending(path, readiness=unavailable)[0]["delivery"] == "pending_transport"
    assert len(pending_notices(path)) == 1

    sent = []
    ready = lambda **kwargs: {"status": "configured"}
    sender = lambda title, body, **kwargs: (sent.append((title, body)) or {"wecom": "ok"})
    assert deliver_pending(path, readiness=ready, sender=sender)[0]["delivery"] == "delivered"
    assert pending_notices(path) == []
    assert deliver_pending(path, readiness=ready, sender=sender) == []
    assert len(sent) == 1


def test_uncertain_relay_response_keeps_notice_without_recipient_in_output(
    tmp_path: Path,
) -> None:
    path = tmp_path / "notices.jsonl"
    enqueue_notice(path,
        identifier="change-2", title="安全门变更", body="证据和回滚"
    )
    results = deliver_pending(
        path,
        readiness=lambda **_: {"status": "configured"},
        sender=lambda *_args, **_kwargs: {
            "wecom": "failed recipients: private-user=SSLError",
            "wecom_recipients": {
                "private-user": {
                    "status": "uncertain",
                    "failure_phase": "response",
                    "retry_safety": "uncertain",
                }
            },
        },
    )
    assert results == [{
        "incident_id": "change-2",
        "delivery": "pending_unproven",
        "failure_phases": ["response"],
        "retry_safety": ["uncertain"],
    }]
    assert len(pending_notices(path)) == 1
    calls = []
    second = deliver_pending(path, readiness=lambda **_: {"status": "configured"},
        sender=lambda *a, **k: calls.append(a))
    assert second[0]["delivery"] == "pending_reconcile" and calls == []


def test_change_notice_retries_only_proved_pre_send_failure(tmp_path):
    path, calls = tmp_path / "notice.jsonl", []
    enqueue_notice(path, identifier="safe", title="change", body="evidence")
    def sender(*args, **kwargs):
        calls.append(args)
        return {"wecom": "failed", "wecom_recipients": {"private": {
            "status": "failed", "retry_safety": "safe", "failure_phase": "connect"}}} if len(calls) == 1 else {"wecom": "ok"}
    ready = lambda **_: {"status": "configured"}
    assert deliver_pending(path, sender=sender, readiness=ready)[0]["delivery"] == "pending_unproven"
    assert deliver_pending(path, sender=sender, readiness=ready)[0]["delivery"] == "delivered"
    assert len(calls) == 2


def test_legacy_pending_has_no_proof_for_blind_retry(tmp_path):
    path = tmp_path / "notice.jsonl"
    TradingIncidentOutbox(path).enqueue(incident_id="legacy", title="change", body="evidence")
    enqueue_notice(path, identifier="legacy", title="change", body="evidence")
    calls = []
    assert deliver_pending(path, readiness=lambda **_: {"status": "configured"},
        sender=lambda *a, **k: calls.append(a))[0]["delivery"] == "pending_reconcile"
    assert calls == []


def test_change_notice_sender_crash_remains_reconcile_only(tmp_path):
    path, calls = tmp_path / "notice.jsonl", []
    enqueue_notice(path, identifier="crash", title="change", body="evidence")
    def sender(*args, **kwargs):
        calls.append(args)
        raise TimeoutError()
    ready = lambda **_: {"status": "configured"}
    assert deliver_pending(path, sender=sender, readiness=ready)[0]["delivery"] == "pending_error"
    assert deliver_pending(path, sender=sender, readiness=ready)[0]["delivery"] == "pending_reconcile"
    assert len(calls) == 1
