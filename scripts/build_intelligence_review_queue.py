#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.intelligence_review_queue import build_review_queue, write_review_queue  # noqa: E402


def _strategy_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("producer strategy Git SHA unavailable") from exc
    value = result.stdout.strip().lower()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        raise RuntimeError("producer strategy Git SHA unavailable")
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a zero-fetch queue for fast agent intelligence review.")
    ap.add_argument("--date", default="today")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--live-dir", default=str(ROOT / "output" / "live"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    market_date = date.today().isoformat() if args.date == "today" else args.date[:10]
    live_dir = Path(args.live_dir)
    queue = build_review_queue(
        live_dir=live_dir,
        market_date=market_date,
        limit=args.limit,
        strategy_sha=_strategy_sha(),
    )
    out = Path(args.output) if args.output else live_dir / f"intelligence_review_queue_{market_date}.json"
    write_review_queue(out, queue)
    counts = queue.get("counts") if isinstance(queue.get("counts"), dict) else {}
    print(
        f"intelligence_review_queue -> {out} status={queue.get('status')} "
        f"selected={counts.get('selected_items', 0)} pending={counts.get('pending_items', 0)} "
        f"evidence={counts.get('evidence_rows', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
