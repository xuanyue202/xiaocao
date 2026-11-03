"""Pure historical-source adoption tests; no APP, network or financial writer."""
import copy
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.test_kol_opening_preparation import case, save, NOW
from tests.test_kol_selection import row, preference
from xiaocao.kol import opening_preparation as prep, rolling_preparation as rolling
from xiaocao.kol.preparation_adoption import adoption
from xiaocao.kol.selection_preview import registered_preparation, preview
from xiaocao.runner_recovery import _hash

EARLY = datetime.fromisoformat('2026-10-22T21:10:00+08:00')


@pytest.fixture
def source(case, monkeypatch):
    root = case['root']
    for relative in (*rolling.CATALOG, *rolling.INSTRUCTIONS):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('unchanged canonical definitions')
    projection = prep.read_projection(case['inputs']['projection'])
    projection['as_of'] = (EARLY-timedelta(minutes=1)).isoformat()
    for item in projection['active_viewpoints']:
        item.update(kol_id='kol-xiaocao', source_published_at='2026-10-22T09:00:00Z')
    projection['latest_evaluations'] = [{'record_id': 'eval-'+item['record_id'], 'evaluation': {
        'viewpoint_id': item['record_id'], 'evaluated_at': '2026-10-22T12:00:00Z',
        'trading_applicability': {'valid_until': '2026-10-23T02:45:00Z'}}}
        for item in projection['active_viewpoints']]
    projection['projection_sha256'] = prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    summary = {'projection_path': str(save(root/'rolling-projection.json', projection)),
               'projection_sha256': projection['projection_sha256']}
    binding = {'automation_id': rolling.OWNER, 'owner_thread_id': 'source-owner',
               'trade_date': '2026-10-22', 'scope': 'source_reasoning_only'}
    inputs = rolling.input_payload(summary, binding=binding, repo_root=root)
    path = save(root/'rolling-input.json', inputs)
    draft = copy.deepcopy(case['draft'])
    draft.update(schema_version=rolling.SCHEMA, input_sha256=_hash(inputs), prepared_at=EARLY.isoformat(),
        valid_until='2026-10-23T11:30:00+08:00', source_coverage_limits=['Registry only; opening conditions unknown.'],
        synthesis=[dict(id='cross-day', viewpoint_ids=inputs['viewpoint_ids'], judgment='Conditional rotation.',
            evolution='Earlier warning remains conditional.', conditions='Verify opening structure.',
            invalidations='No support at opening.', counterevidence='No current market facts yet.')],
        selection_preferences=[preference('mode', {'mode': 'B'}, source_report_id='r', source_quote='source')])
    context = copy.deepcopy(case['context'])
    context['as_of'] = projection['as_of']
    context['context_sha256'] = prep.canonical_sha256({k:v for k,v in context.items() if k!='context_sha256'})
    dispatch = {**case['dispatch'], 'binding': binding, 'input_sha256': _hash(inputs),
                'dispatched_at': (EARLY-timedelta(minutes=1)).isoformat()}
    review = {**case['review'], 'draft_sha256': prep.canonical_sha256(draft),
        'context_sha256': context['context_sha256'], 'dispatch_sha256': prep.canonical_sha256(dispatch),
        'reviewed_at': EARLY.isoformat(), 'rolling_synthesis_reviewed': True, 'selection_preferences_reviewed': True}
    value = prep.accept_preparation(path, draft, review, dispatch, context, now=EARLY)
    prepared_path = save(root/'rolling-prepared.json', value)
    monkeypatch.setenv('CODEX_AUTOMATION_ID', rolling.OWNER)
    monkeypatch.setenv('CODEX_THREAD_ID', 'source-owner')
    rolling.register(path, prepared_path, value)
    return dict(root=root, inputs=inputs, path=path, draft=draft, context=context, dispatch=dispatch,
                review=review, value=value, prepared_path=prepared_path, projection=projection)


def current_input(source, binding, *, as_of=NOW):
    projection = copy.deepcopy(source['projection'])
    projection['as_of'] = as_of.isoformat()
    projection['projection_sha256'] = prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    summary = {'projection_path': str(save(source['root']/'current-projection.json', projection)),
               'projection_sha256': projection['projection_sha256']}
    payload = prep.input_payload(summary, binding=binding, repo_root=source['root'])
    parent = (source['root']/'output/live/auto/runs'/binding['run_id']
              if binding['automation_id']=='xiaocao-daily-morning-execution' else source['root'])
    return save(parent/'current-input.json', payload)


