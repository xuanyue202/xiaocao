"""Publish bounded KOL judgments after current, read-only report verification.

Context/report hashes use publication's RFC 8785 canonical JSON. The trading
decision hash uses kol_policy.decision_sha256; these are different objects and
must never be substituted for one another. Context cache hashes prove internal
consistency, not remote authority. Every NEW publication reads the referenced
current reports through get_kol_record and the complete manifest verifier.
received_at remains a local consumer observation, not a remotely certified date.

Review is independent Agent judgment, not cryptographic permission. Natural
language applicability/falsifiers require Agent reassessment. These commands
neither call a model nor write reports, accounts, orders or notifications.

request stores exact file references/hashes, not copies of potentially private
evidence. Stale/incomplete contexts may request reassessment but cannot publish.
audit/feedback read actual live runs/decision ledgers and paper consumption files
from explicit, disjoint runtime roots, plus optional consumption.jsonl; they describe
recorded consumption, never attribute profits or certify execution.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence

from xiaocao.live import kol_policy
from . import trading_context
from .publication import (
    canonical_bytes, canonical_sha256, manifest_sha256, read_published_publication,
    record_content_sha256,
)


ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = Path("output/live/kol_policy")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{64}")
_MAX_BYTES = 32 * 1024 * 1024


class TradingDecisionError(ValueError):
    """Fixed credential-free error code; never include transport exception text."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise TradingDecisionError(code)


def _time(value) -> datetime:
    return trading_context._timestamp(value)


def _iso(value: datetime) -> str:
    return _time(value).isoformat().replace("+00:00", "Z")


def _id(value) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _sha(value) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _unique(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def _bytes(path: Path) -> bytes:
    _require(path.is_file() and not path.is_symlink(), "regular_input_file_required")
    _require(path.stat().st_size <= _MAX_BYTES, "input_too_large")
    data = path.read_bytes()
    _require(len(data) <= _MAX_BYTES, "input_too_large")
    return data


def read_json(path: Path | str) -> dict:
    try:
        value = json.loads(_bytes(Path(path)), object_pairs_hook=_unique)
        _require(isinstance(value, dict), "json_object_required")
        canonical_bytes(value)
        return value
    except TradingDecisionError:
        raise
    except Exception:
        raise TradingDecisionError("input_read_or_json_failed") from None


def _context(context: dict, now: datetime) -> None:
    _require(isinstance(context, dict), "context_required")
    unsigned = {key: value for key, value in context.items() if key != "context_sha256"}
    _require(context.get("context_sha256") == canonical_sha256(unsigned), "context_hash_mismatch")
    _require(type(context.get("schema_version")) is int and context["schema_version"] == 1
             and context.get("source") == "lianghui_published_registry"
             and type(context.get("authority")) is int and context["authority"] == 0, "context_schema_invalid")
    _require(_time(context["as_of"]) <= now, "future_context")


def _strings(value, code: str) -> set[str]:
    _require(isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value), code)
    _require(len(value) == len(set(value)), code)
    return set(value)


def _source(row: dict) -> dict:
    return {"report_id": row["report_id"], "content_sha256": row["content_sha256"],
            "author_id": row["kol_id"], "source_published_at": row["source_published_at"],
            "received_at": row["received_at"]}


