from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import xiaocao.kol.semantic_bundle as semantic_bundle
from xiaocao.kol.claim_coverage import build_claim_extraction_request
from xiaocao.kol.semantic_bundle import (
    SemanticBundleError,
    ValidatedBundleReceipt,
    build_validated_bundle,
    build_validated_bundle_from_files,
    read_validated_bundle,
    validate_existing_bundle,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[dict, dict, Path, Path, Path]:
    evidence = tmp_path / "evidence.md"
    evidence.write_text(
        "今天市场缩量，下一交易日先看成交额是否恢复。\n",
        encoding="utf-8",
    )
    evidence_sha = _sha(evidence)
    extraction = build_claim_extraction_request(
        evidence,
        evidence_sha256=evidence_sha,
    )
    segment = extraction["segments"][0]
    claim_id = "liquidity-claim"
    thesis_id = "liquidity-thesis"
    validation = {
        "status": "qualify",
        "as_of": "2026-08-08T07:00:00+08:00",
        "summary": "最新市场事实仍要求等待成交量确认。",
        "currentness": {
            "latest_available": True,
            "checked_at": "2026-08-08T07:00:00+08:00",
            "reason": "已读取处理时最新可用市场快照。",
        },
        "facts": [
            {
                "metric": "market_liquidity",
                "value": "contraction",
                "observed_at": "2026-08-08T06:59:00+08:00",
                "evidence": "market-snapshot://fixture",
            }
        ],
    }
    coverage = {
        "todays_market_diagnosis": {
            "status": "present",
            "evidence_quotes": ["今天市场缩量"],
            "reader_meaning": "当下量能不足。",
            "horizon": "当下",
            "triggers": ["成交额恢复"],
            "falsifiers": ["放量后仍普跌"],
        },
        "next_session_playbook": {
            "status": "present",
            "evidence_quotes": ["下一交易日先看成交额是否恢复"],
            "reader_meaning": "下一交易日先确认量能。",
            "horizon": "下一交易日",
            "triggers": ["成交额恢复"],
            "falsifiers": ["放量冲高回落"],
        },
        "next_several_session_base_case": {
            "status": "absent",
            "reason": "原文没有未来数日路径判断。",
        },
        "style_market_cap_regime": {
            "status": "absent",
            "reason": "原文没有风格或市值判断。",
        },
        "market_board_sector_hierarchy": {
            "status": "absent",
            "reason": "原文没有板块或行业层级。",
        },
        "position_risk_budget": {
            "status": "absent",
            "reason": "原文没有明确仓位区间。",
        },
        "named_asset_inventory": {
            "status": "absent",
            "reason": "原文没有点名资产。",
            "assets": [],
        },
    }
    claim_ref = {"segment_id": segment["segment_id"], "quotes": ["今天市场缩量"]}
    draft = {
        "decision_status": "actionable_signal",
        "knowledge_status": "no_reusable_knowledge",
        "knowledge_reason": "只有当下量能观察，没有可复用因果模型。",
        "claims": [
            {
                "claim_id": claim_id,
                "quote": "今天市场缩量",
                "reasoning": "量能不足时不能把短暂反弹当成趋势确认。",
                "asset_scope": ["A-share", "macro"],
                "direction": "defensive",
                "horizon": "下一交易日",
                "confidence": "medium",
                "falsifiers": ["成交额恢复且形成持续主线"],
            }
        ],
        "investment_thesis_inventory": {
            "contract_version": extraction["contract_version"],
            "evidence_sha256": evidence_sha,
            "theses": [
                {
                    "thesis_id": thesis_id,
                    "role": "primary_recommendation",
                    "decision_relevance": "must_surface",
                    "importance_basis": ["market_or_sector_view"],
                    "claim_ids": [claim_id],
                    "subject": "市场量能",
                    "stance": "量能不足时不把短暂反弹当成趋势确认。",
                    "horizon": "下一交易日",
                    "attribution": "作者本人",
                    "evidence_refs": [claim_ref],
                    "priority": {
                        "rank": 1,
                        "urgency": "medium",
                        "potential_impact": "medium",
                        "specificity": "medium",
                        "user_relevance": "unknown",
                        "reason": "量能直接影响下一交易日的风险暴露。",
                    },
                }
            ],
        },
        "investment_thesis_coverage_audit": {
            "contract_version": extraction["contract_version"],
            "evidence_sha256": evidence_sha,
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
                    "disposition": "investment_content",
                    "thesis_ids": [thesis_id],
                    "reason": "该段包含市场量能判断。",
                }
            ],
        },
        "investment_thesis_fact_checks": [
            {
                "thesis_id": thesis_id,
                "status": "not_needed",
                "summary": "本判断只需保留来源边界。",
                "reader_visible": False,
            }
        ],
        "trade_information_coverage": coverage,
        "actionable_signals": [
            {
                "signal_id": "wait-for-liquidity",
                "claim_ids": [claim_id],
                "action": "wait",
                "assets": [{"name": "A股整体", "market": "CN", "theme": "market-wide"}],
                "horizon": "下一交易日",
                "execution": "量能确认前不追涨。",
                "trigger": "成交额恢复。",
                "confidence": "medium",
                "falsifiers": ["放量后仍普跌"],
                "rationale": {
                    "news_or_event": [],
                    "fundamental": [],
                    "trading": ["最新市场成交仍未出现可信的持续放量。"],
                },
            }
        ],
        "market_outlook": {
            "scope": "A股整体",
            "claim_ids": [claim_id],
            "current_phase": "量能不足。",
            "base_case": "下一交易日先观察量能。",
            "strategy": ["量能确认前不追涨。"],
            "turning_points": ["成交额恢复"],
            "horizon": "下一交易日",
            "confidence": "medium",
            "falsifiers": ["放量后仍普跌"],
        },
        "synthesis": {
            "summary": "系统结合最新市场事实后保留等待建议。",
            "confidence": "medium",
        },
        "household_recommendation": {
            "action": "wait",
            "evidence": "来源与最新市场事实均未证明量能修复。",
            "confidence": "medium",
            "horizon": "下一交易日",
            "falsifier": "量价共振并形成持续主线。",
        },
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "decision": "no_trade",
            "reason": "没有可验证的美股上市标的。",
        },
        "content_value": {
            "status": "promoted",
            "tier": "report_only",
            "no_alert_reason": "当前没有需要即时提醒的新增动作。",
        },
        "publication": {
            "summary": "量能不足，下一交易日先观察成交额。",
            "remaining_summary": "不在确认不足时追涨。",
            "report_body": "# 核心判断\n\n量能不足，下一交易日先观察成交额。",
        },
        "reader_insight": {
            "status": "useful",
            "summary": "下一交易日先看成交额是否恢复。",
            "boundary": "量能没有确认前不追涨。",
        },
        "reader_briefing": {
            "format": "wecom_narrative_v1",
            "title": "投资情报｜小草：量能观察",
            "thesis_order": [thesis_id],
            "paragraphs": [{"kind": "kol", "thesis_ids": [thesis_id], "text": "量能不足。"}],
        },
        "longitudinal_projection": {
            "status": "none",
            "reason": "本条只保留当前交易日观察，不建立长期观点。",
            "viewpoints": [],
        },
    }
    request = {
        "schema_version": 1,
        "message_sha256": "1" * 64,
        "content_sha256": "2" * 64,
        "handoff_id": "handoff-fixture",
        "media_sha256": "3" * 64,
        "source": "小草直播",
        "author": "小草",
        "title": "小草直播：量能观察",
        "published_at": "2026-08-08T06:30:00+08:00",
        "captured_at": "2026-08-08T06:40:00+08:00",
        "media_type": "video",
        "source_identity": "capture-fixture",
        "source_version_key": "version-fixture",
        "evidence_path": str(evidence),
        "evidence_sha256": evidence_sha,
        "investment_claim_extraction": extraction,
        "market_evidence": {
            "sha256": "4" * 64,
            "validation": validation,
        },
    }
    bundle_path = tmp_path / "validated_bundle.json"
    receipt_path = tmp_path / "validated_bundle_receipt.json"
    return request, draft, bundle_path, receipt_path, evidence


