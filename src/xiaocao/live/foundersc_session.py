"""One user, one native APP surface, regardless of checkout/account-state path.

Acquire account/ledger locks before this session, never in the opposite order.
The execution port holds a session from probe through final broker readback;
individual adapter operations and raw helper invocations nest in that session.
"""
from __future__ import annotations

import fcntl
import os
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path


_mutex = threading.RLock()
_descriptor: int | None = None


def session_path() -> Path:
    # Neither a checkout nor a caller-controlled account-state directory owns
    # the APP. Keep all supported project entrypoints on the same user lock.
    return Path.home() / "Library/Caches/xiaocao/locks/foundersc-app.lock"


def _after_fork() -> None:
    global _mutex, _descriptor
    if _descriptor is not None:
        os.close(_descriptor)  # Do not unlock the parent's open file description.
    _descriptor = None
    _mutex = threading.RLock()


os.register_at_fork(after_in_child=_after_fork)


@contextmanager
def app_session():
    """Serialize threads/processes; yield an FD the helper must inherit.

If Python is killed while its helper still runs, the inherited descriptor
keeps the surface fenced until that helper exits. A normal subprocess timeout
kills and waits for the helper before releasing the session.
"""
    global _descriptor
    with _mutex:
        if _descriptor is not None:
            yield _descriptor
            return
        path = session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            _descriptor = descriptor
            yield descriptor
        finally:
            _descriptor = None
            # Closing (rather than explicit LOCK_UN) preserves the fence if
            # an interrupted caller leaves a helper holding the inherited FD.
            os.close(descriptor)


def serialized_app_operation(method):
    """Fence an entire multi-command adapter operation, including reads."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        with app_session():
            return method(*args, **kwargs)
    return wrapped
