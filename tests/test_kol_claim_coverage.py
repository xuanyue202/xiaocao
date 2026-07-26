from __future__ import annotations

import copy
import hashlib
import json

import pytest

from xiaocao.kol._shared import DecisionError
from xiaocao.kol.claim_coverage import (
    CONTRACT_VERSION,
    build_claim_extraction_request,
    evidence_segments,
    validate_claim_coverage,
)
from xiaocao.kol.rendering import render_household_item_message


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _covered_item(text: str) -> tuple[dict, str]:
    evidence_sha256 = _sha256_text(text)
    segments = evidence_segments(text, evidence_sha256=evidence_sha256)

    def segment_for(quote: str) -> str:
        for segment in segments:
            if quote in text[segment["start"]:segment["end"]]:
                return segment["segment_id"]
        raise AssertionError(f"quote not segmented: {quote}")

    first_quote = "我建议清仓甲公司"
    second_quote = "这项监管变化可能重写整个乙行业的盈利模型"
    theses = [
        {
            "thesis_id": "direct-exit",
            "role": "primary_recommendation",
            "decision_relevance": "must_surface",
            "importance_basis": ["explicit_recommendation"],
            "claim_ids": ["claim-exit"],
            "subject": "甲公司",
            "stance": "清仓",
            "horizon": "未提供",
            "attribution": "作者本人",
            "evidence_refs": [{
                "segment_id": segment_for(first_quote),
                "quotes": [first_quote],
            }],
            "priority": {
                "rank": 1,
                "urgency": "high",
                "potential_impact": "high",
                "specificity": "high",
                "user_relevance": "unknown",
                "reason": "明确清仓建议会直接改变风险暴露。",
            },
        },
        {
            "thesis_id": "industry-repricing",
            "role": "risk_warning",
            "decision_relevance": "must_surface",
            "importance_basis": ["material_impact_thesis"],
            "claim_ids": ["claim-repricing"],
            "subject": "乙行业",
            "stance": "盈利模型可能重估",
            "horizon": "监管变化发生后",
            "attribution": "作者本人",
            "evidence_refs": [{
                "segment_id": segment_for(second_quote),
                "quotes": [second_quote],
            }],
            "priority": {
                "rank": 2,
                "urgency": "medium",
                "potential_impact": "high",
                "specificity": "medium",
                "user_relevance": "unknown",
                "reason": "虽无买卖动作，但可能显著改变行业定价。",
            },
        },
    ]
    segment_theses: dict[str, list[str]] = {}
    for thesis in theses:
        for ref in thesis["evidence_refs"]:
            segment_theses.setdefault(ref["segment_id"], []).append(
                thesis["thesis_id"]
            )
    reviews = []
    for segment in segments:
        segment_text = text[segment["start"]:segment["end"]]
        linked = segment_theses.get(segment["segment_id"], [])
        if linked:
            disposition = "investment_content"
            reason = "包含已登记的投资论证。"
        elif "本节目由某平台赞助" in segment_text:
            disposition = "advertisement"
            reason = "纯赞助口播，直接排除。"
        else:
            disposition = "non_investment_content"
            reason = "不影响投资决策。"
        reviews.append(
            {
                "segment_id": segment["segment_id"],
                "disposition": disposition,
                "thesis_ids": linked,
                "reason": reason,
            }
        )
    item = {
        "author": "通用作者",
        "title": "通用来源",
        "published_at": "2026-07-26T08:00:00+08:00",
        "source": "local_transcript",
        "media_type": "text",
        "claims": [
            {"claim_id": "claim-exit", "quote": first_quote},
            {"claim_id": "claim-repricing", "quote": second_quote},
        ],
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
        "investment_thesis_fact_checks": [
            {
                "thesis_id": "direct-exit",
                "status": "unverified",
                "summary": "来源未给出足够事实，保留为作者建议。",
                "reader_visible": False,
            },
            {
                "thesis_id": "industry-repricing",
                "status": "unverified",
                "summary": "监管事件仍需按需核实。",
                "reader_visible": True,
            },
        ],
        "reader_briefing": {
            "format": "wecom_narrative_v1",
            "title": "投资情报｜通用作者：观点速览",
            "thesis_order": ["direct-exit", "industry-repricing"],
            "paragraphs": [
                {
                    "kind": "kol",
                    "thesis_ids": ["direct-exit"],
                    "text": "作者明确建议清仓甲公司，但没有给出具体时间和仓位。",
                },
                {
                    "kind": "kol",
                    "thesis_ids": ["industry-repricing"],
                    "text": (
                        "作者同时认为，某项监管变化可能重写整个乙行业"
                        "的盈利模型；这是重大影响判断，不因缺少买卖动作而省略。"
                    ),
                },
                {
                    "kind": "system",
                    "thesis_ids": ["industry-repricing"],
                    "text": "系统补充：该监管事件尚未核实，需要时再进一步调查。",
                },
            ],
        },
    }
    return item, evidence_sha256


