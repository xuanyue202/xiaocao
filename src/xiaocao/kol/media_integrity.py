"""Finite-replay duration checks shared by capture and independent acceptance."""

from __future__ import annotations

import math
from typing import Any


def finite_duration_matches(actual: Any, expected: Any) -> bool:
    """Allow bounded mux/codec rounding, never a percentage of a long replay.

    HLS segment durations and MP4 codec boundaries can round differently. Two
    seconds is a fixed upper bound; a longer recording must not gain a larger
    allowance for missing media.
    """
    try:
        actual_seconds, expected_seconds = float(actual), float(expected)
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        math.isfinite(actual_seconds)
        and math.isfinite(expected_seconds)
        and min(actual_seconds, expected_seconds) >= 60
        and abs(actual_seconds - expected_seconds) <= 2.0
    )
