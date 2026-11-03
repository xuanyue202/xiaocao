"""Conditional semantic reuse yields only a draft; never approval or business effects."""
import copy
from datetime import timedelta
import pytest

from tests.test_kol_opening_preparation import case, accept, save, request, NOW
from xiaocao.kol import opening_preparation as prep
from xiaocao.kol.prepared_policy import materialize
from xiaocao.live import kol_policy


def prepared_packet(case, *, defer=False, template_updates=None):
    case['context']['reports'][0].update(kol_id='kol-fixture',source_published_at='2026-10-22T00:00:00Z',
                                       received_at='2026-10-22T00:01:00Z')
    case['context']['context_sha256']=prep.canonical_sha256({k:v for k,v in case['context'].items() if k!='context_sha256'})
    case['review']['context_sha256']=case['context']['context_sha256']
    template=dict(buy_scale=1,skip_codes=[],exit_codes=[],rationale='Source supports no special selection now.',
        invalidation_conditions=['Reassess new source/conditions.'],xiaocao_mode_overrides=[],mode_mappings=[],
        source_report_ids=['r'],request_conditions=[{'field':'account_risk_status','op':'eq',
        'value':'NORMAL','evidence_ref':'reviewed risk requirement'}],unresolved_semantic_conditions=[])
    if defer:
        template.update(defer_if_no_effect=True,unresolved_semantic_conditions=['No proved support/mapping for extra KOL effect.'])
        case['review']['deferred_overlay_reviewed']=True
    template.update(template_updates or {})
    case['draft']['policy_template']=template
    case['review'].update(policy_template_reviewed=True,draft_sha256=prep.canonical_sha256(case['draft']))
    prepared=accept(case)
    prepared_path=save(case['root']/'prepared.json',prepared)
    facts=request()
    facts.update(book='B',runtime='live',max_wait_seconds=90,entry_deadline=facts['review_wait_until'],
        freeze=dict(market_date='2026-10-23',strategy_run_id='original',strategy_sha='c'*40,
                    snapshot_sha256='b'*64,snapshot_raw_sha256='d'*64,snapshot_row_count=1,checkpoint_sha256='e'*64),
        account_risk={'status':'NORMAL','deploy_factor':1})
    packet=prep.opening_packet(prepared_path,case['path'],facts,now=NOW.replace(minute=26))
    facts['request_sha256']=kol_policy.decision_sha256(facts)
    return prepared,packet,facts


def test_unchanged_conditionally_prepared_policy_materializes_without_model_or_approval(case):
    prepared,packet,facts=prepared_packet(case)
    value=materialize(prepared,packet,facts,now=NOW.replace(minute=26))
    assert value['authority']==0 and value['status']=='independent_review_required'
    assert value['review']==value['publication']==value['source_verification']=='not_performed'
    decision=value['decision']
    assert decision['selection_preferences']==[] and decision['morning_request_sha256']==facts['request_sha256']
    # An actual independent final review is still mandatory; preparation review
    # has a different schema/hash and cannot be promoted by the materializer.
    with pytest.raises(kol_policy.KolPolicyError):kol_policy._validate_pair(decision,prepared['review'])


def test_reviewed_wait_rule_materializes_only_in_its_dated_auction_phase(case):
    prepared,packet,facts=prepared_packet(case,template_updates=dict(buy_scale=0,request_conditions=[
        dict(field='session_phase',op='eq',value='opening_auction',evidence_ref='source-reviewed phase'),
        dict(field='trade_date',op='eq',value='2026-10-23',evidence_ref='source date')]))
    result=materialize(prepared,packet,facts,now=NOW.replace(minute=26))
    assert result['decision']['buy_scale']==0 and result['review']=='not_performed'
    assert result['decision']['valid_until']=='2026-10-23T01:30:00Z'
    from xiaocao.kol.prepared_policy import current_facts,preview_risk
    assert current_facts(facts,now=NOW.replace(minute=30))['session_phase']=='other'
    assert preview_risk(prepared,trade_date='2026-10-24',now=NOW.replace(minute=26)) is None


@pytest.mark.parametrize('phases', [['opening_auction'], ['opening_auction','other']])
def test_auction_restriction_cannot_bypass_date_or_expiry_with_membership_predicate(case, phases):
    with pytest.raises(ValueError,match='PHASE_PREDICATE_INVALID'):
        prepared_packet(case,template_updates=dict(buy_scale=0, request_conditions=[
            dict(field='session_phase',op='in',value=phases,evidence_ref='reviewed source')]))


