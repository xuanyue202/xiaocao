"""Short-lived, append-only KOL daytime coordination.

The coordinator owns only scheduling, ordering, recovery, and terminal
validation.  Existing source adapters continue to own discovery and
enrichment; source-video bytes are never accepted by this seam.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

from .enrichment_types import EnrichmentError, is_durable_report_only
from ._shared import (
    LOCAL_THESIS_ID_PATTERN,
    append_integrity_jsonl,
    read_integrity_jsonl,
)
from .publication import (
    PublicationError,
    PublicationLedger,
    PublicationTransport,
    build_append_only_publication_update,
    build_publish_request,
    build_record,
    canonical_sha256,
    evaluation_id,
    publication_id_for_source,
    report_id,
    stable_claim,
    viewpoint_id,
)
from .reader_copy import (
    ReaderCopyError,
    validate_reader_message,
    validate_reader_source_identity,
)
from .rendering import reader_source_title
from .writer_progress import (
    affected_set_digest,
    ConvergenceLedger,
    FailureFingerprint,
    normalize_source_result,
    resolve_repository_revision,
    WriterProgress,
)


BEIJING = ZoneInfo("Asia/Shanghai")
DAYTIME_HOURS = frozenset(range(7, 24))
MAX_LEDGER_LINE_BYTES = 512 * 1024
MAX_REMINDER_BYTES = 2048
ALERT_BASES = {
    "market_posture",
    "buy",
    "sell",
    "hold",
    "position_boundary",
    "direction",
    "actionable_trigger",
}
VIEWPOINT_TRIGGERS = {
    "same_kol_publication",
    "due_horizon",
    "due_trigger",
    "due_falsifier",
    "material_fact_change",
    "user_request",
}
VIEWPOINT_EVALUATION_STATUSES = {
    "current",
    "expired",
    "invalidated",
    "uncertain",
}
AGENT_OWNED_FAILURE_CATEGORIES = frozenset({
    "code_error",
    "schema_error",
    "environment_error",
    "provider_contract_error",
    "control_plane_handler_error",
    "local_runtime_error",
    "protocol_error",
})
_LOCAL_THESIS_ID = LOCAL_THESIS_ID_PATTERN


def _next_local_playback_recheck(value: datetime) -> datetime:
    """Return the next China-time 20-minute capture boundary."""

    if value.tzinfo is None:
        raise DailyError("daily coordinator clock needs a timezone")
    local = value.astimezone(BEIJING).replace(second=0, microsecond=0)
    next_minute = ((local.minute // 20) + 1) * 20
    if next_minute == 60:
        return (local + timedelta(hours=1)).replace(minute=0)
    return local.replace(minute=next_minute)


class DailyError(EnrichmentError):
    """The daily coordination contract could not be proved."""


class ControlPlaneHandlerError(DailyError):
    """A declared progress handler did not prove its bounded operation."""


class TransientSourceError(DailyError):
    """A self-recoverable source failure with credential-safe diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "source_error",
        code: str = "source_temporarily_unavailable",
        stage: str = "source_run",
    ):
        self.category = str(category or "").strip()
        self.code = str(code or "").strip()
        self.stage = str(stage or "").strip()
        for token in (self.category, self.code, self.stage):
            if (
                not token
                or len(token) > 64
                or not token.isascii()
                or not token[0].islower()
                or not token.replace("_", "").isalnum()
            ):
                raise ValueError("transient source diagnostic token is invalid")
        super().__init__(message)

    def diagnostic(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "code": self.code,
            "stage": self.stage,
            "retryable": True,
        }


class UserActionBlocker(DailyError):
    """A structured blocker whose exact user action may be notified once."""

    def __init__(
        self,
        blocker_key: str,
        action: str,
        *,
        waiting_items: list[Mapping[str, Any]] | None = None,
        claim_receipt_summary: Mapping[str, int] | None = None,
    ):
        self.blocker_key = str(blocker_key or "").strip()
        self.action = str(action or "").strip()
        self.waiting_items = [dict(row) for row in (waiting_items or [])]
        self.claim_receipt_summary = (
            {
                "claim_count": int(
                    (claim_receipt_summary or {}).get("claim_count") or 0
                ),
                "receipt_count": int(
                    (claim_receipt_summary or {}).get("receipt_count") or 0
                ),
                "uncertain_effect_count": int(
                    (claim_receipt_summary or {}).get(
                        "uncertain_effect_count"
                    )
                    or 0
                ),
            }
            if claim_receipt_summary is not None
            else None
        )
        if not self.blocker_key or not self.action:
            raise ValueError("user-action blocker needs a key and exact action")
        super().__init__(self.action)


