"""Big-cap pool helper.

小草 0412 / 0413-A / 0419 反复强调：

    大票要单独排名，不要和小票混在一起评分。

The "big-cap" cohort is a static-per-backtest set of stockIds chosen by ranking
all `type=1` rows from `XiaocaoClient.stock_info()` by `tradableAShare` and
taking the top `top_pct` (default 20%). `tradableAShare` is share count, not
market cap; we use it as a proxy because it is monotonic with float market cap
for blue-chip identification, doesn't require live prices, and is stable enough
to compute once per backtest.

Pure function — caller passes already-fetched stock_info rows.
"""
from __future__ import annotations

from typing import Any, Iterable


def bigcap_codes(
    stock_info_rows: Iterable[dict[str, Any]],
    *,
    top_pct: float = 0.2,
    min_shares: int | None = None,
) -> set[str]:
    """Return the set of stockIds that count as 大票.

    Args:
        stock_info_rows: rows from XiaocaoClient.stock_info(); only entries with
            `type == 1` (普通股) are considered.
        top_pct: top percentile by tradableAShare (e.g. 0.2 = top 20%).
        min_shares: if set, an absolute floor (number of shares) overrides
            the percentile calculation when stricter.

    Returns:
        set of stockId strings (e.g. "300750.XSHE").
    """
    if not 0.0 < top_pct <= 1.0:
        raise ValueError(f"top_pct must be in (0, 1], got {top_pct}")

    candidates: list[tuple[int, str]] = []
    for row in stock_info_rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("type") != 1:
            continue
        shares = row.get("tradableAShare")
        sid = row.get("stockId") or row.get("code")
        if not sid or not isinstance(shares, (int, float)):
            continue
        s = int(shares)
        if s <= 0:
            continue
        candidates.append((s, str(sid)))

    if not candidates:
        return set()

    candidates.sort(key=lambda t: t[0], reverse=True)
    cutoff = max(1, int(len(candidates) * top_pct))
    chosen = candidates[:cutoff]
    if min_shares is not None:
        chosen = [(s, sid) for s, sid in chosen if s >= min_shares]
    return {sid for _, sid in chosen}


def is_bigcap(stock_id: str | None, bigcap_set: set[str]) -> bool:
    if not stock_id:
        return False
    return stock_id in bigcap_set


def split_by_bigcap(
    rows: Iterable[dict[str, Any]],
    bigcap_set: set[str],
    code_field: str = "code",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition rows into (big-caps, others). Order within each preserved."""
    big: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sid = row.get(code_field) or row.get("stockId") or row.get("stockCode")
        if sid and str(sid) in bigcap_set:
            big.append(row)
        else:
            other.append(row)
    return big, other
