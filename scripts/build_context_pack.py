#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.context_pack import build_context_pack, write_context_pack  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a zero-fetch Xiaocao context pack from existing artifacts.")
    ap.add_argument("--date", default="today")
    ap.add_argument("--phase", default="snapshot", help="morning/eod/weekly/snapshot")
    ap.add_argument("--live-dir", default=str(ROOT / "output" / "live"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    market_date = args.date
    if market_date == "today":
        from datetime import date
        market_date = date.today().isoformat()
    live_dir = Path(args.live_dir)
    pack = build_context_pack(live_dir=live_dir, market_date=market_date, phase=args.phase)
    out = Path(args.output) if args.output else live_dir / f"context_pack_{market_date}_{args.phase}.json"
    write_context_pack(out, pack)
    print(f"context_pack -> {out} status ok={pack['data_health']['ok']} signals={pack['signals']['rows_for_date']} intelligence={pack['stock_intelligence']['rows_for_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