def _coverage(context: dict, review: dict, source_report_ids: set[str] | None = None) -> dict[str, dict]:
    coverage = context["coverage"]
    _require(isinstance(coverage, dict) and coverage.get("remote_discovery") == "registry_only",
             "explicit_registry_scope_required")
    authors = _strings(coverage.get("registered_authors"), "registered_authors_invalid")
    covered = _strings(coverage.get("covered_authors"), "covered_authors_invalid")
    _require(bool(authors) and covered == authors and coverage.get("missing_authors") == [], "author_coverage_missing")
    _require(coverage.get("registered_longitudinal_complete") is True, "longitudinal_coverage_incomplete")
    _require(review.get("context_sha256") == context["context_sha256"], "review_context_hash_mismatch")
    index = {}
    identities = coverage.get("author_identities", {})

    def canonical_author(row):
        identity = identities.get(row["kol_id"])
        if identity is None:
            return row.get("canonical_author", row["author"])
        _require(row["author"] in identity["aliases"], "author_alias_not_registered")
        _require(row.get("canonical_author", identity["author"]) == identity["author"], "canonical_author_mismatch")
        return identity["author"]

    for row in context["report_index"]:
        rid = row["report_id"]
        _require(_id(rid) and rid not in index and canonical_author(row) in authors
                 and row.get("longitudinal_loaded") is True, "context_report_index_invalid")
        index[rid] = row
    _require(bool(index) and {canonical_author(row) for row in index.values()} == authors, "author_index_mismatch")
    unloaded = {rid for rid, row in index.items() if row.get("body_loaded") is not True}
    _require(_strings(context.get("unloaded_report_ids"), "unloaded_reports_invalid") == unloaded,
             "unloaded_reports_mismatch")
    acknowledged = _strings(review.get("acknowledged_unloaded_report_ids", []), "unloaded_ack_invalid")
    _require(acknowledged == unloaded, "unloaded_bodies_not_acknowledged")
    cited = source_report_ids if source_report_ids is not None else set(index) - unloaded
    acknowledgements = review.get("acknowledged_context_issues", [])
    _require(isinstance(acknowledgements, list), "context_issue_ack_invalid")
    acknowledged_issues = {}
    for acknowledgement in acknowledgements:
        digest = acknowledgement.get("issue_sha256")
        reason = acknowledgement.get("reason")
        _require(_sha(digest) and digest not in acknowledged_issues and isinstance(reason, str)
                 and bool(reason.strip()), "context_issue_ack_invalid")
        acknowledged_issues[digest] = reason
    required_ack = set()
    for issue in coverage.get("incomplete_reasons", []):
        if issue.get("code") in {"remote_full_discovery_unavailable", "registered_report_bodies_not_loaded"}:
            continue
        _require(issue.get("code") in {"viewpoint_evaluation_missing", "conflicting_latest_evaluations",
                 "evaluation_viewpoint_not_loaded", "relation_viewpoints_not_loaded", "event_annotation_invalid"},
                 "context_coverage_issue_unresolved")
        affected = {issue["report_id"]} if issue.get("report_id") else set()
        for name in ("viewpoints", "evaluations", "relations"):
            affected.update(row["report_id"] for row in context.get(name, [])
                            if row["record_id"] == issue.get("record_id"))
        _require(bool(affected) and affected <= set(index), "coverage_issue_scope_unproven")
        _require(not affected & cited, "current_source_coverage_issue")
        required_ack.add(canonical_sha256(issue))
    _require(set(acknowledged_issues) == required_ack, "historical_issues_not_acknowledged")
    reports = {}
    for row in context["reports"]:
        rid = row["report_id"]
        _require(rid in index and rid not in reports and rid not in unloaded, "context_reports_mismatch")
        _require(all(row.get(key) == index[rid].get(key) for key in (
            "author", "kol_id", "source_published_at", "received_at", "version_received_at", "verified_at", "content_sha256",
        )), "context_report_index_mismatch")
        envelope = row["report"]
        _require(envelope["kind"] == "report" and envelope["record_id"] == rid
                 and record_content_sha256(envelope) == row["content_sha256"] == envelope["content_sha256"],
                 "context_report_content_hash_mismatch")
        payload = envelope["payload"]
        _require(payload["report_id"] == rid and payload["kol_id"] == row["kol_id"]
                 and payload["author"] == row["author"] and _time(payload["source_published_at"]) == _time(row["source_published_at"])
                 and isinstance(row["report_body"], str) and bool(row["report_body"].strip())
                 and payload["report_body"] == row["report_body"], "context_report_payload_mismatch")
        _require(manifest_sha256(row["manifest"]) == row["manifest_sha256"], "context_manifest_hash_mismatch")
        reports[rid] = row
    _require(set(reports) == set(index) - unloaded, "context_body_coverage_mismatch")
    return reports


