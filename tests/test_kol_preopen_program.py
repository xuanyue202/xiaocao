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
    assert prep.aware(value['complete_by'])==EARLY+timedelta(minutes=60)


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
