"""Tests for the multi-channel notifier (src/xiaocao/live/notify.py).

WeCom relay is exercised through an injected poster so no network or popups fire.
"""
from __future__ import annotations

from xiaocao.live import notify as N


def _capturing_poster(status=200, text='{"ok":true}'):
    calls = []

    def poster(url, payload, *, headers=None, verify=True):
        calls.append((url, payload, headers, verify))
        return status, text

    poster.calls = calls
    return poster


def test_no_channels_when_nothing_configured():
    # macos opt-out, no relay env -> nothing fires.
    assert N.notify("t", "b", macos=False, env={}) == {}


def test_wecom_fires_when_relay_config_present():
    poster = _capturing_poster()
    env = {
        N.ENV_WECOM_RELAY_URL: "https://clawsg/send",
        N.ENV_WECOM_RELAY_TOKEN: "tok",
        N.ENV_WECOM_USER_ID: "Chen",
    }
    res = N.notify("卖点触发 000001.XSHG", "dd -8%", env=env, poster=poster)
    assert res["wecom"] == "ok"
    url, payload, headers, verify = poster.calls[0]
    assert url == "https://clawsg/send"
    assert payload == {
        "accountId": "default",
        "userId": "Chen",
        "text": "卖点触发 000001.XSHG\ndd -8%",
    }
    assert headers["Authorization"] == "Bearer tok"
    assert verify is True


def test_wecom_base_url_appends_send_and_honors_account_and_insecure():
    poster = _capturing_poster(text='{"errcode":0,"errmsg":"ok"}')
    res = N.notify(
        "t",
        "b",
        env={
            N.ENV_WECOM_RELAY_URL: "https://clawsg",
            N.ENV_WECOM_RELAY_TOKEN: "tok",
            N.ENV_WECOM_TO_USER: "Chen",
            N.ENV_WECOM_ACCOUNT_ID: "prod",
            N.ENV_WECOM_INSECURE: "true",
        },
        poster=poster,
    )
    assert res["wecom"] == "ok"
    url, payload, _headers, verify = poster.calls[0]
    assert url == "https://clawsg/send"
    assert payload["accountId"] == "prod"
    assert verify is False


def test_wecom_non_200_is_reported_not_raised():
    poster = _capturing_poster(status=500, text="boom")
    res = N.wecom_notify("https://clawsg/send", "t", "b", token="tok", user_id="Chen", poster=poster)
    assert res.startswith("http 500")


def test_wecom_200_error_body_is_not_swallowed_as_ok():
    # Relay /send can report a semantic failure in a 200 body. A body whose errmsg
    # contains "ok" must NOT be read as success.
    poster = _capturing_poster(status=200, text='{"ok":false,"errmsg":"not ok: invalid token"}')
    res = N.wecom_notify("https://clawsg/send", "t", "b", token="tok", user_id="Chen", poster=poster)
    assert res != "ok" and res.startswith("http 200")


def test_wecom_success_markers_are_ok():
    for body in ('{"ok":true}', '{"errcode":0,"errmsg":"ok"}', '{"code":0}', '{"success":true}', ""):
        poster = _capturing_poster(status=200, text=body)
        assert N.wecom_notify("https://clawsg/send", "t", "b", token="tok", user_id="Chen", poster=poster) == "ok"


def test_wecom_network_error_never_raises():
    def boom(url, payload, *, headers=None, verify=True):
        raise ConnectionError("down")

    res = N.wecom_notify("https://clawsg/send", "t", "b", token="tok", user_id="Chen", poster=boom)
    assert res.startswith("error:")


def test_partial_wecom_config_reports_missing_env():
    res = N.notify("t", "b", macos=False, env={N.ENV_WECOM_RELAY_URL: "https://clawsg"})
    assert res["wecom"].startswith("not configured:")
    assert N.ENV_WECOM_RELAY_TOKEN in res["wecom"]
    assert N.ENV_WECOM_USER_ID in res["wecom"]


def test_notify_routes_only_configured_channels():
    poster = _capturing_poster()
    # relay present, macos opt-out -> only wecom key
    res = N.notify(
        "t",
        "b",
        macos=False,
        env={
            N.ENV_WECOM_RELAY_URL: "https://clawsg/send",
            N.ENV_WECOM_RELAY_TOKEN: "tok",
            N.ENV_WECOM_USER_ID: "Chen",
        },
        poster=poster,
    )
    assert set(res) == {"wecom"}


def test_notify_loads_local_env_file(tmp_path, monkeypatch):
    live = tmp_path / "output" / "live"
    live.mkdir(parents=True)
    (live / "notify.env").write_text(
        "\n".join([
            "XIAOCAO_WECOM_RELAY_URL=https://clawsg",
            "XIAOCAO_WECOM_RELAY_TOKEN=file-token",
            "XIAOCAO_WECOM_USER_ID=FileUser",
            "XIAOCAO_WECOM_INSECURE=true",
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in (
        N.ENV_NOTIFY_ENV_FILE,
        N.ENV_WECOM_RELAY_URL,
        N.ENV_WECOM_RELAY_TOKEN,
        N.ENV_WECOM_USER_ID,
        N.ENV_WECOM_TO_USER,
        N.ENV_WECOM_ACCOUNT_ID,
        N.ENV_WECOM_INSECURE,
    ):
        monkeypatch.delenv(key, raising=False)

    poster = _capturing_poster()
    res = N.notify("t", "b", macos=False, poster=poster)
    assert res["wecom"] == "ok"
    url, payload, headers, verify = poster.calls[0]
    assert url == "https://clawsg/send"
    assert payload["userId"] == "FileUser"
    assert headers["Authorization"] == "Bearer file-token"
    assert verify is False


def test_process_env_wins_over_notify_env_file(tmp_path, monkeypatch):
    live = tmp_path / "output" / "live"
    live.mkdir(parents=True)
    (live / "notify.env").write_text(
        "\n".join([
            "XIAOCAO_WECOM_RELAY_URL=https://file",
            "XIAOCAO_WECOM_RELAY_TOKEN=file-token",
            "XIAOCAO_WECOM_USER_ID=FileUser",
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(N.ENV_WECOM_RELAY_URL, "https://env/send")
    monkeypatch.setenv(N.ENV_WECOM_RELAY_TOKEN, "env-token")
    monkeypatch.setenv(N.ENV_WECOM_USER_ID, "EnvUser")

    poster = _capturing_poster()
    res = N.notify("t", "b", macos=False, poster=poster)
    assert res["wecom"] == "ok"
    url, payload, headers, _verify = poster.calls[0]
    assert url == "https://env/send"
    assert payload["userId"] == "EnvUser"
    assert headers["Authorization"] == "Bearer env-token"
