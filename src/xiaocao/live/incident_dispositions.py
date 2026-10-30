"""Durable incident planning views; raw order/account evidence stays authoritative.

These views are consumed by the next original morning owner, never used as a
cash, fill, risk or order admission shortcut. Generations and bad pointers remain
available for audit; updating a view cannot resolve an execution claim.
"""
from __future__ import annotations

import hashlib
import fcntl
import inspect
import json
import marshal
import os
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .book_b_capital import digest, policy
from .book_b_live_lifecycle import _read_jsonl_strict, load_execution_intents
from .trading_execution import ExecutionState, TERMINAL_STATES
from xiaocao.utils.atomic_files import atomic_write


def _bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


@contextmanager
def _view_lock(root: Path):
    """Serialize only derived publication; never acquire a financial/APP lock."""
    folder = root / 'incident_dispositions'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.writer.lock').open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            # Derived support cannot wait ahead of current financial work.
            raise ValueError('INCIDENT_DISPOSITION_WRITER_BUSY') from exc
        yield


def _quarantine_pointer(root: Path) -> None:
    pointer = root / 'incident_dispositions/latest.json'
    if pointer.exists():
        raw = pointer.read_bytes()
        path = root / 'incident_dispositions/quarantine' / (hashlib.sha256(raw).hexdigest() + '.json')
        atomic_write(path, raw, immutable=True)


def _sources(root: Path) -> tuple[dict, list[dict], dict]:
    from .book_b_live_morning import _event_chain_proven
    intents = load_execution_intents(root)
    events = _read_jsonl_strict(root / 'events.jsonl')
    grouped = {}
    for event in events:
        grouped.setdefault(event['plan_id'], []).append(event)
    for plan_id, rows in grouped.items():
        if plan_id not in intents or not _event_chain_proven(plan_id, rows):
            raise ValueError('INCIDENT_DISPOSITION_EXECUTION_SOURCE_UNPROVEN')
        if any(row['plan_hash'] != digest(intents[plan_id]) for row in rows):
            raise ValueError('INCIDENT_DISPOSITION_INTENT_SOURCE_UNPROVEN')
    return intents, events, grouped


def refresh(root: Path, *, trade_date: str, stage: str, now: datetime,
            account: dict | None = None) -> dict:
    """Append an immutable multidimensional view and publish its atomic pointer."""
    root = Path(root)
    with _view_lock(root):
        return _refresh_locked(root, trade_date=trade_date, stage=stage, now=now, account=account)


