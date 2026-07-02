"""Backfill cached minute bars for raw-qibao research cohorts.

The regular intraday backfill script reads backtest trades.  This one builds
targets from the governed cohort definitions so fill-aware research can validate
high-open / limit-like benchmark samples without fetching the whole qibao pool.

Default is dry-run. Use --execute to call the API. Calls are deliberately
single-threaded with a sleep because the Xiaocao API silently throttles bursts.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from research_raw_qibao_rank import (  # noqa: E402
    _code,
    _date,
    _num,
    load_index_by_date,
    load_qibao_pool_by_date,
)
from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.research.cohorts import (  # noqa: E402
    QIBAO_BUYABLE_BENCHMARK,
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
    classify_qibao_raw_cohorts,
)


CACHE_PATH = ROOT / "output" / ".cache" / "xiaocao.db"
OUT_DIR = ROOT / "output" / "research"
DEFAULT_COHORTS = [
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
]
ALL_COHORTS = [
    QIBAO_BUYABLE_BENCHMARK,
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
]


def _has_count(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def load_cached_minute_keys(cache_path: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for params_json, data in iter_cached_responses(cache_path, "/stock/minute_line", include_params=True):
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        if not _has_count(params.get("count")):
            continue
        code = str(params.get("code") or "")
        day = _date(params.get("tradeDate"))
        if not code or not day:
            continue
        rows = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else None
        if isinstance(rows, list) and rows:
            keys.add((day, code))
    return keys


def _next_trade_day(day: str, trade_days: list[str]) -> str | None:
    try:
        idx = trade_days.index(day)
    except ValueError:
        return None
    if idx + 1 >= len(trade_days):
        return None
    return trade_days[idx + 1]


def build_targets(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cohorts = set(args.cohorts.split(",") if isinstance(args.cohorts, str) else args.cohorts)
    qibao_pool = load_qibao_pool_by_date(args.cache)
    index_by_date = load_index_by_date(args.cache)
    have = load_cached_minute_keys(args.cache)
    trade_days = sorted(set(qibao_pool) | {d for d, _ in have})
    selected_counts: dict[str, int] = {cohort: 0 for cohort in cohorts}
    target_map: dict[tuple[str, str], dict[str, Any]] = {}

    for day in sorted(d for d in qibao_pool if args.start <= d <= args.end):
        sell_day = _next_trade_day(day, trade_days)
        by_code = index_by_date.get(day) or {}
        details = [by_code[c] for c in qibao_pool.get(day, []) if c in by_code]
        details.sort(key=lambda row: _num(row.get("jssb")), reverse=True)
        for rank, row in enumerate(details, start=1):
            row_cohorts = [cohort for cohort in classify_qibao_raw_cohorts(row, rank) if cohort in cohorts]
            if not row_cohorts:
                continue
            code = _code(row)
            for cohort in row_cohorts:
                selected_counts[cohort] += 1
            for target_day, side in ((day, "buy"), (sell_day, "sell")):
                if not target_day or target_day > args.max_trade_date:
                    continue
                if (target_day, code) in have:
                    continue
                key = (target_day, code)
                existing = target_map.setdefault(
                    key,
                    {
                        "date": target_day,
                        "code": code,
                        "source_day": day,
                        "side": side,
                        "cohorts": set(),
                        "raw_rank": rank,
                    },
                )
                existing["cohorts"].update(row_cohorts)
                if side == "buy":
                    existing["source_day"] = day
                    existing["raw_rank"] = rank

    targets: list[dict[str, Any]] = []
    for item in target_map.values():
        item["cohorts"] = sorted(item["cohorts"])
        targets.append(item)
    targets.sort(key=lambda row: (row["date"], row["code"]))
    summary = {
        "start": args.start,
        "end": args.end,
        "max_trade_date": args.max_trade_date,
        "cohorts": sorted(cohorts),
        "selected_counts": selected_counts,
        "cached_minute_code_days": len(have),
        "missing_targets": len(targets),
    }
    return targets, summary


def write_targets(targets: list[dict[str, Any]], summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"summary": summary}, ensure_ascii=False, sort_keys=True) + "\n")
        for row in targets:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-07-01")
    ap.add_argument("--end", default="2026-06-28", help="latest signal day; default avoids live-day sell cache")
    ap.add_argument("--max-trade-date", default="2026-06-29", help="latest minute tradeDate to fetch")
    ap.add_argument("--cohorts", default=",".join(DEFAULT_COHORTS), help=f"comma-list; choices include {','.join(ALL_COHORTS)}")
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--target-out", type=Path, default=OUT_DIR / "qibao_cohort_minute_targets.jsonl")
    ap.add_argument("--count", type=int, default=241)
    ap.add_argument("--sleep", type=float, default=0.75)
    ap.add_argument("--max-requests", type=int, default=0, help="0 means no cap")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    targets, summary = build_targets(args)
    write_targets(targets, summary, args.target_out)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"target list: {args.target_out}")
    if not args.execute:
        print("dry-run only; pass --execute to backfill")
        return

    settings = load_settings(None)
    cache = SQLiteCache(args.cache)
    client = XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=cache,
    )
    todo = targets[: args.max_requests] if args.max_requests and args.max_requests > 0 else targets
    success = 0
    empty = 0
    failed = 0
    started = time.time()
    for idx, row in enumerate(todo, start=1):
        date = row["date"]
        code = row["code"]
        try:
            result = client.minute_line(code, "1min", "bfq", date, args.count, 0)
            if isinstance(result, list) and result:
                success += 1
            else:
                empty += 1
        except Exception as exc:
            failed += 1
            print(f"fail {date} {code}: {exc}")
        if idx % 25 == 0 or idx == len(todo):
            elapsed = time.time() - started
            print(f"{idx}/{len(todo)} ok={success} empty={empty} failed={failed} elapsed={elapsed:.1f}s")
        if idx < len(todo) and args.sleep > 0:
            time.sleep(args.sleep)
    print(f"done: ok={success} empty={empty} failed={failed}")


if __name__ == "__main__":
    main()
