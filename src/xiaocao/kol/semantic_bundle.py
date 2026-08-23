"""Canonical semantic bundle construction and validation.

The semantic boundary is deliberately small: source adapters own evidence and
business identities, while the agent supplies only the current judgment.  A
validated artifact and its receipt are written before a consumer is allowed to
prepare or claim an external effect.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ._shared import DecisionError, canonical
from .claim_coverage import (
    CONTRACT_VERSION,
    build_claim_extraction_request,
    evidence_segments,
    validate_claim_coverage,
)
from .enrichment_types import EnrichmentError
from .reader_copy import (
    ReaderCopyError,
    validate_reader_payload,
    validate_reader_source_identity,
)
from .rendering import reader_source_title


BUNDLE_SCHEMA_VERSION = 2
VALIDATOR_VERSION = "kol-semantic-bundle-v5"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_DECISION_STATUSES = {"actionable_signal", "no_actionable_signal"}
_KNOWLEDGE_STATUSES = {"reusable_knowledge", "no_reusable_knowledge"}
_CONTENT_STATUSES = {"low_density", "promoted"}
_CONTENT_TIERS = {"report_only", "alert_eligible"}
_ALERT_BASES = {
    "market_posture",
    "buy",
    "sell",
    "hold",
    "position_boundary",
    "direction",
    "actionable_trigger",
}
_PROJECTION_STATUSES = {"none", "promoted"}
_MARKET_STATUSES = {"support", "qualify", "conflict", "invalidate"}
_ACTIONS = {"buy", "add", "hold", "reduce", "sell", "wait"}

# These values are owned by the request or by a business terminal.  Allowing
# them in the draft would let an analyst silently switch evidence, create a
# second segment algorithm, or mint a second external identity.
_PROTECTED_DRAFT_FIELDS = {
    "schema_version",
    "validator_version",
    "bundle_sha256",
    "bundle_path",
    "validated_bundle_path",
    "receipt_path",
    "validated_bundle_receipt_path",
    "receipt_sha256",
    "evidence_path",
    "evidence_sha256",
    "original_evidence_path",
    "original_evidence_sha256",
    "transcript_path",
    "transcript_sha256",
    "message_sha256",
    "content_sha256",
    "handoff_id",
    "message_id",
    "media_sha256",
    "media_identity",
    "source_identity",
    "source_version_key",
    "full_contract_path",
    "full_contract_sha256",
    "source",
    "author",
    "title",
    "published_at",
    "published_at_basis",
    "source_modified_at",
    "captured_at",
    "first_observed_at",
    "media_type",
    "source_path",
    "publication_version",
    "identity",
    "version_key",
    "segment_ids",
    "segments",
    "market_evidence",
    "extraction_contract_version",
    "idempotency_key",
    "publication_id",
    "report_id",
    "recipient_id",
    "ack_id",
    "bundle",
    "items",
    "prior_bundle",
    "existing_bundle",
    "household_context_provider",
}
_REQUEST_METADATA_FIELDS = {
    "source",
    "author",
    "title",
    "published_at",
    "published_at_basis",
    "source_modified_at",
    "captured_at",
    "first_observed_at",
    "media_type",
    "source_path",
    "publication_version",
}
_EPISODE_RELATIONSHIP_SOURCE_BINDING_PATH = (
    "episode_relationship",
    "related_source_part",
)


class SemanticBundleError(EnrichmentError):
    """Credential-safe, stable failure from the canonical semantic seam."""

    def __init__(
        self,
        safe_reason: str,
        *,
        error_code: str,
        stage: str,
        category: str = "semantic",
        retryability: str = "not_retryable",
        field: str | None = None,
    ) -> None:
        self.category = category
        self.error_code = error_code
        self.stage = stage
        self.safe_reason = safe_reason
        self.retryability = retryability
        self.field = field
        super().__init__(safe_reason)

    @property
    def diagnostic_category(self) -> str:
        return self.category

    @property
    def diagnostic_code(self) -> str:
        return self.error_code

    @property
    def diagnostic_stage(self) -> str:
        return self.stage

    def to_dict(self) -> dict[str, Any]:
        value = {
            "category": self.category,
            "error_code": self.error_code,
            "stage": self.stage,
            "safe_reason": self.safe_reason,
            "retryability": self.retryability,
        }
        if self.field:
            value["field"] = self.field
        return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_canonical(value: Any) -> str:
    return _sha256_bytes(canonical(value).encode("utf-8"))


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".partial",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (canonical(value) + "\n").encode("utf-8"),
    )


def _fail(
    safe_reason: str,
    *,
    error_code: str,
    stage: str,
    field: str | None = None,
) -> SemanticBundleError:
    return SemanticBundleError(
        safe_reason,
        error_code=error_code,
        stage=stage,
        field=field,
    )


def _nonblank(value: Any) -> bool:
    return bool(str(value or "").strip())


def _require_sha(value: Any, *, code: str, stage: str, field: str) -> str:
    result = str(value or "")
    if not _SHA256.fullmatch(result):
        raise _fail(
            f"semantic binding {field} is invalid",
            error_code=code,
            stage=stage,
            field=field,
        )
    return result


def _read_evidence(request: Mapping[str, Any]) -> tuple[Path, str, str]:
    path_value = request.get("evidence_path") or request.get("transcript_path")
    path = Path(str(path_value or "")).expanduser().resolve()
    expected = str(
        request.get("evidence_sha256") or request.get("transcript_sha256") or ""
    )
    if not path.is_file():
        raise _fail(
            "semantic evidence is missing",
            error_code="evidence_missing",
            stage="evidence_binding",
            field="evidence_path",
        )
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(
            "semantic evidence is not valid UTF-8",
            error_code="evidence_invalid",
            stage="evidence_binding",
            field="evidence_path",
        ) from exc
    actual = _sha256_bytes(raw)
    if actual != expected:
        raise _fail(
            "semantic evidence hash does not match request",
            error_code="evidence_binding_mismatch",
            stage="evidence_binding",
            field="evidence_sha256",
        )
    return path, actual, text


def _market_projection(request: Mapping[str, Any], draft: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    raw = request.get("market_evidence")
    if not isinstance(raw, dict):
        raise _fail(
            "current market evidence is required",
            error_code="market_evidence_missing",
            stage="market_validation",
            field="market_evidence",
        )
    supplied_sha = (
        raw.get("sha256")
        or raw.get("evidence_sha256")
        or raw.get("market_evidence_sha256")
        or request.get("market_evidence_sha256")
    )
    market_payload = {
        key: value
        for key, value in raw.items()
        if key not in {"sha256", "evidence_sha256", "market_evidence_sha256"}
    }
    market_sha = (
        str(supplied_sha)
        if supplied_sha
        else _sha256_canonical(market_payload)
    )
    _require_sha(
        market_sha,
        code="market_evidence_invalid",
        stage="market_validation",
        field="market_evidence.sha256",
    )
    projection = raw.get("validation") or raw.get("projection") or raw.get("market_validation")
    if projection is None:
        projection = market_payload
    if not isinstance(projection, dict):
        raise _fail(
            "current market evidence projection is invalid",
            error_code="market_evidence_invalid",
            stage="market_validation",
            field="market_evidence",
        )
    draft_market = draft.get("market_validation")
    if draft_market is not None:
        if draft_market != projection:
            raise _fail(
                "semantic draft duplicates a different market projection",
                error_code="market_projection_mismatch",
                stage="market_validation",
                field="market_validation",
            )
        raise _fail(
            "semantic draft repeats the canonical market projection",
            error_code="market_projection_duplicate",
            stage="market_validation",
            field="market_validation",
        )
    outlook = draft.get("market_outlook")
    if isinstance(outlook, dict) and outlook.get("current_validation") is not None:
        if outlook["current_validation"] != projection:
            raise _fail(
                "market validation and market outlook projection disagree",
                error_code="market_projection_mismatch",
                stage="market_validation",
                field="market_outlook.current_validation",
            )
        raise _fail(
            "semantic draft repeats the canonical market projection",
            error_code="market_projection_duplicate",
            stage="market_validation",
            field="market_outlook.current_validation",
        )
    for signal in draft.get("actionable_signals") or []:
        if isinstance(signal, dict) and signal.get("current_validation") is not None:
            if signal["current_validation"] != projection:
                raise _fail(
                    "actionable signal market projection disagrees",
                    error_code="market_projection_mismatch",
                    stage="market_validation",
                    field="actionable_signals.current_validation",
                )
            raise _fail(
                "semantic draft repeats the canonical market projection",
                error_code="market_projection_duplicate",
                stage="market_validation",
                field="actionable_signals.current_validation",
            )
    return dict(projection), market_sha


def _validate_market(value: Mapping[str, Any]) -> None:
    if value.get("status") not in _MARKET_STATUSES:
        raise _fail(
            "market validation status is invalid",
            error_code="market_validation_invalid",
            stage="market_validation",
            field="market_validation.status",
        )
    for field in ("as_of", "summary"):
        if not _nonblank(value.get(field)):
            raise _fail(
                "market validation is incomplete",
                error_code="market_validation_incomplete",
                stage="market_validation",
                field=f"market_validation.{field}",
            )
    try:
        parsed_as_of = datetime.fromisoformat(str(value["as_of"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail(
            "market validation timestamp is invalid",
            error_code="market_validation_invalid",
            stage="market_validation",
            field="market_validation.as_of",
        ) from exc
    if parsed_as_of.tzinfo is None:
        raise _fail(
            "market validation timestamp has no timezone",
            error_code="market_validation_invalid",
            stage="market_validation",
            field="market_validation.as_of",
        )
    currentness = value.get("currentness")
    if (
        not isinstance(currentness, dict)
        or currentness.get("latest_available") is not True
        or not _nonblank(currentness.get("checked_at"))
        or not _nonblank(currentness.get("reason"))
    ):
        raise _fail(
            "market validation currentness is incomplete",
            error_code="market_validation_incomplete",
            stage="market_validation",
            field="market_validation.currentness",
        )
    try:
        checked_at = datetime.fromisoformat(
            str(currentness["checked_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise _fail(
            "market validation currentness timestamp is invalid",
            error_code="market_validation_invalid",
            stage="market_validation",
            field="market_validation.currentness.checked_at",
        ) from exc
    if checked_at.tzinfo is None:
        raise _fail(
            "market validation currentness timestamp has no timezone",
            error_code="market_validation_invalid",
            stage="market_validation",
            field="market_validation.currentness.checked_at",
        )
    facts = value.get("facts")
    if not isinstance(facts, list) or not facts:
        raise _fail(
            "market validation facts are incomplete",
            error_code="market_validation_incomplete",
            stage="market_validation",
            field="market_validation.facts",
        )
    for fact in facts:
        if not isinstance(fact, dict) or any(
            not _nonblank(fact.get(field))
            for field in ("metric", "value", "observed_at", "evidence")
        ):
            raise _fail(
                "market validation fact is incomplete",
                error_code="market_validation_incomplete",
                stage="market_validation",
                field="market_validation.facts",
            )
        try:
            observed_at = datetime.fromisoformat(
                str(fact["observed_at"]).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise _fail(
                "market validation fact timestamp is invalid",
                error_code="market_validation_invalid",
                stage="market_validation",
                field="market_validation.facts.observed_at",
            ) from exc
        if observed_at.tzinfo is None:
            raise _fail(
                "market validation fact timestamp has no timezone",
                error_code="market_validation_invalid",
                stage="market_validation",
                field="market_validation.facts.observed_at",
            )
        if observed_at > checked_at:
            raise _fail(
                "market validation fact is future-dated at validation time",
                error_code="market_validation_invalid",
                stage="market_validation",
                field="market_validation.facts.observed_at",
            )


def _validate_coverage(item: dict[str, Any], text: str) -> None:
    coverage = item.get("trade_information_coverage")
    required = {
        "todays_market_diagnosis",
        "next_session_playbook",
        "next_several_session_base_case",
        "style_market_cap_regime",
        "market_board_sector_hierarchy",
        "position_risk_budget",
        "named_asset_inventory",
    }
    if not isinstance(coverage, dict) or set(coverage) != required:
        raise _fail(
            "trade-information coverage is incomplete",
            error_code="coverage_incomplete",
            stage="coverage",
            field="trade_information_coverage",
        )
    for name, row in coverage.items():
        if not isinstance(row, dict) or row.get("status") not in {"present", "absent"}:
            raise _fail(
                "trade-information coverage row is invalid",
                error_code="coverage_invalid",
                stage="coverage",
                field=f"trade_information_coverage.{name}",
            )
        if row["status"] == "absent":
            if not _nonblank(row.get("reason")):
                raise _fail(
                    "absent coverage row needs a reason",
                    error_code="coverage_invalid",
                    stage="coverage",
                    field=f"trade_information_coverage.{name}",
                )
            continue
        quotes = row.get("evidence_quotes")
        if not isinstance(quotes, list) or not quotes or any(
            not isinstance(quote, str) or not quote.strip() or quote not in text
            for quote in quotes
        ):
            raise _fail(
                "coverage quotes are not evidence-bound",
                error_code="coverage_not_evidence_bound",
                stage="coverage",
                field=f"trade_information_coverage.{name}",
            )
        for field in ("reader_meaning", "horizon"):
            if not _nonblank(row.get(field)):
                raise _fail(
                    "coverage row is missing reader meaning",
                    error_code="coverage_invalid",
                    stage="coverage",
                    field=f"trade_information_coverage.{name}.{field}",
                )
        for field in ("triggers", "falsifiers"):
            values = row.get(field)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise _fail(
                    "coverage row is missing triggers or falsifiers",
                    error_code="coverage_invalid",
                    stage="coverage",
                    field=f"trade_information_coverage.{name}.{field}",
                )
    inventory = coverage["named_asset_inventory"].get("assets")
    if not isinstance(inventory, list):
        raise _fail(
            "named-asset inventory is invalid",
            error_code="coverage_invalid",
            stage="coverage",
            field="trade_information_coverage.named_asset_inventory.assets",
        )
    for asset in inventory:
        if not isinstance(asset, dict) or any(
            not _nonblank(asset.get(field))
            for field in ("surface_form", "role", "resolution_status")
        ):
            raise _fail(
                "named-asset row is invalid",
                error_code="coverage_invalid",
                stage="coverage",
                field="trade_information_coverage.named_asset_inventory.assets",
            )
        if asset["resolution_status"] == "resolved":
            if not _nonblank(asset.get("official_name")) or not _nonblank(asset.get("market")):
                raise _fail(
                    "resolved named asset is incomplete",
                    error_code="coverage_invalid",
                    stage="coverage",
                    field="trade_information_coverage.named_asset_inventory.assets",
                )
        elif not _nonblank(asset.get("exclusion_reason")):
            raise _fail(
                "unresolved named asset needs a reason",
                error_code="coverage_invalid",
                stage="coverage",
                field="trade_information_coverage.named_asset_inventory.assets",
            )


def _validate_projection(item: dict[str, Any]) -> None:
    content = item.get("content_value") or {}
    projection = item.get("longitudinal_projection")
    if not isinstance(projection, dict):
        raise _fail(
            "promoted content needs a longitudinal projection",
            error_code="longitudinal_projection_missing",
            stage="longitudinal_projection",
            field="longitudinal_projection",
        )
    status = projection.get("status")
    if status == "candidate":
        raise _fail(
            "candidate longitudinal projection is not a terminal decision",
            error_code="longitudinal_projection_candidate",
            stage="longitudinal_projection",
            field="longitudinal_projection.status",
        )
    if status not in _PROJECTION_STATUSES or not _nonblank(projection.get("reason")):
        raise _fail(
            "longitudinal projection status is invalid",
            error_code="longitudinal_projection_invalid",
            stage="longitudinal_projection",
            field="longitudinal_projection.status",
        )
    if content.get("status") == "low_density" and status != "none":
        raise _fail(
            "low-density content cannot create a longitudinal viewpoint",
            error_code="longitudinal_projection_invalid",
            stage="longitudinal_projection",
            field="longitudinal_projection.status",
        )
    viewpoints = projection.get("viewpoints")
    if not isinstance(viewpoints, list):
        raise _fail(
            "longitudinal viewpoints must be a list",
            error_code="longitudinal_projection_invalid",
            stage="longitudinal_projection",
            field="longitudinal_projection.viewpoints",
        )
    if status == "none" and viewpoints:
        raise _fail(
            "none longitudinal projection cannot contain viewpoints",
            error_code="longitudinal_projection_invalid",
            stage="longitudinal_projection",
            field="longitudinal_projection.viewpoints",
        )
    if content.get("status") == "promoted" and status == "promoted" and not viewpoints:
        raise _fail(
            "promoted content needs at least one longitudinal viewpoint",
            error_code="longitudinal_projection_invalid",
            stage="longitudinal_projection",
            field="longitudinal_projection.viewpoints",
        )
    if status == "promoted":
        try:
            evaluated_at = datetime.fromisoformat(
                str(projection.get("evaluated_at") or "").replace(
                    "Z", "+00:00"
                )
            )
        except ValueError as exc:
            raise _fail(
                "longitudinal projection timestamp is invalid",
                error_code="longitudinal_projection_invalid",
                stage="longitudinal_projection",
                field="longitudinal_projection.evaluated_at",
            ) from exc
        if evaluated_at.tzinfo is None:
            raise _fail(
                "longitudinal projection timestamp has no timezone",
                error_code="longitudinal_projection_invalid",
                stage="longitudinal_projection",
                field="longitudinal_projection.evaluated_at",
            )
        claims = {
            str(row.get("claim_id"))
            for row in item.get("claims") or []
            if isinstance(row, dict) and _nonblank(row.get("claim_id"))
        }
        local_ids: set[str] = set()
        for viewpoint in viewpoints:
            if not isinstance(viewpoint, dict):
                raise _fail(
                    "longitudinal viewpoint is invalid",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                )
            local_id = str(viewpoint.get("local_thesis_id") or "")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", local_id) or local_id in local_ids:
                raise _fail(
                    "longitudinal viewpoint identity is invalid",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                    field="longitudinal_projection.viewpoints.local_thesis_id",
                )
            local_ids.add(local_id)
            if any(not _nonblank(viewpoint.get(field)) for field in ("subject", "stance", "horizon", "reasoning")):
                raise _fail(
                    "longitudinal viewpoint meaning is incomplete",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                )
            refs = viewpoint.get("evidence_refs")
            if not isinstance(refs, list) or not refs:
                raise _fail(
                    "longitudinal viewpoint evidence is missing",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                )
            if any(
                not isinstance(ref, dict)
                or str(ref.get("claim_id") or "") not in claims
                or not _nonblank(ref.get("excerpt"))
                for ref in refs
            ):
                raise _fail(
                    "longitudinal viewpoint evidence is not claim-bound",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                )
            evaluation = viewpoint.get("evaluation")
            if not isinstance(evaluation, dict) or evaluation.get("status") not in {
                "current",
                "expired",
                "invalidated",
                "uncertain",
            }:
                raise _fail(
                    "longitudinal viewpoint evaluation is invalid",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                )
            if not _nonblank(evaluation.get("basis")):
                raise _fail(
                    "longitudinal viewpoint evaluation basis is missing",
                    error_code="longitudinal_projection_invalid",
                    stage="longitudinal_projection",
                    field="longitudinal_projection.viewpoints.evaluation.basis",
                )


def _validate_actionable_signals(
    item: Mapping[str, Any],
    market: Mapping[str, Any],
) -> None:
    claim_ids = {
        str(row.get("claim_id"))
        for row in item.get("claims") or []
        if isinstance(row, dict) and _nonblank(row.get("claim_id"))
    }
    signals = item.get("actionable_signals")
    if not isinstance(signals, list):
        raise _fail(
            "actionable signals must be a list",
            error_code="decision_semantics_invalid",
            stage="semantic_validation",
            field="actionable_signals",
        )
    if item.get("decision_status") == "actionable_signal" and not signals:
        raise _fail(
            "actionable decision needs at least one signal",
            error_code="decision_semantics_invalid",
            stage="semantic_validation",
            field="actionable_signals",
        )
    if item.get("decision_status") == "no_actionable_signal" and signals:
        raise _fail(
            "no-action decision cannot contain actionable signals",
            error_code="decision_semantics_invalid",
            stage="semantic_validation",
            field="actionable_signals",
        )
    for signal in signals:
        if not isinstance(signal, dict) or signal.get("action") not in _ACTIONS:
            raise _fail(
                "actionable signal action is invalid",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals.action",
            )
        linked = signal.get("claim_ids")
        if not isinstance(linked, list) or not linked or not set(map(str, linked)).issubset(claim_ids):
            raise _fail(
                "actionable signal claims are invalid",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals.claim_ids",
            )
        assets = signal.get("assets")
        if not isinstance(assets, list) or not assets:
            raise _fail(
                "actionable signal assets are missing",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals.assets",
            )
        if any(
            not isinstance(asset, dict)
            or not _nonblank(asset.get("name"))
            or not _nonblank(asset.get("market"))
            or not (_nonblank(asset.get("ticker")) or _nonblank(asset.get("theme")))
            for asset in assets
        ):
            raise _fail(
                "actionable signal asset is incomplete",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals.assets",
            )
        if any(not _nonblank(signal.get(field)) for field in ("horizon", "execution", "trigger", "confidence")):
            raise _fail(
                "actionable signal is incomplete",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals",
            )
        rationale = signal.get("rationale")
        if not isinstance(rationale, dict) or any(
            not isinstance(rationale.get(field), list)
            for field in ("news_or_event", "fundamental", "trading")
        ) or not any(rationale.get(field) for field in ("news_or_event", "fundamental", "trading")):
            raise _fail(
                "actionable signal rationale is incomplete",
                error_code="decision_semantics_invalid",
                stage="semantic_validation",
                field="actionable_signals.rationale",
            )
        if signal.get("current_validation") != market:
            raise _fail(
                "actionable signal is not projected from canonical market evidence",
                error_code="market_projection_mismatch",
                stage="market_validation",
                field="actionable_signals.current_validation",
            )


def _validate_market_outlook(
    item: Mapping[str, Any],
    market: Mapping[str, Any],
) -> None:
    outlook = item.get("market_outlook")
    if not isinstance(outlook, dict):
        raise _fail(
            "market outlook is missing",
            error_code="market_outlook_invalid",
            stage="market_validation",
            field="market_outlook",
        )
    claim_ids = {
        str(row.get("claim_id"))
        for row in item.get("claims") or []
        if isinstance(row, dict) and _nonblank(row.get("claim_id"))
    }
    linked = outlook.get("claim_ids")
    if linked is not None and (
        not isinstance(linked, list) or not set(map(str, linked)).issubset(claim_ids)
    ):
        raise _fail(
            "market outlook claims are invalid",
            error_code="market_outlook_invalid",
            stage="market_validation",
            field="market_outlook.claim_ids",
        )
    for field in ("scope", "current_phase", "base_case", "horizon", "confidence"):
        if not _nonblank(outlook.get(field)):
            raise _fail(
                "market outlook is incomplete",
                error_code="market_outlook_invalid",
                stage="market_validation",
                field=f"market_outlook.{field}",
            )
    if outlook.get("confidence") not in {"low", "medium", "high"}:
        raise _fail(
            "market outlook confidence is invalid",
            error_code="market_outlook_invalid",
            stage="market_validation",
            field="market_outlook.confidence",
        )
    for field in ("strategy", "turning_points", "falsifiers"):
        values = outlook.get(field)
        if not isinstance(values, list) or not values or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise _fail(
                "market outlook lists are incomplete",
                error_code="market_outlook_invalid",
                stage="market_validation",
                field=f"market_outlook.{field}",
            )
    if outlook.get("current_validation") != market:
        raise _fail(
            "market outlook is not projected from canonical market evidence",
            error_code="market_projection_mismatch",
            stage="market_validation",
            field="market_outlook.current_validation",
        )


def _validate_decision_and_knowledge(item: Mapping[str, Any]) -> str:
    decision_status = item.get("decision_status")
    if decision_status not in _DECISION_STATUSES:
        raise _fail(
            "decision status is invalid",
            error_code="decision_status_invalid",
            stage="semantic_validation",
            field="decision_status",
        )
    knowledge_status = item.get("knowledge_status")
    if knowledge_status not in _KNOWLEDGE_STATUSES:
        raise _fail(
            "knowledge status is invalid",
            error_code="knowledge_status_invalid",
            stage="knowledge",
            field="knowledge_status",
        )
    if knowledge_status == "no_reusable_knowledge" and not _nonblank(item.get("knowledge_reason")):
        raise _fail(
            "knowledge branch needs a reason",
            error_code="knowledge_branch_invalid",
            stage="knowledge",
            field="knowledge_reason",
        )
    if knowledge_status == "reusable_knowledge":
        knowledge = item.get("knowledge") or {}
        if not isinstance(knowledge, dict) or not _nonblank(
            knowledge.get("summary")
        ):
            raise _fail(
                "reusable knowledge branch is incomplete",
                error_code="knowledge_branch_invalid",
                stage="knowledge",
            )
        distillation_value = str(
            item.get("durable_distillation_path") or ""
        ).strip()
        if not distillation_value:
            raise _fail(
                "reusable knowledge requires a durable distillation file",
                error_code="knowledge_distillation_missing",
                stage="knowledge",
                field="durable_distillation_path",
            )
        distillation_path = Path(distillation_value).expanduser().resolve()
        expected_sha = str(
            item.get("durable_distillation_sha256") or ""
        ).strip()
        try:
            distillation_bytes = distillation_path.read_bytes()
            distillation = json.loads(distillation_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _fail(
                "reusable knowledge durable distillation is invalid",
                error_code="knowledge_distillation_invalid",
                stage="knowledge",
                field="durable_distillation_path",
            ) from exc
        if not isinstance(distillation, dict):
            raise _fail(
                "reusable knowledge durable distillation is invalid",
                error_code="knowledge_distillation_invalid",
                stage="knowledge",
                field="durable_distillation_path",
            )
        actual_sha = hashlib.sha256(distillation_bytes).hexdigest()
        if not _SHA256.fullmatch(expected_sha) or expected_sha != actual_sha:
            raise _fail(
                "reusable knowledge durable distillation changed",
                error_code="knowledge_distillation_invalid",
                stage="knowledge",
                field="durable_distillation_sha256",
            )
    return str(decision_status)


def _validate_content_routing(item: Mapping[str, Any]) -> dict[str, Any]:
    content = item.get("content_value")
    if not isinstance(content, dict) or content.get("status") not in _CONTENT_STATUSES:
        raise _fail(
            "content value status is invalid",
            error_code="content_value_invalid",
            stage="content_routing",
            field="content_value.status",
        )
    if not _nonblank(content.get("reason")):
        raise _fail(
            "content value needs a terminal reason",
            error_code="content_value_invalid",
            stage="content_routing",
            field="content_value.reason",
        )
    if content["status"] == "promoted":
        tier = content.get("tier")
        if tier not in _CONTENT_TIERS:
            raise _fail(
                "promoted content tier is invalid",
                error_code="content_value_invalid",
                stage="content_routing",
                field="content_value.tier",
            )
        if tier == "report_only" and not _nonblank(
            content.get("no_alert_reason") or content.get("reason")
        ):
            raise _fail(
                "report-only content needs a no-alert reason",
                error_code="content_value_invalid",
                stage="content_routing",
                field="content_value.no_alert_reason",
            )
        if tier == "alert_eligible":
            alert_basis = content.get("alert_basis")
            if (
                not isinstance(alert_basis, list)
                or not alert_basis
                or not set(str(value) for value in alert_basis) <= _ALERT_BASES
            ):
                raise _fail(
                    "alert-eligible content needs a supported alert basis",
                    error_code="content_value_invalid",
                    stage="content_routing",
                    field="content_value.alert_basis",
                )
        publication = item.get("publication")
        if not isinstance(publication, dict) or any(
            not _nonblank(publication.get(field))
            for field in ("summary", "report_body")
        ):
            raise _fail(
                "promoted content needs reviewed publication copy",
                error_code="reader_copy_invalid",
                stage="reader_copy",
                field="publication",
            )
    return content


def _validate_reader_copy(item: Mapping[str, Any], decision_status: str) -> None:
    raw_insight = item.get("reader_insight")
    if raw_insight is not None and not isinstance(raw_insight, Mapping):
        raise _fail(
            "reader insight must be an object",
            error_code="reader_insight_invalid",
            stage="reader_copy",
            field="reader_insight",
        )
    insight = raw_insight or {}
    if insight or decision_status == "no_actionable_signal":
        if insight.get("status") not in {"useful", "none"}:
            raise _fail(
                "reader insight needs a useful or none status",
                error_code="reader_insight_invalid",
                stage="reader_copy",
                field="reader_insight.status",
            )
        required = ("summary", "boundary") if insight["status"] == "useful" else ("reason",)
        if any(not _nonblank(insight.get(field)) for field in required):
            raise _fail(
                "reader insight is incomplete",
                error_code="reader_insight_invalid",
                stage="reader_copy",
                field="reader_insight",
            )
    raw_reminder = item.get("reader_reminder")
    if raw_reminder is not None:
        if not isinstance(raw_reminder, Mapping):
            raise _fail(
                "reader reminder must be an object",
                error_code="reader_copy_invalid",
                stage="reader_copy",
                field="reader_reminder",
            )
        if any(
            not _nonblank(raw_reminder.get(field))
            for field in ("title", "summary")
        ):
            raise _fail(
                "reader reminder requires title and summary",
                error_code="reader_copy_invalid",
                stage="reader_copy",
                field="reader_reminder",
            )
    publication = item.get("publication") or {}
    if isinstance(publication, Mapping) and publication:
        try:
            validate_reader_payload(
                "report",
                {
                    "author": item.get("author"),
                    "title": reader_source_title(dict(item)),
                    "summary": publication.get("summary"),
                    "report_body": publication.get("report_body"),
                },
            )
        except ReaderCopyError as exc:
            raise _fail(
                str(exc),
                error_code="reader_copy_invalid",
                stage="reader_copy",
                field="publication",
            ) from exc
        try:
            validate_reader_source_identity(
                source_name=Path(str(item.get("evidence_path") or "")).name,
                reader_title=reader_source_title(dict(item)),
                report_body=publication.get("report_body"),
            )
        except ReaderCopyError as exc:
            raise _fail(
                str(exc),
                error_code="reader_source_identity_invalid",
                stage="reader_copy",
                field="reader_title",
            ) from exc


def _validate_household_recommendation(item: Mapping[str, Any]) -> None:
    recommendation = item.get("household_recommendation") or {}
    if recommendation.get("action") not in _ACTIONS or any(
        not _nonblank(recommendation.get(field))
        for field in ("evidence", "confidence", "horizon", "falsifier")
    ):
        raise _fail(
            "household recommendation is incomplete",
            error_code="reader_copy_invalid",
            stage="reader_copy",
            field="household_recommendation",
        )


def _validate_synthesis(item: Mapping[str, Any]) -> None:
    synthesis = item.get("synthesis") or {}
    if not isinstance(synthesis, dict) or any(
        not _nonblank(synthesis.get(field))
        for field in ("summary", "confidence")
    ) or synthesis.get("confidence") not in {"low", "medium", "high"}:
        raise _fail(
            "system synthesis is incomplete",
            error_code="reader_copy_invalid",
            stage="reader_copy",
            field="synthesis",
        )
    if synthesis.get("reader_render_mode") != "kol_context_corrected":
        return
    claims_by_id = {
        str(claim.get("claim_id")): claim
        for claim in item.get("claims") or []
        if isinstance(claim, Mapping)
    }
    reader_quote_ids = synthesis.get("reader_quote_ids")
    normalized_reader_quote_ids = (
        [str(claim_id) for claim_id in reader_quote_ids]
        if isinstance(reader_quote_ids, list)
        else []
    )
    if (
        not isinstance(reader_quote_ids, list)
        or not reader_quote_ids
        or len(normalized_reader_quote_ids)
        != len(set(normalized_reader_quote_ids))
        or any(
            claim_id not in claims_by_id
            for claim_id in normalized_reader_quote_ids
        )
    ):
        raise _fail(
            "context-corrected synthesis requires unique valid reader quote ids",
            error_code="reader_copy_invalid",
            stage="reader_copy",
            field="synthesis.reader_quote_ids",
        )
    if any(
        not _nonblank(claims_by_id[claim_id].get("reader_quote"))
        for claim_id in normalized_reader_quote_ids
    ):
        raise _fail(
            "context-corrected synthesis requires every reader quote",
            error_code="reader_copy_invalid",
            stage="reader_copy",
            field="claims.reader_quote",
        )
    if (
        not isinstance(synthesis.get("analysis_points"), list)
        or not synthesis["analysis_points"]
        or any(
            not isinstance(value, str) or not value.strip()
            for value in synthesis["analysis_points"]
        )
        or not _nonblank(synthesis.get("system_check"))
        or not _nonblank(synthesis.get("system_advice"))
    ):
        raise _fail(
            "context-corrected synthesis requires analysis, check, and advice",
            error_code="reader_copy_invalid",
            stage="reader_copy",
            field="synthesis.analysis_points",
        )


def _validate_book_intent(item: Mapping[str, Any]) -> None:
    book = item.get("book_kol_us")
    if not isinstance(book, dict) or book.get("book") != "KOL-US" or book.get("paper_only") is not True:
        raise _fail(
            "Book KOL-US intent is not paper-only",
            error_code="book_intent_invalid",
            stage="book",
            field="book_kol_us",
        )
    if book.get("decision") not in {"trade", "no_trade"} or (
        book.get("decision") == "no_trade" and not _nonblank(book.get("reason"))
    ):
        raise _fail(
            "Book KOL-US intent is incomplete",
            error_code="book_intent_invalid",
            stage="book",
            field="book_kol_us",
        )


def _validate_reader_and_terminals(item: dict[str, Any]) -> None:
    decision_status = _validate_decision_and_knowledge(item)
    _validate_content_routing(item)
    _validate_reader_copy(item, decision_status)
    _validate_synthesis(item)
    _validate_household_recommendation(item)
    _validate_book_intent(item)


def _validate_segments(item: Mapping[str, Any], known: Mapping[str, Mapping[str, Any]], text: str) -> None:
    unknown: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "segment_id" in value:
                segment_id = str(value.get("segment_id") or "")
                if segment_id not in known:
                    unknown.append(segment_id)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(item)
    if unknown:
        raise _fail(
            "semantic evidence reference uses an unknown request segment",
            error_code="segment_identity_invalid",
            stage="evidence_binding",
            field="segment_id",
        )
    for index, claim in enumerate(item.get("claims") or []):
        if not isinstance(claim, Mapping):
            raise _fail(
                "claim row is invalid",
                error_code="coverage_not_evidence_bound",
                stage="coverage",
                field=f"claims[{index}]",
            )
        quote = claim.get("quote")
        if not isinstance(quote, str) or not quote.strip() or quote not in text:
            claim_id = str(claim.get("claim_id") or "<unknown>")
            raise _fail(
                "claim quote is not evidence-bound",
                error_code="coverage_not_evidence_bound",
                stage="coverage",
                field=f"claims[{claim_id}].quote",
            )
    try:
        validate_claim_coverage(
            dict(item),
            evidence_text=text,
            evidence_sha256=str(item.get("evidence_sha256") or ""),
        )
    except DecisionError as exc:
        raise _fail(
            "investment claim coverage is incomplete",
            error_code="coverage_not_evidence_bound",
            stage="coverage",
        ) from exc


def _validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise _fail(
            "semantic request is invalid",
            error_code="request_invalid",
            stage="request_binding",
        )
    path, evidence_sha, text = _read_evidence(request)
    if request.get("event") == "subscription_video_analysis_input_required":
        contract_path_value = str(
            request.get("full_contract_path") or ""
        ).strip()
        contract_sha_value = str(
            request.get("full_contract_sha256") or ""
        ).strip()
        if not contract_path_value or not contract_sha_value:
            raise _fail(
                "subscription video request is not bound to the full contract",
                error_code="full_contract_binding_missing",
                stage="request_binding",
                field="full_contract_sha256",
            )
        contract_path = Path(contract_path_value).expanduser().resolve()
        try:
            contract_bytes = contract_path.read_bytes()
        except OSError as exc:
            raise _fail(
                "subscription video full contract is missing",
                error_code="full_contract_binding_invalid",
                stage="request_binding",
                field="full_contract_path",
            ) from exc
        actual_contract_sha = hashlib.sha256(contract_bytes).hexdigest()
        if (
            not _SHA256.fullmatch(contract_sha_value)
            or contract_sha_value != actual_contract_sha
        ):
            raise _fail(
                "subscription video full contract changed after request creation",
                error_code="full_contract_binding_invalid",
                stage="request_binding",
                field="full_contract_sha256",
            )
    message_sha = request.get("message_sha256") or request.get("content_sha256")
    if not message_sha:
        raise _fail(
            "message or content hash is required",
            error_code="message_binding_missing",
            stage="request_binding",
            field="message_sha256",
        )
    message_sha = _require_sha(
        message_sha,
        code="message_binding_invalid",
        stage="request_binding",
        field="message_sha256",
    )
    content_sha = str(request.get("content_sha256") or message_sha)
    _require_sha(
        content_sha,
        code="message_binding_invalid",
        stage="request_binding",
        field="content_sha256",
    )
    source_identity = str(request.get("source_identity") or request.get("identity") or "").strip()
    source_version = str(request.get("source_version_key") or request.get("version_key") or "").strip()
    handoff_id = str(request.get("handoff_id") or request.get("message_id") or source_identity).strip()
    if not source_identity or not source_version or not handoff_id:
        raise _fail(
            "source and handoff identity are incomplete",
            error_code="handoff_binding_invalid",
            stage="request_binding",
        )
    media_sha = request.get("media_sha256") or request.get("video_sha256")
    media_identity = str(
        request.get("media_identity")
        or media_sha
        or f"not_applicable:{source_identity}"
    )
    extraction = request.get("investment_claim_extraction") or request.get("claim_extraction")
    if not isinstance(extraction, dict):
        extraction = build_claim_extraction_request(path, evidence_sha256=evidence_sha)
    if extraction.get("contract_version") != CONTRACT_VERSION:
        raise _fail(
            "claim extraction contract is invalid",
            error_code="extraction_contract_invalid",
            stage="evidence_binding",
            field="investment_claim_extraction.contract_version",
        )
    expected_segments = evidence_segments(text, evidence_sha256=evidence_sha)
    supplied_segments = extraction.get("segments")
    if not isinstance(supplied_segments, list):
        raise _fail(
            "claim extraction segments are missing",
            error_code="segment_identity_invalid",
            stage="evidence_binding",
            field="investment_claim_extraction.segments",
        )
    if any(
        not isinstance(row, dict) or not str(row.get("segment_id") or "").strip()
        for row in supplied_segments
    ):
        raise _fail(
            "claim extraction segment identity is invalid",
            error_code="segment_identity_invalid",
            stage="evidence_binding",
            field="investment_claim_extraction.segments",
        )
    expected_by_id = {str(row["segment_id"]): row for row in expected_segments}
    supplied_by_id = {
        str(row.get("segment_id") or ""): row
        for row in supplied_segments
        if isinstance(row, dict)
    }
    if len(supplied_segments) != len(supplied_by_id) or set(supplied_by_id) != set(expected_by_id) or any(
        {key: value for key, value in supplied_by_id[segment_id].items() if key != "text"}
        != {key: value for key, value in expected_by_id[segment_id].items() if key != "text"}
        for segment_id in expected_by_id
        if segment_id in supplied_by_id
    ):
        raise _fail(
            "claim extraction segment identity changed",
            error_code="segment_identity_invalid",
            stage="evidence_binding",
            field="investment_claim_extraction.segments",
        )
    required_ids = extraction.get("required_segment_ids")
    if required_ids is not None and set(map(str, required_ids)) != set(expected_by_id):
        raise _fail(
            "claim extraction required segments changed",
            error_code="segment_identity_invalid",
            stage="evidence_binding",
            field="investment_claim_extraction.required_segment_ids",
        )
    return {
        "path": path,
        "evidence_sha256": evidence_sha,
        "text": text,
        "message_sha256": message_sha,
        "content_sha256": content_sha,
        "handoff_id": handoff_id,
        "media_sha256": str(media_sha) if media_sha else None,
        "media_identity": media_identity,
        "source_identity": source_identity,
        "source_version_key": source_version,
        "extraction": extraction,
        "segments": expected_by_id,
    }


def _check_draft_fields(
    draft: Mapping[str, Any],
    *,
    evidence_sha256: str | None = None,
) -> None:
    def walk(
        value: Any,
        *,
        depth: int = 0,
        path: tuple[str, ...] = (),
    ) -> None:
        if isinstance(value, Mapping):
            for field, child in value.items():
                if field == "evidence_sha256":
                    if evidence_sha256 and evidence_sha256 != child:
                        raise _fail(
                            "semantic draft evidence identity does not match request",
                            error_code="evidence_binding_mismatch",
                            stage="evidence_binding",
                            field="evidence_sha256",
                        )
                    if evidence_sha256 == child:
                        walk(child, depth=depth + 1, path=path + (str(field),))
                    continue
                if field == "contract_version" and child == CONTRACT_VERSION:
                    walk(child, depth=depth + 1, path=path + (str(field),))
                    continue
                protected_metadata = depth == 0 and field in _REQUEST_METADATA_FIELDS
                protected_field = field in _PROTECTED_DRAFT_FIELDS and field not in _REQUEST_METADATA_FIELDS
                relationship_binding = (
                    path == _EPISODE_RELATIONSHIP_SOURCE_BINDING_PATH
                    and field in {"identity", "version_key"}
                )
                if (
                    (protected_metadata or protected_field) and not relationship_binding
                ) or field.endswith("_idempotency_key"):
                    raise _fail(
                        "semantic draft contains a request-owned or business-owned field",
                        error_code="semantic_draft_forbidden_field",
                        stage="semantic_input",
                        field=str(field),
                    )
                walk(child, depth=depth + 1, path=path + (str(field),))
        elif isinstance(value, list):
            for child in value:
                walk(child, depth=depth + 1, path=path)

    walk(draft)


def _source_metadata(request: Mapping[str, Any], validated: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    fields = (
        "source",
        "author",
        "title",
        "published_at",
        "published_at_basis",
        "source_modified_at",
        "captured_at",
        "first_observed_at",
        "media_type",
        "source_path",
        "source_identity",
        "source_version_key",
        "identity",
        "version_key",
        "publication_version",
        "original_evidence_path",
        "original_evidence_sha256",
    )
    for field in fields:
        if request.get(field) is not None:
            metadata[field] = request[field]
    metadata.update(
        {
            "evidence_path": str(validated["path"]),
            "evidence_sha256": validated["evidence_sha256"],
        }
    )
    if any(
        field not in metadata
        for field in ("source", "author", "title", "captured_at")
    ):
        raise _fail(
            "source metadata is incomplete",
            error_code="source_metadata_invalid",
            stage="request_binding",
        )
    return metadata


def _canonical_bundle(request: Mapping[str, Any], draft: Mapping[str, Any], validated: Mapping[str, Any]) -> dict[str, Any]:
    _check_draft_fields(draft, evidence_sha256=str(validated["evidence_sha256"]))
    market, _ = _market_projection(request, draft)
    item = _source_metadata(request, validated)
    for key, value in draft.items():
        if key not in {"cross_source", "market_validation"}:
            item[key] = value
    item["market_validation"] = market
    outlook = item.get("market_outlook")
    if isinstance(outlook, dict):
        normalized_outlook = dict(outlook)
        normalized_outlook["current_validation"] = market
        item["market_outlook"] = normalized_outlook
    signals = item.get("actionable_signals")
    if isinstance(signals, list):
        item["actionable_signals"] = [
            {
                **signal,
                "current_validation": market,
            }
            if isinstance(signal, dict)
            else signal
            for signal in signals
        ]
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "household_context_provider": {
            "type": "lianghui_mcp",
            "fresh_read_per_run": True,
        },
        "items": [item],
        "cross_source": draft.get("cross_source") or {"agreements": [], "conflicts": []},
    }
    _validate_complete_bundle(bundle, validated)
    return bundle


def _validate_complete_bundle(bundle: dict[str, Any], validated: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise _fail(
            "semantic bundle schema version is invalid",
            error_code="bundle_schema_invalid",
            stage="semantic_validation",
        )
    if bundle.get("validator_version") != VALIDATOR_VERSION:
        raise _fail(
            "semantic bundle validator version is invalid",
            error_code="bundle_schema_invalid",
            stage="semantic_validation",
            field="validator_version",
        )
    items = bundle.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise _fail(
            "semantic bundle requires exactly one item",
            error_code="bundle_shape_invalid",
            stage="semantic_validation",
        )
    item = items[0]
    if item.get("evidence_sha256") != validated["evidence_sha256"]:
        raise _fail(
            "semantic bundle evidence binding changed",
            error_code="evidence_binding_mismatch",
            stage="evidence_binding",
        )
    _validate_market(item.get("market_validation") or {})
    _validate_coverage(item, str(validated["text"]))
    _validate_segments(item, validated["segments"], str(validated["text"]))
    _validate_market_outlook(item, item["market_validation"])
    _validate_actionable_signals(item, item["market_validation"])
    _validate_reader_and_terminals(item)
    _validate_projection(item)
    _validate_cross_source(bundle)


def _validate_cross_source(bundle: Mapping[str, Any]) -> None:
    """Reject malformed cross-source rows before downstream processing."""

    cross_source = bundle.get("cross_source")
    if not isinstance(cross_source, dict):
        raise _fail(
            "semantic cross-source assessment is invalid",
            error_code="cross_source_invalid",
            stage="semantic_validation",
            field="cross_source",
        )
    claim_authors = {
        str(claim.get("claim_id") or ""): str(item.get("author") or "")
        for item in bundle.get("items") or []
        if isinstance(item, dict)
        for claim in item.get("claims") or []
        if isinstance(claim, dict)
    }
    for relation_type in ("agreements", "conflicts"):
        relations = cross_source.get(relation_type)
        if not isinstance(relations, list):
            raise _fail(
                "semantic cross-source relations must be lists",
                error_code="cross_source_invalid",
                stage="semantic_validation",
                field=f"cross_source.{relation_type}",
            )
        for index, relation in enumerate(relations):
            field = f"cross_source.{relation_type}[{index}]"
            if not isinstance(relation, dict):
                raise _fail(
                    "semantic cross-source relation must be an object",
                    error_code="cross_source_invalid",
                    stage="semantic_validation",
                    field=field,
                )
            linked = relation.get("claim_ids")
            if (
                not _nonblank(relation.get("topic"))
                or not _nonblank(relation.get("judgment"))
                or not isinstance(linked, list)
                or len(linked) < 2
                or any(not _nonblank(claim_id) for claim_id in linked)
                or not set(map(str, linked)).issubset(claim_authors)
                or len({claim_authors[str(claim_id)] for claim_id in linked}) < 2
            ):
                raise _fail(
                    "semantic cross-source relation is not evidence-bound",
                    error_code="cross_source_invalid",
                    stage="semantic_validation",
                    field=field,
                )


def _bindings(request: Mapping[str, Any], validated: Mapping[str, Any], market_sha: str, draft: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "message_sha256": validated["message_sha256"],
        "content_sha256": validated["content_sha256"],
        "handoff_id": validated["handoff_id"],
        "media_identity": validated["media_identity"],
        "media_sha256": validated["media_sha256"],
        "transcript_sha256": validated["evidence_sha256"],
        "extraction_contract_version": validated["extraction"]["contract_version"],
        "extraction_segments_sha256": _sha256_canonical(
            _normalized_segment_bindings(validated["extraction"]["segments"])
        ),
        "market_evidence_sha256": market_sha,
        "source_identity": validated["source_identity"],
        "source_version_key": validated["source_version_key"],
        "source_metadata_sha256": _sha256_canonical({
            field: request[field]
            for field in sorted(_REQUEST_METADATA_FIELDS)
            if request.get(field) is not None
        }),
        "semantic_draft_sha256": _sha256_canonical(draft),
    }


def _request_binding_preview(
    request: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return receipt bindings without rereading evidence when possible.

    A valid receipt is the durable proof that the transcript was already
    consumed for this exact binding set.  Requests that do not carry the
    existing extraction rows cannot be compared safely without rereading the
    evidence, so they deliberately fall back to the full request validator.
    """

    extraction = request.get("investment_claim_extraction") or request.get(
        "claim_extraction"
    )
    if not isinstance(extraction, dict) or not isinstance(
        extraction.get("segments"), list
    ):
        return None
    supplied_segments = extraction["segments"]
    segment_ids = [
        str(row.get("segment_id") or "")
        for row in supplied_segments
        if isinstance(row, dict)
    ]
    if len(segment_ids) != len(supplied_segments) or len(segment_ids) != len(
        set(segment_ids)
    ):
        return None
    if extraction.get("contract_version") != CONTRACT_VERSION:
        return None
    evidence_sha = str(
        request.get("evidence_sha256") or request.get("transcript_sha256") or ""
    )
    try:
        message_sha = _require_sha(
            request.get("message_sha256"),
            code="message_binding_invalid",
            stage="request_binding",
            field="message_sha256",
        )
        content_sha = _require_sha(
            request.get("content_sha256") or message_sha,
            code="message_binding_invalid",
            stage="request_binding",
            field="content_sha256",
        )
        evidence_sha = _require_sha(
            evidence_sha,
            code="evidence_binding_invalid",
            stage="evidence_binding",
            field="evidence_sha256",
        )
    except SemanticBundleError:
        return None
    source_identity = str(
        request.get("source_identity") or request.get("identity") or ""
    ).strip()
    source_version = str(
        request.get("source_version_key") or request.get("version_key") or ""
    ).strip()
    handoff_id = str(
        request.get("handoff_id") or request.get("message_id") or source_identity
    ).strip()
    if not source_identity or not source_version or not handoff_id:
        return None
    media_sha = request.get("media_sha256") or request.get("video_sha256")
    media_identity = str(
        request.get("media_identity")
        or media_sha
        or f"not_applicable:{source_identity}"
    )
    raw_market = request.get("market_evidence")
    if not isinstance(raw_market, dict):
        return None
    supplied_market_sha = (
        raw_market.get("sha256")
        or raw_market.get("evidence_sha256")
        or raw_market.get("market_evidence_sha256")
        or request.get("market_evidence_sha256")
    )
    market_payload = {
        key: value
        for key, value in raw_market.items()
        if key not in {"sha256", "evidence_sha256", "market_evidence_sha256"}
    }
    market_sha = str(supplied_market_sha or _sha256_canonical(market_payload))
    if not _SHA256.fullmatch(market_sha):
        return None
    return {
        "message_sha256": message_sha,
        "content_sha256": content_sha,
        "handoff_id": handoff_id,
        "media_identity": media_identity,
        "media_sha256": str(media_sha) if media_sha else None,
        "transcript_sha256": evidence_sha,
        "extraction_contract_version": extraction["contract_version"],
        "extraction_segments_sha256": _sha256_canonical(
            _normalized_segment_bindings(supplied_segments)
        ),
        "market_evidence_sha256": market_sha,
        "source_identity": source_identity,
        "source_version_key": source_version,
        "source_metadata_sha256": _sha256_canonical({
            field: request[field]
            for field in sorted(_REQUEST_METADATA_FIELDS)
            if request.get(field) is not None
        }),
        "semantic_draft_sha256": _sha256_canonical(draft),
    }


