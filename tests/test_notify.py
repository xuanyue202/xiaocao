"""Tests for the multi-channel notifier (src/xiaocao/live/notify.py).

Feishu is exercised through an injected poster so no network or popups fire.
"""
from __future__ import annotations

from datetime import datetime, timezone

from xiaocao.live import notify as N


def _capturing_poster(status=200, text='{"code":0}'):
    calls = []

    def poster(url, payload):
        calls.append((url, payload))
        return status, text

    poster.calls = calls
    return poster


def test_no_channels_when_nothing_configured():
    # macos opt-out, no webhook env -> nothing fires.
    assert N.notify("t", "b", macos=False, env={}) == {}


def test_feishu_fires_when_webhook_present():
    poster = _capturing_poster()
    res = N.notify("卖点触发 000001.XSHG", "dd -8%", env={N.ENV_FEISHU_WEBHOOK: "https://hook"}, poster=poster)
    assert res["feishu"] == "ok"
    url, payload = poster.calls[0]
    assert url == "https://hook"
    assert payload["msg_type"] == "text"
    assert "卖点触发" in payload["content"]["text"] and "dd -8%" in payload["content"]["text"]
    # unsigned bot -> no signature fields
    assert "sign" not in payload


def test_feishu_signs_when_secret_present():
    poster = _capturing_poster()
    now = datetime(2026, 6, 20, 1, 30, tzinfo=timezone.utc)
    N.feishu_notify("https://hook", "t", "b", secret="s3cr3t", poster=poster, now=now)
    _, payload = poster.calls[0]
    ts = int(now.timestamp())
    assert payload["timestamp"] == str(ts)
    assert payload["sign"] == N._feishu_sign("s3cr3t", ts)


def test_feishu_non_200_is_reported_not_raised():
    poster = _capturing_poster(status=500, text="boom")
    res = N.feishu_notify("https://hook", "t", "b", poster=poster)
    assert res.startswith("http 500")


def test_feishu_200_error_body_is_not_swallowed_as_ok():
    # Feishu returns failures as HTTP 200 with an error code. A body whose msg
    # contains the substring "ok" (e.g. "token") must NOT be read as success —
    # otherwise a HARD_STOP alert is silently dropped while the loop logs "ok".
    poster = _capturing_poster(status=200, text='{"code":19001,"msg":"invalid token"}')
    res = N.feishu_notify("https://hook", "t", "b", poster=poster)
    assert res != "ok" and res.startswith("http 200")


def test_feishu_success_code_zero_is_ok():
    for body in ('{"code":0,"msg":"success"}', '{"StatusCode":0}', ""):
        poster = _capturing_poster(status=200, text=body)
        assert N.feishu_notify("https://hook", "t", "b", poster=poster) == "ok"


def test_feishu_network_error_never_raises():
    def boom(url, payload):
        raise ConnectionError("down")

    res = N.feishu_notify("https://hook", "t", "b", poster=boom)
    assert res.startswith("error:")


def test_notify_routes_only_configured_channels():
    poster = _capturing_poster()
    # webhook present, macos opt-out -> only feishu key
    res = N.notify("t", "b", macos=False, env={N.ENV_FEISHU_WEBHOOK: "https://hook"}, poster=poster)
    assert set(res) == {"feishu"}
