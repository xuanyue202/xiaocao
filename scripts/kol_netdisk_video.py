#!/usr/bin/env python3
"""Track one real KOL video through Baidu Netdisk browser enrichment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.enrichment import EnrichmentError
from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_netdisk_enrichment")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _load_object(path: Path) -> dict:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnrichmentError(f"invalid JSON evidence file: {path}") from exc
    if not isinstance(value, dict):
        raise EnrichmentError("JSON evidence must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "prepare",
            "liveness",
            "claim",
            "record",
            "capability-failure",
            "capture-dom",
            "import-download",
            "verify",
            "decide",
            "status",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument(
        "--action", choices=("upload", "transcript", "ai_note", "export", "download")
    )
    parser.add_argument(
        "--step",
        choices=(
            "video_ready",
            "transcript_requested",
            "transcript_ready",
            "ai_note_requested",
            "ai_note_ready",
            "export_ready",
            "cloud_document_ready",
            "download_requested",
        ),
    )
    parser.add_argument("--evidence-file", type=Path)
    parser.add_argument("--source-mode", choices=("existing", "uploaded"))
    parser.add_argument(
        "--reconcile-existing",
        action="store_true",
        help="record a DOM-proven existing transcript/AI-note ready state without regenerating it",
    )
    parser.add_argument(
        "--surface", choices=("codex_in_app_browser", "codex_chrome", "opencli")
    )
    parser.add_argument(
        "--reason",
        choices=(
            "browser_security_policy_denied",
            "authentication_required",
            "captcha_required",
            "page_contract_changed",
        ),
    )
    parser.add_argument("--download", type=Path)
    parser.add_argument("--opencli-session")
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    args = parser.parse_args()

    if args.command == "prepare" and args.video is None:
        parser.error("prepare requires --video")
    if args.command not in {"prepare", "status"} and not args.job_id:
        parser.error(f"{args.command} requires --job-id")
    if args.command == "claim" and args.action is None:
        parser.error("claim requires --action")
    if args.command == "liveness" and (
        args.surface is None or args.evidence_file is None
    ):
        parser.error("liveness requires --surface and --evidence-file")
    if args.command == "record" and (args.step is None or args.evidence_file is None):
        parser.error("record requires --step and --evidence-file")
    if args.command == "capability-failure" and (
        args.surface is None or args.reason is None
    ):
        parser.error("capability-failure requires --surface and --reason")
    if args.command == "import-download" and args.download is None:
        parser.error("import-download requires --download")
    if args.command == "capture-dom" and not args.opencli_session:
        parser.error("capture-dom requires --opencli-session")
    if args.command == "verify" and args.audit_file is None:
        parser.error("verify requires --audit-file")
    if args.command == "decide" and args.bundle is None:
        parser.error("decide requires --bundle")

    service = NetdiskEnrichmentService(args.output_dir)
    if args.command == "prepare":
        _print(service.prepare(args.video))
    elif args.command == "status":
        _print(service.status(args.job_id))
    elif args.command == "liveness":
        _print(
            service.record_browser_liveness(
                args.job_id,
                surface=args.surface,
                evidence=_load_object(args.evidence_file),
            )
        )
    elif args.command == "claim":
        _print(service.claim_browser_action(args.job_id, action=args.action))
    elif args.command == "record":
        _print(
            service.record_browser_state(
                args.job_id,
                step=args.step,
                evidence=_load_object(args.evidence_file),
                source_mode=args.source_mode,
                reconcile_existing=args.reconcile_existing,
            )
        )
    elif args.command == "capability-failure":
        _print(
            service.record_capability_failure(
                args.job_id, surface=args.surface, reason=args.reason
            )
        )
    elif args.command == "capture-dom":
        _print(
            service.capture_opencli_transcript(
                args.job_id,
                session=args.opencli_session,
            )
        )
    elif args.command == "import-download":
        _print(service.import_transcript_download(args.job_id, args.download))
    elif args.command == "verify":
        _print(service.verify_download(args.job_id, audit_path=args.audit_file))
    else:
        _print(
            service.decide(
                args.job_id,
                bundle_path=args.bundle,
                decision_output_dir=args.decision_output_dir,
                sender=lambda title, body: notify(title, body, macos=False),
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EnrichmentError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
