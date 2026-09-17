from datetime import datetime, timedelta, timezone
from xiaocao.kol.opening_readiness import opening_readiness


def test_prepared_notes_do_not_claim_opening_ready_when_history_expires_during_retry():
    now = datetime(2026, 9, 17, 1, 10, tzinfo=timezone.utc)
    context = {'coverage': {}, 'report_index': [{'report_id': 'old',
        'verified_at': '2026-09-16T01:34:05Z', 'longitudinal_loaded': True}],
        'reports': [{'report_id': 'current', 'verified_at': now.isoformat()}]}
    preparation = {'status': 'prepared', 'path': 'retained-notes'}
    r = opening_readiness(context, preparation, now=now,
        ready_through=now.replace(hour=3, minute=30), policy={'status': 'expired'})
    assert r['source_analysis_reusable'] is True
    assert r['history_ready_through_horizon'] is False
    assert r['history_refresh_report_ids'] == ['old']
    assert r['current_policy_reusable'] is False
    assert r['next_action'] == 'revalidate_exact_history_ids_reuse_source_notes'
    # Ten minutes passing does not expire source reasoning.
    later = opening_readiness(context, preparation, now=now+timedelta(minutes=10),
        ready_through=now.replace(hour=3, minute=30), policy={'status': 'validated'})
    assert later['source_analysis_reusable'] and later['current_policy_reusable']
    assert later['next_action'] == 'reuse_current_policy_check_live_execution_facts'


def test_fresh_evidence_still_requires_current_applicability():
    now = datetime(2026, 9, 17, 1, 10, tzinfo=timezone.utc)
    context = {'coverage': {}, 'report_index': [{'report_id': 'old',
        'verified_at': now.isoformat(), 'longitudinal_loaded': True}],
        'reports': [{'report_id': 'current', 'verified_at': now.isoformat()}]}
    r = opening_readiness(context, {'status': 'prepared'}, now=now,
        ready_through=now+timedelta(hours=2), policy={'status': 'expired'})
    assert r['history_ready_through_horizon']
    assert r['current_applicability_required']
    assert r['next_action'] == 'complete_opening_draft_and_independent_source_review'
    assert r['precomputation_complete'] is False


def test_bare_skeleton_does_not_count_as_completed_precomputation():
    from xiaocao.kol.publication import canonical_sha256
    now = datetime(2026, 9, 17, 1, 10, tzinfo=timezone.utc)
    context = {'coverage': {}, 'report_index': [{'report_id': 'a',
        'verified_at': now.isoformat(), 'longitudinal_loaded': True}],
        'reports': [{'report_id': 'a', 'verified_at': now.isoformat()}]}
    preparation = {'status': 'prepared', 'source_fingerprint': 'same'}
    draft = {'source_fingerprint': 'same', 'analyst_agent_id': 'analyst',
        'decision_template': {'buy_scale': None, 'rationale': None, 'invalidation_conditions': []}}
    kwargs = dict(now=now, ready_through=now+timedelta(hours=2), opening_draft=draft)
    assert not opening_readiness(context, preparation, **kwargs)['precomputation_complete']
    draft['decision_template'].update(buy_scale=1, rationale='Known evidence supports baseline subject to opening checks.',
        invalidation_conditions=['New verified evidence changes the premise'])
    draft['opening_scenarios'] = [{'condition': 'No new contrary evidence', 'adaptation': 'Retain baseline'}]
    draft['source_review'] = {'draft_sha256': canonical_sha256(draft),
        'status': 'source_reasoning_reviewed', 'reviewer_agent_id': 'parent'}
    assert opening_readiness(context, preparation, **kwargs)['precomputation_complete']
    draft['decision_template']['buy_scale'] = 0
    assert not opening_readiness(context, preparation, **kwargs)['opening_draft_ready']
