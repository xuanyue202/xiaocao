"""Trading-window protection without contacting the APP or Keychain."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from xiaocao.live import app_test_window as window
from xiaocao.live import foundersc_native_ax as native


@pytest.mark.parametrize('clock,allowed', [
    ('2026-09-14T08:59:59+08:00', True),
    ('2026-09-14T09:00:00+08:00', False),
    ('2026-09-14T12:00:00+08:00', False),
    ('2026-09-14T14:59:59+08:00', False),
    ('2026-09-14T15:00:00+08:00', True),
    ('2026-09-18T09:30:00+08:00', False),
    ('2026-09-19T09:30:00+08:00', True),
    ('2026-09-20T14:30:00+08:00', True),
    ('2026-09-14T01:00:00+00:00', False),
    ('2026-09-14T07:00:00+00:00', True),
])
def test_china_wall_clock_boundaries(clock, allowed):
    assert window.app_tests_allowed(datetime.fromisoformat(clock)) is allowed


def test_naive_clock_does_not_guess_host_timezone():
    with pytest.raises(ValueError):
        window.app_tests_allowed(datetime(2026, 9, 14, 8))


@pytest.mark.parametrize('module', [
    'scripts.foundersc_app_rehearsal', 'scripts.foundersc_app_batch_rehearsal',
    'scripts.test_foundersc_reliability',
])
def test_all_test_entrypoints_stop_before_any_setup(monkeypatch, module):
    from importlib import import_module
    entry = import_module(module)
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: False)
    monkeypatch.setattr(sys, 'argv', ['blocked-test'])  # Not even argument parsing is reached.
    with pytest.raises(window.AppTestWindowClosed, match='APP_TEST_TIME_BLOCKED'):
        entry.main()


def make_client(tmp_path, monkeypatch):
    helper = tmp_path / 'helper'
    helper.write_text('unused')
    helper.chmod(0o700)
    calls = []
    def runner(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 0, json.dumps({
            'schema_version': 2, 'helper_version': 10, 'status': 'ok'}))
    return native.FounderscNativeAXClient(helper_path=helper, runner=runner), calls


def test_waiting_test_cannot_dispatch_after_0900(tmp_path, monkeypatch):
    client, calls = make_client(tmp_path, monkeypatch)
    allowed = [True]
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: allowed[0])
    @contextmanager
    def delayed_lock():
        allowed[0] = False
        yield 0
    monkeypatch.setattr(native, 'app_session', delayed_lock)
    with pytest.raises(window.AppTestWindowClosed):
        client.probe()
    assert calls == []


def test_client_remains_test_scoped_after_leaving_context(tmp_path, monkeypatch):
    monkeypatch.delenv(window.TEST_CONTEXT_ENV, raising=False)
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: True)
    @window.app_test_only
    def create():
        return make_client(tmp_path, monkeypatch)
    client, calls = create()
    assert not window.app_test_context_active()
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: False)
    with pytest.raises(window.AppTestWindowClosed):
        client.probe()
    assert calls == []


def test_normal_production_client_is_not_restricted(tmp_path, monkeypatch):
    monkeypatch.delenv(window.TEST_CONTEXT_ENV, raising=False)
    client, calls = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: False)
    assert client.probe().payload['status'] == 'ok'
    assert len(calls) == 1


def test_each_command_rechecks_window(tmp_path, monkeypatch):
    client, calls = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: True)
    client.probe()
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: False)
    with pytest.raises(window.AppTestWindowClosed):
        client.probe()
    assert len(calls) == 1


def test_session_closes_lock_when_wait_crosses_cutoff(tmp_path, monkeypatch):
    from xiaocao.live import foundersc_session as session
    allowed = [True]
    monkeypatch.setattr(window, 'app_tests_allowed', lambda: allowed[0])
    monkeypatch.setattr(session, 'session_path', lambda: tmp_path / 'app.lock')
    original_flock = session.fcntl.flock
    descriptors = []
    def acquire_then_cross(descriptor, operation):
        original_flock(descriptor, operation)
        descriptors.append(descriptor)
        allowed[0] = False
    monkeypatch.setattr(session.fcntl, 'flock', acquire_then_cross)
    with pytest.raises(window.AppTestWindowClosed):
        with session.app_session():
            pytest.fail('APP session must not be entered')
    assert session._descriptor is None
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    # A rejected test must leave the session usable by the production caller.
    monkeypatch.delenv(window.TEST_CONTEXT_ENV, raising=False)
    with session.app_session() as descriptor:
        os.fstat(descriptor)


def test_direct_pytest_skips_app_cases_before_fixtures(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path/'conftest.py').write_text('''
from xiaocao.live import app_test_window

def pytest_configure(config):
    app_test_window.app_tests_allowed = lambda: False
''')
    (tmp_path/'test_foundersc_sample.py').write_text('''
import pytest
@pytest.fixture(autouse=True)
def must_not_run():
    raise AssertionError("APP setup was reached")
def test_automatic_app_marker():
    raise AssertionError("APP test ran")
''')
    (tmp_path/'test_ordinary.py').write_text('''
import pytest
@pytest.mark.app_simulation
def test_explicit_marker():
    raise AssertionError("APP test ran")
def test_unrelated():
    assert True
''')
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(root),str(root/'src')])}
    env.pop(window.TEST_CONTEXT_ENV, None)
    result = subprocess.run([sys.executable,'-m','pytest','-q','-p','tests.conftest',str(tmp_path)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stdout+result.stderr
    assert '1 passed, 2 skipped' in result.stdout
