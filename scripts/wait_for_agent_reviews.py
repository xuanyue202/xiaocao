#!/usr/bin/env python3
"""Bounded rendezvous for the morning agent-review producer.

This script never scores evidence.  It only gives the Codex automation agent a
short window to consume the frozen review queue with
``agent_intelligence_review.py``.  Timeout is a normal base-pick fallback.
"""
from __future__ import annotations

import argparse
import json
import os
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


def review_progress(queue_path: Path, history_path: Path, *, expected_date: str | None = None,
                    expected_binding: dict | None = None) -> dict[str, Any]:
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        if (not isinstance(queue, dict) or not isinstance(queue.get("items"), list)
                or not queue.get("market_date") or any(not isinstance(item, dict) for item in queue["items"])):
            raise ValueError("queue_invalid")
        if expected_date is not None and str(queue["market_date"])[:10] != expected_date[:10]:
            raise ValueError("queue_market_date_mismatch")
        if expected_binding is not None:
            binding = queue.get("freeze_binding") or {}
            if (not isinstance(binding, dict) or queue.get("status") not in {"ready", "empty"}
                    or binding.get("snapshot_sha256") != expected_binding.get("snapshot_sha256")
                    or binding.get("strategy_sha") != expected_binding.get("strategy_sha")):
                raise ValueError("queue_batch_mismatch")
    except (OSError, ValueError) as exc:
        return {"selected": 0, "reviewed": 0, "pending": 0, "reviewed_codes": [],
            "status": "queue_missing" if isinstance(exc, FileNotFoundError) else "queue_invalid"}
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
        and (expected_binding is None or row.get("evidence_freeze_ref") ==
             f"morning-bundle:{expected_binding.get('checkpoint_sha256')}:{expected_binding.get('snapshot_sha256')}")
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
    parser.add_argument("--morning-freeze-receipt", type=Path)
    parser.add_argument("--kol-preparation", action="store_true", help="Original paper owner KOL support; requires original freeze")
    args = parser.parse_args()
    live = Path(args.live_dir)
    queue = live / f"intelligence_review_queue_{args.date[:10]}.json"
    history = live / "stock_sentiment_history.jsonl"
    deadline = time.monotonic() + max(0.0, args.timeout_sec)
    binding = None
    if args.morning_freeze_receipt:
        from xiaocao.live.morning_bundle import resolve_receipt
        binding = resolve_receipt(json.loads(args.morning_freeze_receipt.read_bytes()), args.date[:10], live_dir=live)
    kol = None
    if args.kol_preparation:
        if binding is None:
            parser.error("--kol-preparation requires --morning-freeze-receipt")
        from xiaocao.live.paper_morning_kol import PaperKolReview
        kol = PaperKolReview(Path(os.environ["XIAOCAO_ROOT"]), Path(os.environ["XIAOCAO_DAILY_RUN_DIR"]),
                             args.date, binding, budget_seconds=max(0.0, deadline-time.monotonic()))
    progress = review_progress(queue, history, expected_date=args.date, expected_binding=binding)
    while time.monotonic() < deadline:
        if progress.get("status") == "queue_invalid":
            if kol is not None:
                kol.defer("PAPER_INTELLIGENCE_QUEUE_INVALID")
            break
        target = args.min_reviews if args.min_reviews > 0 else progress["selected"]
        kol_done = kol is None or kol.tick()
        if not progress.get("status") and progress["reviewed"] >= target and kol_done:
            break
        time.sleep(min(max(0.05, args.poll_sec), max(0.0, deadline - time.monotonic())))
        progress = review_progress(queue, history, expected_date=args.date, expected_binding=binding)
    target = args.min_reviews if args.min_reviews > 0 else progress["selected"]
    progress.setdefault("status", "reviewed" if progress["reviewed"] >= target else "fallback_timeout")
    if kol is not None:
        kol.defer("PAPER_ORIGINAL_RENDEZVOUS_EXHAUSTED")
        progress["kol_support"] = {"status": kol.receipt["status"], "receipt_path": str(kol.path)}
    progress["authority"] = "shadow_only"
    print(json.dumps(progress, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
