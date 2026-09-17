"""Bounded pre-arm timing for the 14:55 Book-B closing checkpoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


_CHINA = ZoneInfo("Asia/Shanghai")
_CLOSING_HOUR = 14
_CLOSING_MINUTE = 55
_PREARM_MINUTES = 4
_MAX_PREARM_WAIT_SECONDS = float(_PREARM_MINUTES * 60)
_MAX_SLEEP_CHUNK_SECONDS = 60.0


def closing_prearm_wait_seconds(current: datetime) -> float:
    """Return the bounded delay to 14:55, or zero outside the pre-arm span."""

    local = current.astimezone(_CHINA)
    target = local.replace(
        hour=_CLOSING_HOUR,
        minute=_CLOSING_MINUTE,
        second=0,
        microsecond=0,
    )
    prearm_start = target - timedelta(minutes=_PREARM_MINUTES)
    if not prearm_start <= local < target:
        return 0.0
    return min(
        _MAX_PREARM_WAIT_SECONDS,
        max(0.0, (target - local).total_seconds()),
    )


def wait_for_closing_window(
    *,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Sleep in bounded chunks inside the pre-arm span and return the delay."""

    current = (now or (lambda: datetime.now(_CHINA)))()
    wait_seconds = closing_prearm_wait_seconds(current)
    remaining = wait_seconds
    while remaining > 0:
        chunk = min(_MAX_SLEEP_CHUNK_SECONDS, remaining)
        sleep(chunk)
        remaining -= chunk
    return wait_seconds


def main() -> int:
    wait_for_closing_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