def _validate_inputs(decision: dict, review: dict, context: dict, now: datetime, *, fresh: bool) -> list[dict]:
    try:
        as_of, until, reviewed_at = kol_policy._validate_pair(decision, review)
        _require(as_of <= now and reviewed_at <= now, "future_decision_or_review")
        _context(context, now)
        _require(_time(context["as_of"]) <= as_of, "context_later_than_decision")
        reports = _coverage(context, review, {source["report_id"] for source in decision["source_refs"]})
        for row in context["report_index"]:
            _require(_time(row["source_published_at"]) <= _time(row["received_at"])
                     <= _time(row["version_received_at"]) <= as_of, "context_observation_time_invalid")
            _require(_time(row["version_received_at"]) <= _time(row["verified_at"]) <= now,
                     "source_verification_time_invalid")
        selected = []
        for source in decision["source_refs"]:
            row = reports.get(source["report_id"])
            _require(row is not None and source == _source(row), "source_reference_mismatch")
            _require(_time(row["received_at"]) <= _time(row["version_received_at"]) <= as_of,
                     "source_version_not_observed_as_of")
            _require(_time(row["version_received_at"]) <= _time(row["verified_at"]) <= now,
                     "source_verification_time_invalid")
            if fresh:
                _require(now - _time(row["verified_at"]) <= timedelta(seconds=300), "source_verification_stale")
            selected.append(row)
        if fresh:
            _require(now < until, "decision_expired")
            _require(all(now - _time(check["observed_at"]) <= timedelta(minutes=15)
                         for check in decision["current_checks"]), "current_checks_need_refresh")
        return selected
    except TradingDecisionError:
        raise
    except Exception:
        raise TradingDecisionError("decision_review_or_context_invalid") from None


