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


def dependency_user_action(reason: object, health: dict | None = None) -> dict:
    """Only explicit typed failures require a human; unknown counters do not."""
    health = health or {}
    atoms = str(reason or '').split(':')
    requests = {
        'FOUNDER_NATIVE_TRADE_KEYCHAIN_NOT_READY': '请配置或授权读取本机保存的 APP 交易凭据。',
        'FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING': '请确认本机保存的 APP 交易账户。',
        'NATIVE_AX_KEYCHAIN_READ_DENIED': '请授权读取本机保存的 APP 交易凭据。',
        'NATIVE_AX_KEYCHAIN_READ_FAILED': '请检查本机保存的 APP 交易凭据是否可读取。',
        'NATIVE_AX_KEYCHAIN_SECRET_EMPTY': '请补充本机保存的 APP 交易凭据。',
        'NATIVE_AX_UNLOCK_UNPROVEN_NO_RETRY': '请确认 APP 当前登录状态；系统不会再次尝试密码。',
        'NATIVE_AX_CREDENTIAL_HEALTH_UNPROVEN': '请核验 APP 的账户绑定和上次凭据动作记录。',
        'screen_locked': '请解锁 macOS，随后系统重新核验 APP。',
        'screen_lock_state_unavailable': '请恢复可核验的 macOS 登录状态，随后系统重新核验 APP。',
        'accessibility_denied': '请为 Codex 或终端授予 macOS 辅助功能权限。',
    }
    for atom in atoms:
        if atom in requests:
            return {'required': True, 'request': requests[atom]}
    if health.get('state') in {'attempt_claimed', 'unproven_no_retry'}:
        return {'required': True, 'request': requests['NATIVE_AX_UNLOCK_UNPROVEN_NO_RETRY']}
    if 'client_login_required' in atoms or 'app_absent' in atoms:
        return {'required': False, 'request': None, 'recovery_kind': 'app_client_login'}
    return {'required': False, 'request': None}


def _compact_order(row: dict) -> dict:
    result = {k: row.get(k) for k in ('plan_id', 'state', 'broker_order_id',
        'filled_shares', 'fill_price', 'remaining_shares', 'reason', 'next_action',
        'submit_chain_uncertain', 'cancel_chain_uncertain')}
    proof = row.get('locator_proof')
    proof = proof if isinstance(proof, dict) else {}
    result['fill_quantity_proven'] = not (row.get('submit_chain_uncertain') or row.get('cancel_chain_uncertain')) and ((
        row.get('state') in {'filled', 'partial', 'cancelled', 'rejected'}
        and row.get('receipt_mapping') is True
        and proof.get('fill_observation_pending') is False
    ) or (proof.get('fill_aggregate_proven') is True
          and proof.get('fill_observation_pending') is False))
    if row.get('notification_durable_only') is True:
        result['fill_quantity_proven'] = False
    return result


def terminal_notice(payload: dict, receipt_path: Path, *, include_durable_pending=True) -> dict:
    receipts = list(payload.get('execution_receipts', []))
    reconciliations = [*payload.get('open_plan_reconciliations', []),
                       *payload.get('prior_reconciliations', [])]
    durable = []
    if include_durable_pending and receipt_path.parent.name == 'history' and receipt_path.parent.parent.name == 'runs':
        from .trading_execution import ExecutionStore
        from .book_b_live_lifecycle import open_execution_plan_ids
        path = receipt_path.parent.parent.parent / 'events.jsonl'
        if path.is_file():
            # Outstanding state supplies notification scope; it cannot
            # replace current broker readback or grant trading authority.
            store = ExecutionStore(path)
            try:
                ids = open_execution_plan_ids(path.parent)
                durable = [{**current.as_dict(), 'notification_durable_only': True} for plan_id in ids
                           if (current := store.current(plan_id)) is not None]
            except (OSError, ValueError):
                durable = []
                payload = {**payload, 'pending_evidence_unproven': True}
    pending = [r for r in [*durable, *reconciliations]
               if r.get('state') not in {'filled', 'cancelled', 'rejected', 'skipped'}]
    current_ids = {r.get('plan_id') for r in receipts}
    pending = list({r.get('plan_id'): r for r in pending if r.get('plan_id') not in current_ids}.values())
    action = payload.get('user_action') or dependency_user_action(payload.get('reason'))
    for request in (payload.get('dependency_recovery') or {}).get('requests', []):
        if request.get('status') == 'recovered':
            continue
        failures = request.get('failures') or []
        if failures:
            candidate = (failures[-1].get('evidence') or {}).get('user_action') or {}
            if candidate.get('required') is True:
                action = candidate
    return {**{k: payload.get(k) for k in ('run_id', 'trade_date', 'status', 'reason', 'failed_stage', 'runner_identity')},
            'user_action_required': payload.get('user_action_required') is True or action.get('required') is True,
            'user_action': action, 'pending_evidence_unproven': payload.get('pending_evidence_unproven', False),
            'pending_orders': [_compact_order(r) for r in pending],
            'incident_notifications': _incident_notifications(receipt_path, receipts + pending),
            'receipt_path': str(receipt_path.resolve()),
            'stage_times': payload.get('stage_times', {}),
            'orders': [_compact_order(r) for r in receipts],
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
