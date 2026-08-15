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
from xiaocao.live.book_b_allocation import BookBAllocationFacts  # noqa: E402


def _allocation_facts(args: argparse.Namespace) -> BookBAllocationFacts:
    if args.allocation_facts:
        payload = json.loads(Path(args.allocation_facts).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("allocation facts must be a JSON object")
        facts = BookBAllocationFacts.from_dict(payload)
        if args.environment == "live" and facts.source == "mock_initial":
            raise ValueError("live allocation facts cannot use mock_initial source")
        return facts
    if args.environment == "live":
        raise ValueError("live execution requires authoritative --allocation-facts")
    return BookBAllocationFacts(
        settled_nav=args.settled_nav,
        available_cash=args.available_cash,
        current_open_exposure=args.current_open_exposure,
        deploy_factor=args.deploy_factor,
        fee_rate=args.fee_rate,
        source="mock_initial",
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
    parser.add_argument(
        "--allocation-facts",
        default=None,
        help="JSON object with rolling settled NAV/cash/exposure facts (required for live)",
    )
    parser.add_argument("--settled-nav", type=float, default=30000.0)
    parser.add_argument("--available-cash", type=float, default=30000.0)
    parser.add_argument("--current-open-exposure", type=float, default=0.0)
    parser.add_argument("--deploy-factor", type=float, default=1.0)
    parser.add_argument("--fee-rate", type=float, default=0.0001)
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
    else:
        original_count = len(rows)
        rows = [
            row for row in rows
            if row.get("book", "B") == "B"
            and row.get("owned_lot_id")
            and row.get("t1_blocked") is not True
            and not any(row.get(key) for key in ("sell_block_reason", "sell_blocked_reason", "liquidity_block_reason"))
            and (
                row.get("sell_authorized") is True
                or (row.get("alert") == "SELL_TRIGGERED" and row.get("triggered") is True)
            )
        ]
        if original_count and not rows:
            print(json.dumps({"status": "no_authorized_sell_rows", "date": args.date}, ensure_ascii=False))
            return 0
    if not rows:
        print(json.dumps({"status": "no_rows", "date": args.date}, ensure_ascii=False))
        return 0
    try:
        allocation = _allocation_facts(args) if args.side == "BUY" else None
        plans = plans_from_frozen_rows(
            rows,
            environment=args.environment,
            logical_account_id=args.logical_account_id,
            strategy_sha=args.strategy_sha,
            side=args.side,
            allocation=allocation,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, ensure_ascii=False))
        return 2
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
