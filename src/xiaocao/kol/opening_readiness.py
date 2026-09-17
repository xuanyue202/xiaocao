"""Separate reusable source reasoning, evidence freshness, and current policy.

This read-only checklist grants no trading authority and performs no network I/O.
"""
from datetime import datetime, timedelta, timezone


def _time(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('aware_time_required')
    return result


def opening_readiness(context: dict, preparation: dict, *, now: datetime,
                      ready_through: datetime, policy: dict | None = None,
                      opening_draft: dict | None = None) -> dict:
    if now.tzinfo is None or ready_through.tzinfo is None or ready_through < now:
        raise ValueError('future_aware_horizon_required')
    coverage = context['coverage']
    history_ttl = float(coverage.get('history_max_cache_age_seconds', 86400))
    selected_ttl = float(coverage.get('max_cache_age_seconds', 300))
    history_due, selected_due = [], []
    for row in context.get('report_index', []):
        verified = _time(row['verified_at']) if row.get('verified_at') else None
        if (verified is None or verified > now or
                verified + timedelta(seconds=history_ttl) < ready_through or
                row.get('longitudinal_loaded') is not True):
            history_due.append(row['report_id'])
    for row in context.get('reports', []):
        verified = _time(row['verified_at']) if row.get('verified_at') else None
        if verified is None or verified > now or verified + timedelta(seconds=selected_ttl) < now:
            selected_due.append(row['report_id'])
    reusable = preparation.get('status') in ('prepared', 'source_revalidation_required')
    current_policy = (policy or {}).get('status') == 'validated'
    draft = opening_draft or {}
    template = draft.get('decision_template') or {}
    review = draft.get('source_review') or {}
    from .publication import canonical_sha256
    draft_body = {k: v for k, v in draft.items() if k != 'source_review'}
    draft_ready = bool(
        draft.get('source_fingerprint') == preparation.get('source_fingerprint')
        and draft.get('source_fingerprint')
        and isinstance(template.get('buy_scale'), (int, float))
        and not isinstance(template.get('buy_scale'), bool)
        and 0 <= template['buy_scale'] <= 1
        and template.get('rationale') and template.get('invalidation_conditions')
        and draft.get('opening_scenarios')
        and review.get('draft_sha256') == canonical_sha256(draft_body)
        and review.get('status') == 'source_reasoning_reviewed'
        and review.get('reviewer_agent_id')
        and draft.get('analyst_agent_id')
        and review['reviewer_agent_id'] != draft['analyst_agent_id'])
    if current_policy:
        next_action = 'reuse_current_policy_check_live_execution_facts'
    elif not reusable:
        next_action = 'complete_source_analysis_and_independent_review'
    elif history_due:
        next_action = 'revalidate_exact_history_ids_reuse_source_notes'
    elif selected_due:
        next_action = 'refresh_selected_sources_reuse_unchanged_notes'
    elif not draft_ready:
        next_action = 'complete_opening_draft_and_independent_source_review'
    else:
        next_action = 'finalize_current_applicability_and_publish'
    return {
        'schema_version': 'kol-opening-readiness.v1', 'authority': 0,
        'as_of': now.astimezone(timezone.utc).isoformat(),
        'ready_through': ready_through.astimezone(timezone.utc).isoformat(),
        'source_analysis_reusable': reusable,
        'opening_draft_ready': draft_ready,
        'precomputation_complete': current_policy or (reusable and draft_ready and not history_due and not selected_due),
        'source_preparation_path': preparation.get('path') or preparation.get('reusable_path'),
        'history_ready_through_horizon': not history_due and bool(context.get('report_index')),
        'history_refresh_report_ids': sorted(history_due),
        'selected_refresh_report_ids': sorted(selected_due),
        'current_policy_status': (policy or {}).get('status', 'not_checked'),
        'current_policy_reusable': current_policy,
        'current_applicability_required': not current_policy,
        'next_action': next_action,
    }
