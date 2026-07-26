#!/usr/bin/env python3
"""Prepare, publish, and audit KOL reports through LiangHui MCP."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.kol.initial_import import initial_import_candidates
from xiaocao.kol.longitudinal import (
    longitudinal_projection,
    longitudinal_update_candidates,
)
from xiaocao.kol.publication import (
    PublicationError,
    PublicationLedger,
    manifest_entries,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/live/kol_lianghui_initial"
DEFAULT_LONGITUDINAL_OUTPUT = (
    ROOT / "output/live/kol_lianghui_longitudinal_v1"
)
REQUIRED_KOL_TOOLS = {
    "put_kol_record",
    "publish_kol_report",
    "get_kol_record",
    "get_kol_write_status",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "prepare-initial",
            "verify-contract",
            "run-initial",
            "audit-initial",
            "status",
            "prepare-longitudinal",
            "run-longitudinal",
            "audit-longitudinal",
            "status-longitudinal",
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--delay-seconds", type=float, default=0.75)
    return parser


def _client(config: Path | None) -> LiangHuiMcpClient:
    return (
        LiangHuiMcpClient.from_config(config)
        if config
        else LiangHuiMcpClient.from_config()
    )


def _verify_contract(client: LiangHuiMcpClient) -> list[str]:
    names = {tool["name"] for tool in client.list_tools()}
    missing = sorted(REQUIRED_KOL_TOOLS - names)
    if missing:
        raise PublicationError(
            "LiangHui production MCP is missing KOL tools: "
            + ", ".join(missing)
        )
    return sorted(REQUIRED_KOL_TOOLS)


def _audit(
    client: LiangHuiMcpClient,
    candidates: list[dict],
    *,
    delay_seconds: float,
) -> list[dict]:
    results = []
    for index, candidate in enumerate(candidates):
        report = next(
            record
            for record in candidate["records"]
            if record["kind"] == "report"
        )
        actual = client.call_tool(
            "get_kol_record",
            {"kind": "report", "record_id": report["record_id"]},
        )
        if (
            actual.get("state") != "published"
            or actual.get("content_sha256") != report["content_sha256"]
            or actual.get("manifest_sha256")
            != candidate["publish_request"]["manifest_sha256"]
            or actual.get("manifest") != manifest_entries(candidate["records"])
        ):
            raise PublicationError(
                "production read-back mismatch for " + report["record_id"]
            )
        results.append(
            {
                "report_id": report["record_id"],
                "state": actual["state"],
                "content_sha256": actual["content_sha256"],
                "manifest_sha256": actual["manifest_sha256"],
            }
        )
        if index + 1 < len(candidates):
            time.sleep(max(0.0, delay_seconds))
    return results


def main() -> int:
    args = _parser().parse_args()
    longitudinal = args.command.endswith("-longitudinal")
    candidates = (
        longitudinal_update_candidates(ROOT)
        if longitudinal
        else initial_import_candidates(ROOT)
    )
    output_dir = args.output_dir or (
        DEFAULT_LONGITUDINAL_OUTPUT if longitudinal else DEFAULT_OUTPUT
    )
    ledger = PublicationLedger(output_dir)
    live_client = None
    live_tools = []
    audit_results = []
    if args.command in {"prepare-initial", "prepare-longitudinal"}:
        for candidate in candidates:
            ledger.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
    elif args.command in {
        "verify-contract",
        "run-initial",
        "audit-initial",
        "run-longitudinal",
        "audit-longitudinal",
    }:
        live_client = _client(args.config)
        live_tools = _verify_contract(live_client)
    if args.command in {"run-initial", "run-longitudinal"}:
        assert live_client is not None
        for index, candidate in enumerate(candidates):
            ledger.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
            ledger.run(candidate["publication_key"], live_client)
            if index + 1 < len(candidates):
                time.sleep(max(0.0, args.delay_seconds))
        audit_results = _audit(
            live_client,
            candidates,
            delay_seconds=args.delay_seconds,
        )
    elif args.command in {"audit-initial", "audit-longitudinal"}:
        assert live_client is not None
        audit_results = _audit(
            live_client,
            candidates,
            delay_seconds=args.delay_seconds,
        )
    statuses = (
        []
        if args.command == "verify-contract"
        else [
            ledger.status(candidate["publication_key"])
            for candidate in candidates
        ]
    )
    result = {
        "mode": "longitudinal" if longitudinal else "initial",
        "candidate_count": len(candidates),
        "completed_count": sum(bool(row["completed"]) for row in statuses),
        "live_tools": live_tools,
        "production_readback_count": len(audit_results),
        "report_ids": [
            next(
                record["record_id"]
                for record in candidate["records"]
                if record["kind"] == "report"
            )
            for candidate in candidates
        ],
        "detail_urls": [
            row["publish_receipt"].get("detailUrl")
            for row in statuses
            if row["publish_receipt"]
        ],
        "large_payload_local_bytes": 0,
        "notification_claims_created": 0,
        "book_kol_us_replays": 0,
    }
    if longitudinal:
        projection = longitudinal_projection(candidates)
        result["viewpoint_projection"] = {
            kol_id: {
                "author": row["author"],
                "counts": row["counts"],
                "relation_count": row["relation_count"],
                "current_summary": [
                    {
                        "subject": item["subject"],
                        "stance": item["stance"],
                        "status": item["status"],
                    }
                    for item in row["current_viewpoints"][:5]
                ],
            }
            for kol_id, row in projection["kols"].items()
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "viewpoint_projection.json").write_text(
            json.dumps(projection, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
