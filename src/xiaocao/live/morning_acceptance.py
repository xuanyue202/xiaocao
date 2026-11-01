"""Post-business repair observations, bound to the original owner and receipts.

This is an audit consumer. It never probes the APP, evaluates new trading
permission, reconciles an order or treats an unexercised branch as accepted.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import marshal
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.automation_run import current_run_owner
from xiaocao.runner_recovery import _hash
from xiaocao.utils.atomic_files import atomic_write
from .app_test_window import app_test_context_active


def _read(path: Path, parent: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.resolve().is_relative_to(parent.resolve()):
        raise ValueError('MORNING_ACCEPTANCE_EVIDENCE_PATH_UNPROVEN')
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('MORNING_ACCEPTANCE_EVIDENCE_INVALID')
    return value, raw


def _archive(root: Path, path: Path) -> tuple[dict, bytes]:
    value, raw = _read(path, root / 'runs/history')
    run_id, day = value.get('run_id'), value.get('trade_date')
    if (not isinstance(run_id, str) or not isinstance(day, str)
            or Path(run_id).name != run_id or not run_id.startswith(day + '-')
            or path.resolve() != (root / 'runs/history' / (run_id + '.json')).resolve()
            or Path(value.get('state_path', '')).resolve() != root.resolve()):
        raise ValueError('MORNING_ACCEPTANCE_ORIGINAL_ARCHIVE_UNPROVEN')
    return value, raw


def _consumption(root: Path, receipt: dict) -> dict:
    ref = receipt.get('inherited_incidents') or {}
    if not ref.get('path'):
        return {'status': 'not_recorded'}
    try:
        value, raw = _read(Path(ref['path']), root / 'incident_dispositions/consumptions')
        identity = receipt['runner_identity']
        owner = value['dated_lock_owner']
        if (hashlib.sha256(raw).hexdigest() != ref.get('sha256')
                or value.get('schema_version') != 'book-b-incident-consumption.v1'
                or value.get('run_id') != receipt['run_id'] or value.get('trade_date') != receipt['trade_date']
                or value.get('admission_authority') != 'none' or value.get('accepted_handoff') is not True
                or value.get('consumer') != {'automation_id': identity['automation_id'], 'thread_id': identity['owner_thread_id']}
                or owner.get('automation_id') != identity['automation_id']
                or owner.get('thread_id') != identity['owner_thread_id']
                or owner.get('pid') != identity['runner_pid'] or owner.get('slot') != receipt['trade_date']):
            raise ValueError('MORNING_ACCEPTANCE_CONSUMPTION_BINDING_UNPROVEN')
        current = value['current_ref']
        view, view_raw = _read(Path(current['path']), root / 'incident_dispositions')
        from .book_b_capital import digest
        from .book_b_live_lifecycle import _read_jsonl_strict
        source = view['execution_source']
        events = _read_jsonl_strict(root / 'events.jsonl')
        count = source['event_count']
        if (hashlib.sha256(view_raw).hexdigest() != current['sha256']
                or digest(view) != current['generation_sha256']
                or view.get('schema_version') != 'book-b-incident-dispositions.v1'
                or type(count) is not int or count < 0 or count > len(events)
                or digest(events[:count]) != source['events_sha256']):
            raise ValueError('MORNING_ACCEPTANCE_DISPOSITION_SOURCE_UNPROVEN')
        return {'status': 'observed', 'evidence': {'path': ref['path'], 'sha256': ref['sha256']}}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'unproved'}


def _account_observation(root: Path, receipt: dict, *, recorded_ref: dict | None = None) -> dict:
    try:
        if recorded_ref is None:
            checklist, _ = _read(Path(receipt['checklist_path']), root / 'runs/checklists')
            path = Path(checklist['items']['account_risk']['observation_path'])
        else:
            path = Path(recorded_ref['path'])
        observation, raw = _read(path, root / 'runs/checklists/observations')
        observed = datetime.fromisoformat(observation['observed_at'])
        binding = {**receipt['runner_identity'], 'trade_date': receipt['trade_date'],
                   'preparation_deadline': receipt['preparation_deadline']}
        if (recorded_ref is not None and hashlib.sha256(raw).hexdigest() != recorded_ref['sha256']
                or _hash(observation) != path.stem or observation.get('binding') != binding
                or observation.get('item') != 'account_risk' or not observation.get('evidence')
                or observed.utcoffset() is None
                or observed.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() != receipt['trade_date']):
            raise ValueError('MORNING_ACCEPTANCE_ACCOUNT_OBSERVATION_UNPROVEN')
        return {'status': 'observed', 'recorded_status': observation['status'],
                'evidence': {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'not_recorded_or_unproved'}


def _loaded_runtime() -> dict:
    from .inherited_execution import _calculate
    from .book_b_live_lifecycle import unresolved_prior_sell_codes
    from .foundersc_native_broker import FounderscNativeAXBrokerAdapter
    functions = {'inherited_buy_bound': _calculate, 'prior_sell_fence': unresolved_prior_sell_codes,
                 'native_recovery': FounderscNativeAXBrokerAdapter.recover}
    return {name: hashlib.sha256(marshal.dumps(inspect.unwrap(function).__code__)).hexdigest()
            for name, function in functions.items()}


def record_repair_acceptance(root: Path, receipt_path: Path, *, original_receipt_sha256: str) -> dict:
    root, receipt_path = Path(root), Path(receipt_path)
    receipt, raw = _archive(root, receipt_path)
    # The wrapper sealed/published this in-memory payload before supporting
    # work. Never certify a replacement first encountered by this audit.
    if _hash(receipt) != original_receipt_sha256:
        raise ValueError('MORNING_ACCEPTANCE_SEALED_RECEIPT_CHANGED')
    identity, owner = receipt.get('runner_identity') or {}, current_run_owner() or {}
    if (receipt.get('recovery_of') is not None
            or identity.get('automation_id') != 'xiaocao-book-b-live-morning'
            or os.environ.get('CODEX_AUTOMATION_ID') != identity.get('automation_id')
            or os.environ.get('CODEX_THREAD_ID') != identity.get('owner_thread_id')
            or owner.get('automation_id') != identity.get('automation_id')
            or not identity.get('owner_thread_id') or owner.get('thread_id') != identity['owner_thread_id']
            or owner.get('pid') != os.getpid() or identity.get('runner_pid') != os.getpid()
            or owner.get('slot') != receipt['trade_date']):
        raise ValueError('MORNING_ACCEPTANCE_ORIGINAL_OWNER_REQUIRED')
    consumption = _consumption(root, receipt)
    account = _account_observation(root, receipt)
    stages = receipt.get('stage_times') or {}
    def dated_stage(name):
        try:
            clock = datetime.fromisoformat(stages[name])
            return clock.utcoffset() is not None and clock.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat() == receipt['trade_date']
        except (ValueError, TypeError, KeyError):
            return False
    deferred = receipt.get('deferred_prior_day_buy_plan_ids') or receipt.get('deferred_prior_day_sell_plan_ids')
    admission = ('not_exercised' if not deferred else 'current_admission_reached'
                 if account['status'] == 'observed' and any(dated_stage(stage) for stage in ('materialize', 'execution'))
                 else 'not_reached_or_unproved')
    body = {'schema_version': 'book-b-repair-acceptance.v1', 'trade_date': receipt['trade_date'],
        'run_id': receipt['run_id'], 'runner_identity': identity, 'dated_lock_owner': owner,
        'natural_run_observed': not app_test_context_active(), 'loaded_runtime': _loaded_runtime(),
        'original_receipt': {'path': str(receipt_path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                             'canonical_sha256': original_receipt_sha256},
        'incident_consumption': consumption, 'current_account_observation': account,
        'independent_admission': admission, 'business_status': receipt.get('status'),
        'business_reason': receipt.get('reason'), 'failed_stage': receipt.get('failed_stage'),
        'execution_states': [row.get('state') for row in receipt.get('execution_receipts', [])],
        'admission_authority': 'none', 'broker_actions': 0}
    body['receipt_sha256'] = _hash(body)
    path = root / 'runs/repair_acceptance' / (receipt['run_id'] + '.json')
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    atomic_write(path, payload, immutable=True)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(payload).hexdigest(),
        'natural_run_observed': body['natural_run_observed'], 'independent_admission': admission,
        'incident_consumption': consumption['status'], 'admission_authority': 'none'}


def read_repair_acceptance(root: Path, receipt_path: Path) -> dict:
    """Pipeline observation never manufactures a missing original-owner audit."""
    try:
        receipt, raw = _archive(Path(root), Path(receipt_path))
        path = Path(root) / 'runs/repair_acceptance' / (receipt['run_id'] + '.json')
        value, audit_raw = _read(path, Path(root) / 'runs/repair_acceptance')
        body = {key: val for key, val in value.items() if key != 'receipt_sha256'}
        owner, identity = value.get('dated_lock_owner') or {}, receipt.get('runner_identity') or {}
        if (value.get('schema_version') != 'book-b-repair-acceptance.v1'
                or value.get('admission_authority') != 'none' or value.get('broker_actions') != 0
                or owner.get('automation_id') != identity.get('automation_id')
                or owner.get('thread_id') != identity.get('owner_thread_id')
                or owner.get('pid') != identity.get('runner_pid') or owner.get('slot') != receipt['trade_date']
                or type(value.get('natural_run_observed')) is not bool
                or value.get('receipt_sha256') != _hash(body) or value.get('run_id') != receipt['run_id']
                or value.get('trade_date') != receipt['trade_date']
                or value.get('runner_identity') != receipt.get('runner_identity')
                or value.get('original_receipt') != {'path': str(Path(receipt_path).resolve()),
                    'sha256': hashlib.sha256(raw).hexdigest(), 'canonical_sha256': _hash(receipt)}):
            raise ValueError('MORNING_ACCEPTANCE_ORIGINAL_RECEIPT_CHANGED')
        consumption = value.get('incident_consumption') or {}
        account = value.get('current_account_observation') or {}
        if (consumption.get('status') == 'observed' and _consumption(Path(root), receipt) != consumption
                or account.get('status') == 'observed'
                and _account_observation(Path(root), receipt, recorded_ref=account['evidence']) != account):
            raise ValueError('MORNING_ACCEPTANCE_RECORDED_SOURCE_CHANGED')
        return {'status': 'observed', 'path': str(path.resolve()),
                'sha256': hashlib.sha256(audit_raw).hexdigest(), 'facts': value}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'unproved'}
