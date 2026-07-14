#!/usr/bin/env python3
"""Bounded rendezvous for the morning agent-review producer.

This script never scores evidence.  It only gives the Codex automation agent a
short window to consume the frozen review queue with
``agent_intelligence_review.py``.  Timeout is a normal base-pick fallback.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def review_progress(queue_path: Path, history_path: Path) -> dict[str, Any]:
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        queue = {}
    market_date = str(queue.get("market_date") or "")[:10]
    selected_codes = {
        str(item.get("code") or "")
        for item in (queue.get("items") or [])
        if item.get("code")
    }
    reviewed_codes = sorted({
        str(row.get("code") or "")
        for row in _read_jsonl(history_path)
        if str(row.get("date") or "")[:10] == market_date
        and str(row.get("score_source") or "") == "agent_review"
        and str(row.get("code") or "") in selected_codes
    })
    return {
        "selected": len(selected_codes),
        "reviewed": len(reviewed_codes),
        "pending": max(0, len(selected_codes) - len(reviewed_codes)),
        "reviewed_codes": reviewed_codes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--live-dir", default="output/live")
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument("--poll-sec", type=float, default=2.0)
    parser.add_argument("--min-reviews", type=int, default=0, help="0 means wait for every selected item")
    args = parser.parse_args()
    live = Path(args.live_dir)
    queue = live / f"intelligence_review_queue_{args.date[:10]}.json"
    history = live / "stock_sentiment_history.jsonl"
    deadline = time.monotonic() + max(0.0, args.timeout_sec)
    progress = review_progress(queue, history)
    target = args.min_reviews if args.min_reviews > 0 else progress["selected"]
    while progress["reviewed"] < target and time.monotonic() < deadline:
        time.sleep(min(max(0.05, args.poll_sec), max(0.0, deadline - time.monotonic())))
        progress = review_progress(queue, history)
    progress["status"] = "reviewed" if progress["reviewed"] >= target else "fallback_timeout"
    progress["authority"] = "shadow_only"
    print(json.dumps(progress, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