def _refresh_locked(root: Path, *, trade_date: str, stage: str, now: datetime,
                    account: dict | None = None, replace_unusable_pointer: bool = False) -> dict:
    from .book_b_live_morning import app_buy_permission_reason
    if now.utcoffset() is None:
        raise ValueError('INCIDENT_DISPOSITION_CLOCK_UNPROVEN')
    root = Path(root)
    intents, events, grouped = _sources(root)
    cfg = policy(root)
    binding = (cfg or {}).get('fund_account_binding_sha256')
    accounting = (account or {}).get('accounting') or {}
    isolation = accounting.get('inherited_buy_isolation')
    if isolation is not None:
        from .inherited_execution import verify
        verify(root, isolation, current=False)
    bounds = {entry['plan_id']: entry for entry in (isolation or {}).get('plan_bounds', [])}
    guard_hash = hashlib.sha256(marshal.dumps(app_buy_permission_reason.__code__)).hexdigest()
    guard_source_hash = hashlib.sha256(inspect.getsource(app_buy_permission_reason).encode()).hexdigest()
    records = []
    for plan_id, rows in grouped.items():
        uncertain = [row for row in rows if row['receipt'].get('state') == 'unknown'
                     or row['receipt'].get('submit_chain_uncertain') or row['receipt'].get('cancel_chain_uncertain')]
        if not uncertain:
            continue
        original, latest = uncertain[0], rows[-1]
        receipt, plan = latest['receipt'], intents[plan_id]
        code = str(plan.get('code') or '')
        # This is a view of the validated execution chain, not another broker
        # validator. Formal server rejection can have no order ID; a proved
        # wrong-identity rejection can retain mapping=False. Preserve both.
        terminal_recorded = ExecutionState(receipt['state']) in TERMINAL_STATES
        permission = app_buy_permission_reason(code) if plan.get('side') == 'BUY' else None
        root_class = 'APP_ORDER_EFFECT_UNPROVEN'
        record = {'incident_id': digest({'binding': binding, 'plan_id': plan_id, 'root_class': root_class}),
            'root_class': root_class, 'plan_id': plan_id, 'plan_hash': latest['plan_hash'], 'code': code,
            'original_trade_date': plan['trade_date'], 'first_failure': {'event_hash': original['event_hash'],
                'reason': original['receipt'].get('reason')},
            'service_order': {'state': receipt['state'], 'event_hash': latest['event_hash'],
                'reason': receipt.get('reason'),
                'broker_order_id': receipt.get('broker_order_id'),
                'submit_claim_id': receipt.get('submit_claim_id'), 'terminal': terminal_recorded,
                'terminal_basis': 'formal_execution_state' if terminal_recorded else None,
                'broker_status': receipt.get('broker_status'), 'receipt_mapping': receipt.get('receipt_mapping')},
            'business_limit': {'status': 'expected_exclusion' if permission else 'no_registered_permission_exclusion',
                'reason': permission, 'scope': 'primary_app_new_buy_only'},
            'technical_repair': {'status': 'loaded_guard_present' if permission else 'not_inferred',
                'loaded_guard_sha256': guard_hash if permission else None, 'natural_acceptance': 'not_inferred'},
            'current_economic_impact': {'status': 'bounded_at_snapshot' if plan_id in bounds else
                'execution_terminal' if terminal_recorded else 'requires_fresh_scope_proof',
                'bound': bounds.get(plan_id), 'accounting_observation_sha256': accounting.get('receipt_sha256'),
                'isolation_sha256': (isolation or {}).get('isolation_sha256')},
            'next_window': {'status': 'requires_current_admission',
                'owner_automation_id': 'xiaocao-book-b-live-morning',
                'entrypoint': 'scripts/book_b_live_morning.py', 'accepted_handoff': False,
                'action': 'fresh_account_cash_owned_marks_and_effect_bounds_before_independent_buy'},
            'order_replay_allowed': False}
        records.append(record)
        record['technical_repair']['source_guard_sha256'] = guard_source_hash if permission else None
        record['technical_repair']['history_query_complete'] = (receipt.get('locator_proof') or {}).get('history_query_complete')
    body = {'schema_version': 'book-b-incident-dispositions.v1', 'trade_date': trade_date,
        'stage': stage, 'recorded_at': now.isoformat(), 'logical_account_id': 'primary',
        'fund_account_binding_sha256': binding, 'admission_authority': 'none',
        'source_owner': {'automation_id': os.environ.get('CODEX_AUTOMATION_ID'),
                         'thread_id': os.environ.get('CODEX_THREAD_ID')},
        'execution_source': {'event_count': len(events), 'events_sha256': digest(events)},
        'records': records}
    generation = digest(body)
    folder = root / 'incident_dispositions'
    path = folder / (generation + '.json')
    raw = _bytes(body)
    atomic_write(path, raw, immutable=True)
    reference = {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
        'generation_sha256': generation, 'trade_date': trade_date, 'stage': stage,
        'counts': dict(Counter(row['current_economic_impact']['status'] for row in records)),
        'admission_authority': 'none'}
    try:
        _, prior = _read(root)
        # Slow/older owners can keep their immutable generation, but cannot
        # roll back the next consumer's pointer to older source evidence/time.
        publish = replace_unusable_pointer or (prior['execution_source']['event_count'] <= len(events)
            and (prior['trade_date'], datetime.fromisoformat(prior['recorded_at']))
                <= (trade_date, now))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        _quarantine_pointer(root)
        publish = True
    reference['latest_pointer_updated'] = publish
    if publish:
        atomic_write(folder / 'latest.json', _bytes(reference))
    return reference


