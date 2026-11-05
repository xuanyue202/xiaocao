"""Preload one current-only analyst and deliver its original frozen request.

These authority-zero files carry no account, publication or execution authority.
The original consumer still owns review, publication and its absolute cutoff.
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from xiaocao.kol import opening_preparation as prep
from xiaocao.kol.trading_decision import read_json
from xiaocao.utils.atomic_files import atomic_write

GUIDE = '.codex/skills/xiaocao-trading/references/kol-current-review.md'


def _write(path: Path, value: dict) -> None:
    import json
    atomic_write(path, json.dumps(value, ensure_ascii=False, sort_keys=True).encode(), immutable=True)


def _owner(binding: dict, *, require_pid: bool = False) -> None:
    if (binding.get('automation_id') not in {'xiaocao-book-b-live-morning', 'xiaocao-daily-morning-execution'}
            or os.environ.get('CODEX_AUTOMATION_ID') != binding['automation_id']
            or os.environ.get('CODEX_THREAD_ID') != binding.get('owner_thread_id')):
        raise ValueError('CURRENT_REVIEW_OWNER_MISMATCH')
    if require_pid and 'runner_pid' in binding and binding['runner_pid'] != os.getpid():
        raise ValueError('CURRENT_REVIEW_PID_MISMATCH')


def warmup_path(directory: Path, binding: dict) -> Path:
    return directory / (prep.canonical_sha256(binding) + '.current-warmup.json')


def prepare(directory: Path, binding: dict, preparation_path: Path, *, now: datetime, root: Path,
            current_input_path: Path | None = None) -> Path | None:
    _owner(binding, require_pid=True)
    path = warmup_path(directory, binding)
    if path.exists():
        value = read_warmup(path)
        if value['binding'] != binding:
            raise ValueError('CURRENT_REVIEW_BINDING_MISMATCH')
        return path
    day = binding['trade_date']
    if now >= prep.aware(day + 'T09:20:00+08:00'):
        return None
    prepared = prep.read_preparation(preparation_path, now=now)
    if prepared.get('schema_version') != 'kol-opening-preparation.v2':
        return None
    guide = root / GUIDE
    value = {'schema_version': 'kol-current-warmup.v1', 'authority': 0, 'binding': binding,
        'prepared_at': now.isoformat(), 'cutoff': day + 'T09:27:00+08:00',
        'preparation_path': str(preparation_path.resolve()),
        'preparation_sha256': prepared['preparation_sha256'],
        'guide_path': str(guide.resolve()), 'guide_sha256': hashlib.sha256(guide.read_bytes()).hexdigest(),
        'handoff_path': str(path.with_suffix('.handoff.json').resolve())}
    value['tool_arguments'] = {'task_name': 'current_' + prep.canonical_sha256(binding)[:16],
        'model': 'gpt-6-sol', 'reasoning_effort': 'xhigh', 'fork_turns': 'none',
        'message': f'Read {guide.resolve()} and this exact current-only warmup: {path.resolve()}. '
                   'Preload accepted shared implications/synthesis and complete early delta; resolve schema/mapping '
                   'before the frozen request, leaving future account/market conditions unknown. '
                   'Then start the guide\'s read-only wait once with your actual canonical worker id. '
                   'Only after its original handoff judge current facts/delta, write the existing v3 draft '
                   'and actual phase timings for independent parent review/publication before09:27. '
                   'No new source synthesis, account/order/notification action or automatic neutral judgment.'}
    if current_input_path is not None:
        from xiaocao.kol.shared_judgment import packet
        inputs = read_json(current_input_path)
        if inputs['binding'] != binding:
            raise ValueError('CURRENT_REVIEW_INPUT_BINDING_MISMATCH')
        early = packet(preparation_path, inputs['projection'], now=now)
        early_path = prep.write_artifact(directory, early, '.early-current-packet.json')
        value.update(early_packet_path=str(early_path), early_packet_sha256=early['packet_sha256'])
    value['warmup_sha256'] = prep.canonical_sha256(value)
    _write(path, value)
    return path


def read_warmup(path: Path) -> dict:
    value = read_json(path)
    if (value.get('schema_version') != 'kol-current-warmup.v1' or value.get('authority') != 0
            or value.get('warmup_sha256') != prep.canonical_sha256({k:v for k,v in value.items() if k != 'warmup_sha256'})
            or hashlib.sha256(Path(value['guide_path']).read_bytes()).hexdigest() != value['guide_sha256']
            or Path(value['handoff_path']) != path.with_suffix('.handoff.json').resolve()):
        raise ValueError('CURRENT_REVIEW_WARMUP_INVALID')
    if value.get('early_packet_path'):
        early = read_json(Path(value['early_packet_path']))
        if (early.get('packet_sha256') != value['early_packet_sha256']
                or early['packet_sha256'] != prep.canonical_sha256({k:v for k,v in early.items() if k!='packet_sha256'})
                or early['preparation_sha256'] != value['preparation_sha256']):
            raise ValueError('CURRENT_REVIEW_EARLY_PACKET_INVALID')
    return value


def register(path: Path, dispatch: dict, loaded: dict, *, now: datetime) -> dict:
    warm = read_warmup(path)
    _owner(warm['binding'])
    args, result = dispatch.get('tool_arguments', {}), dispatch.get('tool_result', {})
    worker = result.get('task_name')
    if (not worker or args.get('model') != 'gpt-6-sol' or args.get('reasoning_effort') != 'xhigh'
            or args.get('fork_turns') != 'none' or dispatch.get('accepted') is not True
            or dispatch.get('warmup_sha256') != warm['warmup_sha256']
            or loaded.get('warmup_sha256') != warm['warmup_sha256'] or loaded.get('worker_id') != worker
            or loaded.get('preparation_sha256') != warm['preparation_sha256']
            or (warm.get('early_packet_sha256') and loaded.get('early_packet_sha256') != warm['early_packet_sha256'])
            or not prep.aware(warm['prepared_at']) <= prep.aware(dispatch['dispatched_at'])
                <= prep.aware(loaded['loaded_at']) <= now < prep.aware(warm['binding']['trade_date']+'T09:20:00+08:00')):
        raise ValueError('CURRENT_REVIEW_ACTUAL_DISPATCH_REQUIRED')
    value = {'schema_version': 'kol-current-worker-registration.v1', 'authority': 0,
        'binding': warm['binding'], 'warmup_sha256': warm['warmup_sha256'], 'worker_id': worker,
        'preparation_sha256': warm['preparation_sha256'], 'registered_at': now.isoformat(),
        'dispatch': dispatch, 'loaded': loaded}
    value['registration_sha256'] = prep.canonical_sha256(value)
    _write(path.with_suffix('.worker.json'), value)
    return value


def record_loaded(path: Path, *, worker_id: str, now: datetime) -> dict:
    """Reuse the worker's original reading receipt when entering its wait."""
    warm = read_warmup(path)
    target = path.with_suffix('.loaded.json')
    expected = {'worker_id': worker_id, 'warmup_sha256': warm['warmup_sha256'],
                'preparation_sha256': warm['preparation_sha256']}
    if warm.get('early_packet_sha256'):
        expected['early_packet_sha256'] = warm['early_packet_sha256']
    loaded = read_json(target) if target.exists() else {**expected, 'loaded_at': now.isoformat()}
    if (not worker_id or target.is_symlink()
            or any(loaded.get(key) != value for key, value in expected.items())
            or not prep.aware(warm['prepared_at']) <= prep.aware(loaded['loaded_at']) <= now
            or prep.aware(loaded['loaded_at']) >= prep.aware(warm['binding']['trade_date']+'T09:20:00+08:00')):
        raise ValueError('CURRENT_REVIEW_LOADED_BINDING_INVALID')
    if not target.exists():
        _write(target, loaded)
    return loaded


