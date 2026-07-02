#!/usr/bin/env python3
"""Capture benchmark/watchlist cohort snapshots.

Snapshots are audit/research surfaces only. They do not feed paper trading or
the deterministic strategy spine.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.datasource.api_source import ApiDataSource  # noqa: E402
from xiaocao.research.cohorts import (  # noqa: E402
    QIBAO_COHORTS,
    classify_qibao_raw_cohorts,
    code_of,
    num,
    qibao_snapshot_record,
)
from xiaocao.utils.trading_session import A_SHARE_TZ  # noqa: E402


DEFAULT_OUT = ROOT / "output" / "cohorts" / "cohort_snapshots.jsonl"


def _today_iso() -> str:
    from datetime import datetime

    return datetime.now(A_SHARE_TZ).date().isoformat()


def _source() -> ApiDataSource:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    client = XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=cache,
    )
    return ApiDataSource(client, hpqb_state=0, lpdx_state=0)


def qibao_snapshot(date: str) -> list[dict[str, Any]]:
    source = _source()
    codes = source.get_pool(date, "qibao")
    sorted_codes = source.sort_codes(date, codes, "xiaocaoJSSB")
    details = source.get_stock_index(date, sorted_codes)
    by_code = {code_of(row): row for row in details if isinstance(row, dict) and code_of(row)}
    rows = [by_code[code] for code in sorted_codes if code in by_code]
    # Preserve backend sort order, but guard against unsorted cache/API rows.
    rows.sort(key=lambda row: num(row.get("jssb")), reverse=True)
    out: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        if rank > 10:
            break
        for cohort_id in classify_qibao_raw_cohorts(row, rank):
            out.append(qibao_snapshot_record(date, row, rank, cohort_id))
    return out


def _replace_snapshot(path: Path, date: str, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("date") != date:
                kept.append(row)
    with path.open("w", encoding="utf-8") as fh:
        for row in kept + records:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=_today_iso(), help="trade date, YYYY-MM-DD")
    ap.add_argument("--cohort", default="qibao_raw", choices=["qibao_raw"], help="cohort family")
    ap.add_argument("--output", default=str(DEFAULT_OUT), help="jsonl snapshot path")
    ap.add_argument("--replace", action="store_true", default=True, help="replace existing rows for the date")
    args = ap.parse_args()

    if args.cohort != "qibao_raw":
        raise SystemExit(f"unsupported cohort family: {args.cohort}")
    records = qibao_snapshot(args.date)
    path = Path(args.output)
    if args.replace:
        _replace_snapshot(path, args.date, records)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for row in records:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    counts = Counter(row["cohort_id"] for row in records)
    print(f"wrote {len(records)} rows -> {path}")
    for cohort_id, definition in QIBAO_COHORTS.items():
        print(f"{cohort_id}: {counts.get(cohort_id, 0)} ({definition.layer}, authority={definition.authority})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
