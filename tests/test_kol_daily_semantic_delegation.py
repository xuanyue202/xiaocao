"""The hourly sole writer must enforce model routing before consuming a report."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import kol_daily
from tests.test_kol_semantic_bundle import _fixture
from xiaocao.kol.daily import DailyError
from xiaocao.kol.semantic_bundle import build_validated_bundle_from_files
from xiaocao.kol import semantic_delegation
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


def test_hourly_rejects_canonical_bundle_without_semantic_dispatch(tmp_path):
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


@pytest.mark.parametrize("packet_review", [False, True])
def test_hourly_accepts_bundle_from_immutable_context_revision(tmp_path, packet_review):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    first = prepare(request_path, market_evidence=market)
    revised_market = json.loads(market.read_text(encoding="utf-8"))
    revised_market["as_of"] = "2026-08-08T01:00:00Z"
    market.write_text(json.dumps(revised_market), encoding="utf-8")
    revised = prepare(request_path, market_evidence=market)
    assert Path(revised["packet_path"]).parent.name.startswith("context-")
    packet = json.loads(Path(revised["packet_path"]).read_text(encoding="utf-8"))
    draft_path = Path(packet["expected_outputs"]["semantic_draft.json"])
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    record_dispatch(
        request_path, packet_path=revised["packet_path"],
        agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
        invocation_args=revised["spawn_arguments_path"],
    )
    build_validated_bundle_from_files(request_path, draft_path, market)
    structural = verify_result(
        request_path, packet_path=revised["packet_path"], bundle_path=bundle,
        semantic_draft=draft_path, agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
    )
    review = {
        "decision": "accepted", "reviewer": "parent_main_agent",
        "reviewed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "independent_full_evidence_read": True,
        "reviewed_segment_ids": packet["segment_ids"],
        "bindings": {
            "analysis_request": packet["analysis_request"],
            "packet": {"path": revised["packet_path"], "sha256": revised["packet_sha256"]},
            "semantic_draft": structural["semantic_draft"], "bundle": structural["bundle"],
            "receipt": structural["receipt"], "knowledge_draft": None,
        },
        "checks": {name: {"status": "passed", "evidence": "Full fixture review passed."}
                   for name in PARENT_REVIEW_CHECKS},
    }
    review_path = (
        Path(revised["packet_path"]).with_name("parent_source_review.json")
        if packet_review else request_path.with_name("parent_source_review.json")
    )
    review_path.write_text(
        json.dumps(review), encoding="utf-8"
    )
    assert Path(first["packet_path"]) != Path(revised["packet_path"])
    assert kol_daily._require_canonical_semantic_artifact(bundle, request) == bundle
    if packet_review:
        request_path.with_name("parent_source_review.json").write_text(
            json.dumps(review), encoding="utf-8"
        )
        review_path.write_text(
            json.dumps({**review, "decision": "changes_required"}), encoding="utf-8"
        )
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


def test_changed_contract_remains_exact_semantic_input_wait(tmp_path, monkeypatch):
    references = tmp_path / "references"
    references.mkdir()
    for name in ("full-contract.md", "durable-knowledge.md"):
        shutil.copy2(semantic_delegation.REFERENCES / name, references / name)
    monkeypatch.setattr(semantic_delegation, "REFERENCES", references)
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    prepared = prepare(request_path, market_evidence=market)
    packet = json.loads(Path(prepared["packet_path"]).read_text())
    draft_path = Path(packet["expected_outputs"]["semantic_draft.json"])
    draft_path.write_text(json.dumps(draft))
    record_dispatch(
        request_path, packet_path=prepared["packet_path"],
        agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
        invocation_args=prepared["spawn_arguments_path"],
    )
    build_validated_bundle_from_files(request_path, draft_path, market)
    Path(prepared["packet_path"]).with_name("parent_source_review.json").write_text("{}")
    contract = references / "durable-knowledge.md"
    contract.write_text(contract.read_text() + "\nChanged after dispatch.\n")
    original_request = request_path.read_bytes()

    with pytest.raises(kol_daily.SemanticInputUnavailable, match="binding changed") as caught:
        kol_daily._require_canonical_semantic_artifact(bundle, request)

    assert caught.value.request == request
    assert caught.value.field == "bundle_path"
    assert request_path.read_bytes() == original_request
    result = kol_daily._classified_narrow_source(
        "subscription_video",
        lambda _surface: kol_daily._require_canonical_semantic_artifact(bundle, request),
    )("subscription_video:source")
    assert result["writer_progress"]["status"] == "structured_input"
    assert result["writer_progress"]["response_field"] == "bundle_path"
    waiting = result["waiting_items"][0]
    assert waiting["analysis_request_path"] == str(request_path)
    assert waiting["evidence_sha256"] == request["evidence_sha256"]
    assert "binding changed" in waiting["input_error"]
    runtime = kol_daily.DailyRuntime.__new__(kol_daily.DailyRuntime)
    runtime.args = SimpleNamespace(
        xiaocao_output_dir=tmp_path / "xiaocao",
        decision_output_dir=tmp_path / "decisions",
    )
    monkeypatch.setattr(kol_daily, "XiaocaoLiveService", lambda *_a, **_k: SimpleNamespace(
        import_handoff_capsule=lambda _capsule: None,
    ))
    targets = []

    def process_target(*, handoff_id):
        targets.append(handoff_id)
        return kol_daily._require_canonical_semantic_artifact(bundle, request)

    runtime.xiaocao = process_target
    message_id = "a" * 64
    result = runtime._process_mailbox_message({
        "message_id": message_id,
        "payload": {"handoff_id": message_id, "source_mode": "cloud_handoff"},
    })
    assert targets == [message_id]
    assert result["business_complete"] is False
    assert result["writer_progress"]["status"] == "structured_input"
    assert result["writer_progress"]["item_identity"] == message_id
    assert result["writer_progress"]["response_field"] == "bundle_path"
    assert result["waiting_items"][0]["analysis_request_path"] == str(request_path)
    assert request_path.read_bytes() == original_request


def test_packet_parent_review_does_not_fall_back_for_invalid_file(tmp_path):
    request = tmp_path / "analysis_request.json"
    packet = tmp_path / "context" / "context_packet.json"
    packet.parent.mkdir()
    root_review = request.with_name("parent_source_review.json")
    root_review.write_text('{"decision":"accepted"}', encoding="utf-8")
    assert kol_daily._semantic_parent_review_path(packet, request) == root_review
    packet_review = packet.with_name("parent_source_review.json")
    packet_review.write_text("invalid review", encoding="utf-8")
    assert kol_daily._semantic_parent_review_path(packet, request) == packet_review


def test_missing_parent_review_reports_the_required_evidence(tmp_path):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    prepared = prepare(request_path, market_evidence=market)
    packet_path = Path(prepared["packet_path"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    draft_path = Path(packet["expected_outputs"]["semantic_draft.json"])
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    record_dispatch(
        request_path, packet_path=packet_path,
        agent_id="019a7213-73b4-7351-87c4-13e1234abcde",
        invocation_args=prepared["spawn_arguments_path"],
    )
    build_validated_bundle_from_files(request_path, draft_path, market)
    packet_path.with_name("parent_semantic_review.json").write_text(
        '{"decision":"accepted"}', encoding="utf-8"
    )
    with pytest.raises(
        kol_daily.SemanticInputUnavailable, match="parent full-source review is missing"
    ) as caught:
        kol_daily._require_canonical_semantic_artifact(bundle, request)
    assert caught.value.request == request
    assert caught.value.field == "bundle_path"


def test_semantic_stdin_prompt_exposes_consumer_parent_review_paths(tmp_path, monkeypatch):
    request, request_path, draft, market, bundle = _inputs(tmp_path)
    prepared = prepare(request_path, market_evidence=market)
    packet = json.loads(Path(prepared['packet_path']).read_text())
    draft_path = Path(packet['expected_outputs']['semantic_draft.json'])
    draft_path.write_text(json.dumps(draft))
    record_dispatch(request_path, packet_path=prepared['packet_path'],
                    agent_id='019a7213-73b4-7351-87c4-13e1234abcde',
                    invocation_args=prepared['spawn_arguments_path'])
    build_validated_bundle_from_files(request_path, draft_path, market)
    prompts = []
    monkeypatch.setattr(kol_daily, '_read_agent_line',
                        lambda prompt: prompts.append(prompt) or json.dumps({'bundle_path': str(bundle)}))
    assert kol_daily._read_agent_path(request, 'bundle_path') == bundle
    contract = prompts[0]['parent_source_review_contract']
    packet_review = Path(prepared['packet_path']).with_name('parent_source_review.json')
    assert str(packet_review) in contract['packet_review_paths']
    assert contract['request_review_path'] == str(request_path.with_name('parent_source_review.json'))
    assert contract['required_status'] == 'parent_accepted'
    with pytest.raises(DailyError, match='parent full-source review is missing'):
        kol_daily._require_canonical_semantic_artifact(bundle, request)
    # The advertised fallback is the exact path used by the production consumer.
    fallback = Path(contract['request_review_path'])
    structural = verify_result(
        request_path, packet_path=prepared['packet_path'], bundle_path=bundle,
        semantic_draft=draft_path, agent_id='019a7213-73b4-7351-87c4-13e1234abcde',
    )
    fallback.write_text(json.dumps({
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
        "checks": {name: {"status": "passed", "evidence": "Fixture independently reviewed."}
                   for name in PARENT_REVIEW_CHECKS},
    }))
    assert kol_daily._require_canonical_semantic_artifact(bundle, request) == bundle
    assert 'parent_source_review_contract' not in request
