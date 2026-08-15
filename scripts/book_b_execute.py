#!/usr/bin/env python3
"""Advance frozen Book B intents through the broker-neutral execution seam.

The default environment is ``mock`` and the bundled Founder adapter currently
has no submit capability.  This command is therefore a safe probe/readback
entrypoint; it does not replace ``auto_daily.sh`` or activate real capital.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.trading_runner import (  # noqa: E402
    build_foundersc_execution,
    execute_plans,
    plans_from_frozen_rows,
    read_frozen_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--freeze",
        default="output/live/signal_snapshots.jsonl",
        help="JSONL freeze containing already-selected Book B rows",
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD freeze date")
    parser.add_argument("--environment", choices=("mock", "live"), default="mock")
    parser.add_argument("--logical-account-id", default="primary")
    parser.add_argument("--strategy-sha", default="unknown")
    parser.add_argument("--state-dir", default="output/live/book_b_execution")
    parser.add_argument("--profile", default=None, help="OpenCLI profile; no credentials are read")
    parser.add_argument(
        "--route",
        choices=("manual-limit", "opening-auction", "timed-order"),
        default="manual-limit",
    )
    parser.add_argument("--side", choices=("BUY", "SELL"), default="BUY")
    args = parser.parse_args()

    rows = read_frozen_rows(args.freeze, date=args.date)
    if args.side == "BUY":
        # The freeze contains the full candidate surface.  Only the existing
        # deterministic ★E/eligible rows are executable; silently keeping the
        # rest out of the intent set mirrors paper_record --pick mode_exec_star
        # and prevents a non-selected row from aborting the whole batch.
        rows = [
            row for row in rows
            if row.get("mode_exec_star") is True
            and row.get("mode_trade_eligible") is True
            and row.get("executable_fillable", True) is not False
            and (args.environment != "live" or row.get("is_live") is True)
        ]
    if not rows:
        print(json.dumps({"status": "no_rows", "date": args.date}, ensure_ascii=False))
        return 0
    plans = plans_from_frozen_rows(
        rows,
        environment=args.environment,
        logical_account_id=args.logical_account_id,
        strategy_sha=args.strategy_sha,
        side=args.side,
    )
    execution, _broker = build_foundersc_execution(
        args.state_dir,
        profile=args.profile,
        route=args.route,
    )
    receipts = execute_plans(plans, execution=execution)
    for receipt in receipts:
        print(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
