"""Evidence-bound Book T v2 trend judgment snapshots.

This module is the Phase 1 boundary for Book T v2.  It turns an Agent draft
and already published, receipt-bound KOL records into a deterministic
judgment capsule.  It deliberately does not know about instruments, fills,
positions, accounts, or the paper ledger.  Those concerns belong to later
Book T modules and the existing deterministic spine.

The public seam is :func:`build_trend_snapshot`.  ``published_sources`` are
publication readbacks (the shape returned by ``PublicationLedger.status`` or
the equivalent remote publication readback), not prepared artifacts.  The
builder verifies record hashes, the publication manifest, the terminal
publication receipt, and the latest viewpoint evaluation before using any
source evidence.  Natural-language viewpoint horizons are retained as source
evidence, never guessed by deterministic code; a non-Mache source with an
explicit horizon must carry an ISO ``review_not_after`` on its latest
evaluation before it can remain current.
"""

from __future__ import annotations

import calendar
import copy
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from xiaocao.kol.publication import (
    canonical_sha256,
    manifest_entries,
    manifest_sha256,
    record_content_sha256,
)


SNAPSHOT_SCHEMA_VERSION = 1
AGENT_JUDGMENT_VERSION = "book-t-v2-trend-snapshot-v1"
MACHE_KOL_ID = "kol-lv-xiaotong"
XIAOCAO_KOL_IDS = frozenset({"kol-xiaocao", "xiaocao"})
MISSING_HORIZON_DECAY_DAYS = 1

ELIGIBILITIES = frozenset({"eligible", "wait", "conflicted", "invalidated"})
MARKET_STATUSES = frozenset({"support", "qualify", "conflict", "invalidate"})
PUBLISHED_STATES = frozenset({"published", "superseded"})
CURRENT_EVALUATION_STATES = frozenset({"current"})
CONFLICTED_EVALUATION_STATES = frozenset({"conflicted", "conflict"})
INVALID_EVALUATION_STATES = frozenset({"invalidated", "expired"})

_DIRECTION_ALIASES = {
    "bullish": "bullish",
    "positive": "bullish",
    "up": "bullish",
    "long": "bullish",
    "看多": "bullish",
    "偏多": "bullish",
    "bearish": "bearish",
    "negative": "bearish",
    "down": "bearish",
    "short": "bearish",
    "看空": "bearish",
    "偏空": "bearish",
    "neutral": "neutral",
    "sideways": "neutral",
    "flat": "neutral",
    "中性": "neutral",
    "mixed": "mixed",
    "conflicted": "mixed",
    "分歧": "mixed",
}
_FORBIDDEN_DRAFT_KEYS = frozenset(
    {
        "account",
        "account_id",
        "code",
        "content_sha256",
        "evidence_id",
        "evidence_ids",
        "evidence_sha256",
        "evidence_refs",
        "evaluation_id",
        "fill",
        "ledger",
        "manifest_sha256",
        "notional",
        "order",
        "order_id",
        "position",
        "price",
        "publication_id",
        "publication_key",
        "publication_version",
        "quantity",
        "record_id",
        "receipt",
        "report_id",
        "shares",
        "source_binding",
        "ticker",
        "trade",
        "viewpoint_id",
    }
)
_SAFE_THEME_ID = re.compile(r"^[^\s]{1,160}$")


class TrendSnapshotError(ValueError):
    """The snapshot inputs cannot be converted into a safe judgment capsule."""


class PublicationBindingError(TrendSnapshotError):
    """A KOL source is not bound to a terminal publication receipt."""


def _text(value: Any, *, field: str, required: bool = True) -> str:
    if value is None:
        if required:
            raise TrendSnapshotError(f"{field} is required")
        return ""
    result = str(value).strip()
    if required and not result:
        raise TrendSnapshotError(f"{field} is required")
    return result


def _mapping(value: Any, *, field: str, required: bool = True) -> dict[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise TrendSnapshotError(f"{field} must be an object")
    return {str(key): copy.deepcopy(item) for key, item in value.items()}


def _parse_time(value: Any, *, field: str, date_as_end: bool = False) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if date_as_end else time.min)
    else:
        text = _text(value, field=field)
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                parsed = datetime.combine(
                    date.fromisoformat(text),
                    time.max if date_as_end else time.min,
                )
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise TrendSnapshotError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise TrendSnapshotError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _normalize_as_of(value: Any) -> tuple[str, datetime]:
    parsed = _parse_time(value, field="as_of", date_as_end=True)
    return _iso(parsed), parsed


def _add_month(value: datetime) -> datetime:
    """Add one calendar month, clamping the day instead of using 30 days."""

    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _direction(value: Any, *, field: str) -> str:
    normalized = _text(value, field=field).lower()
    result = _DIRECTION_ALIASES.get(normalized)
    if result is None:
        raise TrendSnapshotError(
            f"{field} must be one of bullish, bearish, neutral, or mixed"
        )
    return result


def _canonical_json(value: Any) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TrendSnapshotError("snapshot input is not canonical JSON") from exc
    if not isinstance(decoded, dict):
        raise TrendSnapshotError("snapshot input must canonicalize to an object")
    return decoded


