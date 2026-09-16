from __future__ import annotations

from datetime import datetime
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
        (datetime(2026, 9, 17, 14, 54, 0, tzinfo=CHINA), 60.0),
        (datetime(2026, 9, 17, 14, 54, 23, 500_000, tzinfo=CHINA), 36.5),
        (datetime(2026, 9, 17, 14, 54, 59, 900_000, tzinfo=CHINA), 0.1),
        (datetime(2026, 9, 17, 14, 53, 59, tzinfo=CHINA), 0.0),
        (datetime(2026, 9, 17, 14, 55, 0, tzinfo=CHINA), 0.0),
        (datetime(2026, 9, 17, 14, 57, 0, tzinfo=CHINA), 0.0),
    ],
)
def test_closing_prearm_wait_is_bounded_to_1454(
    current: datetime,
    expected: float,
) -> None:
    assert closing_prearm_wait_seconds(current) == pytest.approx(expected)


def test_wait_for_closing_window_applies_computed_delay() -> None:
    sleeps: list[float] = []
    current = datetime(2026, 9, 17, 14, 54, 40, tzinfo=CHINA)

    waited = wait_for_closing_window(now=lambda: current, sleep=sleeps.append)

    assert waited == 20.0
    assert sleeps == [20.0]


def test_wait_for_closing_window_does_not_delay_late_run() -> None:
    sleeps: list[float] = []
    current = datetime(2026, 9, 17, 14, 56, 30, tzinfo=CHINA)

    waited = wait_for_closing_window(now=lambda: current, sleep=sleeps.append)

    assert waited == 0.0
    assert sleeps == []