def test_generic_request_has_no_known_author_asset_or_action_keyword_gate(tmp_path):
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    path = tmp_path / "source.txt"
    path.write_text(text, encoding="utf-8")

    request = build_claim_extraction_request(path)
    payload = json.dumps(request, ensure_ascii=False)

    assert request["contract_version"] == CONTRACT_VERSION
    assert request["segments"]
    assert request["required_output_schema"]["reader_briefing"]["format"] == (
        "wecom_narrative_v1"
    )
    assert "SpaceX" not in payload
    assert "路西法" not in payload
    assert "动作词组合" in payload
    assert "不得要求对象、方向、时间、仓位和风险同时齐全" in payload


def test_specific_recommendation_or_material_impact_each_must_surface():
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    item, evidence_sha256 = _covered_item(text)

    summary = validate_claim_coverage(
        item,
        evidence_text=text,
        evidence_sha256=evidence_sha256,
    )

    assert summary["must_surface_count"] == 2
    assert summary["must_surface_thesis_ids"] == [
        "direct-exit",
        "industry-repricing",
    ]
    advertisement = next(
        row
        for row in item["investment_thesis_coverage_audit"]["segment_reviews"]
        if row["disposition"] == "advertisement"
    )
    assert advertisement["thesis_ids"] == []


def test_uncertain_quoted_mention_stays_audit_visible_without_becoming_author_view():
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    item, evidence_sha256 = _covered_item(text)
    quoted = item["investment_thesis_inventory"]["theses"][1]
    quoted["decision_relevance"] = "audit_only"
    quoted["role"] = "quoted_view"
    quoted["importance_basis"] = []
    quoted["attribution"] = "群聊参与者，不能归属于作者"
    quoted.pop("priority")
    item["investment_thesis_fact_checks"] = [
        item["investment_thesis_fact_checks"][0]
    ]
    item["reader_briefing"]["thesis_order"] = ["direct-exit"]
    item["reader_briefing"]["paragraphs"] = [
        item["reader_briefing"]["paragraphs"][0]
    ]

    summary = validate_claim_coverage(
        item,
        evidence_text=text,
        evidence_sha256=evidence_sha256,
    )

    assert summary["thesis_count"] == 2
    assert summary["must_surface_thesis_ids"] == ["direct-exit"]


def test_independent_audit_must_cover_every_segment_and_clear_findings():
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    item, evidence_sha256 = _covered_item(text)
    missing_segment = copy.deepcopy(item)
    missing_segment["investment_thesis_coverage_audit"][
        "segment_reviews"
    ].pop()

    with pytest.raises(
        DecisionError,
        match="did not review every segment",
    ):
        validate_claim_coverage(
            missing_segment,
            evidence_text=text,
            evidence_sha256=evidence_sha256,
        )

    unresolved_merge = copy.deepcopy(item)
    unresolved_merge["investment_thesis_coverage_audit"]["findings"][
        "incorrect_merges"
    ] = ["同一标的的不同期限被合并"]
    with pytest.raises(
        DecisionError,
        match="unresolved findings",
    ):
        validate_claim_coverage(
            unresolved_merge,
            evidence_text=text,
            evidence_sha256=evidence_sha256,
        )


def test_reader_briefing_cannot_hide_or_reorder_a_must_surface_thesis():
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    item, evidence_sha256 = _covered_item(text)
    item["reader_briefing"]["paragraphs"].pop(1)

    with pytest.raises(
        DecisionError,
        match="every must-surface thesis",
    ):
        validate_claim_coverage(
            item,
            evidence_text=text,
            evidence_sha256=evidence_sha256,
        )


def test_reader_output_is_connected_wecom_prose_not_a_table():
    text = (
        "我建议清仓甲公司。\n"
        "这项监管变化可能重写整个乙行业的盈利模型。\n"
        "本节目由某平台赞助。"
    )
    item, _ = _covered_item(text)

    message = render_household_item_message(item)

    assert "作者明确建议清仓甲公司" in message
    assert "重大影响判断" in message
    assert "系统补充：" in message
    assert "| --- |" not in message
    assert "这只是决策信息，不会替你执行真实交易。" in message
