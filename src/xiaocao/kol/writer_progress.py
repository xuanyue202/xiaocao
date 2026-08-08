"""Credential-safe progress and convergence contracts for the KOL writer."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from ._shared import append_integrity_jsonl, read_integrity_jsonl


PROGRESS_STATUSES = frozenset(
    {
        "continue",
        "structured_input",
        "wait_until",
        "repair_required",
        "reconcile_required",
        "user_action_required",
        "terminal",
    }
)
OWNERS = frozenset({"agent", "provider", "user", "reconciliation", "none"})
RETRYABILITIES = frozenset({"retryable", "not_retryable"})
NEXT_ACTIONS = {
    "continue": "continue_in_process",
    "structured_input": "await_structured_input",
    "wait_until": "resume_after_deadline",
    "repair_required": "validate_repair_then_narrow_resume",
    "reconcile_required": "perform_authoritative_readback",
    "user_action_required": "await_user_action",
    "terminal": "stop",
}

_SAFE_TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_MAX_LEDGER_LINE_BYTES = 64 * 1024


class ProgressContractError(ValueError):
    """A writer step cannot be represented by the convergence contract."""


def resolve_repository_revision(root: Path | str) -> str:
    """Resolve one full Git revision without leaking command diagnostics."""

    try:
        result = subprocess.run(
            ("git", "rev-parse", "--verify", "HEAD"),
            cwd=Path(root).expanduser().resolve(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProgressContractError(
            "writer failure revision cannot be resolved"
        ) from exc
    revision = result.stdout.strip()
    if result.returncode != 0 or not _HEX_40.fullmatch(revision):
        raise ProgressContractError("writer failure revision cannot be resolved")
    return revision


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _safe_token(value: Any, *, field_name: str) -> str:
    token = str(value or "").strip()
    if not _SAFE_TOKEN.fullmatch(token):
        raise ProgressContractError(f"{field_name} is not a safe token")
    return token


def _safe_identity(value: Any, *, field_name: str) -> str:
    identity = str(value or "").strip()
    if not _SAFE_IDENTITY.fullmatch(identity):
        raise ProgressContractError(f"{field_name} is not a safe identity")
    return identity


def _revision(value: Any, *, field_name: str, optional: bool = False) -> str | None:
    revision = str(value or "").strip()
    if optional and not revision:
        return None
    if not _HEX_40.fullmatch(revision):
        raise ProgressContractError(f"{field_name} must be a full commit revision")
    return revision


def _sha256(value: Any, *, field_name: str) -> str:
    digest = str(value or "").strip()
    if not _HEX_64.fullmatch(digest):
        raise ProgressContractError(f"{field_name} must be a SHA-256 digest")
    return digest


def _timezone_aware(value: Any, *, field_name: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgressContractError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ProgressContractError(f"{field_name} must include a timezone")
    return raw


def _claim_receipt_summary(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ProgressContractError("claim_receipt_summary must be an object")
    required = {"claim_count", "receipt_count", "uncertain_effect_count"}
    if set(value) != required:
        raise ProgressContractError(
            "claim_receipt_summary needs claim, receipt, and uncertain counts"
        )
    result: dict[str, int] = {}
    for name in sorted(required):
        count = value[name]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ProgressContractError(
                f"claim_receipt_summary {name} must be a non-negative integer"
            )
        result[name] = count
    if result["receipt_count"] > result["claim_count"]:
        raise ProgressContractError("receipt count cannot exceed claim count")
    return result


@dataclass(frozen=True)
class FailureFingerprint:
    """Stable hash of the allowlisted fields that identify one root failure."""

    adapter: str
    category: str
    code: str
    stage: str
    failure_revision: str
    provider_contract_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "adapter",
            _safe_token(self.adapter, field_name="adapter"),
        )
        object.__setattr__(
            self,
            "category",
            _safe_token(self.category, field_name="category"),
        )
        object.__setattr__(self, "code", _safe_token(self.code, field_name="code"))
        object.__setattr__(self, "stage", _safe_token(self.stage, field_name="stage"))
        object.__setattr__(
            self,
            "failure_revision",
            _revision(self.failure_revision, field_name="failure_revision"),
        )
        object.__setattr__(
            self,
            "provider_contract_version",
            _safe_token(
                self.provider_contract_version,
                field_name="provider_contract_version",
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(self._fields())

    def _fields(self) -> dict[str, str]:
        return {
            "adapter": self.adapter,
            "category": self.category,
            "code": self.code,
            "stage": self.stage,
            "failure_revision": self.failure_revision,
            "provider_contract_version": self.provider_contract_version,
        }

    def to_dict(self) -> dict[str, str]:
        return {**self._fields(), "digest": self.digest}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FailureFingerprint":
        if not isinstance(value, Mapping):
            raise ProgressContractError("failure fingerprint must be an object")
        required = {
            "adapter",
            "category",
            "code",
            "stage",
            "failure_revision",
            "provider_contract_version",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ProgressContractError(
                f"failure fingerprint lacks {', '.join(missing)}"
            )
        extra = sorted(set(value) - required - {"digest"})
        if extra:
            raise ProgressContractError(
                f"failure fingerprint contains unsupported field {', '.join(extra)}"
            )
        result = cls(**{name: str(value[name]) for name in required})
        supplied_digest = str(value.get("digest") or "")
        if supplied_digest and supplied_digest != result.digest:
            raise ProgressContractError("failure fingerprint digest does not match")
        return result


@dataclass(frozen=True)
class WriterProgress:
    """One persisted writer result with one mechanically defined next action."""

    status: str
    ownership: str
    retryability: str
    item_identity: str
    stage: str
    next_action: str
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProgressContractError("writer progress schema version is unsupported")
        if self.status not in PROGRESS_STATUSES:
            raise ProgressContractError("writer progress status is unsupported")
        if self.ownership not in OWNERS:
            raise ProgressContractError("writer progress ownership is unsupported")
        if self.retryability not in RETRYABILITIES:
            raise ProgressContractError("writer progress retryability is unsupported")
        object.__setattr__(
            self,
            "item_identity",
            _safe_identity(self.item_identity, field_name="item_identity"),
        )
        object.__setattr__(self, "stage", _safe_token(self.stage, field_name="stage"))
        if self.next_action != NEXT_ACTIONS[self.status]:
            raise ProgressContractError(
                f"{self.status} has exactly one legal next action"
            )
        normalized = dict(self.details)
        normalized["claim_receipt_summary"] = _claim_receipt_summary(
            normalized.get("claim_receipt_summary")
        )
        self._validate_details(normalized)
        object.__setattr__(self, "details", normalized)

    @property
    def failure_fingerprint(self) -> str:
        return str(self.details.get("failure_fingerprint") or "")

    @property
    def failure(self) -> dict[str, Any]:
        value = self.details.get("failure")
        return dict(value) if isinstance(value, Mapping) else {}

    def _validate_details(self, details: dict[str, Any]) -> None:
        required_by_status = {
            "continue": {"completed_stage", "next_stage"},
            "structured_input": {
                "request_kind",
                "request_id",
                "request_schema_version",
                "immutable_bindings",
                "response_field",
            },
            "wait_until": {"category", "code", "deadline", "attempt_budget"},
            "repair_required": {
                "failure",
                "failure_fingerprint",
                "failure_revision",
                "repair_revision",
                "affected_set_digest",
                "targeted_test_profile",
                "narrow_resume_surface",
            },
            "reconcile_required": {
                "effect_kind",
                "claim_identity",
                "readback_operation",
                "retry_forbidden",
            },
            "user_action_required": {"action", "blocker_identity", "dedup_key"},
            "terminal": {
                "content_terminal",
                "gray_report_terminal",
                "reminder_terminal",
                "book_terminal",
                "knowledge_terminal",
                "ack_status",
                "new_external_effect_count",
            },
        }
        missing = sorted(required_by_status[self.status] - set(details))
        if missing:
            raise ProgressContractError(
                f"{self.status} lacks required field {', '.join(missing)}"
            )
        allowed = required_by_status[self.status] | {"claim_receipt_summary"}
        extra = sorted(set(details) - allowed)
        if extra:
            raise ProgressContractError(
                f"{self.status} contains unsupported field {', '.join(extra)}"
            )
        if self.status == "continue":
            _safe_token(details["completed_stage"], field_name="completed_stage")
            _safe_token(details["next_stage"], field_name="next_stage")
            summary = details["claim_receipt_summary"]
            if summary["uncertain_effect_count"] or (
                summary["claim_count"] != summary["receipt_count"]
            ):
                raise ProgressContractError(
                    "continue cannot carry an uncertain or unreceipted effect"
                )
        elif self.status == "structured_input":
            _safe_token(details["request_kind"], field_name="request_kind")
            _safe_identity(details["request_id"], field_name="request_id")
            if (
                isinstance(details["request_schema_version"], bool)
                or not isinstance(details["request_schema_version"], int)
                or details["request_schema_version"] < 1
            ):
                raise ProgressContractError("request_schema_version must be positive")
            if not isinstance(details["immutable_bindings"], Mapping):
                raise ProgressContractError("immutable_bindings must be an object")
            _safe_token(details["response_field"], field_name="response_field")
        elif self.status == "wait_until":
            _safe_token(details["category"], field_name="category")
            _safe_token(details["code"], field_name="code")
            _timezone_aware(details["deadline"], field_name="deadline")
            budget = details["attempt_budget"]
            if (
                not isinstance(budget, Mapping)
                or set(budget) != {"attempted", "maximum"}
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in budget.values()
                )
                or int(budget["attempted"]) < 0
                or int(budget["maximum"]) < 1
                or int(budget["attempted"]) > int(budget["maximum"])
            ):
                raise ProgressContractError("attempt_budget is invalid")
            if self.ownership == "agent":
                raise ProgressContractError(
                    "agent-owned deterministic failures cannot wait indefinitely"
                )
        elif self.status == "repair_required":
            failure = FailureFingerprint.from_dict(details["failure"])
            details["failure"] = failure.to_dict()
            if details["failure_fingerprint"] != failure.digest:
                raise ProgressContractError("repair failure fingerprint does not match")
            if details["failure_revision"] != failure.failure_revision:
                raise ProgressContractError("repair failure revision does not match")
            _revision(
                details["repair_revision"],
                field_name="repair_revision",
                optional=True,
            )
            _sha256(details["affected_set_digest"], field_name="affected_set_digest")
            _safe_token(
                details["targeted_test_profile"],
                field_name="targeted_test_profile",
            )
            _safe_identity(
                details["narrow_resume_surface"],
                field_name="narrow_resume_surface",
            )
            if self.ownership != "agent":
                raise ProgressContractError("repair_required must be agent-owned")
        elif self.status == "reconcile_required":
            _safe_token(details["effect_kind"], field_name="effect_kind")
            _safe_identity(details["claim_identity"], field_name="claim_identity")
            _safe_token(
                details["readback_operation"],
                field_name="readback_operation",
            )
            if details["retry_forbidden"] is not True:
                raise ProgressContractError("reconciliation must forbid retry")
            if self.ownership != "reconciliation":
                raise ProgressContractError(
                    "reconcile_required must be reconciliation-owned"
                )
        elif self.status == "user_action_required":
            if not str(details["action"] or "").strip():
                raise ProgressContractError("user action is required")
            _safe_identity(
                details["blocker_identity"],
                field_name="blocker_identity",
            )
            _safe_identity(details["dedup_key"], field_name="dedup_key")
            if self.ownership != "user":
                raise ProgressContractError("user_action_required must be user-owned")
        elif self.status == "terminal":
            for name in (
                "content_terminal",
                "gray_report_terminal",
                "reminder_terminal",
                "book_terminal",
                "knowledge_terminal",
                "ack_status",
            ):
                _safe_token(details[name], field_name=name)
            count = details["new_external_effect_count"]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ProgressContractError(
                    "new_external_effect_count must be non-negative"
                )
            if self.ownership != "none" or self.retryability != "not_retryable":
                raise ProgressContractError("terminal cannot retain an owner or retry")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ownership": self.ownership,
            "retryability": self.retryability,
            "item_identity": self.item_identity,
            "stage": self.stage,
            "next_action": self.next_action,
            **self.details,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WriterProgress":
        if not isinstance(value, Mapping):
            raise ProgressContractError("writer progress must be an object")
        base = {
            "schema_version",
            "status",
            "ownership",
            "retryability",
            "item_identity",
            "stage",
            "next_action",
        }
        missing = sorted(base - set(value))
        if missing:
            raise ProgressContractError(
                f"writer progress lacks required field {', '.join(missing)}"
            )
        return cls(
            schema_version=value["schema_version"],
            status=str(value["status"]),
            ownership=str(value["ownership"]),
            retryability=str(value["retryability"]),
            item_identity=str(value["item_identity"]),
            stage=str(value["stage"]),
            next_action=str(value["next_action"]),
            details={key: raw for key, raw in value.items() if key not in base},
        )

    @classmethod
    def _build(
        cls,
        status: str,
        *,
        ownership: str,
        retryability: str,
        item_identity: str,
        stage: str,
        claim_receipt_summary: Mapping[str, int],
        **details: Any,
    ) -> "WriterProgress":
        return cls(
            status=status,
            ownership=ownership,
            retryability=retryability,
            item_identity=item_identity,
            stage=stage,
            next_action=NEXT_ACTIONS[status],
            details={
                **details,
                "claim_receipt_summary": dict(claim_receipt_summary),
            },
        )

    @classmethod
    def continue_(
        cls,
        *,
        item_identity: str,
        completed_stage: str,
        next_stage: str,
        claim_receipt_summary: Mapping[str, int],
    ) -> "WriterProgress":
        return cls._build(
            "continue",
            ownership="agent",
            retryability="not_retryable",
            item_identity=item_identity,
            stage=completed_stage,
            completed_stage=completed_stage,
            next_stage=next_stage,
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def structured_input(
        cls,
        *,
        item_identity: str,
        stage: str,
        request_kind: str,
        request_id: str,
        request_schema_version: int,
        immutable_bindings: Mapping[str, Any],
        response_field: str,
        claim_receipt_summary: Mapping[str, int],
    ) -> "WriterProgress":
        return cls._build(
            "structured_input",
            ownership="agent",
            retryability="not_retryable",
            item_identity=item_identity,
            stage=stage,
            request_kind=request_kind,
            request_id=request_id,
            request_schema_version=request_schema_version,
            immutable_bindings=dict(immutable_bindings),
            response_field=response_field,
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def wait_until(
        cls,
        *,
        item_identity: str,
        category: str,
        code: str,
        stage: str,
        deadline: str,
        attempt_budget: Mapping[str, int],
        claim_receipt_summary: Mapping[str, int],
        ownership: str = "provider",
    ) -> "WriterProgress":
        return cls._build(
            "wait_until",
            ownership=ownership,
            retryability="retryable",
            item_identity=item_identity,
            stage=stage,
            category=category,
            code=code,
            deadline=deadline,
            attempt_budget=dict(attempt_budget),
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def repair_required(
        cls,
        *,
        item_identity: str,
        fingerprint: FailureFingerprint,
        repair_revision: str | None,
        affected_set_digest: str,
        claim_receipt_summary: Mapping[str, int],
        targeted_test_profile: str,
        narrow_resume_surface: str,
        retryability: str,
    ) -> "WriterProgress":
        return cls._build(
            "repair_required",
            ownership="agent",
            retryability=retryability,
            item_identity=item_identity,
            stage=fingerprint.stage,
            failure=fingerprint.to_dict(),
            failure_fingerprint=fingerprint.digest,
            failure_revision=fingerprint.failure_revision,
            repair_revision=repair_revision,
            affected_set_digest=affected_set_digest,
            targeted_test_profile=targeted_test_profile,
            narrow_resume_surface=narrow_resume_surface,
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def reconcile_required(
        cls,
        *,
        item_identity: str,
        stage: str,
        effect_kind: str,
        claim_identity: str,
        readback_operation: str,
        claim_receipt_summary: Mapping[str, int],
    ) -> "WriterProgress":
        return cls._build(
            "reconcile_required",
            ownership="reconciliation",
            retryability="not_retryable",
            item_identity=item_identity,
            stage=stage,
            effect_kind=effect_kind,
            claim_identity=claim_identity,
            readback_operation=readback_operation,
            retry_forbidden=True,
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def user_action_required(
        cls,
        *,
        item_identity: str,
        stage: str,
        action: str,
        blocker_identity: str,
        dedup_key: str,
        claim_receipt_summary: Mapping[str, int],
    ) -> "WriterProgress":
        return cls._build(
            "user_action_required",
            ownership="user",
            retryability="retryable",
            item_identity=item_identity,
            stage=stage,
            action=action,
            blocker_identity=blocker_identity,
            dedup_key=dedup_key,
            claim_receipt_summary=claim_receipt_summary,
        )

    @classmethod
    def terminal(
        cls,
        *,
        item_identity: str,
        stage: str,
        content_terminal: str,
        gray_report_terminal: str,
        reminder_terminal: str,
        book_terminal: str,
        knowledge_terminal: str,
        ack_status: str,
        new_external_effect_count: int,
        claim_receipt_summary: Mapping[str, int],
    ) -> "WriterProgress":
        return cls._build(
            "terminal",
            ownership="none",
            retryability="not_retryable",
            item_identity=item_identity,
            stage=stage,
            content_terminal=content_terminal,
            gray_report_terminal=gray_report_terminal,
            reminder_terminal=reminder_terminal,
            book_terminal=book_terminal,
            knowledge_terminal=knowledge_terminal,
            ack_status=ack_status,
            new_external_effect_count=new_external_effect_count,
            claim_receipt_summary=claim_receipt_summary,
        )

    def validate_transition_to(
        self,
        following: "WriterProgress",
        *,
        evidence: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        if self.status == "terminal":
            raise ProgressContractError("terminal progress cannot transition")
        if self.status == "continue" and (
            self.details["next_stage"] != following.stage
        ):
            raise ProgressContractError("continue must enter its declared next stage")
        if self.status == "wait_until":
            if now is None:
                raise ProgressContractError(
                    "wait_until transition requires the current time"
                )
            deadline = datetime.fromisoformat(
                str(self.details["deadline"]).replace("Z", "+00:00")
            )
            if now.tzinfo is None or now < deadline:
                raise ProgressContractError("wait_until deadline has not elapsed")
        if self.status == "structured_input":
            handler_repair = (
                following.status == "repair_required"
                and following.failure.get("category")
                == "control_plane_handler_error"
            )
            receipt = dict(evidence or {})
            if not handler_repair and (
                receipt.get("event") != "structured_input_consumed"
                or receipt.get("request_id") != self.details["request_id"]
                or receipt.get("response_field")
                != self.details["response_field"]
            ):
                raise ProgressContractError(
                    "structured_input needs a matching consumption receipt"
                )
        repair_continues = (
            following.status == "repair_required"
            and following.failure_fingerprint == self.failure_fingerprint
        )
        if self.status == "repair_required" and not repair_continues:
            receipt = dict(evidence or {})
            if (
                receipt.get("event") != "repair_closed"
                or receipt.get("failure_fingerprint") != self.failure_fingerprint
                or not _HEX_40.fullmatch(str(receipt.get("repair_revision") or ""))
            ):
                raise ProgressContractError(
                    "repair_required needs a matching repair closure"
                )
        if (
            self.status == "reconcile_required"
            and following.status != "reconcile_required"
        ):
            handler_repair = (
                following.status == "repair_required"
                and following.failure.get("category")
                == "control_plane_handler_error"
            )
            receipt = dict(evidence or {})
            if not handler_repair and (
                receipt.get("event") != "reconciliation_completed"
                or receipt.get("claim_identity") != self.details["claim_identity"]
            ):
                raise ProgressContractError(
                    "reconcile_required needs authoritative readback evidence"
                )


def affected_set_digest(rows: list[Mapping[str, Any]]) -> str:
    """Hash exact identity/version bindings without persisting their labels."""

    normalized = sorted(
        (
            {
                "identity": _safe_identity(row.get("identity"), field_name="identity"),
                "version_key": _safe_identity(
                    row.get("version_key"),
                    field_name="version_key",
                ),
            }
            for row in rows
        ),
        key=lambda row: (row["identity"], row["version_key"]),
    )
    if not normalized:
        raise ProgressContractError("affected set cannot be empty")
    return _digest(normalized)


def _aggregate_terminal(
    events: list[dict[str, Any]],
    *path: str,
    default: str,
) -> str:
    values: list[str] = []
    for event in events:
        current: Any = event
        for field_name in path:
            current = current.get(field_name) if isinstance(current, Mapping) else None
        value = str(current or "").strip()
        if value:
            values.append(_safe_token(value, field_name=path[-1]))
    unique = list(dict.fromkeys(values))
    return unique[0] if len(unique) == 1 else "mixed_completed" if unique else default


def _source_item_identity(adapter: str, item: Mapping[str, Any] | None) -> str:
    if item is not None:
        identity = str(item.get("identity") or "").strip()
        if _SAFE_IDENTITY.fullmatch(identity):
            return identity
    return f"{adapter}:source"


def _progress_claim_summary(outcome: Mapping[str, Any]) -> dict[str, int]:
    supplied = outcome.get("claim_receipt_summary")
    if isinstance(supplied, Mapping):
        return _claim_receipt_summary(supplied)
    return {
        "claim_count": 0,
        "receipt_count": 0,
        "uncertain_effect_count": 0,
    }


def project_source_outcome(
    adapter: str,
    outcome: Mapping[str, Any],
    *,
    failure_revision: str,
    provider_contract_version: str,
    user_action: Mapping[str, Any] | None = None,
    fallback_wait_deadline: str | None = None,
) -> WriterProgress:
    """Project legacy source output through the finite writer state machine."""

    adapter_name = _safe_token(adapter, field_name="adapter")
    raw_progress = outcome.get("writer_progress")
    if isinstance(raw_progress, Mapping):
        return WriterProgress.from_dict(raw_progress)
    status = str(outcome.get("status") or "")
    summary = _progress_claim_summary(outcome)
    source_identity = f"{adapter_name}:source"
    if status == "no_update":
        return WriterProgress.terminal(
            item_identity=source_identity,
            stage="source_run",
            content_terminal="no_update",
            gray_report_terminal="not_created",
            reminder_terminal="not_created",
            book_terminal="not_created",
            knowledge_terminal="not_created",
            ack_status="not_applicable",
            new_external_effect_count=0,
            claim_receipt_summary=summary,
        )
    if status == "completed":
        raw_events = outcome.get("events")
        events = [
            row for row in raw_events if isinstance(row, dict)
        ] if isinstance(raw_events, list) else []
        external_effect_count = sum(
            int((event.get("gray_report") or {}).get("status") == "published")
            + int((event.get("alert") or {}).get("status") == "delivered")
            + int((event.get("book_kol_us") or {}).get("status") == "filled")
            for event in events
        )
        terminal_summary = (
            {
                "claim_count": external_effect_count,
                "receipt_count": external_effect_count,
                "uncertain_effect_count": 0,
            }
            if summary == {
                "claim_count": 0,
                "receipt_count": 0,
                "uncertain_effect_count": 0,
            }
            else summary
        )
        return WriterProgress.terminal(
            item_identity=source_identity,
            stage="source_run",
            content_terminal=_aggregate_terminal(
                events,
                "content_value",
                "status",
                default="completed",
            ),
            gray_report_terminal=_aggregate_terminal(
                events,
                "gray_report",
                "status",
                default="not_applicable",
            ),
            reminder_terminal=_aggregate_terminal(
                events,
                "alert",
                "status",
                default="not_applicable",
            ),
            book_terminal=_aggregate_terminal(
                events,
                "book_kol_us",
                "status",
                default="not_applicable",
            ),
            knowledge_terminal=_aggregate_terminal(
                events,
                "knowledge_effect",
                "status",
                default="not_applicable",
            ),
            ack_status=str(outcome.get("ack_status") or "not_applicable"),
            new_external_effect_count=external_effect_count,
            claim_receipt_summary=terminal_summary,
        )
    if status != "waiting":
        raise ProgressContractError("source outcome status cannot be projected")
    waiting_items = outcome.get("waiting_items")
    items = [
        row for row in waiting_items if isinstance(row, Mapping)
    ] if isinstance(waiting_items, list) else []
    item = items[0] if items else None
    item_identity = _source_item_identity(adapter_name, item)
    stage = _safe_token(
        (item or {}).get("stage") or "source_run",
        field_name="stage",
    )
    if outcome.get("user_action_required") is True:
        action = dict(user_action or {})
        if not action:
            raise ProgressContractError(
                "user action projection needs exact blocker fields"
            )
        return WriterProgress.user_action_required(
            item_identity=item_identity,
            stage=stage,
            action=str(action.get("action") or ""),
            blocker_identity=str(action.get("blocker_identity") or ""),
            dedup_key=str(action.get("dedup_key") or ""),
            claim_receipt_summary=summary,
        )
    if item is not None and (
        stage == "waiting_semantic_input"
        or item.get("analysis_request_path")
        or item.get("image_request_path")
    ):
        bindings = {
            key: str(item[key])
            for key in ("identity", "version_key", "evidence_sha256")
            if str(item.get(key) or "").strip()
        }
        request_id = _digest({"adapter": adapter_name, **bindings, "stage": stage})
        return WriterProgress.structured_input(
            item_identity=item_identity,
            stage=stage,
            request_kind=(
                "daily_official_article_image_input_required"
                if item.get("image_request_path")
                else "subscription_video_analysis_input_required"
                if adapter_name == "subscription_video"
                else "daily_analysis_input_required"
            ),
            request_id=request_id,
            request_schema_version=1,
            immutable_bindings=bindings,
            response_field=(
                "image_notes_path" if item.get("image_request_path") else "bundle_path"
            ),
            claim_receipt_summary=summary,
        )
    failure_value = outcome.get("failure")
    if not isinstance(failure_value, Mapping) and item is not None:
        failure_value = item.get("failure")
    failure = dict(failure_value) if isinstance(failure_value, Mapping) else {}
    category = str(
        failure.get("category")
        or (item or {}).get("category")
        or "internal_state_error"
    )
    code = str(
        failure.get("code")
        or (item or {}).get("code")
        or "generic_wait_without_deadline"
    )
    if category == "uncertain_state" or "reconciliation" in stage:
        claim_identity = str((item or {}).get("claim_identity") or "")
        readback_operation = str(
            (item or {}).get("readback_operation") or ""
        )
        effect_kind = str((item or {}).get("effect_kind") or "")
        if claim_identity and readback_operation and effect_kind:
            return WriterProgress.reconcile_required(
                item_identity=item_identity,
                stage=stage,
                effect_kind=effect_kind,
                claim_identity=claim_identity,
                readback_operation=readback_operation,
                claim_receipt_summary={
                    **summary,
                    "uncertain_effect_count": max(
                        1,
                        summary["uncertain_effect_count"],
                    ),
                },
            )
        category = "control_plane_handler_error"
        code = "uncertain_effect_lacks_readback_binding"
    deadline = str((item or {}).get("next_poll_not_before") or "").strip()
    if deadline:
        attempted = int((item or {}).get("trigger_attempt") or 1)
        return WriterProgress.wait_until(
            item_identity=item_identity,
            category=category,
            code=code,
            stage=stage,
            deadline=deadline,
            attempt_budget={"attempted": attempted, "maximum": max(3, attempted)},
            claim_receipt_summary=summary,
        )
    if (
        not failure
        and outcome.get("repair_required") is not True
        and fallback_wait_deadline is not None
    ):
        return WriterProgress.wait_until(
            item_identity=item_identity,
            category="provider_wait",
            code="source_pending",
            stage=stage,
            deadline=fallback_wait_deadline,
            attempt_budget={"attempted": 1, "maximum": 2},
            claim_receipt_summary=summary,
        )
    fingerprint = FailureFingerprint(
        adapter=adapter_name,
        category=_safe_token(category, field_name="category"),
        code=_safe_token(code, field_name="code"),
        stage=stage,
        failure_revision=str(
            _revision(failure_revision, field_name="failure_revision")
        ),
        provider_contract_version=provider_contract_version,
    )
    affected_rows = [
        {
            "identity": item_identity,
            "version_key": str((item or {}).get("version_key") or "current"),
        }
    ]
    return WriterProgress.repair_required(
        item_identity=item_identity,
        fingerprint=fingerprint,
        repair_revision=None,
        affected_set_digest=affected_set_digest(affected_rows),
        claim_receipt_summary=summary,
        targeted_test_profile=f"kol_{adapter_name}_{stage}"[:128],
        narrow_resume_surface=(
            f"{adapter_name}:{item_identity}"
            if item is not None
            else f"{adapter_name}:source"
        ),
        retryability=(
            "retryable" if failure.get("retryable", True) is not False
            else "not_retryable"
        ),
    )


class ConvergenceLedger:
    """Append-only observations from which the current repair owner is recovered."""

    def __init__(
        self,
        path: Path | str,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.path = Path(path).expanduser().resolve()
        self.lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        self.now = now or (lambda: datetime.now().astimezone())
        self._thread_lock = threading.RLock()

    def _now(self) -> str:
        value = self.now()
        if value.tzinfo is None:
            raise ProgressContractError("convergence ledger clock needs a timezone")
        return value.isoformat(timespec="seconds")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        return append_integrity_jsonl(
            self.path,
            {"schema_version": 1, **row},
            max_line_bytes=_MAX_LEDGER_LINE_BYTES,
            label="convergence ledger",
            error_factory=ProgressContractError,
        )

    def events(self) -> list[dict[str, Any]]:
        return read_integrity_jsonl(
            self.path,
            max_line_bytes=_MAX_LEDGER_LINE_BYTES,
            label="convergence ledger",
            error_factory=ProgressContractError,
        )

    def record(self, progress: WriterProgress, *, slot: str) -> dict[str, Any]:
        if progress.status != "repair_required":
            raise ProgressContractError(
                "convergence failure observations require repair_required"
            )
        _timezone_aware(slot, field_name="slot")
        with self._locked():
            return self._append(
                {
                    "event": "failure_observed",
                    "observed_at": self._now(),
                    "slot": slot,
                    "failure": progress.failure,
                    "failure_fingerprint": progress.failure_fingerprint,
                    "ownership": progress.ownership,
                    "progress": progress.to_dict(),
                    "retryability": progress.retryability,
                }
            )

    def active_progress(self, adapter: str) -> WriterProgress | None:
        """Recover the latest unclosed repair owned by one adapter."""

        adapter_name = _safe_token(adapter, field_name="adapter")
        rows = self.events()
        latest_by_fingerprint: dict[str, dict[str, Any]] = {}
        for row in rows:
            fingerprint = str(row.get("failure_fingerprint") or "")
            if fingerprint:
                latest_by_fingerprint[fingerprint] = row
        for row in reversed(rows):
            if row.get("event") != "failure_observed":
                continue
            fingerprint = str(row.get("failure_fingerprint") or "")
            if latest_by_fingerprint.get(fingerprint) is not row:
                continue
            failure = row.get("failure")
            if (
                not isinstance(failure, Mapping)
                or failure.get("adapter") != adapter_name
            ):
                continue
            progress = row.get("progress")
            if not isinstance(progress, Mapping):
                raise ProgressContractError(
                    "active convergence row lacks persisted progress"
                )
            return WriterProgress.from_dict(progress)
        return None

    def pending_resume(
        self,
        adapter: str,
    ) -> tuple[WriterProgress, dict[str, Any]] | None:
        """Return a closed repair whose one narrow continuation is still due."""

        adapter_name = _safe_token(adapter, field_name="adapter")
        rows = self.events()
        latest_by_fingerprint: dict[str, dict[str, Any]] = {}
        for row in rows:
            fingerprint = str(row.get("failure_fingerprint") or "")
            if fingerprint:
                latest_by_fingerprint[fingerprint] = row
        for closure in reversed(rows):
            if closure.get("event") != "repair_closed":
                continue
            fingerprint = str(closure.get("failure_fingerprint") or "")
            if latest_by_fingerprint.get(fingerprint) is not closure:
                continue
            observation = next(
                (
                    row
                    for row in reversed(rows)
                    if row.get("event") == "failure_observed"
                    and row.get("failure_fingerprint") == fingerprint
                ),
                None,
            )
            if observation is None:
                raise ProgressContractError("repair closure lost its observation")
            failure = observation.get("failure")
            if (
                not isinstance(failure, Mapping)
                or failure.get("adapter") != adapter_name
            ):
                continue
            return WriterProgress.from_dict(observation["progress"]), closure
        return None

    def record_resume(
        self,
        failure_fingerprint: str,
        *,
        following: WriterProgress,
        slot: str,
    ) -> dict[str, Any]:
        """Consume one matching closure through its declared narrow surface."""

        digest = _sha256(
            failure_fingerprint,
            field_name="failure_fingerprint",
        )
        _timezone_aware(slot, field_name="slot")
        with self._locked():
            rows = [
                row
                for row in self.events()
                if row.get("failure_fingerprint") == digest
            ]
            if not rows or rows[-1].get("event") != "repair_closed":
                raise ProgressContractError("repair has no pending narrow resume")
            closure = rows[-1]
            observation = next(
                row for row in reversed(rows)
                if row.get("event") == "failure_observed"
            )
            prior = WriterProgress.from_dict(observation["progress"])
            receipt = closure["repair_receipt"]
            prior.validate_transition_to(
                following,
                evidence={
                    "event": "repair_closed",
                    "failure_fingerprint": digest,
                    "repair_revision": receipt["repair_revision"],
                },
            )
            return self._append(
                {
                    "event": "repair_resumed",
                    "resumed_at": self._now(),
                    "slot": slot,
                    "failure_fingerprint": digest,
                    "narrow_resume_surface": prior.details[
                        "narrow_resume_surface"
                    ],
                    "result_status": following.status,
                }
            )

    def close_repair(
        self,
        failure_fingerprint: str,
        *,
        repair_receipt: Mapping[str, Any],
        slot: str,
    ) -> dict[str, Any]:
        digest = _sha256(
            failure_fingerprint,
            field_name="failure_fingerprint",
        )
        receipt = dict(repair_receipt)
        required = {
            "receipt_id",
            "failure_fingerprint",
            "repair_revision",
            "targeted_test_profile",
        }
        missing = sorted(required - set(receipt))
        if missing:
            raise ProgressContractError(
                f"repair receipt lacks {', '.join(missing)}"
            )
        extra = sorted(set(receipt) - required)
        if extra:
            raise ProgressContractError(
                f"repair receipt contains unsupported field {', '.join(extra)}"
            )
        if receipt["failure_fingerprint"] != digest:
            raise ProgressContractError("repair receipt fingerprint does not match")
        _safe_identity(receipt["receipt_id"], field_name="receipt_id")
        _revision(receipt["repair_revision"], field_name="repair_revision")
        _safe_token(
            receipt["targeted_test_profile"],
            field_name="targeted_test_profile",
        )
        _timezone_aware(slot, field_name="slot")
        with self._locked():
            observations = [
                row
                for row in self.events()
                if row.get("event") == "failure_observed"
                and row.get("failure_fingerprint") == digest
            ]
            if not observations:
                raise ProgressContractError("repair closure has no matching failure")
            open_progress = WriterProgress.from_dict(observations[-1]["progress"])
            if (
                receipt["targeted_test_profile"]
                != open_progress.details["targeted_test_profile"]
            ):
                raise ProgressContractError(
                    "repair receipt test profile does not match open repair"
                )
            latest_matching = [
                row
                for row in self.events()
                if row.get("failure_fingerprint") == digest
            ][-1]
            if latest_matching.get("event") != "failure_observed":
                raise ProgressContractError("repair is not currently open")
            return self._append(
                {
                    "event": "repair_closed",
                    "closed_at": self._now(),
                    "slot": slot,
                    "failure_fingerprint": digest,
                    "repair_receipt": receipt,
                }
            )

    def current(self, failure_fingerprint: str) -> dict[str, Any] | None:
        digest = _sha256(
            failure_fingerprint,
            field_name="failure_fingerprint",
        )
        rows = [
            row
            for row in self.events()
            if row.get("failure_fingerprint") == digest
        ]
        observations = [row for row in rows if row.get("event") == "failure_observed"]
        if not observations:
            return None
        latest = rows[-1]
        latest_observation = observations[-1]
        latest_slot = latest_observation["slot"]
        same_sweep_count = sum(
            1 for row in observations if row.get("slot") == latest_slot
        )
        slots = list(dict.fromkeys(str(row["slot"]) for row in observations))
        consecutive_slots = 1
        parsed_slots = [
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            for value in slots
        ]
        for index in range(len(parsed_slots) - 1, 0, -1):
            current_slot = parsed_slots[index]
            expected_previous = (
                current_slot - timedelta(hours=1)
                if current_slot.hour > 7
                else (current_slot - timedelta(days=1)).replace(hour=23)
            )
            if parsed_slots[index - 1] != expected_previous:
                break
            consecutive_slots += 1
        closed = latest.get("event") in {"repair_closed", "repair_resumed"}
        latest_closure = next(
            (
                row
                for row in reversed(rows)
                if row.get("event") == "repair_closed"
            ),
            None,
        )
        return {
            "failure_fingerprint": digest,
            "first_seen": observations[0]["observed_at"],
            "last_seen": latest_observation["observed_at"],
            "same_sweep_count": same_sweep_count,
            "consecutive_slots": consecutive_slots,
            "current_owner": None if closed else latest_observation["ownership"],
            "repair_receipt": (
                latest_closure.get("repair_receipt")
                if closed and latest_closure is not None
                else None
            ),
            "closure": (
                latest_closure.get("closed_at")
                if closed and latest_closure is not None
                else None
            ),
            "closed": closed,
        }
