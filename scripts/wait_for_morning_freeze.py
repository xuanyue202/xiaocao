#!/usr/bin/env python3
"""Wait for the dated recommendation and review queue produced by stage one."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, time as wall_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

READY_QUEUE_STATUSES = {"ready", "empty"}


def _producer_terminal_failure(live_dir: Path, date: str) -> dict[str, Any] | None:
    """Only a bound latest producer terminal may end the missing-bundle wait."""
    producers = []
    for path in (live_dir / "auto/runs").glob("*/manifest.json"):
        try:
            manifest = json.loads(path.read_text())
            if not isinstance(manifest, dict):
                continue
            if (manifest.get("automation_id") != "xiaocao-daily-morning"
                    or manifest.get("automation") != "morning-prerecommend"
                    or manifest.get("market_date") != date[:10]
                    or manifest.get("run_id") != path.parent.name
                    or not manifest.get("thread_id")):
                continue
            started = datetime.fromisoformat(manifest["started_at"])
            if started.tzinfo is None:
                continue
            producers.append((started, path, manifest))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    if not producers:
        return None
    _, path, manifest = max(producers, key=lambda item: (item[0], str(item[1])))
    terminal_path = path.parent / "terminal.json"
    try:
        terminal = json.loads(terminal_path.read_text())
        if not isinstance(terminal, dict):
            return None
        integrity = terminal.get("source_integrity")
        source_failure = (terminal.get("terminal_reason") == "source_changed"
            and type(terminal.get("exit_code")) is int and terminal["exit_code"] == 78
            and isinstance(integrity, dict) and integrity.get("status") == "changed")
        if (terminal.get("run_id") != manifest["run_id"]
                or terminal.get("automation") != manifest["automation"]
                or terminal.get("market_date") != date[:10]
                or terminal.get("deterministic_status") != "failed"
                or type(terminal.get("process_exit_code")) is not int
                or terminal["process_exit_code"] == 0 and not source_failure
                or Path(terminal["evidence"]["manifest_path"]).resolve() != path.resolve()):
            return None
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return {"status": "producer_failed", "reason": "ORIGINAL_PRODUCER_TERMINAL_WITHOUT_BUNDLE",
            "market_date": date[:10], "producer_receipt": str(terminal_path.resolve())}


def _freeze_status(*, date: str, live_dir: Path, snapshot_path: Path | None = None) -> dict[str, Any]:
    from xiaocao.live.morning_bundle import acquire_bundle, bundle_required, has_bundle_evidence, validate_components
    market_date = date[:10]
    if has_bundle_evidence(live_dir, market_date):
        result = acquire_bundle(live_dir, market_date)
        return result if result["status"] == "ready" else {**result, "status": "waiting"}
    failure = _producer_terminal_failure(live_dir, market_date)
    if failure is not None:
        return failure
    report = live_dir / f"recommend_{market_date}.md"
    queue_path = live_dir / f"intelligence_review_queue_{market_date}.json"
    base = {"market_date": market_date, "report": str(report), "queue": str(queue_path)}
    if bundle_required(market_date):
        return {**base, "status": "waiting", "reason": "original_bundle_commit_missing"}
    if not report.is_file():
        return {**base, "status": "waiting", "reason": "report_missing"}
    if not queue_path.is_file():
        return {**base, "status": "waiting", "reason": "queue_missing"}
    try:
        report_raw, queue_raw = report.read_bytes(), queue_path.read_bytes()
        queue = json.loads(queue_raw)
        if snapshot_path is None:
            # Historical inspection only; both production consumers pass the
            # exact immutable snapshot and cannot use this compatibility seam.
            if queue.get("market_date") != market_date:
                raise ValueError("queue_market_date_mismatch")
            count = (queue.get("counts") or {}).get("selected_items", 0)
            if queue.get("status") not in READY_QUEUE_STATUSES:
                raise ValueError("queue_not_frozen")
            if type(count) is not int or (queue["status"] == "ready") != (count > 0):
                raise ValueError("queue_status_count_mismatch")
            return {**base, "status": "ready", "reason": "dated_frozen_evidence_ready",
                "queue_status": queue["status"], "selected_items": count}
        if not snapshot_path.is_file():
            raise ValueError("snapshot_missing")
        binding = validate_components(market_date, snapshot_path.read_bytes(), report_raw, queue_raw)
        return {**base, **binding, "status": "ready", "reason": "dated_frozen_evidence_ready",
            "snapshot_path": str(snapshot_path)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {**base, "status": "waiting", "reason": str(exc) or "queue_invalid"}


def wait_for_morning_freeze(
    *,
    date: str,
    live_dir: Path,
    timeout_sec: float,
    poll_sec: float,
    snapshot_path: Path | None = None,
    heartbeat=None,
    heartbeat_seconds: float = 30.0,
    dependency_notice=None,
) -> dict[str, Any]:
    deadline = float("inf") if timeout_sec < 0 else time.monotonic() + timeout_sec
    china_zone = ZoneInfo("Asia/Shanghai")
    live_session = datetime.now(china_zone).date().isoformat() == date[:10]
    next_heartbeat = time.monotonic()
    # The native caller already performed its initial readiness check. Leave
    # the App alone until one minute before the expected 09:25 freeze, then
    # use the existing heartbeat to recover a session that locked while idle.
    resume_at = datetime.fromisoformat(date[:10]).replace(
        hour=9, minute=24, tzinfo=ZoneInfo("Asia/Shanghai")
    ) if heartbeat is not None else None
    result = _freeze_status(
        date=date,
        live_dir=live_dir,
        snapshot_path=snapshot_path,
    )
    emitted_requests = set()
    while result["status"] not in {"ready", "producer_failed"} and time.monotonic() < deadline:
        if live_session and datetime.now(china_zone).date().isoformat() != date[:10]:
            raise RuntimeError("MORNING_FREEZE_WAIT_SESSION_CHANGED")
        request_path = result.get("request_path")
        if dependency_notice and request_path and request_path not in emitted_requests:
            dependency_notice({"event": "morning_bundle_repair_required", **result})
            emitted_requests.add(request_path)
        if resume_at is not None:
            quiet_seconds = (resume_at - datetime.now(resume_at.tzinfo)).total_seconds()
            if quiet_seconds > 0:
                # Recheck wall time after each bounded sleep (suspend/clock
                # changes included), without native calls or freeze polling.
                remaining = max(0.0, deadline - time.monotonic())
                time.sleep(min(60.0, quiet_seconds, remaining))
                continue
        if heartbeat is not None and time.monotonic() >= next_heartbeat:
            heartbeat()
            next_heartbeat = time.monotonic() + max(1.0, heartbeat_seconds)
        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(max(0.05, poll_sec), remaining))
        result = _freeze_status(
            date=date,
            live_dir=live_dir,
            snapshot_path=snapshot_path,
        )
    if result["status"] == "ready":
        return result
    if result["status"] == "producer_failed":
        return result
    return {**result, "status": "timeout"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--live-dir", default="output/live")
    parser.add_argument("--snapshot-path", default=None)
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--timeout-sec", type=float, default=-1.0)
    parser.add_argument("--poll-sec", type=float, default=2.0)
    args = parser.parse_args()
    if args.timeout_sec != 0:
        from xiaocao.utils.business_clock import wait_for_business_time
        wait_for_business_time(args.date, wall_time(9, 25, 1))
    result = wait_for_morning_freeze(
        date=args.date,
        live_dir=Path(args.live_dir),
        snapshot_path=Path(args.snapshot_path) if args.snapshot_path else None,
        timeout_sec=args.timeout_sec,
        poll_sec=args.poll_sec,
        dependency_notice=lambda event: print(json.dumps(event, ensure_ascii=False, sort_keys=True), flush=True),
    )
    if args.receipt_path and result["status"] == "ready":
        from xiaocao.utils.atomic_files import atomic_write
        atomic_write(args.receipt_path, (json.dumps(result, sort_keys=True) + "\n").encode(), immutable=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["status"] == "ready" else 1)


if __name__ == "__main__":
    main()
