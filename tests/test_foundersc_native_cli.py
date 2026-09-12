"""CLI return codes and readiness routing, without the APP or Keychain."""
import json

import pytest

from scripts import foundersc_native_ax as cli
from xiaocao.live.foundersc_native_ax import NativeAXReceipt, FounderscNativeAXError


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    calls = []
    state = {"status": "trade_ready", "surface_state": "trade_ready", "app_running": True,
             "accessibility_trusted": True, "screen_locked": False}
    class Client:
        def __init__(self, **kwargs):
            pass
        def __getattr__(self, name):
            def call(**kwargs):
                calls.append((name, kwargs))
                if state.get("raise"):
                    raise FounderscNativeAXError("NATIVE_AX_COMMAND_TIMEOUT")
                return NativeAXReceipt(dict(state))
            return call
    class Keychain:
        def __init__(self, **kwargs):
            pass
        def run(self, **kwargs):
            assert kwargs == {"read_secrets": False}
            calls.append(("metadata", kwargs))
            return {"trade_item_present": True, "trade_account_present": True}
    monkeypatch.setattr(cli, "FounderscNativeAXClient", Client)
    monkeypatch.setattr(cli, "FounderscKeychainPreflight", Keychain)
    monkeypatch.setattr(cli, "build_helper", lambda **kw: {"status": "reused"})
    monkeypatch.setattr(cli, "source_digest", lambda *_: "test-digest")
    monkeypatch.setattr(cli, "expected_helper_path", lambda *_: tmp_path / "helper")
    monkeypatch.setattr(cli, "_git_readback", lambda: {"runtime_source_clean": True, "sha": "test"})
    def run(*args):
        monkeypatch.setattr(cli.sys, "argv", ["native-cli", *args])
        return cli.main()
    return run, state, calls


@pytest.mark.parametrize("command,status,expected", [
    ("probe", "trade_ready", 0), ("version", "ok", 0),
    ("focus-unlock", "input_focused", 0), ("focus-unlock", "unproven", 2),
    ("fill-login-keychain", "client_login_password_filled", 0),
    ("fill-login-keychain", "unproven", 3),
    ("unlock-keychain", "unlocked", 0), ("unlock-keychain", "unproven", 3),
])
def test_cli_status_and_explicit_flags(boundary, capsys, command, status, expected):
    run, state, calls = boundary
    state["status"] = status
    assert run(command) == expected
    assert json.loads(capsys.readouterr().out)["status"] == status
    assert len(calls) == 1
    if "keychain" in command:
        assert calls[0][1]["explicitly_enabled"] is False


@pytest.mark.parametrize("command", ["build", "preflight", "remote-bootstrap"])
def test_bootstrap_never_mutates_or_reads_secrets(boundary, capsys, command):
    run, state, calls = boundary
    assert run(command) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in {"ready", "reused"}
    assert all(name in {"probe", "metadata"} for name, _ in calls)


def test_locked_machine_does_not_touch_keychain(boundary, capsys):
    run, state, calls = boundary
    state["screen_locked"] = True
    assert run("remote-bootstrap") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert [name for name, _ in calls] == ["probe"]


def test_cli_timeout_is_one_failed_call(boundary, capsys):
    run, state, calls = boundary
    state["raise"] = True
    assert run("probe") == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "NATIVE_AX_COMMAND_TIMEOUT"
    assert len(calls) == 1