def _ensure_json_safe(value: Any, *, field: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TrendSnapshotError(f"{field} is not JSON serializable") from exc


def _find_forbidden_draft_key(value: Any, *, path: str = "agent_draft") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_DRAFT_KEYS:
                return f"{path}.{key}"
            found = _find_forbidden_draft_key(child, path=f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_forbidden_draft_key(child, path=f"{path}[{index}]")
            if found:
                return found
    return None


def _record_payload(record: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise PublicationBindingError(f"{field}.payload is required")
    return {str(key): copy.deepcopy(value) for key, value in payload.items()}


@dataclass(frozen=True)
class _SourceEvidence:
    source_key: str
    role: str
    kol_id: str
    publication_key: str
    publication_state: str
    manifest_sha256: str
    report_id: str
    viewpoint_id: str
    evaluation_id: str
    evaluation_status: str
    source_published_at: str
    evaluated_at: str
    review_not_after: str | None
    source_binding: dict[str, Any]
    viewpoint_content_sha256: str
    evidence_refs: tuple[dict[str, str], ...]
    theme_ids: tuple[str, ...]
    horizon: tuple[str, ...]
    relations: tuple[dict[str, Any], ...]
    subject: str


def _role_for_source(*, kol_id: str) -> str:
    if kol_id in XIAOCAO_KOL_IDS:
        return "xiaocao"
    if kol_id == MACHE_KOL_ID:
        return "mache"
    return "other_kol"


def _publication_parts(raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
    publication = raw.get("publication")
    container = publication if isinstance(publication, Mapping) else raw
    artifact = container.get("artifact")
    if not isinstance(artifact, Mapping):
        artifact = container
    records = artifact.get("records")
    if not isinstance(records, list):
        records = container.get("records")
    if not isinstance(records, list):
        raise PublicationBindingError(
            "publication binding requires the complete published record manifest"
        )
    receipt = (
        container.get("publish_receipt")
        or container.get("publication_receipt")
        or container.get("receipt")
        or raw.get("publish_receipt")
        or raw.get("publication_receipt")
        or raw.get("receipt")
    )
    if not isinstance(receipt, Mapping):
        raise PublicationBindingError(
            "publication receipt is required; prepared artifact is not authoritative"
        )
    receipt_copy = {str(key): copy.deepcopy(value) for key, value in receipt.items()}
    return (
        {str(key): copy.deepcopy(value) for key, value in artifact.items()},
        records,
        receipt_copy,
    )


def _validate_manifest(
    *,
    artifact: Mapping[str, Any],
    records: list[Any],
    receipt: Mapping[str, Any],
) -> str:
    if not records or any(not isinstance(record, Mapping) for record in records):
        raise PublicationBindingError("published manifest records are invalid")
    validated_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        value = dict(record)
        try:
            expected = record_content_sha256(value)
        except Exception as exc:
            raise PublicationBindingError(
                f"publication binding record {index} cannot be validated"
            ) from exc
        if value.get("content_sha256") != expected:
            raise PublicationBindingError(
                f"publication binding record {index} content hash mismatch"
            )
        validated_records.append(value)
    computed_entries = manifest_entries(validated_records)
    request = artifact.get("publish_request")
    request = request if isinstance(request, Mapping) else {}
    supplied_entries = request.get("records") or artifact.get("manifest")
    if supplied_entries is not None and supplied_entries != computed_entries:
        raise PublicationBindingError("publication binding manifest records mismatch")
    supplied_hashes = [
        request.get("manifest_sha256"),
        artifact.get("manifest_sha256"),
        receipt.get("manifestSha256"),
        receipt.get("manifest_sha256"),
    ]
    supplied_hash = next((str(value) for value in supplied_hashes if value), "")
    if not supplied_hash:
        raise PublicationBindingError("publication receipt is missing manifest hash")
    expected_hash = manifest_sha256(computed_entries)
    if supplied_hash != expected_hash:
        raise PublicationBindingError("publication receipt manifest hash mismatch")
    return expected_hash


def _latest_evaluation(
    evaluations: list[dict[str, Any]],
    *,
    viewpoint_id: str,
    as_of: datetime,
    source_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for record in evaluations:
        payload = _record_payload(record, field=f"{source_key}.evaluation")
        if str(payload.get("viewpoint_id") or "") != viewpoint_id:
            continue
        evaluated_at = _parse_time(
            payload.get("evaluated_at"),
            field=f"{source_key}.evaluation.evaluated_at",
        )
        evaluation_as_of = _parse_time(
            payload.get("as_of") or payload.get("evaluated_at"),
            field=f"{source_key}.evaluation.as_of",
        )
        if evaluated_at > as_of or evaluation_as_of > as_of:
            continue
        candidates.append((evaluated_at, record, payload))
    if not candidates:
        raise PublicationBindingError(
            f"{source_key} has no latest viewpoint evaluation bound to as_of"
        )
    _, record, payload = max(
        candidates,
        key=lambda item: (item[0], str(item[1].get("record_id") or "")),
    )
    return dict(record), payload


@dataclass(frozen=True)
class _BoundPublication:
    source_key: str
    publication_state: str
    manifest_sha256: str
    report: dict[str, Any]
    report_payload: dict[str, Any]
    viewpoint: dict[str, Any]
    viewpoint_payload: dict[str, Any]
    evaluation: dict[str, Any]
    evaluation_payload: dict[str, Any]
    relations: tuple[dict[str, Any], ...]
    source_binding: dict[str, Any]


def _normalize_relations(
    relations: Iterable[Any],
    *,
    source_key: str,
) -> tuple[dict[str, Any], ...]:
    parsed: list[dict[str, Any]] = []
    for relation in relations:
        relation_payload = _record_payload(relation, field=f"{source_key}.relation")
        if not all(
            str(relation_payload.get(field) or "").strip()
            for field in ("from_viewpoint_id", "to_viewpoint_id", "relation_type")
        ):
            raise PublicationBindingError(f"{source_key} relation identity is incomplete")
        parsed.append(
            {
                "relation_id": str(
                    relation.get("record_id")
                    or relation_payload.get("relation_id")
                    or ""
                ),
                "from_viewpoint_id": str(relation_payload["from_viewpoint_id"]),
                "to_viewpoint_id": str(relation_payload["to_viewpoint_id"]),
                "relation_type": str(relation_payload["relation_type"]),
                "asserted_at": str(relation_payload.get("asserted_at") or ""),
            }
        )
    return tuple(parsed)


def _bind_publication(
    raw: Any,
    *,
    index: int,
    as_of: datetime,
) -> _BoundPublication:
    if not isinstance(raw, Mapping):
        raise PublicationBindingError(f"published source {index} must be an object")
    source_key = str(raw.get("source_key") or f"source-{index}").strip()
    if not source_key:
        raise PublicationBindingError(f"published source {index} has no source_key")
    artifact, records_raw, receipt = _publication_parts(raw)
    publication_state = str(
        receipt.get("recordState") or receipt.get("record_state") or ""
    ).strip()
    if publication_state not in PUBLISHED_STATES:
        raise PublicationBindingError(
            f"{source_key} publication receipt is not terminally published"
        )
    manifest_hash = _validate_manifest(
        artifact=artifact,
        records=records_raw,
        receipt=receipt,
    )
    records = [dict(record) for record in records_raw]
    reports = [record for record in records if record.get("kind") == "report"]
    viewpoints = [record for record in records if record.get("kind") == "viewpoint"]
    evaluations = [
        record for record in records if record.get("kind") == "viewpoint_evaluation"
    ]
    relations = [
        record for record in records if record.get("kind") == "viewpoint_relation"
    ]
    if len(reports) != 1 or not viewpoints:
        raise PublicationBindingError(
            f"{source_key} publication must bind one report and one or more viewpoints"
    )
    report = reports[0]
    report_payload = _record_payload(report, field=f"{source_key}.report")
    report_id = str(report.get("record_id") or "").strip()
    if report_payload.get("report_id") != report_id:
        raise PublicationBindingError(f"{source_key} report identity does not match its envelope")
    receipt_record_id = str(
        receipt.get("recordId") or receipt.get("record_id") or ""
    ).strip()
    if not receipt_record_id or receipt_record_id != report_id:
        raise PublicationBindingError(f"{source_key} receipt record identity does not match report")
    viewpoint_hint = str(raw.get("viewpoint_id") or "").strip()
    candidates = viewpoints
    if viewpoint_hint:
        candidates = [row for row in viewpoints if row.get("record_id") == viewpoint_hint]
    if len(candidates) != 1:
        raise PublicationBindingError(
            f"{source_key} publication must select exactly one viewpoint"
        )
    viewpoint = candidates[0]
    viewpoint_payload = _record_payload(viewpoint, field=f"{source_key}.viewpoint")
    viewpoint_id = str(viewpoint.get("record_id") or "").strip()
    if viewpoint_payload.get("viewpoint_id") != viewpoint_id:
        raise PublicationBindingError(f"{source_key} viewpoint identity mismatch")
    if str(viewpoint_payload.get("report_id") or "") != str(report.get("record_id") or ""):
        raise PublicationBindingError(f"{source_key} viewpoint is not bound to its report")
    report_viewpoint_ids = report_payload.get("viewpoint_ids")
    if not isinstance(report_viewpoint_ids, list) or viewpoint_id not in report_viewpoint_ids:
        raise PublicationBindingError(
            f"{source_key} report manifest omits the selected viewpoint"
        )
    evaluation, evaluation_payload = _latest_evaluation(
        evaluations,
        viewpoint_id=viewpoint_id,
        as_of=as_of,
        source_key=source_key,
    )
    evaluation_id = str(evaluation.get("record_id") or "").strip()
    if evaluation_payload.get("evaluation_id") != evaluation_id:
        raise PublicationBindingError(
            f"{source_key} evaluation identity does not match its envelope"
        )
    source_binding = report.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise PublicationBindingError(f"{source_key} report source binding is missing")
    binding = {str(key): copy.deepcopy(value) for key, value in source_binding.items()}
    if not binding.get("publication_id") or not binding.get("publication_version"):
        raise PublicationBindingError(f"{source_key} publication identity binding is incomplete")
    for record_name, record in (
        ("viewpoint", viewpoint),
        ("evaluation", evaluation),
    ):
        if record.get("source_binding") != binding:
            raise PublicationBindingError(
                f"{source_key} {record_name} source binding does not match report"
            )
    return _BoundPublication(
        source_key=source_key,
        publication_state=publication_state,
        manifest_sha256=manifest_hash,
        report=report,
        report_payload=report_payload,
        viewpoint=viewpoint,
        viewpoint_payload=viewpoint_payload,
        evaluation=evaluation,
        evaluation_payload=evaluation_payload,
        relations=_normalize_relations(relations, source_key=source_key),
        source_binding=binding,
    )


def _normalize_source(
    raw: Any,
    *,
    index: int,
    as_of: datetime,
) -> _SourceEvidence:
    bound = _bind_publication(raw, index=index, as_of=as_of)
    source_key = bound.source_key
    report = bound.report
    report_payload = bound.report_payload
    viewpoint = bound.viewpoint
    viewpoint_payload = bound.viewpoint_payload
    evaluation = bound.evaluation
    evaluation_payload = bound.evaluation_payload
    binding = bound.source_binding
    publication_state = bound.publication_state
    viewpoint_id = str(viewpoint.get("record_id") or "").strip()
    publication_key = str(
        raw.get("publication_key")
        or binding.get("publication_id")
        or report.get("record_id")
        or source_key
    ).strip()
    source_published_at = str(
        viewpoint_payload.get("source_published_at")
        or report_payload.get("source_published_at")
        or ""
    ).strip()
    if source_published_at:
        published_dt = _parse_time(
            source_published_at,
            field=f"{source_key}.source_published_at",
        )
        if published_dt > as_of:
            raise PublicationBindingError(f"{source_key} publication is future-dated")
        source_published_at = _iso(published_dt)
    else:
        raise PublicationBindingError(
            f"{source_key} publication time is required for freshness binding"
        )
    evaluated_dt = _parse_time(
        evaluation_payload.get("evaluated_at"),
        field=f"{source_key}.evaluation.evaluated_at",
    )
    review_not_after_value = evaluation_payload.get("review_not_after")
    review_not_after = None
    if review_not_after_value not in (None, ""):
        review_not_after_dt = _parse_time(
            review_not_after_value,
            field=f"{source_key}.evaluation.review_not_after",
        )
        if review_not_after_dt < evaluated_dt:
            raise PublicationBindingError(
                f"{source_key} evaluation review_not_after precedes evaluated_at"
            )
        review_not_after = _iso(review_not_after_dt)
    report_kol_id = str(report_payload.get("kol_id") or "").strip()
    viewpoint_kol_id = str(viewpoint_payload.get("kol_id") or "").strip()
    if not report_kol_id or not viewpoint_kol_id:
        raise PublicationBindingError(f"{source_key} stable KOL identity is required")
    if report_kol_id != viewpoint_kol_id:
        raise PublicationBindingError(f"{source_key} report and viewpoint KOL identity mismatch")
    kol_id = viewpoint_kol_id
    subject = str(viewpoint_payload.get("subject") or "").strip()
    role = _role_for_source(
        kol_id=kol_id,
    )
    raw_theme_ids = raw.get("theme_ids") or raw.get("themes") or []
    if isinstance(raw_theme_ids, str):
        raw_theme_ids = [raw_theme_ids]
    if not isinstance(raw_theme_ids, list):
        raise TrendSnapshotError(f"{source_key}.theme_ids must be a list")
    theme_ids = tuple(sorted({str(value).strip() for value in raw_theme_ids if str(value).strip()}))
    raw_horizon = viewpoint_payload.get("horizon") or []
    if isinstance(raw_horizon, str):
        raw_horizon = [raw_horizon]
    if not isinstance(raw_horizon, list):
        raise PublicationBindingError(f"{source_key}.viewpoint.horizon must be a list")
    raw_evidence_refs = viewpoint_payload.get("evidence_refs")
    if not isinstance(raw_evidence_refs, list) or not raw_evidence_refs:
        raise PublicationBindingError(f"{source_key}.viewpoint.evidence_refs are required")
    evidence_refs: list[dict[str, str]] = []
    for ref_index, raw_ref in enumerate(raw_evidence_refs):
        if not isinstance(raw_ref, Mapping):
            raise PublicationBindingError(
                f"{source_key}.viewpoint.evidence_refs[{ref_index}] is invalid"
            )
        ref = {
            field: str(raw_ref.get(field) or "").strip()
            for field in ("claim_id", "segment_id", "evidence_id", "evidence_sha256")
            if str(raw_ref.get(field) or "").strip()
        }
        if not ref:
            raise PublicationBindingError(
                f"{source_key}.viewpoint.evidence_refs[{ref_index}] has no identity"
            )
        evidence_refs.append(ref)
    return _SourceEvidence(
        source_key=source_key,
        role=role,
        kol_id=kol_id,
        publication_key=publication_key,
        publication_state=publication_state,
        manifest_sha256=bound.manifest_sha256,
        report_id=str(report.get("record_id") or ""),
        viewpoint_id=viewpoint_id,
        evaluation_id=str(evaluation.get("record_id") or ""),
        evaluation_status=str(evaluation_payload.get("status") or "").strip(),
        source_published_at=source_published_at,
        evaluated_at=_iso(evaluated_dt),
        review_not_after=review_not_after,
        source_binding=binding,
        viewpoint_content_sha256=str(viewpoint.get("content_sha256") or ""),
        evidence_refs=tuple(evidence_refs),
        theme_ids=theme_ids,
        horizon=tuple(str(value).strip() for value in raw_horizon if str(value).strip()),
        relations=bound.relations,
        subject=subject,
    )


def _validate_agent_draft(draft: Any) -> dict[str, Any]:
    value = _mapping(draft, field="agent_draft")
    forbidden = _find_forbidden_draft_key(value)
    if forbidden:
        raise TrendSnapshotError(
            f"agent draft contains forbidden business identity field at {forbidden}"
        )
    _ensure_json_safe(value, field="agent_draft")
    raw_themes = value.get("themes")
    if not isinstance(raw_themes, list):
        raise TrendSnapshotError("agent_draft.themes must be a list")
    themes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_theme in enumerate(raw_themes):
        theme = _mapping(raw_theme, field=f"agent_draft.themes[{index}]")
        theme_id = _text(theme.get("theme_id"), field=f"agent_draft.themes[{index}].theme_id")
        if not _SAFE_THEME_ID.fullmatch(theme_id):
            raise TrendSnapshotError(f"agent_draft.themes[{index}].theme_id is invalid")
        if theme_id in seen:
            raise TrendSnapshotError(f"agent_draft contains duplicate theme_id {theme_id}")
        seen.add(theme_id)
        display_name = _text(
            theme.get("display_name"),
            field=f"agent_draft.themes[{index}].display_name",
        )
        direction = _direction(
            theme.get("direction"),
            field=f"agent_draft.themes[{index}].direction",
        )
        confidence = theme.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise TrendSnapshotError(f"agent_draft.themes[{index}].confidence must be a number")
        if not 0 <= float(confidence) <= 1:
            raise TrendSnapshotError(
                f"agent_draft.themes[{index}].confidence must be between 0 and 1"
            )
        eligibility = str(theme.get("eligibility") or "wait").strip()
        if eligibility not in ELIGIBILITIES:
            raise TrendSnapshotError(f"agent_draft.themes[{index}].eligibility is invalid")
        source_keys = theme.get("source_keys") or []
        if isinstance(source_keys, str):
            source_keys = [source_keys]
        if not isinstance(source_keys, list) or any(not str(item).strip() for item in source_keys):
            raise TrendSnapshotError(f"agent_draft.themes[{index}].source_keys is invalid")
        normalized = dict(theme)
        normalized.update(
            {
                "theme_id": theme_id,
                "display_name": display_name,
                "direction": direction,
                "confidence": float(confidence),
                "eligibility": eligibility,
                "source_keys": sorted({str(item).strip() for item in source_keys}),
            }
        )
        if normalized.get("effective_from"):
            normalized["effective_from"] = _iso(
                _parse_time(
                    normalized["effective_from"],
                    field=f"agent_draft.themes[{index}].effective_from",
                )
            )
        if normalized.get("review_not_after"):
            normalized["review_not_after"] = _iso(
                _parse_time(
                    normalized["review_not_after"],
                    field=f"agent_draft.themes[{index}].review_not_after",
                )
            )
        themes.append(normalized)
    value["themes"] = themes
    return value


def _normalize_context(context: Any, *, as_of: datetime) -> dict[str, Any]:
    if context is None:
        return {
            "status": "unavailable",
            "reason": "missing_current_xiaocao_context",
            "evidence_ids": [],
        }
    value = _mapping(context, field="xiaocao_context")
    evidence_ids = value.get("evidence_ids") or value.get("evidence") or []
    if isinstance(evidence_ids, str):
        evidence_ids = [evidence_ids]
    if not isinstance(evidence_ids, list):
        raise TrendSnapshotError("xiaocao_context.evidence_ids must be a list")
    normalized_evidence = sorted({str(item).strip() for item in evidence_ids if str(item).strip()})
    context_time_value = value.get("as_of") or value.get("observed_at")
    if not context_time_value:
        return {
            "status": "unavailable",
            "reason": "xiaocao_context_time_missing",
            "evidence_ids": normalized_evidence,
        }
    context_time = _parse_time(context_time_value, field="xiaocao_context.as_of")
    if context_time > as_of or not normalized_evidence:
        return {
            "status": "unavailable",
            "reason": "xiaocao_context_not_current_or_unbound",
            "as_of": _iso(context_time),
            "evidence_ids": normalized_evidence,
        }
    direction = value.get("direction")
    result: dict[str, Any] = {
        "status": "current",
        "as_of": _iso(context_time),
        "observed_at": _iso(
            _parse_time(
                value.get("observed_at") or context_time,
                field="xiaocao_context.observed_at",
            )
        ),
        "stance": str(value.get("stance") or value.get("timing") or "").strip(),
        "evidence_ids": normalized_evidence,
    }
    if direction not in (None, ""):
        result["direction"] = _direction(direction, field="xiaocao_context.direction")
    if value.get("timing_status"):
        result["timing_status"] = str(value["timing_status"]).strip()
    return result


def _market_for_theme(
    market_validation: Any,
    *,
    theme_id: str,
    as_of: datetime,
) -> tuple[dict[str, Any], str, bool]:
    if isinstance(market_validation, Mapping):
        raw = market_validation.get(theme_id)
    elif isinstance(market_validation, list):
        raw = next(
            (
                item
                for item in market_validation
                if isinstance(item, Mapping) and str(item.get("theme_id") or "") == theme_id
            ),
            None,
        )
    else:
        raise TrendSnapshotError("market_validation must be an object or list")
    if not isinstance(raw, Mapping):
        return (
            {
                "status": "unavailable",
                "reason": "market_validation_missing",
                "facts": [],
                "evidence_ids": [],
            },
            "missing",
            False,
        )
    value = {str(key): copy.deepcopy(item) for key, item in raw.items()}
    status = str(value.get("status") or "").strip()
    if status not in MARKET_STATUSES:
        return (
            {
                "status": "unavailable",
                "reason": "market_validation_status_invalid",
                "facts": [],
                "evidence_ids": [],
            },
            "missing",
            False,
        )
    checked_at_value = value.get("checked_at") or (value.get("currentness") or {}).get("checked_at")
    as_of_value = value.get("as_of")
    facts = value.get("facts")
    currentness = value.get("currentness")
    if (
        not checked_at_value
        or not as_of_value
        or not isinstance(currentness, Mapping)
        or not isinstance(facts, list)
        or not facts
    ):
        return (
            {
                "status": status,
                "reason": "market_validation_evidence_incomplete",
                "facts": [],
                "evidence_ids": [],
            },
            status,
            False,
        )
    checked_at = _parse_time(checked_at_value, field=f"market_validation[{theme_id}].checked_at")
    validation_as_of = _parse_time(as_of_value, field=f"market_validation[{theme_id}].as_of")
    latest = currentness.get("latest_available") is True
    current = latest and validation_as_of <= as_of and checked_at <= as_of
    normalized_facts: list[dict[str, Any]] = []
    for index, raw_fact in enumerate(facts):
        if not isinstance(raw_fact, Mapping):
            current = False
            continue
        fact = {str(key): copy.deepcopy(item) for key, item in raw_fact.items()}
        observed_at_value = fact.get("observed_at")
        if not all(
            fact.get(field) not in (None, "")
            for field in ("metric", "value", "evidence")
        ) or not observed_at_value:
            current = False
            continue
        observed_at = _parse_time(
            observed_at_value,
            field=f"market_validation[{theme_id}].facts[{index}].observed_at",
        )
        if observed_at > checked_at:
            current = False
        fact["observed_at"] = _iso(observed_at)
        normalized_facts.append(fact)
    result = {
        "status": status,
        "as_of": _iso(validation_as_of),
        "checked_at": _iso(checked_at),
        "currentness": {
            "latest_available": latest,
            "reason": str(currentness.get("reason") or "").strip(),
            "checked_at": _iso(
                _parse_time(
                    currentness.get("checked_at"),
                    field=(
                        f"market_validation[{theme_id}].currentness.checked_at"
                    ),
                )
            ),
        },
        "facts": normalized_facts,
        "evidence_ids": sorted(
            {
                str(fact.get("evidence") or fact.get("fact_id") or "").strip()
                for fact in normalized_facts
                if str(fact.get("evidence") or fact.get("fact_id") or "").strip()
            }
        ),
    }
    if not result["currentness"]["reason"]:
        current = False
    if not normalized_facts:
        current = False
    if not current:
        result["reason"] = "market_validation_not_current"
    return result, status, current


def _source_status(
    source: _SourceEvidence,
    *,
    as_of: datetime,
    replaced_by: Mapping[str, str],
    theme_review_not_after: datetime | None,
) -> dict[str, Any]:
    status = source.evaluation_status
    if status in INVALID_EVALUATION_STATES:
        return {"status": status, "current": False, "freshness_basis": f"evaluation_{status}"}
    if status in CONFLICTED_EVALUATION_STATES:
        return {
            "status": "conflicted",
            "current": False,
            "freshness_basis": "evaluation_conflicted",
        }
    if status not in CURRENT_EVALUATION_STATES:
        return {"status": "pending", "current": False, "freshness_basis": "evaluation_not_current"}
    if source.viewpoint_id in replaced_by:
        return {
            "status": "replaced",
            "current": False,
            "freshness_basis": "explicit_viewpoint_replacement",
            "replaced_by_viewpoint_id": replaced_by[source.viewpoint_id],
        }
    if source.role == "mache":
        if not source.source_published_at:
            return {
                "status": "stale",
                "current": False,
                "freshness_basis": "mache_publication_time_missing",
            }
        expiry = _add_month(
            _parse_time(
                source.source_published_at,
                field="mache.source_published_at",
            )
        )
        if as_of > expiry:
            return {
                "status": "expired",
                "current": False,
                "freshness_basis": "mache_one_calendar_month_cap",
                "review_not_after": _iso(expiry),
            }
        return {
            "status": "current",
            "current": True,
            "freshness_basis": "mache_one_calendar_month_cap",
            "review_not_after": _iso(expiry),
        }
    if source.role == "other_kol" and not source.horizon:
        expiry = _parse_time(
            source.source_published_at,
            field="other_kol.source_published_at",
        ) + timedelta(days=MISSING_HORIZON_DECAY_DAYS)
        current = as_of <= expiry
        return {
            "status": "current" if current else "stale",
            "current": current,
            "freshness_basis": "missing_horizon_rapid_decay_1d",
            "review_not_after": _iso(expiry),
        }
    if source.role != "mache" and source.horizon and not source.review_not_after:
        return {
            "status": "pending",
            "current": False,
            "freshness_basis": "horizon_requires_machine_review_not_after",
        }
    review_not_after = (
        _parse_time(source.review_not_after, field="source.review_not_after")
        if source.review_not_after
        else theme_review_not_after
    )
    if (
        theme_review_not_after is not None
        and review_not_after is not None
        and theme_review_not_after < review_not_after
    ):
        review_not_after = theme_review_not_after
    if review_not_after is not None and as_of > review_not_after:
        return {
            "status": "stale",
            "current": False,
            "freshness_basis": (
                "source_review_not_after"
                if source.review_not_after
                else "theme_review_not_after"
            ),
            "review_not_after": _iso(review_not_after),
        }
    if review_not_after is not None:
        return {
            "status": "current",
            "current": True,
            "freshness_basis": (
                "source_review_not_after"
                if source.review_not_after
                else "theme_review_not_after"
            ),
            "review_not_after": _iso(review_not_after),
        }
    return {
        "status": "current",
        "current": True,
        "freshness_basis": "published_current_evaluation",
    }


def _source_identity(source: _SourceEvidence, *, state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_key": source.source_key,
        "role": source.role,
        "kol_id": source.kol_id,
        "publication_key": source.publication_key,
        "publication_state": source.publication_state,
        "publication_id": source.source_binding.get("publication_id"),
        "publication_version": source.source_binding.get("publication_version"),
        "report_id": source.report_id,
        "viewpoint_id": source.viewpoint_id,
        "evaluation_id": source.evaluation_id,
        "evaluation_status": source.evaluation_status,
        "source_published_at": source.source_published_at,
        "evaluated_at": source.evaluated_at,
        "review_not_after": state.get("review_not_after") or source.review_not_after,
        "evidence_sha256": source.source_binding.get("evidence_sha256"),
        "evidence_refs": [dict(ref) for ref in source.evidence_refs],
        "viewpoint_content_sha256": source.viewpoint_content_sha256,
        "manifest_sha256": source.manifest_sha256,
        "horizon": list(source.horizon),
        **dict(state),
    }


def _source_keys_for_theme(
    draft_theme: Mapping[str, Any],
    *,
    sources: list[_SourceEvidence],
) -> list[str]:
    explicit = [
        str(value).strip()
        for value in draft_theme.get("source_keys") or []
        if str(value).strip()
    ]
    if explicit:
        unknown = sorted(set(explicit) - {source.source_key for source in sources})
        if unknown:
            raise TrendSnapshotError(
                "agent draft references unknown source_keys: " + ", ".join(unknown)
            )
        return sorted(set(explicit))
    theme_id = str(draft_theme["theme_id"])
    by_theme = [source.source_key for source in sources if theme_id in source.theme_ids]
    if by_theme:
        return sorted(set(by_theme))
    return []


def _source_entry_for_role(
    raw_entry: Any,
    *,
    category: str,
    sources: Mapping[str, _SourceEvidence],
    states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if isinstance(raw_entry, str):
        source_key = raw_entry.strip()
        summary = ""
    elif isinstance(raw_entry, Mapping):
        source_key = str(raw_entry.get("source_key") or "").strip()
        summary = str(raw_entry.get("summary") or raw_entry.get("reason") or "").strip()
    else:
        raise TrendSnapshotError(f"other_kol.{category} entry is invalid")
    if source_key not in sources:
        raise TrendSnapshotError(f"other_kol.{category} references unknown source_key {source_key}")
    source = sources[source_key]
    if source.role != "other_kol":
        raise TrendSnapshotError(
            f"other_kol.{category} source {source_key} is not an other-KOL source"
        )
    return {
        "source_key": source_key,
        "summary": summary,
        "current": bool(states[source_key].get("current")),
        "status": states[source_key].get("status"),
        "freshness_basis": states[source_key].get("freshness_basis"),
        "source_evidence": _source_identity(source, state=states[source_key]),
    }


def _other_kol_projection(
    draft_theme: Mapping[str, Any],
    *,
    selected_sources: Mapping[str, _SourceEvidence],
    states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    projection = draft_theme.get("other_kol")
    projection = projection if isinstance(projection, Mapping) else {}
    output: dict[str, list[dict[str, Any]]] = {
        "confirmations": [],
        "conflicts": [],
        "falsifiers": [],
        "proposals": [],
        "observations": [],
    }
    categorized: set[str] = set()
    for category in output:
        raw_entries = projection.get(category) or []
        if not isinstance(raw_entries, list):
            raise TrendSnapshotError(f"agent_draft.other_kol.{category} must be a list")
        for raw_entry in raw_entries:
            entry = _source_entry_for_role(
                raw_entry,
                category=category,
                sources=selected_sources,
                states=states,
            )
            output[category].append(entry)
            categorized.add(entry["source_key"])
    for source_key, source in sorted(selected_sources.items()):
        if source.role != "other_kol" or source_key in categorized:
            continue
        output["observations"].append(
            _source_entry_for_role(
                source_key,
                category="observations",
                sources=selected_sources,
                states=states,
            )
        )
    return output


def _mache_projection(
    selected_sources: Mapping[str, _SourceEvidence],
    *,
    states: Mapping[str, Mapping[str, Any]],
    replaced_viewpoint_ids: set[str],
) -> dict[str, Any]:
    mache_sources = [source for source in selected_sources.values() if source.role == "mache"]
    active = [source for source in mache_sources if states[source.source_key].get("current")]
    expired = [
        source
        for source in mache_sources
        if states[source.source_key].get("status") == "expired"
    ]
    replaced = [source for source in mache_sources if source.viewpoint_id in replaced_viewpoint_ids]
    common = {
        "viewpoint_ids": [
            source.viewpoint_id
            for source in sorted(active, key=lambda item: item.viewpoint_id)
        ],
        "replaced_viewpoint_ids": sorted(
            source.viewpoint_id for source in replaced
        ),
        "source_evidence": [
            _source_identity(source, state=states[source.source_key])
            for source in sorted(mache_sources, key=lambda item: item.source_key)
        ],
    }
    if active:
        expiries = [
            states[source.source_key].get("review_not_after")
            for source in active
            if states[source.source_key].get("review_not_after")
        ]
        published = [source.source_published_at for source in active if source.source_published_at]
        return {
            "status": "active",
            "published_at": max(published) if published else None,
            "expires_not_after": min(expiries) if expiries else None,
            **common,
        }
    if expired:
        expiries = [
            states[source.source_key].get("review_not_after")
            for source in expired
            if states[source.source_key].get("review_not_after")
        ]
        return {
            "status": "expired",
            "published_at": max(
                (source.source_published_at for source in expired if source.source_published_at),
                default=None,
            ),
            "expires_not_after": min(expiries) if expiries else None,
            **common,
        }
    if replaced:
        return {"status": "replaced", "published_at": None, "expires_not_after": None, **common}
    if mache_sources:
        return {"status": "unavailable", "published_at": None, "expires_not_after": None, **common}
    return {
        "status": "none",
        "published_at": None,
        "expires_not_after": None,
        "viewpoint_ids": [],
        "replaced_viewpoint_ids": [],
        "source_evidence": [],
    }


def _theme_review_time(draft_theme: Mapping[str, Any]) -> datetime | None:
    value = draft_theme.get("review_not_after")
    if not value:
        return None
    return _parse_time(value, field="agent_draft.theme.review_not_after")


def _theme_sources(
    draft_theme: Mapping[str, Any],
    *,
    sources: list[_SourceEvidence],
) -> dict[str, _SourceEvidence]:
    selected_keys = _source_keys_for_theme(draft_theme, sources=sources)
    return {
        source.source_key: source
        for source in sources
        if source.source_key in selected_keys
    }


def _theme_source_states(
    selected_sources: Mapping[str, _SourceEvidence],
    *,
    as_of: datetime,
    theme_review_not_after: datetime | None,
    replaced_by: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    return {
        source_key: _source_status(
            source,
            as_of=as_of,
            replaced_by=replaced_by,
            theme_review_not_after=theme_review_not_after,
        )
        for source_key, source in selected_sources.items()
    }


def _theme_active_sources(
    selected_sources: Mapping[str, _SourceEvidence],
    *,
    states: Mapping[str, Mapping[str, Any]],
) -> tuple[list[_SourceEvidence], list[_SourceEvidence], list[_SourceEvidence]]:
    active = [
        source
        for source in selected_sources.values()
        if states[source.source_key].get("current")
    ]
    invalidated = [
        source
        for source in selected_sources.values()
        if states[source.source_key].get("status") == "invalidated"
    ]
    conflicted = [
        source
        for source in selected_sources.values()
        if states[source.source_key].get("status") == "conflicted"
    ]
    return active, invalidated, conflicted


def _theme_effective_from(
    draft_theme: Mapping[str, Any],
    *,
    as_of: datetime,
    active_sources: Iterable[_SourceEvidence],
) -> datetime:
    effective_value = draft_theme.get("effective_from")
    if effective_value:
        return _parse_time(effective_value, field="agent_draft.theme.effective_from")
    timestamps = [
        _parse_time(source.source_published_at, field="source_published_at")
        for source in active_sources
        if source.source_published_at
    ]
    return min(timestamps) if timestamps else as_of


def _theme_horizon(
    draft_theme: Mapping[str, Any],
    *,
    as_of: datetime,
    selected_sources: Mapping[str, _SourceEvidence],
    states: Mapping[str, Mapping[str, Any]],
    mache: Mapping[str, Any],
) -> tuple[datetime, str]:
    deadlines = [
        _parse_time(state["review_not_after"], field="source.review_not_after")
        for state in states.values()
        if state.get("review_not_after")
    ]
    review_time = _theme_review_time(draft_theme)
    if review_time is not None:
        deadlines.append(review_time)
    mache_expiry = mache.get("expires_not_after")
    if mache_expiry:
        deadlines.append(
            _parse_time(mache_expiry, field="mache_support.expires_not_after")
        )
    output_review_time = min(deadlines) if deadlines else as_of
    horizon_basis = str(draft_theme.get("horizon_basis") or "agent_declared_review")
    if mache.get("status") in {"active", "expired", "replaced"}:
        horizon_basis = f"{horizon_basis};mache_one_calendar_month_cap"
    if any(
        source.role == "other_kol" and not source.horizon
        for source in selected_sources.values()
    ):
        horizon_basis = f"{horizon_basis};missing_horizon_rapid_decay_1d"
    if any(
        source.role != "mache"
        and source.horizon
        and not source.review_not_after
        for source in selected_sources.values()
    ):
        horizon_basis = f"{horizon_basis};horizon_requires_machine_review_not_after"
    return output_review_time, horizon_basis


def _theme_timing(
    context: Mapping[str, Any],
    draft_theme: Mapping[str, Any],
) -> dict[str, Any]:
    timing = dict(context)
    draft_timing = draft_theme.get("xiaocao_timing")
    if isinstance(draft_timing, Mapping):
        if draft_timing.get("stance"):
            timing["stance"] = str(draft_timing["stance"]).strip()
        if draft_timing.get("timing_status"):
            timing["timing_status"] = str(draft_timing["timing_status"]).strip()
    return timing


def _theme_eligibility(
    draft_theme: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    timing: Mapping[str, Any],
    market_status: str,
    market_current: bool,
    active_sources: list[_SourceEvidence],
    invalidated_sources: list[_SourceEvidence],
    conflicted_sources: list[_SourceEvidence],
) -> tuple[str, str]:
    draft_eligibility = str(draft_theme.get("eligibility") or "wait")
    timing_status = str(timing.get("timing_status") or "").lower()
    if market_status == "invalidate":
        return "invalidated", "market_validation_invalidated"
    if draft_eligibility == "invalidated":
        return "invalidated", "agent_judgment_invalidated"
    if market_status == "conflict":
        return "conflicted", "market_validation_conflict"
    if draft_eligibility == "conflicted":
        return "conflicted", "agent_judgment_conflict"
    if invalidated_sources and not active_sources:
        return "invalidated", "all_bound_sources_invalidated"
    if conflicted_sources:
        return "conflicted", "bound_source_conflict"
    if not market_current:
        return "wait", "market_validation_not_current"
    if context.get("status") != "current":
        return "wait", "xiaocao_context_not_current"
    if timing_status in {"wait", "risk_off", "pause"}:
        return "wait", "xiaocao_timing_wait"
    if draft_eligibility == "wait":
        return "wait", "agent_judgment_wait"
    if not active_sources:
        return "wait", "no_current_bound_source"
    return "eligible", "all_phase_one_hard_gates_passed"


def _theme_payload(
    draft_theme: Mapping[str, Any],
    *,
    effective_from: datetime,
    review_not_after: datetime,
    horizon_basis: str,
    timing: Mapping[str, Any],
    mache: Mapping[str, Any],
    other_kol: Mapping[str, Any],
    market: Mapping[str, Any],
    eligibility: str,
    eligibility_reason: str,
    source_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "theme_id": str(draft_theme["theme_id"]),
        "display_name": str(draft_theme["display_name"]),
        "direction": str(draft_theme["direction"]),
        "confidence": float(draft_theme["confidence"]),
        "effective_from": _iso(effective_from),
        "review_not_after": _iso(review_not_after),
        "horizon": {
            "basis": horizon_basis,
            "review_not_after": _iso(review_not_after),
        },
        "horizon_basis": horizon_basis,
        "xiaocao_timing": dict(timing),
        "mache_support": dict(mache),
        "other_kol": dict(other_kol),
        "market_validation": dict(market),
        "eligibility": eligibility,
        "eligibility_reason": eligibility_reason,
        "source_evidence": source_evidence,
    }


def _build_theme(
    draft_theme: Mapping[str, Any],
    *,
    as_of: datetime,
    context: Mapping[str, Any],
    market_validation: Any,
    sources: list[_SourceEvidence],
    replaced_by: Mapping[str, str],
) -> dict[str, Any]:
    theme_id = str(draft_theme["theme_id"])
    selected = _theme_sources(draft_theme, sources=sources)
    review_time = _theme_review_time(draft_theme)
    states = _theme_source_states(
        selected,
        as_of=as_of,
        theme_review_not_after=review_time,
        replaced_by=replaced_by,
    )
    market, market_status, market_current = _market_for_theme(
        market_validation,
        theme_id=theme_id,
        as_of=as_of,
    )
    mache = _mache_projection(
        selected,
        states=states,
        replaced_viewpoint_ids=set(
            source.viewpoint_id
            for source in selected.values()
            if source.viewpoint_id in replaced_by
        ),
    )
    active_sources, invalidated_sources, conflicted_sources = _theme_active_sources(
        selected,
        states=states,
    )
    effective_from = _theme_effective_from(
        draft_theme,
        as_of=as_of,
        active_sources=active_sources,
    )
    output_review_time, horizon_basis = _theme_horizon(
        draft_theme,
        as_of=as_of,
        selected_sources=selected,
        states=states,
        mache=mache,
    )
    timing = _theme_timing(context, draft_theme)
    other_kol = _other_kol_projection(
        draft_theme,
        selected_sources=selected,
        states=states,
    )
    eligibility, eligibility_reason = _theme_eligibility(
        draft_theme,
        context=context,
        timing=timing,
        market_status=market_status,
        market_current=market_current,
        active_sources=active_sources,
        invalidated_sources=invalidated_sources,
        conflicted_sources=conflicted_sources,
    )
    source_states = {
        source_key: states[source_key] for source_key in sorted(states)
    }
    source_evidence = [
        _source_identity(source, state=source_states[source.source_key])
        for source in sorted(selected.values(), key=lambda item: item.source_key)
    ]
    return _theme_payload(
        draft_theme,
        effective_from=effective_from,
        review_not_after=output_review_time,
        horizon_basis=horizon_basis,
        timing=timing,
        mache=mache,
        other_kol=other_kol,
        market=market,
        eligibility=eligibility,
        eligibility_reason=eligibility_reason,
        source_evidence=source_evidence,
    )


def _normalize_sources(
    published_sources: Iterable[Any],
    *,
    as_of: datetime,
) -> list[_SourceEvidence]:
    if isinstance(published_sources, (str, bytes, Mapping)):
        raise TrendSnapshotError("published_sources must be a list of publication readbacks")
    try:
        raw_sources = list(published_sources)
    except TypeError as exc:
        raise TrendSnapshotError("published_sources must be iterable") from exc
    sources = [
        _normalize_source(raw, index=index, as_of=as_of)
        for index, raw in enumerate(raw_sources)
    ]
    keys = [source.source_key for source in sources]
    if len(keys) != len(set(keys)):
        raise TrendSnapshotError("published_sources contains duplicate source_key")
    return sorted(sources, key=lambda source: source.source_key)


def _replacement_index(sources: Iterable[_SourceEvidence]) -> dict[str, str]:
    replaced_by: dict[str, str] = {}
    for source in sources:
        for relation in source.relations:
            if relation.get("relation_type") != "replaces":
                continue
            old_id = str(relation.get("to_viewpoint_id") or "").strip()
            new_id = str(relation.get("from_viewpoint_id") or "").strip()
            if old_id and new_id:
                prior = replaced_by.get(old_id)
                if prior is None or new_id > prior:
                    replaced_by[old_id] = new_id
    return replaced_by


@dataclass(frozen=True)
class TrendJudgmentSnapshot(Mapping[str, Any]):
    """Immutable, hash-bound view of one Book T v2 judgment snapshot."""

    _canonical_payload: str
    snapshot_sha256: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "TrendJudgmentSnapshot":
        value = _canonical_json(payload)
        expected = str(value.get("snapshot_sha256") or "")
        if not expected:
            raise TrendSnapshotError("snapshot_sha256 is required")
        body = copy.deepcopy(value)
        body.pop("snapshot_sha256", None)
        receipt = body.get("binding_receipt")
        if isinstance(receipt, Mapping):
            receipt = dict(receipt)
            if receipt.get("snapshot_sha256") != expected:
                raise TrendSnapshotError(
                    "binding receipt snapshot hash does not match payload"
                )
            receipt.pop("snapshot_sha256", None)
            body["binding_receipt"] = receipt
        if canonical_sha256(body) != expected:
            raise TrendSnapshotError("snapshot hash does not match payload")
        return cls(
            _canonical_payload=json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            snapshot_sha256=expected,
        )

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self._canonical_payload)
        if not isinstance(value, dict):
            raise TrendSnapshotError("snapshot payload is not an object")
        return value

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __hash__(self) -> int:
        return hash(self.snapshot_sha256)


def build_trend_snapshot(
    as_of: str | date | datetime,
    *,
    published_sources: Iterable[Any] | None = None,
    publications: Iterable[Any] | None = None,
    published_publications: Iterable[Any] | None = None,
    xiaocao_context: Mapping[str, Any] | None = None,
    market_validation: Any = None,
    agent_draft: Mapping[str, Any] | None = None,
    generated_at: str | date | datetime | None = None,
    agent_judgment_version: str = AGENT_JUDGMENT_VERSION,
) -> TrendJudgmentSnapshot:
    """Build one frozen, evidence-bound Book T v2 judgment snapshot.

    ``publications`` and ``published_publications`` are compatibility aliases
    for callers migrating to the explicit ``published_sources`` name.  A
    source must contain a terminal ``publish_receipt`` and a complete hashed
    record manifest.  ``agent_draft`` may describe judgment, timing, and role
    projections, but identity, evidence, execution, and ledger fields are
    supplied by this deterministic builder and are rejected in the draft.
    """

    if published_sources is not None and (
        publications is not None or published_publications is not None
    ):
        raise TrendSnapshotError("provide only one published source collection")
    source_collection = published_sources
    if source_collection is None:
        source_collection = publications if publications is not None else published_publications
    if source_collection is None:
        source_collection = []
    as_of_label, as_of_dt = _normalize_as_of(as_of)
    draft = _validate_agent_draft(agent_draft or {"themes": []})
    sources = _normalize_sources(source_collection, as_of=as_of_dt)
    context = _normalize_context(xiaocao_context, as_of=as_of_dt)
    replaced_by = _replacement_index(sources)
    themes: list[dict[str, Any]] = []
    for draft_theme in draft["themes"]:
        themes.append(
            _build_theme(
                draft_theme,
                as_of=as_of_dt,
                context=context,
                market_validation=market_validation or {},
                sources=sources,
                replaced_by=replaced_by,
            )
        )
    themes.sort(key=lambda theme: theme["theme_id"])
    generated_dt = _parse_time(
        generated_at if generated_at is not None else as_of,
        field="generated_at",
        date_as_end=True,
    )
    if generated_dt < as_of_dt:
        raise TrendSnapshotError("generated_at cannot precede as_of")
    if not str(agent_judgment_version or "").strip():
        raise TrendSnapshotError("agent_judgment_version is required")
    source_summary = []
    for source in sources:
        source_summary.append(
            {
                "source_key": source.source_key,
                "role": source.role,
                "publication_key": source.publication_key,
                "publication_state": source.publication_state,
                "manifest_sha256": source.manifest_sha256,
                "report_id": source.report_id,
                "viewpoint_id": source.viewpoint_id,
                "evaluation_id": source.evaluation_id,
                "evaluation_status": source.evaluation_status,
                "source_published_at": source.source_published_at,
                "evaluated_at": source.evaluated_at,
                "review_not_after": source.review_not_after,
                "binding": source.source_binding,
                "evidence_refs": [dict(ref) for ref in source.evidence_refs],
                "theme_ids": list(source.theme_ids),
                "horizon": list(source.horizon),
            }
        )
    input_summary = {
        "as_of": as_of_label,
        "published_sources": source_summary,
        "xiaocao_context": context,
        "market_validation": market_validation or {},
        "agent_draft": draft,
    }
    _ensure_json_safe(input_summary, field="snapshot inputs")
    input_summary_sha = canonical_sha256(_canonical_json(input_summary))
    base_receipt = {
        "schema_version": 1,
        "status": "validated",
        "input_summary_sha256": input_summary_sha,
        "validated_at": _iso(generated_dt),
        "source_count": len(sources),
    }
    body: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "as_of": as_of_label,
        "generated_at": _iso(generated_dt),
        "agent_judgment_version": str(agent_judgment_version).strip(),
        "input_summary_sha256": input_summary_sha,
        "themes": themes,
        "binding_receipt": base_receipt,
    }
    snapshot_sha = canonical_sha256(body)
    payload = {
        **body,
        "snapshot_sha256": snapshot_sha,
        "binding_receipt": {**base_receipt, "snapshot_sha256": snapshot_sha},
    }
    return TrendJudgmentSnapshot.from_payload(payload)


__all__ = [
    "AGENT_JUDGMENT_VERSION",
    "PublicationBindingError",
    "TrendJudgmentSnapshot",
    "TrendSnapshotError",
    "build_trend_snapshot",
]
