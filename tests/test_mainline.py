from __future__ import annotations

from xiaocao.strategy.mainline import (
    block_strength_avg,
    compute_mainline,
    top_k_block_codes,
)


def _row(code: str, num: float) -> dict:
    return {"blockCode": code, "blockName": code, "num": num}


def test_top_k_returns_sorted_top_k_codes():
    rows = [_row("A", 10), _row("B", 50), _row("C", 30), _row("D", 5)]
    assert top_k_block_codes(rows, topk=2) == ["B", "C"]


def test_top_k_handles_unsorted_and_missing_codes():
    rows = [{"foo": 1}, _row("X", 1), _row("Y", 100), _row("Z", 50)]
    assert top_k_block_codes(rows, topk=2) == ["Y", "Z"]


def test_compute_mainline_strict_requires_every_day():
    history = [
        [_row("A", 10), _row("B", 9), _row("C", 8)],  # day 1
        [_row("A", 11), _row("B", 9), _row("D", 8)],  # day 2  — C drops, D enters
        [_row("A", 12), _row("B", 9), _row("E", 8)],  # day 3  — D drops, E enters
    ]
    # window=3 topk=3, default min_hits=3 → only A and B persist all three days
    out = compute_mainline(history, window=3, topk=3)
    assert out == {"A", "B"}


def test_compute_mainline_relaxed_min_hits():
    history = [
        [_row("A", 10), _row("B", 9)],  # day 1
        [_row("A", 11), _row("C", 8)],  # day 2
        [_row("B", 7), _row("D", 6)],   # day 3
    ]
    out = compute_mainline(history, window=3, topk=2, min_hits=2)
    assert out == {"A", "B"}


def test_compute_mainline_window_clipping():
    # window=2 should ignore the oldest day even if min_hits=2
    history = [
        [_row("OLD", 10)],
        [_row("A", 10)],
        [_row("A", 10)],
    ]
    out = compute_mainline(history, window=2, topk=1, min_hits=2)
    assert out == {"A"}


def test_compute_mainline_empty_history():
    assert compute_mainline([]) == set()


def test_block_strength_avg_skips_missing_days():
    history = [
        [_row("A", 10), _row("B", 5)],
        [_row("B", 6)],  # A absent
        [_row("A", 14), _row("B", 7)],
    ]
    # A is present on day 1 (10) and day 3 (14) → avg = 12
    assert block_strength_avg(history, "A", window=3) == 12.0
    # Block never present → 0.0
    assert block_strength_avg(history, "Z", window=3) == 0.0
