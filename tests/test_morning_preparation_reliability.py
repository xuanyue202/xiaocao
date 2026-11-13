"""Missed preparation targets must not waste source work or discard legal support."""
import json
import os
import copy
from datetime import datetime

from tests.test_kol_opening_preparation import case, save, NOW
from tests.test_kol_rolling_preparation import source, current_input, EARLY
from xiaocao.kol import opening_preparation as prep, rolling_preparation as rolling
from xiaocao.kol.preparation_adoption import adoption, read_adoption


def test_intended_use_rejects_expiring_source_before_dispatch(source, monkeypatch, capsys):
    from scripts import kol_trading_prepare as cli
    from xiaocao.kol import trading_context as tc
    monkeypatch.setattr(tc, 'build_trading_context', lambda **kw: {})
    monkeypatch.setattr(tc, 'latest_report_coverage', lambda *a, **kw: {'scope':'fixture'})
    monkeypatch.setattr(tc, 'write_trading_projection', lambda *a, **kw: source['inputs']['projection'])
    class Clock:
        @classmethod
        def now(cls, tz):
            return EARLY.astimezone(tz)
    monkeypatch.setattr(cli, 'datetime', Clock)
    result = cli.main(['rolling-inputs', '--root', str(source['root']),
                       '--output-dir', str(source['root']/'target'),
                       '--fresh-through', '2026-10-23T11:30:00+08:00'])
    receipt = json.loads(capsys.readouterr().out)
    assert result == 2 and receipt['status'] == 'blocked'
    assert receipt['reason'] == 'KOL_PREPARATION_SOURCE_EXPIRES_BEFORE_USE'
    assert receipt['source_readiness']['expired_before_use_count'] == len(source['inputs']['viewpoint_ids'])
    assert receipt['model_dispatch'] == 'not_required_source_expiry'


