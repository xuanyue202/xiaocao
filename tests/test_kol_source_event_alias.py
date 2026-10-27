"""Same-event reupload proofs must suppress all duplicate business effects."""

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from contextlib import nullcontext

import pytest

from xiaocao.kol import source_event_alias as aliases
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.publication import manifest_sha256, record_content_sha256


@pytest.fixture
def alias_case(tmp_path, monkeypatch):
    def write(name, value):
        path = tmp_path / name
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    old_text = write("old.txt", "原直播投资原句与条件。")
    new_text = write("new.txt", "新版ASR：原直播投资原句与条件。")
    common = {"author": "作者", "source": "subscription", "published_at": "2026-10-12",
              "claims": [{"claim_id": "c1", "quote": "投资原句与条件。"}]}
    prior = {**common, "source_identity": "old", "source_version_key": "v1",
             "book_kol_us": {"decision": "no_trade", "reason": "无完整计划"},
             "evidence_path": old_text["path"], "evidence_sha256": old_text["sha256"]}
    request = write("request.json", {**prior})
    current = {**common, "source_identity": "new", "source_version_key": "v2",
               "evidence_path": new_text["path"], "evidence_sha256": new_text["sha256"],
               "book_kol_us": {"decision": "no_trade"},
               "source_event_equivalence": {"status": "same_event", "material_differences": [],
                   "reason": "完整双遍复核，只有ASR分段差异", "prior_request": request,
                   "prior_evidence": old_text, "claim_matches": [
                       {"claim_id": "c1", "prior_claim_ids": ["c1"], "current_quote": "投资原句与条件。",
                        "prior_quote": "投资原句与条件。", "reason": "语义与条件一致"}]}}
    notification = {"idempotency_key": "n1", "status": "delivered", "receipt": "relay://n1",
                    "author": common["author"], "kol_claims": common["claims"],
                    "evidence": old_text["path"], "evidence_sha256": old_text["sha256"]}
    book = {"book": "KOL-US", "paper_only": True, "status": "no_trade", "reason": "无完整计划",
            "evidence": old_text["path"], "evidence_context": {"evidence_sha256": old_text["sha256"], "claim_ids": ["c1"]}}
    terminal = {"kind": "source_event", "event_id": "old", "author": "作者",
                "source_binding": {"source_identity": "old", "publication_version": "v1"},
                "content_value": {"status": "promoted", "tier": "alert_eligible", "reason": "投资信息"},
                "gray_report": {"status": "published", "receipt": "p1", "detail_url": "https://report/r1", "terminal_order": 1},
                "alert": {"status": "delivered", "receipt": "relay://n1", "all_recipients": True,
                          "stable_link_count": 1, "stable_report_url": "https://report/r1", "terminal_order": 3},
                "book_kol_us": {**book, "idempotent_replay": False, "terminal_order": 2}}
    knowledge = write("knowledge.json", {"authority": 0})
    terminal["knowledge_effect"] = {"status": "reusable_knowledge", "distillation_path": knowledge["path"],
                                    "distillation_sha256": knowledge["sha256"]}
    prior.update(durable_distillation_path=knowledge["path"], durable_distillation_sha256=knowledge["sha256"])
    old_result = {**prior, "notification": notification, "book_kol_us": {**book, "idempotent_replay": False}, "daily_terminal": terminal,
                  "durable_distillation_path": knowledge["path"], "durable_distillation_sha256": knowledge["sha256"]}
    bundle_ref = write("bundle.json", {"items": [current]})
    prior_bundle_ref = write("prior_bundle.json", {"items": [prior]})
    result_ref = write("result.json", {"status": "completed", "items": [old_result]})
    decisions = tmp_path / "decisions"
    (decisions / "book_kol_us").mkdir(parents=True)
    (decisions / "events.jsonl").write_text(json.dumps({"event": "notification_delivered", **notification}) + "\n")
    (decisions / "household_outbox.jsonl").write_text(json.dumps({key: value for key, value in notification.items()
                                                                if key != "receipt"}) + "\n")
    (decisions / "book_kol_us" / "decisions.jsonl").write_text(json.dumps(book) + "\n")
    report = {"schema_version": 1, "kind": "report", "record_id": "r1", "created_at": "2026-10-12T00:00:00Z", "payload": {"body": "完整报告"},
              "source_binding": {"evidence_sha256": old_text["sha256"], "publication_version": "v1",
                                 "publication_id": "xiaocao:subscription_video:old"}}
    report["content_sha256"] = record_content_sha256(report)
    records = [{key: report[key] for key in ["kind", "record_id", "content_sha256"]}]
    report.update(state="published", manifest=records, manifest_sha256=manifest_sha256(records))
    receipt = {"idempotencyKey": "p1", "recordState": "published", "recordId": "r1",
               "contentSha256": report["content_sha256"], "manifestSha256": report["manifest_sha256"],
               "detailUrl": "https://report/r1"}
    proof = {"bundle_sha256": bundle_ref["sha256"], "prior_bundle": prior_bundle_ref,
             "prior_result": result_ref, "report_readback": write("report.json", report),
             "publication_readback": write("receipt.json", receipt),
             "observed_at": datetime.now(timezone.utc).isoformat()}
    for prefix in ["current", "prior"]:
        context = tmp_path / prefix
        context.mkdir()
        (context / "dispatch.json").write_text(json.dumps({"agent_id": "analyst"}))
        proof[f"{prefix}_packet"] = write(f"{prefix}/packet.json", {
            "analysis_request": request,
            "expected_outputs": {"semantic_draft.json": str(context / "draft.json")},
        })
        proof[f"{prefix}_review"] = write(f"{prefix}/review.json", {"decision": "accepted"})
    def accepted(*args, **kwargs):
        review = json.loads(kwargs["semantic_review"].read_text())
        return {"status": "verified", "semantic_acceptance": {
            "status": "parent_accepted" if review["decision"] == "accepted" else "changes_required"}}
    monkeypatch.setattr(aliases, "verify_delegated_result", accepted)
    snapshots = {"p": {"completed": True, "publish_receipt": receipt, "artifact": {"records": records}}}
    monkeypatch.setattr(aliases.PublicationLedger, "status_snapshot", lambda self: deepcopy(snapshots))
    validated_calls = []
    def read(path):
        validated_calls.append(path)
        value = json.loads(path.read_text())
        row = value["items"][0]
        return SimpleNamespace(bindings={"source_identity": row["source_identity"],
                                        "source_version_key": row["source_version_key"]}), value
    monkeypatch.setattr(aliases, "read_validated_bundle", read)
    return SimpleNamespace(path=tmp_path / "bundle.json", proof=proof, decisions=decisions,
                           current=current, write=write, validated_calls=validated_calls)


