"""Deterministic handoff regressions using the existing canonical semantic fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import subprocess
from pathlib import Path

import pytest

from tests.test_kol_semantic_bundle import _fixture
from xiaocao.kol import semantic_bundle as canonical
from xiaocao.kol import semantic_delegation as delegation
from xiaocao.kol.claim_coverage import build_claim_extraction_request


AGENT_ID = "019a7213-73b4-7351-87c4-13e1234abcde"
OTHER_AGENT_ID = "019a7213-73b4-7351-87c4-13e1234abcd0"


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _read(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    request, draft, bundle, receipt, evidence = _fixture(tmp_path)
    market = _write(tmp_path / "market.json", request.pop("market_evidence"))
    request["artifact_dir"] = str(tmp_path)
    path = _write(tmp_path / "analysis_request.json", request)
    draft_path = _write(tmp_path / "draft.json", draft)
    household = _write(tmp_path / "household.json", {"as_of": "2026-08-08", "holdings": []})
    return {"request": path, "draft": draft_path, "market": market, "household": household,
            "bundle": bundle, "receipt": receipt, "evidence": evidence}


def _prepare(inputs):
    return delegation.prepare(inputs["request"], market_evidence=inputs["market"],
                              household_context=inputs["household"])


def _dispatch(inputs, prepared):
    return delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                      agent_id=AGENT_ID, invocation_args=prepared["spawn_arguments_path"])


def _bundle(inputs):
    canonical.build_validated_bundle_from_files(inputs["request"], inputs["draft"], inputs["market"])


def _verify(inputs, prepared, **overrides):
    args = {"packet_path": prepared["packet_path"], "bundle_path": inputs["bundle"],
            "agent_id": AGENT_ID, "semantic_draft": inputs["draft"]}
    return delegation.verify_result(inputs["request"], **{**args, **overrides})


def test_complete_context_receipt_roundtrip_is_local_and_idempotent(inputs, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("The helper attempted external I/O or bundle rebuilding")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    request_before = inputs["request"].read_bytes()
    prepared = _prepare(inputs)
    packet = _read(prepared["packet_path"])
    assert packet["analysis_request"]["sha256"] == _sha(inputs["request"])
    assert packet["evidence"]["sha256"] == _sha(inputs["evidence"])
    assert packet["market_evidence"]["sha256"] == _sha(inputs["market"])
    assert packet["household_context"]["sha256"] == _sha(inputs["household"])
    assert packet["segment_ids"] == [row["segment_id"] for row in _read(inputs["request"])["investment_claim_extraction"]["segments"]]
    assert packet["source_metadata"]["author"] == "小草"
    assert all(Path(ref["path"]).is_absolute() for ref in packet["contracts"].values())
    prompt = prepared["spawn_arguments"]["message"]
    for requirement in ("COMPLETELY to EOF", "WHOLE immutable evidence", "Pass 1", "Pass 2",
                        "EVERY segment", "complete reader report", "durable-knowledge.md", "No external writers"):
        assert requirement in prompt
    assert prepared["spawn_arguments"]["fork_context"] is False
    dispatch = _dispatch(inputs, prepared)
    assert dispatch["agent_id"] == AGENT_ID
    assert dispatch["recorded_at"].endswith("Z")
    assert dispatch["provenance"] == "parent_reported_not_service_attested"
    _bundle(inputs)
    monkeypatch.setattr(canonical, "build_validated_bundle", forbidden)
    monkeypatch.setattr(canonical, "build_validated_bundle_from_files", forbidden)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in inputs["request"].parent.rglob("*") if p.is_file()}
    result = _verify(inputs, prepared)
    assert result["status"] == "verified"
    assert result["market_input_projection_checked"] is True
    assert result["limitations"] == delegation.LIMITATIONS
    assert _prepare(inputs) == prepared
    assert _dispatch(inputs, prepared) == dispatch
    assert _verify(inputs, prepared) == result
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in inputs["request"].parent.rglob("*") if p.is_file()}
    assert inputs["request"].read_bytes() == request_before


@pytest.mark.parametrize("field,value", [("model", "gpt-5.6-luna"), ("reasoning_effort", "high"),
                                         ("fork_context", True), ("fork_context", 0), ("message", "summary only")])
def test_wrong_dispatch_arguments_block(inputs, field, value):
    prepared = _prepare(inputs)
    args = {**prepared["spawn_arguments"], field: value}
    path = _write(inputs["request"].parent / "actual_args.json", args)
    with pytest.raises(delegation.DelegationError, match="Invocation"):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=AGENT_ID, invocation_args=path)
    assert not Path(prepared["packet_path"]).with_name("dispatch.json").exists()


@pytest.mark.parametrize("agent_id", ["", "failed", "{\"error\":\"spawn failed\"}", "agent-placeholder",
                                     "00000000-0000-0000-0000-000000000000"])
def test_empty_failure_or_placeholder_agent_ids_block(inputs, agent_id):
    prepared = _prepare(inputs)
    with pytest.raises(delegation.DelegationError, match="UUID"):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=agent_id, invocation_args=prepared["spawn_arguments_path"])


def test_missing_dispatch_and_wrong_returned_agent_block(inputs):
    prepared = _prepare(inputs)
    _bundle(inputs)
    with pytest.raises(delegation.DelegationError, match="Missing accepted dispatch"):
        _verify(inputs, prepared)
    _dispatch(inputs, prepared)
    with pytest.raises(delegation.DelegationError, match="agent ID mismatch"):
        _verify(inputs, prepared, agent_id=OTHER_AGENT_ID)
    original = Path(prepared["packet_path"]).with_name("dispatch.json").read_bytes()
    with pytest.raises(delegation.DelegationError, match="Conflicting dispatch"):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=OTHER_AGENT_ID, invocation_args=prepared["spawn_arguments_path"])
    assert Path(prepared["packet_path"]).with_name("dispatch.json").read_bytes() == original


@pytest.mark.parametrize("target", ["evidence", "request", "market", "household", "contract", "durable", "prompt", "packet"])
def test_input_changes_block_without_modifying_sealed_bundle(inputs, monkeypatch, target, tmp_path):
    refs = tmp_path / "contracts"
    refs.mkdir()
    for name in ("full-contract.md", "durable-knowledge.md"):
        (refs / name).write_bytes((delegation.REFERENCES / name).read_bytes())
    monkeypatch.setattr(delegation, "REFERENCES", refs)
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    before = (inputs["bundle"].read_bytes(), inputs["receipt"].read_bytes())
    paths = {**inputs, "contract": refs / "full-contract.md", "durable": refs / "durable-knowledge.md",
             "prompt": Path(prepared["analyst_prompt_path"]), "packet": Path(prepared["packet_path"])}
    path = paths[target]
    path.write_bytes(path.read_bytes() + b"\n ")
    with pytest.raises((delegation.DelegationError, canonical.SemanticBundleError)):
        _verify(inputs, prepared)
    assert (inputs["bundle"].read_bytes(), inputs["receipt"].read_bytes()) == before


def test_tampered_evidence_blocks_prepare_before_any_output(inputs):
    inputs["evidence"].write_text("Changed evidence", encoding="utf-8")
    with pytest.raises(canonical.SemanticBundleError, match="hash"):
        _prepare(inputs)
    assert not (inputs["request"].parent / ".semantic_delegation").exists()


@pytest.mark.parametrize("target", ["bundle", "receipt", "draft", "dispatch"])
def test_tampered_result_or_dispatch_blocks(inputs, target):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    path = inputs.get(target, Path(prepared["packet_path"]).with_name("dispatch.json"))
    value = _read(path)
    if target == "bundle":
        value["items"][0]["publication"]["report_body"] += " changed"
    elif target == "receipt":
        value["bindings"]["source_identity"] = "other"
    elif target == "draft":
        value["knowledge_reason"] += " changed"
    else:
        value["invocation_args"]["model"] = "gpt-5.6-luna"
    _write(path, value)
    with pytest.raises((delegation.DelegationError, canonical.SemanticBundleError)):
        _verify(inputs, prepared)


def test_unrelated_valid_receipt_cannot_substitute_same_evidence(inputs):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    request = {**_read(inputs["request"]), "source_identity": "another-source",
               "market_evidence": _read(inputs["market"])}
    canonical.build_validated_bundle(request, _read(inputs["draft"]))
    with pytest.raises(canonical.SemanticBundleError, match="current item"):
        _verify(inputs, prepared)


@pytest.mark.parametrize("shape", ["aliases", "subscription_video", "embedded_market", "absent_extraction", "no_market"])
def test_supported_request_shapes_and_precise_market_check_scope(inputs, shape):
    request = _read(inputs["request"])
    if shape == "aliases":
        for first, second in (("source_identity", "identity"), ("source_version_key", "version_key"),
                              ("evidence_path", "transcript_path"), ("evidence_sha256", "transcript_sha256"),
                              ("investment_claim_extraction", "claim_extraction")):
            request[second] = request.pop(first)
    if shape == "subscription_video":
        contract = delegation.REFERENCES / "full-contract.md"
        request.update(event="subscription_video_analysis_input_required", full_contract_path=str(contract),
                       full_contract_sha256=_sha(contract))
    if shape == "embedded_market":
        request["market_evidence"] = _read(inputs["market"])
    if shape == "absent_extraction":
        del request["investment_claim_extraction"]
    _write(inputs["request"], request)
    market = None if shape in {"embedded_market", "no_market"} else inputs["market"]
    prepared = delegation.prepare(inputs["request"], market_evidence=market)
    _dispatch(inputs, prepared)
    canonical.build_validated_bundle({**request, "market_evidence": _read(inputs["market"])}, _read(inputs["draft"]))
    assert _verify(inputs, prepared)["market_input_projection_checked"] is (shape != "no_market")


def test_full_segment_packet_and_component_hash_without_media_reads(inputs, monkeypatch):
    request = _read(inputs["request"])
    # Only deterministic text fixtures; no new KOL semantic judgments.
    inputs["evidence"].write_text("\n\n".join(f"Segment {n}: " + "source text " * 100 for n in range(8)), encoding="utf-8")
    request["evidence_sha256"] = _sha(inputs["evidence"])
    request["investment_claim_extraction"] = build_claim_extraction_request(inputs["evidence"])
    component = inputs["request"].parent / "component.txt"
    component.write_text("Complete component evidence", encoding="utf-8")
    request["component_evidence"] = [{"transcript_path": str(component), "transcript_sha256": _sha(component)}]
    request["video_path"] = str(inputs["request"].parent / "must-not-open.mp4")
    _write(inputs["request"], request)
    prepared = _prepare(inputs)
    packet = _read(prepared["packet_path"])
    assert len(packet["segment_ids"]) > 1
    assert packet["segment_ids"] == [row["segment_id"] for row in request["investment_claim_extraction"]["segments"]]
    assert packet["component_evidence"][0]["sha256"] == _sha(component)
    component.write_text("changed", encoding="utf-8")
    with pytest.raises(delegation.DelegationError, match="Component evidence hash changed"):
        _dispatch(inputs, prepared)


def test_cli_json_outputs_and_blocked_exit(inputs, capsys):
    path = delegation.REPO_ROOT / "scripts/kol_semantic_delegation.py"
    spec = importlib.util.spec_from_file_location("delegation_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["prepare", "--analysis-request", str(inputs["request"]),
                     "--market-evidence", str(inputs["market"])]) == 0
    prepared = json.loads(capsys.readouterr().out)
    common = ["--analysis-request", str(inputs["request"]), "--packet", prepared["packet_path"], "--agent-id", AGENT_ID]
    verifying = ["verify-result", *common, "--bundle", str(inputs["bundle"]), "--semantic-draft", str(inputs["draft"])]
    assert cli.main(verifying) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert cli.main(["record-dispatch", *common, "--invocation-args", prepared["spawn_arguments_path"]]) == 0
    assert json.loads(capsys.readouterr().out)["agent_id"] == AGENT_ID
    _bundle(inputs)
    assert cli.main(verifying) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"


def test_parent_can_install_consumption_guard_in_canonical_reader_without_recursion(inputs, monkeypatch):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    original_reader = canonical.read_validated_bundle
    reader_calls = []

    def guarded_reader(*args, **kwargs):
        reader_calls.append(1)
        assert len(reader_calls) == 1, "Consumption guard reentered the canonical reader"
        receipt, bundle = original_reader(*args, **kwargs)
        result = delegation.verify_consumption_guard(
            inputs["request"], packet_path=prepared["packet_path"], agent_id=AGENT_ID,
            semantic_draft=inputs["draft"], receipt=receipt, bundle=bundle,
        )
        assert result["status"] == "verified"
        return receipt, bundle

    monkeypatch.setattr(canonical, "read_validated_bundle", guarded_reader)
    assert _verify(inputs, prepared)["status"] == "verified"
    assert reader_calls == [1]


def _continuation(inputs, prepared):
    original = {**delegation.DISPATCH_PARAMETERS, "message": "Original complete context before the helper existed."}
    delivery = {
        "invocation_args": {"target": AGENT_ID, "message": prepared["spawn_arguments"]["message"], "interrupt": False},
        "result": {"submission_id": "019a7abc-8371-7290-8a04-67459bd354a9"},
    }
    directory = inputs["request"].parent
    return (_write(directory / "original_spawn.json", original), _write(directory / "delivery.json", delivery))


def test_existing_agent_context_delivery_roundtrip_preserves_original_spawn(inputs):
    prepared = _prepare(inputs)
    original, delivery = _continuation(inputs, prepared)
    original_bytes = original.read_bytes()
    record = delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                        agent_id=AGENT_ID, invocation_args=original, context_delivery=delivery)
    assert record["dispatch_kind"] == "existing_agent_context_delivery"
    assert record["original_invocation_provenance"] == "full_args"
    assert record["invocation_args"] == _read(original)
    assert record["context_delivery"]["submission_id"] == _read(delivery)["result"]["submission_id"]
    assert record["context_delivery"]["file"]["sha256"] == _sha(delivery)
    assert original.read_bytes() == original_bytes
    _bundle(inputs)
    result = _verify(inputs, prepared)
    assert result["status"] == "verified"
    assert result["dispatch_kind"] == "existing_agent_context_delivery"
    assert result["context_submission_id"] == record["context_delivery"]["submission_id"]
    assert delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                      agent_id=AGENT_ID, invocation_args=original, context_delivery=delivery) == record
    delivery.write_bytes(delivery.read_bytes() + b"\n")
    with pytest.raises(delegation.DelegationError, match="Dispatch binding"):
        _verify(inputs, prepared)


@pytest.mark.parametrize("problem", ["no_delivery", "wrong_model", "wrong_effort", "forked_context", "wrong_agent",
                                   "summary_message", "failed_result", "empty_submission", "agent_as_submission"])
def test_existing_agent_requires_fixed_route_and_exact_accepted_context_delivery(inputs, problem):
    prepared = _prepare(inputs)
    original, delivery = _continuation(inputs, prepared)
    args = _read(original)
    value = _read(delivery)
    if problem == "wrong_model":
        args["model"] = "gpt-5.6-luna"
    elif problem == "wrong_effort":
        args["reasoning_effort"] = "high"
    elif problem == "forked_context":
        args["fork_context"] = True
    elif problem == "wrong_agent":
        value["invocation_args"]["target"] = OTHER_AGENT_ID
    elif problem == "summary_message":
        value["invocation_args"]["message"] = "Summary only, model gpt-6-astra xhigh"
    elif problem == "failed_result":
        value["result"] = {"error": "send_input failed"}
    elif problem == "empty_submission":
        value["result"]["submission_id"] = ""
    elif problem == "agent_as_submission":
        value["result"]["submission_id"] = AGENT_ID
    _write(original, args)
    _write(delivery, value)
    with pytest.raises(delegation.DelegationError):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=AGENT_ID, invocation_args=original,
                                   context_delivery=None if problem == "no_delivery" else delivery)
    assert not Path(prepared["packet_path"]).with_name("dispatch.json").exists()


def test_migrated_parameters_only_continuation_requires_actual_target_delivery(inputs):
    # Match the pilot: exact persisted packet without optional context; no retained spawn message.
    prepared = delegation.prepare(inputs["request"])
    original, delivery = _continuation(inputs, prepared)
    _write(original, dict(delegation.DISPATCH_PARAMETERS))
    artifacts = [Path(prepared[key]) for key in ("packet_path", "analyst_prompt_path", "spawn_arguments_path")]
    before = {path: path.read_bytes() for path in artifacts}
    with pytest.raises(delegation.DelegationError, match="original message"):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=AGENT_ID, invocation_args=original)
    record = delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                        agent_id=AGENT_ID, invocation_args=original, context_delivery=delivery)
    assert record["original_invocation_provenance"] == "original_parameters_only"
    assert record["invocation_args"] == delegation.DISPATCH_PARAMETERS
    assert "message" not in record["invocation_args"]
    assert record["context_delivery"]["invocation_args"]["target"] == AGENT_ID
    _bundle(inputs)
    result = _verify(inputs, prepared)
    assert result["original_invocation_provenance"] == "original_parameters_only"
    assert result["market_input_projection_checked"] is False
    assert result["semantic_acceptance"]["status"] == "not_assessed"
    assert {path: path.read_bytes() for path in artifacts} == before


@pytest.mark.parametrize("problem", ["old_id_field", "wrong_target", "wrong_model", "missing_effort", "missing_fork", "failed_submission"])
def test_parameters_only_migration_still_fails_closed(inputs, problem):
    prepared = _prepare(inputs)
    original, delivery = _continuation(inputs, prepared)
    retained = dict(delegation.DISPATCH_PARAMETERS)
    value = _read(delivery)
    if problem == "old_id_field":
        value["invocation_args"]["id"] = value["invocation_args"].pop("target")
    elif problem == "wrong_target":
        value["invocation_args"]["target"] = OTHER_AGENT_ID
    elif problem == "wrong_model":
        retained["model"] = "gpt-5.6-luna"
    elif problem == "missing_effort":
        del retained["reasoning_effort"]
    elif problem == "missing_fork":
        del retained["fork_context"]
    else:
        value["result"] = {"error": "send_input failed"}
    _write(original, retained)
    _write(delivery, value)
    with pytest.raises(delegation.DelegationError):
        delegation.record_dispatch(inputs["request"], packet_path=prepared["packet_path"],
                                   agent_id=AGENT_ID, invocation_args=original, context_delivery=delivery)
    assert not Path(prepared["packet_path"]).with_name("dispatch.json").exists()


def _parent_review(inputs, prepared):
    """Synthetic review metadata for tests, never a review of a live KOL item."""
    packet = _read(prepared["packet_path"])
    review = {
        "reviewer": "parent_main_agent", "decision": "accepted",
        "reviewed_at": "2026-08-08T00:00:00Z", "independent_full_evidence_read": True,
        "reviewed_segment_ids": packet["segment_ids"],
        "bindings": {
            "analysis_request": packet["analysis_request"],
            "packet": {"path": prepared["packet_path"], "sha256": _sha(Path(prepared["packet_path"]))},
            **{name: {"path": str(inputs[key]), "sha256": _sha(inputs[key])}
               for name, key in (("semantic_draft", "draft"), ("bundle", "bundle"), ("receipt", "receipt"))},
            "knowledge_draft": None,
        },
        "checks": {key: {"status": "passed", "evidence": "Synthetic fixture review notes for " + key}
                   for key in delegation.PARENT_REVIEW_CHECKS},
    }
    return _write(inputs["request"].parent / "parent_review.json", review)


def test_product_acceptance_is_separate_from_structural_validation_and_packet_stays_stable(inputs):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    result = _verify(inputs, prepared)
    assert result["status"] == "verified"
    assert result["semantic_acceptance"]["status"] == "not_assessed"
    review_path = _parent_review(inputs, prepared)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in inputs["request"].parent.rglob("*") if p.is_file()}
    reviewed = _verify(inputs, prepared, semantic_review=review_path)
    assert reviewed["semantic_acceptance"]["status"] == "parent_accepted"
    assert "parent assertions" in reviewed["semantic_acceptance"]["limitations"]
    assert _prepare(inputs) == prepared
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in inputs["request"].parent.rglob("*") if p.is_file()}
    review = _read(review_path)
    review["decision"] = "changes_required"
    review["checks"]["reader_report_quality"]["status"] = "failed"
    _write(review_path, review)
    reviewed = _verify(inputs, prepared, semantic_review=review_path)
    assert reviewed["status"] == "verified"  # Only the explicitly named structural scope.
    assert reviewed["semantic_acceptance"]["status"] == "changes_required"


@pytest.mark.parametrize("problem", ["wrong_reviewer", "not_independent", "missing_segment", "missing_check",
                                    "empty_evidence", "accepted_failed_check", "wrong_bundle", "wrong_request"])
def test_parent_review_requires_independent_complete_and_exact_bound_evidence(inputs, problem):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    review_path = _parent_review(inputs, prepared)
    review = _read(review_path)
    if problem == "wrong_reviewer":
        review["reviewer"] = "analyst"
    elif problem == "not_independent":
        review["independent_full_evidence_read"] = False
    elif problem == "missing_segment":
        review["reviewed_segment_ids"] = []
    elif problem == "missing_check":
        del review["checks"]["reader_report_quality"]
    elif problem == "empty_evidence":
        review["checks"]["reader_report_quality"]["evidence"] = " "
    elif problem == "accepted_failed_check":
        review["checks"]["reader_report_quality"]["status"] = "failed"
    else:
        key = "bundle" if problem == "wrong_bundle" else "analysis_request"
        review["bindings"][key]["sha256"] = "0" * 64
    _write(review_path, review)
    with pytest.raises(delegation.DelegationError):
        _verify(inputs, prepared, semantic_review=review_path)


def test_semantic_review_cli_changes_required_returns_nonzero_without_rewriting_result(inputs, capsys):
    prepared = _prepare(inputs)
    _dispatch(inputs, prepared)
    _bundle(inputs)
    review_path = _parent_review(inputs, prepared)
    review = _read(review_path)
    review["decision"] = "changes_required"
    _write(review_path, review)
    spec = importlib.util.spec_from_file_location("review_cli", delegation.REPO_ROOT / "scripts/kol_semantic_delegation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["verify-result", "--analysis-request", str(inputs["request"]), "--packet", prepared["packet_path"],
                     "--agent-id", AGENT_ID, "--bundle", str(inputs["bundle"]), "--semantic-draft", str(inputs["draft"]),
                     "--semantic-review", str(review_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["semantic_acceptance"]["status"] == "changes_required"
