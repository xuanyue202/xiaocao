import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import morning_preflight_alert as alert
from xiaocao.live.notify import wecom_transport_readiness
from xiaocao.live.trading_execution import TradingIncidentOutbox


def test_transport_readiness_redacts_credentials_and_recipients():
    result = wecom_transport_readiness(env={
        "XIAOCAO_WECOM_RELAY_URL": "https://example.invalid/send",
        "XIAOCAO_WECOM_RELAY_TOKEN": "secret-token",
        "XIAOCAO_WECOM_USER_IDS": "private-recipient",
    }, audience="trading")
    assert result == {"status": "configured", "recipient_count": 1, "missing": []}
    assert "secret-token" not in json.dumps(result)
    assert "private-recipient" not in json.dumps(result)


def test_market_assessment_uses_one_uncached_authentication_probe(monkeypatch):
    client = object()
    factory = Mock(return_value=client)
    probe = Mock(return_value={
        "status": "blocked", "reason": "MARKET_DATA_AUTH_REQUIRED",
        "checks": [{"auth_failure_category": "MARKET_LOGIN_CAPTCHA_REQUIRED"}],
    })
    monkeypatch.setattr(alert, "load_settings", lambda _: SimpleNamespace(base_url="https://example.invalid"))
    monkeypatch.setattr(alert, "XiaocaoClient", factory)
    monkeypatch.setattr(alert, "authentication_preflight", probe)
    result = alert.assess_market_auth("2026-09-23")
    assert result["status"] == "blocked"
    assert result["reason"] == "MARKET_LOGIN_CAPTCHA_REQUIRED"
    factory.assert_called_once_with(base_url="https://example.invalid", timeout=8, retries=0, cache=None)
    probe.assert_called_once_with(client, "2026-09-23")


def test_exact_book_b_receipt_and_producer_failure_are_distinct(tmp_path):
    book = tmp_path / "book.json"
    book.write_text(json.dumps({
        "trade_date": "2026-09-23", "run_id": "2026-09-23-abc",
        "status": "blocked", "reason": "LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED",
        "failed_stage": "preflight",
    }))
    result = alert.assess_receipt("book-b", "2026-09-23", book)
    assert result["status"] == "blocked"
    assert result["reason"] == "LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED"
    with pytest.raises(ValueError, match="DATE_OR_RUN_MISMATCH"):
        alert.assess_receipt("book-b", "2026-09-24", book)

    producer = tmp_path / "producer.json"
    producer.write_text(json.dumps({
        "market_date": "2026-09-23", "automation": "morning-prerecommend",
        "deterministic_status": "failed", "exit_code": 1,
    }))
    assert alert.assess_receipt("producer", "2026-09-23", producer)["reason"] == "PRODUCER_DETERMINISTIC_FAILED"


def test_blocker_wecom_delivery_is_durable_and_deduplicated(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "wecom_transport_readiness", lambda **_: {
        "status": "configured", "recipient_count": 1, "missing": [],
    })
    sender = Mock(return_value={"wecom": "ok"})
    outbox = TradingIncidentOutbox(tmp_path / "incidents.jsonl")
    assessment = {
        "kind": "market-auth", "trade_date": "2026-09-23", "status": "blocked",
        "reason": "MARKET_LOGIN_CAPTCHA_REQUIRED", "evidence": "fresh_official_authentication_probe",
    }
    first = alert.deliver_blocker(assessment, outbox=outbox, sender=sender)
    second = alert.deliver_blocker(assessment, outbox=outbox, sender=sender)
    assert first["delivery"] == "delivered"
    assert second["delivery"] == "already_delivered"
    sender.assert_called_once()
    rows = [json.loads(line) for line in (tmp_path / "incidents.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["pending", "delivered"]
    assert rows[1]["result"] == {"wecom": "ok"}


def test_unconfigured_transport_keeps_pending_incident_without_send(monkeypatch, tmp_path):
    monkeypatch.setattr(alert, "wecom_transport_readiness", lambda **_: {
        "status": "blocked", "recipient_count": 0,
        "missing": ["XIAOCAO_WECOM_USER_IDS"],
    })
    sender = Mock()
    outbox = TradingIncidentOutbox(tmp_path / "incidents.jsonl")
    result = alert.deliver_blocker({
        "kind": "producer", "trade_date": "2026-09-23", "status": "blocked",
        "reason": "PRODUCER_DETERMINISTIC_FAILED", "evidence": "receipt=sample",
    }, outbox=outbox, sender=sender)
    assert result["delivery"] == "transport_unconfigured"
    assert result["transport_missing"] == ["XIAOCAO_WECOM_USER_IDS"]
    sender.assert_not_called()
    rows = [json.loads(line) for line in (tmp_path / "incidents.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["pending"]


def test_ready_preflight_does_not_notify(tmp_path):
    sender = Mock()
    result = alert.deliver_blocker({
        "kind": "market-auth", "trade_date": "2026-09-23", "status": "reachable",
        "reason": None, "evidence": "fresh_official_authentication_probe",
    }, outbox=TradingIncidentOutbox(tmp_path / "incidents.jsonl"), sender=sender)
    assert result["delivery"] == "not_needed"
    sender.assert_not_called()
    assert not (tmp_path / "incidents.jsonl").exists()


def test_broken_market_probe_still_escalates_without_exposing_exception(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(alert, "assess_market_auth", Mock(side_effect=RuntimeError("secret remote response")))
    captured = []

    def fake_delivery(assessment, *, outbox):
        captured.append(assessment)
        return {**assessment, "delivery": "delivered"}

    monkeypatch.setattr(alert, "deliver_blocker", fake_delivery)
    assert alert.main([
        "--date", "2026-09-23", "--kind", "market-auth", "--outbox", str(tmp_path / "outbox.jsonl"),
    ]) == 2
    assert captured[0]["reason"] == "MARKET_PREFLIGHT_PROBE_ERROR"
    assert "secret remote response" not in capsys.readouterr().out
