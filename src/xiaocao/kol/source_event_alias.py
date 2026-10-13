"""Read-only proof for an ASR reupload of an already completed source event."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .enrichment_types import EnrichmentError, validate_decision_completion
from .publication import PublicationLedger, manifest_sha256, record_content_sha256
from .semantic_bundle import read_validated_bundle


def _reference(ref: Any) -> tuple[Path, bytes]:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise EnrichmentError("source event alias requires an immutable file reference")
    path = Path(ref["path"]).expanduser().resolve()
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise EnrichmentError("source event alias evidence changed")
    return path, data


def _json(ref: Any) -> tuple[Path, dict[str, Any]]:
    path, data = _reference(ref)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise EnrichmentError("source event alias evidence must be an object")
    return path, value


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verify_source_event_alias(
    bundle_file: Path, proof: dict[str, Any], decision_output_dir: Path,
) -> dict[str, Any]:
    """Verify full-source analyst equivalence and existing effects; never execute."""
    from .daily import validate_source_event

    _, bundle = read_validated_bundle(bundle_file)
    item = bundle["items"][0]
    equivalence = item.get("source_event_equivalence") or {}
    if (equivalence.get("status") != "same_event"
            or equivalence.get("material_differences") != []
            or not str(equivalence.get("reason") or "").strip()):
        raise EnrichmentError("source event alias lacks accepted full-source equivalence")
    if proof.get("bundle_sha256") != hashlib.sha256(bundle_file.read_bytes()).hexdigest():
        raise EnrichmentError("source event alias proof is not bound to the accepted bundle")
    prior_request_path, prior_request = _json(equivalence.get("prior_request"))
    prior_evidence_path, prior_evidence = _reference(equivalence.get("prior_evidence"))
    current_text = Path(item["evidence_path"]).read_text()
    prior_text = prior_evidence.decode("utf-8")
    prior_bundle_path, _ = _json(proof.get("prior_bundle"))
    prior_receipt, prior_bundle = read_validated_bundle(prior_bundle_path)
    prior = prior_bundle["items"][0]
    if (prior_request.get("source_identity") != prior_receipt.bindings.get("source_identity")
            or prior_request.get("source_version_key") != prior_receipt.bindings.get("source_version_key")
            or prior_request.get("evidence_sha256") != equivalence["prior_evidence"]["sha256"]
            or Path(prior["evidence_path"]).resolve() != prior_evidence_path
            or prior["evidence_sha256"] != equivalence["prior_evidence"]["sha256"]
            or prior["author"] != item["author"] or prior["source"] != item["source"]
            or prior["published_at"] != item["published_at"]
            or prior["source_identity"] == item["source_identity"]):
        raise EnrichmentError("source event alias changes author, source or event date")
    current_claims = {row["claim_id"]: row for row in item["claims"]}
    prior_claims = {row["claim_id"]: row for row in prior["claims"]}
    matches = equivalence.get("claim_matches")
    if (not current_claims or not isinstance(matches, list)
            or len(matches) != len(current_claims)
            or {row.get("claim_id") for row in matches} != set(current_claims)):
        raise EnrichmentError("source event alias leaves current claims unmatched")
    matched_prior: set[str] = set()
    for row in matches:
        ids = row.get("prior_claim_ids")
        quote, old_quote = row.get("current_quote"), row.get("prior_quote")
        if (not isinstance(ids, list) or len(ids) != 1 or ids[0] not in prior_claims
                or not str(row.get("reason") or "").strip()
                or not isinstance(quote, str) or not quote or quote not in current_text
                or not isinstance(old_quote, str) or not old_quote or old_quote not in prior_text
                or quote != current_claims[row["claim_id"]].get("quote")
                or old_quote != prior_claims[ids[0]].get("quote")):
            raise EnrichmentError("source event alias claim evidence does not match")
        matched_prior.update(ids)
    if matched_prior != set(prior_claims):
        raise EnrichmentError("source event alias omits prior investment claims")
    _, prior_result = _json(proof.get("prior_result"))
    notification, book = validate_decision_completion(prior_result)
    old_item = prior_result["items"][0]
    terminal = validate_source_event(old_item.get("daily_terminal"))
    if (old_item.get("claims") != prior["claims"]
            or old_item.get("evidence_sha256") != prior["evidence_sha256"]
            or terminal.get("event_id") != prior["source_identity"]
            or terminal.get("source_binding") != {
                "source_identity": prior["source_identity"],
                "publication_version": prior["source_version_key"],
            } or book.get("status") != "no_trade"
            or prior.get("book_kol_us", {}).get("decision") != "no_trade"
            or item.get("book_kol_us", {}).get("decision") != "no_trade"):
        raise EnrichmentError("source event alias requires exact prior completion and no-trade intent")
    if (terminal["alert"].get("receipt") != notification.get("receipt")
            or {key: value for key, value in terminal["book_kol_us"].items()
                if key != "terminal_order"} != book
            or book.get("reason") != prior["book_kol_us"].get("reason")
            or Path(str(book.get("evidence") or "")).resolve() != prior_evidence_path
            or book.get("evidence_context", {}).get("evidence_sha256") != prior["evidence_sha256"]
            or set(book.get("evidence_context", {}).get("claim_ids") or []) != set(prior_claims)):
        raise EnrichmentError("source event alias terminal does not match prior delivery and Book evidence")
    # Verify independently durable delivery and paper accounting, not just a result file.
    outbox = _rows(decision_output_dir / "household_outbox.jsonl")
    transport_fields = {"status", "receipt", "delivered_at"}
    notification_copy = {key: value for key, value in notification.items() if key not in transport_fields}
    if (Path(str(notification.get("evidence") or "")).resolve() != prior_evidence_path
            or notification.get("evidence_sha256") != prior["evidence_sha256"]
            or notification.get("author") != prior["author"]
            or notification.get("kol_claims") != prior["claims"]
            or not any({key: value for key, value in row.items() if key not in transport_fields}
                       == notification_copy for row in outbox)):
        raise EnrichmentError("source event alias reminder copy is not bound to prior source claims")
    delivered = _rows(decision_output_dir / "events.jsonl")
    if not any(row.get("event") == "notification_delivered"
               and row.get("status") == "delivered"
               and row.get("idempotency_key") == notification.get("idempotency_key")
               and row.get("receipt") == notification.get("receipt") for row in delivered):
        raise EnrichmentError("source event alias lacks the original notification receipt")
    papers = _rows(decision_output_dir / "book_kol_us" / "decisions.jsonl")
    receipted_book = {key: value for key, value in book.items() if key != "idempotent_replay"}
    if not any(row == receipted_book for row in papers):
        raise EnrichmentError("source event alias lacks the original Book receipt")
    knowledge_ref = {"path": old_item["durable_distillation_path"],
                     "sha256": old_item["durable_distillation_sha256"]}
    if (knowledge_ref != {"path": prior.get("durable_distillation_path"),
                          "sha256": prior.get("durable_distillation_sha256")}
            or terminal.get("knowledge_effect") != {
                "status": "reusable_knowledge", "distillation_path": knowledge_ref["path"],
                "distillation_sha256": knowledge_ref["sha256"],
            }):
        raise EnrichmentError("source event alias knowledge terminal changes prior accepted knowledge")
    _reference(knowledge_ref)
    _, report = _json(proof.get("report_readback"))
    _, receipt = _json(proof.get("publication_readback"))
    observed = datetime.fromisoformat(str(proof.get("observed_at") or "").replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if observed.tzinfo is None or not 0 <= age <= 3600:
        raise EnrichmentError("source event alias needs a recent authoritative readback")
    states = PublicationLedger(decision_output_dir.parent / "kol_daily" / "publications").status_snapshot()
    state = next((value for value in states.values()
                  if value.get("completed") and value.get("publish_receipt", {}).get("idempotencyKey")
                  == terminal["gray_report"]["receipt"]), None)
    if state is None:
        raise EnrichmentError("source event alias lacks the original publication ledger")
    records = state["artifact"]["records"]
    local_report = next(row for row in records if row["kind"] == "report")
    expected = {(row["kind"], row["record_id"], row["content_sha256"]) for row in records}
    actual = {(row["kind"], row["record_id"], row["content_sha256"]) for row in report["manifest"]}
    binding = report.get("source_binding") or {}
    if (report.get("state") != "published" or receipt.get("recordState") != "published"
            or report.get("record_id") != local_report["record_id"]
            or receipt.get("recordId") != local_report["record_id"]
            or report.get("content_sha256") != local_report["content_sha256"]
            or record_content_sha256(report) != local_report["content_sha256"]
            or receipt.get("contentSha256") != local_report["content_sha256"]
            or report.get("manifest_sha256") != manifest_sha256(report["manifest"])
            or receipt.get("manifestSha256") != report.get("manifest_sha256")
            or not expected <= actual
            or receipt.get("idempotencyKey") != terminal["gray_report"]["receipt"]
            or receipt.get("detailUrl") != terminal["gray_report"]["detail_url"]
            or binding.get("evidence_sha256") != prior["evidence_sha256"]
            or binding.get("publication_version") != prior["source_version_key"]
            or binding.get("publication_id") != f"xiaocao:subscription_video:{prior['source_identity']}"):
        raise EnrichmentError("source event alias publication readback does not match")
    return {
        "schema_version": 1, "proof_kind": "accepted_source_event_alias",
        "current_evidence_path": str(Path(item["evidence_path"]).resolve()),
        "current_evidence_sha256": item["evidence_sha256"],
        "prior_evidence_path": str(prior_evidence_path),
        "prior_evidence_sha256": prior["evidence_sha256"],
        "household_notification": notification, "book_kol_us": book,
        "prior_daily_terminal": terminal, "alias_proof": proof,
    }
