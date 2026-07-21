#!/usr/bin/env python3
"""Advance one real KOL video through deterministic Baidu AASR enrichment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from xiaocao.kol.enrichment import (
    BaiduAasrClient,
    EnrichmentError,
    S3AudioPublisher,
    VideoEnrichmentService,
)
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_enrichment")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("prepare", "submit", "poll", "render", "verify", "decide", "status"),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--job-id")
    parser.add_argument("--s3-prefix")
    parser.add_argument(
        "--speech-url-env",
        default="KOL_AASR_SPEECH_URL",
        help="environment variable containing an authorized HTTPS .wav URL",
    )
    parser.add_argument(
        "--publication-reference",
        help="stable secret-free reference required with --speech-url-env",
    )
    parser.add_argument("--audit-file", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    args = parser.parse_args()

    if args.command == "prepare" and args.video is None:
        parser.error("prepare requires --video")
    if args.command not in {"prepare", "status"} and not args.job_id:
        parser.error(f"{args.command} requires --job-id")
    if args.command == "verify" and args.audit_file is None:
        parser.error("verify requires --audit-file")
    if args.command == "decide" and args.bundle is None:
        parser.error("decide requires --bundle")

    needs_client = args.command in {"submit", "poll"}
    client = BaiduAasrClient.from_env() if needs_client else None
    service = VideoEnrichmentService(args.output_dir, aasr_client=client)
    if args.command == "prepare":
        _print(service.prepare(args.video))
        return 0
    if args.command == "status":
        _print(service.status(args.job_id))
        return 0
    if args.command == "submit":
        current = service.status(args.job_id)
        if current.get("provider_task_id"):
            _print({**current, "idempotent_replay": True})
            return 0
        if args.s3_prefix:
            published = S3AudioPublisher().publish(
                current["audio_path"],
                s3_prefix=args.s3_prefix,
                audio_sha256=current["audio_sha256"],
            )
            speech_url = published.speech_url
            publication_reference = published.publication_reference
        else:
            speech_url = str(os.environ.get(args.speech_url_env) or "").strip()
            publication_reference = str(args.publication_reference or "").strip()
            if not speech_url or not publication_reference:
                parser.error(
                    "submit requires --s3-prefix, or an HTTPS URL in --speech-url-env "
                    "plus --publication-reference"
                )
        _print(
            service.submit(
                args.job_id,
                speech_url=speech_url,
                publication_reference=publication_reference,
            )
        )
        return 0
    if args.command == "poll":
        result = service.poll(args.job_id)
        _print(result)
        return 2 if result.get("status") == "failed" else 0
    if args.command == "render":
        _print(service.render(args.job_id))
        return 0
    if args.command == "verify":
        _print(service.verify(args.job_id, audit_path=args.audit_file))
        return 0
    _print(
        service.decide(
            args.job_id,
            bundle_path=args.bundle,
            decision_output_dir=args.decision_output_dir,
            sender=lambda title, body: notify(title, body, macos=False, audience="kol"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EnrichmentError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