def deliver(directory: Path, request: dict, dispatch_path: Path, *, now: datetime,
            publish: bool = True) -> dict | None:
    """Original consumer sends to its already waiting worker without parent hops."""
    path = warmup_path(directory, request['binding'])
    if not path.exists() or not path.with_suffix('.worker.json').exists():
        return None
    warm, registered = read_warmup(path), read_json(path.with_suffix('.worker.json'))
    packet = read_json(Path(request['kol_inputs']['packet_path']))
    if (registered.get('registration_sha256') != prep.canonical_sha256({k:v for k,v in registered.items() if k!='registration_sha256'})
            or registered['binding'] != request['binding'] or warm['binding'] != request['binding']
            or registered['warmup_sha256'] != warm['warmup_sha256']
            or registered['preparation_sha256'] != packet['preparation_sha256']
            or warm['preparation_sha256'] != packet['preparation_sha256']
            or now >= prep.aware(request['review_wait_until'])
            or prep.aware(request['review_wait_until']) > prep.aware(warm['cutoff'])):
        raise ValueError('CURRENT_REVIEW_DELIVERY_BINDING_MISMATCH')
    value = {'schema_version': 'kol-current-handoff.v1', 'authority': 0,
        'binding': request['binding'], 'warmup_sha256': warm['warmup_sha256'],
        'worker_id': registered['worker_id'], 'request_sha256': request['request_sha256'],
        'dispatch_path': str(dispatch_path.resolve()), 'delivered_at': now.isoformat(),
        'cutoff': request['review_wait_until']}
    # The original packet retains the complete source-preparation delta. The
    # waiting analyst already read the early delta: expose only genuinely new
    # units here, with both immutable projections bound for independent audit.
    early_path = warm.get('early_packet_path')
    if early_path:
        from .morning_observability import review_brief
        early = read_json(Path(early_path))
        before = prep.viewpoint_units(prep.read_projection(early['current_projection']))
        current_input = read_json(Path(packet['current_input_path']))
        after = prep.viewpoint_units(prep.read_projection(current_input['projection']))
        changed = {i for i in before.keys() & after.keys()
                   if prep.canonical_sha256(before[i]) != prep.canonical_sha256(after[i])}
        added, removed = after.keys()-before.keys(), before.keys()-after.keys()
        brief = review_brief(request)
        brief.pop('kol_inputs', None)
        work = {'schema_version':'kol-current-work.v1', 'authority':0,
            'request_sha256':request['request_sha256'],
            'request_path':str(dispatch_path.with_name(dispatch_path.name.removesuffix('.dispatch.json')+'.json')),
            'full_packet_path':request['kol_inputs']['packet_path'], 'full_packet_sha256':packet['packet_sha256'],
            'early_packet_path':early_path, 'early_packet_sha256':early['packet_sha256'],
            'preparation_sha256':packet['preparation_sha256'], 'facts':brief,
            'source_fingerprint':packet['source_fingerprint'],
            'since_preload':{'added':sorted(added),'changed':sorted(changed),'removed':sorted(removed),
                'units':{i:after[i] for i in sorted(added|changed)},
                'relation_history':prep.relation_history(prep.read_projection(current_input['projection']))
                    if added or changed or removed else {}},
            'instruction':'Use already-read source reasoning and early delta; review all since_preload delta and current facts. Full original delta remains bound; final independent review/source verification/publication remain mandatory.'}
        work['work_sha256'] = prep.canonical_sha256(work)
        work_path = prep.write_artifact(directory, work, '.current-work.json')
        value.update(work_path=str(work_path), work_sha256=work['work_sha256'])
    value['handoff_sha256'] = prep.canonical_sha256(value)
    if publish:
        _write(Path(warm['handoff_path']), value)
    return value


