"""Bounded pre-arm timing for the 14:45 Book-B closing checkpoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, time as wall_time
from zoneinfo import ZoneInfo


_CHINA = ZoneInfo("Asia/Shanghai")
_CLOSING_HOUR = 14
_CLOSING_MINUTE = 45


def closing_prearm_wait_seconds(current: datetime) -> float:
    """Return the same-day delay to 14:45, including scheduler early wakes."""

    local = current.astimezone(_CHINA)
    target = local.replace(
        hour=_CLOSING_HOUR,
        minute=_CLOSING_MINUTE,
        second=0,
        microsecond=0,
    )
    return max(0.0, (target - local).total_seconds())


def wait_for_closing_window(
    *,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Sleep in bounded chunks inside the pre-arm span and return the delay."""

    from xiaocao.utils.business_clock import wait_for_business_time
    now = now or (lambda: datetime.now(_CHINA))
    current = now()
    return wait_for_business_time(current.astimezone(_CHINA).date().isoformat(),
                                  wall_time(14, 45), now=now, sleep=sleep)


def main() -> int:
    wait_for_closing_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
