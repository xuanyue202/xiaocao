"""Actual preparation/review proof, bounded phases and original source floor."""
import copy
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.test_kol_opening_preparation import case, save
from tests.test_kol_rolling_preparation import source
from xiaocao.kol import preopen_program as pp, opening_preparation as prep
from xiaocao.runner_recovery import _hash

DAY='2026-10-23'
EARLY=datetime.fromisoformat(DAY+'T06:30:00+08:00')


def plan(root,monkeypatch,calendar=None):
    monkeypatch.setenv('CODEX_AUTOMATION_ID',pp.OWNER)
    monkeypatch.setenv('CODEX_THREAD_ID','source-owner')
    return pp.create_plan(root,acquired_at=EARLY,slot=EARLY.replace(minute=0),
                          calendar=calendar or {'latest':DAY},runner_pid=os.getpid(),thread_id='source-owner')


def staged(source,monkeypatch):
    root=source['root']
    path,value=plan(root,monkeypatch)
    from xiaocao.kol.rolling_preparation import input_payload
    source['path']=save(root/'current-program-input.json',input_payload(source['inputs']['projection'],
        binding={**source['inputs']['binding'],'trade_date':DAY},repo_root=root,intended_use_at=DAY+'T09:27:30+08:00'))
    observed=EARLY+timedelta(minutes=1)
    current=[observed]
    program=pp.Program(root,path,now=lambda:current[0],emit=lambda row:None,
        input_builder=lambda:{'status':'written','path':str(source['path'])})
    program.refresh()
    stage_path=Path(program.current['stage_path'])
    stage=pp.read(stage_path)
    inputs=prep.read_json(Path(stage['input_path']))
    dispatch=copy.deepcopy(source['dispatch'])
    dispatch.update(binding=inputs['binding'],input_sha256=_hash(inputs),dispatched_at=observed.isoformat())
    dispatch_path=save(root/'actual-dispatch.json',dispatch)
    return program,current,stage_path,stage,inputs,dispatch,dispatch_path


def test_preparation_has_real_45_minute_budget_and_original_0920_cap(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    assert prep.aware(stage['complete_by'])-current[0]==timedelta(minutes=45)
    assert prep.aware(stage['review_open_by'])-current[0]==timedelta(minutes=30)
    assert prep.aware(stage['dispatch_by'])==EARLY+timedelta(minutes=5)
    assert prep.aware(program.plan['complete_by'])==EARLY.replace(hour=9,minute=20)
    current[0]+=timedelta(minutes=6)
    assert program.status()['status']=='missed_dispatch_deadline'
    with pytest.raises(ValueError,match='EARLY_DISPATCH'):
        pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])


def test_worker_dispatch_and_review_context_are_required_before_acceptance(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    draft=copy.deepcopy(source['draft']);draft.update(input_sha256=_hash(inputs),prepared_at=(current[0]+timedelta(minutes=10)).isoformat())
    context=copy.deepcopy(source['context']);context['as_of']=current[0].isoformat()
    context['context_sha256']=prep.canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
    review=copy.deepcopy(source['review']);review.update(reviewer_id='source-owner',reviewed_at=(current[0]+timedelta(minutes=15)).isoformat())
    with pytest.raises(FileNotFoundError):
        pp.validate_acceptance(inputs,draft,review,dispatch,context,now=current[0]+timedelta(minutes=16))
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0]+timedelta(seconds=10))
    context_path=save(source['root']/'review-context.json',context)
    pp.record_review(Path(stage['input_path']),context_path,now=current[0]+timedelta(minutes=2))
    proof=pp.validate_acceptance(inputs,draft,review,dispatch,context,now=current[0]+timedelta(minutes=16))
    assert proof['authority']==0 and proof['completed_at'].endswith('+08:00')
    with pytest.raises(ValueError,match='DEADLINE'):
        pp.validate_acceptance(inputs,draft,review,dispatch,context,now=prep.aware(stage['complete_by']))


def test_repeated_unchanged_input_never_renews_phase_budget(source,monkeypatch):
    program,current,stage_path,stage,*_=staged(source,monkeypatch)
    current[0]+=timedelta(minutes=20)
    program.refresh()
    assert pp.read(Path(program.current['stage_path']))==stage
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==1


