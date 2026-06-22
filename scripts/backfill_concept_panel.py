#!/usr/bin/env python3
"""Backfill the concept-rank panel (block_category_rank_v3) to cover prior cycles.

The cache held only 2025-01→2026-05 (a bull stretch). The API serves concept
ranks back to ~2023 (2022 is empty) and per-stock date_kline back to 2021 — which
includes real drawdowns (the Jan-Feb 2024 small-cap crash, 2023 H2 weakness). This
backfills the concept panel over the missing range so the trend book can finally
be tested CROSS-CYCLE with the same mainline_signal + trend_guards machinery.

Rate-limited + cache-first by construction (the client reads cache before the API,
and a sleep spaces network calls — see CLAUDE.md "Calling the xiaocao data API").
Idempotent: already-cached dates return instantly.

Usage: python3 scripts/backfill_concept_panel.py [--from 2023-01-01] [--to 2025-01-02]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


def trading_dates(client) -> list[str]:
    """Trading calendar from a single fresh date_kline call on a long-lived blue-chip
    (cache-first; the broad-universe cache only covers 2025-05+, so fetch the spine)."""
    dates: set[str] = set()
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list):
            for b in data:
                if isinstance(b, dict) and b.get("tradeDate"):
                    dates.add(b["tradeDate"])
    if len([d for d in dates if d < "2025-01-01"]) < 100:  # pre-2025 calendar missing -> fetch it
        bars = client.date_kline("600519.XSHG", count=1500, adj="qfq")
        if isinstance(bars, list):
            for b in bars:
                if isinstance(b, dict) and b.get("tradeDate"):
                    dates.add(b["tradeDate"])
    return sorted(dates)


def already_have() -> set[str]:
    """Dates for which block_category_rank_v3 (model=0) is already cached."""
    import json
    have: set[str] = set()
    for pj, _ in iter_cached_responses(str(DB), "/stock/xiao_cao_block_category_rank_v3", include_params=True):
        try:
            p = json.loads(pj).get("params", {})
            if p.get("model") == 0 and p.get("date"):
                have.add(p["date"])
        except Exception:
            pass
    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", default="2023-01-01")
    ap.add_argument("--to", dest="hi", default="2025-01-02")
    ap.add_argument("--sleep", type=float, default=1.2)
    a = ap.parse_args()

    s = load_settings(None)
    client = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                           cache=SQLiteCache(DB))
    cal = [d for d in trading_dates(client) if a.lo <= d <= a.hi]
    have = already_have()
    todo = [d for d in cal if d not in have]
    print(f"trading dates in [{a.lo},{a.hi}] known from cache: {len(cal)}; "
          f"already have concept ranks: {len([d for d in cal if d in have])}; to fetch: {len(todo)}",
          flush=True)
    ok = empty = 0
    for i, d in enumerate(todo, 1):
        try:
            r = client.get_block_category_rank_v3(d, model=0)
            lst = (r.get("localCategoryRankList") or r.get("globalCategoryRankList")) if isinstance(r, dict) else None
            n = len(lst) if isinstance(lst, list) else 0
            if n:
                ok += 1
            else:
                empty += 1
        except Exception as e:
            empty += 1
            print(f"  {d}: ERR {e}", file=sys.stderr, flush=True)
        if i % 25 == 0:
            print(f"  ...{i}/{len(todo)} (ok={ok} empty={empty}) last={d}", flush=True)
        time.sleep(a.sleep)
    print(f"done: fetched {len(todo)} dates -> ok(non-empty)={ok}, empty={empty}", flush=True)


if __name__ == "__main__":
    main()
