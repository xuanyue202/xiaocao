#!/usr/bin/env python3
"""Fetch full date_kline history (2021+) for the big-cap universe — for the real
STOCK-LEVEL cross-cycle trend test (the concept panel serves no historical returns).

date_kline serves ~2021-02 onward (incl. the 2022 bear + Jan-Feb 2024 crash), so
this gives genuine cross-cycle stock prices. Rate-limited + cache-first: each
code's full series is one cached call; re-runs skip cached codes.

Usage: python3 scripts/backfill_bigcap_history.py [--top 500] [--count 1300] [--sleep 0.7]
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


def top_bigcaps(n: int) -> list[str]:
    info = None
    for data in iter_cached_responses(str(DB), "/stock/stock_info"):
        if isinstance(data, list):
            info = data
            break
    rows = []
    for r in info or []:
        if isinstance(r, dict) and r.get("statusType") == 1:
            c, s = r.get("code"), r.get("tradableAShare")
            if c and isinstance(s, (int, float)) and s > 0:
                rows.append((float(s), c))
    rows.sort(reverse=True)
    return [c for _, c in rows[:n]]


def have_deep_history(code: str, before: str = "2022-06-01") -> bool:
    """Already cached a long series for this code (a bar earlier than `before`)?"""
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if data[0].get("code") == code:
                ds = [b.get("tradeDate") for b in data if isinstance(b, dict)]
                if ds and min(ds) < before:
                    return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--count", type=int, default=1300)
    ap.add_argument("--sleep", type=float, default=0.7)
    # date_kline only PERSISTS when paramTime is a past date (is_historical); with
    # param_time="" it is treated as volatile/latest and fetched-but-not-cached.
    ap.add_argument("--param-time", default="2026-06-18", help="past trade date so the response caches")
    a = ap.parse_args()

    s = load_settings(None)
    client = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                           cache=SQLiteCache(DB))
    codes = top_bigcaps(a.top)
    print(f"big-cap universe (top {a.top} by tradableAShare): {len(codes)} codes", flush=True)
    ok = empty = fail = 0
    for i, code in enumerate(codes, 1):
        try:
            bars = client.date_kline(code, count=a.count, adj="qfq", param_time=a.param_time)
            if isinstance(bars, list) and bars:
                ok += 1
            else:
                empty += 1
        except Exception as e:
            fail += 1
            print(f"  {code}: ERR {e}", file=sys.stderr, flush=True)
        if i % 50 == 0:
            print(f"  ...{i}/{len(codes)} (ok={ok} empty={empty} fail={fail}) last={code}", flush=True)
        time.sleep(a.sleep)
    print(f"done: {ok} fetched, {empty} empty, {fail} failed of {len(codes)}", flush=True)


if __name__ == "__main__":
    main()
