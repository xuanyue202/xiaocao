#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.run_flow import (  # noqa: E402
    build_snapshot,
    events_from_log,
    supporting_health_from_live,
    upsert_snapshot_event,
    write_snapshot,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build structured run-flow diagnostics from an automation log.")
    ap.add_argument("--automation", required=True, help="morning/eod/weekly")
    ap.add_argument("--date", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--exit-code", type=int, default=0)
    ap.add_argument("--live-dir", default=str(ROOT / "output" / "live"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    live_dir = Path(args.live_dir)
    log_path = Path(args.log)
    events = events_from_log(automation=args.automation, market_date=args.date, log_path=log_path)
    supporting_health = supporting_health_from_live(live_dir=live_dir, market_date=args.date)
    snapshot = build_snapshot(
        automation=args.automation,
        market_date=args.date,
        events=events,
        exit_code=args.exit_code,
        supporting_health=supporting_health,
    )
    out = Path(args.output) if args.output else live_dir / f"run_flow_{args.date}_{args.automation}.json"
    write_snapshot(out, snapshot)
    upsert_snapshot_event(live_dir / "run_flow.jsonl", snapshot, snapshot_path=out)
    print(f"run_flow -> {out} status={snapshot['status']} steps={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