def test_source_floor_is_0730_even_when_preparation_wakes_at0630(tmp_path,monkeypatch):
    path,value=plan(tmp_path,monkeypatch)
    monkeypatch.setenv('XIAOCAO_KOL_PREOPEN_PLAN',str(path))
    pp.seal(path.with_name('source-release.json'),{'plan_sha256':value['sha256'],
        'released_at':EARLY.replace(hour=7,minute=30).isoformat()})
    slot=EARLY.replace(minute=0)
    assert not pp.source_release_admitted(slot,EARLY,EARLY.replace(hour=7,minute=29))
    assert pp.source_release_admitted(slot,EARLY,EARLY.replace(hour=7,minute=30))
    monkeypatch.setenv('CODEX_THREAD_ID','foreign')
    with pytest.raises(ValueError,match='OWNER'):
        pp.source_release_admitted(slot,EARLY,EARLY.replace(hour=8))


def test_unproved_or_nontrading_calendar_only_grants_source_scope(tmp_path,monkeypatch):
    path,value=plan(tmp_path,monkeypatch,{'latest':'2026-10-22'})
    assert value['target_trade_date'] is None and value['fresh_through'] is None
    assert value['scope']=='source_only_or_evening'
    assert prep.aware(value['complete_by'])==EARLY.replace(hour=9,minute=20)


def test_source_recovery_gets_its_own_budget_after_proved_initial_gap(source,monkeypatch):
    root=source['root'];path,value=plan(root,monkeypatch)
    current=[EARLY]
    from xiaocao.kol.rolling_preparation import input_payload
    source['path']=save(root/'recovered-program-input.json',input_payload(source['inputs']['projection'],
        binding={**source['inputs']['binding'],'trade_date':DAY},repo_root=root,intended_use_at=DAY+'T09:27:30+08:00'))
    results=[{'status':'blocked','reason':'KOL_PREPARATION_SOURCE_EXPIRES_BEFORE_USE'},
             {'status':'written','path':str(source['path'])}]
    program=pp.Program(root,path,now=lambda:current[0],emit=lambda row:None,input_builder=lambda:results.pop(0))
    assert program.refresh()['status']=='source_blocked'
    current[0]=EARLY.replace(hour=8,minute=4)
    program.refresh();stage=pp.read(Path(program.current['stage_path']))
    assert prep.aware(stage['dispatch_by'])==current[0]+timedelta(minutes=5)
    assert prep.aware(stage['complete_by'])==current[0]+timedelta(minutes=45)


def test_unknown_active_worker_is_retained_after_its_budget_not_replaced(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])
    changed=prep.read_json(source['path']);projection=prep.read_projection(changed['projection'])
    projection['active_viewpoints'][0]['content_sha256']='9'*64
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    changed['projection']={'projection_path':str(save(source['root']/'new-projection.json',projection)),
                           'projection_sha256':projection['projection_sha256']}
    other=save(source['root']/'new-input.json',changed)
    program.input_builder=lambda:{'status':'written','path':str(other)}
    current[0]=prep.aware(stage['complete_by'])+timedelta(minutes=1)
    program.refresh()
    assert program.current['stage_path']==str(stage_path)
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==1


def test_full_preparation_acceptance_carries_budget_and_independent_review_proof(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    now=current[0]+timedelta(minutes=20)
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])
    context=copy.deepcopy(source['context']);context['as_of']=current[0].isoformat()
    context['context_sha256']=prep.canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
    context_path=save(source['root']/'current-context.json',context)
    pp.record_review(Path(stage['input_path']),context_path,now=current[0]+timedelta(minutes=5))
    draft=copy.deepcopy(source['draft']);draft.update(input_sha256=_hash(inputs),prepared_at=(current[0]+timedelta(minutes=10)).isoformat())
    review=copy.deepcopy(source['review']);review.update(reviewer_id='source-owner',reviewed_at=now.isoformat(),
        context_sha256=context['context_sha256'],draft_sha256=prep.canonical_sha256(draft),dispatch_sha256=prep.canonical_sha256(dispatch))
    accepted=prep.accept_preparation(Path(stage['input_path']),draft,review,dispatch,context,now=now)
    path=save(source['root']/'early-reviewed.json',accepted)
    pp.complete(path)
    current[0]=now
    assert program.status()['status']=='accepted'
    assert accepted['preopen_program']['completed_at']==now.isoformat()
    assert prep.read_preparation(path,now=now)==accepted