def wait(path: Path, *, worker_id: str, now=None, sleep=time.sleep) -> dict:
    clock = now or (lambda: datetime.now(prep.TZ))
    warm = read_warmup(path)
    until = prep.aware(warm['cutoff'])
    while clock() < until:
        target = Path(warm['handoff_path'])
        if target.exists():
            value = read_json(target)
            if (value.get('handoff_sha256') != prep.canonical_sha256({k:v for k,v in value.items() if k!='handoff_sha256'})
                    or value['warmup_sha256'] != warm['warmup_sha256'] or value['worker_id'] != worker_id
                    or value['binding'] != warm['binding'] or clock() >= prep.aware(value['cutoff'])):
                raise ValueError('CURRENT_REVIEW_HANDOFF_INVALID')
            dispatch = read_json(Path(value['dispatch_path']))
            if (dispatch['request_sha256'] != value['request_sha256']
                    or dispatch.get('sha256') != prep.canonical_sha256({k:v for k,v in dispatch.items() if k!='sha256'})
                    or dispatch.get('current_worker_id') != worker_id
                    or dispatch.get('cutoff') != value['cutoff']):
                raise ValueError('CURRENT_REVIEW_REQUEST_MISMATCH')
            if value.get('work_path'):
                work = read_json(Path(value['work_path']))
                if (work.get('work_sha256') != value['work_sha256']
                        or work['work_sha256'] != prep.canonical_sha256({k:v for k,v in work.items() if k!='work_sha256'})
                        or work['request_sha256'] != value['request_sha256']):
                    raise ValueError('CURRENT_REVIEW_WORK_INVALID')
            return value
        sleep(min(.1, max(0, (until-clock()).total_seconds())))
    raise ValueError('CURRENT_REVIEW_ORIGINAL_CUTOFF')