def _normalized_segment_bindings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [
        {
            str(key): child
            for key, child in row.items()
            if key != "text"
        }
        for row in value
        if isinstance(row, dict)
    ]
    return sorted(rows, key=lambda row: str(row.get("segment_id") or ""))


@dataclass(frozen=True)
class ValidatedBundleReceipt:
    """Hash-bound proof that a canonical bundle passed the full validator."""

    schema_version: int
    bindings: dict[str, Any]
    bundle_path: str
    bundle_sha256: str
    bundle_schema_version: int
    validator_version: str
    created_at: str
    receipt_sha256: str
    reused: bool = False

    def _unsigned(self) -> dict[str, Any]:
        return {
            "event": "validated_bundle_receipt",
            "schema_version": self.schema_version,
            "bindings": self.bindings,
            "bundle_path": self.bundle_path,
            "bundle_sha256": self.bundle_sha256,
            "bundle_schema_version": self.bundle_schema_version,
            "validator_version": self.validator_version,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._unsigned(), "receipt_sha256": self.receipt_sha256}

    def with_reused(self, reused: bool) -> "ValidatedBundleReceipt":
        return replace(self, reused=reused)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ValidatedBundleReceipt":
        required = {
            "event",
            "schema_version",
            "bindings",
            "bundle_path",
            "bundle_sha256",
            "bundle_schema_version",
            "validator_version",
            "created_at",
            "receipt_sha256",
        }
        if not isinstance(value, Mapping) or not required.issubset(value):
            raise _fail(
                "validated bundle receipt is incomplete",
                error_code="receipt_invalid",
                stage="receipt_reconciliation",
            )
        if value.get("event") != "validated_bundle_receipt":
            raise _fail(
                "validated bundle receipt event is invalid",
                error_code="receipt_invalid",
                stage="receipt_reconciliation",
            )
        try:
            receipt = cls(
                schema_version=int(value["schema_version"]),
                bindings=dict(value["bindings"]),
                bundle_path=str(value["bundle_path"]),
                bundle_sha256=str(value["bundle_sha256"]),
                bundle_schema_version=int(value["bundle_schema_version"]),
                validator_version=str(value["validator_version"]),
                created_at=str(value["created_at"]),
                receipt_sha256=str(value["receipt_sha256"]),
            )
        except (TypeError, ValueError) as exc:
            raise _fail(
                "validated bundle receipt fields are invalid",
                error_code="receipt_invalid",
                stage="receipt_reconciliation",
            ) from exc
        if (
            receipt.schema_version != 1
            or receipt.bundle_schema_version != BUNDLE_SCHEMA_VERSION
            or receipt.validator_version != VALIDATOR_VERSION
        ):
            raise _fail(
                "validated bundle receipt version is invalid",
                error_code="receipt_invalid",
                stage="receipt_reconciliation",
            )
        if receipt.receipt_sha256 != _sha256_canonical(receipt._unsigned()):
            raise _fail(
                "validated bundle receipt hash is invalid",
                error_code="receipt_integrity_invalid",
                stage="receipt_reconciliation",
            )
        _require_sha(
            receipt.bundle_sha256,
            code="receipt_invalid",
            stage="receipt_reconciliation",
            field="bundle_sha256",
        )
        return receipt


def _load_reusable_receipt(
    receipt_path: Path,
    bundle_path: Path,
    expected_bindings: Mapping[str, Any],
) -> ValidatedBundleReceipt | None:
    if not receipt_path.is_file() or not bundle_path.is_file():
        return None
    try:
        receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt = ValidatedBundleReceipt.from_dict(receipt_value)
        bundle_bytes = bundle_path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SemanticBundleError):
        return None
    if _sha256_bytes(bundle_bytes) != receipt.bundle_sha256:
        return None
    if receipt.bindings != dict(expected_bindings):
        return None
    try:
        bundle = json.loads(bundle_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(bundle, dict) or bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        return None
    return receipt.with_reused(True)


def build_validated_bundle(
    request: Mapping[str, Any],
    semantic_draft: Mapping[str, Any],
    *,
    bundle_path: Path | str | None = None,
    receipt_path: Path | str | None = None,
) -> ValidatedBundleReceipt:
    """Build, fully validate, and atomically persist one semantic artifact.

    ``semantic_draft`` is intentionally not a near-complete bundle.  Request
    owned evidence and source metadata are projected from ``request`` and all
    external identities remain outside the artifact hash.
    """

    if not isinstance(semantic_draft, Mapping):
        raise _fail(
            "semantic draft is invalid",
            error_code="semantic_draft_invalid",
            stage="semantic_input",
        )
    default_artifact_dir = request.get("artifact_dir")
    default_bundle_path = request.get("validated_bundle_path") or request.get(
        "bundle_path"
    )
    if default_bundle_path is None and default_artifact_dir is not None:
        default_bundle_path = Path(str(default_artifact_dir)) / "validated_bundle.json"
    if default_bundle_path is None:
        evidence_path = request.get("evidence_path") or request.get("transcript_path")
        source_version = str(
            request.get("source_version_key") or request.get("version_key") or ""
        ).strip()
        if evidence_path and source_version:
            default_bundle_path = Path(str(evidence_path)).expanduser().resolve().with_name(
                f"{source_version}.validated_bundle.json"
            )
    if default_bundle_path is None:
        raise _fail(
            "validated bundle output path is missing",
            error_code="artifact_path_invalid",
            stage="artifact",
            field="bundle_path",
        )
    bundle_file = Path(bundle_path or default_bundle_path).expanduser().resolve()
    default_receipt_path = request.get("validated_bundle_receipt_path")
    if default_receipt_path is None:
        default_receipt_path = bundle_file.with_name("validated_bundle_receipt.json")
    receipt_file = Path(receipt_path or default_receipt_path).expanduser().resolve()
    _check_draft_fields(semantic_draft, evidence_sha256=str(request.get("evidence_sha256") or request.get("transcript_sha256") or ""))
    preview_bindings = _request_binding_preview(request, semantic_draft)
    if preview_bindings is not None:
        reusable = _load_reusable_receipt(
            receipt_file,
            bundle_file,
            preview_bindings,
        )
        if reusable is not None:
            return reusable

    validated = _validate_request(request)
    _check_draft_fields(
        semantic_draft,
        evidence_sha256=str(validated["evidence_sha256"]),
    )
    market, market_sha = _market_projection(request, semantic_draft)
    expected_bindings = _bindings(request, validated, market_sha, semantic_draft)
    reusable = _load_reusable_receipt(receipt_file, bundle_file, expected_bindings)
    if reusable is not None:
        return reusable

    bundle = _canonical_bundle(request, semantic_draft, validated)
    bundle_bytes = (canonical(bundle) + "\n").encode("utf-8")
    bundle_sha = _sha256_bytes(bundle_bytes)
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    unsigned_receipt = {
        "event": "validated_bundle_receipt",
        "schema_version": 1,
        "bindings": expected_bindings,
        "bundle_path": str(bundle_file),
        "bundle_sha256": bundle_sha,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "created_at": created_at,
    }
    receipt = ValidatedBundleReceipt(
        schema_version=1,
        bindings=expected_bindings,
        bundle_path=str(bundle_file),
        bundle_sha256=bundle_sha,
        bundle_schema_version=BUNDLE_SCHEMA_VERSION,
        validator_version=VALIDATOR_VERSION,
        created_at=created_at,
        receipt_sha256=_sha256_canonical(unsigned_receipt),
    )
    # Bundle first, receipt second: a consumer can only proceed after both
    # artifacts exist and the receipt verifies the exact bundle bytes.
    _atomic_bytes(bundle_file, bundle_bytes)
    _atomic_json(receipt_file, receipt.to_dict())
    return receipt


def build_validated_bundle_from_files(
    analysis_request_path: Path | str,
    semantic_draft_path: Path | str,
    market_evidence_path: Path | str,
) -> ValidatedBundleReceipt:
    """Build one canonical artifact from three independently owned inputs.

    The deterministic adapter owns ``analysis_request_path``; the Agent owns
    only the judgment draft and the separately captured current-market
    evidence.  Keeping market evidence out of the draft prevents a caller from
    silently projecting two different market states into one item.
    """

    def read_object(path_value: Path | str, *, label: str) -> tuple[Path, dict[str, Any]]:
        path = Path(path_value).expanduser().resolve()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _fail(
                f"{label} is invalid",
                error_code=f"{label.replace(' ', '_')}_invalid",
                stage="semantic_input",
            ) from exc
        if not isinstance(value, dict):
            raise _fail(
                f"{label} must be an object",
                error_code=f"{label.replace(' ', '_')}_invalid",
                stage="semantic_input",
            )
        return path, value

    request_path, request = read_object(
        analysis_request_path,
        label="analysis request",
    )
    _, draft = read_object(semantic_draft_path, label="semantic draft")
    _, market_evidence = read_object(
        market_evidence_path,
        label="market evidence",
    )
    if request.get("market_evidence") is not None:
        raise _fail(
            "analysis request already contains mutable market evidence",
            error_code="market_evidence_ownership_invalid",
            stage="market_validation",
            field="market_evidence",
        )
    artifact_dir = request.get("artifact_dir") or request_path.parent
    canonical_request = {
        **request,
        "artifact_dir": str(Path(str(artifact_dir)).expanduser().resolve()),
        "market_evidence": market_evidence,
    }
    return build_validated_bundle(canonical_request, draft)


def validate_existing_bundle(
    request: Mapping[str, Any],
    existing_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a legacy/cached artifact without creating a receipt or claims."""

    if not isinstance(existing_bundle, Mapping):
        raise _fail(
            "existing semantic bundle is invalid",
            error_code="bundle_shape_invalid",
            stage="legacy_validation",
        )
    validated = _validate_request(request)
    bundle = json.loads(canonical(existing_bundle))
    _validate_complete_bundle(bundle, validated)
    return bundle


def read_validated_bundle(
    bundle_path: Path | str,
    *,
    receipt_path: Path | str | None = None,
) -> tuple[ValidatedBundleReceipt, dict[str, Any]]:
    """Read and revalidate a persisted artifact before a consumer effect."""

    bundle_file = Path(bundle_path).expanduser().resolve()
    receipt_file = Path(receipt_path).expanduser().resolve() if receipt_path else (
        bundle_file.with_name("validated_bundle_receipt.json")
    )
    try:
        bundle_bytes = bundle_file.read_bytes()
        bundle = json.loads(bundle_bytes.decode("utf-8"))
        receipt_value = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(
            "validated bundle artifact or receipt cannot be read",
            error_code="receipt_invalid",
            stage="receipt_reconciliation",
        ) from exc
    if not isinstance(bundle, dict):
        raise _fail(
            "validated bundle artifact is invalid",
            error_code="bundle_shape_invalid",
            stage="receipt_reconciliation",
        )
    receipt = ValidatedBundleReceipt.from_dict(receipt_value)
    if (
        receipt.bundle_path != str(bundle_file)
        or receipt.bundle_sha256 != _sha256_bytes(bundle_bytes)
    ):
        raise _fail(
            "validated bundle receipt does not bind the artifact",
            error_code="receipt_binding_mismatch",
            stage="receipt_reconciliation",
        )
    items = bundle.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise _fail(
            "validated bundle artifact has no single item",
            error_code="bundle_shape_invalid",
            stage="receipt_reconciliation",
        )
    item = items[0]
    bindings = receipt.bindings
    evidence_path = Path(str(item.get("evidence_path") or "")).expanduser().resolve()
    evidence_sha = str(item.get("evidence_sha256") or "")
    market = item.get("market_validation")
    if not isinstance(market, dict):
        raise _fail(
            "validated bundle market evidence is missing",
            error_code="market_evidence_missing",
            stage="receipt_reconciliation",
        )
    request = {
        "message_sha256": bindings.get("message_sha256"),
        "content_sha256": bindings.get("content_sha256"),
        "handoff_id": bindings.get("handoff_id"),
        "media_sha256": bindings.get("media_sha256"),
        "media_identity": bindings.get("media_identity"),
        "source": item.get("source"),
        "author": item.get("author"),
        "title": item.get("title"),
        "published_at": item.get("published_at"),
        "published_at_basis": item.get("published_at_basis"),
        "source_modified_at": item.get("source_modified_at"),
        "captured_at": item.get("captured_at"),
        "first_observed_at": item.get("first_observed_at"),
        "media_type": item.get("media_type"),
        "source_identity": bindings.get("source_identity") or item.get("source_identity"),
        "source_version_key": bindings.get("source_version_key") or item.get("source_version_key"),
        "evidence_path": str(evidence_path),
        "evidence_sha256": evidence_sha,
        "investment_claim_extraction": build_claim_extraction_request(
            evidence_path,
            evidence_sha256=evidence_sha,
        ),
        "market_evidence": {
            "sha256": bindings.get("market_evidence_sha256"),
            "validation": market,
        },
    }
    validated = _validate_request(request)
    if (
        bindings.get("extraction_contract_version")
        != validated["extraction"]["contract_version"]
        or bindings.get("extraction_segments_sha256")
        != _sha256_canonical(
            _normalized_segment_bindings(validated["extraction"]["segments"])
        )
    ):
        raise _fail(
            "validated bundle receipt extraction binding changed",
            error_code="receipt_binding_mismatch",
            stage="receipt_reconciliation",
            field="extraction_contract_version",
        )
    _validate_complete_bundle(bundle, validated)
    return receipt.with_reused(True), bundle


def validate_receipt_bindings(
    receipt: ValidatedBundleReceipt,
    expected: Mapping[str, Any],
) -> None:
    """Check a persisted receipt against the live adapter identity."""

    for field, value in expected.items():
        if value is None:
            continue
        if receipt.bindings.get(field) != value:
            raise _fail(
                "validated bundle receipt does not match the current item",
                error_code="receipt_binding_mismatch",
                stage="receipt_reconciliation",
                field=str(field),
            )


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "VALIDATOR_VERSION",
    "SemanticBundleError",
    "ValidatedBundleReceipt",
    "build_validated_bundle",
    "build_validated_bundle_from_files",
    "read_validated_bundle",
    "validate_receipt_bindings",
    "validate_existing_bundle",
]
