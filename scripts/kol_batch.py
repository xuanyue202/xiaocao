#!/usr/bin/env python3
"""Run or inspect the resumable multi-source KOL batch coordinator."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from xiaocao.kol.batch import BatchCoordinator, BatchError
from xiaocao.live.notify import (
    ENV_WECOM_ACCOUNT_ID,
    ENV_WECOM_INSECURE,
    ENV_WECOM_RELAY_TOKEN,
    ENV_WECOM_RELAY_URL,
    _env_first,
    _merged_env,
    _truthy,
    _wecom_user_ids,
    wecom_notify,
)


DEFAULT_OUTPUT = Path("output/live/kol_batch")
MAX_BATCH_SPEC_BYTES = 16 * 1024 * 1024


class _StopRequested(BaseException):
    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _read_spec(path: Path) -> dict[str, Any]:
    try:
        if (
            path.suffix.lower() != ".json"
            or path.stat().st_size > MAX_BATCH_SPEC_BYTES
        ):
            raise BatchError("batch spec must be a small JSON file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BatchError("batch spec is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError("batch spec is invalid") from exc
    if (
        not isinstance(value, dict)
        or not str(value.get("batch_id") or "").strip()
        or not isinstance(value.get("children"), list)
    ):
        raise BatchError("batch spec is incomplete")
    watched = value.get("watched_artifacts", [])
    if not isinstance(watched, list):
        raise BatchError("batch watched_artifacts must be a list")
    insight_path = str(value.get("insight_path") or "").strip()
    if insight_path:
        resolved = Path(insight_path).expanduser()
        if not resolved.is_absolute():
            resolved = path.resolve().parent / resolved
        value["insight_path"] = str(resolved.resolve())
    return value


def _read_insight(path: Path) -> dict[str, Any]:
    try:
        if (
            path.suffix.lower() != ".json"
            or path.stat().st_size > MAX_BATCH_SPEC_BYTES
        ):
            raise BatchError("batch insight must be a small JSON file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BatchError("batch insight is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError("batch insight is invalid") from exc
    if not isinstance(value, dict):
        raise BatchError("batch insight must be a JSON object")
    return value


def _publish_insight(
    service: BatchCoordinator,
    batch_id: str,
    insight_path: Path,
) -> dict[str, Any]:
    src = _merged_env(os.environ)
    relay_url = _env_first(src, ENV_WECOM_RELAY_URL)
    token = _env_first(src, ENV_WECOM_RELAY_TOKEN)
    recipients = list(_wecom_user_ids(src, audience="kol"))
    if not relay_url or not token or not recipients:
        raise BatchError("KOL WeChat delivery is not configured")
    account_id = _env_first(src, ENV_WECOM_ACCOUNT_ID) or "default"

    def send(recipient: str, title: str, body: str) -> str:
        return wecom_notify(
            relay_url,
            title,
            body,
            token=token,
            user_id=recipient,
            account_id=account_id,
            insecure=_truthy(_env_first(src, ENV_WECOM_INSECURE)),
        )

    return service.publish_insight(
        batch_id,
        _read_insight(insight_path),
        recipients=recipients,
        sender=send,
    )


def _completion_summary(
    state: dict[str, Any],
    audit: dict[str, Any],
    *,
    insight_delivery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "acceptance_status": audit["status"],
        "batch_id": audit["batch_id"],
        "status": state["status"],
        "children": [
            {
                "adapter": child["adapter"],
                "author": child["author"],
                "media_type": child["media_type"],
                "status": child["status"],
                "household": (
                    child.get("terminal_receipt", {})
                    .get("household", {})
                    .get("status")
                ),
                "book_kol_us": (
                    child.get("terminal_receipt", {})
                    .get("book_kol_us", {})
                    .get("status")
                ),
            }
            for child in audit["children"]
        ],
        "terminal_receipt_count": audit["terminal_receipt_count"],
        "interruption_count": audit["interruption_count"],
        "new_external_side_effect_count": (
            insight_delivery["new_external_side_effect_count"]
            if insight_delivery is not None
            else audit["new_external_side_effect_count"]
        ),
        "coordinator_source_video_bytes": audit[
            "coordinator_source_video_bytes"
        ],
    }
    if audit["batch_insight"]["status"] != "not_required":
        summary["batch_insight"] = audit["batch_insight"]
        summary["recorded_external_side_effect_count"] = audit[
            "new_external_side_effect_count"
        ]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("run", "status", "audit", "deliver-insight"),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--insight", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    args = parser.parse_args()

    service = BatchCoordinator(args.output_dir)
    if args.command == "deliver-insight":
        if not args.batch_id or args.insight is None:
            parser.error(
                "deliver-insight requires --batch-id and --insight"
            )
        _print(
            _publish_insight(
                service,
                args.batch_id,
                args.insight.resolve(),
            )
        )
        return 0
    if args.command in {"status", "audit"}:
        if not args.batch_id:
            parser.error(f"{args.command} requires --batch-id")
        _print(
            service.status(args.batch_id)
            if args.command == "status"
            else service.audit(args.batch_id)
        )
        return 0
    if args.spec is None:
        parser.error("run requires --spec")
    if not 0.1 <= args.poll_interval_seconds <= 60:
        parser.error("--poll-interval-seconds must be within 0.1..60")

    spec = _read_spec(args.spec)
    batch_id = str(spec["batch_id"])
    service.create_batch(
        batch_id,
        spec["children"],
        watched_artifacts=spec.get("watched_artifacts", []),
        insight_required=bool(spec.get("insight_path")),
    )

    def stop(signum: int, _frame: Any) -> None:
        raise _StopRequested(signum)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        service.record_runner_started(batch_id)
        if args.once:
            state = service.run_once(batch_id)
            if (
                state["status"] == "completed"
                and spec.get("insight_path")
            ):
                _publish_insight(
                    service,
                    batch_id,
                    Path(str(spec["insight_path"])),
                )
                state = service.status(batch_id)
            _print(state)
            return 0

        while True:
            state = service.run_once(batch_id)
            if state["status"] == "completed":
                insight_delivery = None
                if spec.get("insight_path"):
                    insight_delivery = _publish_insight(
                        service,
                        batch_id,
                        Path(str(spec["insight_path"])),
                    )
                    state = service.status(batch_id)
                service.record_runner_completed(batch_id)
                audit = service.audit(batch_id)
                _print(
                    _completion_summary(
                        state,
                        audit,
                        insight_delivery=insight_delivery,
                    )
                )
                return 0
            runnable = [
                row
                for row in state["children"]
                if row["status"] not in {"terminal", "paused"}
            ]
            if not runnable:
                _print(state)
                return 2
            time.sleep(args.poll_interval_seconds)
    except _StopRequested as exc:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        service.record_interruption(
            batch_id,
            reason=f"signal_{exc.signum}",
        )
        return 128 + exc.signum


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BatchError as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc
