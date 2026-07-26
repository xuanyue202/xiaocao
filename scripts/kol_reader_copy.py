#!/usr/bin/env python3
"""Prepare, run, and audit the Lv reader-copy production correction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.kol.publication import (
    PublicationError,
    PublicationLedger,
    manifest_entries,
    read_published_publication,
)
from xiaocao.kol.reader_copy_correction import (
    LV_JULY_13_REPORT_ID,
    LV_JULY_20_REPORT_ID,
    build_lv_reader_copy_correction,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/live/kol_reader_copy_20260726"
REPORT_IDS = (LV_JULY_13_REPORT_ID, LV_JULY_20_REPORT_ID)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("prepare", "run", "audit", "status"),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=None)
    return parser


def _client(path: Path | None) -> LiangHuiMcpClient:
    return (
        LiangHuiMcpClient.from_config(path)
        if path
        else LiangHuiMcpClient.from_config()
    )


def _prepared(
    ledger: PublicationLedger,
    publication_key: str,
) -> dict[str, Any] | None:
    try:
        return ledger.status(publication_key)
    except PublicationError as exc:
        if str(exc) == "publication is not prepared":
            return None
        raise


def _candidate_from_state(state: dict[str, Any]) -> dict[str, Any]:
    artifact = state["artifact"]
    return {
        "publication_key": state["publication_key"],
        "records": artifact["records"],
        "publish_request": artifact["publish_request"],
        "metadata": artifact["metadata"],
    }


def _prepare_candidates(
    ledger: PublicationLedger,
    client: LiangHuiMcpClient,
) -> list[dict[str, Any]]:
    prefix = "reader-copy-natural-chinese-v2:"
    first_key = prefix + LV_JULY_13_REPORT_ID
    second_key = prefix + LV_JULY_20_REPORT_ID
    first_state = _prepared(ledger, first_key)
    if first_state is None:
        first = build_lv_reader_copy_correction(
            read_published_publication(client, LV_JULY_13_REPORT_ID)
        )
        ledger.prepare(
            first["publication_key"],
            first["records"],
            first["publish_request"],
            metadata=first["metadata"],
        )
        first_state = ledger.status(first_key)
    first = _candidate_from_state(first_state)
    replacements = first["metadata"]["replacements"]

    second_state = _prepared(ledger, second_key)
    if second_state is None:
        second = build_lv_reader_copy_correction(
            read_published_publication(client, LV_JULY_20_REPORT_ID),
            prior_replacements=replacements,
        )
        ledger.prepare(
            second["publication_key"],
            second["records"],
            second["publish_request"],
            metadata=second["metadata"],
        )
        second_state = ledger.status(second_key)
    return [first, _candidate_from_state(second_state)]


def _local_candidates(ledger: PublicationLedger) -> list[dict[str, Any]]:
    candidates = []
    for report_id in REPORT_IDS:
        state = _prepared(
            ledger,
            "reader-copy-natural-chinese-v2:" + report_id,
        )
        if state is None:
            raise PublicationError("reader-copy correction is not prepared")
        candidates.append(_candidate_from_state(state))
    return candidates


def _audit_candidate(
    client: LiangHuiMcpClient,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    report = next(
        record
        for record in candidate["records"]
        if record["kind"] == "report"
    )
    actual = client.call_tool(
        "get_kol_record",
        {"kind": "report", "record_id": report["record_id"]},
    )
    expected_manifest = manifest_entries(candidate["records"])
    if (
        actual.get("state") != "published"
        or actual.get("content_sha256") != report["content_sha256"]
        or actual.get("manifest_sha256")
        != candidate["publish_request"]["manifest_sha256"]
        or actual.get("manifest") != expected_manifest
    ):
        raise PublicationError(
            "reader-copy production read-back mismatch for "
            + report["record_id"]
        )
    publication = read_published_publication(client, report["record_id"])
    viewpoints = [
        record["payload"]
        for record in publication["records"]
        if record["kind"] == "viewpoint"
        and str(record["payload"].get("local_thesis_id") or "").endswith(
            "-reader-cn-v2"
        )
    ]
    if not viewpoints:
        raise PublicationError("reader-copy replacements are not readable")
    return {
        "report_id": report["record_id"],
        "title": report["payload"]["title"],
        "content_sha256": actual["content_sha256"],
        "manifest_sha256": actual["manifest_sha256"],
        "corrected_viewpoints": [
            {
                "subject": row["subject"],
                "stance": row["stance"],
            }
            for row in viewpoints
        ],
        "detail_url": actual.get("detailUrl"),
    }


def main() -> int:
    args = _parser().parse_args()
    ledger = PublicationLedger(args.output_dir)
    client = None
    if args.command == "status":
        candidates = _local_candidates(ledger)
    else:
        client = _client(args.config)
        if args.command in {"prepare", "run"}:
            candidates = _prepare_candidates(ledger, client)
        else:
            candidates = _local_candidates(ledger)

    if args.command == "run":
        assert client is not None
        for candidate in candidates:
            ledger.run(candidate["publication_key"], client)

    audits = []
    if args.command in {"run", "audit"}:
        assert client is not None
        audits = [
            _audit_candidate(client, candidate)
            for candidate in candidates
        ]

    statuses = [
        ledger.status(candidate["publication_key"])
        for candidate in candidates
    ]
    result = {
        "candidate_count": len(candidates),
        "completed_count": sum(
            bool(status["completed"]) for status in statuses
        ),
        "report_ids": REPORT_IDS,
        "audits": audits,
        "large_payload_local_bytes": 0,
        "notification_claims_created": 0,
        "book_kol_us_replays": 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
