"""Task-local runner deduplication, separate from resource/ledger locks."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

_task_identity = ContextVar("xiaocao_automation_id", default=None)
_run_owner = ContextVar("xiaocao_dated_run_owner", default=None)


def current_automation_id():
    return _task_identity.get() or os.environ.get("CODEX_AUTOMATION_ID")


def current_run_owner() -> dict | None:
    """Evidence of this process holding a dated runner lock, not an env alias."""
    owner = _run_owner.get()
    return dict(owner) if owner is not None else None


def validate_automation_identity(expected: str, requested: str) -> None:
    inherited = os.environ.get("CODEX_AUTOMATION_ID")
    if requested != expected or (inherited and inherited != expected):
        raise ValueError("AUTOMATION_ENTRYPOINT_ID_MISMATCH")


def runner_identity(automation_id: str, entrypoint: str) -> dict:
    return {"automation_id": automation_id, "owner_thread_id": os.environ.get("CODEX_THREAD_ID"),
            "runner_pid": os.getpid(), "entrypoint": entrypoint}


@contextmanager
def automation_run(automation_id: str, slot: str, *, root: Path):
    for value in (automation_id, slot):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
            raise ValueError("AUTOMATION_LOCK_ID_INVALID")
    path = Path(root) / automation_id / f"{slot}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.seek(0)
            try:
                owner = json.load(handle)
            except ValueError:
                owner = {"status": "unproven"}
            yield {"status": "busy", "automation_id": automation_id, "owner": owner}
            return
        owner = {"automation_id": automation_id, "pid": os.getpid(),
                 "thread_id": os.environ.get("CODEX_THREAD_ID"),
                 "slot": slot, "acquired_at": datetime.now(timezone.utc).isoformat()}
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        token = _task_identity.set(automation_id)
        owner_token = _run_owner.set(owner)
        try:
            yield {"status": "acquired", **owner}
        finally:
            _run_owner.reset(owner_token)
            _task_identity.reset(token)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_scheduler_header(expected: str, *, date: str, codex_home: Path | None = None,
                              now: datetime | None = None) -> dict:
    """Prove the initial header matches the inherited task before effects.

    This is local header evidence, not an unavailable scheduler run token.
    """
    from zoneinfo import ZoneInfo
    validate_automation_identity(expected, expected)
    current = now or datetime.now(timezone.utc)
    if current.utcoffset() is None or current.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != date:
        raise ValueError("INITIAL_SCHEDULER_DATE_MISMATCH")
    thread = os.environ.get('CODEX_THREAD_ID')
    if not thread or os.environ.get('CODEX_AUTOMATION_ID') != expected:
        raise ValueError('AUTOMATION_RUNTIME_IDENTITY_UNPROVEN')
    base = codex_home or Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')
    paths = list((base/'sessions'/date.replace('-','/')).glob(f'*{thread}.jsonl'))
    if len(paths) != 1:
        raise ValueError('INITIAL_SCHEDULER_HEADER_NOT_VERIFIED')
    meta, header = None, None
    user_index = 0
    for line in paths[0].read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        payload = row.get('payload') or {}
        if row.get('type') == 'session_meta':
            meta = payload
        if row.get('type') == 'response_item' and payload.get('role') == 'user':
            content = '\n'.join(item.get('text','') for item in payload.get('content',[]) if isinstance(item,dict))
            # Codex persists the injected AGENTS/environment prelude as user[0].
            # Skip that one structural item, never a human message or later copied header.
            prelude = (user_index == 0 and content.startswith('# AGENTS.md instructions for ')
                       and '<INSTRUCTIONS>' in content and '</INSTRUCTIONS>' in content
                       and '<environment_context>' in content and '</environment_context>' in content)
            user_index += 1
            if prelude:
                continue
            header = content
            break
    if (not meta or meta.get('id') != thread or not header
            or re.search(r'^Automation ID:\s*'+re.escape(expected)+r'\s*$',header,re.M) is None):
        raise ValueError('INITIAL_SCHEDULER_ID_MISMATCH')
    try:
        created = datetime.fromisoformat(str(meta.get('timestamp', '')).replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('INITIAL_SCHEDULER_DATE_MISMATCH') from exc
    if created.tzinfo is None or created.astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()!=date:
        raise ValueError('INITIAL_SCHEDULER_DATE_MISMATCH')
    return {'automation_id':expected,'thread_id':thread,'market_date':date,
            'header_sha256':hashlib.sha256(header.encode()).hexdigest(),
            'identity_proof':'initial_header_and_inherited_thread_scheduler_token_unavailable'}


def validate_monitor_scheduler(*, date: str, phase: str | None = None,
                               now: datetime | None = None) -> dict | None:
    """Opening/sparse production commands prove their own header before reads."""
    expected_by_phase = {"opening": "xiaocao-intraday-monitor",
                         "sparse": "xiaocao-intraday-monitor-05"}
    inherited = os.environ.get("CODEX_AUTOMATION_ID")
    expected = expected_by_phase.get(phase)
    if expected is not None and inherited is not None and inherited != expected:
        raise ValueError("AUTOMATION_ENTRYPOINT_ID_MISMATCH")
    if inherited in expected_by_phase.values():
        return validate_scheduler_header(expected or inherited, date=date, now=now)
    return None
