#!/usr/bin/env python3
"""Run the resumable Lv Xiaotong + Lucifer cloud-video pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.subscription_video import SubscriptionVideoService
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_subscription_videos")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _read_bundle(request: dict[str, Any]) -> Path:
    print(json.dumps(request, ensure_ascii=False, sort_keys=True), flush=True)
    response = sys.stdin.readline()
    if not response:
        raise EnrichmentError(
            "subscription video runner requires a decision bundle path on stdin"
        )
    value = response.strip()
    if value.startswith("{"):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise EnrichmentError(
                "subscription video bundle response is invalid JSON"
            ) from exc
        value = str(payload.get("bundle_path") or "").strip()
    if not value:
        raise EnrichmentError("subscription video decision bundle path is missing")
    return Path(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "scan", "status"))
    parser.add_argument("--config", type=Path, default=Path("xiaocao.yaml"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--opencli-profile")
    parser.add_argument(
        "--lv-session",
        default="xiaocao-lv-subscription",
    )
    parser.add_argument(
        "--private-session",
        default="xiaocao-lv-subscription",
    )
    parser.add_argument(
        "--enrichment-session",
        default="xiaocao-lv-subscription",
    )
    args = parser.parse_args()

    service = SubscriptionVideoService(
        args.output_dir,
        config_path=args.config,
    )
    if args.command == "status":
        _print(service.status())
        return 0

    discovered = service.scan_opencli(
        lv_session=args.lv_session,
        private_session=args.private_session,
        profile=args.opencli_profile,
    )
    if args.command == "scan":
        if discovered is not None:
            _print(discovered)
        return 0

    pending = service.pending_items()
    if not pending:
        return 0
    completed = []
    for item in pending:
        state = service.advance_item(
            item,
            lv_session=args.lv_session,
            private_session=args.private_session,
            enrichment_session=args.enrichment_session,
            profile=args.opencli_profile,
        )
        if state.get("event") == "subscription_video_analysis_input_required":
            bundle_path = _read_bundle(state)
            state = service.decide_item(
                item,
                bundle_path=bundle_path,
                decision_output_dir=args.decision_output_dir,
                sender=lambda title, body: notify(
                    title,
                    body,
                    macos=False,
                    audience="kol",
                ),
            )
        if state.get("status") != "decided":
            _print(
                {
                    "event": "subscription_video_pending",
                    "identity": item["identity"],
                    "version_key": item["version_key"],
                    "source": item["source"],
                    "author": item["author"],
                    "checkpoint": state,
                }
            )
            return 2
        completed.append(
            {
                "identity": item["identity"],
                "version_key": item["version_key"],
                "source": item["source"],
                "author": item["author"],
                "job_id": state["job_id"],
                "decision_result_path": state["decision_result_path"],
            }
        )
    _print(
        {
            "event": "subscription_video_run_completed",
            "completed": completed,
        }
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EnrichmentError as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc
