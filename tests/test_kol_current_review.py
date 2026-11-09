"""Direct frozen delivery and shared-delta reuse preserve original authority."""
import copy
from datetime import datetime
from pathlib import Path

import pytest
from tests.test_kol_rolling_preparation import source, case, current_input, NOW
from xiaocao.kol import opening_preparation as prep
from xiaocao.kol.preparation_adoption import adoption
from xiaocao.live import current_review as warm, kol_policy
from xiaocao.live.morning_dispatch import write_warm_dispatch
from xiaocao.kol.shared_judgment import packet as shared_packet


@pytest.fixture
def ready(source, monkeypatch):
    binding = dict(trade_date='2026-10-23', automation_id='xiaocao-daily-morning-execution',
                   owner_thread_id='paper-owner', run_id='run')
    monkeypatch.setenv('CODEX_AUTOMATION_ID', binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID', binding['owner_thread_id'])
    run = source['root']/'output/live/auto/runs/run'
    prep.write_artifact(run, {'fixture':True}, '.json')
    (run/'manifest.json').write_text(__import__('json').dumps(dict(market_date='2026-10-23',
        automation_id=binding['automation_id'], thread_id='paper-owner', run_id='run')))
    guide = source['root']/warm.GUIDE
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text('Current-only analyst guide')
    before = datetime.fromisoformat('2026-10-23T09:10:00+08:00')
    projection=copy.deepcopy(source['projection'])
    projection['as_of']=before.isoformat()
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    pp=prep.write_artifact(run,projection,'.early-projection.json')
    early=prep.input_payload(dict(projection_path=str(pp),projection_sha256=projection['projection_sha256']),
                             binding=binding,repo_root=source['root'])
    ep=prep.write_artifact(run,early,'.early-input.json')
    path = warm.prepare(run, binding, source['prepared_path'], now=before, root=source['root'],
                        current_input_path=ep)
    value = prep.read_json(path)
    dispatch = dict(accepted=True, warmup_sha256=value['warmup_sha256'],
        dispatched_at=before.isoformat(), tool_arguments=dict(model='gpt-6-sol',
        reasoning_effort='xhigh',fork_turns='none'),tool_result=dict(task_name='/root/current_paper'))
    loaded = dict(worker_id='/root/current_paper', warmup_sha256=value['warmup_sha256'],
                  preparation_sha256=value['preparation_sha256'],loaded_at=before.isoformat(),
                  early_packet_sha256=value['early_packet_sha256'])
    return source, binding, path, dispatch, loaded, before


def make_request(ready):
    source,binding,path,_,_,_=ready
    now=NOW.replace(minute=25,second=36)
    ip=current_input(source,binding,as_of=now)
    adopted=adoption(source['prepared_path'],ip,now=now)
    ap=prep.write_artifact(path.parent,adopted,'.adoption.json')
    request=dict(trade_date='2026-10-23',runtime='paper',binding=binding,
        requested_at=now.isoformat(),review_wait_until='2026-10-23T09:27:00+08:00',
        entry_deadline='2026-10-23T09:27:00+08:00',max_wait_seconds=84,
        freeze_sha256='a'*64,strategy_sha='b'*40,candidates=[dict(code='000001.XSHE',mode='A')])
    packet=prep.opening_packet(source['prepared_path'],ip,request,now=now,adoption_path=ap)
    pp=prep.write_artifact(path.parent,packet,'.packet.json')
    request['kol_inputs']=dict(packet_path=str(pp),packet_sha256=packet['packet_sha256'],
        warm_worker=None,current_warmup_path=str(path))
    request['request_sha256']=kol_policy.decision_sha256(request)
    return request,now


def test_frozen_request_reaches_existing_waiter_without_parent_spawn(ready):
    _,_,path,dispatch,loaded,before=ready
    warm.register(path,dispatch,loaded,now=before)
    request,now=make_request(ready)
    rp=prep.write_artifact(path.parent,request,'.request.json')
    dp=write_warm_dispatch(request,rp,now=now)
    handoff=prep.read_json(dp)
    assert handoff['next_action']=='await_preloaded_current_worker' and handoff['tool_arguments'] is None
    received=warm.wait(path,worker_id='/root/current_paper',now=lambda:now,
                       sleep=lambda _:pytest.fail('already delivered request must not poll'))
    assert received['request_sha256']==request['request_sha256']
    assert received['delivered_at']==now.isoformat()
    assert received['cutoff']=='2026-10-23T09:27:00+08:00'
    work=prep.read_json(Path(received['work_path']))
    assert work['request_path']==str(rp)
    assert work['since_preload']['added']==work['since_preload']['changed']==work['since_preload']['removed']==[]
    assert work['full_packet_path']==request['kol_inputs']['packet_path']
    assert handoff['actual_dispatch']=='not_observed'  # handoff never fabricates model activity


def test_cli_wait_reuses_previously_registered_loaded_receipt(ready, monkeypatch):
    import sys
    from datetime import timedelta
    from scripts import kol_current_review as cli
    _, _, path, dispatch, loaded, before = ready
    loaded_path = path.with_suffix('.loaded.json')
    warm._write(loaded_path, loaded)
    original = loaded_path.read_bytes()
    warm.register(path, dispatch, loaded, now=before)
    class Clock:
        @classmethod
        def now(cls, tz):
            return (before + timedelta(seconds=5)).astimezone(tz)
    monkeypatch.setattr(cli, 'datetime', Clock)
    entered = []
    def wait(actual, *, worker_id):
        entered.append((actual, worker_id))
        return {'status': 'waiting_reached'}
    monkeypatch.setattr(warm, 'wait', wait)
    monkeypatch.setattr(sys, 'argv', ['kol_current_review.py', 'wait', '--warmup', str(path),
                                     '--worker-id', loaded['worker_id']])
    assert cli.main() == 0
    assert entered == [(path, loaded['worker_id'])]
    assert loaded_path.read_bytes() == original


@pytest.mark.parametrize('damage', ['worker_id', 'warmup_sha256', 'preparation_sha256',
                                    'early_packet_sha256', 'loaded_at'])
def test_wait_rejects_foreign_or_late_loaded_receipt(ready, damage):
    _, _, path, _, loaded, before = ready
    loaded[damage] = '2026-10-23T09:20:00+08:00' if damage == 'loaded_at' else 'foreign'
    warm._write(path.with_suffix('.loaded.json'), loaded)
    with pytest.raises(ValueError, match='LOADED_BINDING'):
        warm.record_loaded(path, worker_id='/root/current_paper', now=before.replace(minute=21))


@pytest.mark.parametrize('damage',['late','foreign','wrong_source','no_actual_dispatch'])
def test_invalid_preloaded_registration_never_delivers(ready,monkeypatch,damage):
    _,_,path,dispatch,loaded,before=ready
    if damage=='late':before=before.replace(minute=20)
    elif damage=='foreign':monkeypatch.setenv('CODEX_THREAD_ID','foreign')
    elif damage=='wrong_source':loaded['preparation_sha256']='a'*64
    else:dispatch['accepted']=False
    with pytest.raises(ValueError):warm.register(path,dispatch,loaded,now=before)
    assert not path.with_suffix('.worker.json').exists()


def test_wait_never_returns_late_current_handoff(ready):
    _,_,path,dispatch,loaded,before=ready
    warm.register(path,dispatch,loaded,now=before)
    request,now=make_request(ready)
    write_warm_dispatch(request,prep.write_artifact(path.parent,request,'.request.json'),now=now)
    with pytest.raises(ValueError,match='ORIGINAL_CUTOFF'):
        warm.wait(path,worker_id='/root/current_paper',now=lambda:now.replace(minute=27))


def test_shared_packet_reuses_all_syntheses_and_exposes_changed_unit(ready):
    source,_,_,_,_,_=ready
    projection=copy.deepcopy(source['projection'])
    projection['as_of']=NOW.isoformat()
    projection['active_viewpoints'][0]['report_content_sha256']='d'*64
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    p=prep.write_artifact(source['root'],projection,'.projection.json')
    summary=dict(projection_path=str(p),projection_sha256=projection['projection_sha256'])
    result=shared_packet(source['prepared_path'],summary,now=NOW)
    changed=projection['active_viewpoints'][0]['record_id']
    assert result['delta']['changed']==[changed] and changed in result['delta']['units']
    assert result['invalidated_synthesis'] and result['invalidated_implications']
    assert result['coverage']['current_count']==len(projection['active_viewpoints'])
    assert result['policy_adoption']=='not_performed'


@pytest.mark.parametrize('damage', ['registration', 'guide', 'early_packet'])
def test_bad_preload_keeps_original_current_dispatch(ready, damage):
    _,_,path,dispatch,loaded,before=ready
    warm.register(path,dispatch,loaded,now=before)
    request,now=make_request(ready)
    value=prep.read_json(path)
    if damage=='registration':path.with_suffix('.worker.json').write_text('{}')
    elif damage=='guide':Path(value['guide_path']).write_text('changed guide')
    else:Path(value['early_packet_path']).unlink()
    dp=write_warm_dispatch(request,prep.write_artifact(path.parent,request,'.request.json'),now=now)
    result=prep.read_json(dp)
    assert result['next_action']=='dispatch_current_worker'
    assert result['tool_arguments']['model']=='gpt-6-sol'
    assert result['tool_arguments']['reasoning_effort']=='xhigh'
    assert result['current_warmup_unavailable']
    assert result['cutoff']==request['review_wait_until']
    assert not path.with_suffix('.handoff.json').exists()