def test_build_validated_bundle_persists_receipt_before_consumer_use(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)

    receipt = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )

    assert isinstance(receipt, ValidatedBundleReceipt)
    assert receipt.reused is False
    assert bundle_path.is_file()
    assert receipt_path.is_file()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    stored_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert bundle["schema_version"] == 2
    assert bundle["items"][0]["evidence_sha256"] == request["evidence_sha256"]
    assert bundle["items"][0]["market_validation"] == (
        request["market_evidence"]["validation"]
    )
    assert "idempotency_key" not in json.dumps(bundle, ensure_ascii=False)
    assert stored_receipt["bundle_sha256"] == receipt.bundle_sha256
    assert stored_receipt["receipt_sha256"] == receipt.receipt_sha256
    assert receipt.bindings["message_sha256"] == request["message_sha256"]
    assert receipt.bindings["market_evidence_sha256"] == "4" * 64


def test_build_validated_bundle_requires_captured_at(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    request.pop("captured_at")

    with pytest.raises(SemanticBundleError, match="source metadata is incomplete"):
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )


def test_source_metadata_change_invalidates_reusable_receipt(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    first = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )
    request["captured_at"] = "2026-08-08T06:41:00+08:00"

    second = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )

    assert second.reused is False
    assert second.receipt_sha256 != first.receipt_sha256
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["items"][0]["captured_at"] == request["captured_at"]


