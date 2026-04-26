"""Rolling main-line tracker.

小草 0413-A / 0413-B / 0419 反复强调一句话：

    主线的特征是反复出现 — 同一批方向连续多天进 top-K 才算主线。

This module turns a series of daily block_rank arrays into a `set` of
"sticky" block codes that have appeared in the top-K of at least `min_hits`
days within the trailing window. Pure function.

Inputs are expected to be the rows returned by
`XiaocaoClient.get_industry_block_rank(date, model)`. Each row should at
minimum carry `blockCode` and `num` (the strength score the rows are sorted
by). We sort defensively in case the upstream order is not reliable.
"""
from __future__ import annotations

from typing import Any


def _block_code(row: dict[str, Any]) -> str | None:
    return row.get("blockCode") or row.get("code") or row.get("category_code")


def _strength(row: dict[str, Any]) -> float:
    for key in ("num", "value", "score", "trendScore"):
        v = row.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def top_k_block_codes(rank_rows: list[dict[str, Any]], topk: int) -> list[str]:
    if not rank_rows:
        return []
    sortable: list[tuple[float, str]] = []
    for row in rank_rows:
        if not isinstance(row, dict):
            continue
        code = _block_code(row)
        if not code:
            continue
        sortable.append((_strength(row), str(code)))
    sortable.sort(key=lambda t: t[0], reverse=True)
    return [code for _, code in sortable[:topk]]


def compute_mainline(
    rank_history: list[list[dict[str, Any]]],
    *,
    window: int = 3,
    topk: int = 5,
    min_hits: int | None = None,
) -> set[str]:
    """Identify main-line blocks from a sequence of daily rank snapshots.

    Args:
        rank_history: list of daily rank-row arrays, oldest first. We only
            consume the trailing `window` entries.
        window: how many trailing days to consider.
        topk: top-K cutoff per day.
        min_hits: minimum number of days within the window the block must
            appear in top-K. Defaults to `window` (must appear every day) when
            unset, which is the strictest 小草-style "老面孔" definition.

    Returns:
        set of block codes considered main-line.
    """
    if not rank_history:
        return set()
    trailing = rank_history[-window:]
    if min_hits is None:
        # Default: require the block to be present on every day of the window.
        # When window=3 this means appearing in top-K each of the last 3 days.
        min_hits = max(1, window)
    counts: dict[str, int] = {}
    for day in trailing:
        for code in top_k_block_codes(day, topk):
            counts[code] = counts.get(code, 0) + 1
    return {code for code, c in counts.items() if c >= min_hits}


def block_strength_avg(
    rank_history: list[list[dict[str, Any]]],
    block_code: str,
    *,
    window: int = 3,
) -> float:
    """Average `num` strength of a given block over the trailing `window` days.

    Useful for ranking main-line blocks against each other (中军 vs 补涨 vs 后排).
    Days where the block does not appear are skipped (averaged over present-days).
    """
    trailing = rank_history[-window:]
    values: list[float] = []
    for day in trailing:
        for row in day or []:
            if isinstance(row, dict) and _block_code(row) == block_code:
                values.append(_strength(row))
                break
    if not values:
        return 0.0
    return sum(values) / len(values)
