from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from xiaocao.kol.claim_coverage import (
    CONTRACT_VERSION,
    evidence_segments,
    validate_claim_coverage,
)
from xiaocao.kol.rendering import render_household_item_message
from xiaocao.live.notify import split_wecom_text_by_bytes


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _lines_with_segments(
    text: str,
    *,
    evidence_sha256: str,
) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    segments = evidence_segments(text, evidence_sha256=evidence_sha256)
    line_starts: list[int] = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        line_starts.append(cursor)
        cursor += len(line)

    by_line: dict[int, list[dict[str, Any]]] = {}
    for segment in segments:
        start = int(segment["start"])
        line_number = 1
        for index, line_start in enumerate(line_starts, start=1):
            if line_start > start:
                break
            line_number = index
        by_line.setdefault(line_number, []).append(segment)
    return by_line, segments


def _expand_lines(values: list[Any]) -> set[int]:
    result: set[int] = set()
    for value in values:
        if isinstance(value, int):
            result.add(value)
            continue
        pieces = str(value).split("-", 1)
        if len(pieces) == 1:
            result.add(int(pieces[0]))
        else:
            start, end = (int(piece) for piece in pieces)
            result.update(range(start, end + 1))
    return result


def build(spec: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
    evidence_path = Path(spec["evidence_path"]).expanduser().resolve()
    text = evidence_path.read_text(encoding="utf-8")
    evidence_sha256 = _sha256_text(text)
    if evidence_sha256 != spec["evidence_sha256"]:
        raise ValueError("gold review evidence hash changed")
    segments_by_line, segments = _lines_with_segments(
        text,
        evidence_sha256=evidence_sha256,
    )

    claims: list[dict[str, Any]] = []
    theses: list[dict[str, Any]] = []
    fact_checks: list[dict[str, Any]] = []
    segment_theses: dict[str, list[str]] = {}
    for row in spec["theses"]:
        thesis_id = row["thesis_id"]
        decision_relevance = row.get("decision_relevance", "must_surface")
        claim_id = f"claim-{thesis_id}"
        refs = []
        for quote_row in row["evidence"]:
            line_number = int(quote_row["line"])
            quote = quote_row["quote"]
            matches = []
            for segment in segments_by_line.get(line_number, []):
                segment_text = text[int(segment["start"]):int(segment["end"])]
                if quote in segment_text:
                    matches.append(segment)
            if len(matches) != 1:
                raise ValueError(
                    f"{thesis_id} quote does not identify one segment on "
                    f"line {line_number}: {quote}"
                )
            segment = matches[0]
            refs.append(
                {
                    "segment_id": segment["segment_id"],
                    "quotes": [quote],
                }
            )
        fact_check = row.get("fact_check") or {}
        claims.append(
            {
                "claim_id": claim_id,
                "quote": row["evidence"][0]["quote"],
                "reader_quote": row["reader_text"],
                "reasoning": (
                    f"{row.get('priority_reason') or row['stance']} "
                    f"{fact_check.get('summary') or row['stance']}"
                ).strip(),
                "asset_scope": row.get("asset_scope") or [row["subject"]],
                "direction": row.get("direction") or row["stance"],
                "horizon": row["horizon"],
                "confidence": row.get("confidence") or (
                    "medium"
                    if fact_check.get("status") in {"support", "not_needed"}
                    else "low"
                ),
                "falsifiers": row.get("falsifiers") or [
                    fact_check.get("summary")
                    or "来源条件或当前事实发生实质变化时重新评估。"
                ],
            }
        )
        thesis = {
            "thesis_id": thesis_id,
            "role": row["role"],
            "decision_relevance": decision_relevance,
            "importance_basis": row.get("importance_basis", []),
            "claim_ids": [claim_id],
            "subject": row["subject"],
            "stance": row["stance"],
            "horizon": row["horizon"],
            "attribution": row.get("attribution", spec["author"]),
            "evidence_refs": refs,
        }
        if decision_relevance == "must_surface":
            thesis["priority"] = {
                    "rank": int(row["rank"]),
                    "urgency": row["urgency"],
                    "potential_impact": row["potential_impact"],
                    "specificity": row["specificity"],
                    "user_relevance": row.get("user_relevance", "unknown"),
                    "reason": row["priority_reason"],
            }
            fact_check = row["fact_check"]
            fact_checks.append(
                {
                    "thesis_id": thesis_id,
                    "status": fact_check["status"],
                    "summary": fact_check["summary"],
                    "reader_visible": fact_check["reader_visible"],
                }
            )
        theses.append(thesis)
        for line_number in _expand_lines(row["investment_lines"]):
            for segment in segments_by_line.get(line_number, []):
                linked = segment_theses.setdefault(segment["segment_id"], [])
                if thesis_id not in linked:
                    linked.append(thesis_id)

    advertisement_lines = _expand_lines(spec.get("advertisement_lines", []))
    reviews = []
    for segment in segments:
        segment_id = segment["segment_id"]
        linked = sorted(
            segment_theses.get(segment_id, []),
            key=lambda thesis_id: next(
                int(row.get("rank", len(spec["theses"]) + 1))
                for row in spec["theses"]
                if row["thesis_id"] == thesis_id
            ),
        )
        line_number = next(
            line
            for line, line_segments in segments_by_line.items()
            if any(value["segment_id"] == segment_id for value in line_segments)
        )
        if linked:
            disposition = "investment_content"
            reason = "该段含有已登记的投资论证、资产配置或重大风险信息。"
        elif line_number in advertisement_lines:
            disposition = "advertisement"
            reason = "会员、直播或课程推广，不进入投资主张。"
        else:
            disposition = "non_investment_content"
            reason = "独立复读后未发现会改变投资或资本风险决策的内容。"
        reviews.append(
            {
                "segment_id": segment_id,
                "source_line": line_number,
                "disposition": disposition,
                "thesis_ids": linked,
                "reason": reason,
            }
        )

    paragraphs = []
    for paragraph in spec["reader_paragraphs"]:
        paragraphs.append(
            {
                "kind": paragraph["kind"],
                "thesis_ids": paragraph["thesis_ids"],
                "text": paragraph["text"],
            }
        )
    item = {
        "source": spec["source"],
        "author": spec["author"],
        "title": spec["title"],
        "published_at": spec["published_at"],
        "media_type": spec["media_type"],
        "evidence_path": str(evidence_path),
        "evidence_sha256": evidence_sha256,
        "decision_status": spec.get("decision_status", "actionable_signal"),
        "claims": claims,
        "investment_thesis_inventory": {
            "contract_version": CONTRACT_VERSION,
            "evidence_sha256": evidence_sha256,
            "theses": theses,
        },
        "investment_thesis_coverage_audit": {
            "contract_version": CONTRACT_VERSION,
            "evidence_sha256": evidence_sha256,
            "review_mode": "independent_semantic_reread",
            "status": "passed",
            "findings": {
                "missing_theses": [],
                "incorrect_merges": [],
                "role_errors": [],
            },
            "segment_reviews": reviews,
        },
        "investment_thesis_fact_checks": fact_checks,
        "reader_briefing": {
            "format": "wecom_narrative_v1",
            "title": spec["reader_title"],
            "thesis_order": [
                row["thesis_id"]
                for row in sorted(
                    (
                        value
                        for value in spec["theses"]
                        if value.get("decision_relevance", "must_surface")
                        == "must_surface"
                    ),
                    key=lambda value: value["rank"],
                )
            ],
            "paragraphs": paragraphs,
        },
    }
    validation = validate_claim_coverage(
        item,
        evidence_text=text,
        evidence_sha256=evidence_sha256,
    )
    return item, render_household_item_message(item), validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-bundle")
    parser.add_argument("--decision-bundle-output")
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    item, message, validation = build(spec)
    transport_text = f"{item['reader_briefing']['title']}\n{message}"
    chunks = split_wecom_text_by_bytes(transport_text)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "review_kind": "read_only_gold_inventory",
                "external_side_effect_count": 0,
                "coordinator_source_video_bytes": 0,
                "validation": validation,
                "item": item,
                "reader_message": message,
                "reader_message_utf8_bytes": len(message.encode("utf-8")),
                "transport_contract": {
                    "utf8_chunk_limit_bytes": 2048,
                    "chunk_count": len(chunks),
                    "utf8_chunk_sizes_bytes": [
                        len(chunk.encode("utf-8")) for chunk in chunks
                    ],
                    "lossless_reassembly": "".join(chunks) == transport_text,
                    "semantic_boundary_split": all(
                        chunk.endswith("\n\n") for chunk in chunks[:-1]
                    ),
                    "logical_receipt_count": 1,
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if bool(args.base_bundle) != bool(args.decision_bundle_output):
        raise ValueError(
            "--base-bundle and --decision-bundle-output must be used together"
        )
    if args.base_bundle:
        base_bundle = json.loads(
            Path(args.base_bundle).read_text(encoding="utf-8")
        )
        rows = base_bundle.get("items")
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise ValueError("base decision bundle requires exactly one item")
        base_claims = [
            value
            for value in rows[0].get("claims") or []
            if isinstance(value, dict)
        ]
        gold_ids = {value["claim_id"] for value in item["claims"]}
        rows[0].update(
            {
                "claims": item["claims"]
                + [
                    value
                    for value in base_claims
                    if value.get("claim_id") not in gold_ids
                ],
                "investment_thesis_inventory": item[
                    "investment_thesis_inventory"
                ],
                "investment_thesis_coverage_audit": item[
                    "investment_thesis_coverage_audit"
                ],
                "investment_thesis_fact_checks": item[
                    "investment_thesis_fact_checks"
                ],
                "reader_briefing": item["reader_briefing"],
                "media_type": item["media_type"],
                "notification_revision": "complete-claim-gold-v4",
            }
        )
        Path(args.decision_bundle_output).write_text(
            json.dumps(base_bundle, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "validation": validation,
                "reader_message_utf8_bytes": len(message.encode("utf-8")),
                "external_side_effect_count": 0,
                "coordinator_source_video_bytes": 0,
                "transport_chunk_count": len(chunks),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