@pytest.mark.parametrize('failure',[TimeoutError('cache read stalled'),ValueError('bad JSON')])
def test_bootstrap_fault_retains_original_source_release(tmp_path,monkeypatch,failure):
    import subprocess
    path,value=plan(tmp_path,monkeypatch)
    current=[EARLY]
    def failed():
        if isinstance(failure,TimeoutError):raise subprocess.TimeoutExpired('cache-only-input',45)
        raise failure
    def advance(seconds):current[0]+=timedelta(seconds=seconds)
    program=pp.Program(tmp_path,path,now=lambda:current[0],sleep=advance,emit=lambda row:None,input_builder=failed)
    program.before_source()
    assert pp.read(path.with_name('source-release.json'))['released_at']==EARLY.replace(hour=7,minute=30).isoformat()
    assert program.status()['status']=='source_verification_failed'
    assert program.plan['runner_pid']==os.getpid()


def test_terminal_proof_releases_changed_input_but_never_renews_same_input(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])
    current[0]+=timedelta(minutes=20)
    receipt={'tool_name':'collaboration.list_agents','tool_arguments':{},'observed_at':current[0].isoformat(),
        'tool_result':{'agents':[{'agent_name':dispatch['worker_id'],'agent_status':{'completed':'draft did not pass source review'}}]}}
    path=save(source['root']/'actual-terminal.json',receipt)
    pp.record_worker_terminal(Path(stage['input_path']),path,now=current[0])
    program.refresh()
    assert pp.read(Path(program.current['stage_path']))==stage
    changed=prep.read_json(source['path']);projection=prep.read_projection(changed['projection'])
    projection['active_viewpoints'][0]['content_sha256']='9'*64
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    changed['projection']={'projection_path':str(save(source['root']/'terminal-new-projection.json',projection)),
        'projection_sha256':projection['projection_sha256']}
    other=save(source['root']/'terminal-new-input.json',changed)
    program.input_builder=lambda:{'status':'written','path':str(other)}
    program.refresh()
    assert program.current['stage_path']!=str(stage_path)
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==2


def test_parallel_refresh_cannot_duplicate_model_stage(source,monkeypatch):
    import threading
    program,current,stage_path,stage,*_=staged(source,monkeypatch)
    barrier=threading.Barrier(3)
    errors=[]
    def refresh():
        try:barrier.wait();program.refresh()
        except Exception as exc:errors.append(exc)
    threads=[threading.Thread(target=refresh) for _ in range(2)]
    for thread in threads:thread.start()
    barrier.wait()
    for thread in threads:thread.join(timeout=2)
    assert not errors and all(not thread.is_alive() for thread in threads)
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==1
    assert pp.read(stage_path)==stage


def test_calendar_recovery_does_not_extend_original_morning_deadline(source,monkeypatch):
    root=source['root']
    path,value=plan(root,monkeypatch,{'status':'unproved','queried_date':DAY})
    current=[EARLY]
    calls=[]
    from xiaocao.kol.rolling_preparation import input_payload
    input_path=save(root/'calendar-recovered.json',input_payload(source['inputs']['projection'],
        binding={**source['inputs']['binding'],'trade_date':DAY},repo_root=root,intended_use_at=DAY+'T09:27:30+08:00'))
    def calendar():calls.append(1);return {'latest':DAY,'queried_date':DAY,'observed_at':current[0].isoformat()}
    program=pp.Program(root,path,now=lambda:current[0],emit=lambda row:None,calendar_probe=calendar,
        input_builder=lambda:{'status':'written','path':str(input_path)})
    assert program.refresh()['status']=='source_blocked' and not calls
    current[0]+=timedelta(minutes=5)
    program.refresh()
    assert calls==[1] and program.target_trade_date==DAY
    assert pp.read(path)['complete_by']==value['complete_by']
    assert prep.aware(value['complete_by'])==EARLY.replace(hour=9,minute=20)


