from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from xiaocao.kol.claim_coverage import CONTRACT_VERSION, evidence_segments


def attach_claim_contract(
    item: dict[str, Any],
    evidence_path: Path | str,
) -> dict[str, Any]:
    """Attach a minimal valid shared contract to legacy unit-test fixtures."""
    path = Path(evidence_path)
    text = path.read_text(encoding="utf-8")
    evidence_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    segments = evidence_segments(text, evidence_sha256=evidence_sha256)
    if not segments:
        raise AssertionError("claim-contract fixture needs non-empty evidence")

    def evidence_ref(quote: str) -> dict[str, Any]:
        for segment in segments:
            segment_text = text[segment["start"]:segment["end"]]
            if quote and quote in segment_text:
                return {
                    "segment_id": segment["segment_id"],
                    "quotes": [quote],
                }
        first = segments[0]
        fallback = text[first["start"]:first["end"]].strip()
        return {
            "segment_id": first["segment_id"],
            "quotes": [fallback],
        }

    theses = []
    paragraphs = []
    fact_checks = []
    segment_theses: dict[str, list[str]] = {}
    for rank, claim in enumerate(item.get("claims") or [], start=1):
        claim_id = str(claim["claim_id"])
        thesis_id = f"fixture-thesis-{rank}"
        quote = str(claim.get("quote") or "")
        ref = evidence_ref(quote)
        reader_text = str(
            claim.get("reader_quote")
            or claim.get("quote")
            or "来源包含一条投资判断"
        ).strip()
        if not reader_text.endswith(("。", "！", "？", ".", "!", "?")):
            reader_text += "。"
        theses.append(
            {
                "thesis_id": thesis_id,
                "role": "primary_recommendation",
                "decision_relevance": "must_surface",
                "importance_basis": ["explicit_recommendation"],
                "claim_ids": [claim_id],
                "subject": "测试来源主张",
                "stance": str(claim.get("direction") or "关注"),
                "horizon": str(claim.get("horizon") or "未提供"),
                "attribution": "作者本人",
                "evidence_refs": [ref],
                "priority": {
                    "rank": rank,
                    "urgency": "medium",
                    "potential_impact": "medium",
                    "specificity": "medium",
                    "user_relevance": "unknown",
                    "reason": "单元测试中的来源主张必须保持可见。",
                },
            }
        )
        paragraphs.append(
            {
                "kind": "kol",
                "thesis_ids": [thesis_id],
                "text": f"作者表示，{reader_text}",
            }
        )
        fact_checks.append(
            {
                "thesis_id": thesis_id,
                "status": "not_needed",
                "summary": "该单元测试不评估外部事实。",
                "reader_visible": False,
            }
        )
        segment_theses.setdefault(ref["segment_id"], []).append(thesis_id)

    item["investment_thesis_inventory"] = {
        "contract_version": CONTRACT_VERSION,
        "evidence_sha256": evidence_sha256,
        "theses": theses,
    }
    item["investment_thesis_coverage_audit"] = {
        "contract_version": CONTRACT_VERSION,
        "evidence_sha256": evidence_sha256,
        "review_mode": "independent_semantic_reread",
        "status": "passed",
        "findings": {
            "missing_theses": [],
            "incorrect_merges": [],
            "role_errors": [],
        },
        "segment_reviews": [
            {
                "segment_id": segment["segment_id"],
                "disposition": (
                    "investment_content"
                    if segment["segment_id"] in segment_theses
                    else "non_investment_content"
                ),
                "thesis_ids": segment_theses.get(segment["segment_id"], []),
                "reason": (
                    "包含测试来源主张。"
                    if segment["segment_id"] in segment_theses
                    else "该段不包含本测试关注的投资主张。"
                ),
            }
            for segment in segments
        ],
    }
    item["investment_thesis_fact_checks"] = fact_checks
    item["reader_briefing"] = {
        "format": "wecom_narrative_v1",
        "title": f"投资情报｜{item.get('author', 'KOL')}：观点速览",
        "thesis_order": [thesis["thesis_id"] for thesis in theses],
        "paragraphs": paragraphs,
    }
    item["evidence_sha256"] = evidence_sha256
    return item