def test_previous_evening_source_shared_by_producer_without_app_owner(source):
    path, value = registered_preparation(source['root'], '2026-10-23', now=NOW)
    assert value['binding']['automation_id'] == rolling.OWNER
    assert path == source['prepared_path']
    rows = [{**row('000001.XSHE', 'A', 1), 'date': '2026-10-23'},
            {**row('000002.XSHE', 'B', 4), 'date': '2026-10-23'}]
    original = copy.deepcopy(rows)
    result = preview(rows, {'market_date': '2026-10-23', 'snapshot_sha256': 'a'*64}, root=source['root'],
                     now=NOW, fingerprint_reader=lambda *a: value['source_fingerprint'])
    assert result['selected_codes'][0] == '000002.XSHE'
    assert rows == original and result['policy_adoption']=='not_performed'


@pytest.mark.parametrize('runtime', ['paper', 'live'])
def test_each_current_consumer_adopts_same_prior_evening_brief_and_gets_own_worker(source, monkeypatch, runtime):
    from xiaocao.live.morning_dispatch import write_warm_dispatch
    from xiaocao.live.kol_policy import decision_sha256
    automation = 'xiaocao-daily-morning-execution' if runtime=='paper' else 'xiaocao-book-b-live-morning'
    binding = dict(automation_id=automation, owner_thread_id=runtime+'-owner', trade_date='2026-10-23')
    monkeypatch.setenv('CODEX_AUTOMATION_ID', automation)
    monkeypatch.setenv('CODEX_THREAD_ID', binding['owner_thread_id'])
    if runtime=='paper':
        binding['run_id'] = 'original-paper'
        save(source['root']/'output/live/auto/runs/original-paper/manifest.json', dict(
            market_date='2026-10-23', automation_id=automation, thread_id=binding['owner_thread_id'],
            run_id=binding['run_id']))
    else:
        binding['runner_pid'] = os.getpid()
    current = current_input(source, binding)
    adopted = adoption(source['prepared_path'], current, now=NOW)
    adopted_path = save(current.parent/'adopted.json', adopted)
    assert adopted['source_binding'] == source['value']['binding']
    assert adopted['binding'] == binding and adopted['policy_adoption']=='not_performed'
    facts = dict(trade_date='2026-10-23', runtime=runtime, binding=binding,
        requested_at=NOW.replace(minute=25).isoformat(), review_wait_until=NOW.replace(minute=27).isoformat(),
        entry_deadline=NOW.replace(minute=27).isoformat(), max_wait_seconds=120,
        freeze_sha256='a'*64, strategy_sha='b'*40, candidates=[{'code':'000001.XSHE', 'mode':'A'}])
    packet = prep.opening_packet(source['prepared_path'], current, facts, now=NOW.replace(minute=26),
                                 adoption_path=adopted_path)
    assert packet['synthesis'] == source['draft']['synthesis'] and not packet['delta']['changed']
    packet_path = prep.write_artifact(current.parent, packet, '.packet.json')
    facts['kol_inputs'] = dict(packet_path=str(packet_path), packet_sha256=packet['packet_sha256'], warm_worker=None)
    facts['request_sha256'] = decision_sha256(facts)
    path = write_warm_dispatch(facts, save(current.parent/'request.json', facts), now=NOW.replace(minute=26))
    handoff = prep.read_json(path)
    assert handoff['next_action']=='dispatch_current_worker'
    assert handoff['tool_arguments']['model']=='gpt-6-sol' and 'target' not in handoff['tool_arguments']
    assert prep.read_json(source['prepared_path']) == source['value']


@pytest.mark.parametrize('damage', ['coverage', 'self_review', 'review_flag', 'future_source', 'catalog', 'instructions', 'expiry'])
def test_rolling_acceptance_preserves_source_review_and_time_boundaries(source, damage):
    draft, review = copy.deepcopy(source['draft']), copy.deepcopy(source['review'])
    if damage=='coverage': draft['synthesis'][0]['viewpoint_ids'].pop()
    elif damage=='self_review': review['reviewer_id']=draft['worker_id']
    elif damage=='review_flag': review['rolling_synthesis_reviewed']=False
    elif damage=='expiry': draft['valid_until']=(EARLY+timedelta(hours=25)).isoformat()
    elif damage=='catalog': (source['root']/rolling.CATALOG[0]).write_text('changed definitions')
    elif damage=='instructions': (source['root']/rolling.INSTRUCTIONS[0]).write_text('changed preparation rules')
    else:
        projection=source['projection']
        projection['active_viewpoints'][0]['source_published_at']='2026-10-23T01:00:00Z'
        projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
        save(Path(source['inputs']['projection']['projection_path']),projection)
    review['draft_sha256']=prep.canonical_sha256(draft)
    with pytest.raises(ValueError):
        prep.accept_preparation(source['path'], draft, review, source['dispatch'], source['context'], now=EARLY)


