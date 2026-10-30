"""Observe deferred old claims after the original opening result is sealed.

This is part of the same owner/process and original budget. It never rewrites
the opening receipt, publishes a new trading result, or calls an execution
entry that can prepare, submit, replace or cancel an order.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .bounded_readback import original_readback, ReadbackDeadlineExpired
from .book_b_live_lifecycle import load_execution_intents, read_execution_plan
from .trading_execution import ExecutionReceipt, ExecutionStore, TradePlan, TERMINAL_STATES, _safe_failure_code
from xiaocao.automation_run import current_automation_id
from xiaocao.utils.atomic_files import atomic_write


def reconcile_deferred(root: Path, receipt_path: Path, *,
        reconcile: Callable[[TradePlan], ExecutionReceipt],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict:
    root, receipt_path = Path(root), Path(receipt_path)
    raw = receipt_path.read_bytes()
    terminal = json.loads(raw)
    identity = terminal['runner_identity']
    expected = (root / 'runs/history' / (terminal['run_id'] + '.json')).resolve()
    if (receipt_path.is_symlink() or receipt_path.resolve() != expected
            or Path(terminal['state_path']).resolve() != root.resolve()
            or identity.get('automation_id') != 'xiaocao-book-b-live-morning'
            or current_automation_id() != identity['automation_id']
            or not identity.get('owner_thread_id')
            or identity['owner_thread_id'] != os.environ.get('CODEX_THREAD_ID')
            or identity.get('runner_pid') != os.getpid()):
        raise ValueError('MORNING_DEFERRED_ORIGINAL_OWNER_UNPROVEN')
    deadline = datetime.fromisoformat(terminal['preparation_deadline'])
    if deadline.utcoffset() is None:
        raise ValueError('MORNING_DEFERRED_ORIGINAL_DEADLINE_UNPROVEN')
    ids = list(dict.fromkeys(terminal.get('deferred_prior_day_buy_plan_ids', [])
        + terminal.get('deferred_prior_day_sell_plan_ids', [])))
    store = ExecutionStore(root / 'events.jsonl')
    results, unobserved = [], []
    deferred_reason = None
    current_proofs = []
    # A process-level blocked receipt is not completion of its current repair
    # or claimed orders. Return promptly so that owner can use its legal narrow
    # continuation; old reads must not consume that opportunity or dated lock.
    if terminal['status'] not in {'completed', 'no_action', 'skipped'}:
        deferred_reason = 'CURRENT_BUSINESS_NOT_TERMINAL'
    else:
        from .book_b_live_morning import _event_chain_proven
        current_ids = set(terminal.get('persisted_plan_ids', [])) | {
            row['plan_id'] for row in terminal.get('execution_receipts', [])}
        try:
            with original_readback(deadline):
                current_intents = load_execution_intents(root)
                for plan_id in current_ids:
                    plan = read_execution_plan(current_intents[plan_id])
                    current = store.current(plan_id)
                    if (current is None or current.state not in TERMINAL_STATES
                            or current.plan_hash != plan.plan_hash
                            or not _event_chain_proven(plan_id, store.events(plan_id))):
                        deferred_reason = 'CURRENT_ORDER_TERMINAL_UNPROVEN'
                        break
                    current_proofs.append({'plan_id': plan_id, 'plan_hash': current.plan_hash,
                        'event_id': current.event_id, 'state': current.state.value})
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            deferred_reason = _safe_failure_code(exc)
    if deferred_reason:
        unobserved = ids
    intents = load_execution_intents(root) if not deferred_reason else {}
    for index, plan_id in enumerate(ids if not deferred_reason else []):
        if now() >= deadline:
            unobserved = ids[index:]
            break
        before = None
        try:
            with original_readback(deadline):
                before = store.current(plan_id)
                plan = read_execution_plan(intents[plan_id])
                if (plan.trade_date >= terminal['trade_date'] or before is None
                        or before.plan_hash != plan.plan_hash or not before.submit_claim_id):
                    raise ValueError('MORNING_DEFERRED_ORIGINAL_CLAIM_UNPROVEN')
                observed = reconcile(plan)
                durable = store.current(plan_id)
                if durable is None or observed.event_id != durable.event_id or durable.plan_hash != plan.plan_hash:
                    raise ValueError('MORNING_DEFERRED_DURABLE_READBACK_UNPROVEN')
            results.append({'plan_id': plan_id, 'before_event_id': before.event_id,
                'receipt': durable.as_dict(), 'observed_at': now().isoformat()})
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            results.append({'plan_id': plan_id, 'before_event_id': before.event_id if before else None,
                'status': 'unproven', 'reason': _safe_failure_code(exc), 'observed_at': now().isoformat()})
            if isinstance(exc, ReadbackDeadlineExpired) or now() >= deadline:
                unobserved = ids[index + 1:]
                break
    from .incident_dispositions import refresh
    try:
        if deferred_reason:
            dispositions = {'status': 'deferred', 'reason': deferred_reason, 'admission_authority': 'none'}
        else:
            with original_readback(deadline):
                dispositions = refresh(root, trade_date=terminal['trade_date'], stage='post_business', now=now())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        dispositions = {'status': 'degraded', 'reason': _safe_failure_code(exc), 'admission_authority': 'none'}
    body = {'schema_version': 'book-b-deferred-reconciliation.v1', 'trade_date': terminal['trade_date'],
        'original_run_id': terminal['run_id'], 'runner_identity': identity,
        'terminal_receipt_path': str(receipt_path.resolve()),
        'terminal_receipt_sha256': hashlib.sha256(raw).hexdigest(),
        'original_deadline': deadline.isoformat(), 'completed_at': now().isoformat(),
        'results': results, 'unobserved_plan_ids': unobserved,
        'deferred_reason': deferred_reason, 'current_terminal_proofs': current_proofs,
        'incident_dispositions': dispositions, 'actions': 'exact_claim_readback_only',
        'budget_extended': False, 'opening_receipt_rewritten': False}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    path = root / 'runs/deferred_reconciliation' / (hashlib.sha256(payload).hexdigest() + '.json')
    atomic_write(path, payload, immutable=True)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(payload).hexdigest(),
        'attempted_count': len(results), 'proved_receipt_count': sum('receipt' in row for row in results),
        'unproven_count': sum('receipt' not in row for row in results),
        'unobserved_count': len(unobserved), 'deferred_reason': deferred_reason,
        'actions': 'exact_claim_readback_only'}
