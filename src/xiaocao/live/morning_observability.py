"""Small operator messages; complete immutable receipts stay on disk."""
from __future__ import annotations

import json
import re
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
    receipts = list(payload.get('execution_receipts', []))
    pending = [r for r in payload.get('open_plan_reconciliations', [])
               if r.get('state') not in {'filled', 'cancelled', 'rejected', 'skipped'}]
    return {**{k: payload.get(k) for k in ('run_id', 'trade_date', 'status', 'reason', 'failed_stage')},
            'pending_orders': [{k: r.get(k) for k in ('plan_id', 'state', 'broker_order_id',
                'filled_shares', 'remaining_shares', 'reason', 'next_action')} for r in pending],
            'incident_notifications': _incident_notifications(receipt_path, receipts + pending),
            'receipt_path': str(receipt_path.resolve()),
            'stage_times': payload.get('stage_times', {}),
            'orders': [{k: r.get(k) for k in ('plan_id', 'state', 'broker_order_id',
                       'filled_shares', 'fill_price', 'reason', 'submit_chain_uncertain',
                       'cancel_chain_uncertain')} for r in receipts],
            'review': {k: (payload.get('review_rendezvous') or {}).get(k)
                       for k in ('status', 'reason', 'supporting_health', 'decision_id')},
            'submission_observations': payload.get('submission_observations', [])}


def _incident_notifications(receipt_path: Path, orders: list[dict]) -> list[dict]:
    """Read existing delivery proof; never send or infer user acknowledgement."""
    if receipt_path.parent.name != 'history' or receipt_path.parent.parent.name != 'runs':
        return []
    path = receipt_path.parent.parent.parent / 'incidents.jsonl'
    ids = {str(r['broker_order_id']) for r in orders if r.get('broker_order_id')}
    if not ids or not path.is_file():
        return []
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        return [{'status': 'delivery_readback_unproven'}]
    matches = {}
    for row in rows:
        if not isinstance(row, dict):
            return [{'status': 'delivery_readback_unproven'}]
        order = re.search(r'(?:^|\s)order_id=([^\s]+)', str(row.get('body', '')))
        if order and order.group(1) in ids:
            matches[row.get('incident_id')] = order.group(1)
    results = {}
    for row in rows:
        key = row.get('incident_id')
        if key in matches:
            prior = results.get(key, {})
            if prior.get('status') == 'delivered':
                continue
            results[key] = {'incident_id': key, 'broker_order_id': matches[key],
                            'status': row.get('status')}
            if row.get('status') == 'delivered':
                result = row.get('result')
                results[key].update(delivered_at=row.get('created_at'),
                    wecom=result.get('wecom') if isinstance(result, dict) else None)
    return list(results.values())
