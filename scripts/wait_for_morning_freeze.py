#!/usr/bin/env python3
"""Wait for the dated recommendation and review queue produced by stage one."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from xiaocao.live.trading_runner import frozen_rows_digest, read_frozen_rows


READY_QUEUE_STATUSES = {"ready", "empty"}


def _freeze_status(
    *,
    date: str,
    live_dir: Path,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    market_date = date[:10]
    report = live_dir / f"recommend_{market_date}.md"
    queue_path = live_dir / f"intelligence_review_queue_{market_date}.json"
    base = {
        "market_date": market_date,
        "report": str(report),
        "queue": str(queue_path),
    }
    if not report.is_file():
        return {**base, "status": "waiting", "reason": "report_missing"}
    try:
        if report.stat().st_size <= 0:
            return {**base, "status": "waiting", "reason": "report_empty"}
    except OSError:
        return {**base, "status": "waiting", "reason": "report_unreadable"}
    if not queue_path.is_file():
        return {**base, "status": "waiting", "reason": "queue_missing"}
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**base, "status": "waiting", "reason": "queue_invalid"}
    queue_date = str(queue.get("market_date") or "")[:10]
    if queue_date != market_date:
        return {
            **base,
            "status": "waiting",
            "reason": "queue_market_date_mismatch",
            "queue_market_date": queue_date,
        }
    queue_status = str(queue.get("status") or "")
    if queue_status not in READY_QUEUE_STATUSES:
        return {
            **base,
            "status": "waiting",
            "reason": "queue_not_frozen",
            "queue_status": queue_status,
        }
    counts = queue.get("counts") if isinstance(queue.get("counts"), dict) else {}
    selected_items = int(counts.get("selected_items") or 0)
    if (queue_status == "ready" and selected_items <= 0) or (
        queue_status == "empty" and selected_items != 0
    ):
        return {
            **base,
            "status": "waiting",
            "reason": "queue_status_count_mismatch",
            "queue_status": queue_status,
            "selected_items": selected_items,
        }
    result = {
        **base,
        "status": "ready",
        "reason": "dated_frozen_evidence_ready",
        "queue_status": queue_status,
        "selected_items": selected_items,
    }
    if snapshot_path is None:
        return result
    binding = queue.get("freeze_binding")
    if not isinstance(binding, dict):
        return {**base, "status": "waiting", "reason": "queue_freeze_binding_missing"}
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    if str(binding.get("report_sha256") or "") != report_sha256:
        return {**base, "status": "waiting", "reason": "queue_report_binding_mismatch"}
    try:
        rows = read_frozen_rows(snapshot_path, date=market_date)
    except FileNotFoundError:
        return {**base, "status": "waiting", "reason": "snapshot_missing"}
    except (OSError, ValueError):
        return {**base, "status": "waiting", "reason": "snapshot_invalid"}
    snapshot_sha256 = frozen_rows_digest(rows)
    if (
        int(binding.get("snapshot_row_count") or 0) != len(rows)
        or str(binding.get("snapshot_sha256") or "") != snapshot_sha256
        or not str(binding.get("strategy_run_id") or "").strip()
        or not re.fullmatch(
            r"[0-9a-f]{40}|[0-9a-f]{64}",
            str(binding.get("strategy_sha") or ""),
        )
    ):
        return {**base, "status": "waiting", "reason": "queue_snapshot_binding_mismatch"}
    return {
        **result,
        "snapshot_path": str(snapshot_path),
        "snapshot_row_count": len(rows),
        "snapshot_sha256": snapshot_sha256,
        "strategy_run_id": str(binding["strategy_run_id"]),
        "strategy_sha": str(binding["strategy_sha"]),
        "report_sha256": report_sha256,
    }


def wait_for_morning_freeze(
    *,
    date: str,
    live_dir: Path,
    timeout_sec: float,
    poll_sec: float,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, timeout_sec)
    result = _freeze_status(
        date=date,
        live_dir=live_dir,
        snapshot_path=snapshot_path,
    )
    while result["status"] != "ready" and time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(max(0.05, poll_sec), remaining))
        result = _freeze_status(
            date=date,
            live_dir=live_dir,
            snapshot_path=snapshot_path,
        )
    if result["status"] == "ready":
        return result
    return {**result, "status": "timeout"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--live-dir", default="output/live")
    parser.add_argument("--snapshot-path", default=None)
    parser.add_argument("--timeout-sec", type=float, default=240.0)
    parser.add_argument("--poll-sec", type=float, default=1.0)
    args = parser.parse_args()
    result = wait_for_morning_freeze(
        date=args.date,
        live_dir=Path(args.live_dir),
        snapshot_path=Path(args.snapshot_path) if args.snapshot_path else None,
        timeout_sec=args.timeout_sec,
        poll_sec=args.poll_sec,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["status"] == "ready" else 1)


if __name__ == "__main__":
    main()
