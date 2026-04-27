"""Backfill 1min historical K-line for every (buyDate, code) in a backtest output.

Use case: Phase C R2/R3/R4 SOPs need per-stock 9:30-9:50 minute data on the
actual trade dates. /stock/minute_line supports historical when called with
{tradeDate, count} — caches into output/.cache/xiaocao.db like every other
endpoint, so subsequent runs are read-only.

Usage:
  python3 scripts/backfill_intraday_minute.py [--source DIR] [--workers 6]

  --source DIR: output dir of a backtest run; default xiaocao_8mo_v3_baseline
                Reads `trades.csv` for the (buyDate, code) targets.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

DEFAULT_SOURCE = ROOT / "output" / "xiaocao_8mo_v3_baseline"
DEFAULT_COUNT = 241  # 9:30-15:00 inclusive at 1min freq


def load_targets(trades_csv: Path) -> list[tuple[str, str]]:
    """Return list of (buyDate, code) — dedup."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    with trades_csv.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = row.get("buyDate")
            c = row.get("code")
            if d and c and (d, c) not in seen:
                seen.add((d, c))
                out.append((d, c))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="backtest output dir to read trades.csv from")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--include-shadow", action="store_true",
                        help="include shadow trades (default: only active)")
    args = parser.parse_args()

    source_dir = Path(args.source)
    trades_csv = source_dir / "trades.csv"
    if not trades_csv.exists():
        sys.exit(f"trades.csv not found at {trades_csv}")

    targets = load_targets(trades_csv)
    if not args.include_shadow:
        # Filter to active-only (adaptiveActive=True or empty)
        active_pairs: set[tuple[str, str]] = set()
        with trades_csv.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                aa = row.get("adaptiveActive", "").strip().lower()
                if aa in ("true", ""):
                    active_pairs.add((row["buyDate"], row["code"]))
        targets = [t for t in targets if t in active_pairs]

    print(f"Targets: {len(targets)} (date, code) pairs")
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    client = XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )

    # Fetch in parallel
    success = 0
    failure = 0
    empty = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(client.minute_line, code, "1min", "bfq", date, args.count, 0): (date, code)
            for date, code in targets
        }
        for fut in as_completed(futures):
            date, code = futures[fut]
            try:
                r = fut.result()
                if isinstance(r, list) and r:
                    success += 1
                else:
                    empty += 1
            except Exception:
                failure += 1
            done = success + failure + empty
            if done % 25 == 0:
                elapsed = time.time() - t0
                rate = done / max(elapsed, 0.01)
                print(f"  {done}/{len(targets)} ({rate:.1f}/s, {failure} fail, {empty} empty)")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s: {success} ok, {empty} empty, {failure} failed")
    print("Cached responses are now readable via xiaocao.api.cache.iter_cached_responses().")


if __name__ == "__main__":
    main()
