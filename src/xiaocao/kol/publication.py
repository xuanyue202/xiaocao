"""Durable LiangHui publication seam for KOL intelligence.

The Agent owns report and viewpoint judgment.  LiangHui owns authenticated
family scope, stable visibility, idempotency receipts, compare-and-swap, and
the canonical household URL.  This module keeps the exact small requests in an
append-only ledger so an uncertain network result is reconciled before retry.
"""

from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import json
import os
import signal
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

import rfc8785

from .decisions import DecisionError
from .reader_copy import ReaderCopyError, validate_reader_payload


KOL_RECORD_KINDS = {
    "report",
    "viewpoint",
    "viewpoint_evaluation",
    "viewpoint_relation",
}
REUSABLE_RECORD_STATES = {"staged", "published", "immutable"}
TERMINAL_PUBLICATION_STATES = {"published", "superseded"}
MAX_LEDGER_LINE_BYTES = 512 * 1024


class PublicationError(DecisionError):
    """A fail-closed LiangHui publication contract violation."""


class PublicationTransport(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call one authenticated LiangHui MCP tool."""


def canonical_bytes(value: Any) -> bytes:
    """Return RFC 8785 canonical JSON bytes."""

    try:
        return rfc8785.dumps(value)
    except (ValueError, TypeError) as exc:
        raise PublicationError("KOL publication is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _base32_sha256(value: str) -> str:
    token = base64.b32encode(hashlib.sha256(value.encode()).digest())
    return token.decode().rstrip("=").lower()


def report_id(publication_id: str) -> str:
    stable_publication_id = str(publication_id or "").strip()
    if not stable_publication_id:
        raise PublicationError("publication_id is required")
    value = (
        "lianghui-kol-report-v1\0publication\0" + stable_publication_id
    )
    return "kr_" + _base32_sha256(value)


def _stable_id(prefix: str, parts: list[str]) -> str:
    if not all(str(part or "").strip() for part in parts):
        raise PublicationError(f"{prefix} identity parts are incomplete")
    value = "\0".join([f"lianghui-kol-{prefix}-v1", *parts])
    return f"{prefix}_{_base32_sha256(value)}"


def viewpoint_id(
    report_id_value: str,
    local_thesis_id: str,
    evidence_refs: list[Any],
) -> str:
    if not evidence_refs:
        raise PublicationError("viewpoint evidence_refs cannot be empty")
    return _stable_id(
        "vp",
        [
            report_id_value,
            local_thesis_id,
            canonical_sha256(evidence_refs),
        ],
    )


def evaluation_id(
    viewpoint_id_value: str,
    as_of: str,
    evaluated_at: str,
) -> str:
    return _stable_id("ve", [viewpoint_id_value, as_of, evaluated_at])


def relation_id(
    from_viewpoint_id: str,
    to_viewpoint_id: str,
    relation_type: str,
    asserted_at: str,
) -> str:
    return _stable_id(
        "vr",
        [
            from_viewpoint_id,
            to_viewpoint_id,
            relation_type,
            asserted_at,
        ],
    )


def content_hash_input(envelope: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "schema_version": envelope["schema_version"],
            "kind": envelope["kind"],
            "record_id": envelope["record_id"],
            "created_at": envelope["created_at"],
            "source_binding": envelope["source_binding"],
            "payload": envelope["payload"],
        }
    except KeyError as exc:
        raise PublicationError(
            f"KOL envelope is missing {exc.args[0]}"
        ) from exc


def record_content_sha256(envelope: dict[str, Any]) -> str:
    return canonical_sha256(content_hash_input(envelope))


def _require_utc_z(value: Any, *, field: str) -> None:
    text = str(value or "")
    if "T" not in text or not text.endswith("Z"):
        raise PublicationError(f"{field} must be UTC ISO-8601 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PublicationError(f"{field} must be UTC ISO-8601 ending in Z") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        raise PublicationError(f"{field} must be UTC ISO-8601 ending in Z")


def build_record(
    *,
    kind: str,
    record_id_value: str,
    idempotency_key: str,
    created_at: str,
    source_binding: dict[str, Any],
    payload: dict[str, Any],
    expected_content_sha256: str | None = None,
) -> dict[str, Any]:
    if kind not in KOL_RECORD_KINDS:
        raise PublicationError(f"unsupported KOL record kind: {kind}")
    _require_utc_z(created_at, field="created_at")
    try:
        validate_reader_payload(kind, payload)
    except ReaderCopyError as exc:
        raise PublicationError(str(exc)) from exc
    envelope: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "record_id": record_id_value,
        "idempotency_key": idempotency_key,
        "created_at": created_at,
        "source_binding": source_binding,
        "payload": payload,
    }
    if expected_content_sha256 is not None:
        if kind != "report":
            raise PublicationError(
                "expected_content_sha256 is only valid for report correction"
            )
        envelope["expected_content_sha256"] = expected_content_sha256
    envelope["content_sha256"] = record_content_sha256(envelope)
    return envelope


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be", errors="surrogatepass")


def manifest_entries(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries = [
        {
            "kind": str(record["kind"]),
            "record_id": str(record["record_id"]),
            "content_sha256": str(record["content_sha256"]),
        }
        for record in records
    ]
    entries.sort(
        key=lambda row: _utf16_sort_key(
            "\0".join(
                (
                    row["kind"],
                    row["record_id"],
                    row["content_sha256"],
                )
            )
        )
    )
    return entries


def manifest_sha256(records: list[dict[str, str]]) -> str:
    normalized = [
        {
            "kind": row["kind"],
            "record_id": row["record_id"],
            "content_sha256": row["content_sha256"],
        }
        for row in records
    ]
    normalized.sort(
        key=lambda row: _utf16_sort_key(
            "\0".join(
                (
                    row["kind"],
                    row["record_id"],
                    row["content_sha256"],
                )
            )
        )
    )
    return canonical_sha256(normalized)


def build_publish_request(
    records: list[dict[str, Any]],
    *,
    idempotency_key: str,
    reason: str | None = None,
    expected_content_sha256: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    reports = [record for record in records if record.get("kind") == "report"]
    if len(reports) != 1:
        raise PublicationError("publication needs exactly one report record")
    report = reports[0]
    entries = manifest_entries(records)
    request: dict[str, Any] = {
        "schema_version": 1,
        "idempotency_key": idempotency_key,
        "report_id": report["record_id"],
        "report_content_sha256": report["content_sha256"],
        "manifest_sha256": manifest_sha256(entries),
        "records": entries,
    }
    if expected_content_sha256 is not None:
        request["expected_content_sha256"] = expected_content_sha256
    if expected_manifest_sha256 is not None:
        request["expected_manifest_sha256"] = expected_manifest_sha256
    if reason is not None:
        request["reason"] = reason
    return request


def publication_id_for_source(
    *,
    adapter: str,
    source_identity: str,
) -> str:
    """Namespace an existing stable source-event identity.

    Version and batch identity are deliberately excluded, so corrections retain
    the same report and independent publication events cannot merge by title.
    """

    normalized_adapter = str(adapter or "").strip()
    normalized_source = str(source_identity or "").strip()
    if not normalized_adapter or not normalized_source:
        raise PublicationError("source publication identity is incomplete")
    return f"xiaocao:{normalized_adapter}:{normalized_source}"


def stable_claim(operation: str, *parts: str) -> str:
    if operation not in {"put", "publish"}:
        raise PublicationError("unsupported publication claim operation")
    digest = hashlib.sha256(
        "\0".join([operation, *parts]).encode()
    ).hexdigest()
    return f"lh-{operation}-{digest}"


def _envelope_from_read(value: dict[str, Any]) -> dict[str, Any]:
    """Rebuild and verify the exact hashable envelope returned by LiangHui."""

    try:
        envelope = {
            "schema_version": value["schema_version"],
            "kind": value["kind"],
            "record_id": value["record_id"],
            "idempotency_key": value["idempotency_key"],
            "content_sha256": value["content_sha256"],
            "created_at": value["created_at"],
            "source_binding": value["source_binding"],
            "payload": value["payload"],
        }
    except KeyError as exc:
        raise PublicationError(
            f"LiangHui record read is missing {exc.args[0]}"
        ) from exc
    if envelope["content_sha256"] != record_content_sha256(envelope):
        raise PublicationError("LiangHui record read failed content validation")
    return envelope


def read_published_publication(
    client: PublicationTransport,
    report_id_value: str,
) -> dict[str, Any]:
    """Read the complete current manifest without producing a side effect."""

    current = client.call_tool(
        "get_kol_record",
        {"kind": "report", "record_id": report_id_value},
    )
    if current.get("state") != "published":
        raise PublicationError("LiangHui report is not published")
    report = _envelope_from_read(current)
    manifest = current.get("manifest")
    if not isinstance(manifest, list) or not manifest:
        raise PublicationError("LiangHui published report lacks a manifest")
    records: list[dict[str, Any]] = []
    for entry in manifest:
        if not isinstance(entry, dict):
            raise PublicationError("LiangHui manifest entry is invalid")
        if (
            entry.get("kind") == "report"
            and entry.get("record_id") == report_id_value
            and entry.get("content_sha256") == report["content_sha256"]
        ):
            record = report
        else:
            record = _envelope_from_read(
                client.call_tool(
                    "get_kol_record",
                    {
                        "kind": entry.get("kind"),
                        "record_id": entry.get("record_id"),
                        "content_sha256": entry.get("content_sha256"),
                    },
                )
            )
        if {
            "kind": record["kind"],
            "record_id": record["record_id"],
            "content_sha256": record["content_sha256"],
        } != {
            "kind": entry.get("kind"),
            "record_id": entry.get("record_id"),
            "content_sha256": entry.get("content_sha256"),
        }:
            raise PublicationError("LiangHui manifest record read mismatched")
        records.append(record)
    if manifest_entries(records) != manifest:
        raise PublicationError("LiangHui manifest order or contents mismatched")
    if manifest_sha256(manifest) != current.get("manifest_sha256"):
        raise PublicationError("LiangHui manifest hash failed validation")
    return {
        "report": report,
        "records": records,
        "content_sha256": report["content_sha256"],
        "manifest_sha256": current["manifest_sha256"],
        "published_at": current.get("published_at"),
        "updated_at": current.get("updated_at"),
    }


def build_append_only_publication_update(
    *,
    current_records: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    viewpoint_ids: list[str],
    created_at: str,
    revision: str,
    reason: str,
    report_payload_updates: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Append Agent records while preserving the exact published history."""

    reports = [
        record for record in current_records if record.get("kind") == "report"
    ]
    if len(reports) != 1:
        raise PublicationError("current publication needs exactly one report")
    current_report = reports[0]
    if current_report["content_sha256"] != record_content_sha256(current_report):
        raise PublicationError("current report content hash does not match")
    current_manifest = manifest_entries(current_records)
    current_manifest_sha256 = manifest_sha256(current_manifest)
    current_viewpoint_ids = list(
        current_report["payload"].get("viewpoint_ids") or []
    )
    if not set(current_viewpoint_ids) <= set(viewpoint_ids):
        raise PublicationError("publication update cannot remove viewpoint ids")
    current_identities = {
        (str(record["kind"]), str(record["record_id"])): str(
            record["content_sha256"]
        )
        for record in current_records
        if record["kind"] != "report"
    }
    addition_identities: set[tuple[str, str]] = set()
    for record in additions:
        if record.get("kind") == "report":
            raise PublicationError("report cannot be an appended record")
        if record.get("content_sha256") != record_content_sha256(record):
            raise PublicationError("appended record content hash does not match")
        identity = (str(record["kind"]), str(record["record_id"]))
        if identity in current_identities or identity in addition_identities:
            raise PublicationError(
                "publication update has duplicate record identity"
            )
        addition_identities.add(identity)
    available_viewpoint_ids = {
        str(record["record_id"])
        for record in [*current_records, *additions]
        if record.get("kind") == "viewpoint"
    }
    if set(viewpoint_ids) != available_viewpoint_ids:
        raise PublicationError(
            "publication viewpoint_ids must match its viewpoint records"
        )
    payload = copy.deepcopy(current_report["payload"])
    updates = copy.deepcopy(report_payload_updates or {})
    unsupported_updates = set(updates) - {
        "title",
        "summary",
        "report_body",
    }
    if unsupported_updates:
        raise PublicationError(
            "report correction cannot change stable publication fields: "
            + ", ".join(sorted(unsupported_updates))
        )
    payload.update(updates)
    payload["viewpoint_ids"] = viewpoint_ids
    source_binding = current_report["source_binding"]
    publication_id = str(source_binding["publication_id"])
    if payload == current_report["payload"]:
        report = copy.deepcopy(current_report)
        report["idempotency_key"] = stable_claim(
            "put",
            publication_id,
            revision,
            "restage-report",
            current_report["content_sha256"],
        )
    else:
        report = build_record(
            kind="report",
            record_id_value=current_report["record_id"],
            idempotency_key=stable_claim(
                "put",
                publication_id,
                revision,
                "report",
                current_report["content_sha256"],
            ),
            created_at=created_at,
            source_binding=source_binding,
            payload=payload,
            expected_content_sha256=current_report["content_sha256"],
        )
    records = [
        report,
        *[
            record
            for record in current_records
            if record.get("kind") != "report"
        ],
        *additions,
    ]
    publish = build_publish_request(
        records,
        idempotency_key=stable_claim(
            "publish",
            publication_id,
            revision,
            current_manifest_sha256,
        ),
        reason=reason,
        expected_content_sha256=current_report["content_sha256"],
        expected_manifest_sha256=current_manifest_sha256,
    )
    return records, publish


class PublicationLedger:
    """Append-only exact-request and receipt ledger for LiangHui writes."""

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.lock_path = self.output_dir / ".lock"
        self._thread_lock = threading.RLock()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self._thread_lock, self.lock_path.open(
            "a+", encoding="utf-8"
        ) as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _events_unlocked(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise PublicationError("publication ledger cannot be read") from exc
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if len(line.encode()) > MAX_LEDGER_LINE_BYTES:
                raise PublicationError(
                    f"publication ledger line {number} exceeds limit"
                )
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PublicationError(
                    f"publication ledger line {number} is invalid"
                ) from exc
            unsigned = dict(row)
            event_id = str(unsigned.pop("event_id", ""))
            if event_id != canonical_sha256(unsigned):
                raise PublicationError(
                    f"publication ledger line {number} failed integrity validation"
                )
            rows.append(row)
        return rows

    def events(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._events_unlocked()

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "schema_version": 1,
            "event": event,
            "occurred_at": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
            **fields,
        }
        row["event_id"] = canonical_sha256(row)
        encoded = canonical_bytes(row) + b"\n"
        if len(encoded) > MAX_LEDGER_LINE_BYTES:
            raise PublicationError("publication ledger event exceeds limit")
        blocked = {signal.SIGINT, signal.SIGTERM}
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.events_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            remaining = memoryview(encoded)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise PublicationError(
                        "publication ledger append made no progress"
                    )
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        return row

    def prepare(
        self,
        publication_key: str,
        records: list[dict[str, Any]],
        publish_request: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not publication_key.strip():
            raise PublicationError("publication_key is required")
        for record in records:
            if record.get("content_sha256") != record_content_sha256(record):
                raise PublicationError("record content hash does not match")
        expected = build_publish_request(
            records,
            idempotency_key=str(publish_request["idempotency_key"]),
            reason=publish_request.get("reason"),
            expected_content_sha256=publish_request.get(
                "expected_content_sha256"
            ),
            expected_manifest_sha256=publish_request.get(
                "expected_manifest_sha256"
            ),
        )
        if expected != publish_request:
            raise PublicationError("publish request does not match records")
        artifact = {
            "records": records,
            "publish_request": publish_request,
            "metadata": metadata or {},
        }
        artifact_sha256 = canonical_sha256(artifact)
        with self._locked():
            publication_events = [
                row
                for row in self._events_unlocked()
                if row.get("publication_key") == publication_key
            ]
            prepared = [
                row
                for row in publication_events
                if row.get("event") == "publication_prepared"
            ]
            if prepared:
                if prepared[-1].get("artifact_sha256") != artifact_sha256:
                    prior_artifact = prepared[-1].get("artifact") or {}
                    prior_records = prior_artifact.get("records") or []
                    prior_bindings = [
                        row.get("source_binding")
                        for row in prior_records
                    ]
                    current_bindings = [
                        row.get("source_binding")
                        for row in records
                    ]
                    latest = publication_events[-1]
                    rejection_base = (
                        latest.get("event") == "record_call_uncertain"
                        and latest.get("error_code") == "INVALID_ARGUMENT"
                        and not any(
                            row.get("event")
                            in {
                                "publication_call_claimed",
                                "publication_receipt",
                            }
                            for row in publication_events
                        )
                        and prior_bindings == current_bindings
                        and prior_artifact.get("metadata")
                        == artifact.get("metadata")
                    )
                    receipt_keys = {
                        str(row.get("record_key") or "")
                        for row in publication_events
                        if row.get("event") == "record_receipt"
                    }
                    rejected_key = str(latest.get("record_key") or "")
                    differences = [
                        (prior, current)
                        for prior, current in zip(prior_records, records)
                        if prior != current
                    ]
                    strict_partial_repair = False
                    if (
                        rejection_base
                        and receipt_keys
                        and len(prior_records) == len(records)
                        and len(differences) == 1
                        and rejected_key not in receipt_keys
                    ):
                        prior_rejected, current_replacement = differences[0]
                        unchanged_identity = all(
                            prior_rejected.get(field)
                            == current_replacement.get(field)
                            for field in (
                                "kind",
                                "record_id",
                                "idempotency_key",
                                "created_at",
                                "source_binding",
                            )
                        )
                        prior_by_key = {
                            self._record_key(row): row
                            for row in prior_records
                        }
                        current_by_key = {
                            self._record_key(row): row
                            for row in records
                        }
                        strict_partial_repair = (
                            self._record_key(prior_rejected) == rejected_key
                            and unchanged_identity
                            and all(
                                key in prior_by_key
                                and key in current_by_key
                                and prior_by_key[key] == current_by_key[key]
                                for key in receipt_keys
                            )
                        )
                    recoverable_rejection = rejection_base and (
                        not receipt_keys or strict_partial_repair
                    )
                    if not recoverable_rejection:
                        raise PublicationError(
                            "prepared publication changed under a stable key"
                        )
                    self._append(
                        "publication_prepared",
                        publication_key=publication_key,
                        artifact_sha256=artifact_sha256,
                        artifact=artifact,
                        supersedes_artifact_sha256=prepared[-1][
                            "artifact_sha256"
                        ],
                        repair_reason=(
                            "server_rejected_prior_record_as_invalid_argument"
                        ),
                        large_payload_local_bytes=0,
                    )
            else:
                self._append(
                    "publication_prepared",
                    publication_key=publication_key,
                    artifact_sha256=artifact_sha256,
                    artifact=artifact,
                    large_payload_local_bytes=0,
                )
        return self.status(publication_key)

    def status(self, publication_key: str) -> dict[str, Any]:
        with self._locked():
            events = [
                row
                for row in self._events_unlocked()
                if row.get("publication_key") == publication_key
            ]
        prepared = next(
            (
                row
                for row in reversed(events)
                if row.get("event") == "publication_prepared"
            ),
            None,
        )
        if prepared is None:
            raise PublicationError("publication is not prepared")
        record_receipts: dict[str, dict[str, Any]] = {}
        record_claims: dict[str, dict[str, Any]] = {}
        record_claim_counts: dict[str, int] = {}
        publish_receipt: dict[str, Any] | None = None
        for row in events:
            if row.get("event") == "record_call_claimed":
                key = str(row["record_key"])
                record_claims[key] = row["request"]
                record_claim_counts[key] = record_claim_counts.get(key, 0) + 1
            elif row.get("event") == "record_receipt":
                record_receipts[str(row["record_key"])] = row["receipt"]
            elif row.get("event") == "publication_receipt":
                publish_receipt = row["receipt"]
        artifact = prepared["artifact"]
        return {
            "publication_key": publication_key,
            "artifact_sha256": prepared["artifact_sha256"],
            "artifact": artifact,
            "record_receipts": record_receipts,
            "record_claims": record_claims,
            "record_claim_counts": record_claim_counts,
            "publish_receipt": publish_receipt,
            "completed": bool(
                publish_receipt
                and publish_receipt.get("recordState")
                in TERMINAL_PUBLICATION_STATES
            ),
            "event_count": len(events),
            "large_payload_local_bytes": 0,
        }

    @staticmethod
    def _record_key(record: dict[str, Any]) -> str:
        return "\0".join(
            (
                str(record["kind"]),
                str(record["record_id"]),
                str(record["content_sha256"]),
            )
        )

    @staticmethod
    def _mcp_code(exc: Exception) -> str:
        return str(getattr(exc, "code", "") or "")

    def _status_or_missing(
        self,
        client: PublicationTransport,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        try:
            return client.call_tool(
                "get_kol_write_status",
                {"idempotency_key": idempotency_key},
            )
        except Exception as exc:
            if self._mcp_code(exc) == "NOT_FOUND":
                return None
            raise

    def run(
        self,
        publication_key: str,
        client: PublicationTransport,
    ) -> dict[str, Any]:
        """Reconcile, stage exact records, then atomically publish.

        A durable call claim is appended before every external write.  Any
        exception is recorded as uncertain and returned to the caller; the next
        run checks the server receipt before deciding whether the exact original
        request can be called again.
        """

        state = self.status(publication_key)
        if state["completed"]:
            return state
        artifact = state["artifact"]
        records = artifact["records"]
        for record in records:
            record_key = self._record_key(record)
            receipt = state["record_receipts"].get(record_key)
            if receipt and receipt.get("recordState") in REUSABLE_RECORD_STATES:
                continue
            request = state["record_claims"].get(record_key)
            if receipt and receipt.get("recordState") == "expired_or_missing":
                attempt = state["record_claim_counts"].get(record_key, 0) + 1
                request = dict(record)
                request["idempotency_key"] = stable_claim(
                    "put",
                    str(record["idempotency_key"]),
                    str(record["content_sha256"]),
                    f"renew-{attempt}",
                )
                receipt = None
            elif receipt:
                raise PublicationError(
                    "record receipt state requires explicit reconciliation"
                )
            if request is None or (
                state["record_receipts"].get(record_key) is not None
                and receipt is None
            ):
                request = request or record
                with self._locked():
                    self._append(
                        "record_call_claimed",
                        publication_key=publication_key,
                        record_key=record_key,
                        idempotency_key=request["idempotency_key"],
                        request=request,
                    )
                state = self.status(publication_key)
            claim = str(request["idempotency_key"])
            reconciled = self._status_or_missing(client, claim)
            if reconciled is not None:
                with self._locked():
                    self._append(
                        "record_receipt",
                        publication_key=publication_key,
                        record_key=record_key,
                        receipt=reconciled,
                        reconciled=True,
                    )
                state = self.status(publication_key)
                receipt = state["record_receipts"][record_key]
                if receipt.get("recordState") not in REUSABLE_RECORD_STATES:
                    if (
                        receipt.get("recordState") == "expired_or_missing"
                        and state["record_claim_counts"].get(record_key, 0) < 3
                    ):
                        return self.run(publication_key, client)
                    raise PublicationError(
                        "renewed record claim is not reusable"
                    )
                continue
            try:
                receipt = client.call_tool("put_kol_record", request)
            except Exception as exc:
                with self._locked():
                    self._append(
                        "record_call_uncertain",
                        publication_key=publication_key,
                        record_key=record_key,
                        idempotency_key=claim,
                        error_type=type(exc).__name__,
                        error_code=self._mcp_code(exc),
                    )
                raise
            with self._locked():
                self._append(
                    "record_receipt",
                    publication_key=publication_key,
                    record_key=record_key,
                    receipt=receipt,
                    reconciled=False,
                )
            state = self.status(publication_key)

        publish_request = artifact["publish_request"]
        publish_claim = str(publish_request["idempotency_key"])
        with self._locked():
            self._append(
                "publication_call_claimed",
                publication_key=publication_key,
                idempotency_key=publish_claim,
                request=publish_request,
            )
        reconciled = self._status_or_missing(client, publish_claim)
        if reconciled is not None:
            with self._locked():
                self._append(
                    "publication_receipt",
                    publication_key=publication_key,
                    receipt=reconciled,
                    reconciled=True,
                )
            return self.status(publication_key)
        try:
            receipt = client.call_tool(
                "publish_kol_report",
                publish_request,
            )
        except Exception as exc:
            with self._locked():
                self._append(
                    "publication_call_uncertain",
                    publication_key=publication_key,
                    idempotency_key=publish_claim,
                    error_type=type(exc).__name__,
                    error_code=self._mcp_code(exc),
                )
            raise
        with self._locked():
            self._append(
                "publication_receipt",
                publication_key=publication_key,
                receipt=receipt,
                reconciled=False,
            )
        return self.status(publication_key)
