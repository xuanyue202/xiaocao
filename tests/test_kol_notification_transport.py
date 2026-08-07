from __future__ import annotations

import hashlib
import json

import pytest

from xiaocao.kol.notification_transport import (
    NotificationTransport,
    NotificationTransportError,
)


def _canonical(value: dict) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _request(**overrides) -> dict:
    value = {
        "schema_version": 1,
        "notification_id": "notice-1",
        "source_task": {
            "host_id": "remote-control:host-1",
            "thread_id": "thread-1",
        },
        "report_id": "kr_report_1",
        "stable_report_url": "https://reader.example/kol-reports/kr_report_1",
        "title": "投资情报｜小草：弱轮动下的周一剧本",
        "body": (
            "高开不追，显著低开后再验证修复；断板低吸也只用约 10% 仓位试错。"
            "\n\n查看完整报告：https://reader.example/kol-reports/kr_report_1"
        ),
        "recipients": ["Chen", "FeiFei"],
        "missing_confirmation": {
            "kind": "recipient_missing_confirmation",
            "reference": "user-confirmed-20260803",
            "confirmed_at": "2026-08-03T00:40:00+08:00",
        },
        "original_failure": {
            "claimed_at": "2026-08-03T00:21:59+08:00",
            "recorded_at": "2026-08-03T00:22:00+08:00",
            "status": (
                "failed recipients: Chen=error: ConnectionError; "
                "FeiFei=error: ConnectionError"
            ),
            "delivered_recipients": [],
        },
    }
    value.update(overrides)
    value["content_sha256"] = hashlib.sha256(
        f"{value['title']}\n{value['body']}".encode()
    ).hexdigest()
    value["handoff_id"] = hashlib.sha256(_canonical(value).encode()).hexdigest()
    return value


def _makeup_request(**overrides) -> dict:
    value = _request()
    value.pop("handoff_id")
    value.pop("missing_confirmation")
    value.pop("original_failure")
    value["makeup_authorization"] = {
        "kind": "user_authorized_makeup",
        "reference": "codex-user-message-20260807",
        "authorized_at": "2026-08-07T11:50:00+08:00",
    }
    value.update(overrides)
    value["content_sha256"] = hashlib.sha256(
        f"{value['title']}\n{value['body']}".encode()
    ).hexdigest()
    value["handoff_id"] = hashlib.sha256(_canonical(value).encode()).hexdigest()
    return value


def test_transport_requires_explicit_missing_recipient_confirmation(tmp_path):
    request = _request(missing_confirmation={})
    unsigned = dict(request)
    unsigned.pop("handoff_id")
    request["handoff_id"] = hashlib.sha256(
        _canonical(unsigned).encode()
    ).hexdigest()

    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )

    with pytest.raises(
        NotificationTransportError,
        match="missing-recipient confirmation",
    ):
        transport.send(request, sender=lambda *_args: {"status": "ok"})


def test_transport_sends_each_recipient_once_and_replays_from_receipts(tmp_path):
    calls: list[str] = []

    def sender(_title: str, _body: str, recipient: str) -> dict:
        calls.append(recipient)
        return {"status": "ok", "detail": "ok"}

    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )
    request = _request()

    first = transport.send(request, sender=sender)
    second = transport.send(request, sender=sender)

    assert calls == ["Chen", "FeiFei"]
    assert first["status"] == "delivered"
    assert second["status"] == "delivered"
    assert first == second
    assert first["handoff_id"] == request["handoff_id"]
    assert first["content_sha256"] == request["content_sha256"]
    assert first["recipient_receipts"] == second["recipient_receipts"]
    assert set(first["recipient_receipts"]) == {"Chen", "FeiFei"}
    assert first["receipt_sha256"] == hashlib.sha256(
        _canonical({k: v for k, v in first.items() if k != "receipt_sha256"}).encode()
    ).hexdigest()


def test_user_authorized_makeup_sends_each_recipient_exactly_once(tmp_path):
    calls: list[str] = []

    def sender(_title: str, _body: str, recipient: str) -> dict:
        calls.append(recipient)
        return {"status": "ok", "detail": "ok"}

    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )
    request = _makeup_request()

    first = transport.send(request, sender=sender)
    second = transport.send(request, sender=sender)

    assert calls == ["Chen", "FeiFei"]
    assert first == second
    assert set(first["recipient_receipts"]) == {"Chen", "FeiFei"}


def test_makeup_authorization_rejects_ambiguous_dual_authority(tmp_path):
    request = _makeup_request(
        missing_confirmation={
            "kind": "recipient_missing_confirmation",
            "reference": "also-present",
            "confirmed_at": "2026-08-07T11:51:00+08:00",
        }
    )
    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )

    with pytest.raises(
        NotificationTransportError,
        match="makeup authorization is invalid",
    ):
        transport.send(request, sender=lambda *_args: {"status": "ok"})


def test_transport_retries_only_a_proven_safe_failure(tmp_path):
    attempts = {"Chen": 0, "FeiFei": 0}

    def sender(_title: str, _body: str, recipient: str) -> dict:
        attempts[recipient] += 1
        if recipient == "FeiFei" and attempts[recipient] == 1:
            return {
                "status": "failed",
                "detail": "error: ConnectionRefusedError",
                "retry_safety": "safe",
                "failure_phase": "connect",
            }
        return {"status": "ok", "detail": "ok"}

    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )
    request = _request()

    with pytest.raises(NotificationTransportError, match="safe retry is allowed"):
        transport.send(request, sender=sender)
    result = transport.send(request, sender=sender)

    assert attempts == {"Chen": 1, "FeiFei": 2}
    assert result["status"] == "delivered"


def test_transport_stops_on_uncertain_recipient_without_resending(tmp_path):
    calls: list[str] = []

    def sender(_title: str, _body: str, recipient: str) -> dict:
        calls.append(recipient)
        return {
            "status": "uncertain",
            "detail": "error: ConnectionResetError",
            "retry_safety": "uncertain",
            "failure_phase": "response",
        }

    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen", "FeiFei"),
    )
    request = _request()

    with pytest.raises(NotificationTransportError, match="outcome is uncertain"):
        transport.send(request, sender=sender)
    with pytest.raises(NotificationTransportError, match="outcome is uncertain"):
        transport.send(request, sender=sender)

    assert calls == ["Chen"]


def test_transport_rejects_unconfigured_or_malformed_targets(tmp_path):
    transport = NotificationTransport(
        tmp_path,
        configured_recipients=lambda: ("Chen",),
    )

    with pytest.raises(NotificationTransportError, match="not configured"):
        transport.send(_request(), sender=lambda *_args: {"status": "ok"})

    request = _request(recipients=["Chen"])
    request["body"] += "\nhttps://reader.example/second-link"
    request["content_sha256"] = hashlib.sha256(
        f"{request['title']}\n{request['body']}".encode()
    ).hexdigest()
    unsigned = dict(request)
    unsigned.pop("handoff_id")
    request["handoff_id"] = hashlib.sha256(
        _canonical(unsigned).encode()
    ).hexdigest()

    with pytest.raises(NotificationTransportError, match="exactly one stable report URL"):
        transport.send(request, sender=lambda *_args: {"status": "ok"})
