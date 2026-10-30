"""Original-budget broker readback: no password, order action or new time budget.

The post-business owner uses this scope while observing deferred old claims.
Default execution keeps its existing lock/command behavior. Within the scope,
both queued lock acquisition and each helper process share the original deadline.
"""
from __future__ import annotations

import fcntl
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

_deadline: ContextVar[tuple[datetime, float, bool] | None] = ContextVar('broker_readback_deadline', default=None)
_READ_COMMANDS = frozenset({'version', 'probe', 'check-dialogs', 'read-query',
    'open-query-surface', 'open-order-surface', 'probe-submit-rejection'})


class ReadbackDeadlineExpired(RuntimeError):
    def __init__(self):
        super().__init__('ORIGINAL_READBACK_DEADLINE_EXHAUSTED')


def active() -> bool:
    return _deadline.get() is not None


def remaining() -> float | None:
    bound = _deadline.get()
    if bound is None:
        return None
    seconds = min((bound[0] - datetime.now(timezone.utc)).total_seconds(), bound[1] - time.monotonic())
    if seconds <= 0:
        raise ReadbackDeadlineExpired()
    return seconds


@contextmanager
def original_readback(deadline: datetime, *, allow_known_rejection_ack: bool = False):
    if deadline.utcoffset() is None:
        raise ValueError('ORIGINAL_READBACK_DEADLINE_UNPROVEN')
    prior = _deadline.get()
    if prior is not None:
        deadline = min(deadline, prior[0])
    seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
    monotonic_deadline = time.monotonic() + seconds
    if prior is not None:
        monotonic_deadline = min(monotonic_deadline, prior[1])
    allow_ack = allow_known_rejection_ack and (prior[2] if prior is not None else True)
    token = _deadline.set((deadline, monotonic_deadline, allow_ack))
    try:
        remaining()
        yield
    finally:
        _deadline.reset(token)


def require_read_command(command: str) -> None:
    if active():
        remaining()
        if command not in _READ_COMMANDS and not (
                command == 'acknowledge-submit-rejection' and _deadline.get()[2]):
            raise RuntimeError('ORIGINAL_READBACK_BROKER_WRITE_FORBIDDEN')


def known_rejection_ack_allowed() -> bool:
    return not active() or _deadline.get()[2]


@contextmanager
def mutex(lock):
    seconds = remaining()
    acquired = lock.acquire() if seconds is None else lock.acquire(timeout=seconds)
    if not acquired:
        raise ReadbackDeadlineExpired()
    try:
        remaining()
        yield
    finally:
        lock.release()


def file_lock(descriptor: int, *, wait: bool = True) -> None:
    if not wait:
        remaining()
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if not active():
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return
    while True:
        seconds = remaining()
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            time.sleep(min(0.05, seconds))


def open_locked_file(path: Path):
    """Preserve legacy file handles, closing even when bounded acquisition fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+', encoding='utf-8')
    try:
        file_lock(handle.fileno())
        return handle
    except BaseException:
        handle.close()
        raise
