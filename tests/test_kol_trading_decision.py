"""Read-only remote fixtures and isolated local request/publication stores."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.kol import trading_context as tc, trading_decision as td
from xiaocao.kol.publication import canonical_bytes, canonical_sha256, manifest_entries, manifest_sha256, record_content_sha256, report_id
from xiaocao.live import kol_policy


NOW = datetime(2026, 9, 6, 2, 0, tzinfo=timezone.utc)
CREATED = "2026-09-05T01:00:00Z"
CODE = "600519.XSHG"


def iso(value=NOW):
    return value.isoformat().replace("+00:00", "Z")


class Reader:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.reports = {}
        for author in ("short-term", "environment"):
            identity = "fixture:" + author
            rid = report_id(identity)
            record = {
                "schema_version": 1, "kind": "report", "record_id": rid,
                "idempotency_key": "fixture-" + rid, "created_at": CREATED,
                "source_binding": {"publication_id": identity, "publication_version": "v1",
                                   "evidence_sha256": "e" * 64, "decision_result_sha256": "d" * 64},
                "payload": {"report_id": rid, "author": author, "kol_id": "kol-" + author,
                            "source_published_at": CREATED, "report_body": "完整报告及反证。",
                            "viewpoint_ids": []},
            }
            record["content_sha256"] = record_content_sha256(record)
            self.reports[rid] = record

    def call_tool(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        assert name == "get_kol_record", "Never allow a remote write"
        if self.fail:
            raise OSError("Authorization: Bearer SECRET_FROM_CONFIG")
        record = copy.deepcopy(self.reports[args["record_id"]])
        return {**record, "state": "published", "manifest": manifest_entries([record]),
                "manifest_sha256": manifest_sha256(manifest_entries([record])),
                "published_at": CREATED, "updated_at": CREATED,
                "Authorization": "Bearer SECRET_FROM_REMOTE"}


def register(root, reader):
    path = root / "output/live/kol_daily/publications/events.jsonl"
    path.parent.mkdir(parents=True)
    events = []
    for record in reader.reports.values():
        rid = record["record_id"]
        request = {"report_id": rid, "report_content_sha256": record["content_sha256"],
                   "records": manifest_entries([record]), "manifest_sha256": manifest_sha256(manifest_entries([record]))}
        artifact = {"records": [record], "publish_request": request, "metadata": {}}
        for event in [
            {"event": "publication_prepared", "artifact": artifact, "artifact_sha256": canonical_sha256(artifact)},
            {"event": "publication_receipt", "receipt": {"recordId": rid, "contentSha256": record["content_sha256"],
             "manifestSha256": request["manifest_sha256"], "recordState": "published",
             "detailUrl": "https://example.test/kol-reports/" + rid}},
        ]:
            row = {"schema_version": 1, "publication_key": rid, "occurred_at": CREATED, **event}
            events.append({**row, "event_id": canonical_sha256(row)})
    path.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in events))
    return path


def rehash(context):
    context["context_sha256"] = canonical_sha256({key: value for key, value in context.items() if key != "context_sha256"})


def review_for(decision, context):
    return {"decision_sha256": kol_policy.decision_sha256(decision), "status": "approved",
            "reviewer_agent_id": "independent-main-agent", "reviewed_at": decision["as_of"],
            "coverage_complete": True, "source_fidelity": True, "applicability_checked": True,
            "counterevidence_checked": True, "context_sha256": context["context_sha256"],
            "acknowledged_unloaded_report_ids": []}


@pytest.fixture
def bundle(tmp_path):
    reader = Reader()
    register(tmp_path, reader)
    context = tc.build_trading_context(repo_root=tmp_path, client=reader, clock=lambda: NOW)
    decision = {"schema_version": kol_policy.SCHEMA_VERSION, "decision_id": "decision-1", "agent_id": "source-reader",
                "book": "B", "runtime": "live", "as_of": iso(), "valid_until": iso(NOW + timedelta(hours=24)),
                "source_refs": [td._source(row) for row in context["reports"]],
                "buy_scale": 0.5, "skip_codes": [], "exit_codes": [CODE],
                "rationale": "Independent full-source synthesis.", "invalidation_conditions": ["Agent reassesses the stated conditions."],
                "current_checks": [{"claim": "Current facts were checked.", "observed_at": iso(),
                                    "evidence_ref": "frozen-quote-1", "verdict": "supports"}]}
    reader.calls.clear()
    return decision, review_for(decision, context), context, reader


def publish(root, bundle, when=NOW):
    decision, review, context, reader = bundle
    return td.publish_trading_decision(root, decision, review, context, client=reader, clock=lambda: when)


def write_files(root, bundle):
    for filename, value in zip(("decision.json", "review.json", "context.json"), bundle[:3]):
        (root / filename).write_text(json.dumps(value, ensure_ascii=False))
    (root / "frozen.json").write_text('{"quote":"fixture-only"}')
    (root / "decision-context.json").write_text('{"eligible_codes":["600519.XSHG"]}')


def command():
    spec = importlib.util.spec_from_file_location("kol_trading_decision_cli", Path(__file__).resolve().parents[1] / "scripts/kol_trading_decision.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_remote_readback_and_distinct_hashes(tmp_path, bundle):
    decision, review, context, reader = bundle
    before = (tmp_path / "output/live/kol_daily/publications/events.jsonl").read_bytes()
    receipt = publish(tmp_path, bundle)
    assert receipt["status"] == "published"
    assert receipt["source_count"] == 2
    assert receipt["coverage_scope"] == "registry_only"
    assert receipt["decision_sha256"] == kol_policy.decision_sha256(decision)
    assert receipt["context_sha256"] == context["context_sha256"]
    assert all(source["content_sha256"] != receipt["decision_sha256"] for source in decision["source_refs"])
    assert len(reader.calls) == 2
    assert {name for name, _ in reader.calls} == {"get_kol_record"}
    stored = td.read_json(tmp_path / td.POLICY_PATH / "decisions/decision-1.json")
    assert stored["decision"] == decision
    assert stored["review"] == review
    assert (tmp_path / "output/live/kol_daily/publications/events.jsonl").read_bytes() == before
    assert not (tmp_path / "output/live/kol_daily/publications/.lock").exists()
    assert "SECRET" not in json.dumps(receipt)
    assert td.decision_status(tmp_path, book="B", runtime="live", clock=lambda: NOW)["status"] == "validated"
    assert td.decision_status(tmp_path, book="B", runtime="paper", clock=lambda: NOW)["status"] == "no_decision"


def test_completed_publish_retry_preserves_receipts_after_expiry_without_remote_calls(tmp_path, bundle):
    first = publish(tmp_path, bundle)
    root = tmp_path / td.POLICY_PATH
    before = {str(path): path.read_bytes() for path in root.rglob("*.json")}
    bundle[3].calls.clear()
    bundle[3].fail = True
    assert publish(tmp_path, bundle, NOW + timedelta(days=2)) == first
    assert bundle[3].calls == []
    assert {str(path): path.read_bytes() for path in root.rglob("*.json")} == before
    assert td.decision_status(tmp_path, book="B", runtime="live", clock=lambda: NOW + timedelta(days=2))["status"] == "expired"


def test_partial_publication_resume_revalidates_and_preserves_verification(tmp_path, bundle, monkeypatch):
    original = kol_policy.publish_decision

    def fail(*args, **kwargs):
        raise OSError("simulated failure after source verification")

    monkeypatch.setattr(kol_policy, "publish_decision", fail)
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    proof = tmp_path / td.POLICY_PATH / "source_verifications/decision-1.json"
    before = proof.read_bytes()
    assert not (tmp_path / td.POLICY_PATH / "decisions/decision-1.json").exists()
    bundle[3].calls.clear()
    monkeypatch.setattr(kol_policy, "publish_decision", original)
    receipt = publish(tmp_path, bundle, NOW + timedelta(seconds=10))
    assert receipt["status"] == "published"
    assert len(bundle[3].calls) == 2
    assert proof.read_bytes() == before


def test_verification_write_failure_cannot_publish(tmp_path, bundle, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("audit disk failure")

    monkeypatch.setattr(td.os, "link", fail)
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    assert not (tmp_path / td.POLICY_PATH / "decisions/decision-1.json").exists()


@pytest.mark.parametrize("change", ["decision", "review", "context"])
def test_completed_id_conflict_fails_before_remote_read(tmp_path, bundle, change):
    publish(tmp_path, bundle)
    decision, review, context, reader = bundle
    reader.calls.clear()
    if change == "decision":
        decision["buy_scale"] = 0
        review["decision_sha256"] = kol_policy.decision_sha256(decision)
    elif change == "review":
        review["reviewer_agent_id"] = "new-independent-reviewer"
    else:
        context["note"] = "changed context"
        rehash(context)
        review["context_sha256"] = context["context_sha256"]
    with pytest.raises(td.TradingDecisionError, match="decision_id_conflict"):
        publish(tmp_path, bundle)
    assert reader.calls == []


@pytest.mark.parametrize("field,value", [
    ("content_sha256", "a" * 64), ("author_id", "display-name-not-kol-id"),
    ("source_published_at", iso()), ("received_at", CREATED), ("report_id", "unregistered"),
])
def test_sources_must_match_exact_authoritative_context_row(tmp_path, bundle, field, value):
    decision, review, context, reader = bundle
    decision["source_refs"][0][field] = value
    review["decision_sha256"] = kol_policy.decision_sha256(decision)
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    assert reader.calls == []
    assert not (tmp_path / td.POLICY_PATH / "decisions").exists()


def test_report_hash_cannot_be_replaced_with_trading_decision_or_source_binding_hash(tmp_path, bundle):
    decision, review, _, reader = bundle
    for incorrect in [review["decision_sha256"], "d" * 64, "e" * 64]:
        decision["source_refs"][0]["content_sha256"] = incorrect
        review["decision_sha256"] = kol_policy.decision_sha256(decision)
        with pytest.raises(td.TradingDecisionError, match="source_reference_mismatch"):
            publish(tmp_path, bundle)
    assert reader.calls == []


@pytest.mark.parametrize("offset,accepted", [(300, True), (301, False), (-1, False)])
def test_verified_at_max_age_and_future_boundary(tmp_path, bundle, offset, accepted):
    if offset == -1:
        context = bundle[2]
        for row in context["reports"] + context["report_index"]:
            row["verified_at"] = iso(NOW + timedelta(seconds=1))
        rehash(context)
        bundle[1]["context_sha256"] = context["context_sha256"]
        when = NOW
    else:
        when = NOW + timedelta(seconds=offset)
    if accepted:
        assert publish(tmp_path, bundle, when)["status"] == "published"
    else:
        with pytest.raises(td.TradingDecisionError):
            publish(tmp_path, bundle, when)


def test_verification_freshness_is_checked_again_after_remote_read(tmp_path, bundle):
    times = iter((NOW, NOW + timedelta(seconds=301)))
    with pytest.raises(td.TradingDecisionError, match="source_verification_stale"):
        td.publish_trading_decision(tmp_path, *bundle[:3], client=bundle[3], clock=lambda: next(times))
    assert not (tmp_path / td.POLICY_PATH / "decisions").exists()


@pytest.mark.parametrize("mutation", ["hash", "schema", "authority", "source", "future", "body", "embedded_hash", "index", "manifest"])
def test_context_integrity_and_structure(tmp_path, bundle, mutation):
    _, review, context, reader = bundle
    if mutation == "hash":
        context["context_sha256"] = "0" * 64
    elif mutation == "schema":
        context["schema_version"] = 2
    elif mutation == "authority":
        context["authority"] = 1
    elif mutation == "source":
        context["source"] = "local_inference"
    elif mutation == "future":
        context["as_of"] = iso(NOW + timedelta(seconds=1))
    elif mutation == "body":
        context["reports"][0]["report_body"] = "edited body"
    elif mutation == "embedded_hash":
        context["reports"][0]["report"]["content_sha256"] = "0" * 64
    elif mutation == "index":
        context["report_index"][0]["kol_id"] = "wrong-author"
    else:
        context["reports"][0]["manifest_sha256"] = "0" * 64
    if mutation != "hash":
        rehash(context)
        review["context_sha256"] = context["context_sha256"]
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    assert reader.calls == []


@pytest.mark.parametrize("payload_time,row_time", [
    ("2026-09-05T09:00:00+08:00", "2026-09-05T01:00:00Z"),
    ("2026-09-05T01:00:00.000000Z", "2026-09-05T01:00:00+00:00"),
])
def test_payload_time_compares_instants_but_source_refs_remain_exact(tmp_path, bundle, payload_time, row_time):
    decision, review, context, reader = bundle
    row = context["reports"][0]
    row["report"]["payload"]["source_published_at"] = payload_time
    digest = record_content_sha256(row["report"])
    row["report"]["content_sha256"] = row["content_sha256"] = digest
    row["source_published_at"] = row_time
    row["manifest"] = manifest_entries([row["report"]])
    row["manifest_sha256"] = manifest_sha256(row["manifest"])
    reader.reports[row["report_id"]] = copy.deepcopy(row["report"])
    index = next(item for item in context["report_index"] if item["report_id"] == row["report_id"])
    index.update(content_sha256=digest, source_published_at=row_time)
    decision["source_refs"] = [td._source(item) for item in context["reports"]]
    rehash(context)
    review.update(review_for(decision, context))
    assert publish(tmp_path, bundle)["status"] == "published"
    decision["decision_id"] = "different-source-spelling"
    decision["source_refs"][0]["source_published_at"] = "2026-09-05T01:00:00.000Z"
    review.update(review_for(decision, context))
    with pytest.raises(td.TradingDecisionError, match="source_reference_mismatch"):
        publish(tmp_path, bundle)


@pytest.mark.parametrize("location,ack,accepted", [
    ("history", True, True), ("history", False, False), ("current", True, False), ("unknown", True, False),
])
def test_only_scoped_uncited_historical_issues_can_be_acknowledged(tmp_path, bundle, location, ack, accepted):
    decision, review, context, _ = bundle
    cited, old = decision["source_refs"]
    decision["source_refs"] = [cited]
    issue = {"code": "relation_viewpoints_not_loaded", "record_id": "relation-with-missing-target", "viewpoint_ids": ["missing"]}
    if location != "unknown":
        context["relations"].append({"record_id": issue["record_id"],
                                     "report_id": old["report_id"] if location == "history" else cited["report_id"]})
    context["coverage"]["incomplete_reasons"].append(issue)
    rehash(context)
    review.update(review_for(decision, context))
    if ack:
        review["acknowledged_context_issues"] = [{"issue_sha256": canonical_sha256(issue),
                                                 "reason": "This historical relation is not used by this judgment."}]
    if accepted:
        assert publish(tmp_path, bundle)["status"] == "published"
    else:
        with pytest.raises(td.TradingDecisionError):
            publish(tmp_path, bundle)


def test_old_uncited_history_is_not_required_to_refresh_every_five_minutes(tmp_path, bundle):
    decision, review, context, _ = bundle
    historical_id = decision["source_refs"].pop()["report_id"]
    for row in context["reports"] + context["report_index"]:
        if row["report_id"] == historical_id:
            row.update(received_at=CREATED, version_received_at=CREATED, verified_at=CREATED)
    rehash(context)
    review.update(review_for(decision, context))
    assert publish(tmp_path, bundle)["status"] == "published"


def test_canonical_author_coverage_preserves_source_alias_identity(tmp_path, bundle):
    _, review, context, _ = bundle
    row = context["reports"][0]
    original = row["author"]
    context["coverage"]["author_identities"] = {
        row["kol_id"]: {"author": "canonical-name", "aliases": [original, "canonical-name"]},
    }
    for key in ("registered_authors", "covered_authors"):
        context["coverage"][key] = ["canonical-name" if name == original else name for name in context["coverage"][key]]
    for item in context["reports"] + context["report_index"]:
        if item["kol_id"] == row["kol_id"]:
            item["canonical_author"] = "canonical-name"
    rehash(context)
    review["context_sha256"] = context["context_sha256"]
    assert publish(tmp_path, bundle)["status"] == "published"


@pytest.mark.parametrize("field,value", [
    ("missing_authors", ["missing-author"]), ("covered_authors", []),
    ("registered_longitudinal_complete", False), ("registered_longitudinal_complete", 1),
    ("remote_discovery", "complete"), ("incomplete_reasons", [{"code": "viewpoint_evaluation_missing"}]),
])
def test_incomplete_coverage_blocks_despite_rehashed_context(tmp_path, bundle, field, value):
    _, review, context, reader = bundle
    context["coverage"][field] = value
    rehash(context)
    review["context_sha256"] = context["context_sha256"]
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    assert reader.calls == []


@pytest.mark.parametrize("acknowledged", [False, True])
def test_optional_unloaded_body_requires_exact_review_acknowledgement(tmp_path, bundle, acknowledged):
    decision, review, context, reader = bundle
    unloaded = context["reports"].pop()
    rid = unloaded["report_id"]
    decision["source_refs"] = [source for source in decision["source_refs"] if source["report_id"] != rid]
    row = next(row for row in context["report_index"] if row["report_id"] == rid)
    row.update(body_loaded=False, not_loaded_reason="report_body_not_selected")
    context["unloaded_report_ids"] = [rid]
    context["coverage"]["incomplete_reasons"].append({"code": "registered_report_bodies_not_loaded", "report_ids": [rid]})
    rehash(context)
    review.update(review_for(decision, context))
    if acknowledged:
        review["acknowledged_unloaded_report_ids"] = [rid]
        assert publish(tmp_path, bundle)["status"] == "published"
        assert len(reader.calls) == 1
    else:
        with pytest.raises(td.TradingDecisionError, match="unloaded_bodies_not_acknowledged"):
            publish(tmp_path, bundle)


def test_rehashed_local_context_cannot_impersonate_current_remote_report(tmp_path, bundle):
    decision, review, context, reader = bundle
    row = context["reports"][0]
    row["report_body"] = row["report"]["payload"]["report_body"] = "Forged but internally hash-consistent report."
    digest = record_content_sha256(row["report"])
    row["report"]["content_sha256"] = row["content_sha256"] = digest
    row["manifest"] = manifest_entries([row["report"]])
    row["manifest_sha256"] = manifest_sha256(row["manifest"])
    index = next(item for item in context["report_index"] if item["report_id"] == row["report_id"])
    index["content_sha256"] = digest
    decision["source_refs"] = [td._source(item) for item in context["reports"]]
    rehash(context)
    review.update(review_for(decision, context))
    with pytest.raises(td.TradingDecisionError, match="remote_current_report_changed"):
        publish(tmp_path, bundle)
    assert reader.calls
    assert not (tmp_path / td.POLICY_PATH / "decisions").exists()


def test_changed_remote_current_version_blocks(tmp_path, bundle):
    record = next(iter(bundle[3].reports.values()))
    record["payload"]["report_body"] = "A newly corrected current report."
    record["content_sha256"] = record_content_sha256(record)
    with pytest.raises(td.TradingDecisionError, match="remote_current_report_changed"):
        publish(tmp_path, bundle)


def test_remote_error_is_credential_free(tmp_path, bundle):
    bundle[3].fail = True
    with pytest.raises(td.TradingDecisionError) as caught:
        publish(tmp_path, bundle)
    assert "SECRET" not in str(caught.value)
    assert "Authorization" not in str(caught.value)


def test_production_client_uses_existing_config_only_for_get_tool(tmp_path, bundle, monkeypatch):
    monkeypatch.setattr(tc.LiangHuiMcpClient, "from_config", lambda: bundle[3])
    assert td.publish_trading_decision(tmp_path, *bundle[:3], clock=lambda: NOW)["status"] == "published"
    assert {name for name, _ in bundle[3].calls} == {"get_kol_record"}


def test_existing_bare_policy_record_cannot_claim_remote_validation(tmp_path, bundle):
    kol_policy.publish_decision(tmp_path / td.POLICY_PATH / "decisions", *bundle[:2], NOW)
    with pytest.raises(td.TradingDecisionError):
        publish(tmp_path, bundle)
    assert bundle[3].calls == []


def request(root, when=NOW):
    return td.request_decision(root, book="B", runtime="live", phase="morning", context_path=Path("context.json"),
                               decision_context_path=Path("decision-context.json"), frozen_evidence=[Path("frozen.json")], clock=lambda: when)


def test_request_is_hash_bound_immutable_and_idempotent(tmp_path, bundle):
    write_files(tmp_path, bundle)
    first = request(tmp_path)
    path = Path(first["request_path"])
    before = path.read_bytes()
    record = td.read_json(path)
    payload = record["payload"]
    assert payload["schema_version"] == "kol-trading-request.v1"
    assert canonical_sha256(payload) == first["request_sha256"]
    assert record["record_sha256"] == first["record_sha256"]
    for reference in [payload["context"], payload["decision_context"], *payload["frozen_evidence_refs"]]:
        assert reference["sha256"] == hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest()
    assert request(tmp_path, NOW + timedelta(hours=1)) == first
    assert path.read_bytes() == before
    assert bundle[3].calls == []
    assert not (tmp_path / td.POLICY_PATH / "decisions").exists()


def test_changed_evidence_creates_different_request_without_overwriting(tmp_path, bundle):
    write_files(tmp_path, bundle)
    first = request(tmp_path)
    (tmp_path / "frozen.json").write_text('{"quote":"new exact evidence"}')
    second = request(tmp_path)
    assert first["request_id"] != second["request_id"]
    assert len(list((tmp_path / td.POLICY_PATH / "requests").glob("*.json"))) == 2


def test_request_can_ask_for_refresh_of_incomplete_context(tmp_path, bundle):
    bundle[2]["coverage"]["missing_authors"] = ["missing-source"]
    rehash(bundle[2])
    write_files(tmp_path, bundle)
    assert request(tmp_path, NOW + timedelta(hours=2))["status"] == "requested"
    assert bundle[3].calls == []


@pytest.mark.parametrize("damage", ["missing", "context_hash", "corrupt_request", "symlink", "naive", "future"])
def test_request_failures(tmp_path, bundle, damage):
    write_files(tmp_path, bundle)
    when = NOW
    if damage == "missing":
        (tmp_path / "decision-context.json").unlink()
    elif damage == "context_hash":
        bundle[2]["context_sha256"] = "0" * 64
        (tmp_path / "context.json").write_text(json.dumps(bundle[2]))
    elif damage == "corrupt_request":
        receipt = request(tmp_path)
        Path(receipt["request_path"]).write_text("{}")
    elif damage == "symlink":
        (tmp_path / "frozen.json").unlink()
        (tmp_path / "frozen.json").symlink_to(tmp_path / "decision-context.json")
    elif damage == "naive":
        when = NOW.replace(tzinfo=None)
    else:
        when = NOW - timedelta(seconds=1)
    with pytest.raises(td.TradingDecisionError):
        request(tmp_path, when)


def test_request_concurrent_retry_returns_one_receipt(tmp_path, bundle):
    write_files(tmp_path, bundle)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: request(tmp_path), range(8)))
    assert all(row == receipts[0] for row in receipts)
    assert len(list((tmp_path / td.POLICY_PATH / "requests").glob("*.json"))) == 1


def consumption(root, receipt, runtime, *, when=NOW, adjustment=None):
    directory = root / runtime
    directory.mkdir(exist_ok=True)
    row = {"book": "B", "runtime": runtime, "decision_id": receipt["decision_id"],
           "decision_sha256": receipt["decision_sha256"], "consumed_at": iso(when),
           "adjustment": adjustment or {}, "execution_status": "not_submitted"}
    row["consumption_sha256"] = canonical_sha256(row)
    (directory / "consumption.jsonl").write_bytes(canonical_bytes(row) + b"\n")
    return row


def test_feedback_separates_actual_live_paper_evidence_and_makes_no_profit_claims(tmp_path, bundle):
    bundle[0]["runtime"] = "both"
    bundle[1].update(review_for(bundle[0], bundle[2]))
    receipt = publish(tmp_path, bundle)
    consumption(tmp_path, receipt, "live", adjustment={"skip": True})
    consumption(tmp_path, receipt, "paper", adjustment={"triggered": True})
    output = td.audit_feedback(tmp_path, live_root=tmp_path / "live", paper_root=tmp_path / "paper", clock=lambda: NOW)
    assert output["published_decision_count"] == 1
    live, paper = output["consumption"]["live"], output["consumption"]["paper"]
    assert live["record_count"] == paper["record_count"] == 1
    assert live["skip_record_count"] == 1
    assert paper["exit_request_record_count"] == 1
    assert live["reported_execution_status_counts"] == {"not_submitted": 1}
    assert output["execution_verification"] == "not_performed"
    assert output["profit_attribution"] == "not_established"


def test_missing_consumption_is_not_zero_confirmed_consumption(tmp_path):
    output = td.audit_feedback(tmp_path)
    assert output["consumption"]["live"]["status"] == "missing"
    assert output["consumption"]["paper"]["record_count"] is None


def test_feedback_reads_real_live_run_and_paper_writer_schemas(tmp_path, bundle):
    from xiaocao.live import paper_decision_support as paper
    from xiaocao.live.book_b_live_morning import BookBLiveMorningReceipt

    decision, review, context, _ = bundle
    decision["runtime"] = "both"
    review.update(review_for(decision, context))
    receipt = publish(tmp_path, bundle)
    live_root = tmp_path / "output/live/book_b_live_execution"
    runs = live_root / "runs"
    runs.mkdir(parents=True)
    run = BookBLiveMorningReceipt(trade_date="2026-09-06", status="no_action", reason="fixture", plan_count=0,
        execution_receipts=(), preparation_receipts=(), freeze_path="fixture", allocation_facts_path="fixture", state_path=str(live_root),
        policy_consumptions=({"stage": "allocation", "code": CODE, "decision_id": receipt["decision_id"],
                              "decision_sha256": receipt["decision_sha256"], "scale": 0.5, "skip": False},))
    (runs / "2026-09-06.json").write_text(json.dumps(run.as_dict()))
    snapshot = kol_policy.load_decision(tmp_path / td.POLICY_PATH / "decisions", "B", "paper", NOW)
    slot = {"code": CODE, "kol_decision_id": receipt["decision_id"], "kol_decision_sha256": receipt["decision_sha256"],
            "kol_snapshot_sha256": kol_policy.decision_sha256(snapshot), "baseline_shares": 200, "final_shares": 100}
    paper.write_consumption(tmp_path, "2026-09-06", "mode_exec_star", {
        "status": "claimed", "risk_receipt": {}, "kol_decision": snapshot, "slots": [slot],
    })
    paper.complete_consumption(tmp_path, "2026-09-06", "mode_exec_star", entries=[{"code": CODE, "shares": 100}])
    result = td.audit_feedback(tmp_path, clock=lambda: NOW)
    live, simulated = result["consumption"]["live"], result["consumption"]["paper"]
    assert live["record_count"] == simulated["record_count"] == 1
    assert live["missing_consumption_clock_count"] == 1
    assert simulated["missing_consumption_clock_count"] == 0
    assert simulated["paper_slot_count"] == simulated["paper_scaled_slot_count"] == 1
    assert simulated["paper_terminal_status_counts"] == {"bought": 1}
    assert simulated["paper_claims_without_terminal"] == 0
    assert simulated["hash_bound_record_count"] == 1
    assert result["profit_attribution"] == "not_established"


def test_feedback_reads_live_exit_ledger_once_without_counting_run_mirror(tmp_path, bundle):
    receipt = publish(tmp_path, bundle)
    root = tmp_path / "output/live/book_b_live_execution"
    root.mkdir(parents=True)
    event = {"schema_version": 1, "decision_id": "monitor-owned-lot-event", "book": "B", "environment": "live",
             "kol_decision_id": receipt["decision_id"], "kol_decision_sha256": receipt["decision_sha256"],
             "kol_exit_currently_valid": True, "recorded_at": iso(), "previous_hash": None}
    event["event_hash"] = kol_policy.decision_sha256(event)
    (root / "book_b_live_decisions.jsonl").write_text(json.dumps(event) + "\n")
    (root / "runs/intraday").mkdir(parents=True)
    (root / "runs/intraday/closing.json").write_text(json.dumps({"decisions": [event]}))
    output = td.audit_feedback(tmp_path, clock=lambda: NOW)["consumption"]["live"]
    assert output["record_count"] == output["exit_request_record_count"] == 1
    assert output["source_file_count"] == 1


def test_old_live_runs_without_consumption_fields_do_not_claim_zero_consumption(tmp_path):
    runs = tmp_path / "output/live/book_b_live_execution/runs"
    runs.mkdir(parents=True)
    (runs / "2026-09-04.json").write_text('{"status":"no_action","trade_date":"2026-09-04"}')
    output = td.audit_feedback(tmp_path)["consumption"]["live"]
    assert output["status"] == "not_recorded"
    assert output["legacy_file_count"] == 1 and output["record_count"] is None


@pytest.mark.parametrize("damage", ["claim_hash", "terminal_hash", "terminal_binding", "terminal_count", "orphan", "slot_binding"])
def test_paper_consumption_production_bindings_are_verified(tmp_path, bundle, damage):
    from xiaocao.live import paper_decision_support as paper
    bundle[0]["runtime"] = "paper"
    bundle[1].update(review_for(bundle[0], bundle[2]))
    publish(tmp_path, bundle)
    snapshot = kol_policy.load_decision(tmp_path / td.POLICY_PATH / "decisions", "B", "paper", NOW)
    slot = {"kol_decision_id": snapshot["decision_id"], "kol_decision_sha256": snapshot["decision_sha256"],
            "kol_snapshot_sha256": kol_policy.decision_sha256(snapshot), "baseline_shares": 100, "final_shares": 0}
    paper.write_consumption(tmp_path, "2026-09-06", "mode_exec_star", {"status": "no_buy", "kol_decision": snapshot, "slots": [slot]})
    paper.complete_consumption(tmp_path, "2026-09-06", "mode_exec_star", entries=[])
    path = paper.consumption_path(tmp_path, "2026-09-06", "mode_exec_star")
    terminal = path.with_suffix(".result.json")
    if damage == "orphan":
        path.unlink()
    else:
        target = terminal if damage.startswith("terminal") else path
        value = td.read_json(target)
        if damage in ("claim_hash", "terminal_hash"):
            value["receipt_sha256"] = "0" * 64
        elif damage == "terminal_binding":
            value["consumption_sha256"] = "0" * 64
            value["receipt_sha256"] = kol_policy.decision_sha256({k: v for k, v in value.items() if k != "receipt_sha256"})
        elif damage == "terminal_count":
            value["buy_count"] = 1
            value["receipt_sha256"] = kol_policy.decision_sha256({k: v for k, v in value.items() if k != "receipt_sha256"})
        else:
            value["slots"][0]["kol_snapshot_sha256"] = "0" * 64
            value["receipt_sha256"] = kol_policy.decision_sha256({k: v for k, v in value.items() if k != "receipt_sha256"})
        target.write_text(json.dumps(value))
    with pytest.raises(td.TradingDecisionError):
        td.audit_feedback(tmp_path, clock=lambda: NOW)


@pytest.mark.parametrize("damage", ["runtime", "book", "hash", "unbound_decision", "row_hash", "future", "json", "duplicate_key"])
def test_audit_rejects_cross_scope_or_damaged_consumption(tmp_path, bundle, damage):
    receipt = publish(tmp_path, bundle)
    row = consumption(tmp_path, receipt, "live")
    path = tmp_path / "live/consumption.jsonl"
    if damage == "json":
        path.write_text("{")
    elif damage == "duplicate_key":
        path.write_text('{"runtime":"paper",' + json.dumps(row)[1:])
    else:
        if damage == "runtime":
            row["runtime"] = "paper"
        elif damage == "book":
            row["book"] = "T"
        elif damage == "hash":
            row["decision_sha256"] = "0" * 64
        elif damage == "unbound_decision":
            row["decision_id"] = "unpublished"
        elif damage == "future":
            row["consumed_at"] = iso(NOW + timedelta(seconds=1))
        else:
            row["consumption_sha256"] = "0" * 64
        path.write_text(json.dumps(row))
    with pytest.raises(td.TradingDecisionError):
        td.audit_feedback(tmp_path, live_root=tmp_path / "live", paper_root=tmp_path / "paper", clock=lambda: NOW)


@pytest.mark.parametrize("nested", [False, True])
def test_audit_roots_must_be_distinct_and_non_overlapping(tmp_path, nested):
    with pytest.raises(td.TradingDecisionError, match="roots_must_be_disjoint"):
        td.audit_feedback(tmp_path, live_root=tmp_path / "live", paper_root=tmp_path / "live/sub" if nested else tmp_path / "live")


def test_cli_publish_request_status_and_feedback(tmp_path, bundle, capsys):
    write_files(tmp_path, bundle)
    cli = command()
    common = ["--root", str(tmp_path)]
    assert cli.main(["publish", *common, "--decision", "decision.json", "--review", "review.json", "--context", "context.json"],
                    client=bundle[3], clock=lambda: NOW) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "published"
    assert "SECRET" not in json.dumps(receipt)
    assert cli.main(["request", *common, "--book", "B", "--runtime", "live", "--phase", "morning",
                     "--context", "context.json", "--decision-context", "decision-context.json", "--frozen-evidence", "frozen.json"], clock=lambda: NOW) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "requested"
    assert cli.main(["status", *common, "--book", "B", "--runtime", "live"], clock=lambda: NOW) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "validated" and "record" not in status
    assert cli.main(["feedback", *common], clock=lambda: NOW) == 0
    assert json.loads(capsys.readouterr().out)["profit_attribution"] == "not_established"


@pytest.mark.parametrize("arguments", [["publish"], ["request"], ["publish", "--decision", "missing", "--review", "missing", "--context", "missing"]])
def test_cli_invalid_inputs_use_compact_safe_error(tmp_path, capsys, arguments):
    assert command().main([*arguments, "--root", str(tmp_path)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {"status", "code"}
    assert result["status"] == "blocked"


def test_cli_does_not_print_remote_error_credentials(tmp_path, bundle, capsys):
    write_files(tmp_path, bundle)
    bundle[3].fail = True
    assert command().main(["publish", "--root", str(tmp_path), "--decision", "decision.json", "--review", "review.json", "--context", "context.json"],
                          client=bundle[3], clock=lambda: NOW) == 2
    output = capsys.readouterr().out
    assert "SECRET" not in output and "Authorization" not in output


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '[]'])
def test_strict_json_input_rejects_duplicates_nonfinite_and_nonobjects(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_text(raw)
    with pytest.raises(td.TradingDecisionError):
        td.read_json(path)
