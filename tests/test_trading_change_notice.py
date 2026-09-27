from pathlib import Path

from scripts.trading_change_notice import deliver_pending, pending_notices
from xiaocao.live.trading_execution import TradingIncidentOutbox


def test_failed_delivery_stays_pending_and_later_retries_once(tmp_path: Path) -> None:
    path = tmp_path / "notices.jsonl"
    outbox = TradingIncidentOutbox(path)
    outbox.enqueue(incident_id="change-1", title="策略变更", body="证据、验证和回滚")
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
    TradingIncidentOutbox(path).enqueue(
        incident_id="change-2", title="安全门变更", body="证据和回滚"
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
