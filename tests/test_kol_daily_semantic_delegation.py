"""The hourly sole writer must enforce model routing before consuming a report."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import kol_daily
from tests.test_kol_semantic_bundle import _fixture
from xiaocao.kol.daily import DailyError
from xiaocao.kol.semantic_bundle import build_validated_bundle_from_files
from xiaocao.kol.semantic_delegation import (
    PARENT_REVIEW_CHECKS, prepare, record_dispatch, verify_result,
)


def _inputs(tmp_path):
    request, draft, bundle, _receipt, _evidence = _fixture(tmp_path)
    market = tmp_path / "market.json"
    market.write_text(json.dumps(request.pop("market_evidence")), encoding="utf-8")
    request_path = tmp_path / "analysis_request.json"
    request["analysis_request_path"] = str(request_path)
    request["artifact_dir"] = str(tmp_path)
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request, request_path, draft, market, bundle


def test_hourly_rejects_canonical_bundle_without_astra_dispatch(tmp_path):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    build_validated_bundle_from_files(request_path, draft_path, market)
    with pytest.raises(DailyError, match="semantic delegation"):
        kol_daily._require_canonical_semantic_artifact(bundle, request)


def test_hourly_accepts_only_bound_dispatch_and_unchanged_draft(tmp_path):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    prepared = prepare(request_path, market_evidence=market)
    packet = json.loads(Path(prepared["packet_path"]).read_text(encoding="utf-8"))
    draft_path = Path(packet["expected_outputs"]["semantic_draft.json"])
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    record_dispatch(
        request_path, packet_path=prepared["packet_path"],
        agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
        invocation_args=prepared["spawn_arguments_path"],
    )
    build_validated_bundle_from_files(request_path, draft_path, market)
    with pytest.raises(DailyError, match="semantic delegation"):
        kol_daily._require_canonical_semantic_artifact(bundle, request)
    structural = verify_result(
        request_path, packet_path=prepared["packet_path"], bundle_path=bundle,
        semantic_draft=draft_path, agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
    )
    review = {
        "decision": "accepted", "reviewer": "parent_main_agent",
        "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "independent_full_evidence_read": True,
        "reviewed_segment_ids": packet["segment_ids"],
        "bindings": {
            "analysis_request": packet["analysis_request"],
            "packet": {"path": prepared["packet_path"], "sha256": prepared["packet_sha256"]},
            "semantic_draft": structural["semantic_draft"], "bundle": structural["bundle"],
            "receipt": structural["receipt"], "knowledge_draft": None,
        },
        "checks": {name: {"status": "passed", "evidence": "Full fixture claim and reader copy matched."}
                   for name in PARENT_REVIEW_CHECKS},
    }
    review_path = request_path.with_name("parent_source_review.json")
    review_path.write_text(json.dumps(review), encoding="utf-8")
    assert kol_daily._require_canonical_semantic_artifact(bundle, request) == bundle
    for field, bad_value in (
        ("reviewed_segment_ids", []),
        ("independent_full_evidence_read", False),
        ("decision", "changes_required"),
        ("checks", {name: {"status": "passed"} for name in PARENT_REVIEW_CHECKS}),
    ):
        review_path.write_text(json.dumps({**review, field: bad_value}), encoding="utf-8")
        with pytest.raises(DailyError, match="semantic delegation"):
            kol_daily._require_canonical_semantic_artifact(bundle, request)
    review_path.write_text(json.dumps(review), encoding="utf-8")
    draft["publication"]["report_body"] += "不属于原审批的新内容。"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    with pytest.raises(DailyError, match="semantic delegation"):
        kol_daily._require_canonical_semantic_artifact(bundle, request)


def test_other_authors_keep_existing_canonical_route(tmp_path):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    request["author"] = "另一位作者"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    build_validated_bundle_from_files(request_path, draft_path, market)
    assert kol_daily._require_canonical_semantic_artifact(bundle, request) == bundle