def test_same_hash_does_not_renew_viewpoint_expiry(source):
    with pytest.raises(ValueError, match='SOURCE_EXPIRED'):
        rolling.validate_current_sources(source['value'], now=NOW.replace(hour=11))


def test_late_source_seal_cannot_enter_original_opening_as_prepared(source, monkeypatch):
    late=NOW.replace(minute=21)
    review={**source['review'],'reviewed_at':late.isoformat()}
    value=prep.accept_preparation(source['path'],source['draft'],review,source['dispatch'],source['context'],now=late)
    path=save(source['root']/'late-prepared.json',value)
    rolling.register(source['path'],path,value)
    with pytest.raises(ValueError,match='LATE_FOR_OPENING'):
        registered_preparation(source['root'],'2026-10-23',now=NOW.replace(minute=25))
    binding=dict(automation_id='xiaocao-book-b-live-morning',owner_thread_id='app-owner',
                 trade_date='2026-10-23',runner_pid=os.getpid())
    monkeypatch.setenv('CODEX_AUTOMATION_ID',binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID',binding['owner_thread_id'])
    current=current_input(source,binding,as_of=NOW.replace(minute=25))
    with pytest.raises(ValueError,match='LATE_FOR_OPENING'):
        adoption(path,current,now=NOW.replace(minute=25))


def test_uncertain_brief_keeps_current_judgment_pending_without_expensive_fingerprint(source, monkeypatch):
    source['draft']['selection_preferences'][0]['applicability']='uncertain'
    source['draft']['policy_template'] = dict(buy_scale=1, skip_codes=[], exit_codes=[],
        rationale='Wait for actual opening acceptance.', invalidation_conditions=['Opening conditions change.'],
        xiaocao_mode_overrides=[], mode_mappings=[], source_report_ids=['r'], request_conditions=[],
        unresolved_semantic_conditions=['Opening acceptance unknown.'], defer_if_no_effect=False)
    source['review'].update(policy_template_reviewed=True, restrictive_branch_reviewed=True,
                           draft_sha256=prep.canonical_sha256(source['draft']))
    value=prep.accept_preparation(source['path'], source['draft'], source['review'], source['dispatch'],
                                  source['context'], now=EARLY)
    save(source['prepared_path'],value)
    directory=source['root']/rolling.DIRECTORY
    for path in directory.glob('*.json'): path.unlink()
    rolling.register(source['path'],source['prepared_path'],value)
    def forbidden(*args): raise AssertionError('No supported preference needs this full fingerprint.')
    result=preview([],{'market_date':'2026-10-23','snapshot_sha256':'a'*64},root=source['root'],now=NOW,
                   fingerprint_reader=forbidden)
    assert result['current_applicability']=='not_completed'
    assert result['reason']=='CURRENT_APPLICABILITY_REVIEW_REQUIRED'
    assert result['unresolved_semantic_conditions']==['Opening acceptance unknown.']
    assert result['current_source_head']=='not_checked'
    assert result['source_synthesis']==source['draft']['synthesis']


def test_changed_source_is_bound_as_delta_and_never_materialized_as_unchanged(source, monkeypatch):
    from xiaocao.kol.prepared_policy import materialize
    from xiaocao.live.kol_policy import decision_sha256
    binding=dict(automation_id='xiaocao-book-b-live-morning', owner_thread_id='current-owner',
                 trade_date='2026-10-23', runner_pid=os.getpid())
    monkeypatch.setenv('CODEX_AUTOMATION_ID',binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID',binding['owner_thread_id'])
    current=current_input(source,binding)
    payload=prep.read_json(current)
    projection=prep.read_projection(payload['projection'])
    projection['active_viewpoints'][0]['content_sha256']='f'*64
    projection['source_fingerprint']='e'*64
    projection['projection_sha256']=prep.canonical_sha256({k:v for k,v in projection.items() if k!='projection_sha256'})
    save(Path(payload['projection']['projection_path']),projection)
    payload.update(source_fingerprint='e'*64)
    payload['projection']['projection_sha256']=projection['projection_sha256']
    save(current,payload)
    adopted=adoption(source['prepared_path'],current,now=NOW)
    adopted_path=save(source['root']/'delta-adoption.json',adopted)
    facts=dict(binding=binding, runtime='live',trade_date='2026-10-23',requested_at=NOW.replace(minute=25).isoformat(),
        review_wait_until=NOW.replace(minute=27).isoformat(),freeze_sha256='a'*64,strategy_sha='b'*40,
        candidates=[{'code':'000001.XSHE','mode':'A'}])
    packet=prep.opening_packet(source['prepared_path'],current,facts,now=NOW.replace(minute=26),
                               adoption_path=adopted_path)
    assert packet['delta']['changed']==['0']
    assert not packet['synthesis'] and packet['invalidated_synthesis']
    facts['request_sha256']=decision_sha256(facts)
    with pytest.raises(ValueError):materialize(source['value'],packet,facts,now=NOW.replace(minute=26))


def test_source_reviewed_auction_wait_changes_exposure_without_changing_candidate_pool(source):
    source['draft']['policy_template'] = dict(buy_scale=0, skip_codes=[], exit_codes=[],
        rationale='Source explicitly waits for post-open confirmation for this date.',
        invalidation_conditions=['After auction, reassess original source and fresh facts.'],
        xiaocao_mode_overrides=[], mode_mappings=[], source_report_ids=['r'],
        request_conditions=[dict(field='trade_date', op='eq', value='2026-10-23', evidence_ref='dated source'),
                            dict(field='session_phase', op='eq', value='opening_auction', evidence_ref='actual clock')],
        unresolved_semantic_conditions=[])
    source['review'].update(policy_template_reviewed=True, restrictive_branch_reviewed=True,
                           draft_sha256=prep.canonical_sha256(source['draft']))
    value=prep.accept_preparation(source['path'],source['draft'],source['review'],source['dispatch'],
                                  source['context'],now=EARLY)
    save(source['prepared_path'],value)
    for path in (source['root']/rolling.DIRECTORY).glob('*.json'):path.unlink()
    rolling.register(source['path'],source['prepared_path'],value)
    rows=[{**row('000001.XSHE','A',1),'date':'2026-10-23'}]
    original=copy.deepcopy(rows)
    result=preview(rows,{'market_date':'2026-10-23','snapshot_sha256':'a'*64},root=source['root'],
        now=NOW.replace(minute=26),fingerprint_reader=lambda *a:value['source_fingerprint'])
    assert result['candidate_codes']==['000001.XSHE'] and result['selected_codes']==[]
    assert result['risk_adjustment']['buy_scale']==0
    assert sum(result['portfolio_diff']['after']['mode_target_weights'].values())==0
    assert rows==original and result['policy_adoption']=='not_performed'
    later=preview(rows,{'market_date':'2026-10-23','snapshot_sha256':'a'*64},root=source['root'],
        now=NOW.replace(minute=30),fingerprint_reader=lambda *a:value['source_fingerprint'])
    assert 'risk_adjustment' not in later


@pytest.mark.app_simulation
def test_original_app_inputs_adopt_shared_reasoning_without_a_source_worker(source, monkeypatch):
    from xiaocao.live import morning_kol_inputs as morning
    from xiaocao.live.morning_checklist import MorningChecklist
    binding=dict(automation_id='xiaocao-book-b-live-morning', owner_thread_id='app-owner',
                 trade_date='2026-10-23', runner_pid=os.getpid())
    monkeypatch.setenv('CODEX_AUTOMATION_ID',binding['automation_id'])
    monkeypatch.setenv('CODEX_THREAD_ID',binding['owner_thread_id'])
    current=current_input(source,binding)
    summary=prep.read_json(current)['projection']
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(morning,'datetime',Clock)
    monkeypatch.setattr('xiaocao.live.morning_checklist.datetime',Clock)
    monkeypatch.setattr(morning,'build_trading_context',lambda **kwargs:{})
    monkeypatch.setattr(morning,'write_trading_projection',lambda *args,**kwargs:summary)
    checklist=MorningChecklist.create(source['root']/'checklists',binding)
    result=morning.prepare_inputs(checklist,repo_root=source['root'])
    assert result['preparation_status']=='shared_rolling_adopted'
    assert result['worker_id'] is None and result['source_worker_id']==source['value']['worker_id']
    loaded=checklist.read()['items']['kol_inputs_loaded']
    assert loaded['status']=='passed'
    adopted=prep.read_json(Path(loaded['evidence']['preparation_adoption_path']))
    assert adopted['binding']==binding and adopted['source_binding']==source['value']['binding']
