"""Short-lived, append-only KOL daytime coordination.

The coordinator owns only scheduling, ordering, recovery, and terminal
validation.  Existing source adapters continue to own discovery and
enrichment; source-video bytes are never accepted by this seam.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from .enrichment_types import EnrichmentError, is_durable_report_only
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
from .writer_progress import ConvergenceLedger, WriterProgress


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
_LOCAL_THESIS_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")


class DailyError(EnrichmentError):
    """The daily coordination contract could not be proved."""


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

    def __init__(self, blocker_key: str, action: str):
        self.blocker_key = str(blocker_key or "").strip()
        self.action = str(action or "").strip()
        if not self.blocker_key or not self.action:
            raise ValueError("user-action blocker needs a key and exact action")
        super().__init__(self.action)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


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
    projection_id = canonical_sha256(
        {
            "report_id": report["record_id"],
            "evidence_sha256": request["evidence_sha256"],
            "projection": projection,
        }
    )
    updated_records, publish = build_append_only_publication_update(
        current_records=records,
        additions=additions,
        viewpoint_ids=viewpoint_ids,
        created_at=projection["evaluated_at"],
        revision=f"initial-projection-{projection_id}",
        reason="补齐来源证据支持的初始长期观点；不创建提醒或 Book 动作。",
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
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.convergence = ConvergenceLedger(
            self.output_dir / "convergence.jsonl",
            now=lambda: self._beijing_now(),
        )
        self.lock_path = self.output_dir / ".lock"
        self.now = now or (lambda: datetime.now(BEIJING))
        self._thread_lock = threading.RLock()

    def _beijing_now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise DailyError("daily coordinator clock needs a timezone")
        return value.astimezone(BEIJING)

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
        if not self.events_path.is_file():
            return []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DailyError("daily ledger cannot be read") from exc
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > MAX_LEDGER_LINE_BYTES:
                raise DailyError(f"daily ledger line {number} exceeds limit")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DailyError(
                    f"daily ledger line {number} is invalid"
                ) from exc
            event_id = str(row.get("event_id") or "")
            unsigned = dict(row)
            unsigned.pop("event_id", None)
            if event_id != _sha256(unsigned):
                raise DailyError(
                    f"daily ledger line {number} failed integrity validation"
                )
            rows.append(row)
        return rows

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
        start = next(
            (
                index
                for index in range(end - 1, -1, -1)
                if rows[index].get("event")
                in {"sweep_started", "sweep_resumed"}
            ),
            0,
        )
        attempt = rows[start : end + 1]
        legacy_failure = {
            "category": "source_error",
            "code": "legacy_unclassified_failure",
            "stage": "source_run",
            "retryable": True,
        }
        failures = {
            str(row.get("source") or ""): legacy_failure
            for row in attempt
            if row.get("event") == "source_retryable_failure"
        }
        source_states: list[dict[str, Any]] = []
        for row in attempt:
            if row.get("event") != "source_completed":
                continue
            result = row.get("result")
            if not isinstance(result, dict):
                continue
            state = {
                key: value
                for key, value in {
                    "name": str(row.get("source") or ""),
                    "status": result.get("status"),
                    "retryable": result.get("retryable"),
                    "user_action_required": result.get("user_action_required"),
                    "waiting_count": result.get("waiting_count"),
                    "waiting_items": result.get("waiting_items"),
                }.items()
                if value is not None
            }
            if state["name"] in failures:
                state["failure"] = failures[state["name"]]
            source_states.append(state)
        if any(row.get("user_action_required") for row in source_states):
            health = "blocked"
        elif failures:
            health = "degraded"
        elif any(row.get("status") == "waiting" for row in source_states):
            health = "waiting"
        else:
            health = "healthy"
        return {
            **completed,
            "health": health,
            "source_states": source_states,
        }

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "schema_version": 1,
            "event": event,
            "occurred_at": self._beijing_now().isoformat(timespec="seconds"),
            **fields,
        }
        row["event_id"] = _sha256(row)
        payload = (_canonical(row) + "\n").encode("utf-8")
        if len(payload) > MAX_LEDGER_LINE_BYTES:
            raise DailyError("daily ledger event exceeds limit")
        blocked = {signal.SIGINT, signal.SIGTERM}
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.events_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise DailyError("daily ledger append made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        return row

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
                active_progress = self.convergence.active_progress(name)
                retained_outcome: dict[str, Any] | None = None
                if active_progress is not None:
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
                self._append("source_started", slot=slot, source=name)
                try:
                    outcome = (
                        retained_outcome
                        if retained_outcome is not None
                        else runner()
                    )
                except UserActionBlocker as exc:
                    blocker_state_rows = [
                        row
                        for row in self._events_unlocked()
                        if row.get("event")
                        in {"blocker_notified", "blocker_cleared"}
                        and row.get("source") == name
                    ]
                    active_key = (
                        str(blocker_state_rows[-1].get("blocker_key"))
                        if blocker_state_rows
                        and blocker_state_rows[-1].get("event")
                        == "blocker_notified"
                        else ""
                    )
                    notified = active_key == exc.blocker_key
                    if not notified:
                        if blocker_sender is None:
                            raise DailyError(
                                "user-action blocker requires an operational sender"
                            ) from exc
                        blocker_sender("KOL 日常运行需要你处理", exc.action)
                        self._append(
                            "blocker_notified",
                            slot=slot,
                            source=name,
                            blocker_key=exc.blocker_key,
                            action=exc.action,
                        )
                    outcome = {
                        "status": "waiting",
                        "blocker_key": exc.blocker_key,
                        "user_action_required": True,
                        "notification_sent": not notified,
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
                    if consecutive_prior >= 1:
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
                except BaseException as exc:
                    self._append(
                        "source_interrupted",
                        slot=slot,
                        source=name,
                        error_type=type(exc).__name__,
                    )
                    raise
                if outcome is None:
                    outcome = {"status": "no_update"}
                if not isinstance(outcome, dict):
                    raise DailyError(f"daily source {name} returned an invalid result")
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
                _validate_source_outcome(outcome)
                raw_progress = outcome.get("writer_progress")
                if raw_progress is not None:
                    progress = WriterProgress.from_dict(raw_progress)
                    if progress.status == "repair_required":
                        self.convergence.record(progress, slot=slot)
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
            source_states = [
                {
                    key: row[key]
                    for key in (
                        "name",
                        "status",
                        "retryable",
                        "repair_required",
                        "repair_key",
                        "user_action_required",
                        "waiting_count",
                        "waiting_items",
                        "failure",
                        "writer_progress",
                    )
                    if key in row
                }
                for row in results
            ]
            if any(row.get("user_action_required") for row in results):
                health = "blocked"
            elif any(
                row.get("failure") or row.get("repair_required")
                for row in results
            ):
                health = "degraded"
            elif any(row.get("status") == "waiting" for row in results):
                health = "waiting"
            else:
                health = "healthy"
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(results),
                source_states=source_states,
                coordinator_source_video_bytes=0,
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
            }
            for state in ((last or {}).get("source_states") or [])
            if isinstance(state, dict) and state.get("repair_required") is True
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
                row.get("event")
                in {"source_recovery_exhausted", "source_acquisition_stalled"}
                for row in rows
            ) + sum(
                row.get("event") == "failure_observed"
                for row in convergence_rows
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
