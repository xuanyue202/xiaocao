"""Daytime login test authority cannot reach order actions."""
from types import SimpleNamespace
import pytest
from xiaocao.live.authentication_test_scope import AUTH_TEST_ENV, require_authentication_command
from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient

pytestmark = [pytest.mark.app_simulation, pytest.mark.app_authentication]


@pytest.mark.parametrize('command', ['prepare', 'prepare-order', 'submit', 'submit-prepared', 'cancel', 'cancel-selected', 'advance'])
def test_auth_only_client_rejects_order_effect_before_helper(monkeypatch, command):
    monkeypatch.setenv(AUTH_TEST_ENV, '1')
    client = FounderscNativeAXClient()
    monkeypatch.setattr(client, '_run_locked', lambda *a, **k: pytest.fail('must not reach helper'))
    with pytest.raises(RuntimeError, match='ORDER_ACTION_FORBIDDEN'):
        client._run(command)


def test_explicit_login_test_port_can_probe_with_normal_window_closed(monkeypatch):
    monkeypatch.setenv(AUTH_TEST_ENV, '1')
    monkeypatch.setenv('XIAOCAO_APP_SIMULATION_TEST', '1')
    client = FounderscNativeAXClient()
    seen = []
    monkeypatch.setattr(client, '_run_locked', lambda command, *a, **k: seen.append(command) or SimpleNamespace())
    client._run('probe')
    assert seen == ['probe']


def test_auth_flag_does_not_change_normal_order_authority_when_absent(monkeypatch):
    monkeypatch.delenv(AUTH_TEST_ENV, raising=False)
    require_authentication_command('submit')  # Existing production gates own it.


@pytest.mark.parametrize("command", ["open-order-surface", "open-query-surface", "read-query"])
def test_auth_finish_can_reach_read_only_trade_navigation(monkeypatch, command):
    monkeypatch.setenv(AUTH_TEST_ENV, "1")
    client = FounderscNativeAXClient()
    seen = []
    monkeypatch.setattr(client, "_run_locked", lambda command, *a, **k: seen.append(command))
    client._run(command)
    assert seen == [command]


def test_native_auth_dispatch_guard(tmp_path):
    import json
    import shutil
    import subprocess
    from pathlib import Path
    compiler = shutil.which("swiftc")
    if not compiler:
        pytest.skip("Swift compiler required")
    source = (Path(__file__).resolve().parents[1] / "native/foundersc_ax_executor/Sources/FounderscNativeAX/main.swift").read_text()
    routine = source[source.index("private func authenticationTestCommandAllowed("):source.index("let arguments = Array(CommandLine.arguments.dropFirst())")]
    harness = "import Foundation\n" + routine + '\nprint(String(data:try! JSONSerialization.data(withJSONObject:CommandLine.arguments.dropFirst().map { authenticationTestCommandAllowed($0) }),encoding:.utf8)!)\n'
    path=tmp_path / "guard.swift"
    binary=tmp_path / "guard"
    path.write_text(harness)
    result=subprocess.run([compiler,str(path),"-o",str(binary)],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stderr
    commands=["prepare-order","submit-prepared-order","cancel-order","confirm-pending-order","acknowledge-submit-rejection","open-query-surface","open-order-surface","read-query","fill-client-login-stdin"]
    result=subprocess.run([str(binary),*commands],capture_output=True,text=True,check=True,timeout=4)
    assert json.loads(result.stdout)==[False]*5+[True]*4
