#!/usr/bin/env python3
"""Run or inspect the resumable Xiaocao live capture-to-decisions pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.xiaocao_live import (
    DEFAULT_CAPTURE_LEDGER,
    DEFAULT_DECISION_OUTPUT,
    DEFAULT_NETDISK_OUTPUT,
    DEFAULT_OUTPUT,
    DEFAULT_SNIFFER_BINARY,
    XiaocaoLiveService,
)
from xiaocao.live.notify import notify


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "run",
            "capture",
            "validate-capture",
            "cleanup-capture",
            "status",
            "cancel-wait",
            "audit",
            "reconcile-capture",
            "reconcile-existing",
            "confirm",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--capture-ledger",
        type=Path,
        default=DEFAULT_CAPTURE_LEDGER,
    )
    parser.add_argument(
        "--netdisk-output",
        type=Path,
        default=DEFAULT_NETDISK_OUTPUT,
    )
    parser.add_argument(
        "--decision-output",
        type=Path,
        default=DEFAULT_DECISION_OUTPUT,
    )
    parser.add_argument(
        "--sniffer-binary",
        type=Path,
        default=DEFAULT_SNIFFER_BINARY,
    )
    parser.add_argument("--capture-job-id")
    parser.add_argument(
        "--page-url",
        help="Xiaoetong replay page URL to bind when starting a capture",
    )
    parser.add_argument(
        "--opencli-session",
        default="site:baidu-netdisk",
    )
    parser.add_argument("--opencli-profile")
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--cleanup-evidence", type=Path)
    parser.add_argument("--acceptance-evidence", type=Path)
    parser.add_argument(
        "--confirmation",
        help="Legacy migration only; routine Ticket 03 runs complete from receipts",
    )
    args = parser.parse_args()
    if args.page_url and (
        args.command != "run" or args.capture_job_id is not None
    ):
        parser.error("--page-url is only valid when starting a new run")

    service = XiaocaoLiveService(
        args.output_dir,
        capture_ledger=args.capture_ledger,
        netdisk_output=args.netdisk_output,
        decision_output=args.decision_output,
        sniffer_binary=args.sniffer_binary,
    )
    if args.command == "status":
        _print(service.status())
        return 0
    if args.command == "capture":
        if not args.capture_job_id:
            parser.error("capture requires --capture-job-id")
        _print(service.advance_capture(args.capture_job_id))
        return 0
    if args.command == "validate-capture":
        if not args.capture_job_id:
            parser.error("validate-capture requires --capture-job-id")
        _print(service.validate_media(args.capture_job_id))
        return 0
    if args.command == "cleanup-capture":
        if not args.capture_job_id:
            parser.error("cleanup-capture requires --capture-job-id")
        _print(service.cleanup_sniffer(capture_job_id=args.capture_job_id))
        return 0
    if args.command == "cancel-wait":
        if not args.capture_job_id:
            parser.error("cancel-wait requires --capture-job-id")
        _print(service.cancel_capture_wait(args.capture_job_id))
        return 0
    if args.command == "confirm":
        if not args.confirmation:
            parser.error("confirm requires --confirmation")
        _print(service.confirm(confirmation=args.confirmation))
        return 0
    if args.command == "audit":
        if not args.capture_job_id:
            parser.error("audit requires --capture-job-id")
        _print(service.audit_acceptance(args.capture_job_id))
        return 0
    if args.command == "reconcile-capture":
        if not args.capture_job_id:
            parser.error("reconcile-capture requires --capture-job-id")
        _print(service.reconcile_completed_capture(args.capture_job_id))
        return 0
    if args.command == "reconcile-existing":
        if (
            not args.capture_job_id
            or args.cleanup_evidence is None
            or args.acceptance_evidence is None
        ):
            parser.error(
                "reconcile-existing requires --capture-job-id, "
                "--cleanup-evidence, and --acceptance-evidence"
            )
        _print(
            service.reconcile_existing(
                args.capture_job_id,
                cleanup_evidence_path=args.cleanup_evidence,
                acceptance_evidence_path=args.acceptance_evidence,
            )
        )
        return 0
    if not args.capture_job_id:
        _print(service.start(page_url=args.page_url))
        return 0
    _print(
        service.advance(
            args.capture_job_id,
            opencli_session=args.opencli_session,
            opencli_profile=args.opencli_profile,
            audit_path=args.audit_file,
            bundle_path=args.bundle,
            sender=lambda title, body: notify(
                title,
                body,
                macos=False,
                audience="kol",
            ),
        )
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