def test_alias_requires_both_accepted_bundles_and_reuses_receipts(alias_case):
    c = alias_case
    result = aliases.verify_source_event_alias(c.path, c.proof, c.decisions)
    assert result["proof_kind"] == "accepted_source_event_alias"
    assert result["prior_daily_terminal"]["event_id"] == "old"
    assert result["household_notification"]["receipt"] == "relay://n1"
    assert len(c.validated_calls) == 2
    assert len((c.decisions / "events.jsonl").read_text().splitlines()) == 1
    assert len((c.decisions / "book_kol_us" / "decisions.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("revision", ["identical_transcript", "changed_transcript", "same_version"])
def test_same_identity_renamed_revision_requires_identical_transcript(alias_case, revision):
    c = alias_case
    item = deepcopy(c.current)
    item["source_identity"] = "old"
    if revision != "changed_transcript":
        ref = c.write("new.txt", "原直播投资原句与条件。")
        item["evidence_sha256"] = ref["sha256"]
    if revision == "same_version":
        item["source_version_key"] = "v1"
    ref = c.write("bundle.json", {"items": [item]})
    c.proof["bundle_sha256"] = ref["sha256"]
    if revision != "identical_transcript":
        with pytest.raises(EnrichmentError, match="changes author, source or event date"):
            aliases.verify_source_event_alias(c.path, c.proof, c.decisions)
        return
    result = aliases.verify_source_event_alias(c.path, c.proof, c.decisions)
    assert result["proof_kind"] == "accepted_source_event_alias"
    assert result["current_evidence_sha256"] == result["prior_evidence_sha256"]
    assert len((c.decisions / "events.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("mutation", ["quote", "missing_claim", "extra_prior", "changed_day", "trade", "material_change"])
def test_alias_rejects_incomplete_or_different_source_semantics(alias_case, mutation):
    c = alias_case
    item = deepcopy(c.current)
    eq = item["source_event_equivalence"]
    if mutation == "quote":
        eq["claim_matches"][0]["current_quote"] = "不是原句"
    elif mutation == "missing_claim":
        eq["claim_matches"] = []
    elif mutation == "extra_prior":
        eq["claim_matches"][0]["prior_claim_ids"].append("absent")
    elif mutation == "changed_day":
        item["published_at"] = "2026-10-13"
    elif mutation == "trade":
        item["book_kol_us"]["decision"] = "buy"
    else:
        eq["material_differences"] = ["新增观点"]
    ref = c.write("bundle.json", {"items": [item]})
    c.proof["bundle_sha256"] = ref["sha256"]
    with pytest.raises(EnrichmentError):
        aliases.verify_source_event_alias(c.path, c.proof, c.decisions)


@pytest.mark.parametrize("missing", ["delivery", "book", "changed_report", "stale_readback", "changed_evidence", "unaccepted"])
def test_alias_rejects_missing_durable_effect_proofs(alias_case, monkeypatch, missing):
    c = alias_case
    if missing == "delivery":
        (c.decisions / "events.jsonl").write_text("")
    elif missing == "book":
        (c.decisions / "book_kol_us" / "decisions.jsonl").write_text("")
    elif missing == "changed_report":
        report = json.loads((c.path.parent / "report.json").read_text())
        report["payload"]["body"] = "被改写的报告"
        c.proof["report_readback"] = c.write("report.json", report)
    elif missing == "stale_readback":
        c.proof["observed_at"] = "2020-01-01T00:00:00+00:00"
    elif missing == "changed_evidence":
        (c.path.parent / "old.txt").write_text("改动")
    else:
        def reject(path):
            raise EnrichmentError("parent acceptance missing")
        monkeypatch.setattr(aliases, "read_validated_bundle", reject)
    with pytest.raises(EnrichmentError):
        aliases.verify_source_event_alias(c.path, c.proof, c.decisions)


@pytest.mark.parametrize("same_identity", [False, True])
def test_alias_completion_and_replay_never_dispatch_business_writers(
    alias_case, monkeypatch, same_identity,
):
    from xiaocao.kol import decisions
    from xiaocao.kol.netdisk_enrichment import NetdiskEnrichmentService
    from xiaocao.kol.daily import validate_source_event

    c = alias_case
    if same_identity:
        text = (c.path.parent / "old.txt").read_text()
        evidence = c.write("new.txt", text)
        c.current.update(source_identity="old", evidence_sha256=evidence["sha256"])
        bundle = c.write("bundle.json", {"items": [c.current]})
        c.proof["bundle_sha256"] = bundle["sha256"]
    transcript = c.path.parent / "new.txt"
    sha = hashlib.sha256(transcript.read_bytes()).hexdigest()
    state = {"job_id": "j1", "status": "verified", "transcript_path": str(transcript), "transcript_sha256": sha}
    rows = []
    class Store:
        def job_lock(self, job):
            return nullcontext()
        def latest(self, job):
            return rows[-1] if rows else state
        def append(self, row):
            rows.append(row)
    class Pipeline:
        def __init__(self, *args, **kwargs):
            self.book = SimpleNamespace(validate=lambda value: None)
        def _failures(self, bundle):
            return []
        def _validate_cross_source(self, bundle):
            pass
        def _validate_item(self, item):
            return SimpleNamespace(path=transcript, sha256=sha)
        def process(self, *args, **kwargs):
            raise AssertionError("duplicate event cannot publish, send or book")
    monkeypatch.setattr(decisions, "DecisionPipeline", Pipeline)
    service = NetdiskEnrichmentService(c.path.parent / "enrichment")
    service.store = Store()
    reconciliation = aliases.verify_source_event_alias(c.path, c.proof, c.decisions)
    ref = c.write("reconciliation.json", reconciliation)
    result = service.reconcile_semantic_duplicate(
        "j1", bundle_path=c.path, reconciliation_path=ref["path"], decision_output_dir=c.decisions,
    )
    persisted = json.loads(__import__("pathlib").Path(result["decision_result_path"]).read_text())
    terminal = validate_source_event(persisted["items"][0]["daily_terminal"])
    assert terminal["event_id"] == ("old" if same_identity else "new")
    assert terminal["source_binding"]["source_identity"] == ("old" if same_identity else "new")
    assert terminal["source_binding"]["publication_version"] == "v2"
    assert terminal["source_event_alias"]["canonical_event_id"] == "old"
    assert persisted["semantic_duplicate_reconciliation"]["new_external_side_effect_count"] == 0
    replay = service.reconcile_semantic_duplicate(
        "j1", bundle_path=c.path, reconciliation_path=ref["path"], decision_output_dir=c.decisions,
    )
    assert replay["idempotent_replay"] is True
    assert len(rows) == 1
    assert len((c.decisions / "events.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("intent", ["buy", None])
def test_alias_rejects_prior_trade_or_missing_intent(alias_case, intent):
    c = alias_case
    prior = json.loads((c.path.parent / "prior_bundle.json").read_text())
    if intent is None:
        prior["items"][0].pop("book_kol_us")
    else:
        prior["items"][0]["book_kol_us"]["decision"] = intent
    c.proof["prior_bundle"] = c.write("prior_bundle.json", prior)
    with pytest.raises(EnrichmentError):
        aliases.verify_source_event_alias(c.path, c.proof, c.decisions)


@pytest.mark.parametrize("effect", ["foreign_notification", "foreign_book", "terminal_fill", "terminal_alert", "knowledge"])
def test_alias_rejects_real_receipts_from_other_objects_and_terminal_mismatch(alias_case, effect):
    c = alias_case
    result = json.loads((c.path.parent / "result.json").read_text())
    row = result["items"][0]
    if effect == "foreign_notification":
        row["notification"]["evidence_sha256"] = "foreign"
        # A real matching outbox/delivery alone cannot prove ownership.
        (c.decisions / "household_outbox.jsonl").write_text(json.dumps(row["notification"]) + "\n")
    elif effect == "foreign_book":
        row["book_kol_us"]["evidence_context"]["evidence_sha256"] = "foreign"
        row["daily_terminal"]["book_kol_us"]["evidence_context"]["evidence_sha256"] = "foreign"
        (c.decisions / "book_kol_us" / "decisions.jsonl").write_text(json.dumps(
            {k: v for k, v in row["book_kol_us"].items() if k != "idempotent_replay"}) + "\n")
    elif effect == "terminal_fill":
        row["daily_terminal"]["book_kol_us"]["status"] = "filled"
    elif effect == "terminal_alert":
        row["daily_terminal"]["alert"]["receipt"] = "relay://other"
    else:
        row["daily_terminal"]["knowledge_effect"]["distillation_sha256"] = "foreign"
    c.proof["prior_result"] = c.write("result.json", result)
    with pytest.raises(EnrichmentError):
        aliases.verify_source_event_alias(c.path, c.proof, c.decisions)


@pytest.mark.parametrize("prefix", ["current", "prior"])
def test_alias_rejects_structurally_valid_but_parent_rejected_source(alias_case, prefix):
    c = alias_case
    c.proof[f"{prefix}_review"] = c.write(f"{prefix}/review.json", {"decision": "changes_required"})
    with pytest.raises(EnrichmentError, match="parent acceptance"):
        aliases.verify_source_event_alias(c.path, c.proof, c.decisions)