def test_monitor_refreshes_once_per_checkpoint_and_keeps_one_stage(source,monkeypatch):
    program,current,stage_path,stage,*_=staged(source,monkeypatch)
    calls=[]
    original=program.input_builder
    program.input_builder=lambda:(calls.append(1),original())[1]
    class Stop:
        n=0
        def wait(self,seconds):
            self.n+=1
            current[0]=EARLY.replace(hour=8,minute=30,second=self.n)
            return self.n>2
        def set(self):pass
    program.stop=Stop()
    thread=program.monitor();thread.join(timeout=3)
    assert not thread.is_alive() and len(calls)==1
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==1


def test_coordinator_preopen_admission_requires_release_and_legacy_six_stays_closed(tmp_path,monkeypatch):
    from xiaocao.kol.daily import DailyCoordinator
    path,value=plan(tmp_path,monkeypatch)
    slot=EARLY.replace(minute=0)
    now=[EARLY.replace(hour=7,minute=30)]
    service=DailyCoordinator(tmp_path/'coordinator',now=lambda:now[0])
    monkeypatch.setattr(service,'_run',lambda *a,**kw:{'admitted':kw['admitted'],'slot':kw['slot_start']})
    monkeypatch.delenv('XIAOCAO_KOL_PREOPEN_PLAN',raising=False)
    assert service.run([],automation_slot_start=slot,automation_acquired_at=EARLY)['admitted'] is False
    monkeypatch.setenv('XIAOCAO_KOL_PREOPEN_PLAN',str(path))
    pp.seal(path.with_name('source-release.json'),{'plan_sha256':value['sha256'],'released_at':now[0].isoformat()})
    assert service.run([],automation_slot_start=slot,automation_acquired_at=EARLY)['admitted'] is True
    now[0]-=timedelta(seconds=1)
    assert service.run([],automation_slot_start=slot,automation_acquired_at=EARLY)['admitted'] is False


@pytest.mark.parametrize('terminal',['corrupt','wrong-stage'])
def test_invalid_terminal_never_releases_unknown_worker(source,monkeypatch,terminal):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])
    if terminal=='corrupt':stage_path.with_name('worker-terminal.json').write_text('{}')
    else:pp.seal(stage_path.with_name('worker-terminal.json'),{'stage_sha256':'wrong','worker_id':'other',
        'receipt_path':str(source['root']/'missing-status.json'),'receipt_sha256':'0'*64})
    changed=prep.read_json(source['path']);projection=prep.read_projection(changed['projection'])
    projection['active_viewpoints'][0]['content_sha256']='b'*64
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    changed['projection']={'projection_path':str(save(source['root']/'invalid-terminal-projection.json',projection)),
        'projection_sha256':projection['projection_sha256']}
    other=save(source['root']/'invalid-terminal-input.json',changed)
    program.input_builder=lambda:{'status':'written','path':str(other)}
    result=program.refresh()
    assert result['status']=='source_verification_failed'
    assert program.current['stage_path']==str(stage_path)
    assert len(list((program.path.parent/'stages').glob('*/stage.json')))==1


def test_running_tool_status_cannot_release_worker(source,monkeypatch):
    program,current,stage_path,stage,inputs,dispatch,dispatch_path=staged(source,monkeypatch)
    pp.record_dispatch(Path(stage['input_path']),dispatch_path,now=current[0])
    receipt=save(source['root']/'still-running.json',{'tool_name':'collaboration.list_agents','tool_arguments':{},
        'observed_at':current[0].isoformat(),'tool_result':{'agents':[{'agent_name':dispatch['worker_id'],'agent_status':'running'}]}})
    with pytest.raises(ValueError,match='TERMINAL_UNPROVEN'):
        pp.record_worker_terminal(Path(stage['input_path']),receipt,now=current[0])
    assert not stage_path.with_name('worker-terminal.json').exists()