def test_file_builder_keeps_market_evidence_out_of_semantic_draft(tmp_path):
    request, draft, _, _, _ = _fixture(tmp_path)
    market_evidence = request.pop("market_evidence")
    request["artifact_dir"] = str(tmp_path / "artifacts")
    request_path = tmp_path / "analysis_request.json"
    draft_path = tmp_path / "semantic_draft.json"
    market_path = tmp_path / "market_evidence.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    draft_path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    market_path.write_text(
        json.dumps(market_evidence, ensure_ascii=False),
        encoding="utf-8",
    )

    receipt = build_validated_bundle_from_files(
        request_path,
        draft_path,
        market_path,
    )

    assert Path(receipt.bundle_path).is_file()
    assert Path(receipt.bundle_path).with_name(
        "validated_bundle_receipt.json"
    ).is_file()
    assert receipt.bindings["market_evidence_sha256"] == "4" * 64


def test_builder_rejects_claim_quote_not_bound_to_evidence(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["claims"][0]["quote"] = "校正后的观点不在逐字稿中"

    with pytest.raises(
        SemanticBundleError,
        match="claim quote is not evidence-bound",
    ) as caught:
        build_validated_bundle(
            request=request,
            semantic_draft=draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )

    assert caught.value.error_code == "coverage_not_evidence_bound"
    assert caught.value.stage == "coverage"
    assert caught.value.field == "claims[liquidity-claim].quote"


def test_builder_rejects_non_object_claim_before_downstream_processing(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["claims"] = ["not-an-object"]

    with pytest.raises(SemanticBundleError, match="claim row is invalid") as caught:
        build_validated_bundle(
            request=request,
            semantic_draft=draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )

    assert caught.value.error_code == "coverage_not_evidence_bound"
    assert caught.value.stage == "coverage"
    assert caught.value.field == "claims[0]"


def test_two_argument_builder_uses_request_artifact_directory(tmp_path):
    request, draft, _, _, _ = _fixture(tmp_path)
    request["artifact_dir"] = str(tmp_path / "artifacts")

    receipt = build_validated_bundle(request, draft)

    assert Path(receipt.bundle_path) == (tmp_path / "artifacts" / "validated_bundle.json").resolve()
    assert Path(receipt.bundle_path).is_file()
    assert (tmp_path / "artifacts" / "validated_bundle_receipt.json").is_file()


def test_candidate_projection_fails_before_artifact_or_receipt(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["longitudinal_projection"] = {
        "status": "candidate",
        "reason": "待后续确认",
        "viewpoints": [],
    }

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )

    assert caught.value.category == "semantic"
    assert caught.value.error_code == "longitudinal_projection_candidate"
    assert caught.value.stage == "longitudinal_projection"
    assert not bundle_path.exists()
    assert not receipt_path.exists()


def test_market_projection_and_segment_identity_are_single_source_of_truth(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["market_outlook"]["current_validation"] = {
        **request["market_evidence"]["validation"],
        "summary": "另一套市场判断。",
    }

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "market_projection_mismatch"

    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["investment_thesis_inventory"]["theses"][0]["evidence_refs"][0][
        "segment_id"
    ] = "not-a-request-segment"
    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "segment_identity_invalid"


def test_request_owns_metadata_and_segment_identity(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["title"] = "旧 bundle 标题"

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "semantic_draft_forbidden_field"

    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    request["investment_claim_extraction"]["segments"].append(
        dict(request["investment_claim_extraction"]["segments"][0])
    )
    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "segment_identity_invalid"


def test_market_and_decision_cardinality_are_terminal_constraints(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    del request["market_evidence"]["validation"]["currentness"]

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "market_validation_incomplete"

    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["actionable_signals"] = []
    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.error_code == "decision_semantics_invalid"


def test_alert_basis_is_validated_before_business_publication(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["content_value"] = {
        "status": "promoted",
        "tier": "alert_eligible",
        "reason": "来源给出当前市场姿态。",
        "alert_basis": ["market_posture", "risk_boundary"],
    }

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )

    assert caught.value.error_code == "content_value_invalid"
    assert caught.value.stage == "content_routing"
    assert caught.value.field == "content_value.alert_basis"
    assert not bundle_path.exists()
    assert not receipt_path.exists()


def test_synthesis_is_validated_before_business_publication(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["synthesis"] = {
        "kol_signal": "来源认为市场仍在轮动。",
        "system_judgment": "系统判断继续等待。",
        "household_action": "等待。",
        "book_action": "不交易。",
    }

    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )

    assert caught.value.error_code == "reader_copy_invalid"
    assert caught.value.stage == "reader_copy"
    assert caught.value.field == "synthesis"
    assert not bundle_path.exists()
    assert not receipt_path.exists()

    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    draft["synthesis"]["confidence"] = "certain"
    with pytest.raises(SemanticBundleError) as caught:
        build_validated_bundle(
            request,
            draft,
            bundle_path=bundle_path,
            receipt_path=receipt_path,
        )
    assert caught.value.field == "synthesis"


def test_receipt_reuse_does_not_change_external_identity_or_scan_evidence_again(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    first = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )
    second = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )

    assert second.reused is True
    assert second.bundle_sha256 == first.bundle_sha256
    assert second.receipt_sha256 == first.receipt_sha256
    assert second.bindings == first.bindings
    assert "idempotency" not in second.bindings


def test_valid_receipt_reuse_does_not_reread_transcript(tmp_path, monkeypatch):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )

    def fail_if_read(_request):
        raise AssertionError("receipt reuse reread the transcript")

    monkeypatch.setattr(semantic_bundle, "_validate_request", fail_if_read)
    reused = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )
    assert reused.reused is True


def test_persisted_artifact_readback_revalidates_receipt_and_corrupt_receipt_rebuilds(
    tmp_path,
):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    first = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )

    persisted, bundle = read_validated_bundle(bundle_path)
    assert persisted.reused is True
    assert bundle["validator_version"] == first.validator_version
    assert bundle["household_context_provider"] == {
        "type": "lianghui_mcp",
        "fresh_read_per_run": True,
    }

    receipt_path.write_text("{\"receipt_sha256\": \"broken\"}\n", encoding="utf-8")
    rebuilt = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )
    assert rebuilt.reused is False
    assert ValidatedBundleReceipt.from_dict(
        json.loads(receipt_path.read_text(encoding="utf-8"))
    ).bundle_sha256 == rebuilt.bundle_sha256


def test_legacy_validation_uses_same_complete_validator_without_writing_receipt(tmp_path):
    request, draft, bundle_path, receipt_path, _ = _fixture(tmp_path)
    first = build_validated_bundle(
        request,
        draft,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    validated = validate_existing_bundle(request, bundle)

    assert validated["schema_version"] == 2
    assert hashlib.sha256(
        (json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    ).hexdigest() == first.bundle_sha256
    assert receipt_path.is_file()