def _utc_iso8601(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailyError("daily timestamp is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DailyError("daily timestamp needs a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sha256(value: Any) -> str:
    return canonical_sha256(value)


def _required_reason(value: Any, *, label: str) -> str:
    reason = str(value or "").strip()
    if not reason:
        raise DailyError(f"{label} requires a reason")
    return reason


def _reader_text_list(value: Any, *, label: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise DailyError(f"{label} must be a list")
    rows = [str(row or "").strip() for row in value]
    if any(not row for row in rows):
        raise DailyError(f"{label} contains an empty value")
    return rows


def _publication_evidence_list(value: Any) -> list[Any]:
    """Keep reader-safe evidence while excluding local filesystem paths."""

    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise DailyError("longitudinal evaluation evidence must be a list")
    return [
        row
        for row in value
        if not (
            isinstance(row, str)
            and Path(row).expanduser().is_absolute()
        )
    ]


def _normalize_longitudinal_projection(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Validate one explicit, evidence-gated longitudinal decision."""

    projection = item.get("longitudinal_projection")
    if not isinstance(projection, dict):
        raise DailyError(
            "promoted event needs an explicit longitudinal projection decision"
        )
    status = str(projection.get("status") or "").strip()
    reason = _required_reason(
        projection.get("reason"),
        label="longitudinal projection",
    )
    raw_viewpoints = projection.get("viewpoints", [])
    if not isinstance(raw_viewpoints, list):
        raise DailyError("longitudinal viewpoints must be a list")
    if status == "none":
        if raw_viewpoints:
            raise DailyError(
                "longitudinal none decision cannot contain viewpoints"
            )
        return {
            "status": status,
            "reason": reason,
            "viewpoints": [],
        }
    if status != "promoted" or not raw_viewpoints:
        raise DailyError(
            "longitudinal promoted decision needs at least one viewpoint"
        )
    evaluated_at = _utc_iso8601(
        str(projection.get("evaluated_at") or "")
    )
    claims = item.get("claims")
    if not isinstance(claims, list) or not claims:
        raise DailyError(
            "longitudinal viewpoints need the complete source claim inventory"
        )
    claim_ids = {
        str(row.get("claim_id") or "").strip()
        for row in claims
        if isinstance(row, dict)
        and str(row.get("claim_id") or "").strip()
    }
    if not claim_ids:
        raise DailyError("longitudinal source claim inventory is empty")
    normalized: list[dict[str, Any]] = []
    local_ids: set[str] = set()
    for index, raw in enumerate(raw_viewpoints):
        if not isinstance(raw, dict):
            raise DailyError(
                f"longitudinal viewpoint {index} must be an object"
            )
        local_id = str(raw.get("local_thesis_id") or "").strip()
        if not _LOCAL_THESIS_ID.fullmatch(local_id):
            raise DailyError(
                f"longitudinal viewpoint {index} has an invalid local thesis id"
            )
        if local_id in local_ids:
            raise DailyError("longitudinal viewpoint ids must be unique")
        local_ids.add(local_id)
        required = {
            field: str(raw.get(field) or "").strip()
            for field in ("subject", "stance", "horizon", "reasoning")
        }
        if any(not value for value in required.values()):
            raise DailyError(
                f"longitudinal viewpoint {index} lacks reader-facing meaning"
            )
        refs = raw.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise DailyError(
                f"longitudinal viewpoint {index} lacks evidence refs"
            )
        for ref in refs:
            if not isinstance(ref, dict):
                raise DailyError("longitudinal evidence ref must be an object")
            claim_id = str(ref.get("claim_id") or "").strip()
            excerpt = str(ref.get("excerpt") or "").strip()
            if claim_id not in claim_ids or not excerpt:
                raise DailyError(
                    "longitudinal evidence ref is not bound to a source claim"
                )
        evaluation = raw.get("evaluation")
        if not isinstance(evaluation, dict):
            raise DailyError(
                f"longitudinal viewpoint {index} lacks an initial evaluation"
            )
        evaluation_status = str(evaluation.get("status") or "").strip()
        if evaluation_status not in VIEWPOINT_EVALUATION_STATUSES:
            raise DailyError(
                "longitudinal viewpoint evaluation status is unsupported"
            )
        basis = str(evaluation.get("basis") or "").strip()
        if not basis:
            raise DailyError(
                "longitudinal viewpoint evaluation needs a basis"
            )
        as_of = _utc_iso8601(
            str(evaluation.get("as_of") or evaluated_at)
        )
        normalized.append(
            {
                "local_thesis_id": local_id,
                **required,
                "attribution": str(
                    raw.get("attribution") or item.get("author") or ""
                ).strip(),
                "role": str(raw.get("role") or "").strip(),
                "triggers": _reader_text_list(
                    raw.get("triggers"),
                    label="longitudinal triggers",
                ),
                "falsifiers": _reader_text_list(
                    raw.get("falsifiers"),
                    label="longitudinal falsifiers",
                ),
                "uncertainties": _reader_text_list(
                    raw.get("uncertainties"),
                    label="longitudinal uncertainties",
                ),
                "evidence_refs": refs,
                "evaluation": {
                    "status": evaluation_status,
                    "as_of": as_of,
                    "evaluated_at": evaluated_at,
                    "basis": basis,
                    "confidence": str(
                        evaluation.get("confidence") or "medium"
                    ).strip(),
                    "uncertainties": _reader_text_list(
                        evaluation.get("uncertainties"),
                        label="longitudinal evaluation uncertainties",
                    ),
                    "evidence": _publication_evidence_list(
                        evaluation.get("evidence")
                    ),
                },
            }
        )
    return {
        "status": status,
        "reason": reason,
        "evaluated_at": evaluated_at,
        "viewpoints": normalized,
    }


def _initial_longitudinal_records(
    *,
    report_id_value: str,
    kol_id: str,
    source_published_at: str,
    source_binding: dict[str, Any],
    projection: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    viewpoint_ids: list[str] = []
    publication_id = str(source_binding["publication_id"])
    for spec in projection["viewpoints"]:
        refs = spec["evidence_refs"]
        viewpoint_id_value = viewpoint_id(
            report_id_value,
            spec["local_thesis_id"],
            refs,
        )
        viewpoint_ids.append(viewpoint_id_value)
        payload = {
            "viewpoint_id": viewpoint_id_value,
            "report_id": report_id_value,
            "kol_id": kol_id,
            "local_thesis_id": spec["local_thesis_id"],
            "subject": spec["subject"],
            "stance": spec["stance"],
            "source_published_at": source_published_at,
            "evidence_refs": refs,
            "horizon": spec["horizon"],
            "reasoning": spec["reasoning"],
        }
        for field in (
            "attribution",
            "role",
            "triggers",
            "falsifiers",
            "uncertainties",
        ):
            if spec.get(field) not in (None, "", []):
                payload[field] = spec[field]
        evaluated_at = spec["evaluation"]["evaluated_at"]
        viewpoint = build_record(
            kind="viewpoint",
            record_id_value=viewpoint_id_value,
            idempotency_key=stable_claim(
                "put",
                publication_id,
                "initial-viewpoint-v1",
                viewpoint_id_value,
            ),
            created_at=evaluated_at,
            source_binding=source_binding,
            payload=payload,
        )
        records.append(viewpoint)
        evaluation = spec["evaluation"]
        evaluation_id_value = evaluation_id(
            viewpoint_id_value,
            evaluation["as_of"],
            evaluation["evaluated_at"],
        )
        evaluation_payload = {
            "evaluation_id": evaluation_id_value,
            "viewpoint_id": viewpoint_id_value,
            "status": evaluation["status"],
            "as_of": evaluation["as_of"],
            "evaluated_at": evaluation["evaluated_at"],
            "basis": evaluation["basis"],
            "confidence": evaluation["confidence"],
            "uncertainties": evaluation["uncertainties"],
        }
        if evaluation["evidence"]:
            evaluation_payload["evidence"] = evaluation["evidence"]
        records.append(
            build_record(
                kind="viewpoint_evaluation",
                record_id_value=evaluation_id_value,
                idempotency_key=stable_claim(
                    "put",
                    publication_id,
                    "initial-evaluation-v1",
                    evaluation_id_value,
                ),
                created_at=evaluation["evaluated_at"],
                source_binding=source_binding,
                payload=evaluation_payload,
            )
        )
    return records, viewpoint_ids


def validate_source_event(value: Any) -> dict[str, Any]:
    """Validate one content-value result and its independent terminals."""

    if not isinstance(value, dict) or value.get("kind") != "source_event":
        raise DailyError("daily source event is invalid")
    event_id = str(value.get("event_id") or "").strip()
    if not event_id:
        raise DailyError("daily source event needs a stable event_id")
    if int(value.get("coordinator_source_video_bytes") or 0) != 0:
        raise DailyError("daily coordinator must read zero source-video bytes")
    content = value.get("content_value")
    if not isinstance(content, dict):
        raise DailyError("daily source event lacks content value")
    disposition = str(content.get("status") or "")
    _required_reason(content.get("reason"), label="content value")
    report = value.get("gray_report")
    alert = value.get("alert")
    book = value.get("book_kol_us")
    if not all(isinstance(row, dict) for row in (report, alert, book)):
        raise DailyError("daily source event lacks independent terminals")
    durable_report_only = is_durable_report_only(value)
    valid_book_status = book.get("status") in {"filled", "no_trade"} or (
        durable_report_only and book.get("status") == "not_created"
    )
    if (
        book.get("book") != "KOL-US"
        or book.get("paper_only") is not True
        or not valid_book_status
    ):
        raise DailyError("daily Book terminal is not KOL-US paper-only")
    if book.get("status") in {"no_trade", "not_created"}:
        _required_reason(book.get("reason"), label="Book KOL-US no-trade")
    if disposition == "low_density":
        if report.get("status") != "not_created":
            raise DailyError("low-density item cannot create a gray report")
        if alert.get("status") != "not_created":
            raise DailyError("low-density item cannot create a reminder")
        if book.get("status") != "no_trade":
            raise DailyError("low-density item cannot create a Book trade")
        return value
    if disposition != "promoted":
        raise DailyError("daily content value result is unsupported")
    tier = str(content.get("tier") or "")
    if tier not in {"report_only", "alert_eligible"}:
        raise DailyError("promoted event needs a supported content tier")
    if (
        report.get("status") != "published"
        or not str(report.get("receipt") or "").strip()
        or not str(report.get("detail_url") or "").strip()
    ):
        raise DailyError("promoted event lacks a durable complete gray report")
    try:
        report_order = int(report["terminal_order"])
        alert_order = int(alert["terminal_order"])
        book_order = int(book["terminal_order"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DailyError("promoted terminal order is incomplete") from exc
    if report_order >= alert_order or report_order >= book_order:
        raise DailyError("gray report must precede reminder and Book terminals")
    if tier == "report_only":
        if alert.get("status") != "not_eligible":
            raise DailyError("report-only event needs a legal no-alert terminal")
        _required_reason(alert.get("reason"), label="no-alert terminal")
    else:
        if (
            alert.get("status") != "delivered"
            or not str(alert.get("receipt") or "").strip()
            or alert.get("all_recipients") is not True
            or alert.get("stable_link_count") != 1
            or alert.get("stable_report_url") != report.get("detail_url")
        ):
            raise DailyError(
                "alert event needs one all-recipient stable-link reminder"
            )
    return value


def validate_viewpoint_terminal(value: Any) -> dict[str, Any]:
    """Validate viewpoint maintenance and its zero-side-effect boundary."""

    if not isinstance(value, dict) or value.get("kind") not in {
        "viewpoint_evaluation",
        "viewpoint_projection",
    }:
        raise DailyError("viewpoint maintenance terminal is invalid")
    publication = value.get("gray_publication") or {}
    if (
        value.get("trigger") not in VIEWPOINT_TRIGGERS
        or publication.get("status") != "published"
        or not str(publication.get("detail_url") or "").strip()
        or value.get("history_preserved") is not True
        or value.get("current_projection_order_preserved") is not True
        or (value.get("alert") or {}).get("status") != "not_created"
        or (value.get("book_kol_us") or {}).get("status") != "not_created"
        or int(value.get("coordinator_source_video_bytes") or 0) != 0
    ):
        raise DailyError("viewpoint maintenance side-effect boundary failed")
    if value.get("kind") == "viewpoint_projection" and (
        int(value.get("viewpoint_count") or 0) < 1
        or int(value.get("evaluation_count") or 0) < 1
    ):
        raise DailyError("initial viewpoint projection is incomplete")
    return value


def _validate_source_outcome(outcome: dict[str, Any]) -> None:
    events = outcome.get("events", [])
    if outcome.get("status") == "completed":
        if not isinstance(events, list) or not events:
            raise DailyError("completed daily source needs terminal events")
        identities: set[str] = set()
        for event in events:
            if isinstance(event, dict) and event.get("kind") == "source_event":
                validated = validate_source_event(event)
            else:
                validated = validate_viewpoint_terminal(event)
            identity = str(validated["event_id"])
            if identity in identities:
                raise DailyError("independent source events cannot be merged")
            identities.add(identity)
    elif events not in (None, []):
        raise DailyError("non-completed daily source cannot claim terminal events")


def build_triggered_evaluation_candidate(
    current_publication: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Build one append-only currentness update with no event side effects."""

    trigger = str(request.get("trigger") or "")
    if trigger not in VIEWPOINT_TRIGGERS:
        raise DailyError("viewpoint evaluation trigger is unsupported")
    report = current_publication.get("report")
    records = current_publication.get("records")
    if not isinstance(report, dict) or not isinstance(records, list):
        raise DailyError("current viewpoint publication is incomplete")
    viewpoint_id_value = str(request.get("viewpoint_id") or "")
    if not any(
        isinstance(row, dict)
        and row.get("kind") == "viewpoint"
        and row.get("record_id") == viewpoint_id_value
        for row in records
    ):
        raise DailyError("triggered viewpoint does not exist in current history")
    as_of = str(request.get("as_of") or "").strip()
    evaluated_at = str(request.get("evaluated_at") or "").strip()
    basis = str(request.get("basis") or "").strip()
    status = str(request.get("status") or "").strip()
    if (
        not as_of
        or not evaluated_at
        or not basis
        or status not in VIEWPOINT_EVALUATION_STATUSES
    ):
        raise DailyError("triggered viewpoint evaluation is incomplete")
    as_of_utc = _utc_iso8601(as_of)
    evaluated_at_utc = _utc_iso8601(evaluated_at)
    evaluation_id_value = evaluation_id(
        viewpoint_id_value,
        as_of_utc,
        evaluated_at_utc,
    )
    evaluation = build_record(
        kind="viewpoint_evaluation",
        record_id_value=evaluation_id_value,
        idempotency_key=stable_claim(
            "put",
            str(report["record_id"]),
            "evaluation",
            evaluation_id_value,
        ),
        created_at=evaluated_at_utc,
        source_binding=report["source_binding"],
        payload={
            "evaluation_id": evaluation_id_value,
            "viewpoint_id": viewpoint_id_value,
            "status": status,
            "as_of": as_of_utc,
            "evaluated_at": evaluated_at_utc,
            "basis": basis,
            "confidence": str(request.get("confidence") or "medium"),
            "uncertainties": list(request.get("uncertainties") or []),
        },
    )
    updated_records, publish = build_append_only_publication_update(
        current_records=records,
        additions=[evaluation],
        viewpoint_ids=list(report["payload"].get("viewpoint_ids") or []),
        created_at=evaluated_at,
        revision=f"triggered-{evaluation_id_value}",
        reason="触发式长期观点时效复核；不创建事件提醒或 Book 动作。",
    )
    return {
        "publication_key": f"viewpoint-maintenance:{evaluation_id_value}",
        "records": updated_records,
        "publish_request": publish,
        "metadata": {
            "trigger": trigger,
            "evaluation_id": evaluation_id_value,
            "notification_claim_authorized": False,
            "book_kol_us_replay_authorized": False,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
        },
    }


def build_initial_projection_candidate(
    current_publication: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Append the first evidence-gated projection to one report-only history."""

    if request.get("operation") != "initial_projection":
        raise DailyError("initial viewpoint projection operation is invalid")
    if request.get("trigger") != "user_request":
        raise DailyError("initial viewpoint projection needs user review")
    report = current_publication.get("report")
    records = current_publication.get("records")
    if not isinstance(report, dict) or not isinstance(records, list):
        raise DailyError("current viewpoint publication is incomplete")
    if report["payload"].get("alert_eligible") is not False:
        raise DailyError("initial viewpoint backfill is only for report-only history")
    if report["payload"].get("viewpoint_ids") or any(
        row.get("kind") == "viewpoint" for row in records
    ):
        raise DailyError("initial viewpoint projection already exists")
    if (
        str(request.get("report_id") or "") != str(report["record_id"])
        or str(request.get("evidence_sha256") or "")
        != str(report["source_binding"]["evidence_sha256"])
    ):
        raise DailyError("initial viewpoint projection changed source evidence")
    evidence_path = Path(str(request.get("evidence_path") or "")).expanduser()
    if not evidence_path.is_file():
        raise DailyError("initial viewpoint projection evidence is missing")
    try:
        evidence_bytes = evidence_path.read_bytes()
        evidence_text = evidence_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DailyError(
            "initial viewpoint projection evidence is not valid Markdown"
        ) from exc
    if hashlib.sha256(evidence_bytes).hexdigest() != request["evidence_sha256"]:
        raise DailyError("initial viewpoint projection evidence hash changed")
    claims = request.get("claims")
    if not isinstance(claims, list) or any(
        not isinstance(row, dict)
        or not str(row.get("claim_id") or "").strip()
        or not str(row.get("quote") or "").strip()
        or str(row["quote"]).strip() not in evidence_text
        for row in claims
    ):
        raise DailyError(
            "initial viewpoint projection claims are not bound to evidence"
        )
    projection = _normalize_longitudinal_projection(
        {
            "author": report["payload"]["author"],
            "claims": claims,
            "longitudinal_projection": request.get(
                "longitudinal_projection"
            ),
        }
    )
    if projection["status"] != "promoted":
        raise DailyError("initial viewpoint backfill needs real viewpoints")
    additions, viewpoint_ids = _initial_longitudinal_records(
        report_id_value=str(report["record_id"]),
        kol_id=str(report["payload"]["kol_id"]),
        source_published_at=str(report["payload"]["source_published_at"]),
        source_binding=report["source_binding"],
        projection=projection,
    )
    report_copy = request.get("report_copy")
    report_payload_updates: dict[str, str] | None = None
    if report_copy is not None:
        if not isinstance(report_copy, dict):
            raise DailyError("initial viewpoint report copy must be an object")
        allowed_report_copy_fields = {"title", "summary", "report_body"}
        if set(report_copy) != allowed_report_copy_fields:
            raise DailyError(
                "initial viewpoint report copy fields must be exactly title, "
                "summary, and report_body"
            )
        report_payload_updates = {
            field: str(report_copy.get(field) or "").strip()
            for field in allowed_report_copy_fields
        }
        if any(not value for value in report_payload_updates.values()):
            raise DailyError(
                "initial viewpoint report copy fields cannot be empty"
            )
    projection_id = canonical_sha256(
        {
            "report_id": report["record_id"],
            "evidence_sha256": request["evidence_sha256"],
            "projection": projection,
            "report_copy": report_payload_updates,
        }
    )
    updated_records, publish = build_append_only_publication_update(
        current_records=records,
        additions=additions,
        viewpoint_ids=viewpoint_ids,
        created_at=projection["evaluated_at"],
        revision=f"initial-projection-{projection_id}",
        reason=(
            "补齐来源证据支持的初始长期观点并修订同一报告正文；"
            "不创建提醒或 Book 动作。"
            if report_payload_updates
            else "补齐来源证据支持的初始长期观点；不创建提醒或 Book 动作。"
        ),
        report_payload_updates=report_payload_updates,
    )
    return {
        "publication_key": f"viewpoint-projection:{projection_id}",
        "records": updated_records,
        "publish_request": publish,
        "metadata": {
            "trigger": "user_request",
            "projection_id": projection_id,
            "viewpoint_count": len(viewpoint_ids),
            "evaluation_count": len(
                [row for row in additions if row["kind"] == "viewpoint_evaluation"]
            ),
            "report_copy_corrected": bool(report_payload_updates),
            "notification_claim_authorized": False,
            "book_kol_us_replay_authorized": False,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
        },
    }


def initial_projection_terminal(
    candidate: dict[str, Any],
    publication_state: dict[str, Any],
) -> dict[str, Any]:
    receipt = publication_state.get("publish_receipt") or {}
    if (
        publication_state.get("completed") is not True
        or receipt.get("recordState") not in {"published", "superseded"}
        or not str(receipt.get("detailUrl") or "").strip()
    ):
        raise DailyError("initial viewpoint projection did not publish")
    metadata = candidate["metadata"]
    return {
        "kind": "viewpoint_projection",
        "event_id": metadata["projection_id"],
        "trigger": metadata["trigger"],
        "viewpoint_count": metadata["viewpoint_count"],
        "evaluation_count": metadata["evaluation_count"],
        "gray_publication": {
            "status": "published",
            "detail_url": receipt["detailUrl"],
        },
        "history_preserved": True,
        "current_projection_order_preserved": True,
        "alert": {"status": "not_created"},
        "book_kol_us": {"status": "not_created"},
        "coordinator_source_video_bytes": 0,
    }


def triggered_evaluation_terminal(
    candidate: dict[str, Any],
    publication_state: dict[str, Any],
) -> dict[str, Any]:
    receipt = publication_state.get("publish_receipt") or {}
    if (
        publication_state.get("completed") is not True
        or receipt.get("recordState") not in {"published", "superseded"}
        or not str(receipt.get("detailUrl") or "").strip()
    ):
        raise DailyError("viewpoint evaluation publication did not complete")
    metadata = candidate["metadata"]
    return {
        "kind": "viewpoint_evaluation",
        "event_id": metadata["evaluation_id"],
        "trigger": metadata["trigger"],
        "gray_publication": {
            "status": "published",
            "detail_url": receipt["detailUrl"],
        },
        "history_preserved": True,
        "current_projection_order_preserved": True,
        "alert": {"status": "not_created"},
        "book_kol_us": {"status": "not_created"},
        "coordinator_source_video_bytes": 0,
    }


@dataclass(frozen=True)
class DailyPublicationContext:
    """Stable lightweight binding for one independent source event."""

    adapter: str
    source_identity: str
    publication_version: str
    kol_id: str
    source: str
    source_published_at: str
    media_types: tuple[str, ...]
    source_parts: tuple[dict[str, Any], ...]


def _publication_candidate(
    item: dict[str, Any],
    *,
    context: DailyPublicationContext,
) -> dict[str, Any]:
    content = item.get("content_value") or {}
    if content.get("status") != "promoted":
        raise DailyError("only promoted content can create a gray report")
    tier = str(content.get("tier") or "")
    if tier not in {"report_only", "alert_eligible"}:
        raise DailyError("promoted content tier is invalid")
    if tier == "alert_eligible":
        bases = content.get("alert_basis")
        if (
            not isinstance(bases, list)
            or not bases
            or not set(str(row) for row in bases) <= ALERT_BASES
        ):
            raise DailyError("alert-eligible event lacks a permissive live basis")
    publication = item.get("publication")
    if not isinstance(publication, dict):
        raise DailyError("promoted event lacks reviewed publication copy")
    publication_key = publication_id_for_source(
        adapter=context.adapter,
        source_identity=context.source_identity,
    )
    report_id_value = report_id(publication_key)
    evidence_sha = str(item.get("evidence_sha256") or "")
    if len(evidence_sha) != 64:
        raise DailyError("promoted event lacks evidence_sha256")
    decision_sha = canonical_sha256(item)
    source_binding = {
        "publication_id": publication_key,
        "publication_version": context.publication_version,
        "evidence_sha256": evidence_sha,
        "decision_result_sha256": decision_sha,
        "extraction_contract_version": "kol-intelligence-v1",
    }
    alert_eligible = tier == "alert_eligible"
    alert_reason = (
        "permissive_live_investment_content_gate"
        if alert_eligible
        else _required_reason(
            content.get("no_alert_reason") or content.get("reason"),
            label="report-only no-alert",
        )
    )
    insight = item.get("reader_insight") or {}
    source_published_at = _utc_iso8601(context.source_published_at)
    projection = _normalize_longitudinal_projection(item)
    longitudinal_records, viewpoint_ids = _initial_longitudinal_records(
        report_id_value=report_id_value,
        kol_id=context.kol_id,
        source_published_at=source_published_at,
        source_binding=source_binding,
        projection=projection,
    )
    report_payload = {
        "report_id": report_id_value,
        "report_kind": "publication_event",
        "kol_id": context.kol_id,
        "author": str(item.get("author") or ""),
        "source": context.source,
        "title": reader_source_title(item),
        "summary": str(publication.get("summary") or ""),
        "source_published_at": source_published_at,
        "media_types": list(context.media_types),
        "source_parts": [dict(row) for row in context.source_parts],
        "report_format": "markdown",
        "report_body": str(publication.get("report_body") or ""),
        "viewpoint_ids": viewpoint_ids,
        "alert_eligible": alert_eligible,
        "alert_reason": alert_reason,
        "reader_insight": {
            "status": str(insight.get("status") or "useful"),
            "reason": str(
                insight.get("summary")
                or content.get("reason")
                or "本事件包含可供家庭检索的投资判断。"
            ),
        },
    }
    try:
        validate_reader_source_identity(
            source_name=Path(str(item.get("evidence_path") or "")).name,
            reader_title=report_payload["title"],
            report_body=report_payload["report_body"],
        )
    except ReaderCopyError as exc:
        raise DailyError(str(exc)) from exc
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key=stable_claim(
            "put", publication_key, "report", decision_sha
        ),
        created_at=source_published_at,
        source_binding=source_binding,
        payload=report_payload,
    )
    records = [report, *longitudinal_records]
    publish = build_publish_request(
        records,
        idempotency_key=stable_claim(
            "publish", publication_key, decision_sha
        ),
        reason="新 KOL 来源事件：先发布完整报告，再完成提醒与纸面 Book。",
    )
    return {
        "publication_key": publication_key,
        "records": records,
        "publish_request": publish,
        "metadata": {
            "historical": False,
            "notification_claim_authorized": alert_eligible,
            "book_kol_us_replay_authorized": not is_durable_report_only(item),
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "viewpoint_count": len(viewpoint_ids),
            "evaluation_count": len(
                [
                    row
                    for row in longitudinal_records
                    if row["kind"] == "viewpoint_evaluation"
                ]
            ),
        },
    }


def _without_urls(value: Any) -> str:
    words = [
        word
        for word in str(value or "").split()
        if not word.startswith(("http://", "https://"))
    ]
    return " ".join(words).strip()


def _fit_reminder(value: str, *, suffix: str) -> str:
    budget = MAX_REMINDER_BYTES - len(suffix.encode("utf-8"))
    if budget <= 0:
        raise DailyError("stable report link exceeds reminder boundary")
    encoded = value.encode("utf-8")
    if len(encoded) > budget:
        encoded = encoded[: max(0, budget - len("…".encode("utf-8")))]
        while True:
            try:
                value = encoded.decode("utf-8") + "…"
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    return value.rstrip() + suffix


def _reader_reminder_copy(
    item: dict[str, Any],
    publication: dict[str, Any],
    *,
    detail_url: str,
) -> tuple[str, str]:
    reader_reminder = item.get("reader_reminder") or {}
    insight = item.get("reader_insight") or {}
    reminder_title = str(reader_reminder.get("title") or "").strip()
    title = (
        f"投资情报｜{item.get('author')}："
        f"{reminder_title or reader_source_title(item)}"
    )
    reminder_summary = _without_urls(reader_reminder.get("summary"))
    body = reminder_summary or "\n\n".join(
        row
        for row in (
            _without_urls(insight.get("summary")),
            _without_urls(publication.get("remaining_summary")),
        )
        if row
    )
    suffix = f"\n\n查看完整报告：{detail_url}"
    body = _fit_reminder(body, suffix=suffix)
    try:
        validate_reader_message(title, body)
    except ReaderCopyError as exc:
        raise DailyError(str(exc)) from exc
    return title, body


def knowledge_terminal_for_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Project the independently completed knowledge branch into its terminal."""

    status = str(item.get("knowledge_status") or "").strip()
    if status == "no_reusable_knowledge":
        return {
            "status": status,
            "reason": _required_reason(
                item.get("knowledge_reason"),
                label="knowledge branch",
            ),
        }
    if status != "reusable_knowledge":
        raise DailyError("daily knowledge branch has no terminal status")
    path_value = str(item.get("durable_distillation_path") or "").strip()
    sha256 = str(item.get("durable_distillation_sha256") or "").strip()
    path = Path(path_value).expanduser().resolve()
    try:
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DailyError(
            "reusable knowledge terminal lost its durable distillation"
        ) from exc
    if not re.fullmatch(r"[0-9a-f]{64}", sha256) or sha256 != actual_sha256:
        raise DailyError(
            "reusable knowledge terminal changed its durable distillation"
        )
    return {
        "status": status,
        "distillation_path": str(path),
        "distillation_sha256": sha256,
    }


class DailyPublicationPipeline:
    """Publish one event report before delegating Book and reminder effects."""

    def __init__(
        self,
        delegate: Any,
        *,
        ledger: PublicationLedger,
        client: PublicationTransport,
        context: DailyPublicationContext,
    ):
        self.delegate = delegate
        self.ledger = ledger
        self.client = client
        self.context = context
        self.book = delegate.book
        self._publication_state: dict[str, Any] | None = None
        self._content: dict[str, Any] | None = None
        self._publication_copy: dict[str, Any] | None = None
        self._reminder_message: tuple[str, str] | None = None

    def process(self, bundle: dict[str, Any]) -> dict[str, Any]:
        items = bundle.get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise DailyError("daily publication pipeline needs one source event")
        item = items[0]
        if not isinstance(item, dict):
            raise DailyError("daily publication item is invalid")
        content = item.get("content_value")
        if not isinstance(content, dict):
            raise DailyError("daily decision bundle lacks content value")
        self._content = content
        self._publication_copy = item.get("publication") or {}
        if content.get("status") == "promoted":
            publication_key = publication_id_for_source(
                adapter=self.context.adapter,
                source_identity=self.context.source_identity,
            )
            try:
                state = self.ledger.status(publication_key)
            except PublicationError as exc:
                if "not prepared" not in str(exc):
                    raise
                state = None
            if not state or not state.get("completed"):
                candidate = _publication_candidate(item, context=self.context)
                self.ledger.prepare(
                    candidate["publication_key"],
                    candidate["records"],
                    candidate["publish_request"],
                    metadata=candidate["metadata"],
                )
                state = self.ledger.run(
                    candidate["publication_key"],
                    self.client,
                )
            receipt = state.get("publish_receipt") or {}
            if (
                not state.get("completed")
                or not str(receipt.get("detailUrl") or "").strip()
            ):
                raise DailyError("gray report receipt lacks a stable detail URL")
            self._publication_state = state
            if content.get("tier") == "alert_eligible":
                self._reminder_message = _reader_reminder_copy(
                    item,
                    self._publication_copy,
                    detail_url=str(receipt["detailUrl"]),
                )
        elif content.get("status") != "low_density":
            raise DailyError("daily content value result is invalid")
        result = self.delegate.process(bundle)
        self._sync_terminal(result, alert_order=None)
        return result

    def _sync_terminal(
        self,
        result: dict[str, Any],
        *,
        alert_order: int | None,
    ) -> None:
        item = result["items"][0]
        content = self._content or {}
        book = item.get("book_kol_us") or {}
        knowledge = knowledge_terminal_for_item(item)
        if content.get("status") == "low_density":
            terminal = {
                "kind": "source_event",
                "event_id": self.context.source_identity,
                "author": item.get("author"),
                "source_binding": {
                    "source_identity": self.context.source_identity,
                    "publication_version": self.context.publication_version,
                },
                "content_value": content,
                "claim_semantic_routing": item.get("claim_semantic_routing") or {},
                "gray_report": {"status": "not_created"},
                "alert": {"status": "not_created"},
                "book_kol_us": book,
                "knowledge_effect": knowledge,
                "coordinator_source_video_bytes": 0,
            }
        else:
            receipt = (self._publication_state or {}).get("publish_receipt") or {}
            notification = item.get("notification") or {}
            tier = content.get("tier")
            if tier == "report_only":
                alert = {
                    "status": "not_eligible",
                    "reason": str(
                        content.get("no_alert_reason")
                        or content.get("reason")
                        or ""
                    ),
                    "terminal_order": alert_order or 3,
                }
            elif notification.get("status") == "delivered":
                alert = {
                    "status": "delivered",
                    "receipt": notification.get("receipt"),
                    "all_recipients": True,
                    "stable_report_url": receipt.get("detailUrl"),
                    "stable_link_count": 1,
                    "terminal_order": alert_order or 3,
                }
            else:
                alert = {
                    "status": "pending",
                    "terminal_order": alert_order or 3,
                }
            terminal = {
                "kind": "source_event",
                "event_id": self.context.source_identity,
                "author": item.get("author"),
                "source_binding": {
                    "source_identity": self.context.source_identity,
                    "publication_version": self.context.publication_version,
                },
                "content_value": content,
                "claim_semantic_routing": item.get("claim_semantic_routing") or {},
                "gray_report": {
                    "status": "published",
                    "detail_url": receipt.get("detailUrl"),
                    "receipt": str(
                        receipt.get("idempotencyKey")
                        or receipt.get("receiptId")
                        or receipt.get("detailUrl")
                        or ""
                    ),
                    "terminal_order": 1,
                },
                "alert": alert,
                "book_kol_us": {**book, "terminal_order": 2},
                "knowledge_effect": knowledge,
                "coordinator_source_video_bytes": 0,
            }
        item["daily_terminal"] = terminal

    def deliver_wechat(
        self,
        result: dict[str, Any],
        *,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        content = self._content or {}
        if content.get("status") == "low_density":
            delivery = self.delegate.deliver_wechat(result, sender=sender)
            self._sync_terminal(result, alert_order=None)
            return delivery
        if content.get("tier") == "report_only":
            item = result["items"][0]
            notification = item.get("notification") or {}
            notification.update(
                {
                    "status": "suppressed",
                    "reason": str(
                        content.get("no_alert_reason")
                        or content.get("reason")
                        or ""
                    ),
                }
            )
            self._sync_terminal(result, alert_order=3)
            return {
                "status": "legally_not_eligible",
                "deliveries": [],
                "skipped": [notification.get("idempotency_key")],
            }
        receipt = (self._publication_state or {}).get("publish_receipt") or {}
        item = result["items"][0]
        if self._reminder_message is None:
            raise DailyError("reader reminder was not prepared")
        title, body = self._reminder_message

        def report_message(
            _item: dict[str, Any],
            _cross_source: dict[str, Any],
        ) -> tuple[str, str]:
            return title, body

        delivery = self.delegate.deliver_wechat(
            result,
            sender=sender,
            message_builder=report_message,
        )
        self._sync_terminal(result, alert_order=3)
        return delivery


class DailyCoordinator:
    """Public ``run``/``status``/``audit`` seam for Ticket 07."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        now: Callable[[], datetime] | None = None,
        failure_revision: Callable[[], str] | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.convergence = ConvergenceLedger(
            self.output_dir / "convergence.jsonl",
            now=lambda: self._beijing_now(),
        )
        self.lock_path = self.output_dir / ".lock"
        self.now = now or (lambda: datetime.now(BEIJING))
        self._failure_revision_provider = failure_revision or (
            lambda: resolve_repository_revision(Path(__file__).parents[3])
        )
        self._resolved_failure_revision: str | None = None
        self._thread_lock = threading.RLock()

    def _failure_revision(self) -> str:
        if self._resolved_failure_revision is None:
            try:
                self._resolved_failure_revision = (
                    self._failure_revision_provider()
                )
            except Exception:
                # A broken injected resolver is itself an Agent-owned control
                # plane fault. Keep the failure fingerprint bound to the real
                # checkout so that the fault can still converge in the ledger.
                self._resolved_failure_revision = resolve_repository_revision(
                    Path(__file__).parents[3]
                )
        return self._resolved_failure_revision

    def _agent_repair(
        self,
        name: str,
        *,
        category: str,
        code: str,
        stage: str,
        item_identity: str | None = None,
    ) -> tuple[dict[str, Any], WriterProgress]:
        identity = item_identity or f"{name}:source"
        fingerprint = FailureFingerprint(
            adapter=name,
            category=category,
            code=code,
            stage=stage,
            failure_revision=self._failure_revision(),
            provider_contract_version="xiaocao_writer_v1",
        )
        progress = WriterProgress.repair_required(
            item_identity=identity,
            fingerprint=fingerprint,
            repair_revision=None,
            affected_set_digest=affected_set_digest([{
                "identity": identity,
                "version_key": "current",
            }]),
            claim_receipt_summary={
                "claim_count": 0,
                "receipt_count": 0,
                "uncertain_effect_count": 0,
            },
            targeted_test_profile=f"kol_{name}_{stage}"[:128],
            narrow_resume_surface=(
                f"{name}:source"
                if identity == f"{name}:source"
                else f"{name}:{identity}"
            ),
            retryability="retryable",
        )
        return ({
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [{
                "identity": identity,
                "stage": stage,
                "failure": {
                    "category": category,
                    "code": code,
                    "stage": stage,
                    "retryable": True,
                },
            }],
            "failure": {
                "category": category,
                "code": code,
                "stage": stage,
                "retryable": True,
            },
            "repair_required": True,
            "resume_policy": progress.next_action,
            "user_action_required": False,
            "writer_progress": progress.to_dict(),
        }, progress)

    @staticmethod
    def _reconciliation_result(
        progress: WriterProgress,
        value: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(value, dict):
            raise ControlPlaneHandlerError(
                "reconciliation handler result must be an object"
            )
        if set(value) != {"outcome", "reconciliation_receipt"}:
            raise ControlPlaneHandlerError(
                "reconciliation handler must return only outcome and receipt"
            )
        outcome = value["outcome"]
        receipt = value["reconciliation_receipt"]
        if not isinstance(outcome, dict) or not isinstance(receipt, dict):
            raise ControlPlaneHandlerError(
                "reconciliation outcome and receipt must be objects"
            )
        required = {
            "event",
            "claim_identity",
            "readback_operation",
            "readback_evidence_sha256",
            "external_business_effects_replayed",
        }
        if set(receipt) != required:
            raise ControlPlaneHandlerError(
                "reconciliation receipt fields do not match the contract"
            )
        if (
            receipt["event"] != "reconciliation_completed"
            or receipt["claim_identity"]
            != progress.details["claim_identity"]
            or receipt["readback_operation"]
            != progress.details["readback_operation"]
            or re.fullmatch(
                r"[0-9a-f]{64}",
                str(receipt["readback_evidence_sha256"]),
            )
            is None
            or receipt["readback_evidence_sha256"]
            != canonical_sha256(outcome)
            or receipt["external_business_effects_replayed"] is not False
        ):
            raise ControlPlaneHandlerError(
                "reconciliation receipt does not prove the declared readback"
            )
        return outcome, receipt

    @staticmethod
    def _structured_input_result(
        progress: WriterProgress,
        value: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(value, dict):
            raise ControlPlaneHandlerError(
                "structured input handler result must be an object"
            )
        if set(value) != {"outcome", "structured_input_receipt"}:
            raise ControlPlaneHandlerError(
                "structured input handler must return only outcome and receipt"
            )
        outcome = value["outcome"]
        receipt = value["structured_input_receipt"]
        if not isinstance(outcome, dict) or not isinstance(receipt, dict):
            raise ControlPlaneHandlerError(
                "structured input outcome and receipt must be objects"
            )
        required = {
            "event",
            "request_id",
            "request_schema_version",
            "response_field",
            "immutable_bindings_sha256",
            "request_sha256",
            "response_sha256",
        }
        if set(receipt) != required:
            raise ControlPlaneHandlerError(
                "structured input receipt fields do not match the contract"
            )
        sha_fields = (
            "immutable_bindings_sha256",
            "request_sha256",
            "response_sha256",
        )
        if (
            receipt["event"] != "structured_input_consumed"
            or receipt["request_id"] != progress.details["request_id"]
            or receipt["request_schema_version"]
            != progress.details["request_schema_version"]
            or receipt["response_field"] != progress.details["response_field"]
            or receipt["immutable_bindings_sha256"]
            != canonical_sha256(progress.details["immutable_bindings"])
            or any(
                re.fullmatch(r"[0-9a-f]{64}", str(receipt[field])) is None
                for field in sha_fields
            )
        ):
            raise ControlPlaneHandlerError(
                "structured input receipt does not match the persisted request"
            )
        return outcome, receipt

    @staticmethod
    def _invoke_source_step(
        source: dict[str, Any],
        *,
        runner: Callable[[], Any],
        retained_outcome: dict[str, Any] | None,
        narrow_runner: Any,
        resume_progress: WriterProgress | None,
        resume_surface: str,
        structured_progress: WriterProgress | None,
        reconciliation_progress: WriterProgress | None,
    ) -> Any:
        if retained_outcome is not None:
            return retained_outcome
        if resume_progress is not None:
            return narrow_runner(resume_surface)
        if structured_progress is not None:
            handler = source.get("structured_input")
            if not callable(handler):
                raise ControlPlaneHandlerError(
                    "source lacks structured input continuation"
                )
            return handler(structured_progress)
        if reconciliation_progress is not None:
            handler = source.get("reconcile")
            if not callable(handler):
                raise ControlPlaneHandlerError(
                    "source lacks reconciliation"
                )
            return handler(reconciliation_progress)
        return runner()

    def _beijing_now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise DailyError("daily coordinator clock needs a timezone")
        return value.astimezone(BEIJING)

    def _xiaocao_provider_wait_after_failure(
        self,
        name: str,
        failure: Mapping[str, Any],
        prior_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Keep one exact playback wait alive across a provider outage."""

        if (
            name != "xiaocao_wechat_live"
            or str(failure.get("category") or "") != "source_error"
            or str(failure.get("code") or "")
            != "source_temporarily_unavailable"
            or str(failure.get("stage") or "") != "source_run"
        ):
            return None
        prior_result = next(
            (
                row.get("result")
                for row in reversed(prior_rows)
                if row.get("event") == "source_completed"
                and row.get("source") == name
            ),
            None,
        )
        if not isinstance(prior_result, dict) or prior_result.get("status") != (
            "waiting"
        ):
            return None
        prior_progress = next(
            (
                row.get("progress")
                for row in reversed(prior_rows)
                if row.get("event") == "source_progressed"
                and row.get("source") == name
            ),
            None,
        )
        if (
            not isinstance(prior_progress, dict)
            or prior_progress.get("status") != "wait_until"
        ):
            return None
        summary = prior_progress.get("claim_receipt_summary")
        if (
            not isinstance(summary, Mapping)
            or int(summary.get("claim_count", -1))
            != int(summary.get("receipt_count", -2))
            or int(summary.get("uncertain_effect_count", -1)) != 0
        ):
            return None
        waiting_items = prior_result.get("waiting_items")
        if not isinstance(waiting_items, list) or len(waiting_items) != 1:
            return None
        item = waiting_items[0]
        if not isinstance(item, Mapping):
            return None
        rebound = dict(item)
        if not (
            str(rebound.get("identity") or "")
            and str(rebound.get("capture_job_id") or "")
            and rebound.get("status") == "awaiting_playback"
        ):
            return None
        deadline = _next_local_playback_recheck(self._beijing_now())
        rebound["next_poll_not_before"] = deadline.isoformat(
            timespec="seconds"
        )
        rebound["failure"] = dict(failure)
        return {
            "status": "waiting",
            "retryable": True,
            "failure": dict(failure),
            "waiting_count": 1,
            "waiting_items": [rebound],
        }

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _events_unlocked(self) -> list[dict[str, Any]]:
        return read_integrity_jsonl(
            self.events_path,
            max_line_bytes=MAX_LEDGER_LINE_BYTES,
            label="daily ledger",
            error_factory=DailyError,
        )

    def events(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._events_unlocked()

    @staticmethod
    def _last_sweep_state(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        end = next(
            (
                index
                for index in range(len(rows) - 1, -1, -1)
                if rows[index].get("event") == "sweep_completed"
            ),
            None,
        )
        if end is None:
            return None
        completed = rows[end]
        if isinstance(completed.get("source_states"), list):
            return completed
        return {
            **completed,
            "health": "degraded",
            "source_states": [{
                "name": "coordinator",
                "status": "waiting",
                "repair_required": True,
                "user_action_required": False,
                "failure": {
                    "category": "schema_error",
                    "code": "progress_record_missing",
                    "stage": "daily_ledger_readback",
                    "retryable": True,
                },
            }],
        }

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "schema_version": 1,
            "event": event,
            "occurred_at": self._beijing_now().isoformat(timespec="seconds"),
            **fields,
        }
        return append_integrity_jsonl(
            self.events_path,
            row,
            max_line_bytes=MAX_LEDGER_LINE_BYTES,
            label="daily ledger",
            error_factory=DailyError,
        )

    @staticmethod
    def _source_states(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        states: list[dict[str, Any]] = []
        for row in results:
            state = {
                key: row[key]
                for key in (
                    "name",
                    "status",
                    "resume_policy",
                    "repair_required",
                    "repair_key",
                    "user_action_required",
                    "waiting_count",
                    "waiting_items",
                    "failure",
                    "writer_progress",
                    "resume_command",
                )
                if key in row
            }
            effect_count = (
                0
                if row.get("external_business_effects_replayed") is False
                else sum(
                    int(event.get("gray_report", {}).get("status") == "published")
                    + int(event.get("alert", {}).get("status") == "delivered")
                    + int(event.get("book_kol_us", {}).get("status") == "filled")
                    for event in row.get("events") or []
                    if isinstance(event, Mapping)
                )
            )
            if effect_count:
                state["new_external_effect_count"] = effect_count
            states.append(state)
        return states

    @staticmethod
    def _source_progress_for_identity(
        rows: list[dict[str, Any]],
        source: str,
        identity: str,
    ) -> dict[str, Any] | None:
        """Return the latest per-object projection, not only the source latest."""

        for row in reversed(rows):
            if (
                row.get("event") != "source_progressed"
                or row.get("source") != source
            ):
                continue
            progress = row.get("progress")
            if (
                isinstance(progress, Mapping)
                and str(progress.get("item_identity") or "") == identity
            ):
                return row
        return None

    @staticmethod
    def _source_waiting_item_for_identity(
        rows: list[dict[str, Any]],
        source: str,
        identity: str,
    ) -> tuple[dict[str, Any], Mapping[str, Any]] | None:
        """Find a durable waiting item when a source has several waiters."""

        for row in reversed(rows):
            if row.get("source") != source:
                continue
            candidates: list[Any] = []
            if row.get("event") == "source_completed":
                result = row.get("result")
                if isinstance(result, Mapping):
                    candidates = list(result.get("waiting_items") or [])
                    container = result
                else:
                    container = {}
            elif row.get("event") == "sweep_completed":
                container = {}
                for state in row.get("source_states") or []:
                    if isinstance(state, Mapping) and state.get("name") == source:
                        container = state
                        candidates = list(state.get("waiting_items") or [])
                        break
            else:
                continue
            for item in candidates:
                if (
                    isinstance(item, Mapping)
                    and str(item.get("identity") or "") == identity
                ):
                    return dict(item), container
        return None

    def _source_state_with_pending_waits(
        self,
        *,
        source: str,
        prior_rows: list[dict[str, Any]],
        prior_state: Mapping[str, Any],
        target_identity: str,
        result: Mapping[str, Any],
        following: WriterProgress,
    ) -> dict[str, Any]:
        """Project one narrow result while retaining unrelated pending objects."""

        companions = [
            dict(item)
            for item in (prior_state.get("waiting_items") or [])
            if (
                isinstance(item, Mapping)
                and str(item.get("identity") or "") != target_identity
            )
        ]
        current_items = [
            dict(item)
            for item in (result.get("waiting_items") or [])
            if isinstance(item, Mapping)
        ]
        pending = companions + (
            current_items if following.status == "wait_until" else []
        )
        deduplicated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in pending:
            item_id = str(item.get("identity") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            deduplicated.append(item)
        if not deduplicated:
            return dict(result)

        projected = dict(result)
        projected.update({
            "status": "waiting",
            "waiting_count": len(deduplicated),
            "waiting_items": deduplicated,
        })
        if following.status != "wait_until":
            companion_progress = self._source_progress_for_identity(
                prior_rows,
                source,
                str(deduplicated[0].get("identity") or ""),
            )
            if companion_progress is not None:
                projected["writer_progress"] = dict(
                    companion_progress["progress"]
                )
                projected["resume_policy"] = WriterProgress.from_dict(
                    companion_progress["progress"]
                ).next_action
            else:
                projected_progress = normalize_source_result(
                    source,
                    {
                        "status": "waiting",
                        "waiting_count": 1,
                        "waiting_items": [deduplicated[0]],
                    },
                    failure_revision=self._failure_revision(),
                    provider_contract_version="xiaocao_writer_v1",
                )
                projected["writer_progress"] = projected_progress.to_dict()
                projected["resume_policy"] = projected_progress.next_action
        return projected

    @staticmethod
    def _duplicate_effect_audit(results: list[dict[str, Any]]) -> dict[str, Any]:
        effect_fields = {
            "publication": ("gray_report", {"published"}),
            "reminder": ("alert", {"delivered"}),
            "book": ("book_kol_us", {"filled"}),
            "knowledge": ("knowledge", {"published", "completed"}),
            "ack": ("ack", {"acked", "already_acked"}),
        }
        seen = {kind: set() for kind in effect_fields}
        duplicates = {kind: 0 for kind in sorted(effect_fields)}
        for result in results:
            for event in result.get("events") or []:
                if not isinstance(event, Mapping):
                    continue
                for kind, (field_name, statuses) in effect_fields.items():
                    effect = event.get(field_name)
                    if not isinstance(effect, Mapping):
                        continue
                    if effect.get("status") not in statuses:
                        continue
                    identity = next(
                        (
                            value
                            for name in (
                                "idempotency_key",
                                "idempotencyKey",
                                "receipt",
                                "receiptId",
                                "receipt_id",
                                "trade_id",
                                "id",
                                )
                            if (
                                (value := effect.get(name)) is not None
                                and value != ""
                            )
                        ),
                        None,
                    )
                    if isinstance(identity, Mapping):
                        identity = canonical_sha256(identity)
                    if identity is None:
                        continue
                    identity = str(identity)
                    if identity in seen[kind]:
                        duplicates[kind] += 1
                    else:
                        seen[kind].add(identity)
        return {
            "duplicate_count": sum(duplicates.values()),
            "duplicate_effect_counts": duplicates,
        }

    @staticmethod
    def _sweep_health(results: list[dict[str, Any]]) -> str:
        if any(row.get("user_action_required") for row in results):
            return "blocked"
        if any(row.get("failure") or row.get("repair_required") for row in results):
            return "degraded"
        if any(row.get("status") == "waiting" for row in results):
            return "waiting"
        return "healthy"

    def _notify_user_action_unlocked(
        self,
        *,
        source: str,
        blocker_key: str,
        action: str,
        blocker_sender: Callable[[str, str], Any],
    ) -> bool:
        if not source or not blocker_key or not action:
            raise DailyError("user-action notification binding is incomplete")
        if not callable(blocker_sender):
            raise DailyError("user-action blocker requires an operational sender")
        blocker_state_rows = [
            row
            for row in self._events_unlocked()
            if row.get("event") in {"blocker_notified", "blocker_cleared"}
            and row.get("source") == source
        ]
        active_key = (
            str(blocker_state_rows[-1].get("blocker_key"))
            if blocker_state_rows
            and blocker_state_rows[-1].get("event") == "blocker_notified"
            else ""
        )
        if active_key == blocker_key:
            return False
        blocker_sender("KOL 日常运行需要你处理", action)
        self._append(
            "blocker_notified",
            slot=self._beijing_now().strftime("%Y-%m-%dT%H:00+08:00"),
            source=source,
            blocker_key=blocker_key,
            action=action,
        )
        return True

    def notify_user_action(
        self,
        *,
        source: str,
        blocker_key: str,
        action: str,
        blocker_sender: Callable[[str, str], Any],
    ) -> bool:
        """Send one operational blocker notice until that source clears it."""

        with self._locked():
            return self._notify_user_action_unlocked(
                source=source,
                blocker_key=blocker_key,
                action=action,
                blocker_sender=blocker_sender,
            )

    def run(
        self,
        sources: list[dict[str, Any]],
        *,
        blocker_sender: Callable[[str, str], Any] | None = None,
    ) -> dict[str, Any]:
        now = self._beijing_now()
        if now.hour not in DAYTIME_HOURS:
            return {
                "status": "outside_window",
                "silent": True,
                "beijing_time": now.isoformat(timespec="seconds"),
            }
        slot = now.strftime("%Y-%m-%dT%H:00+08:00")
        sweep_started_monotonic = time.monotonic()
        ordered = sorted(
            sources,
            key=lambda row: (int(row.get("priority", 100)), str(row.get("name", ""))),
        )
        with self._locked():
            prior_rows = self._events_unlocked()
            recorded_terminal_ids = {
                str(event.get("event_id"))
                for row in prior_rows
                if row.get("event") == "source_completed"
                for event in (row.get("result", {}).get("events") or [])
                if isinstance(event, dict) and event.get("event_id")
            }
            completed_by_source = {
                str(row.get("source")): row.get("result")
                for row in prior_rows
                if row.get("event") == "source_completed"
                and row.get("slot") == slot
                and (row.get("result") or {}).get("status")
                in {"no_update", "completed"}
            }
            self._append(
                "sweep_resumed" if completed_by_source else "sweep_started",
                slot=slot,
            )
            self._append(
                "runner_started",
                slot=slot,
                source_count=len(ordered),
            )
            results: list[dict[str, Any]] = []
            for source in ordered:
                name = str(source.get("name") or "").strip()
                runner = source.get("run")
                if not name or not callable(runner):
                    raise DailyError("daily source needs a name and callable runner")
                if name in completed_by_source:
                    prior_result = completed_by_source[name]
                    if not isinstance(prior_result, dict):
                        raise DailyError("daily prior source result is invalid")
                    results.append(
                        {"name": name, **prior_result, "resumed": True}
                    )
                    continue
                pending_resume = self.convergence.pending_resume(name)
                active_progress = self.convergence.active_progress(name)
                retained_outcome: dict[str, Any] | None = None
                retained_progress: WriterProgress | None = None
                narrow_runner = source.get("narrow_resume")
                resume_progress: WriterProgress | None = None
                resume_surface = ""
                reconciliation_progress: WriterProgress | None = None
                structured_progress: WriterProgress | None = None
                if pending_resume is not None:
                    resume_progress, _closure = pending_resume
                    resume_surface = str(
                        resume_progress.details["narrow_resume_surface"]
                    )
                    if not callable(narrow_runner):
                        raise DailyError(
                            f"daily source {name} lacks its narrow repair resume"
                        )
                elif active_progress is not None:
                    failure = active_progress.failure
                    retained_outcome = {
                        "status": "waiting",
                        "waiting_count": 1,
                        "waiting_items": [{
                            "identity": active_progress.item_identity,
                            "stage": active_progress.stage,
                            "failure": {
                                "category": failure["category"],
                                "code": failure["code"],
                                "stage": failure["stage"],
                                "retryable": (
                                    active_progress.retryability == "retryable"
                                ),
                            },
                        }],
                        "retryable": False,
                        "failure": {
                            "category": failure["category"],
                            "code": failure["code"],
                            "stage": failure["stage"],
                            "retryable": (
                                active_progress.retryability == "retryable"
                            ),
                        },
                        "repair_key": active_progress.failure_fingerprint,
                        "repair_required": True,
                        "user_action_required": False,
                        "writer_progress": active_progress.to_dict(),
                    }
                    self._append(
                        "source_repair_ownership_retained",
                        slot=slot,
                        source=name,
                        failure_fingerprint=(
                            active_progress.failure_fingerprint
                        ),
                    )
                else:
                    latest_progress_row = next(
                        (
                            row
                            for row in reversed(prior_rows)
                            if row.get("event") == "source_progressed"
                            and row.get("source") == name
                        ),
                        None,
                    )
                    if latest_progress_row is not None:
                        prior_progress = WriterProgress.from_dict(
                            latest_progress_row["progress"]
                        )
                        if prior_progress.status == "wait_until":
                            deadline = datetime.fromisoformat(
                                str(prior_progress.details["deadline"]).replace(
                                    "Z", "+00:00"
                                )
                            )
                            if now < deadline:
                                prior_outcome = next(
                                    (
                                        row.get("result")
                                        for row in reversed(prior_rows)
                                        if row.get("event") == "source_completed"
                                        and row.get("source") == name
                                    ),
                                    None,
                                )
                                if not isinstance(prior_outcome, dict):
                                    raise DailyError(
                                        "provider wait lost its source result"
                                    )
                                retained_outcome = dict(prior_outcome)
                                retained_progress = prior_progress
                                self._append(
                                    "source_wait_deadline_retained",
                                    slot=slot,
                                    source=name,
                                    deadline=prior_progress.details["deadline"],
                                )
                        elif prior_progress.status == "reconcile_required":
                            reconciliation_progress = prior_progress
                        elif prior_progress.status == "structured_input":
                            structured_progress = prior_progress
                self._append("source_started", slot=slot, source=name)
                progress_override: WriterProgress | None = retained_progress
                user_action_context: dict[str, str] | None = None
                reconciliation_receipt: dict[str, Any] | None = None
                structured_input_receipt: dict[str, Any] | None = None
                try:
                    outcome = self._invoke_source_step(
                        source,
                        runner=runner,
                        retained_outcome=retained_outcome,
                        narrow_runner=narrow_runner,
                        resume_progress=resume_progress,
                        resume_surface=resume_surface,
                        structured_progress=structured_progress,
                        reconciliation_progress=reconciliation_progress,
                    )
                    if reconciliation_progress is not None:
                        outcome, reconciliation_receipt = (
                            self._reconciliation_result(
                                reconciliation_progress,
                                outcome,
                            )
                        )
                    if structured_progress is not None:
                        outcome, structured_input_receipt = (
                            self._structured_input_result(
                                structured_progress,
                                outcome,
                            )
                        )
                    while (
                        isinstance(outcome, dict)
                        and isinstance(outcome.get("writer_progress"), dict)
                    ):
                        in_process = WriterProgress.from_dict(
                            outcome["writer_progress"]
                        )
                        if in_process.status != "continue":
                            break
                        continuation = source.get("continue")
                        if not callable(continuation):
                            raise DailyError(
                                f"daily source {name} lacks its continuation"
                            )
                        self._append(
                            "source_progressed",
                            slot=slot,
                            source=name,
                            progress=in_process.to_dict(),
                        )
                        following_outcome = continuation(
                            str(in_process.details["next_stage"])
                        )
                        if (
                            not isinstance(following_outcome, dict)
                            or not isinstance(
                                following_outcome.get("writer_progress"),
                                dict,
                            )
                        ):
                            raise DailyError(
                                "daily continuation lacks writer progress"
                            )
                        following_progress = WriterProgress.from_dict(
                            following_outcome["writer_progress"]
                        )
                        in_process.validate_transition_to(following_progress)
                        outcome = following_outcome
                except ControlPlaneHandlerError:
                    outcome, progress_override = self._agent_repair(
                        name,
                        category="control_plane_handler_error",
                        code="progress_handler_contract_invalid",
                        stage="progress_handler",
                        item_identity=(
                            reconciliation_progress.item_identity
                            if reconciliation_progress is not None
                            else structured_progress.item_identity
                            if structured_progress is not None
                            else None
                        ),
                    )
                except UserActionBlocker as exc:
                    if blocker_sender is None:
                        raise DailyError(
                            "user-action blocker requires an operational sender"
                        ) from exc
                    notified = not self._notify_user_action_unlocked(
                        source=name,
                        blocker_key=exc.blocker_key,
                        action=exc.action,
                        blocker_sender=blocker_sender,
                    )
                    waiting_items = exc.waiting_items or [{
                        "identity": f"{name}:source",
                        "stage": "external_authorization",
                        "user_action_required": True,
                    }]
                    outcome = {
                        "status": "waiting",
                        "blocker_key": exc.blocker_key,
                        "user_action_required": True,
                        "notification_sent": not notified,
                        "waiting_count": len(waiting_items),
                        "waiting_items": waiting_items,
                    }
                    if exc.claim_receipt_summary is not None:
                        outcome["claim_receipt_summary"] = (
                            exc.claim_receipt_summary
                        )
                    user_action_context = {
                        "action": exc.action,
                        "blocker_identity": exc.blocker_key,
                        "dedup_key": exc.blocker_key,
                    }
                except TransientSourceError as exc:
                    failure = exc.diagnostic()
                    self._append(
                        "source_retryable_failure",
                        slot=slot,
                        source=name,
                        failure=failure,
                    )
                    consecutive_prior = 0
                    for row in reversed(prior_rows):
                        if (
                            row.get("event") != "source_completed"
                            or row.get("source") != name
                        ):
                            continue
                        prior_failure = (row.get("result") or {}).get(
                            "failure"
                        )
                        if not isinstance(prior_failure, dict):
                            break
                        if all(
                            prior_failure.get(field) == failure.get(field)
                            for field in ("category", "code", "stage")
                        ):
                            consecutive_prior += 1
                            continue
                        break
                    deterministic_agent_fault = (
                        exc.category in AGENT_OWNED_FAILURE_CATEGORIES
                    )
                    if consecutive_prior >= 1 or deterministic_agent_fault:
                        consecutive_count = consecutive_prior + 1
                        repair_key = (
                            f"{name}-{failure['stage']}-{failure['code']}"
                            "-recovery-exhausted"
                        )
                        self._append(
                            "source_recovery_exhausted",
                            slot=slot,
                            source=name,
                            failure=failure,
                            repair_key=repair_key,
                            consecutive_count=consecutive_count,
                            deterministic_recovery_attempted=True,
                            external_business_effects_replayed=False,
                        )
                        outcome = {
                            "status": "waiting",
                            "retryable": False,
                            "failure": failure,
                            "repair_key": repair_key,
                            "repair_required": True,
                            "user_action_required": False,
                            "consecutive_failure_count": consecutive_count,
                        }
                    else:
                        outcome = {
                            "status": "waiting",
                            "retryable": True,
                            "failure": failure,
                        }
                    provider_wait = self._xiaocao_provider_wait_after_failure(
                        name,
                        failure,
                        prior_rows,
                    )
                    if provider_wait is not None:
                        outcome = provider_wait
                except Exception:
                    outcome, progress_override = self._agent_repair(
                        name,
                        category="code_error",
                        code="unhandled_source_exception",
                        stage="source_run",
                    )
                except BaseException as exc:
                    self._append(
                        "source_interrupted",
                        slot=slot,
                        source=name,
                        error_type=type(exc).__name__,
                    )
                    raise
                try:
                    if outcome is None:
                        outcome = {"status": "no_update"}
                    if not isinstance(outcome, dict):
                        raise DailyError(
                            f"daily source {name} returned an invalid result"
                        )
                    status = str(outcome.get("status") or "")
                    if status not in {"no_update", "completed", "waiting"}:
                        raise DailyError(
                            f"daily source {name} returned an unsupported status"
                        )
                    if status == "completed":
                        events = outcome.get("events")
                        if not isinstance(events, list):
                            raise DailyError(
                                f"daily source {name} completed without events"
                            )
                        fresh_events = [
                            event
                            for event in events
                            if isinstance(event, dict)
                            and str(event.get("event_id") or "")
                            not in recorded_terminal_ids
                        ]
                        replayed_count = len(events) - len(fresh_events)
                        if fresh_events:
                            outcome = {**outcome, "events": fresh_events}
                            recorded_terminal_ids.update(
                                str(event["event_id"])
                                for event in fresh_events
                            )
                            if replayed_count:
                                outcome["replayed_terminal_count"] = replayed_count
                        else:
                            outcome = {
                                "status": "no_update",
                                "replayed_terminal_count": replayed_count,
                            }
                        self._append(
                            "terminal_replay_audit",
                            slot=slot,
                            source=name,
                            replayed_terminal_count=replayed_count,
                            audited=True,
                        )
                    _validate_source_outcome(outcome)
                except Exception:
                    outcome, progress_override = self._agent_repair(
                        name,
                        category="schema_error",
                        code="source_result_schema_invalid",
                        stage="source_result_validation",
                    )
                stalled_items = [
                    row
                    for row in (outcome.get("waiting_items") or [])
                    if isinstance(row, dict)
                    and row.get("stage") == "source_acquisition"
                    and str(row.get("identity") or "")
                    and str(row.get("version_key") or "")
                ]
                prior_source_results = [
                    row.get("result") or {}
                    for row in reversed(prior_rows)
                    if row.get("event") == "source_completed"
                    and row.get("source") == name
                ]
                stalled_keys = {
                    (str(row["identity"]), str(row["version_key"]))
                    for row in stalled_items
                }
                prior_stalled_keys = {
                    (
                        str(row.get("identity") or ""),
                        str(row.get("version_key") or ""),
                    )
                    for result in prior_source_results[:1]
                    for row in (result.get("waiting_items") or [])
                    if isinstance(row, dict)
                    and row.get("stage") == "source_acquisition"
                }
                repeated_stalls = sorted(stalled_keys & prior_stalled_keys)
                if repeated_stalls and not outcome.get("user_action_required"):
                    repair_key = f"{name}-source-acquisition-stalled"
                    self._append(
                        "source_acquisition_stalled",
                        slot=slot,
                        source=name,
                        repair_key=repair_key,
                        items=[
                            {"identity": identity, "version_key": version}
                            for identity, version in repeated_stalls
                        ],
                        deterministic_recovery_attempted=True,
                        external_business_effects_replayed=False,
                    )
                    outcome = {
                        **outcome,
                        "retryable": False,
                        "repair_key": repair_key,
                        "repair_required": True,
                        "user_action_required": False,
                    }
                if (
                    outcome.get("repair_required") is True
                    and not isinstance(outcome.get("failure"), dict)
                ):
                    repair_stage = str(
                        ((outcome.get("waiting_items") or [{}])[0]).get(
                            "stage"
                        )
                        or "source_run"
                    )
                    outcome = {
                        **outcome,
                        "failure": {
                            "category": "internal_state_error",
                            "code": (
                                "source_acquisition_stalled"
                                if repair_stage == "source_acquisition"
                                else "deterministic_recovery_exhausted"
                            ),
                            "stage": repair_stage,
                            "retryable": False,
                        },
                    }
                try:
                    progress = (
                        progress_override
                        if progress_override is not None
                        else normalize_source_result(
                            name,
                            outcome,
                            failure_revision=self._failure_revision(),
                            provider_contract_version="xiaocao_writer_v1",
                            user_action=user_action_context,
                        )
                    )
                except Exception:
                    outcome, progress = self._agent_repair(
                        name,
                        category="schema_error",
                        code="progress_projection_failed",
                        stage="progress_projection",
                    )
                if resume_progress is not None:
                    self.convergence.record_resume(
                        resume_progress.failure_fingerprint,
                        following=progress,
                        slot=slot,
                    )
                if structured_progress is not None:
                    structured_progress.validate_transition_to(
                        progress,
                        evidence=structured_input_receipt,
                    )
                if (
                    reconciliation_progress is not None
                    and progress.status != "reconcile_required"
                ):
                    reconciliation_progress.validate_transition_to(
                        progress,
                        evidence=reconciliation_receipt,
                    )
                if reconciliation_receipt is not None:
                    self._append(
                        "side_effect_reconciled",
                        slot=slot,
                        source=name,
                        claim_identity=(
                            reconciliation_receipt["claim_identity"]
                        ),
                        readback_operation=(
                            reconciliation_receipt["readback_operation"]
                        ),
                        external_business_effects_replayed=False,
                    )
                outcome = {
                    **{
                        key: value
                        for key, value in outcome.items()
                        if key != "retryable"
                    },
                    "resume_policy": progress.next_action,
                    "writer_progress": progress.to_dict(),
                }
                if progress.status == "wait_until":
                    outcome["resume_command"] = (
                        "PYTHONPATH=src .venv/bin/python scripts/kol_daily.py "
                        "resume-source-wait "
                        f"--source-adapter {name} "
                        f"--source-identity {progress.item_identity}"
                    )
                if progress.status == "repair_required":
                    failure = progress.failure
                    outcome = {
                        **outcome,
                        "status": "waiting",
                        "failure": {
                            "category": failure["category"],
                            "code": failure["code"],
                            "stage": failure["stage"],
                            "retryable": (
                                progress.retryability == "retryable"
                            ),
                        },
                        "repair_key": progress.failure_fingerprint,
                        "repair_required": True,
                        "user_action_required": False,
                        "writer_progress": progress.to_dict(),
                    }
                    self.convergence.record(progress, slot=slot)
                self._append(
                    "source_progressed",
                    slot=slot,
                    source=name,
                    progress=progress.to_dict(),
                )
                prior_blockers = [
                    row
                    for row in self._events_unlocked()
                    if row.get("event") == "blocker_notified"
                    and row.get("source") == name
                ]
                prior_clears = [
                    row
                    for row in self._events_unlocked()
                    if row.get("event") == "blocker_cleared"
                    and row.get("source") == name
                ]
                if (
                    not outcome.get("user_action_required")
                    and len(prior_blockers) > len(prior_clears)
                ):
                    self._append(
                        "blocker_cleared",
                        slot=slot,
                        source=name,
                        blocker_key=prior_blockers[-1].get("blocker_key"),
                    )
                summary = {"name": name, **outcome}
                results.append(summary)
                self._append(
                    "source_completed",
                    slot=slot,
                    source=name,
                    result=outcome,
                    coordinator_source_video_bytes=0,
                )
            source_states = self._source_states(results)
            health = self._sweep_health(results)
            duplicate_audit = self._duplicate_effect_audit(results)
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(results),
                source_states=source_states,
                elapsed_ms=max(
                    0,
                    int((time.monotonic() - sweep_started_monotonic) * 1000),
                ),
                coordinator_source_video_bytes=0,
            )
            self._append(
                "duplicate_effect_audit",
                slot=slot,
                **duplicate_audit,
            )
        silent = (
            all(row["status"] in {"no_update", "waiting"} for row in results)
            and not any(row.get("failure") for row in results)
            and not any(row.get("repair_required") for row in results)
        )
        return {
            "status": "completed",
            "slot": slot,
            "health": health,
            "silent": silent,
            "source_results": results,
        }

    def resume_wait(
        self,
        source: dict[str, Any],
        *,
        item_identity: str,
        _completed_user_action: bool = False,
    ) -> dict[str, Any]:
        """Resume one exact paused source without starting a new sweep."""

        now = self._beijing_now()
        name = str(source.get("name") or "").strip()
        narrow_runner = source.get("narrow_resume")
        identity = str(item_identity or "").strip()
        if not name or not callable(narrow_runner) or not identity:
            kind = "user action" if _completed_user_action else "provider wait"
            raise DailyError(
                f"{kind} resume needs one source and exact item identity"
            )
        started = time.monotonic()
        with self._locked():
            prior_rows = self._events_unlocked()
            progress_row = self._source_progress_for_identity(
                prior_rows,
                name,
                identity,
            )
            projected_from_waiting_item = False
            if progress_row is None and not _completed_user_action:
                waiting_binding = self._source_waiting_item_for_identity(
                    prior_rows,
                    name,
                    identity,
                )
                if waiting_binding is not None:
                    waiting_item, waiting_container = waiting_binding
                    waiting_outcome: dict[str, Any] = {
                        "status": "waiting",
                        "waiting_count": 1,
                        "waiting_items": [waiting_item],
                    }
                    claim_summary = waiting_container.get(
                        "claim_receipt_summary"
                    )
                    if isinstance(claim_summary, Mapping):
                        waiting_outcome["claim_receipt_summary"] = dict(
                            claim_summary
                        )
                    projected = normalize_source_result(
                        name,
                        waiting_outcome,
                        failure_revision=self._failure_revision(),
                        provider_contract_version="xiaocao_writer_v1",
                    )
                    progress_row = {
                        "slot": "",
                        "source": name,
                        "progress": projected.to_dict(),
                    }
                    projected_from_waiting_item = True
            if progress_row is None:
                progress_row = next(
                    (
                        row
                        for row in reversed(prior_rows)
                        if row.get("event") == "source_progressed"
                        and row.get("source") == name
                    ),
                    None,
                )
            if progress_row is None:
                raise DailyError("source resume has no persisted progress")
            prior = WriterProgress.from_dict(progress_row["progress"])
            expected_status = (
                "user_action_required" if _completed_user_action else "wait_until"
            )
            if prior.status != expected_status:
                if _completed_user_action:
                    raise DailyError("source is not waiting for user action")
                raise DailyError("source is not waiting for a provider deadline")
            if prior.item_identity != identity:
                raise DailyError("source resume item identity changed")
            if _completed_user_action:
                surface = (
                    identity
                    if identity.startswith(f"{name}:")
                    else f"{name}:{identity}"
                )
            else:
                deadline = datetime.fromisoformat(
                    str(prior.details["deadline"]).replace("Z", "+00:00")
                )
                if now < deadline:
                    raise DailyError("provider wait deadline has not elapsed")
                surface = str(
                    prior.details.get("narrow_resume_surface")
                    or f"{name}:{identity}"
                )
                if surface != f"{name}:{identity}":
                    raise DailyError("provider wait narrow resume surface changed")
            prior_sweep = self._last_sweep_state(prior_rows)
            if prior_sweep is None:
                raise DailyError("provider wait resume lost its originating sweep")
            prior_states = prior_sweep.get("source_states")
            if not isinstance(prior_states, list) or not any(
                isinstance(row, Mapping) and row.get("name") == name
                for row in prior_states
            ):
                raise DailyError("provider wait resume lost its source state")
            slot = str(progress_row.get("slot") or prior_sweep.get("slot") or "")
            resume_event = (
                "source_user_action_resume_started"
                if _completed_user_action
                else "source_wait_resume_started"
            )
            resume_fields: dict[str, Any] = {
                "slot": slot,
                "source": name,
                "item_identity": identity,
                "narrow_resume_surface": surface,
            }
            if _completed_user_action:
                resume_fields["blocker_identity"] = prior.details[
                    "blocker_identity"
                ]
            else:
                resume_fields["deadline"] = prior.details["deadline"]
            if projected_from_waiting_item:
                self._append(
                    "source_wait_resume_projection_bound",
                    slot=slot,
                    source=name,
                    item_identity=identity,
                    projected_status=prior.status,
                    projection_source="waiting_items",
                )
            self._append(resume_event, **resume_fields)
            try:
                outcome = narrow_runner(surface)
            except BaseException as exc:
                self._append(
                    (
                        "source_user_action_resume_interrupted"
                        if _completed_user_action
                        else "source_wait_resume_interrupted"
                    ),
                    slot=slot,
                    source=name,
                    item_identity=identity,
                    error_type=type(exc).__name__,
                )
                raise
            if outcome is None:
                outcome = {"status": "no_update"}
            if not isinstance(outcome, dict):
                raise DailyError("source narrow resume returned invalid output")
            _validate_source_outcome(outcome)
            progress_value = outcome.get("writer_progress")
            following = (
                WriterProgress.from_dict(progress_value)
                if isinstance(progress_value, Mapping)
                else normalize_source_result(
                    name,
                    outcome,
                    failure_revision=self._failure_revision(),
                    provider_contract_version="xiaocao_writer_v1",
                )
            )
            prior.validate_transition_to(following, now=now)
            result = {
                **{
                    key: value
                    for key, value in outcome.items()
                    if key != "retryable"
                },
                "resume_policy": following.next_action,
                "writer_progress": following.to_dict(),
            }
            if following.status == "wait_until":
                result["resume_command"] = (
                    "PYTHONPATH=src .venv/bin/python scripts/kol_daily.py "
                    "resume-source-wait "
                    f"--source-adapter {name} "
                    f"--source-identity {following.item_identity}"
                )
            if following.status == "repair_required":
                self.convergence.record(following, slot=slot)
            if (
                _completed_user_action
                and following.status != "user_action_required"
            ):
                self._append(
                    "blocker_cleared",
                    slot=slot,
                    source=name,
                    blocker_key=prior.details["dedup_key"],
                )
            self._append(
                "source_progressed",
                slot=slot,
                source=name,
                progress=following.to_dict(),
            )
            self._append(
                "source_completed",
                slot=slot,
                source=name,
                result=result,
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            source_states = [
                self._source_states([{
                    "name": name,
                    **self._source_state_with_pending_waits(
                        source=name,
                        prior_rows=prior_rows,
                        prior_state=row,
                        target_identity=identity,
                        result=result,
                        following=following,
                    ),
                }])[0]
                if row.get("name") == name
                else dict(row)
                for row in prior_states
                if isinstance(row, Mapping)
            ]
            health = self._sweep_health(source_states)
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(source_states),
                source_states=source_states,
                elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            duplicate_audit = self._duplicate_effect_audit([
                {"name": name, **result}
            ])
            self._append(
                "duplicate_effect_audit",
                slot=slot,
                continuation_only=True,
                **duplicate_audit,
            )
        return {
            "status": "completed",
            "slot": slot,
            "health": health,
            "continuation_only": True,
            "source_result": {"name": name, **result},
        }

    def resume_user_action(
        self,
        source: dict[str, Any],
        *,
        item_identity: str,
    ) -> dict[str, Any]:
        """Resume one exact source after its declared user action completed."""

        return self.resume_wait(
            source,
            item_identity=item_identity,
            _completed_user_action=True,
        )

    def record_repair_resume(
        self,
        source: str,
        *,
        prior: WriterProgress,
        outcome: Mapping[str, Any],
        following: WriterProgress,
        slot: str,
    ) -> dict[str, Any]:
        """Persist one validated repair continuation into the daily ledger."""

        name = str(source or "").strip()
        if (
            not name
            or prior.status != "repair_required"
            or prior.failure["adapter"] != name
        ):
            raise DailyError("repair resume needs its exact source progress")
        _validate_source_outcome(dict(outcome))
        started = time.monotonic()
        with self._locked():
            prior_rows = self._events_unlocked()
            prior_sweep = self._last_sweep_state(prior_rows)
            if prior_sweep is None:
                raise DailyError("repair resume lost its originating sweep")
            prior_states = prior_sweep.get("source_states")
            if not isinstance(prior_states, list) or not any(
                isinstance(row, Mapping) and row.get("name") == name
                for row in prior_states
            ):
                raise DailyError("repair resume lost its source state")
            result = {
                **{
                    key: value
                    for key, value in outcome.items()
                    if key != "retryable"
                },
                "resume_policy": following.next_action,
                "writer_progress": following.to_dict(),
            }
            if following.status == "wait_until":
                result["resume_command"] = (
                    "PYTHONPATH=src .venv/bin/python scripts/kol_daily.py "
                    "resume-source-wait "
                    f"--source-adapter {name} "
                    f"--source-identity {following.item_identity}"
                )
            self._append(
                "source_repair_resume_started",
                slot=slot,
                source=name,
                failure_fingerprint=prior.failure_fingerprint,
                item_identity=following.item_identity,
                narrow_resume_surface=prior.details["narrow_resume_surface"],
            )
            resume = self.convergence.record_resume(
                prior.failure_fingerprint,
                following=following,
                slot=slot,
            )
            self._append(
                "source_progressed",
                slot=slot,
                source=name,
                progress=following.to_dict(),
            )
            self._append(
                "source_completed",
                slot=slot,
                source=name,
                result=result,
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            current_state = self._source_states([{
                "name": name,
                **result,
            }])[0]
            source_states = [
                current_state
                if isinstance(row, Mapping) and row.get("name") == name
                else dict(row)
                for row in prior_states
                if isinstance(row, Mapping)
            ]
            health = self._sweep_health(source_states)
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(source_states),
                source_states=source_states,
                elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            duplicate_audit = self._duplicate_effect_audit([{
                "name": name,
                **result,
            }])
            self._append(
                "duplicate_effect_audit",
                slot=slot,
                continuation_only=True,
                **duplicate_audit,
            )
        return resume

    def resume_structured_input(
        self,
        source: dict[str, Any],
        *,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        """Consume one exact persisted semantic request without a new sweep."""

        name = str(source.get("name") or "").strip()
        handler = source.get("structured_input")
        if (
            not name
            or not callable(handler)
            or progress.status != "structured_input"
        ):
            raise DailyError(
                "structured input resume needs one source and bound request"
            )
        started = time.monotonic()
        with self._locked():
            prior_rows = self._events_unlocked()
            prior_sweep = self._last_sweep_state(prior_rows)
            if prior_sweep is None:
                raise DailyError(
                    "structured input resume lost its originating sweep"
                )
            prior_states = prior_sweep.get("source_states")
            if not isinstance(prior_states, list) or not any(
                isinstance(row, Mapping) and row.get("name") == name
                for row in prior_states
            ):
                raise DailyError(
                    "structured input resume lost its source state"
                )
            slot = str(prior_sweep.get("slot") or "")
            self._append(
                "source_structured_input_resume_started",
                slot=slot,
                source=name,
                item_identity=progress.item_identity,
                request_id=progress.details["request_id"],
            )
            try:
                wrapped = handler(progress)
                outcome, receipt = self._structured_input_result(
                    progress,
                    wrapped,
                )
            except BaseException as exc:
                self._append(
                    "source_structured_input_resume_interrupted",
                    slot=slot,
                    source=name,
                    item_identity=progress.item_identity,
                    error_type=type(exc).__name__,
                )
                raise
            if not isinstance(outcome, dict):
                raise DailyError(
                    "structured input handler returned invalid output"
                )
            if outcome.get("status") == "completed":
                events = outcome.get("events")
                if not isinstance(events, list):
                    raise DailyError(
                        "structured input completion lacks terminal events"
                    )
                recorded_terminal_ids = {
                    str(event.get("event_id"))
                    for row in prior_rows
                    if row.get("event") == "source_completed"
                    for event in (row.get("result", {}).get("events") or [])
                    if isinstance(event, Mapping) and event.get("event_id")
                }
                fresh_events = [
                    event
                    for event in events
                    if isinstance(event, dict)
                    and str(event.get("event_id") or "")
                    not in recorded_terminal_ids
                ]
                replayed_count = len(events) - len(fresh_events)
                outcome = (
                    {**outcome, "events": fresh_events}
                    if fresh_events
                    else {
                        "status": "no_update",
                        "replayed_terminal_count": replayed_count,
                    }
                )
                if fresh_events and replayed_count:
                    outcome["replayed_terminal_count"] = replayed_count
                self._append(
                    "terminal_replay_audit",
                    slot=slot,
                    source=name,
                    replayed_terminal_count=replayed_count,
                    audited=True,
                    continuation_only=True,
                )
            _validate_source_outcome(outcome)
            progress_value = outcome.get("writer_progress")
            following = (
                WriterProgress.from_dict(progress_value)
                if isinstance(progress_value, Mapping)
                else normalize_source_result(
                    name,
                    outcome,
                    failure_revision=self._failure_revision(),
                    provider_contract_version="xiaocao_writer_v1",
                )
            )
            progress.validate_transition_to(following, evidence=receipt)
            result = {
                **{
                    key: value
                    for key, value in outcome.items()
                    if key != "retryable"
                },
                "resume_policy": following.next_action,
                "structured_input_receipt": receipt,
                "writer_progress": following.to_dict(),
            }
            if following.status == "repair_required":
                self.convergence.record(following, slot=slot)
            self._append(
                "source_progressed",
                slot=slot,
                source=name,
                progress=following.to_dict(),
            )
            self._append(
                "source_completed",
                slot=slot,
                source=name,
                result=result,
                coordinator_source_video_bytes=0,
            )
            target_state = self._source_states([{"name": name, **result}])[0]
            source_states = [
                target_state if row.get("name") == name else dict(row)
                for row in prior_states
                if isinstance(row, Mapping)
            ]
            health = self._sweep_health(source_states)
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(source_states),
                source_states=source_states,
                elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            duplicate_audit = self._duplicate_effect_audit([
                {"name": name, **result}
            ])
            self._append(
                "duplicate_effect_audit",
                slot=slot,
                continuation_only=True,
                **duplicate_audit,
            )
        return {
            "status": "completed",
            "slot": slot,
            "health": health,
            "continuation_only": True,
            "source_result": {"name": name, **result},
        }

    def resume_reconciliation(
        self,
        source: dict[str, Any],
        *,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        """Complete one source from an exact authoritative terminal readback."""

        name = str(source.get("name") or "").strip()
        handler = source.get("reconcile")
        if (
            not name
            or not callable(handler)
            or progress.status != "reconcile_required"
        ):
            raise DailyError(
                "source reconciliation needs one source and exact claim"
            )
        started = time.monotonic()
        with self._locked():
            prior_rows = self._events_unlocked()
            prior_sweep = self._last_sweep_state(prior_rows)
            if prior_sweep is None:
                raise DailyError("source reconciliation lost its sweep")
            prior_states = prior_sweep.get("source_states")
            if not isinstance(prior_states, list) or not any(
                isinstance(row, Mapping) and row.get("name") == name
                for row in prior_states
            ):
                raise DailyError("source reconciliation lost its source state")
            slot = str(prior_sweep.get("slot") or "")
            self._append(
                "source_reconciliation_resume_started",
                slot=slot,
                source=name,
                item_identity=progress.item_identity,
                claim_identity=progress.details["claim_identity"],
                readback_operation=progress.details["readback_operation"],
            )
            wrapped = handler(progress)
            outcome, receipt = self._reconciliation_result(progress, wrapped)
            terminal = outcome.pop("terminal_event", None)
            if terminal is not None:
                validate_source_event(terminal)
                outcome = {**outcome, "status": "completed", "events": [terminal]}
            _validate_source_outcome(outcome)
            following = normalize_source_result(
                name,
                outcome,
                failure_revision=self._failure_revision(),
                provider_contract_version="xiaocao_writer_v1",
            )
            if terminal is not None and following.status == "terminal":
                following = WriterProgress.terminal(
                    item_identity=progress.item_identity,
                    stage=following.stage,
                    content_terminal=following.details["content_terminal"],
                    gray_report_terminal=following.details["gray_report_terminal"],
                    reminder_terminal=following.details["reminder_terminal"],
                    book_terminal=following.details["book_terminal"],
                    knowledge_terminal=following.details["knowledge_terminal"],
                    ack_status=following.details["ack_status"],
                    new_external_effect_count=0,
                    claim_receipt_summary=following.details[
                        "claim_receipt_summary"
                    ],
                )
            progress.validate_transition_to(following, evidence=receipt)
            result = {
                **outcome,
                "resume_policy": following.next_action,
                "reconciliation_receipt": receipt,
                "writer_progress": following.to_dict(),
            }
            if following.status == "repair_required":
                self.convergence.record(following, slot=slot)
            self._append(
                "side_effect_reconciled",
                slot=slot,
                source=name,
                claim_identity=receipt["claim_identity"],
                readback_operation=receipt["readback_operation"],
                external_business_effects_replayed=False,
            )
            self._append(
                "source_progressed",
                slot=slot,
                source=name,
                progress=following.to_dict(),
            )
            self._append(
                "source_completed",
                slot=slot,
                source=name,
                result=result,
                coordinator_source_video_bytes=0,
            )
            target_state = self._source_states([{"name": name, **result}])[0]
            source_states = [
                target_state if row.get("name") == name else dict(row)
                for row in prior_states
                if isinstance(row, Mapping)
            ]
            health = self._sweep_health(source_states)
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(source_states),
                source_states=source_states,
                elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
                coordinator_source_video_bytes=0,
                continuation_only=True,
            )
            duplicate_audit = self._duplicate_effect_audit([
                {"name": name, **result}
            ])
            self._append(
                "duplicate_effect_audit",
                slot=slot,
                continuation_only=True,
                **duplicate_audit,
            )
        return {
            "status": "completed",
            "slot": slot,
            "health": health,
            "continuation_only": True,
            "source_result": {"name": name, **result},
        }

    def status(self) -> dict[str, Any]:
        rows = self.events()
        last = self._last_sweep_state(rows)
        health = str((last or {}).get("health") or "unknown")
        return {
            "status": (
                "ready"
                if health in {"healthy", "waiting"}
                else health
                if last
                else "ready"
            ),
            "last_sweep": (
                {
                    "slot": last["slot"],
                    "status": last["status"],
                    "health": health,
                    "source_states": last.get("source_states", []),
                }
                if last
                else None
            ),
            "event_count": len(rows),
        }

    def convergence_report(
        self,
        *,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> dict[str, Any]:
        now = self._beijing_now()
        start = period_start or now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ).isoformat(timespec="seconds")
        end = period_end or now.isoformat(timespec="seconds")
        return self.convergence.report(
            self.events(),
            period_start=start,
            period_end=end,
        )

    def stability_acceptance_report(
        self,
        *,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        end = as_of or self._beijing_now().isoformat(timespec="seconds")
        return self.convergence.acceptance_report(
            self.events(),
            as_of=end,
        )

    def audit(self) -> dict[str, Any]:
        rows = self.events()
        convergence_rows = self.convergence.events()
        last = self._last_sweep_state(rows)
        operational_status = str((last or {}).get("health") or "unknown")
        latest_failures = [
            {
                "source": str(state.get("name") or ""),
                **state["failure"],
            }
            for state in ((last or {}).get("source_states") or [])
            if isinstance(state, dict) and isinstance(state.get("failure"), dict)
        ]
        latest_repairs = [
            {
                "source": str(state.get("name") or ""),
                "repair_key": str(state.get("repair_key") or ""),
                "owner": str(progress.get("ownership") or "agent"),
                "failure_fingerprint": str(
                    progress.get("failure_fingerprint")
                    or state.get("repair_key")
                    or ""
                ),
                "next_action": str(
                    progress.get("next_action")
                    or "validate_repair_then_narrow_resume"
                ),
            }
            for state in ((last or {}).get("source_states") or [])
            if isinstance(state, dict) and state.get("repair_required") is True
            for progress in [
                state.get("writer_progress")
                if isinstance(state.get("writer_progress"), dict)
                else {}
            ]
        ]
        source_bytes = sum(
            int(row.get("coordinator_source_video_bytes") or 0)
            for row in rows
        )
        source_events = [
            event
            for row in rows
            if row.get("event") == "source_completed"
            for event in (row.get("result", {}).get("events") or [])
            if isinstance(event, dict) and event.get("kind") == "source_event"
        ]
        viewpoint_events = [
            event
            for row in rows
            if row.get("event") == "source_completed"
            for event in (row.get("result", {}).get("events") or [])
            if isinstance(event, dict)
            and event.get("kind") == "viewpoint_evaluation"
        ]
        dispositions = {"low_density": 0, "promoted": 0}
        tiers = {"alert_eligible": 0, "report_only": 0}
        gray_count = 0
        reminder_count = 0
        book_trade_count = 0
        for event in source_events:
            content = event["content_value"]
            dispositions[content["status"]] += 1
            if content["status"] == "promoted":
                tiers[content["tier"]] += 1
            if event["gray_report"]["status"] == "published":
                gray_count += 1
            if event["alert"]["status"] == "delivered":
                reminder_count += 1
            if event["book_kol_us"]["status"] == "filled":
                book_trade_count += 1
        safety_status = "accepted" if source_bytes == 0 else "failed"
        return {
            "status": (
                "failed"
                if safety_status == "failed"
                else "degraded"
                if operational_status in {"blocked", "degraded"}
                else "accepted"
            ),
            "safety_status": safety_status,
            "operational_status": operational_status,
            "latest_failures": latest_failures,
            "latest_repairs": latest_repairs,
            "event_count": len(rows),
            "coordinator_source_video_bytes": source_bytes,
            "ledger_head_sha256": rows[-1]["event_id"] if rows else None,
            "content_value_counts": dispositions,
            "promoted_tier_counts": tiers,
            "gray_report_count": gray_count,
            "reminder_count": reminder_count,
            "book_trade_count": book_trade_count,
            "event_ids": [str(row["event_id"]) for row in source_events],
            "interruption_count": sum(
                row.get("event") == "source_interrupted" for row in rows
            ),
            "operational_reminder_count": sum(
                row.get("event") == "blocker_notified" for row in rows
            ),
            "transient_failure_count": sum(
                row.get("event") == "source_retryable_failure" for row in rows
            ),
            "repair_required_count": sum(
                row.get("event") == "source_completed"
                and (row.get("result") or {}).get("repair_required") is True
                for row in rows
            ),
            "failure_fingerprint_count": len({
                str(row.get("failure_fingerprint") or "")
                for row in convergence_rows
                if row.get("event") == "failure_observed"
            }),
            "repair_closed_count": sum(
                row.get("event") == "repair_closed"
                for row in convergence_rows
            ),
            "viewpoint_evaluation_count": len(viewpoint_events),
        }
