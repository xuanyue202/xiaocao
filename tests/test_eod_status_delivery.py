"""Paper EOD notices use the production durable delivery boundary, without transport."""
from functools import partial

import pytest

from scripts import status as cli
from xiaocao.live import incident_delivery


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LIVE_DIR", tmp_path)
    monkeypatch.setattr("requests.sessions.Session.request",
        lambda *args, **kwargs: pytest.fail("real HTTP transport is forbidden in digest tests"))
    monkeypatch.setattr(cli, "notify", lambda *args, **kwargs: pytest.fail("legacy notifier must never run in an offline test"), raising=False)
    monkeypatch.setattr(cli.status_mod, "format_digest_body", lambda d: "cash=" + str(d["cash"]))
    calls, results = [], []
    def send(title, body, **kwargs):
        calls.append((title, body, kwargs))
        return results.pop(0) if results else {"wecom": "ok"}
    monkeypatch.setattr(cli, "deliver_pending", partial(incident_delivery.deliver_pending,
        sender=send, readiness=lambda **kwargs: {"status": "configured"}), raising=False)
    return tmp_path, calls, results


def digest(**values):
    return {"market_date": "2026-10-19", "cash": 100, "generated_at": "first", **values}


def test_exact_digest_is_sent_once_despite_new_render_clock(delivery):
    root, calls, _ = delivery
    first = cli.push_digest(digest())
    second = cli.push_digest(digest(generated_at="second"))
    assert len(calls) == 1
    assert first["delivery"] == "delivered" and second["delivery"] == "already_delivered"
    assert first["incident_id"] == second["incident_id"]
    assert incident_delivery.pending_notices(root / "paper_eod_status_notices.jsonl") == []


def test_uncertain_digest_stays_reconcile_only_without_resend(delivery):
    root, calls, results = delivery
    results.append({"wecom": "failed", "wecom_recipients": {"recipient": {
        "status": "failed", "failure_phase": "response", "retry_safety": "uncertain"}}})
    assert cli.push_digest(digest())["delivery"] == "pending_unproven"
    assert cli.push_digest(digest())["delivery"] == "pending_reconcile"
    assert len(calls) == 1
    assert len(incident_delivery.pending_notices(root / "paper_eod_status_notices.jsonl")) == 1


def test_proved_presend_failure_can_retry_the_exact_digest(delivery):
    _, calls, results = delivery
    results.append({"wecom": "failed", "wecom_recipients": {"recipient": {
        "status": "failed", "failure_phase": "connect", "retry_safety": "safe"}}})
    assert cli.push_digest(digest())["delivery"] == "pending_unproven"
    assert cli.push_digest(digest())["delivery"] == "delivered"
    assert cli.push_digest(digest())["delivery"] == "already_delivered"
    assert len(calls) == 2 and calls[0] == calls[1]


def test_new_market_date_or_material_body_is_a_distinct_notice(delivery):
    _, calls, _ = delivery
    ids = [cli.push_digest(d)["incident_id"] for d in [digest(), digest(cash=101), digest(market_date="2026-10-20")]]
    assert len(set(ids)) == len(calls) == 3


def test_status_cli_push_uses_durable_boundary(delivery, monkeypatch, capsys):
    _, calls, _ = delivery
    monkeypatch.setattr(cli.status_mod, "build_digest", lambda **kwargs: digest())
    monkeypatch.setattr(cli.status_mod, "format_digest", lambda d: "display")
    monkeypatch.setattr("sys.argv", ["status.py", "--push-wecom"])
    cli.main(); cli.main()
    assert len(calls) == 1
    output = capsys.readouterr()
    assert output.out == "display\ndisplay\n"
    assert "delivered" in output.err and "already_delivered" in output.err


def test_notice_claim_failure_never_reaches_transport(delivery, monkeypatch, capsys):
    _, calls, _ = delivery
    monkeypatch.setattr(cli.status_mod, "build_digest", lambda **kwargs: digest())
    monkeypatch.setattr(cli.status_mod, "format_digest", lambda d: "display")
    monkeypatch.setattr("sys.argv", ["status.py", "--push-wecom"])
    def failed_claim(*args, **kwargs):
        raise OSError("unwritable evidence")
    monkeypatch.setattr(cli, "enqueue_notice", failed_claim)
    cli.main()
    assert calls == []
    assert "supporting-layer degraded" in capsys.readouterr().err