def test_current_consumer_accepts_completed_late_preparation_inside_original_window(source, monkeypatch):
    late = NOW.replace(minute=24)
    value = prep.accept_preparation(source['path'], source['draft'],
        {**source['review'], 'reviewed_at': late.isoformat()}, source['dispatch'], source['context'], now=late)
    path = save(source['root']/'late-complete.json', value)
    binding = dict(automation_id='xiaocao-book-b-live-morning', owner_thread_id='app-owner',
                   trade_date='2026-10-23', runner_pid=os.getpid())
    monkeypatch.setenv('CODEX_AUTOMATION_ID', binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID', binding['owner_thread_id'])
    current = current_input(source, binding, as_of=NOW.replace(minute=25))
    receipt = adoption(path, current, now=NOW.replace(minute=25), judgment_mode='conditional_first_v2')
    assert receipt['preparation_timing'] == 'late_ready'
    assert receipt['policy_adoption'] == 'not_performed'
    proof = save(source['root']/'late-adoption.json', receipt)
    assert read_adoption(proof, path, current, now=NOW.replace(minute=26)) == receipt


def test_early_source_owner_exposes_preparation_before_long_capture():
    from scripts.kol_automation_slot_gate import preparation_obligation
    early = datetime.fromisoformat('2026-11-13T07:30:00+08:00')
    value = preparation_obligation('xiaocao-kol-hourly-low-bandwidth-operation', early)
    assert value['next_action'] == 'prepare_published_snapshot'
    assert value['capture_completion_required'] is False
    assert value['authority'] == 0
    assert value['source_publication_required'] is True


def test_audit_fingerprint_change_reuses_exact_semantics_for_current_request(case):
    from tests.test_kol_prepared_policy import prepared_packet
    from xiaocao.kol.prepared_policy import materialize
    from xiaocao.live.kol_policy import decision_sha256
    prepared, _, facts = prepared_packet(case)
    current = copy.deepcopy(case['inputs'])
    projection = prep.read_projection(current['projection'])
    projection['context_sha256'] = '9'*64
    projection['source_fingerprint'] = '8'*64
    projection['projection_sha256'] = prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    save(case['root']/'changed-audit-projection.json', projection)
    current.update(projection={'projection_path':str(case['root']/'changed-audit-projection.json'),
        'projection_sha256':projection['projection_sha256']}, source_fingerprint=projection['source_fingerprint'])
    path = save(case['root']/'changed-audit-input.json', current)
    facts.pop('request_sha256')
    facts['judgment_mode'] = 'conditional_first_v2'
    packet = prep.opening_packet(case['root']/'prepared.json', path, facts, now=NOW.replace(minute=26))
    facts['request_sha256'] = decision_sha256(facts)
    result = materialize(prepared, packet, facts, now=NOW.replace(minute=26))
    assert result['status'] == 'independent_review_required'
    assert result['source_verification'] == result['publication'] == 'not_performed'
    assert packet['semantic_source_sha256'] == packet['prepared_semantic_source_sha256']


import pytest

@pytest.mark.parametrize('mode, clock, error', [
    ('conditional_first_v1', '09:24:00', 'LATE_FOR_OPENING'),
    ('conditional_first_v2', '09:27:30', 'AFTER_SUPPORT_CUTOFF'),
    ('conditional_first_v2', '09:28:00', 'AFTER_SUPPORT_CUTOFF'),
])
def test_late_recovery_preserves_legacy_and_hard_cutoff(mode, clock, error):
    from xiaocao.live.morning_support import preparation_timing
    with pytest.raises(ValueError, match=error):
        preparation_timing(datetime.fromisoformat('2026-11-13T'+clock+'+08:00'),
                           '2026-11-13', mode=mode)


def test_v2_keeps_earlier_original_budget():
    from xiaocao.live.morning_support import support_deadline
    request = {'judgment_mode':'conditional_first_v2', 'trade_date':'2026-11-13',
        'requested_at':'2026-11-13T09:25:40+08:00', 'max_wait_seconds':30,
        'review_wait_until':'2026-11-13T09:27:30+08:00', 'entry_deadline':'2026-11-13T09:30:00+08:00'}
    assert support_deadline(request).isoformat() == '2026-11-13T09:26:10+08:00'


def test_semantic_delta_cannot_use_audit_only_reuse(case):
    from tests.test_kol_prepared_policy import prepared_packet
    from xiaocao.kol.prepared_policy import materialize
    from xiaocao.live.kol_policy import decision_sha256
    prepared, packet, request = prepared_packet(case)
    request.pop('request_sha256')
    request['judgment_mode'] = 'conditional_first_v2'
    request['request_sha256'] = decision_sha256(request)
    packet['request_sha256'] = request['request_sha256']
    packet['semantic_source_sha256'] = 'a'*64
    packet['prepared_semantic_source_sha256'] = 'b'*64
    packet['packet_sha256'] = prep.canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'})
    with pytest.raises(ValueError):
        materialize(prepared, packet, request, now=NOW.replace(minute=26))



def test_distant_morning_horizon_stops_before_projection_and_model(source, monkeypatch, capsys):
    from scripts import kol_trading_prepare as cli
    from xiaocao.kol import trading_context as tc
    monkeypatch.setattr(tc,'build_trading_context',lambda **kw:pytest.fail('Unreachable horizon needs no source work'))
    class Clock:
        @classmethod
        def now(cls,tz):return EARLY.astimezone(tz)
    monkeypatch.setattr(cli,'datetime',Clock)
    original=source['prepared_path'].read_bytes()
    result=cli.main(['rolling-inputs','--root',str(source['root']),
                    '--output-dir',str(source['root']/'weekend-horizon'),
                    '--fresh-through','2026-10-26T09:27:30+08:00'])
    receipt=json.loads(capsys.readouterr().out)
    assert result==2 and receipt['reason']=='KOL_PREPARATION_TARGET_OUTSIDE_CURRENT_HORIZON'
    assert receipt['model_dispatch']=='not_required_preparation_horizon'
    assert source['prepared_path'].read_bytes()==original
