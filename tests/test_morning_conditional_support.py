"""Pure deadline/semantic admission checks; no APP adapter, market or formal store."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_kol_opening_preparation import case, save, NOW
from tests.test_kol_prepared_policy import prepared_packet
from tests.test_kol_trading_decision import Reader, register, review_for
from xiaocao.kol import opening_preparation as prep, trading_context as tc, trading_decision as td
from xiaocao.live import kol_policy
from xiaocao.live.morning_dispatch import write_warm_dispatch, read_deferred_overlay
from xiaocao.live.morning_support import CONDITIONAL_FIRST, support_deadline


def test_versioned_deadline_never_refunds_original_budget():
    request = dict(requested_at='2026-11-05T09:26:00+08:00',
        entry_deadline='2026-11-05T11:30:00+08:00', max_wait_seconds=120,
        review_wait_until='2026-11-05T09:28:00+08:00')
    assert support_deadline(request).isoformat() == '2026-11-05T09:27:00+08:00'
    request['judgment_mode'] = CONDITIONAL_FIRST
    assert support_deadline(request).isoformat() == '2026-11-05T09:27:30+08:00'
    request['max_wait_seconds'] = 20
    assert support_deadline(request).isoformat() == '2026-11-05T09:26:20+08:00'
    request['review_wait_until'] = '2026-11-05T09:26:05+08:00'
    assert support_deadline(request).isoformat() == '2026-11-05T09:26:05+08:00'


@pytest.mark.parametrize('clock', ['09:30:00', '09:31:00', '13:01:00'])
def test_late_original_morning_never_becomes_new_current_model_budget(clock):
    request = dict(judgment_mode=CONDITIONAL_FIRST, requested_at='2026-11-05T'+clock+'+08:00',
        entry_deadline='2026-11-05T14:57:00+08:00', review_wait_until='2026-11-05T14:57:00+08:00',
        max_wait_seconds=120)
    assert support_deadline(request).isoformat() == '2026-11-05T09:27:30+08:00'


def test_retained_runtime_and_preparation_bind_conditional_instruction_bytes(case):
    from xiaocao.live.runtime_evidence import source_manifest
    from xiaocao.live.runtime_snapshot import freeze_runtime
    prepared, _, _ = prepared_packet(case)
    relative = '.codex/skills/xiaocao-trading/references/kol-conditional-morning.md'
    manifest = source_manifest(case['root'])
    assert relative in manifest
    snapshot = freeze_runtime(case['root'], case['root']/'retained', manifest)
    assert (snapshot/relative).read_bytes() == (case['root']/relative).read_bytes()
    (case['root']/relative).write_text('Changed conditional semantics')
    with pytest.raises(ValueError):
        prep.read_preparation(case['root']/'prepared.json', now=NOW.replace(minute=26))


def test_old_rule_closure_invalidates_for_source_owner_reprepare(case):
    value = prep.read_json(case['path'])
    value['rules'].pop()
    save(case['path'], value)
    with pytest.raises(ValueError, match='KOL_PREPARATION_RULES_CHANGED'):
        prep._inputs(case['path'])


def test_policy_reader_cannot_wait_behind_writer_through_opening_deadline(tmp_path):
    import fcntl
    import subprocess
    import sys
    code = '''
import fcntl,json,sys
from pathlib import Path
from datetime import datetime,timezone
from xiaocao.live.kol_policy import load_decision
p=Path(sys.argv[1]);lock=(p/'.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX)
busy=load_decision(p,'B','paper',datetime.now(timezone.utc))
fcntl.flock(lock,fcntl.LOCK_UN)
clear=load_decision(p,'B','paper',datetime.now(timezone.utc))
print(json.dumps([busy,clear]))
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                            capture_output=True, text=True, timeout=3, check=True)
    import json
    busy, clear = json.loads(result.stdout)
    assert busy['status'] == 'blocked' and 'KOL_POLICY_STORE_BUSY' in busy['reason']
    assert clear['status'] == 'no_decision'


@pytest.mark.parametrize('lock_kind', ['publication_control', 'source_verifications', 'decisions', 'released_control', 'sequential'])
def test_morning_publisher_locks_share_original_budget_without_losing_serialization(tmp_path, lock_kind):
    import subprocess
    import sys
    code = '''
import fcntl,json,sys,threading
from pathlib import Path
from datetime import timedelta
from tests.test_kol_trading_decision import bundle,morning_bundle,NOW
from xiaocao.kol import trading_decision as td
from xiaocao.live import kol_policy
p=Path(sys.argv[1]);kind=sys.argv[2]
decision,review,context,reader,request=morning_bundle(bundle.__wrapped__(p))
budget=.5 if kind in {'released_control','sequential'} else .05
request.update(max_wait_seconds=budget,entry_deadline=(NOW+timedelta(seconds=budget)).isoformat(),
               review_wait_until=(NOW+timedelta(seconds=budget)).isoformat())
request['request_sha256']=kol_policy.decision_sha256({k:v for k,v in request.items() if k!='request_sha256'})
decision['morning_request_sha256']=review['morning_request_sha256']=request['request_sha256']
review['decision_sha256']=kol_policy.decision_sha256(decision)
directory=p/td.POLICY_PATH/('publication_control' if kind in {'released_control','sequential'} else kind)
directory.mkdir(parents=True,exist_ok=True);lock=(directory/'.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX)
timer=None
second_timer=None
if kind=='released_control':
 timer=threading.Timer(.05,lambda:fcntl.flock(lock,fcntl.LOCK_UN));timer.start()
if kind=='sequential':
 second=p/td.POLICY_PATH/'source_verifications';second.mkdir(parents=True,exist_ok=True)
 second_lock=(second/'.lock').open('a+');fcntl.flock(second_lock,fcntl.LOCK_EX)
 timer=threading.Timer(.3,lambda:fcntl.flock(lock,fcntl.LOCK_UN));timer.start()
 second_timer=threading.Timer(.75,lambda:fcntl.flock(second_lock,fcntl.LOCK_UN));second_timer.start()
try:
 result=td.publish_trading_decision(p,decision,review,context,client=reader,clock=lambda:NOW,morning_request=request)
 assert kind=='released_control' and result['status']=='published'
 assert kol_policy.load_decision(p/td.POLICY_PATH/'decisions','B','live',NOW)['status']=='validated'
except td.TradingDecisionError:
 assert kind!='released_control'
 assert not list((p/td.POLICY_PATH/'decisions').glob('*.json'))
finally:
 if timer:timer.join()
 if second_timer:second_timer.join()
print('bounded')
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path), lock_kind],
                            capture_output=True, text=True, timeout=3, check=True)
    assert result.stdout.strip() == 'bounded'


@pytest.mark.parametrize('failure', ['missing', 'unresolved', 'changed', 'condition', 'late'])
def test_conditional_dispatch_degrades_without_current_worker(case, monkeypatch, failure):
    from xiaocao.live import current_review
    monkeypatch.setattr(current_review, 'deliver', lambda *a, **k: pytest.fail('No current worker'))
    _, _, facts = prepared_packet(case)
    facts.pop('request_sha256')
    facts.update(judgment_mode=CONDITIONAL_FIRST, max_wait_seconds=120,
                 review_wait_until='2026-10-23T09:27:30+08:00', entry_deadline='2026-10-23T09:30:00+08:00')
    prepared = prep.read_json(case['root']/'prepared.json')
    if failure == 'unresolved':
        # Reaccept a new independently reviewed fixture, never mutate a receipt.
        case['draft']['policy_template']['unresolved_semantic_conditions'] = ['Unproved breadth']
    if failure == 'condition':
        case['draft']['policy_template']['request_conditions'][0]['value'] = 'BLOCKED'
    if failure in {'unresolved', 'condition'}:
        from tests.test_kol_opening_preparation import accept
        case['review']['draft_sha256'] = prep.canonical_sha256(case['draft'])
        prepared = accept(case)
        save(case['root']/'prepared.json', prepared)
    packet = prep.opening_packet(case['root']/'prepared.json', case['path'], facts, now=NOW.replace(minute=26))
    if failure == 'changed':
        packet['delta']['changed'] = ['changed-source']
        packet['packet_sha256'] = prep.canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'})
    packet_path = save(case['root']/'packet.json', packet)
    if failure != 'missing':
        facts['kol_inputs'] = dict(packet_path=str(packet_path), packet_sha256=packet['packet_sha256'],
            warm_worker=prepared['worker_id'], current_warmup_path='must-not-deliver.json')
    facts['request_sha256'] = kol_policy.decision_sha256(facts)
    now = NOW.replace(minute=27, second=30) if failure == 'late' else NOW.replace(minute=26)
    path = write_warm_dispatch(facts, case['root']/'request.json', now=now)
    deferred = read_deferred_overlay(path, facts['request_sha256'])
    assert deferred['status'] == 'deferred' and deferred['semantic_review_completed'] is False
    assert deferred['model_dispatch'] == deferred['publication'] == 'not_performed'
    assert prep.read_json(path)['next_action'] == 'continue_original_baseline_deferred'
    assert not (case['root']/td.POLICY_PATH/'decisions').exists()


@pytest.mark.parametrize('route,finish,late_read,accepted', [
    (None, '09:27:05', False, False),
    (CONDITIONAL_FIRST, '09:27:05', False, True),
    (CONDITIONAL_FIRST, '09:27:29', False, True),
    (CONDITIONAL_FIRST, '09:27:30', False, False),
    (CONDITIONAL_FIRST, '09:27:29', True, False),
])
def test_actual_publisher_enforces_versioned_cap_through_source_read(tmp_path, route, finish, late_read, accepted):
    start = datetime.fromisoformat('2026-09-06T09:26:00+08:00')
    reader = Reader()
    register(tmp_path, reader)
    context = tc.build_trading_context(repo_root=tmp_path, client=reader, clock=lambda:start)
    request = dict(trade_date='2026-09-06', runtime='paper', book='B', requested_at=start.isoformat(),
        entry_deadline='2026-09-06T11:30:00+08:00', max_wait_seconds=120,
        review_wait_until='2026-09-06T09:28:00+08:00')
    if route: request['judgment_mode'] = route
    request['request_sha256'] = kol_policy.decision_sha256(request)
    iso = lambda t:t.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    decision = dict(schema_version=kol_policy.SCHEMA_VERSION, decision_id='conditional-fixture',
        agent_id='source-worker', book='B', runtime='paper', as_of=iso(start),
        valid_until='2026-09-06T03:30:00Z', source_refs=[td._source(r) for r in context['reports']],
        buy_scale=1, skip_codes=[], exit_codes=[], mode_mappings=[], rationale='Independent fixture conditional review.',
        invalidation_conditions=['New evidence'], morning_request_sha256=request['request_sha256'],
        current_checks=[dict(claim='Current facts', observed_at=iso(start), evidence_ref='fixture', verdict='supports')])
    review = review_for(decision, context)
    review['morning_request_sha256'] = request['request_sha256']
    review['mode_mapping_reviewed'] = True
    current = [datetime.fromisoformat('2026-09-06T'+finish+'+08:00')]
    call = reader.call_tool
    def read(*args):
        result = call(*args)
        if late_read: current[0] = start.replace(minute=27, second=30)
        return result
    reader.call_tool = read
    reader.calls.clear()
    run = lambda:td.publish_trading_decision(tmp_path, decision, review, context, client=reader,
        clock=lambda:current[0], morning_request=request)
    if accepted:
        first = run()
        assert first['status'] == 'published'
        current[0] = start.replace(hour=10)
        assert run() == first  # exact completed receipt readback, no renewed effect
        assert len(reader.calls) == 2
    else:
        with pytest.raises(td.TradingDecisionError, match='morning_publication_deadline'): run()
        assert not list((tmp_path/td.POLICY_PATH/'decisions').glob('*.json'))
