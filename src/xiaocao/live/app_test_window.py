"""Keep APP engineering tests outside the user's trading window (China time)."""
from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime, time
from functools import wraps
from zoneinfo import ZoneInfo

_active = ContextVar("app_simulation_test", default=False)
TEST_CONTEXT_ENV = "XIAOCAO_APP_SIMULATION_TEST"
WINDOW_DESCRIPTION = "Asia/Shanghai: weekends, or weekdays before 09:00 / from 15:00"


class AppTestWindowClosed(RuntimeError):
    pass


def app_tests_allowed(now: datetime | None = None) -> bool:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    if current.tzinfo is None:
        raise ValueError("APP test clock must have a timezone")
    current = current.astimezone(ZoneInfo("Asia/Shanghai"))
    return current.weekday() >= 5 or current.time() < time(9) or current.time() >= time(15)


def require_app_test_window() -> None:
    if not app_tests_allowed():
        raise AppTestWindowClosed("APP_TEST_TIME_BLOCKED: " + WINDOW_DESCRIPTION)


def app_test_context_active() -> bool:
    return _active.get() or os.environ.get(TEST_CONTEXT_ENV) == "1"


def app_test_only(function):
    """Mark a manual/automatic test entrypoint; production callers stay unmarked."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        require_app_test_window()
        token = _active.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _active.reset(token)
    return wrapped
