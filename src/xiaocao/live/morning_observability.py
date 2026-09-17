"""Small operator messages; complete immutable receipts stay on disk."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path


_CANDIDATE_FIELDS = (
    'code', 'name', 'mode', 'mode_state', 'mode_trade_eligible',
    'mode_exec_star', 'mode_exec_rank', 'mode_exec_target_weight',
    'open', 'open_pct_change', 'basket_price', 'market_price',
    'market_observed_at', 'market_guard_status', 'down_price',
    'ai_hard_veto', 'veto_flags', 'snapshot_ref',
)


def review_brief(request: dict) -> dict:
    """Project decision-bearing fields without replacing the source artifact."""
    requested = datetime.fromisoformat(request['requested_at'])
    entry = datetime.fromisoformat(request['entry_deadline'])
    deadline = min(entry, requested + timedelta(seconds=min(120, request['max_wait_seconds'])))
    return {
        'schema_version': 'book-b-live-review-brief.v1',
        **{k: request.get(k) for k in (
            'request_id', 'request_sha256', 'requested_at', 'entry_deadline',
            'freeze_path', 'freeze_sha256', 'strategy_sha', 'trade_date',
            'allocation_facts_path', 'allocation_capsule_sha256',
            'account_facts', 'account_risk',
        )},
        'review_deadline': deadline.isoformat(),
        'candidates': [{k: row[k] for k in _CANDIDATE_FIELDS if k in row}
                       for row in request.get('candidates', [])],
        'detail_policy': 'Read full request only for missing decision-relevant fields.',
    }


def review_notice(request: dict, request_path: Path, receipt_path: Path, brief_path: Path) -> dict:
    brief = review_brief(request)
    return {'event': 'book_b_live_review_requested',
            'request_id': request['request_id'], 'request_sha256': request['request_sha256'],
            'request_path': str(request_path), 'receipt_path': str(receipt_path),
            'brief_path': str(brief_path), 'review_deadline': brief['review_deadline'],
            'candidate_count': len(brief['candidates'])}


def terminal_notice(payload: dict, receipt_path: Path) -> dict:
    receipts = payload.get('execution_receipts', [])
    return {**{k: payload.get(k) for k in ('run_id', 'trade_date', 'status', 'reason', 'failed_stage')},
            'receipt_path': str(receipt_path.resolve()),
            'stage_times': payload.get('stage_times', {}),
            'orders': [{k: r.get(k) for k in ('plan_id', 'state', 'broker_order_id',
                       'filled_shares', 'fill_price', 'reason', 'submit_chain_uncertain',
                       'cancel_chain_uncertain')} for r in receipts],
            'review': {k: (payload.get('review_rendezvous') or {}).get(k)
                       for k in ('status', 'reason', 'supporting_health', 'decision_id')},
            'submission_observations': payload.get('submission_observations', [])}
