from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from xiaocao.live.closing_startup import (
    closing_prearm_wait_seconds,
    wait_for_closing_window,
)


CHINA = ZoneInfo("Asia/Shanghai")


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (datetime(2026, 10, 8, 14, 40, 0, tzinfo=CHINA), 300.0),
        (datetime(2026, 10, 8, 14, 40, 8, 259390, tzinfo=CHINA), 291.74061),
        (datetime(2026, 10, 8, 14, 39, 59, tzinfo=CHINA), 0.0),
        (datetime(2026, 9, 17, 14, 41, 0, tzinfo=CHINA), 240.0),
        (datetime(2026, 9, 17, 14, 42, 31, tzinfo=CHINA), 149.0),
        (datetime(2026, 9, 17, 14, 44, 0, tzinfo=CHINA), 60.0),
        (datetime(2026, 9, 17, 14, 44, 23, 500_000, tzinfo=CHINA), 36.5),
        (datetime(2026, 9, 17, 14, 44, 59, 900_000, tzinfo=CHINA), 0.1),
        (datetime(2026, 9, 17, 14, 40, 59, tzinfo=CHINA), 241.0),
        (datetime(2026, 9, 17, 14, 45, 0, tzinfo=CHINA), 0.0),
        (datetime(2026, 9, 17, 14, 57, 0, tzinfo=CHINA), 0.0),
    ],
)
def test_closing_prearm_wait_is_bounded_to_prearm_span(
    current: datetime,
    expected: float,
) -> None:
    assert closing_prearm_wait_seconds(current) == pytest.approx(expected)


def test_wait_for_closing_window_applies_computed_delay() -> None:
    sleeps: list[float] = []
    current = datetime(2026, 9, 17, 14, 42, 40, tzinfo=CHINA)

    waited = wait_for_closing_window(now=lambda: current, sleep=sleeps.append)

    assert waited == 140.0
    assert sleeps == [60.0, 60.0, 20.0]


def test_wait_for_closing_window_does_not_delay_late_run() -> None:
    sleeps: list[float] = []
    current = datetime(2026, 9, 17, 14, 56, 30, tzinfo=CHINA)

    waited = wait_for_closing_window(now=lambda: current, sleep=sleeps.append)

    assert waited == 0.0
    assert sleeps == []


def test_observed_early_dispatch_reaches_legal_close_before_business() -> None:
    current = datetime(2026, 10, 8, 14, 40, 8, 259390, tzinfo=CHINA)
    sleeps: list[float] = []

    def advance(seconds: float) -> None:
        nonlocal current
        sleeps.append(seconds)
        current += timedelta(seconds=seconds)

    waited = wait_for_closing_window(now=lambda: current, sleep=advance)

    assert waited == pytest.approx(291.74061)
    assert current == datetime(2026, 10, 8, 14, 45, tzinfo=CHINA)
    assert all(0 < seconds <= 60 for seconds in sleeps)
