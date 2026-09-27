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