def _read(root: Path) -> tuple[dict, dict]:
    folder = root / 'incident_dispositions'
    ref = json.loads((folder/'latest.json').read_text())
    path = Path(ref['path'])
    if path.is_symlink() or path.resolve() != (folder/(ref['generation_sha256']+'.json')).resolve():
        raise ValueError('INCIDENT_DISPOSITION_PATH_UNPROVEN')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('INCIDENT_DISPOSITION_HASH_MISMATCH')
    body = json.loads(raw)
    prefix = body['execution_source']
    recorded = datetime.fromisoformat(body['recorded_at'])
    if (digest(body) != ref['generation_sha256'] or body.get('admission_authority') != 'none'
            or body.get('schema_version') != 'book-b-incident-dispositions.v1'
            or type(prefix['event_count']) is not int or prefix['event_count'] < 0
            or recorded.utcoffset() is None
            or ref['trade_date'] != body['trade_date'] or ref['stage'] != body['stage']):
        raise ValueError('INCIDENT_DISPOSITION_BINDING_UNPROVEN')
    return ref, body


def consume(root: Path, *, trade_date: str, run_id: str, now: datetime) -> dict:
    """Prove an actual original-run consumption, rebuilding a derived view if needed."""
    root = Path(root)
    with _view_lock(root):
        return _consume_locked(root, trade_date=trade_date, run_id=run_id, now=now)


def _consume_locked(root: Path, *, trade_date: str, run_id: str, now: datetime) -> dict:
    if now.utcoffset() is None or not run_id:
        raise ValueError('INCIDENT_DISPOSITION_CONSUMER_BINDING_UNPROVEN')
    prior_ref = None
    recovery = None
    try:
        prior_ref, prior = _read(root)
        _, events, _ = _sources(root)
        prefix = prior['execution_source']
        if (len(events) < prefix['event_count']
                or digest(events[:prefix['event_count']]) != prefix['events_sha256']):
            raise ValueError('INCIDENT_DISPOSITION_SOURCE_PREFIX_CHANGED')
        if prior.get('fund_account_binding_sha256') != (policy(root) or {}).get('fund_account_binding_sha256'):
            raise ValueError('INCIDENT_DISPOSITION_ACCOUNT_MISMATCH')
        advanced = len(events) != prefix['event_count']
        if prior['trade_date'] > trade_date or datetime.fromisoformat(prior['recorded_at']) > now:
            raise ValueError('INCIDENT_DISPOSITION_FUTURE_SOURCE')
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        recovery = type(exc).__name__ + ':' + str(exc)
        _quarantine_pointer(root)
        prior_ref, advanced = None, True
    current = _refresh_locked(root, trade_date=trade_date, stage='morning_consumption', now=now,
        replace_unusable_pointer=prior_ref is None) if advanced or prior_ref is None else prior_ref
    from .app_test_window import app_test_context_active
    from xiaocao.automation_run import current_run_owner
    run_owner = current_run_owner()
    owner_bound = (os.environ.get('CODEX_AUTOMATION_ID') == 'xiaocao-book-b-live-morning'
        and bool(os.environ.get('CODEX_THREAD_ID')) and not app_test_context_active()
        and run_owner is not None and run_owner.get('automation_id') == 'xiaocao-book-b-live-morning'
        and run_owner.get('slot') == trade_date and run_owner.get('pid') == os.getpid()
        and run_owner.get('thread_id') == os.environ['CODEX_THREAD_ID'])
    body = {'schema_version':'book-b-incident-consumption.v1','trade_date':trade_date,'run_id':run_id,
        'consumed_at':now.isoformat(),'consumer':{'automation_id':os.environ.get('CODEX_AUTOMATION_ID'),
            'thread_id':os.environ.get('CODEX_THREAD_ID')},'prior_ref':prior_ref,'current_ref':current,
        'dated_lock_owner':run_owner,
        'source_advanced':advanced,'derived_recovery':recovery,'admission_authority':'none',
        'accepted_handoff':owner_bound}
    raw=_bytes(body);path=root/'incident_dispositions/consumptions'/(hashlib.sha256(raw).hexdigest()+'.json')
    atomic_write(path,raw,immutable=True)
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),
        'current_ref':current,'derived_recovery':recovery,'admission_authority':'none'}
