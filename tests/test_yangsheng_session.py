"""Read-only session evidence must never become assumed login or UI recovery."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from xiaocao.yangsheng import session


def observation(**changes):
    value = {'read_only': True, 'state': 'observed', 'reason': 'window_metadata_available',
             'pid': 40127, 'observed_at': datetime.now(timezone.utc).isoformat(),
             'ax_windows': [{'bounds': [10, 20, 500, 400], 'minimized': False,
                             'security_text': True, 'acknowledgement': True}],
             'visible_windows': [{'id': 14087, 'bounds': [10, 20, 500, 400]}]}
    value.update(changes)
    return value


def test_security_prompt_is_reported_without_recovery_or_raw_window_text(monkeypatch):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(observation()), ''))
    monkeypatch.setattr(session.subprocess, 'run', runner)
    result = session.session_status()
    assert result['state'] == 'reauthentication_required'
    assert result['authenticated_verified'] is False
    assert result['native_inputs'] == result['activations'] == result['proxy_changes'] == 0
    assert runner.call_count == 1
    assert runner.call_args.args[0][0] == '/usr/bin/swift'


@pytest.mark.parametrize('state,reason', [
    ('unknown', 'ax_unavailable'),
    ('not_running', 'application_not_running'),
])
def test_absent_prompt_never_proves_login(monkeypatch, state, reason):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0,
        json.dumps(observation(state=state, reason=reason, window_id=None)), ''))
    monkeypatch.setattr(session.subprocess, 'run', runner)
    result = session.session_status()
    assert result['state'] == state
    assert result['authenticated_verified'] is False


@pytest.mark.parametrize('payload', ['not-json', '[]', '{}',
    json.dumps(observation(read_only=False)),
    json.dumps(observation(state='authenticated')),
    json.dumps(observation(visible_windows=[{'id': None, 'bounds': [10, 20, 500, 400]}])),
    json.dumps(observation(pid=True)),
    json.dumps(observation(observed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())),
    json.dumps(observation(observed_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())),
    json.dumps(observation(reason='ax_unavailable')),
    json.dumps(observation(state=[])),
])
def test_untrusted_or_unbound_observation_stays_unknown(monkeypatch, payload):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, payload, ''))
    monkeypatch.setattr(session.subprocess, 'run', runner)
    result = session.session_status()
    assert result['state'] == 'unknown'
    assert result['reason'] == 'observer_response_invalid'
    assert result['authenticated_verified'] is False
    assert runner.call_count == 1


@pytest.mark.parametrize('failure', [OSError('missing'), subprocess.TimeoutExpired('swift', 8)])
def test_observer_failure_does_not_retry_launch_or_click(monkeypatch, failure):
    runner = Mock(side_effect=failure)
    monkeypatch.setattr(session.subprocess, 'run', runner)
    assert session.session_status()['state'] == 'unknown'
    assert runner.call_count == 1


@pytest.mark.parametrize('offset', [0, 1.5])
def test_same_geometry_on_multiple_ax_or_cg_windows_is_ambiguous(monkeypatch, offset):
    for side in ('ax_windows', 'visible_windows'):
        value = observation()
        duplicate = dict(value[side][0])
        duplicate['bounds'] = list(duplicate['bounds'])
        value[side][0]['bounds'][0] -= offset
        duplicate['bounds'][0] += offset
        if side == 'visible_windows':
            duplicate['id'] += 1
        value[side].append(duplicate)
        monkeypatch.setattr(session.subprocess, 'run', Mock(return_value=
            subprocess.CompletedProcess([], 0, json.dumps(value), '')))
        result = session.session_status()
        assert result['state'] == 'unknown'
        assert result['reason'] == 'ambiguous_window_binding'
        assert 'window_id' not in result


def test_hidden_or_minimized_security_text_is_not_current_protection(monkeypatch):
    for changed in ('offscreen', 'minimized', 'no_prompt', 'no_button'):
        value = observation()
        if changed == 'offscreen':
            value['visible_windows'][0]['bounds'][0] += 200
        elif changed == 'minimized':
            value['ax_windows'][0]['minimized'] = True
        elif changed == 'no_prompt':
            value['ax_windows'][0]['security_text'] = False
        else:
            value['ax_windows'][0]['acknowledgement'] = False
        monkeypatch.setattr(session.subprocess, 'run', Mock(return_value=
            subprocess.CompletedProcess([], 0, json.dumps(value), '')))
        result = session.session_status()
        assert result['state'] == 'unknown'
        assert result['authenticated_verified'] is False
        assert 'window_id' not in result


@pytest.mark.parametrize('extra_id', ['private-window-text', {'private': 'contents'}])
def test_unknown_state_never_echoes_arbitrary_window_metadata(monkeypatch, extra_id):
    value = observation(state='unknown', reason='ax_unavailable', window_id=extra_id)
    monkeypatch.setattr(session.subprocess, 'run', Mock(return_value=
        subprocess.CompletedProcess([], 0, json.dumps(value), '')))
    result = session.session_status()
    assert result['state'] == 'unknown'
    assert 'window_id' not in result
    assert 'private' not in json.dumps(result)
