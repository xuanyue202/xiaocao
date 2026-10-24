"""Explicit read-only WeChat session diagnosis; absence of a prompt is unknown."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess


OBSERVER = Path(__file__).resolve().parents[3] / 'scripts/kol_liuguan_session.swift'


def _bounds(value):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)
            or value[2] <= 0 or value[3] <= 0):
        raise ValueError('invalid_bounds')
    return value


def _matches(left, right):
    return all(abs(a - b) < 2 for a, b in zip(left, right))


def _classify(value):
    state, reason = value['state'], value['reason']
    if (state, reason) in {('not_running', 'application_not_running'),
                          ('unknown', 'ax_unavailable'), ('unknown', 'application_binding_not_unique')}:
        return {'state': state, 'reason': reason}
    if (state, reason) != ('observed', 'window_metadata_available'):
        raise ValueError('invalid_observer_state')
    ax, cg = value['ax_windows'], value['visible_windows']
    if not isinstance(ax, list) or not isinstance(cg, list):
        raise ValueError('invalid_windows')
    ax_bounds = [_bounds(row['bounds']) for row in ax]
    cg_bounds = [_bounds(row['bounds']) for row in cg]
    for row in ax:
        if any(type(row.get(key)) is not bool for key in ('minimized', 'security_text', 'acknowledgement')):
            raise ValueError('invalid_ax_metadata')
    ids = [row['id'] for row in cg]
    if any(type(wid) is not int or wid <= 0 for wid in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid_window_ids')
    candidates = [[j for j, bounds in enumerate(cg_bounds) if _matches(rect, bounds)] for rect in ax_bounds]
    ambiguous = any(len(js) > 1 for js in candidates) or any(
        sum(j in js for js in candidates) > 1 for j in range(len(cg)))
    if ambiguous:
        return {'state': 'unknown', 'reason': 'ambiguous_window_binding'}
    for row, js in zip(ax, candidates):
        if len(js) == 1 and not row['minimized'] and row['security_text'] and row['acknowledgement']:
            return {'state': 'reauthentication_required', 'reason': 'visible_account_security_prompt',
                    'window_id': ids[js[0]]}
    return {'state': 'unknown', 'reason': 'no_visible_security_prompt'}


def session_status() -> dict:
    result = {'read_only': True, 'state': 'unknown', 'reason': 'observer_unavailable',
              'authenticated_verified': False, 'native_inputs': 0, 'activations': 0,
              'proxy_changes': 0}
    try:
        observed = subprocess.run(['/usr/bin/swift', str(OBSERVER)],
                                  capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return result
    try:
        value = json.loads(observed.stdout)
        if observed.returncode or not isinstance(value, dict) or value.get('read_only') is not True:
            raise ValueError('invalid_observation')
        timestamp = datetime.fromisoformat(value['observed_at'])
        if timestamp.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - timestamp).total_seconds() <= 10:
            raise ValueError('stale_observation')
        if 'pid' in value and (type(value['pid']) is not int or value['pid'] <= 1):
            raise ValueError('invalid_pid')
        if value['state'] == 'observed' and type(value.get('pid')) is not int:
            raise ValueError('unbound_observation')
        classified = _classify(value)
    except (ValueError, TypeError, KeyError, OverflowError):
        result['reason'] = 'observer_response_invalid'
        return result
    result.update(classified)
    result['observed_at'] = value['observed_at']
    if 'pid' in value:
        result['pid'] = value['pid']
    return result
