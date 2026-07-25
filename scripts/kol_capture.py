#!/usr/bin/env python3
"""Arm and advance the Xiaocao KOL capture-node workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.capture import (
    CHECKPOINT_STATUSES,
    CaptureJobStore,
    SnifferClient,
    resolve_candidate,
)


DEFAULT_LEDGER = Path("output/live/kol_capture_jobs.jsonl")


def _print(row: object) -> None:
    print(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "arm",
            "poll",
            "status",
            "checkpoint",
            "retry-download",
            "sanitize-ledger",
        ),
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--sniffer-url", default="http://127.0.0.1:2022")
    parser.add_argument("--job-id")
    parser.add_argument("--download", action="store_true", help="start download after a new capture")
    parser.add_argument("--state", choices=sorted(CHECKPOINT_STATUSES))
    parser.add_argument("--artifact-path")
    args = parser.parse_args()

    store = CaptureJobStore(args.ledger)
    if args.command == "sanitize-ledger":
        _print(store.sanitize_ledger())
        return 0
    client = SnifferClient(args.sniffer_url)
    if args.command == "arm":
        status = client.status()
        row = store.arm(client.candidates(), sniffer_status=status)
        _print(row)
        return 0

    current = store.latest(args.job_id)
    if current is None:
        parser.error("no capture job found; run arm first")
    if args.command == "status":
        _print(current)
        return 0
    if args.command == "checkpoint":
        if not args.state:
            parser.error("checkpoint requires --state")
        current = store.checkpoint(
            current,
            status=args.state,
            artifact_path=args.artifact_path,
        )
        _print(current)
        return 0
    if args.command == "retry-download":
        candidate = resolve_candidate(current, client.candidates())
        if candidate is None:
            parser.error("captured live is no longer available to retry")
        task_id = client.start_download(candidate, force=True)
        current = store.transition(
            current,
            "download_restarted",
            status="downloading",
            download_task_id=task_id,
        )
        _print(current)
        return 0

    if current.get("status") == "awaiting_capture":
        candidates = client.candidates()
        detected = store.detect_capture(current, candidates)
        if detected is not None:
            current = detected
    else:
        candidates = []
    if current.get("status") == "captured" and args.download:
        candidate = resolve_candidate(current, candidates or client.candidates())
        if candidate is None:
            parser.error("captured live is no longer available to download")
        task_id = client.start_download(candidate)
        current = store.transition(
            current,
            "download_started",
            status="downloading",
            download_task_id=task_id,
        )
    elif current.get("status") == "downloading":
        current = store.reconcile_download(current, client.tasks()) or current
    _print(current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
