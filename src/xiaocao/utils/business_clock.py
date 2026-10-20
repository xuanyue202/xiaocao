"""Absolute China-market start gates, independent of scheduler wake jitter."""
from __future__ import annotations

from datetime import datetime, time
from typing import Callable
import time as clock

from .trading_session import A_SHARE_TZ


def wait_for_business_time(
    market_date: str,
    target: time,
    *,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> float:
    """Wait in bounded chunks; historical replay has no wall-clock delay.

    A rollover while waiting invalidates the dated owner rather than letting
    yesterday's business proceed on a new session.
    """
    now = now or (lambda: datetime.now(A_SHARE_TZ))
    sleep = sleep or clock.sleep
    current = now().astimezone(A_SHARE_TZ)
    if current.date().isoformat() != market_date[:10]:
        return 0.0
    deadline = datetime.combine(current.date(), target, tzinfo=A_SHARE_TZ)
    waited = 0.0
    while current < deadline:
        seconds = min(60.0, (deadline - current).total_seconds())
        sleep(seconds)
        waited += seconds
        current = now().astimezone(A_SHARE_TZ)
        if current.date() != deadline.date():
            raise RuntimeError("BUSINESS_WAIT_SESSION_CHANGED")
    return waited
