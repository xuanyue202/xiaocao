#!/usr/bin/env python3
"""Poll and process the one configured Lv Xiaotong browser subscription."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.lv_subscription import LvSubscriptionService
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_lv_subscription")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _run_bundle_builder(
    bundle_override: Path | None,
):
    override_used = False

    def build(evidence: dict[str, Any]) -> Path:
        nonlocal override_used
        if bundle_override is not None:
            if override_used:
                raise EnrichmentError(
                    "run --bundle can cover only one pending source version"
                )
            override_used = True
            return bundle_override
        request = {
            "event": "subscription_analysis_input_required",
            "identity": evidence["identity"],
            "version_key": evidence["version_key"],
            "title": evidence["title"],
            "media_type": evidence["media_type"],
            "analysis_request_path": evidence["analysis_request_path"],
            "evidence_path": evidence["evidence_path"],
            "evidence_sha256": evidence["evidence_sha256"],
        }
        print(
            json.dumps(request, ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        response = sys.stdin.readline()
        if not response:
            raise EnrichmentError(
                "subscription runner requires one decision bundle path on stdin"
            )
        value = response.strip()
        if value.startswith("{"):
            try:
                payload = json.loads(value)
            except json.JSONDecodeError as exc:
                raise EnrichmentError(
                    "subscription runner bundle response is invalid JSON"
                ) from exc
            value = str(payload.get("bundle_path") or "").strip()
        if not value:
            raise EnrichmentError(
                "subscription runner decision bundle path is missing"
            )
        return Path(value)

    return build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "poll",
            "run",
            "claim-download",
            "complete-download",
            "ingest",
            "decide",
            "status",
        ),
    )
    parser.add_argument("--config", type=Path, default=Path("xiaocao.yaml"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--opencli-session", default="xiaocao-lv-subscription")
    parser.add_argument("--opencli-profile")
    parser.add_argument(
        "--bootstrap-bind",
        action="store_true",
        help=(
            "bind the active user-authorized Chrome OpenCLI share tab before "
            "the one-shot run"
        ),
    )
    parser.add_argument("--identity")
    parser.add_argument("--downloaded-file", type=Path)
    parser.add_argument("--claim-id")
    parser.add_argument(
        "--bundle",
        type=Path,
        help=(
            "decision bundle for decide, or a one-pending-item override for run"
        ),
    )
    parser.add_argument(
        "--decision-output-dir",
        type=Path,
        default=DEFAULT_DECISIONS,
    )
    args = parser.parse_args()

    if args.command in {
        "claim-download",
        "complete-download",
        "ingest",
        "decide",
    } and not args.identity:
        parser.error(f"{args.command} requires --identity")
    if args.command == "complete-download" and args.downloaded_file is None:
        parser.error("complete-download requires --downloaded-file")
    if args.command == "complete-download" and not args.claim_id:
        parser.error("complete-download requires --claim-id")
    if args.command == "decide" and args.bundle is None:
        parser.error("decide requires --bundle")
    if args.bootstrap_bind and args.command != "run":
        parser.error("--bootstrap-bind is valid only with run")

    service = LvSubscriptionService.from_config(
        args.output_dir,
        config_path=args.config,
    )
    if args.command == "poll":
        result = service.poll_opencli(
            session=args.opencli_session,
            profile=args.opencli_profile,
        )
        if result is not None:
            _print(result)
    elif args.command == "run":
        result = service.run_opencli(
            session=args.opencli_session,
            profile=args.opencli_profile,
            decision_output_dir=args.decision_output_dir,
            bundle_builder=_run_bundle_builder(args.bundle),
            sender=lambda title, body: notify(
                title,
                body,
                macos=False,
                audience="kol",
            ),
            bootstrap_bind=args.bootstrap_bind,
        )
        if result is not None:
            _print(result)
    elif args.command == "claim-download":
        _print(service.claim_browser_download(args.identity))
    elif args.command == "complete-download":
        _print(
            service.complete_browser_download(
                args.identity,
                args.downloaded_file,
                claim_id=args.claim_id,
            )
        )
    elif args.command == "ingest":
        _print(service.ingest_browser_download(args.identity))
    elif args.command == "decide":
        _print(
            service.decide(
                args.identity,
                bundle_path=args.bundle,
                decision_output_dir=args.decision_output_dir,
                sender=lambda title, body: notify(
                    title,
                    body,
                    macos=False,
                    audience="kol",
                ),
            )
        )
    else:
        _print(service.status())
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