@pytest.mark.parametrize('damage',['delta','source','condition','unresolved','late','packet_hash','request_hash'])
def test_materialization_rejects_new_semantics_or_unproved_current_facts(case,damage):
    prepared,packet,facts=prepared_packet(case)
    now=NOW.replace(minute=26)
    if damage=='delta':packet['delta']['changed']=['0']
    elif damage=='source':packet['source_fingerprint']='changed'
    elif damage=='condition':prepared['draft']['policy_template']['request_conditions'][0]['value']='BLOCKED'
    elif damage=='unresolved':prepared['draft']['policy_template']['unresolved_semantic_conditions']=['unproved breadth condition']
    elif damage=='late':now=NOW.replace(minute=27)
    elif damage=='packet_hash':packet['request_facts_sha256']='changed'
    else:facts['request_sha256']='f'*64
    with pytest.raises(ValueError):materialize(prepared,packet,facts,now=now)


def test_dispatch_handoff_points_parent_to_unapproved_prepared_candidate(case):
    from xiaocao.live.morning_dispatch import write_warm_dispatch
    prepared,packet,facts=prepared_packet(case)
    packet_path=prep.write_artifact(case['root'],packet,'.packet.json')
    facts.pop('request_sha256')
    facts['kol_inputs']={'packet_path':str(packet_path),'packet_sha256':packet['packet_sha256'],'warm_worker':prepared['worker_id']}
    facts['request_sha256']=kol_policy.decision_sha256(facts)
    path=save(case['root']/'request.json',facts)
    result=write_warm_dispatch(facts,path,now=NOW.replace(minute=26))
    value=prep.read_json(result)
    assert value['next_action']=='independently_review_prepared_draft'
    candidate=prep.read_json(value['prepared_policy_path'])
    assert candidate['authority']==0 and candidate['review']=='not_performed'
    assert 'context' not in candidate
    assert prep.read_json(candidate['context_path'])['context_sha256']==candidate['context_sha256']
    assert prep.read_json(candidate['decision_path'])==candidate['decision']


def test_explicit_reviewed_no_effect_fallback_keeps_unknowns_without_model_or_neutral_approval(case):
    from xiaocao.kol.prepared_policy import defer_no_effect
    prepared,packet,facts=prepared_packet(case,defer=True)
    value=defer_no_effect(prepared,packet,facts,now=NOW.replace(minute=26))
    assert value['status']=='deferred' and value['semantic_review_completed'] is False
    assert value['known_unresolved_conditions'] and value['model_dispatch']=='not_performed'
    with pytest.raises(ValueError,match='SEMANTIC_REVIEW_NEEDED'):
        materialize(prepared,packet,facts,now=NOW.replace(minute=26))
    prepared['draft']['policy_template']['buy_scale']=.5
    with pytest.raises(ValueError,match='RISK_EFFECT_PRESENT'):
        defer_no_effect(prepared,packet,facts,now=NOW.replace(minute=26))


def test_no_effect_fallback_rejects_unreviewed_flags_or_applicable_selection(case):
    from xiaocao.kol.prepared_policy import defer_no_effect
    from tests.test_kol_selection import row, preference
    prepared,packet,facts=prepared_packet(case,defer=True)
    prepared['review']['deferred_overlay_reviewed']=False
    with pytest.raises(ValueError,match='NOT_REVIEWED'):
        defer_no_effect(prepared,packet,facts,now=NOW.replace(minute=26))
    prepared['review']['deferred_overlay_reviewed']=True
    prefs=[preference('mode',{'mode':'A'},source_report_id='r')]
    prepared['draft']['selection_preferences']=prefs
    packet['selection_preferences']=prefs
    facts['candidates']=[{**row('000001.XSHE','A',1),'date':'2026-10-23'}]
    facts.pop('request_sha256')
    packet['request_facts_sha256']=prep.canonical_sha256(facts)
    packet['packet_sha256']=prep.canonical_sha256({k:v for k,v in packet.items() if k!='packet_sha256'})
    facts['request_sha256']=kol_policy.decision_sha256(facts)
    with pytest.raises(ValueError,match='SELECTION_EFFECT_PRESENT'):
        defer_no_effect(prepared,packet,facts,now=NOW.replace(minute=26))


def test_deferred_handoff_proves_exact_request_and_retains_uncertainty(case):
    from xiaocao.live.morning_dispatch import write_warm_dispatch,read_deferred_overlay
    prepared,packet,facts=prepared_packet(case,defer=True)
    packet_path=prep.write_artifact(case['root'],packet,'.packet.json')
    facts.pop('request_sha256')
    facts['kol_inputs']={'packet_path':str(packet_path),'packet_sha256':packet['packet_sha256'],'warm_worker':prepared['worker_id']}
    facts['request_sha256']=kol_policy.decision_sha256(facts)
    path=save(case['root']/'request.json',facts)
    handoff=write_warm_dispatch(facts,path,now=NOW.replace(minute=26))
    deferred=read_deferred_overlay(handoff,facts['request_sha256'])
    assert deferred['status']=='deferred' and deferred['known_unresolved_conditions']
    assert prep.read_json(handoff)['next_action']=='continue_original_baseline_deferred'
    with pytest.raises(ValueError,match='HASH_INVALID'):read_deferred_overlay(handoff,'f'*64)