def _sync(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    _require(directory.resolve() == directory.absolute(), "store_symlink_forbidden")
    _sync(directory.parent)
    fd = os.open(directory / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _require(not list(directory.glob(".pending-*")), "incomplete_durable_write")
        yield
    finally:
        os.close(fd)


def _stored(path: Path) -> dict:
    record = read_json(path)
    _require(set(record) == {"payload", "recorded_at", "record_sha256"}, "durable_record_invalid")
    _require(record["record_sha256"] == canonical_sha256({key: value for key, value in record.items()
                                                        if key != "record_sha256"}), "durable_record_hash_mismatch")
    _time(record["recorded_at"])
    return record


def _append(directory: Path, identifier: str, payload: dict, now: datetime) -> dict:
    _require(_id(identifier), "invalid_durable_id")
    path = directory / (identifier + ".json")
    with _locked(directory):
        if path.exists() or path.is_symlink():
            record = _stored(path)
            _require(canonical_bytes(record["payload"]) == canonical_bytes(payload), "immutable_id_conflict")
            _require(_time(record["recorded_at"]) <= now, "future_durable_record")
            return record
        record = {"payload": payload, "recorded_at": _iso(now)}
        record["record_sha256"] = canonical_sha256(record)
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
        # An interrupted write retains its marker and blocks consumers/retries.
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        _sync(directory)
        os.unlink(temporary)
        return record


def _prior_decision(directory: Path, identifier: str) -> dict | None:
    if not directory.exists():
        return None
    with kol_policy._lock(directory, write=False):
        return next((record for record in kol_policy._records(directory)
                     if record["decision"]["decision_id"] == identifier), None)


def _publish_receipt(receipt: dict, verification: dict) -> dict:
    return {**receipt, "context_sha256": verification["payload"]["context_sha256"],
            "coverage_scope": "registry_only", "source_validation": "remote_current_readback_at_publication",
            "source_count": len(verification["payload"]["sources"]),
            "verification_sha256": verification["record_sha256"]}


def publish_trading_decision(root: Path, decision: dict, review: dict, context: dict, *,
                             client=None, clock: Callable[[], datetime] = utc_now) -> dict:
    """Read referenced current remote manifests, durably verify, then publish.

    Exact completed retries reconcile the original two receipts without remote
    reads or TTL extension. A verification-only crash resumes only after another
    current remote read; an existing bare kol_policy publication cannot masquerade
    as having passed this CLI's source verification.
    """
    try:
        now = _time(clock())
        # Detach all caller-owned dictionaries; retain the policy JSON encoding
        # for its decision/review hashes (RFC 8785 would normalize 1.0 to 1).
        decision, review, context = json.loads(json.dumps([decision, review, context], allow_nan=False))
        selected = _validate_inputs(decision, review, context, now, fresh=False)
        directory = Path(root).absolute() / POLICY_PATH
        identifier = decision["decision_id"]
        binding = {"schema_version": "kol-source-verification.v1", "decision_id": identifier,
                   "decision_sha256": kol_policy.decision_sha256(decision),
                   "review_sha256": kol_policy.decision_sha256(review), "context_sha256": context["context_sha256"],
                   "coverage_scope": "registry_only", "sources": [
                       {**_source(row), "manifest_sha256": row["manifest_sha256"]} for row in selected],
                   "received_at_basis": "context_consumer_observation"}
        with _locked(directory / "publication_control"):
            prior = _prior_decision(directory / "decisions", identifier)
            if prior:
                _require(kol_policy.decision_sha256(prior["decision"]) == binding["decision_sha256"]
                         and kol_policy.decision_sha256(prior["review"]) == binding["review_sha256"], "decision_id_conflict")
                with _locked(directory / "source_verifications"):
                    proof = _stored(directory / "source_verifications" / (identifier + ".json"))
                _require(proof["payload"] == binding, "verification_binding_mismatch")
                _require(_time(proof["recorded_at"]) <= _time(prior["receipt"]["published_at"]) <= now,
                         "verification_receipt_time_mismatch")
                return _publish_receipt(prior["receipt"], proof)
            _validate_inputs(decision, review, context, now, fresh=True)
            transport = trading_context.ReadOnlyPublicationTransport(client, timeout_seconds=10,
                retries=0, max_read_calls=256, total_timeout_seconds=60)
            for row in selected:
                publication = read_published_publication(transport, row["report_id"])
                trading_context._validate_publication(publication, {
                    **row, "publication_id": row["report"]["source_binding"]["publication_id"],
                })
                _require(publication["report"] == row["report"]
                         and publication["manifest_sha256"] == row["manifest_sha256"], "remote_current_report_changed")
                _require(trading_context._eligible(publication, row, _time(decision["as_of"])),
                         "remote_publication_not_observed_as_of")
            finished = _time(clock())
            _require(finished >= now, "clock_regressed")
            _validate_inputs(decision, review, context, finished, fresh=True)
            proof = _append(directory / "source_verifications", identifier, binding, finished)
            receipt = kol_policy.publish_decision(directory / "decisions", decision, review, finished)
            return _publish_receipt(receipt, proof)
    except TradingDecisionError:
        raise
    except Exception:
        raise TradingDecisionError("publish_validation_or_durability_failed") from None


def _file_reference(root: Path, value: Path | str) -> dict:
    path = Path(value)
    path = path if path.is_absolute() else root / path
    data = _bytes(path)
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def request_decision(root: Path, *, book: str, runtime: str, phase: str, context_path: Path,
                     decision_context_path: Path, frozen_evidence: Sequence[Path] = (),
                     clock: Callable[[], datetime] = utc_now) -> dict:
    """Persist a hash-bound rendezvous request. This never starts a worker."""
    try:
        now = _time(clock())
        kol_policy._scope(book, runtime)
        _require(_id(phase), "invalid_request_phase")
        root = Path(root).absolute()
        context_ref = _file_reference(root, context_path)
        context_bytes = _bytes(Path(context_ref["path"]))
        _require(hashlib.sha256(context_bytes).hexdigest() == context_ref["sha256"], "context_file_changed")
        context = json.loads(context_bytes, object_pairs_hook=_unique)
        _context(context, now)
        context_ref["context_sha256"] = context["context_sha256"]
        decision_ref = _file_reference(root, decision_context_path)
        references = sorted((_file_reference(root, path) for path in frozen_evidence), key=lambda row: row["path"])
        _require(len(references) == len({row["path"] for row in references}), "duplicate_frozen_evidence")
        payload = {"schema_version": "kol-trading-request.v1", "book": book, "runtime": runtime, "phase": phase,
                   "context": context_ref, "decision_context": decision_ref, "frozen_evidence_refs": references,
                   "coverage_scope": context["coverage"]["remote_discovery"], "action": "agent_reassessment_required"}
        digest = canonical_sha256(payload)
        identifier = "ktr-" + digest
        stored = _append(root / POLICY_PATH / "requests", identifier, payload, now)
        return {"status": "requested", "request_id": identifier, "request_sha256": digest,
                "record_sha256": stored["record_sha256"], "created_at": stored["recorded_at"],
                "book": book, "runtime": runtime, "phase": phase, "context_sha256": context["context_sha256"],
                "request_path": str(root / POLICY_PATH / "requests" / (identifier + ".json"))}
    except TradingDecisionError:
        raise
    except Exception:
        raise TradingDecisionError("request_validation_or_durability_failed") from None


def decision_status(root: Path, *, book: str, runtime: str, clock: Callable[[], datetime] = utc_now) -> dict:
    snapshot = kol_policy.load_decision(Path(root) / POLICY_PATH / "decisions", book, runtime, clock())
    # Do not print freeform rationale, exception text, report bodies or config.
    return {"status": snapshot["status"], "book": book, "runtime": runtime,
            "decision_id": snapshot["decision_id"], "buy_scale": snapshot["buy_scale"],
            "skip_count": len(snapshot["skip_codes"]), "exit_request_count": len(snapshot["exit_codes"])}


def _consumption_evidence(location: Path, runtime: str) -> tuple[list[dict], dict]:
    """Adapt production receipt schemas without inventing consumption clocks."""
    rows, files = [], []
    stats = {"source_file_count": 0, "legacy_file_count": 0, "consumption_container_count": 0,
             "production_hash_bound_record_count": 0,
             "paper_slot_count": 0, "paper_scaled_slot_count": 0, "paper_zero_slot_count": 0,
             "paper_claims_without_terminal": 0, "paper_terminal_status_counts": {}}

    def read(path, *, jsonl=False):
        _require(path.absolute() == path.resolve(), "consumption_path_symlink_forbidden")
        data = _bytes(path)
        files.append({"path": str(path.relative_to(location)), "sha256": hashlib.sha256(data).hexdigest()})
        value = ([json.loads(line, object_pairs_hook=_unique) for line in data.splitlines() if line.strip()]
                 if jsonl else json.loads(data, object_pairs_hook=_unique))
        canonical_bytes(value)
        return value

    def bound(value, field):
        _require(value.get(field) == kol_policy.decision_sha256({k: v for k, v in value.items() if k != field}),
                 "production_consumption_hash_mismatch")

    def normalize(value, *, identifier=None, digest=None, observed=None, adjustment=None):
        _require(value.get("book", "B") == "B" and value.get("runtime", runtime) == runtime,
                 "production_consumption_scope_mismatch")
        return {"book": "B", "runtime": runtime, "decision_id": identifier,
                "decision_sha256": digest, "consumed_at": observed, "adjustment": adjustment or {}}

    generic = location / "consumption.jsonl"
    if generic.exists():
        rows.extend(read(generic, jsonl=True))
        stats["consumption_container_count"] += 1
    if runtime == "live":
        for path in sorted((location / "runs").glob("*.json")):
            run = read(path)
            if "policy_consumptions" not in run:
                stats["legacy_file_count"] += 1
                continue
            normalize(run)
            _require(isinstance(run["policy_consumptions"], list), "live_policy_consumptions_invalid")
            stats["consumption_container_count"] += 1
            for item in run["policy_consumptions"]:
                rows.append(normalize(item, identifier=item.get("decision_id"), digest=item.get("decision_sha256"),
                    observed=item.get("consumed_at"), adjustment={"skip": item.get("skip") is True}))
        ledger = location / "book_b_live_decisions.jsonl"
        if ledger.exists():
            previous = None
            for item in read(ledger, jsonl=True):
                bound(item, "event_hash")
                _require(item.get("previous_hash") == previous, "live_decision_chain_broken")
                previous = item["event_hash"]
                if "kol_decision_id" not in item:
                    continue
                _require(item.get("environment") == "live", "live_decision_environment_mismatch")
                rows.append(normalize(item, identifier=item["kol_decision_id"], digest=item.get("kol_decision_sha256"),
                    observed=item.get("recorded_at"), adjustment={"triggered": item.get("kol_exit_currently_valid") is True}))
                stats["consumption_container_count"] += 1
                stats["production_hash_bound_record_count"] += 1
    else:
        directory = location / "consumption"
        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".result.json"):
                _require(path.with_name(path.name.removesuffix(".result.json") + ".json").is_file(), "orphan_paper_terminal")
                continue
            claim = read(path)
            bound(claim, "receipt_sha256")
            _require(claim.get("schema_version") == "paper-policy-consumption.v1", "paper_consumption_schema_invalid")
            snapshot, slots = claim["kol_decision"], claim["slots"]
            _require(isinstance(snapshot, dict) and isinstance(slots, list), "paper_consumption_payload_invalid")
            _require(snapshot.get("book") == "B" and snapshot.get("runtime") == "paper", "paper_snapshot_scope_mismatch")
            if snapshot.get("status") == "validated":
                kol_policy._validate_record(snapshot.get("record"))
            rows.append(normalize(claim, identifier=snapshot.get("decision_id"), digest=snapshot.get("decision_sha256"),
                                  observed=snapshot.get("evaluated_at"), adjustment={"skip": claim.get("status") == "no_buy"}))
            stats["consumption_container_count"] += 1
            stats["production_hash_bound_record_count"] += 1
            for slot in slots:
                _require(slot.get("kol_decision_id") == snapshot.get("decision_id")
                         and slot.get("kol_decision_sha256") == snapshot.get("decision_sha256")
                         and slot.get("kol_snapshot_sha256") == kol_policy.decision_sha256(snapshot), "paper_slot_decision_mismatch")
                baseline, final = slot["baseline_shares"], slot["final_shares"]
                _require(type(baseline) is int and type(final) is int and 0 <= final <= baseline, "paper_slot_quantity_invalid")
                stats["paper_slot_count"] += 1
                stats["paper_scaled_slot_count"] += 0 < final < baseline
                stats["paper_zero_slot_count"] += final == 0
            terminal_path = path.with_suffix(".result.json")
            if terminal_path.exists():
                terminal = read(terminal_path)
                bound(terminal, "receipt_sha256")
                normalize(terminal)
                _require(terminal.get("schema_version") == "paper-policy-result.v1"
                         and terminal.get("consumption_sha256") == claim["receipt_sha256"]
                         and all(terminal.get(key) == claim.get(key) for key in ("date", "pick"))
                         and terminal.get("status") in ("bought", "no_buy"), "paper_terminal_binding_invalid")
                entries = terminal.get("entries")
                _require(isinstance(entries, list) and type(terminal.get("buy_count")) is int
                         and terminal["buy_count"] == len(entries)
                         and terminal["status"] == ("bought" if entries else "no_buy"), "paper_terminal_count_invalid")
                name = terminal["status"]
                counts = stats["paper_terminal_status_counts"]
                counts[name] = counts.get(name, 0) + 1
            else:
                stats["paper_claims_without_terminal"] += 1
    stats.update(source_file_count=len(files), evidence_sha256=canonical_sha256(files))
    return rows, stats


def audit_feedback(root: Path, *, live_root: Path | None = None, paper_root: Path | None = None,
                   clock: Callable[[], datetime] = utc_now) -> dict:
    """Read live runs/*.json and hash-chained book_b_live_decisions.jsonl;
    paper consumption/*.json claims plus their independently bound result files.
    An explicit consumption.jsonl in either root is also supported. Legacy run
    files lacking policy_consumptions do not prove zero policy consumption.
    Missing clocks/hash bindings are counted explicitly, never manufactured.
    """
    try:
        now = _time(clock())
        root = Path(root).absolute()
        live_root = Path(live_root or root / "output/live/book_b_live_execution").absolute()
        paper_root = Path(paper_root or root / "output/live/paper_decision_support").absolute()
        live, paper = live_root.resolve(), paper_root.resolve()
        _require(live != paper and live not in paper.parents and paper not in live.parents, "consumption_roots_must_be_disjoint")
        directory = root / POLICY_PATH / "decisions"
        records = []
        if directory.exists():
            with kol_policy._lock(directory, write=False):
                records = kol_policy._records(directory)
        by_id = {record["decision"]["decision_id"]: record for record in records}
        summaries = {}
        for runtime, location in (("live", live_root), ("paper", paper_root)):
            rows, evidence = _consumption_evidence(location, runtime)
            if evidence["consumption_container_count"] == 0:
                summaries[runtime] = {**evidence, "status": "not_recorded" if evidence["source_file_count"] else "missing",
                                      "record_count": None, "decision_counts": {}}
                continue
            counts, books, executions = Counter(), Counter(), Counter()
            hash_bound = skips = exits = missing_clock = unbound_reference = 0
            for row in rows:
                canonical_bytes(row)
                _require(isinstance(row, dict) and row.get("runtime") == runtime, "consumption_runtime_mismatch")
                kol_policy._scope(row.get("book"), runtime)
                observed = _time(row["consumed_at"]) if row.get("consumed_at") else None
                _require(observed is None or observed <= now, "future_consumption")
                missing_clock += observed is None
                identifier = row["decision_id"]
                if identifier is not None:
                    record = by_id.get(identifier)
                    _require(record is not None, "consumption_decision_unknown")
                    decision = record["decision"]
                    _require(decision["book"] == row["book"] and decision["runtime"] in (runtime, "both")
                             and row.get("decision_sha256") in (None, record["receipt"]["decision_sha256"]),
                             "consumption_decision_binding_mismatch")
                    unbound_reference += row.get("decision_sha256") is None
                    _require(observed is None or _time(record["receipt"]["published_at"]) <= observed, "consumption_before_publication")
                if "consumption_sha256" in row:
                    _require(row["consumption_sha256"] == canonical_sha256({key: value for key, value in row.items()
                                                                          if key != "consumption_sha256"}),
                             "consumption_hash_mismatch")
                    hash_bound += 1
                counts[identifier or "no_decision"] += 1
                books[row["book"]] += 1
                adjustment = row.get("adjustment", {})
                _require(isinstance(adjustment, dict), "consumption_adjustment_invalid")
                skips += adjustment.get("skip") is True
                exits += adjustment.get("triggered") is True
                if "execution_status" in row:
                    _require(row["execution_status"] in (
                        "not_submitted", "submitted", "acknowledged", "partial", "filled",
                        "cancelled", "rejected", "unknown", "blocked",
                    ), "consumption_execution_status_invalid")
                    executions[row["execution_status"]] += 1
            summaries[runtime] = {**evidence, "status": "read", "record_count": len(rows),
                                  "hash_bound_record_count": hash_bound + evidence["production_hash_bound_record_count"],
                                  "missing_consumption_clock_count": missing_clock, "unbound_decision_reference_count": unbound_reference,
                                  "decision_counts": dict(sorted(counts.items())), "book_counts": dict(sorted(books.items())),
                                  "skip_record_count": skips, "exit_request_record_count": exits,
                                  "reported_execution_status_counts": dict(sorted(executions.items()))}
        return {"status": "audited", "published_decision_count": len(records), "consumption": summaries,
                "execution_verification": "not_performed", "profit_attribution": "not_established"}
    except TradingDecisionError:
        raise
    except Exception:
        raise TradingDecisionError("audit_evidence_invalid") from None
