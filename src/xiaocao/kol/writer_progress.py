"""Credential-safe progress and convergence contracts for the KOL writer."""

from __future__ import annotations

import fcntl
import hashlib
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from zoneinfo import ZoneInfo

from ._shared import (
    append_integrity_jsonl,
    canonical_sha256,
    read_integrity_jsonl,
)


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
STATUS_REQUIRED_FIELDS = {
    "continue": frozenset({"completed_stage", "next_stage"}),
    "structured_input": frozenset({
        "request_kind",
        "request_id",
        "request_schema_version",
        "immutable_bindings",
        "response_field",
    }),
    "wait_until": frozenset({"category", "code", "deadline", "attempt_budget"}),
    "repair_required": frozenset({
        "failure",
        "failure_fingerprint",
        "failure_revision",
        "repair_revision",
        "affected_set_digest",
        "targeted_test_profile",
        "narrow_resume_surface",
    }),
    "reconcile_required": frozenset({
        "effect_kind",
        "claim_identity",
        "readback_operation",
        "retry_forbidden",
    }),
    "user_action_required": frozenset({"action", "blocker_identity", "dedup_key"}),
    "terminal": frozenset({
        "content_terminal",
        "gray_report_terminal",
        "reminder_terminal",
        "book_terminal",
        "knowledge_terminal",
        "ack_status",
        "new_external_effect_count",
    }),
}

_SAFE_TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}")
_SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_MAX_LEDGER_LINE_BYTES = 64 * 1024
_ACCEPTANCE_TIMEZONE = ZoneInfo("Asia/Shanghai")
_REQUIRED_STABILITY_DAYS = 7
_REQUIRED_STABILITY_SLOTS = 50
_REQUIRED_RECENT_DAYS = 3
_REQUIRED_RECENT_SLOTS = 20
_PEER_GATE_P95_LIMIT_MS = 60_000
_CLEAN_SWEEP_P95_LIMIT_MS = 300_000
_MIN_LATENCY_SAMPLES = 20
_GENERIC_WAIT_CODES = frozenset({
    "generic_wait_without_deadline",
    "source_pending",
})
_INTERNAL_FAILURE_CATEGORIES = frozenset({
    "code_error",
    "schema_error",
    "environment_error",
    "provider_contract_error",
    "control_plane_handler_error",
    "local_runtime_error",
    "protocol_error",
    "internal_state_error",
})
_DUPLICATE_EFFECT_KINDS = frozenset({
    "publication",
    "reminder",
    "book",
    "knowledge",
    "ack",
})


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


def _digest(value: Any) -> str:
    return canonical_sha256(value)


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


def _safe_branch(value: Any, *, field_name: str) -> str:
    branch = str(value or "").strip()
    if not _SAFE_BRANCH.fullmatch(branch) or branch.startswith("/"):
        raise ProgressContractError(f"{field_name} is not a safe branch")
    return branch


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
class RepairValidationReceipt:
    """Proof that one repository repair is safe for one exact mailbox wait."""

    message_id: str
    content_sha256: str
    failure_fingerprint: str
    failure_revision: str
    failure_code: str
    failure_stage: str
    repair_revision: str
    target_branch: str
    target_branch_revision: str
    target_branch_lineage: dict[str, Any]
    targeted_test_profile: str
    test_command_digest: str
    test_result_sha256: str
    test_status: str
    validated_at: str
    receipt_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ProgressContractError(
                "repair validation receipt schema version is unsupported"
            )
        _sha256(self.message_id, field_name="message_id")
        _sha256(self.content_sha256, field_name="content_sha256")
        _sha256(self.failure_fingerprint, field_name="failure_fingerprint")
        _revision(self.failure_revision, field_name="failure_revision")
        _safe_token(self.failure_code, field_name="failure_code")
        _safe_token(self.failure_stage, field_name="failure_stage")
        _revision(self.repair_revision, field_name="repair_revision")
        _safe_branch(self.target_branch, field_name="target_branch")
        _revision(
            self.target_branch_revision,
            field_name="target_branch_revision",
        )
        if set(self.target_branch_lineage) != {
            "failure_revision",
            "repair_revision",
            "target_branch_revision",
            "is_ancestor",
        }:
            raise ProgressContractError("repair validation branch lineage is invalid")
        for field_name in (
            "failure_revision",
            "repair_revision",
            "target_branch_revision",
        ):
            _revision(
                self.target_branch_lineage[field_name],
                field_name=f"target_branch_lineage.{field_name}",
            )
        if self.target_branch_lineage["repair_revision"] != self.repair_revision:
            raise ProgressContractError("repair validation lineage revision changed")
        if (
            self.target_branch_lineage["target_branch_revision"]
            != self.target_branch_revision
        ):
            raise ProgressContractError("repair validation branch tip changed")
        if self.target_branch_lineage["is_ancestor"] is not True:
            raise ProgressContractError("repair validation lineage is not proven")
        _safe_token(
            self.targeted_test_profile,
            field_name="targeted_test_profile",
        )
        _sha256(self.test_command_digest, field_name="test_command_digest")
        _sha256(self.test_result_sha256, field_name="test_result_sha256")
        if self.test_status != "passed":
            raise ProgressContractError("repair validation test did not pass")
        _timezone_aware(self.validated_at, field_name="validated_at")
        _sha256(self.receipt_sha256, field_name="receipt_sha256")
        if self.receipt_sha256 != self._unsigned_digest():
            raise ProgressContractError("repair validation receipt hash changed")

    def _unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "content_sha256": self.content_sha256,
            "failure_fingerprint": self.failure_fingerprint,
            "failure_revision": self.failure_revision,
            "failure_code": self.failure_code,
            "failure_stage": self.failure_stage,
            "repair_revision": self.repair_revision,
            "target_branch": self.target_branch,
            "target_branch_revision": self.target_branch_revision,
            "target_branch_lineage": dict(self.target_branch_lineage),
            "targeted_test_profile": self.targeted_test_profile,
            "test_command_digest": self.test_command_digest,
            "test_result_sha256": self.test_result_sha256,
            "test_status": self.test_status,
            "validated_at": self.validated_at,
        }

    def _unsigned_digest(self) -> str:
        return _digest(self._unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._unsigned_dict(),
            "receipt_sha256": self.receipt_sha256,
        }

    @classmethod
    def create(
        cls,
        *,
        message_id: str,
        content_sha256: str,
        failure_fingerprint: str,
        failure_revision: str,
        failure_code: str,
        failure_stage: str,
        repair_revision: str,
        target_branch: str,
        target_branch_revision: str,
        targeted_test_profile: str,
        test_command_digest: str,
        test_result_sha256: str,
        validated_at: str,
    ) -> "RepairValidationReceipt":
        lineage = {
            "failure_revision": failure_revision,
            "repair_revision": repair_revision,
            "target_branch_revision": target_branch_revision,
            "is_ancestor": True,
        }
        unsigned = {
            "schema_version": 1,
            "message_id": message_id,
            "content_sha256": content_sha256,
            "failure_fingerprint": failure_fingerprint,
            "failure_revision": failure_revision,
            "failure_code": failure_code,
            "failure_stage": failure_stage,
            "repair_revision": repair_revision,
            "target_branch": target_branch,
            "target_branch_revision": target_branch_revision,
            "target_branch_lineage": lineage,
            "targeted_test_profile": targeted_test_profile,
            "test_command_digest": test_command_digest,
            "test_result_sha256": test_result_sha256,
            "test_status": "passed",
            "validated_at": validated_at,
        }
        digest = _digest(unsigned)
        return cls(
            **unsigned,
            receipt_sha256=digest,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RepairValidationReceipt":
        if not isinstance(value, Mapping):
            raise ProgressContractError("repair validation receipt must be an object")
        required = {
            "schema_version",
            "message_id",
            "content_sha256",
            "failure_fingerprint",
            "failure_revision",
            "failure_code",
            "failure_stage",
            "repair_revision",
            "target_branch",
            "target_branch_revision",
            "target_branch_lineage",
            "targeted_test_profile",
            "test_command_digest",
            "test_result_sha256",
            "test_status",
            "validated_at",
            "receipt_sha256",
        }
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required)
        if missing:
            raise ProgressContractError(
                f"repair validation receipt lacks {', '.join(missing)}"
            )
        if extra:
            raise ProgressContractError(
                "repair validation receipt contains unsupported field "
                + ", ".join(extra)
            )
        lineage = value["target_branch_lineage"]
        if not isinstance(lineage, Mapping):
            raise ProgressContractError("repair validation lineage must be an object")
        return cls(
            schema_version=value["schema_version"],
            message_id=str(value["message_id"]),
            content_sha256=str(value["content_sha256"]),
            failure_fingerprint=str(value["failure_fingerprint"]),
            failure_revision=str(value["failure_revision"]),
            failure_code=str(value["failure_code"]),
            failure_stage=str(value["failure_stage"]),
            repair_revision=str(value["repair_revision"]),
            target_branch=str(value["target_branch"]),
            target_branch_revision=str(value["target_branch_revision"]),
            target_branch_lineage={str(k): v for k, v in lineage.items()},
            targeted_test_profile=str(value["targeted_test_profile"]),
            test_command_digest=str(value["test_command_digest"]),
            test_result_sha256=str(value["test_result_sha256"]),
            test_status=str(value["test_status"]),
            validated_at=str(value["validated_at"]),
            receipt_sha256=str(value["receipt_sha256"]),
        )


class RepairValidationLedger:
    """Append-only store for repository-owned repair validation receipts."""

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser().resolve()
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def receipts(self) -> list[RepairValidationReceipt]:
        rows = read_integrity_jsonl(
            self.path,
            max_line_bytes=_MAX_LEDGER_LINE_BYTES,
            label="repair validation ledger",
            error_factory=ProgressContractError,
        )
        return [
            RepairValidationReceipt.from_dict(
                {key: value for key, value in row.items() if key != "event_id"}
            )
            for row in rows
        ]

    def append(self, receipt: RepairValidationReceipt) -> RepairValidationReceipt:
        if not isinstance(receipt, RepairValidationReceipt):
            raise ProgressContractError("repair validation receipt is invalid")
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                if any(
                    prior.receipt_sha256 == receipt.receipt_sha256
                    for prior in self.receipts()
                ):
                    return receipt
                append_integrity_jsonl(
                    self.path,
                    receipt.to_dict(),
                    max_line_bytes=_MAX_LEDGER_LINE_BYTES,
                    label="repair validation ledger",
                    error_factory=ProgressContractError,
                )
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return receipt

    def find_matching(
        self,
        context: Mapping[str, Any],
        *,
        repair_revision: str,
    ) -> RepairValidationReceipt | None:
        expected = {
            "message_id": str(context.get("message_id") or ""),
            "content_sha256": str(context.get("content_sha256") or ""),
            "failure_fingerprint": str(
                context.get("failure_fingerprint") or ""
            ),
            "failure_revision": str(context.get("failure_revision") or ""),
            "failure_code": str(context.get("code") or ""),
            "failure_stage": str(context.get("stage") or ""),
        }
        for receipt in reversed(self.receipts()):
            if (
                all(getattr(receipt, key) == value for key, value in expected.items())
                and receipt.repair_revision == repair_revision
            ):
                return receipt
        return None

    def require(
        self,
        context: Mapping[str, Any],
        *,
        repair_revision: str,
    ) -> RepairValidationReceipt:
        receipt = self.find_matching(context, repair_revision=repair_revision)
        if receipt is None:
            raise ProgressContractError(
                "matching repair validation receipt is required"
            )
        return receipt


TARGETED_REPAIR_TESTS: dict[str, tuple[str, ...]] = {
    "kol_mailbox_exact_resume": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_mailbox.py",
        "tests/test_kol_semantic_bundle.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_wechat_official.py",
        "tests/test_kol_repair_validation.py",
        "-q",
    ),
    "kol_lv_download_recovery": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_writer_progress.py",
        "tests/test_kol_repair_validation.py",
        "-q",
        "-k",
        (
            "reviewed_historical_small_items_retire or "
            "filtered_image_repair_records_identity_bound_preview_derivative or "
            "filtered_image_repair_uses_read_only_preview_surface or "
            "existing_image_claim_uses_read_only_preview_after_zero_download_readback or "
            "new_filtered_image_claim_uses_preview_without_frontend_trigger or "
            "read_only_provider_reconciliation_wait_is_not_an_uncertain_effect or "
            "newer_repair_lifecycle_supersedes_old_fingerprint or "
            "repair_validation_accepts_exact_lv_download_recovery_profile"
        ),
    ),
    "kol_lv_text_image_source_run": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_semantic_bundle.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_daily.py",
        "-q",
        "-k",
        (
            "analysis_request_replay_backfills_first_observed_at or "
            "builder_allows_episode_relationship_source_binding or "
            "repair_validation_accepts_lv_text_image_source_run_profile or "
            "persisted_validated_bundle_is_reused or "
            "narrow_source_provider_failure_becomes_bounded_wait or "
            "subscription_decision_pipeline_provider_error_is_diagnostic"
        ),
    ),
    "kol_lv_text_image_browser_open": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "lv_text_image_browser_open_exposes_diagnostic or "
            "repair_validation_accepts_lv_text_image_browser_open_profile or "
            "repair_closure_accepts_lv_text_image_browser_open_profile"
        ),
    ),
    "kol_subscription_video_private_listing_validation": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "-q",
        "-k",
        (
            "private_scan_allows_slow_directory_settlement or "
            "private_scan_classifies_directory_failure or "
            "source_classifier_promotes_opencli_login_to_blocker or "
            "source_cli_narrow_runner_supports_subscription_video or "
            "repair_validation_accepts_subscription_private_listing_profile"
        ),
    ),
    "kol_subscription_video_browser_eval": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "private_scan_chunks_recursive_eval_below_opencli_deadline or "
            "private_scan_retries_one_preclaim_browser_eval_timeout or "
            "private_scan_reloads_one_bound_shell_before_second_read or "
            "opencli_json_classifies_cdp_timeout or "
            "narrow_source_failure_keeps_seven_state_contract or "
            "source_repair_validation_accepts_pending_resume or "
            "repair_validation_accepts_subscription_video_browser_eval_profile or "
            "repair_closure_accepts_subscription_video_browser_eval_profile or "
            "repair_closure_refreshes_pending_resume or "
            "repair_resume_persists_following_repair"
        ),
    ),
    "kol_subscription_video_browser_open": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "private_scan_retries_one_preclaim_browser_open_timeout or "
            "private_scan_retries_open_after_wrong_preclaim_readback or "
            "repair_validation_accepts_subscription_video_browser_open_profile or "
            "repair_closure_accepts_subscription_video_browser_open_profile"
        ),
    ),
    "kol_subscription_video_source_run": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_subscription_video.py",
        "tests/test_kol_decisions.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_netdisk_enrichment.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "semantic_duplicate_requires_receipted_household_and_paper_ledgers or "
            "no_trade_is_an_idempotent_book_decision or "
            "each_replay_uses_fresh_household_context or "
            "lv_transfer_unobserved_toast_waits_for_bound_receipt or "
            "lv_transfer_legacy_unobserved_blocker_requires_repair_revision or "
            "lv_transfer_legacy_observability_repair_runs_one_bound_probe or "
            "blocked_legacy_transfer_can_reenter_exact_reconciliation or "
            "lv_transfer_reopens_share_once_after_target_not_unique or "
            "lv_destination_triggered_claim_has_poll_deadline or "
            "source_cli_narrow_runner_supports_subscription_video or "
            "transcript_claim_replay_never_repeats_generation_interaction or "
            "source_repair_validation_accepts_pending_resume or "
            "repair_validation_accepts_subscription_video_source_run_profile or "
            "repair_validation_accepts_subscription_video_source_alias_profile or "
            "repair_closure_accepts_subscription_video_observability_profile_alias or "
            "repair_resume_persists_following_repair"
        ),
    ),
    "kol_shared_lv_listing_browser_eval": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "listing_recovers_once_after_detached_read_only_eval or "
            "existing_image_claim_uses_read_only_preview_after_zero_download_readback or "
            "new_filtered_image_claim_uses_preview_without_frontend_trigger or "
            "repair_validation_accepts_shared_lv_listing_browser_eval_profile or "
            "repair_closure_accepts_shared_lv_listing_browser_eval_profile"
        ),
    ),
    "kol_shared_lv_listing_validation": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_lv_subscription.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "browser_listing_recurses_without_parent_mtime_pruning_in_bounded_batches or "
            "repair_validation_accepts_shared_lv_listing_validation_profile or "
            "repair_closure_accepts_shared_lv_listing_validation_profile"
        ),
    ),
    "kol_xiaocao_wechat_live_source_run": (
        "env",
        "PYTHONPATH=src",
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/test_kol_capture.py",
        "tests/test_kol_daily.py",
        "tests/test_kol_repair_validation.py",
        "tests/test_kol_xiaocao_live.py",
        "tests/test_kol_xiaocao_wechat.py",
        "tests/test_kol_writer_progress.py",
        "-q",
        "-k",
        (
            "source_cli_narrow_runner_supports_xiaocao_wechat_live or "
            "xiaoetong_recorded_video_source_identity_is_stable or "
            "recorded_video_capture_uses_file_binding_not_stale_live_context or "
            "start_with_recorded_video_page_arms_file_bound_capture_without_source_job or "
            "start_rejects_recorded_video_without_media_file_binding or "
            "start_classifies_sniffer_candidate_baseline_failure or "
            "recorded_video_page_arms_bound_capture or "
            "existing_recorded_video_page_resolves_media_file_before_arming or "
            "runtime_initialization_defers_lianghui_config or "
            "narrow_source_user_action_keeps_seven_state_contract or "
            "source_repair_resume_follows_bound_xiaocao_cloud_handoff or "
            "repair_validation_accepts_xiaocao_wechat_source_profile or "
            "new_source_account_login_redirect_resolves_exact_page or "
            "bound_provider_block_waits_for_the_same_page or "
            "unbound_provider_block_fails_closed or "
            "account_login_state_is_authoritative_when_page_url_stays_bound or "
            "cloud_handoff_wait_has_durable_poll_deadline or "
            "compressed_capture_wait_has_durable_poll_deadline or "
            "pending_cloud_handoff_resumes_exact_job_after_stale_playback_state or "
            "repair_closure_accepts_xiaocao_wechat_source_profile"
        ),
    ),
}

_TARGETED_REPAIR_IMPLEMENTATION_PATHS: dict[str, frozenset[str]] = {
    "kol_mailbox_exact_resume": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/mailbox.py",
            "src/xiaocao/kol/semantic_bundle.py",
            "src/xiaocao/kol/writer_progress.py",
            "src/xiaocao/kol/wechat_official.py",
        }
    ),
    "kol_lv_download_recovery": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/lv_historical_retirement_20260808.json",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_lv_text_image_source_run": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/semantic_bundle.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_lv_text_image_browser_open": frozenset(
        {
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_subscription_video_private_listing_validation": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/subscription_video.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_subscription_video_browser_eval": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/subscription_video.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_subscription_video_browser_open": frozenset(
        {
            "src/xiaocao/kol/subscription_video.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_subscription_video_source_run": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/daily.py",
            "src/xiaocao/kol/decisions.py",
            "src/xiaocao/kol/household.py",
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/netdisk_enrichment.py",
            "src/xiaocao/kol/subscription_video.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_shared_lv_listing_browser_eval": frozenset(
        {
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_shared_lv_listing_validation": frozenset(
        {
            "src/xiaocao/kol/lv_subscription.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
    "kol_xiaocao_wechat_live_source_run": frozenset(
        {
            "scripts/kol_daily.py",
            "src/xiaocao/kol/daily.py",
            "src/xiaocao/kol/capture.py",
            "src/xiaocao/kol/xiaocao_live.py",
            "src/xiaocao/kol/xiaocao_wechat.py",
            "src/xiaocao/kol/writer_progress.py",
        }
    ),
}

_TARGETED_REPAIR_TEST_PATHS: dict[str, frozenset[str]] = {
    "kol_mailbox_exact_resume": frozenset(
        {
            "tests/test_kol_mailbox.py",
            "tests/test_kol_semantic_bundle.py",
            "tests/test_kol_daily.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_wechat_official.py",
        }
    ),
    "kol_lv_download_recovery": frozenset(
        {
            "tests/test_kol_daily.py",
            "tests/test_kol_lv_subscription.py",
            "tests/test_kol_writer_progress.py",
            "tests/test_kol_repair_validation.py",
        }
    ),
    "kol_lv_text_image_source_run": frozenset(
        {
            "tests/test_kol_daily.py",
            "tests/test_kol_lv_subscription.py",
            "tests/test_kol_semantic_bundle.py",
            "tests/test_kol_repair_validation.py",
        }
    ),
    "kol_lv_text_image_browser_open": frozenset(
        {
            "tests/test_kol_lv_subscription.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_subscription_video_private_listing_validation": frozenset(
        {
            "tests/test_kol_subscription_video.py",
            "tests/test_kol_daily.py",
            "tests/test_kol_repair_validation.py",
        }
    ),
    "kol_subscription_video_browser_eval": frozenset(
        {
            "tests/test_kol_daily.py",
            "tests/test_kol_subscription_video.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_subscription_video_browser_open": frozenset(
        {
            "tests/test_kol_subscription_video.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_subscription_video_source_run": frozenset(
        {
            "tests/test_kol_subscription_video.py",
            "tests/test_kol_decisions.py",
            "tests/test_kol_daily.py",
            "tests/test_kol_netdisk_enrichment.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_shared_lv_listing_browser_eval": frozenset(
        {
            "tests/test_kol_lv_subscription.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_shared_lv_listing_validation": frozenset(
        {
            "tests/test_kol_lv_subscription.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
    "kol_xiaocao_wechat_live_source_run": frozenset(
        {
            "tests/test_kol_capture.py",
            "tests/test_kol_daily.py",
            "tests/test_kol_repair_validation.py",
            "tests/test_kol_xiaocao_live.py",
            "tests/test_kol_xiaocao_wechat.py",
            "tests/test_kol_writer_progress.py",
        }
    ),
}

_LV_DOWNLOAD_REPAIR_PROFILE = "kol_lv_download_recovery"
_LV_DOWNLOAD_REPAIR_PROFILE_ALIASES = frozenset({
    _LV_DOWNLOAD_REPAIR_PROFILE,
    "kol_lv_text_image_browser_download_recovery",
    "kol_lv_text_image_provider_download_link",
    "kol_lv_text_image_provider_preview_reconciliation",
})
_LV_DOWNLOAD_REPAIR_CODES = frozenset({
    "blocked_download_frame_missing",
    "provider_download_filtered",
    "provider_download_link_errno_2",
    "provider_frontend_target_not_ready",
    "detached_mid_command",
    "opencli_command_failed",
    "opencli_timeout",
    "uncertain_effect_lacks_readback_binding",
})


def _canonical_lv_download_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "lv_text_image"
        and str(context.get("targeted_test_profile") or "")
        in _LV_DOWNLOAD_REPAIR_PROFILE_ALIASES
        and str(context.get("code") or "") in _LV_DOWNLOAD_REPAIR_CODES
        and str(context.get("stage") or "")
        in {
            "browser_download_recovery",
            "provider_download_link",
            "provider_download_trigger",
            "provider_preview_reconciliation",
        }
    ):
        return _LV_DOWNLOAD_REPAIR_PROFILE
    return None


_LV_TEXT_IMAGE_SOURCE_REPAIR_PROFILE = "kol_lv_text_image_source_run"


def _canonical_lv_text_image_source_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "lv_text_image"
        and str(context.get("targeted_test_profile") or "")
        == _LV_TEXT_IMAGE_SOURCE_REPAIR_PROFILE
        and str(context.get("category") or "") == "source_error"
        and str(context.get("code") or "")
        == "source_temporarily_unavailable"
        and str(context.get("stage") or "") == "source_run"
    ):
        return _LV_TEXT_IMAGE_SOURCE_REPAIR_PROFILE
    return None


_LV_TEXT_IMAGE_BROWSER_OPEN_REPAIR_PROFILE = (
    "kol_lv_text_image_browser_open"
)


def _canonical_lv_text_image_browser_open_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "lv_text_image"
        and str(context.get("targeted_test_profile") or "")
        == _LV_TEXT_IMAGE_BROWSER_OPEN_REPAIR_PROFILE
        and (
            str(context.get("category") or ""),
            str(context.get("code") or ""),
        )
        in {
            ("transport_error", "opencli_command_failed"),
            ("timeout", "opencli_timeout"),
        }
        and str(context.get("stage") or "") == "browser_open"
    ):
        return _LV_TEXT_IMAGE_BROWSER_OPEN_REPAIR_PROFILE
    return None


_SUBSCRIPTION_PRIVATE_LISTING_REPAIR_PROFILE = (
    "kol_subscription_video_private_listing_validation"
)
_SUBSCRIPTION_PRIVATE_LISTING_REPAIR_CODES = frozenset({
    "private_listing_incomplete",
    "private_listing_timeout",
    "private_directory_load_timeout",
    "private_wrong_browser_origin",
    "private_wrong_directory",
    "private_listing_bounds_exceeded",
    "private_directory_page_bound_exceeded",
})


def _canonical_subscription_private_listing_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "subscription_video"
        and str(context.get("targeted_test_profile") or "")
        == _SUBSCRIPTION_PRIVATE_LISTING_REPAIR_PROFILE
        and str(context.get("code") or "")
        in _SUBSCRIPTION_PRIVATE_LISTING_REPAIR_CODES
        and str(context.get("stage") or "") == "private_listing_validation"
    ):
        return _SUBSCRIPTION_PRIVATE_LISTING_REPAIR_PROFILE
    return None


_SHARED_LV_LISTING_BROWSER_EVAL_REPAIR_PROFILE = (
    "kol_shared_lv_listing_browser_eval"
)
# The LV image adapter reports failed OpenCLI commands before any claim;
# repeated retries remain bound to the latest exact fingerprint, including
# read-only listing evaluation failures that recover on the next read.
_SHARED_LV_LISTING_BROWSER_EVAL_CODES = frozenset({
    "detached_mid_command",
    "opencli_command_failed",
})

_SHARED_LV_LISTING_VALIDATION_REPAIR_PROFILE = (
    "kol_shared_lv_listing_validation"
)

_SUBSCRIPTION_VIDEO_BROWSER_EVAL_REPAIR_PROFILE = (
    "kol_subscription_video_browser_eval"
)
_SUBSCRIPTION_VIDEO_BROWSER_OPEN_REPAIR_PROFILE = (
    "kol_subscription_video_browser_open"
)


def _canonical_subscription_video_browser_open_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "subscription_video"
        and str(context.get("targeted_test_profile") or "")
        == _SUBSCRIPTION_VIDEO_BROWSER_OPEN_REPAIR_PROFILE
        and (
            str(context.get("category") or ""),
            str(context.get("code") or ""),
        )
        in {
            ("timeout", "opencli_timeout"),
            ("transport_error", "opencli_command_failed"),
        }
        and str(context.get("stage") or "") == "browser_open"
    ):
        return _SUBSCRIPTION_VIDEO_BROWSER_OPEN_REPAIR_PROFILE
    return None


def _canonical_subscription_video_browser_eval_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if (
        str(context.get("adapter") or "") == "subscription_video"
        and str(context.get("targeted_test_profile") or "")
        == _SUBSCRIPTION_VIDEO_BROWSER_EVAL_REPAIR_PROFILE
        and str(context.get("code") or "")
        in {
            "opencli_command_failed",
            "opencli_cdp_timeout",
            "opencli_timeout",
        }
        and str(context.get("stage") or "") == "browser_eval"
    ):
        return _SUBSCRIPTION_VIDEO_BROWSER_EVAL_REPAIR_PROFILE
    return None


def _canonical_shared_lv_listing_browser_eval_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    adapter = str(context.get("adapter") or "")
    if (
        adapter in {"lv_text_image", "subscription_video"}
        and str(context.get("targeted_test_profile") or "")
        == f"kol_{adapter}_browser_eval"
        and str(context.get("category") or "") == "transport_error"
        and str(context.get("code") or "")
        in _SHARED_LV_LISTING_BROWSER_EVAL_CODES
        and str(context.get("stage") or "") == "browser_eval"
    ):
        return _SHARED_LV_LISTING_BROWSER_EVAL_REPAIR_PROFILE
    return None


_XIAOCAO_WECHAT_SOURCE_REPAIR_PROFILE = (
    "kol_xiaocao_wechat_live_source_run"
)
_XIAOCAO_WECHAT_COMPRESSED_CAPTURE_REPAIR_PROFILE = (
    "kol_xiaocao_wechat_live_compressed_capture"
)
_XIAOCAO_WECHAT_CLOUD_HANDOFF_REPAIR_PROFILE = (
    "kol_xiaocao_wechat_live_cloud_handoff"
)
_SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE = (
    "kol_subscription_video_source_run"
)
_SUBSCRIPTION_VIDEO_OBSERVABILITY_REPAIR_PROFILE_ALIAS = (
    "kol_subscription_video_cloud_transfer_confirmation"
)
_SUBSCRIPTION_VIDEO_CLOUD_ENRICHMENT_REPAIR_PROFILE = (
    "kol_subscription_video_cloud_enrichment"
)
_SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE_ALIASES = frozenset({
    _SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE,
    _SUBSCRIPTION_VIDEO_OBSERVABILITY_REPAIR_PROFILE_ALIAS,
    "kol_subscription_video_source_recovery",
    "kol_subscription_video_source_acquisition",
    _SUBSCRIPTION_VIDEO_CLOUD_ENRICHMENT_REPAIR_PROFILE,
})


def _canonical_subscription_video_source_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    failure = (
        str(context.get("category") or ""),
        str(context.get("code") or ""),
        str(context.get("stage") or ""),
    )
    if (
        str(context.get("adapter") or "") == "subscription_video"
        and str(context.get("targeted_test_profile") or "")
        in _SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE_ALIASES
        and failure
        in {
            (
                "source_error",
                "source_temporarily_unavailable",
                "source_run",
            ),
            (
                "item_error",
                "item_processing_failed",
                "source_acquisition",
            ),
            (
                "internal_state_error",
                "cloud_transfer_unobserved_reconciled_absent",
                "source_run",
            ),
            (
                "provider_contract_error",
                "lv_transfer_response_unobserved_legacy",
                "cloud_transfer_confirmation",
            ),
            (
                "internal_state_error",
                "progress_deadline_missing",
                "cloud_enrichment",
            ),
        }
    ):
        return _SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE
    return None


def _canonical_shared_lv_listing_validation_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    adapter = str(context.get("adapter") or "")
    if (
        adapter in {"lv_text_image", "subscription_video"}
        and str(context.get("targeted_test_profile") or "")
        == f"kol_{adapter}_listing_validation"
        and str(context.get("category") or "") == "incomplete_scan"
        and str(context.get("code") or "")
        in {
            "share_metadata_missing",
            "share_root_template_missing",
            "share_directory_template_missing",
        }
        and str(context.get("stage") or "") == "listing_validation"
    ):
        return _SHARED_LV_LISTING_VALIDATION_REPAIR_PROFILE
    return None


def _canonical_xiaocao_wechat_source_repair_profile(
    context: Mapping[str, Any],
) -> str | None:
    if str(context.get("adapter") or "") != "xiaocao_wechat_live":
        return None
    declared_profile = str(context.get("targeted_test_profile") or "")
    failure = (
        str(context.get("category") or ""),
        str(context.get("code") or ""),
        str(context.get("stage") or ""),
    )
    if (
        declared_profile == _XIAOCAO_WECHAT_SOURCE_REPAIR_PROFILE
        and failure
        == (
            "source_error",
            "source_temporarily_unavailable",
            "source_run",
        )
    ) or (
        declared_profile
        == _XIAOCAO_WECHAT_COMPRESSED_CAPTURE_REPAIR_PROFILE
        and failure
        == (
            "internal_state_error",
            "progress_deadline_missing",
            "compressed_capture",
        )
    ) or (
        declared_profile == _XIAOCAO_WECHAT_CLOUD_HANDOFF_REPAIR_PROFILE
        and failure
        == (
            "internal_state_error",
            "progress_deadline_missing",
            "cloud_handoff",
        )
    ):
        return _XIAOCAO_WECHAT_SOURCE_REPAIR_PROFILE
    return None


class RepairValidationService:
    """Resolve, test, and persist one exact repository repair proof."""

    def __init__(
        self,
        repository_root: Path | str,
        *,
        ledger: RepairValidationLedger,
        git_runner: Callable[[tuple[str, ...]], Any] | None = None,
        test_runner: Callable[[tuple[str, ...]], Any] | None = None,
        now: Callable[[], str] | None = None,
    ):
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.ledger = ledger
        self.git_runner = git_runner or self._run_git
        self.test_runner = test_runner or self._run_tests
        self.now = now or (
            lambda: datetime.now().astimezone().isoformat(timespec="seconds")
        )

    def _run_git(self, command: tuple[str, ...]) -> Any:
        return subprocess.run(
            ("git", *command),
            cwd=self.repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=15,
        )

    def _run_tests(self, command: tuple[str, ...]) -> Any:
        return subprocess.run(
            command,
            cwd=self.repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=300,
        )

    @staticmethod
    def _output(result: Any) -> str:
        return "\n".join(
            value
            for value in (
                str(getattr(result, "stdout", "") or ""),
                str(getattr(result, "stderr", "") or ""),
            )
            if value
        )

    def _git_value(self, command: tuple[str, ...], *, field_name: str) -> str:
        result = self.git_runner(command)
        if getattr(result, "returncode", 1) != 0:
            raise ProgressContractError(f"repair validation {field_name} readback failed")
        value = str(getattr(result, "stdout", "") or "").strip()
        if not value:
            raise ProgressContractError(f"repair validation {field_name} is missing")
        return value

    def _expected_profile(self, context: Mapping[str, Any]) -> str:
        lv_profile = _canonical_lv_download_repair_profile(context)
        if lv_profile is not None:
            return lv_profile
        lv_source_profile = _canonical_lv_text_image_source_repair_profile(
            context
        )
        if lv_source_profile is not None:
            return lv_source_profile
        lv_browser_open_profile = (
            _canonical_lv_text_image_browser_open_repair_profile(context)
        )
        if lv_browser_open_profile is not None:
            return lv_browser_open_profile
        subscription_profile = (
            _canonical_subscription_private_listing_repair_profile(context)
        )
        if subscription_profile is not None:
            return subscription_profile
        subscription_browser_open_profile = (
            _canonical_subscription_video_browser_open_repair_profile(
                context
            )
        )
        if subscription_browser_open_profile is not None:
            return subscription_browser_open_profile
        subscription_browser_eval_profile = (
            _canonical_subscription_video_browser_eval_repair_profile(context)
        )
        if subscription_browser_eval_profile is not None:
            return subscription_browser_eval_profile
        browser_eval_profile = (
            _canonical_shared_lv_listing_browser_eval_repair_profile(context)
        )
        if browser_eval_profile is not None:
            return browser_eval_profile
        listing_validation_profile = (
            _canonical_shared_lv_listing_validation_repair_profile(context)
        )
        if listing_validation_profile is not None:
            return listing_validation_profile
        xiaocao_wechat_profile = (
            _canonical_xiaocao_wechat_source_repair_profile(context)
        )
        if xiaocao_wechat_profile is not None:
            return xiaocao_wechat_profile
        subscription_source_profile = (
            _canonical_subscription_video_source_repair_profile(context)
        )
        if subscription_source_profile is not None:
            return subscription_source_profile
        if (
            str(context.get("category") or "")
            in {"configuration", "source_error", "timeout"}
            and str(context.get("code") or "").startswith("wechat_official_")
            and str(context.get("stage") or "").startswith("wechat_official_")
        ):
            return "kol_mailbox_exact_resume"
        if (
            str(context.get("stage") or "").startswith("mailbox_")
            and str(context.get("category") or "")
            in {
                "contract_error",
                "schema_error",
                "control_plane_handler_error",
                "processor_error",
            }
        ) or (
            str(context.get("category") or "") == "processor_error"
            and str(context.get("stage") or "") == "business_processing"
        ):
            return "kol_mailbox_exact_resume"
        raise ProgressContractError(
            "repair validation has no repository-owned targeted test profile"
        )

    def resolve_head(self) -> str:
        revision = self._git_value(
            ("rev-parse", "--verify", "HEAD^{commit}"),
            field_name="HEAD",
        )
        if not _HEX_40.fullmatch(revision):
            raise ProgressContractError("repair validation HEAD is invalid")
        return revision

    def require_current(
        self,
        context: Mapping[str, Any],
        *,
        repair_revision: str,
    ) -> RepairValidationReceipt:
        """Require a receipt whose branch readback still names current HEAD."""

        receipt = self.ledger.require(
            context,
            repair_revision=repair_revision,
        )
        if receipt.targeted_test_profile != self._expected_profile(context):
            raise ProgressContractError(
                "repair validation targeted test profile changed"
            )
        if self.resolve_head() != repair_revision:
            raise ProgressContractError("repair revision is not current HEAD")
        branch = self._git_value(
            ("branch", "--show-current"),
            field_name="target branch",
        )
        remote_revision = self._git_value(
            (
                "rev-parse",
                "--verify",
                f"origin/{branch}^{{commit}}",
            ),
            field_name="target branch remote",
        )
        if (
            receipt.target_branch != branch
            or receipt.target_branch_revision != remote_revision
        ):
            raise ProgressContractError(
                "repair validation target branch readback changed"
            )
        return receipt

    def validate(
        self,
        context: Mapping[str, Any],
        *,
        repair_revision: str | None = None,
    ) -> RepairValidationReceipt:
        message_id = str(context.get("message_id") or "")
        content_sha256 = str(context.get("content_sha256") or "")
        failure_fingerprint = str(context.get("failure_fingerprint") or "")
        failure_revision = str(context.get("failure_revision") or "")
        failure_code = str(context.get("code") or "")
        failure_stage = str(context.get("stage") or "")
        _sha256(message_id, field_name="message_id")
        _sha256(content_sha256, field_name="content_sha256")
        _sha256(failure_fingerprint, field_name="failure_fingerprint")
        _revision(failure_revision, field_name="failure_revision")
        profile = self._expected_profile(context)
        declared_profile = str(context.get("targeted_test_profile") or "")
        if (
            declared_profile
            and declared_profile != profile
            and not (
                profile == _LV_DOWNLOAD_REPAIR_PROFILE
                and declared_profile in _LV_DOWNLOAD_REPAIR_PROFILE_ALIASES
            )
            and not (
                profile == _SHARED_LV_LISTING_BROWSER_EVAL_REPAIR_PROFILE
                and declared_profile
                in {
                    "kol_lv_text_image_browser_eval",
                    "kol_subscription_video_browser_eval",
                }
            )
            and not (
                profile == _XIAOCAO_WECHAT_SOURCE_REPAIR_PROFILE
                and declared_profile
                in {
                    _XIAOCAO_WECHAT_COMPRESSED_CAPTURE_REPAIR_PROFILE,
                    _XIAOCAO_WECHAT_CLOUD_HANDOFF_REPAIR_PROFILE,
                }
            )
            and not (
                profile == _SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE
                and declared_profile
                in _SUBSCRIPTION_VIDEO_SOURCE_REPAIR_PROFILE_ALIASES
            )
            and not (
                profile == _SHARED_LV_LISTING_VALIDATION_REPAIR_PROFILE
                and declared_profile
                in {
                    "kol_lv_text_image_listing_validation",
                    "kol_subscription_video_listing_validation",
                }
            )
        ):
            raise ProgressContractError("repair validation test profile changed")
        resolved_revision = repair_revision or self.resolve_head()
        _revision(resolved_revision, field_name="repair_revision")
        head = self.resolve_head()
        if resolved_revision != head:
            raise ProgressContractError("repair revision is not current HEAD")
        target_branch = self._git_value(
            ("branch", "--show-current"),
            field_name="target branch",
        )
        _safe_branch(target_branch, field_name="target_branch")
        target_branch_revision = self._git_value(
            (
                "rev-parse",
                "--verify",
                f"origin/{target_branch}^{{commit}}",
            ),
            field_name="target branch remote",
        )
        if target_branch_revision != resolved_revision:
            raise ProgressContractError("repair revision is not pushed")
        changed_files_result = self.git_runner(
            ("diff-tree", "--no-commit-id", "--name-only", "-r", resolved_revision)
        )
        if getattr(changed_files_result, "returncode", 1) != 0:
            raise ProgressContractError("repair commit file readback failed")
        changed_files = {
            line.strip()
            for line in str(getattr(changed_files_result, "stdout", "") or "").splitlines()
            if line.strip()
        }
        if not changed_files & _TARGETED_REPAIR_IMPLEMENTATION_PATHS[profile]:
            raise ProgressContractError("repair commit is unrelated to target")
        if not changed_files & _TARGETED_REPAIR_TEST_PATHS[profile]:
            raise ProgressContractError(
                "repair commit lacks a targeted regression change"
            )
        message_result = self.git_runner(
            ("show", "-s", "--format=%B", resolved_revision)
        )
        if getattr(message_result, "returncode", 1) != 0:
            raise ProgressContractError("repair commit message readback failed")
        trailers = {
            line.strip()
            for line in str(
                getattr(message_result, "stdout", "") or ""
            ).splitlines()
        }
        if f"Repair-Fingerprint: {failure_fingerprint}" not in trailers:
            raise ProgressContractError(
                "repair commit does not bind the failure fingerprint"
            )
        lineage = (
            "merge-base",
            "--is-ancestor",
            failure_revision,
            resolved_revision,
        )
        ancestry = self.git_runner(lineage)
        if getattr(ancestry, "returncode", 1) != 0:
            raise ProgressContractError("repair revision is outside failure lineage")
        command = TARGETED_REPAIR_TESTS[profile]
        result = self.test_runner(command)
        output = self._output(result)
        if getattr(result, "returncode", 1) != 0:
            raise ProgressContractError("repair validation targeted test failed")
        command_digest = _digest(command)
        result_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        receipt = RepairValidationReceipt.create(
            message_id=message_id,
            content_sha256=content_sha256,
            failure_fingerprint=failure_fingerprint,
            failure_revision=failure_revision,
            failure_code=failure_code,
            failure_stage=failure_stage,
            repair_revision=resolved_revision,
            target_branch=target_branch,
            target_branch_revision=target_branch_revision,
            targeted_test_profile=profile,
            test_command_digest=command_digest,
            test_result_sha256=result_digest,
            validated_at=self.now(),
        )
        return self.ledger.append(receipt)


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
        required = STATUS_REQUIRED_FIELDS[self.status]
        missing = sorted(required - set(details))
        if missing:
            raise ProgressContractError(
                f"{self.status} lacks required field {', '.join(missing)}"
            )
        allowed = required | {"claim_receipt_summary"}
        if self.status == "wait_until":
            allowed = allowed | {"narrow_resume_surface"}
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
            if "narrow_resume_surface" in details:
                _safe_identity(
                    details["narrow_resume_surface"],
                    field_name="narrow_resume_surface",
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
        narrow_resume_surface: str | None = None,
    ) -> "WriterProgress":
        resume_binding = (
            {"narrow_resume_surface": narrow_resume_surface}
            if narrow_resume_surface is not None
            else {}
        )
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
            **resume_binding,
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


def _completed_source_identity(
    adapter: str,
    events: list[dict[str, Any]],
) -> str:
    identities = list(dict.fromkeys(
        str(event.get("event_id") or "").strip()
        for event in events
        if _SAFE_IDENTITY.fullmatch(
            str(event.get("event_id") or "").strip()
        )
    ))
    return identities[0] if len(identities) == 1 else f"{adapter}:source"


def _progress_claim_summary(outcome: Mapping[str, Any]) -> dict[str, int]:
    supplied = outcome.get("claim_receipt_summary")
    if isinstance(supplied, Mapping):
        return _claim_receipt_summary(supplied)
    return {
        "claim_count": 0,
        "receipt_count": 0,
        "uncertain_effect_count": 0,
    }


def normalize_source_result(
    adapter: str,
    outcome: Mapping[str, Any],
    *,
    failure_revision: str,
    provider_contract_version: str,
    user_action: Mapping[str, Any] | None = None,
) -> WriterProgress:
    """Normalize one source result into the finite writer state machine."""

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
            item_identity=_completed_source_identity(adapter_name, events),
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
        raise ProgressContractError("source result status cannot be normalized")
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
    if not (item or {}).get("stage") and failure.get("stage"):
        stage = _safe_token(failure["stage"], field_name="stage")
    category = str(
        failure.get("category")
        or (item or {}).get("category")
        or "internal_state_error"
    )
    code = str(
        failure.get("code")
        or (item or {}).get("code")
        or "progress_deadline_missing"
    )
    if category == "uncertain_state" or summary["uncertain_effect_count"]:
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
        maximum = max(
            attempted,
            int(
                (item or {}).get("trigger_attempt_maximum")
                or max(3, attempted)
            ),
        )
        return WriterProgress.wait_until(
            item_identity=item_identity,
            category=category,
            code=code,
            stage=stage,
            deadline=deadline,
            attempt_budget={"attempted": attempted, "maximum": maximum},
            narrow_resume_surface=f"{adapter_name}:{item_identity}",
            claim_receipt_summary=summary,
        )
    if not failure and outcome.get("repair_required") is not True:
        category = "internal_state_error"
        code = "progress_deadline_missing"
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

    def report(
        self,
        daily_events: list[Mapping[str, Any]],
        *,
        period_start: str,
        period_end: str,
    ) -> dict[str, Any]:
        return build_convergence_report(
            daily_events,
            self.events(),
            period_start=period_start,
            period_end=period_end,
        )

    def acceptance_report(
        self,
        daily_events: list[Mapping[str, Any]],
        *,
        as_of: str,
    ) -> dict[str, Any]:
        """Build the final acceptance report from the append-only ledger."""

        return build_stability_acceptance_report(
            daily_events,
            self.events(),
            as_of=as_of,
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

    @staticmethod
    def _latest_repair_lifecycle_by_target(
        rows: list[dict[str, Any]],
    ) -> tuple[
        dict[str, tuple[tuple[str, str], dict[str, Any]]],
        dict[tuple[str, str], tuple[int, dict[str, Any]]],
    ]:
        """Bind repair lifecycle events to their exact narrow resume target.

        A diagnosis may become more precise while the same item stays on the
        same narrow resume surface, producing a new failure fingerprint. Once
        that newer lifecycle is closed or resumed, an older fingerprint for
        the same target must not become active again.
        """

        observation_by_fingerprint: dict[
            str, tuple[tuple[str, str], dict[str, Any]]
        ] = {}
        latest_by_target: dict[
            tuple[str, str], tuple[int, dict[str, Any]]
        ] = {}
        for index, row in enumerate(rows):
            fingerprint = str(row.get("failure_fingerprint") or "")
            if not fingerprint:
                continue
            if row.get("event") == "failure_observed":
                progress_value = row.get("progress")
                if not isinstance(progress_value, Mapping):
                    raise ProgressContractError(
                        "active convergence row lacks persisted progress"
                    )
                progress = WriterProgress.from_dict(progress_value)
                target = (
                    str(progress.failure["adapter"]),
                    str(progress.details["narrow_resume_surface"]),
                )
                observation_by_fingerprint[fingerprint] = (target, row)
            binding = observation_by_fingerprint.get(fingerprint)
            if binding is not None:
                latest_by_target[binding[0]] = (index, row)
        return observation_by_fingerprint, latest_by_target

    def active_progress(self, adapter: str) -> WriterProgress | None:
        """Recover the latest unclosed repair owned by one adapter."""

        adapter_name = _safe_token(adapter, field_name="adapter")
        rows = self.events()
        _observations, latest_by_target = (
            self._latest_repair_lifecycle_by_target(rows)
        )
        for (target_adapter, _surface), (_index, row) in sorted(
            latest_by_target.items(),
            key=lambda item: item[1][0],
            reverse=True,
        ):
            if target_adapter != adapter_name:
                continue
            if row.get("event") != "failure_observed":
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
        observation_by_fingerprint, latest_by_target = (
            self._latest_repair_lifecycle_by_target(rows)
        )
        for (target_adapter, _surface), (_index, closure) in sorted(
            latest_by_target.items(),
            key=lambda item: item[1][0],
            reverse=True,
        ):
            if target_adapter != adapter_name:
                continue
            if closure.get("event") != "repair_closed":
                continue
            fingerprint = str(closure.get("failure_fingerprint") or "")
            binding = observation_by_fingerprint.get(fingerprint)
            if binding is None:
                raise ProgressContractError("repair closure lost its observation")
            _target, observation = binding
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
            resume = self._append(
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
            if following.status == "repair_required":
                self._append(
                    {
                        "event": "failure_observed",
                        "observed_at": self._now(),
                        "slot": slot,
                        "failure": following.failure,
                        "failure_fingerprint": (
                            following.failure_fingerprint
                        ),
                        "ownership": following.ownership,
                        "progress": following.to_dict(),
                        "retryability": following.retryability,
                    }
                )
            return resume

    def close_repair(
        self,
        failure_fingerprint: str,
        *,
        repair_receipt: RepairValidationReceipt | Mapping[str, Any],
        validation_ledger: RepairValidationLedger,
        slot: str,
    ) -> dict[str, Any]:
        digest = _sha256(
            failure_fingerprint,
            field_name="failure_fingerprint",
        )
        if not isinstance(validation_ledger, RepairValidationLedger):
            raise ProgressContractError(
                "repair closure requires its validation ledger"
            )
        receipt_value = (
            repair_receipt.to_dict()
            if isinstance(repair_receipt, RepairValidationReceipt)
            else dict(repair_receipt)
        )
        receipt = RepairValidationReceipt.from_dict(receipt_value)
        if receipt.failure_fingerprint != digest:
            raise ProgressContractError("repair receipt fingerprint does not match")
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
            expected_profile = str(
                open_progress.details["targeted_test_profile"]
            )
            canonical_lv_profile = _canonical_lv_download_repair_profile({
                "adapter": open_progress.failure["adapter"],
                "targeted_test_profile": expected_profile,
                "code": open_progress.failure["code"],
                "stage": open_progress.failure["stage"],
            })
            if canonical_lv_profile is not None:
                expected_profile = canonical_lv_profile
            canonical_subscription_browser_eval_profile = (
                _canonical_subscription_video_browser_eval_repair_profile({
                    "adapter": open_progress.failure["adapter"],
                    "targeted_test_profile": expected_profile,
                    "code": open_progress.failure["code"],
                    "stage": open_progress.failure["stage"],
                })
            )
            if canonical_subscription_browser_eval_profile is not None:
                expected_profile = canonical_subscription_browser_eval_profile
            else:
                canonical_browser_eval_profile = (
                    _canonical_shared_lv_listing_browser_eval_repair_profile({
                        "adapter": open_progress.failure["adapter"],
                        "targeted_test_profile": expected_profile,
                        "category": open_progress.failure["category"],
                        "code": open_progress.failure["code"],
                        "stage": open_progress.failure["stage"],
                    })
                )
                if canonical_browser_eval_profile is not None:
                    expected_profile = canonical_browser_eval_profile
            canonical_listing_validation_profile = (
                _canonical_shared_lv_listing_validation_repair_profile({
                    "adapter": open_progress.failure["adapter"],
                    "targeted_test_profile": expected_profile,
                    "category": open_progress.failure["category"],
                    "code": open_progress.failure["code"],
                    "stage": open_progress.failure["stage"],
                })
            )
            if canonical_listing_validation_profile is not None:
                expected_profile = canonical_listing_validation_profile
            canonical_xiaocao_wechat_profile = (
                _canonical_xiaocao_wechat_source_repair_profile({
                    "adapter": open_progress.failure["adapter"],
                    "targeted_test_profile": expected_profile,
                    "category": open_progress.failure["category"],
                    "code": open_progress.failure["code"],
                    "stage": open_progress.failure["stage"],
                })
            )
            if canonical_xiaocao_wechat_profile is not None:
                expected_profile = canonical_xiaocao_wechat_profile
            canonical_subscription_source_profile = (
                _canonical_subscription_video_source_repair_profile({
                    "adapter": open_progress.failure["adapter"],
                    "targeted_test_profile": expected_profile,
                    "category": open_progress.failure["category"],
                    "code": open_progress.failure["code"],
                    "stage": open_progress.failure["stage"],
                })
            )
            if canonical_subscription_source_profile is not None:
                expected_profile = canonical_subscription_source_profile
            if (
                receipt.targeted_test_profile
                != expected_profile
            ):
                raise ProgressContractError(
                    "repair receipt test profile does not match open repair"
                )
            failure = open_progress.failure
            if (
                receipt.failure_revision != failure["failure_revision"]
                or receipt.failure_code != failure["code"]
                or receipt.failure_stage != failure["stage"]
            ):
                raise ProgressContractError(
                    "repair receipt does not match the open failure"
                )
            persisted = validation_ledger.find_matching(
                {
                    "message_id": receipt.message_id,
                    "content_sha256": receipt.content_sha256,
                    "failure_fingerprint": digest,
                    "failure_revision": receipt.failure_revision,
                    "code": receipt.failure_code,
                    "stage": receipt.failure_stage,
                },
                repair_revision=receipt.repair_revision,
            )
            if persisted != receipt:
                raise ProgressContractError(
                    "repair receipt is not present in the validation ledger"
                )
            latest_matching = [
                row
                for row in self.events()
                if row.get("failure_fingerprint") == digest
            ][-1]
            if latest_matching.get("event") == "repair_closed":
                if (
                    latest_matching.get("repair_receipt")
                    == receipt.to_dict()
                ):
                    return latest_matching
            elif latest_matching.get("event") != "failure_observed":
                raise ProgressContractError("repair is not currently open")
            return self._append(
                {
                    "event": "repair_closed",
                    "closed_at": self._now(),
                    "slot": slot,
                    "failure_fingerprint": digest,
                    "repair_receipt": receipt.to_dict(),
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

    def record_peer_gate(
        self,
        audit: Mapping[str, Any],
        *,
        slot: str | None = None,
    ) -> dict[str, Any]:
        """Persist only credential-safe peer-gate counts and latency."""

        attempt_count = audit.get("attempt_count")
        if attempt_count is None:
            attempt_count = int(audit.get("list_attempt_count") or 0) + int(
                audit.get("read_thread_attempt_count") or 0
            )
        elapsed_ms = audit.get("elapsed_ms", 0)
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 0
            or isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, int)
            or elapsed_ms < 0
        ):
            raise ProgressContractError("peer gate audit counts are invalid")
        if slot is not None:
            _timezone_aware(slot, field_name="slot")
        with self._locked():
            return self._append(
                {
                    "event": "peer_gate_observed",
                    "observed_at": self._now(),
                    "slot": slot,
                    "attempt_count": attempt_count,
                    "elapsed_ms": elapsed_ms,
                    "gate_result": _safe_token(
                        audit.get("gate_result") or "unknown",
                        field_name="gate_result",
                    ),
                }
            )

    def record_rollout_readback(
        self,
        readback: "RolloutReadback",
        *,
        slot: str,
        baseline: Mapping[str, Any],
        restart_after_failed_acceptance: bool = False,
    ) -> dict[str, Any]:
        """Record an accepted rollout and start its measured window."""

        if not isinstance(readback, RolloutReadback) or not readback.accepted:
            raise ProgressContractError("rollout readback is not accepted")
        _timezone_aware(slot, field_name="slot")
        if not isinstance(baseline, Mapping):
            raise ProgressContractError("rollout baseline must be an object")
        if not isinstance(restart_after_failed_acceptance, bool):
            raise ProgressContractError(
                "restart_after_failed_acceptance must be boolean"
            )
        safe_baseline = {
            str(key): value for key, value in baseline.items()
            if str(key) in {
                "failure_fingerprints",
                "repair_required",
                "repair_closed",
                "generic_waits",
                "runner_starts",
                "side_effect_reconciliations",
                "duplicate_effect_findings",
                "known_failure_fingerprints",
            }
        }
        if "known_failure_fingerprints" in safe_baseline:
            raw_fingerprints = safe_baseline["known_failure_fingerprints"]
            if not isinstance(raw_fingerprints, list):
                raise ProgressContractError(
                    "known_failure_fingerprints must be a list"
                )
            safe_baseline["known_failure_fingerprints"] = sorted({
                _sha256(value, field_name="known failure fingerprint")
                for value in raw_fingerprints
            })
        with self._locked():
            existing = [
                row for row in self.events()
                if row.get("event") == "rollout_readback"
            ]
            if existing and not restart_after_failed_acceptance:
                raise ProgressContractError("rollout readback already recorded")
            recorded_at = self._now()
            return self._append(
                {
                    "event": "rollout_readback",
                    "observed_at": recorded_at,
                    "slot": slot,
                    "readback": readback.to_dict(),
                    "baseline": safe_baseline,
                    "stability_window_start": recorded_at,
                    "restart_after_failed_acceptance": (
                        restart_after_failed_acceptance
                    ),
                }
            )


@dataclass(frozen=True)
class RolloutReadback:
    """Credential-safe proof that one writer can own the production rollout."""

    automation_id: str
    writer_task_id: str
    target_revision: str
    active_writer_count: int
    duplicate_automation_count: int
    automation_owner: str
    automation_readback: bool
    worktree_protected: bool
    dependencies_ready: bool
    private_config_ready: bool
    restored_state_ready: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ProgressContractError("rollout readback schema version is unsupported")
        object.__setattr__(
            self,
            "automation_id",
            _safe_identity(self.automation_id, field_name="automation_id"),
        )
        object.__setattr__(
            self,
            "writer_task_id",
            _safe_identity(self.writer_task_id, field_name="writer_task_id"),
        )
        object.__setattr__(
            self,
            "target_revision",
            _revision(self.target_revision, field_name="target_revision"),
        )
        for field_name in (
            "active_writer_count",
            "duplicate_automation_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ProgressContractError(
                    f"rollout {field_name} must be a non-negative integer"
                )
        if self.automation_owner != self.automation_id:
            raise ProgressContractError("rollout automation ownership does not match")
        if self.active_writer_count != 1:
            raise ProgressContractError("rollout requires exactly one active writer")
        if self.duplicate_automation_count != 0:
            raise ProgressContractError("rollout cannot have duplicate automations")
        if not all(
            value is True
            for value in (
                self.automation_readback,
                self.worktree_protected,
                self.dependencies_ready,
                self.private_config_ready,
                self.restored_state_ready,
            )
        ):
            raise ProgressContractError("rollout readback is incomplete")

    @property
    def accepted(self) -> bool:
        return True

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RolloutReadback":
        if not isinstance(value, Mapping):
            raise ProgressContractError("rollout readback must be an object")
        required = {
            "schema_version",
            "automation_id",
            "writer_task_id",
            "target_revision",
            "active_writer_count",
            "duplicate_automation_count",
            "automation_owner",
            "automation_readback",
            "worktree_protected",
            "dependencies_ready",
            "private_config_ready",
            "restored_state_ready",
        }
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required)
        if missing:
            raise ProgressContractError(
                f"rollout readback lacks {', '.join(missing)}"
            )
        if extra:
            raise ProgressContractError(
                f"rollout readback contains unsupported field {', '.join(extra)}"
            )
        return cls(**{name: value[name] for name in required})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "automation_id": self.automation_id,
            "writer_task_id": self.writer_task_id,
            "target_revision": self.target_revision,
            "active_writer_count": self.active_writer_count,
            "duplicate_automation_count": self.duplicate_automation_count,
            "automation_owner": self.automation_owner,
            "automation_readback": self.automation_readback,
            "worktree_protected": self.worktree_protected,
            "dependencies_ready": self.dependencies_ready,
            "private_config_ready": self.private_config_ready,
            "restored_state_ready": self.restored_state_ready,
        }


def _report_timestamp(value: Any, *, field_name: str) -> datetime:
    raw = _timezone_aware(value, field_name=field_name)
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _report_in_period(row: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    raw = row.get("occurred_at") or row.get("slot")
    if not raw:
        return True
    try:
        value = _report_timestamp(raw, field_name="event timestamp")
    except ProgressContractError:
        return False
    return start <= value <= end


def _report_at_or_before(row: Mapping[str, Any], end: datetime) -> bool:
    raw = row.get("occurred_at") or row.get("slot")
    if not raw:
        return True
    try:
        return _report_timestamp(raw, field_name="event timestamp") <= end
    except ProgressContractError:
        return False


def _acceptance_event_timestamp(row: Mapping[str, Any]) -> datetime | None:
    raw = row.get("occurred_at") or row.get("slot")
    if not raw:
        return None
    return _report_timestamp(raw, field_name="acceptance event timestamp")


def _acceptance_rows_until(
    rows: list[Mapping[str, Any]],
    *,
    as_of: datetime,
) -> list[Mapping[str, Any]]:
    return [
        row for row in rows
        if isinstance(row, Mapping)
        and (
            (timestamp := _acceptance_event_timestamp(row)) is None
            or timestamp <= as_of
        )
    ]


def _acceptance_rows_in_window(
    rows: list[Mapping[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> list[Mapping[str, Any]]:
    return [
        row for row in rows
        if isinstance(row, Mapping)
        and (
            (timestamp := _acceptance_event_timestamp(row)) is None
            or start <= timestamp <= end
        )
    ]


def _acceptance_non_negative_int(
    value: Any,
    *,
    field_name: str,
    default: int | None = None,
) -> int | None:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProgressContractError(
            f"{field_name} must be a non-negative integer"
        )
    return value


def _acceptance_latency_ms(row: Mapping[str, Any]) -> int | None:
    for field_name in ("sweep_elapsed_ms", "elapsed_ms", "latency_ms"):
        if field_name in row:
            return _acceptance_non_negative_int(
                row[field_name],
                field_name=field_name,
            )
    return None


def _acceptance_p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (95 * len(ordered) + 99) // 100
    return ordered[rank - 1]


def _acceptance_blocker(
    code: str,
    *,
    owner: str = "agent",
    **details: Any,
) -> dict[str, Any]:
    _safe_token(code, field_name="acceptance blocker code")
    result: dict[str, Any] = {"code": code, "owner": owner}
    result.update(details)
    return result


def _acceptance_failure_fingerprint(row: Mapping[str, Any]) -> str:
    value = str(row.get("failure_fingerprint") or "")
    if not value:
        raise ProgressContractError(
            "failure observation lacks failure_fingerprint"
        )
    return _sha256(value, field_name="failure_fingerprint")


def _acceptance_internal_user_action(row: Mapping[str, Any]) -> bool:
    if row.get("user_action_required") is not True:
        return False
    failure = row.get("failure")
    return (
        isinstance(failure, Mapping)
        and str(failure.get("category") or "")
        in _INTERNAL_FAILURE_CATEGORIES
    )


def _acceptance_generic_wait(row: Mapping[str, Any]) -> bool:
    if row.get("event") == "generic_wait":
        return True
    code = str(row.get("code") or "")
    failure = row.get("failure")
    if isinstance(failure, Mapping):
        code = code or str(failure.get("code") or "")
    if code in _GENERIC_WAIT_CODES:
        return True
    progress = row.get("writer_progress")
    if not isinstance(progress, Mapping):
        return False
    details = progress.get("details")
    return (
        progress.get("status") == "wait_until"
        and isinstance(details, Mapping)
        and str(details.get("code") or "") in _GENERIC_WAIT_CODES
    )


def _acceptance_duplicate_counts(row: Mapping[str, Any]) -> dict[str, int]:
    counts = {kind: 0 for kind in sorted(_DUPLICATE_EFFECT_KINDS)}
    raw_counts = row.get("duplicate_effect_counts")
    if isinstance(raw_counts, Mapping):
        for kind, value in raw_counts.items():
            token = _safe_token(kind, field_name="duplicate effect kind")
            count = _acceptance_non_negative_int(
                value,
                field_name="duplicate effect count",
            )
            if token in counts:
                counts[token] += int(count or 0)
    raw_effects = row.get("duplicate_effects")
    if isinstance(raw_effects, list):
        for kind in raw_effects:
            token = _safe_token(kind, field_name="duplicate effect kind")
            if token in counts:
                counts[token] += 1
    for kind in _DUPLICATE_EFFECT_KINDS:
        field_name = f"duplicate_{kind}_count"
        if field_name in row:
            counts[kind] += int(
                _acceptance_non_negative_int(
                    row[field_name],
                    field_name=field_name,
                )
                or 0
            )
    total = _acceptance_non_negative_int(
        row.get("duplicate_count"),
        field_name="duplicate_count",
        default=0,
    ) or 0
    if sum(counts.values()) < total:
        counts["publication"] += total - sum(counts.values())
    return counts


def _is_sweep_duplicate_effect_audit(row: Mapping[str, Any]) -> bool:
    """Select the business-effect audit, not legacy source replay audits."""

    return (
        row.get("event") == "duplicate_effect_audit"
        and not row.get("source")
    )


def _acceptance_effect_identity(value: Mapping[str, Any]) -> str | None:
    for field_name in (
        "idempotency_key",
        "idempotencyKey",
        "receipt",
        "receiptId",
        "receipt_id",
        "trade_id",
        "id",
    ):
        candidate = value.get(field_name)
        if candidate is None or candidate == "":
            continue
        if isinstance(candidate, Mapping):
            return _digest(candidate)
        return str(candidate)
    return None


def _acceptance_recomputed_duplicate_counts(
    daily_rows: list[Mapping[str, Any]],
) -> dict[str, int]:
    effect_fields = {
        "publication": ("gray_report", {"published"}),
        "reminder": ("alert", {"delivered"}),
        "book": ("book_kol_us", {"filled"}),
        "knowledge": ("knowledge", {"published", "completed"}),
        "ack": ("ack", {"acked", "already_acked"}),
    }
    seen: dict[str, set[str]] = {
        kind: set() for kind in effect_fields
    }
    duplicates = {kind: 0 for kind in sorted(effect_fields)}
    for row in daily_rows:
        if row.get("event") != "source_completed":
            continue
        result = row.get("result")
        if not isinstance(result, Mapping):
            continue
        events = result.get("events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, Mapping):
                continue
            for kind, (field_name, statuses) in effect_fields.items():
                effect = event.get(field_name)
                if not isinstance(effect, Mapping):
                    continue
                if effect.get("status") not in statuses:
                    continue
                identity = _acceptance_effect_identity(effect)
                if identity is None:
                    continue
                if identity in seen[kind]:
                    duplicates[kind] += 1
                else:
                    seen[kind].add(identity)
    return duplicates


def _acceptance_active_active(row: Mapping[str, Any]) -> bool:
    if (
        row.get("event") == "peer_gate_observed"
        and row.get("gate_result") == "no_op"
    ):
        return True
    if row.get("active_active") is True or row.get("active-active") is True:
        return True
    if row.get("event") in {
        "active_active_detected",
        "active-active",
    }:
        return True
    count = _acceptance_non_negative_int(
        row.get("active_writer_count"),
        field_name="active_writer_count",
        default=0,
    ) or 0
    if count > 1:
        return True
    writer_ids = row.get("active_writer_ids")
    return isinstance(writer_ids, list) and len(writer_ids) > 1


def _acceptance_fingerprint_report(
    convergence_rows: list[Mapping[str, Any]],
    *,
    start: datetime | None,
    recent_start_date: date,
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    fingerprint_rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in convergence_rows:
        if row.get("event") not in {
            "failure_observed",
            "repair_closed",
            "repair_resumed",
        }:
            continue
        fingerprint = _acceptance_failure_fingerprint(row)
        fingerprint_rows.setdefault(fingerprint, []).append(row)

    known_from_baseline: set[str] = set()
    raw_known = baseline.get("known_failure_fingerprints")
    if raw_known is not None:
        if not isinstance(raw_known, list):
            raise ProgressContractError(
                "known_failure_fingerprints must be a list"
            )
        for fingerprint in raw_known:
            known_from_baseline.add(_sha256(
                fingerprint,
                field_name="known failure fingerprint",
            ))
    known_fingerprints = set(fingerprint_rows) | known_from_baseline
    open_fingerprints: list[str] = []
    closed_fingerprints: set[str] = set()
    recurrence_rows: list[tuple[str, Mapping[str, Any]]] = []
    closure_receipt_missing: set[str] = set()
    blockers: list[dict[str, Any]] = []
    for fingerprint in sorted(known_fingerprints):
        rows = fingerprint_rows.get(fingerprint, [])
        closed_once = False
        latest_event: str | None = None
        latest_owner = "agent"
        for row in rows:
            event = str(row.get("event") or "")
            if event == "failure_observed":
                if closed_once:
                    event_timestamp = _acceptance_event_timestamp(row)
                    if (
                        event_timestamp is None
                        or start is None
                        or event_timestamp >= start
                    ):
                        recurrence_rows.append((fingerprint, row))
                latest_event = event
                latest_owner = str(row.get("ownership") or "agent")
            elif event == "repair_closed":
                receipt = row.get("repair_receipt")
                if (
                    not isinstance(receipt, Mapping)
                    or receipt.get("failure_fingerprint") != fingerprint
                ):
                    closure_receipt_missing.add(fingerprint)
                    latest_event = event
                    continue
                closed_once = True
                latest_event = event
                latest_owner = "none"
            elif event == "repair_resumed" and closed_once:
                latest_event = event
                latest_owner = "none"
        if closed_once and fingerprint not in closure_receipt_missing:
            closed_fingerprints.add(fingerprint)
        if (
            latest_event not in {"repair_closed", "repair_resumed"}
            or fingerprint in closure_receipt_missing
        ):
            open_fingerprints.append(fingerprint)
            blockers.append(_acceptance_blocker(
                "fingerprint_closure_incomplete",
                fingerprint=fingerprint,
                owner=latest_owner,
            ))
    for fingerprint in sorted(closure_receipt_missing):
        blockers.append(_acceptance_blocker(
            "repair_closure_receipt_missing",
            fingerprint=fingerprint,
        ))
    if recurrence_rows:
        for fingerprint in sorted({row[0] for row in recurrence_rows}):
            blockers.append(_acceptance_blocker(
                "repair_after_same_root_recurrence",
                fingerprint=fingerprint,
            ))
    recent_recurrence = [
        row for _fingerprint, row in recurrence_rows
        if (
            (timestamp := _acceptance_event_timestamp(row)) is not None
            and timestamp.astimezone(_ACCEPTANCE_TIMEZONE).date()
            >= recent_start_date
        )
    ]
    fingerprints_at_rollout = {
        fingerprint
        for fingerprint, rows in fingerprint_rows.items()
        if any(
            (
                (timestamp := _acceptance_event_timestamp(row)) is None
                or start is None
                or timestamp <= start
            )
            for row in rows
        )
    }
    baseline_count = baseline.get("failure_fingerprints")
    hard_failure = bool(recurrence_rows)
    if baseline_count is not None:
        baseline_count = _acceptance_non_negative_int(
            baseline_count,
            field_name="baseline failure_fingerprints",
        )
        inventory_at_rollout = fingerprints_at_rollout | known_from_baseline
        if int(baseline_count or 0) != len(inventory_at_rollout):
            blockers.append(_acceptance_blocker(
                (
                    "known_fingerprint_inventory_missing"
                    if baseline_count and not inventory_at_rollout
                    else "known_fingerprint_inventory_mismatch"
                ),
                expected=int(baseline_count or 0),
                observed=len(inventory_at_rollout),
            ))
            hard_failure = True
    return {
        "fingerprints": {
            "observed": len(known_fingerprints),
            "closed": len(closed_fingerprints),
            "open": open_fingerprints,
            "same_root_recurrence": len(recurrence_rows),
            "recent_same_root_recurrence": len(recent_recurrence),
        },
        "blockers": blockers,
        "hard_failure": hard_failure,
        "repairs": {
            "required": sum(
                row.get("event") == "failure_observed"
                for row in convergence_rows
            ),
            "closed": sum(
                row.get("event") == "repair_closed"
                for row in convergence_rows
            ),
        },
    }


def _acceptance_clean_sweep(row: Mapping[str, Any]) -> bool:
    if row.get("event") != "sweep_completed" or row.get("health") != "healthy":
        return False
    if int(row.get("coordinator_source_video_bytes") or 0) != 0:
        return False
    states = row.get("source_states")
    if not isinstance(states, list):
        return True
    for state in states:
        if not isinstance(state, Mapping):
            return False
        if state.get("user_action_required") is True:
            return False
        if state.get("failure") or state.get("repair_required") is True:
            return False
        if int(state.get("new_external_effect_count") or 0) != 0:
            return False
        if state.get("status") not in {"no_update", "terminal"}:
            return False
    return True


def _acceptance_next_window(
    *,
    status: str,
    start: datetime | None,
    as_of: datetime,
    scheduled_slots: int,
) -> dict[str, Any]:
    if status == "failed":
        return {
            "kind": "new_rollout",
            "reason_code": "restart_stability_window_after_failed_acceptance",
        }
    if start is None:
        return {
            "kind": "rollout_readback",
            "reason_code": "await_authoritative_rollout_readback",
        }
    return {
        "kind": "stability_window",
        "not_before": max(
            as_of,
            start + timedelta(days=_REQUIRED_STABILITY_DAYS),
        ).isoformat(timespec="seconds"),
        "scheduled_slots_remaining": max(
            0,
            _REQUIRED_STABILITY_SLOTS - scheduled_slots,
        ),
    }


def build_stability_acceptance_report(
    daily_events: list[Mapping[str, Any]],
    convergence_events: list[Mapping[str, Any]],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Recompute the seven-day acceptance gates from append-only ledgers.

    ``pending_observation`` is deliberately a normal result.  It means the
    authoritative rollout or the required future sample is not available yet;
    only ``passed`` is permission to close issue06.
    """

    end = _report_timestamp(as_of, field_name="as_of")
    daily_rows = _acceptance_rows_until(daily_events, as_of=end)
    convergence_rows = _acceptance_rows_until(convergence_events, as_of=end)
    rollout_rows = [
        row for row in convergence_rows
        if row.get("event") == "rollout_readback"
    ]
    if not rollout_rows:
        return {
            "schema_version": 1,
            "status": "pending_observation",
            "as_of": as_of,
            "rollout": {"status": "not_recorded"},
            "window": {
                "start": None,
                "as_of": as_of,
                "elapsed_days": 0,
                "scheduled_slots": 0,
                "observed_days": 0,
                "missing_observation_dates": [],
                "required_days": _REQUIRED_STABILITY_DAYS,
                "required_scheduled_slots": _REQUIRED_STABILITY_SLOTS,
                "last_three_days_scheduled_slots": 0,
                "required_last_three_days": _REQUIRED_RECENT_DAYS,
                "required_last_twenty_slots": _REQUIRED_RECENT_SLOTS,
            },
            "latency": {
                "peer_gate": {
                    "sample_count": 0,
                    "p95_ms": None,
                    "limit_ms": _PEER_GATE_P95_LIMIT_MS,
                    "status": "pending_observation",
                },
                "clean_sweep": {
                    "sample_count": 0,
                    "p95_ms": None,
                    "limit_ms": _CLEAN_SWEEP_P95_LIMIT_MS,
                    "status": "pending_observation",
                },
            },
            "fingerprints": {
                "observed": 0,
                "closed": 0,
                "open": [],
                "same_root_recurrence": 0,
            },
            "repairs": {"required": 0, "closed": 0},
            "safety": {
                "active_active": 0,
                "duplicate_effects": 0,
                "duplicate_effect_audits": 0,
                "source_video_bytes": 0,
                "internal_user_dependencies": 0,
                "generic_waits": 0,
                "p0_safety_incidents": 0,
                "excluded_by_reason": {},
            },
            "blockers": [_acceptance_blocker("rollout_readback_missing")],
            "next_verification_window": _acceptance_next_window(
                status="pending_observation",
                start=None,
                as_of=end,
                scheduled_slots=0,
            ),
        }

    blockers: list[dict[str, Any]] = []
    hard_failure = False
    if any(
        row.get("restart_after_failed_acceptance") is not True
        for row in rollout_rows[1:]
    ):
        blockers.append(_acceptance_blocker("multiple_rollout_readbacks"))
        hard_failure = True
    rollout = rollout_rows[-1]
    readback_value = rollout.get("readback")
    readback: RolloutReadback | None = None
    try:
        readback = RolloutReadback.from_dict(readback_value)
    except ProgressContractError:
        blockers.append(_acceptance_blocker("rollout_readback_invalid"))
        hard_failure = True
    start_raw = rollout.get("stability_window_start") or rollout.get("slot")
    start = (
        _report_timestamp(start_raw, field_name="stability_window_start")
        if start_raw
        else None
    )
    if start is None:
        blockers.append(_acceptance_blocker("stability_window_start_missing"))
        hard_failure = True
    elif start > end:
        blockers.append(_acceptance_blocker("as_of_before_rollout"))
        hard_failure = True

    window_daily = (
        _acceptance_rows_in_window(daily_rows, start=start, end=end)
        if start is not None
        else []
    )
    window_convergence = (
        _acceptance_rows_in_window(convergence_rows, start=start, end=end)
        if start is not None
        else []
    )

    scheduled_slots = sorted({
        str(row.get("slot"))
        for row in window_daily
        if row.get("event") == "sweep_completed" and row.get("slot")
    })
    parsed_scheduled_slots = [
        _report_timestamp(slot, field_name="scheduled slot")
        for slot in scheduled_slots
    ]
    local_end = end.astimezone(_ACCEPTANCE_TIMEZONE)
    recent_start_date = local_end.date() - timedelta(days=2)
    recent_slots = [
        slot for slot in parsed_scheduled_slots
        if recent_start_date <= slot.astimezone(_ACCEPTANCE_TIMEZONE).date()
        <= local_end.date()
    ]
    scheduled_dates = {
        slot.astimezone(_ACCEPTANCE_TIMEZONE).date()
        for slot in parsed_scheduled_slots
    }
    missing_observation_dates: list[str] = []
    if start is not None:
        window_start_date = start.astimezone(_ACCEPTANCE_TIMEZONE).date()
        window_end_date = local_end.date()
        expected_dates = {
            window_start_date + timedelta(days=offset)
            for offset in range((window_end_date - window_start_date).days + 1)
        }
        missing_observation_dates = sorted(
            date_value.isoformat()
            for date_value in expected_dates - scheduled_dates
        )
    elapsed_days = (
        round((end - start).total_seconds() / 86400, 10)
        if start is not None
        else 0
    )
    if start is not None and elapsed_days < _REQUIRED_STABILITY_DAYS:
        blockers.append(_acceptance_blocker("observation_days_incomplete"))
    if elapsed_days >= _REQUIRED_STABILITY_DAYS and missing_observation_dates:
        blockers.append(_acceptance_blocker(
            "observation_days_discontinuous",
            count=len(missing_observation_dates),
        ))
    if len(scheduled_slots) < _REQUIRED_STABILITY_SLOTS:
        blockers.append(_acceptance_blocker("scheduled_slots_incomplete"))
    if len({
        slot.astimezone(_ACCEPTANCE_TIMEZONE).date() for slot in recent_slots
    }) < _REQUIRED_RECENT_DAYS:
        blockers.append(_acceptance_blocker("recent_observation_days_incomplete"))
    if len(recent_slots) < _REQUIRED_RECENT_SLOTS:
        blockers.append(_acceptance_blocker("recent_scheduled_slots_incomplete"))

    excluded_by_reason: dict[str, int] = {}
    for row in window_daily:
        if row.get("event") != "slot_excluded":
            continue
        reason = str(row.get("reason") or row.get("code") or "")
        if not reason:
            blockers.append(_acceptance_blocker("excluded_slot_reason_missing"))
            hard_failure = True
            continue
        try:
            reason = _safe_token(reason, field_name="slot exclusion reason")
        except ProgressContractError:
            blockers.append(_acceptance_blocker("excluded_slot_reason_invalid"))
            hard_failure = True
            continue
        excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1

    all_window_rows = window_daily + window_convergence
    active_active = sum(
        _acceptance_active_active(row) for row in all_window_rows
    )
    if readback is not None and readback.active_writer_count != 1:
        active_active += 1
    if active_active:
        blockers.append(_acceptance_blocker(
            "active_active_detected",
            count=active_active,
        ))
        hard_failure = True

    duplicate_effects = {kind: 0 for kind in sorted(_DUPLICATE_EFFECT_KINDS)}
    duplicate_audit_rows = [
        row for row in all_window_rows
        if _is_sweep_duplicate_effect_audit(row)
    ]
    for row in duplicate_audit_rows:
        for kind, count in _acceptance_duplicate_counts(row).items():
            duplicate_effects[kind] += count
    recomputed_duplicate_effects = _acceptance_recomputed_duplicate_counts(
        window_daily
    )
    audit_slots = {
        str(row.get("slot"))
        for row in duplicate_audit_rows
        if row.get("slot")
    }
    missing_duplicate_audit_slots = set(scheduled_slots) - audit_slots
    if missing_duplicate_audit_slots:
        blockers.append(_acceptance_blocker(
            "duplicate_effect_audit_missing",
            count=len(missing_duplicate_audit_slots),
        ))
    if duplicate_effects != recomputed_duplicate_effects:
        blockers.append(_acceptance_blocker(
            "duplicate_effect_audit_mismatch",
        ))
        hard_failure = True
    duplicate_total = sum(duplicate_effects.values())
    if duplicate_total:
        blockers.append(_acceptance_blocker(
            "duplicate_effects_detected",
            count=duplicate_total,
        ))
        hard_failure = True

    source_video_bytes = 0
    internal_user_dependencies = 0
    generic_waits = 0
    for row in all_window_rows:
        source_video_bytes += int(
            _acceptance_non_negative_int(
                row.get("coordinator_source_video_bytes"),
                field_name="coordinator_source_video_bytes",
                default=0,
            )
            or 0
        )
        for state in row.get("source_states") or []:
            if not isinstance(state, Mapping):
                continue
            internal_user_dependencies += int(
                _acceptance_internal_user_action(state)
            )
            generic_waits += int(_acceptance_generic_wait(state))
        internal_user_dependencies += int(
            _acceptance_internal_user_action(row)
        )
        generic_waits += int(_acceptance_generic_wait(row))
    if source_video_bytes:
        blockers.append(_acceptance_blocker(
            "source_video_bytes_detected",
            count=source_video_bytes,
        ))
        hard_failure = True
    if internal_user_dependencies:
        blockers.append(_acceptance_blocker(
            "internal_failure_user_dependency",
            count=internal_user_dependencies,
        ))
        hard_failure = True
    if generic_waits:
        blockers.append(_acceptance_blocker(
            "generic_wait_detected",
            count=generic_waits,
        ))
        hard_failure = True

    def is_p0_incident(row: Mapping[str, Any]) -> bool:
        failure = row.get("failure")
        failure_severity = (
            failure.get("severity")
            if isinstance(failure, Mapping)
            else None
        )
        failure_priority = (
            failure.get("priority")
            if isinstance(failure, Mapping)
            else None
        )
        return bool(
            row.get("severity") == "P0"
            or row.get("priority") == "P0"
            or failure_severity == "P0"
            or failure_priority == "P0"
            or row.get("p0_safety_incident") is True
            or row.get("safety_status") in {"failed", "unsafe", "P0"}
            or row.get("event") in {
                "p0_safety_incident",
                "safety_incident",
                "safety_failure",
            }
        )

    p0_incidents = sum(is_p0_incident(row) for row in all_window_rows)
    if p0_incidents:
        blockers.append(_acceptance_blocker(
            "p0_safety_incident",
            count=p0_incidents,
        ))
        hard_failure = True

    peer_latencies = [
        int(latency)
        for row in window_convergence
        if row.get("event") == "peer_gate_observed"
        for latency in [_acceptance_latency_ms(row)]
        if latency is not None
    ]
    clean_sweep_latencies: list[int] = []
    missing_clean_sweep_latency = 0
    for row in window_daily:
        if not _acceptance_clean_sweep(row):
            continue
        latency = _acceptance_latency_ms(row)
        if latency is None:
            missing_clean_sweep_latency += 1
        else:
            clean_sweep_latencies.append(latency)
    peer_p95 = _acceptance_p95(peer_latencies)
    clean_sweep_p95 = _acceptance_p95(clean_sweep_latencies)
    if not peer_latencies:
        blockers.append(_acceptance_blocker("peer_gate_latency_missing"))
    elif len(peer_latencies) < _MIN_LATENCY_SAMPLES:
        blockers.append(_acceptance_blocker(
            "peer_gate_latency_samples_insufficient",
            count=len(peer_latencies),
            required=_MIN_LATENCY_SAMPLES,
        ))
    elif peer_p95 is not None and peer_p95 > _PEER_GATE_P95_LIMIT_MS:
        blockers.append(_acceptance_blocker(
            "peer_gate_p95_exceeded",
            p95_ms=peer_p95,
            limit_ms=_PEER_GATE_P95_LIMIT_MS,
        ))
        hard_failure = True
    if not clean_sweep_latencies or missing_clean_sweep_latency:
        blockers.append(_acceptance_blocker("clean_sweep_latency_missing"))
    elif len(clean_sweep_latencies) < _MIN_LATENCY_SAMPLES:
        blockers.append(_acceptance_blocker(
            "clean_sweep_latency_samples_insufficient",
            count=len(clean_sweep_latencies),
            required=_MIN_LATENCY_SAMPLES,
        ))
    elif clean_sweep_p95 is not None and clean_sweep_p95 > _CLEAN_SWEEP_P95_LIMIT_MS:
        blockers.append(_acceptance_blocker(
            "clean_sweep_p95_exceeded",
            p95_ms=clean_sweep_p95,
            limit_ms=_CLEAN_SWEEP_P95_LIMIT_MS,
        ))
        hard_failure = True

    baseline = rollout.get("baseline")
    if baseline is not None and not isinstance(baseline, Mapping):
        raise ProgressContractError("rollout baseline must be an object")
    baseline = baseline or {}
    fingerprint_report = _acceptance_fingerprint_report(
        convergence_rows,
        start=start,
        recent_start_date=recent_start_date,
        baseline=baseline,
    )
    blockers.extend(fingerprint_report["blockers"])
    hard_failure = hard_failure or fingerprint_report["hard_failure"]

    window = {
        "start": (
            start.isoformat(timespec="seconds") if start is not None else None
        ),
        "as_of": as_of,
        "elapsed_days": elapsed_days,
        "scheduled_slots": len(scheduled_slots),
        "observed_days": len(scheduled_dates),
        "missing_observation_dates": missing_observation_dates,
        "required_days": _REQUIRED_STABILITY_DAYS,
        "required_scheduled_slots": _REQUIRED_STABILITY_SLOTS,
        "last_three_days_scheduled_slots": len(recent_slots),
        "required_last_three_days": _REQUIRED_RECENT_DAYS,
        "required_last_twenty_slots": _REQUIRED_RECENT_SLOTS,
    }
    latency = {
        "peer_gate": {
            "sample_count": len(peer_latencies),
            "p95_ms": peer_p95,
            "limit_ms": _PEER_GATE_P95_LIMIT_MS,
            "status": (
                "pending_observation"
                if peer_p95 is None or len(peer_latencies) < _MIN_LATENCY_SAMPLES
                else "failed"
                if peer_p95 > _PEER_GATE_P95_LIMIT_MS
                else "passed"
            ),
        },
        "clean_sweep": {
            "sample_count": len(clean_sweep_latencies),
            "missing_sample_count": missing_clean_sweep_latency,
            "p95_ms": clean_sweep_p95,
            "limit_ms": _CLEAN_SWEEP_P95_LIMIT_MS,
            "status": (
                "pending_observation"
                if (
                    clean_sweep_p95 is None
                    or missing_clean_sweep_latency
                    or len(clean_sweep_latencies) < _MIN_LATENCY_SAMPLES
                )
                else "failed"
                if clean_sweep_p95 > _CLEAN_SWEEP_P95_LIMIT_MS
                else "passed"
            ),
        },
    }
    safety = {
        "active_active": active_active,
        "duplicate_effects": duplicate_total,
        "duplicate_effect_audits": len(duplicate_audit_rows),
        "duplicate_effects_by_kind": duplicate_effects,
        "source_video_bytes": source_video_bytes,
        "internal_user_dependencies": internal_user_dependencies,
        "generic_waits": generic_waits,
        "p0_safety_incidents": p0_incidents,
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
    }
    fingerprints = fingerprint_report["fingerprints"]
    repairs = {
        "required": sum(
            row.get("event") == "failure_observed"
            for row in window_convergence
        ),
        "closed": sum(
            row.get("event") == "repair_closed"
            for row in window_convergence
        ),
    }
    if readback is not None:
        rollout_report = {
            "status": "accepted",
            "automation_id": readback.automation_id,
            "writer_task_id": readback.writer_task_id,
            "target_revision": readback.target_revision,
            "stability_window_start": rollout.get(
                "stability_window_start", rollout.get("slot")
            ),
            "security_validation": {
                "automation_readback": readback.automation_readback,
                "worktree_protected": readback.worktree_protected,
                "dependencies_ready": readback.dependencies_ready,
                "private_config_ready": readback.private_config_ready,
                "restored_state_ready": readback.restored_state_ready,
            },
        }
    else:
        rollout_report = {"status": "invalid"}
    pending_blockers = {
        "observation_days_incomplete",
        "observation_days_discontinuous",
        "scheduled_slots_incomplete",
        "recent_observation_days_incomplete",
        "recent_scheduled_slots_incomplete",
        "peer_gate_latency_missing",
        "peer_gate_latency_samples_insufficient",
        "clean_sweep_latency_missing",
        "clean_sweep_latency_samples_insufficient",
        "duplicate_effect_audit_missing",
        "fingerprint_closure_incomplete",
        "repair_closure_receipt_missing",
        "known_fingerprint_inventory_missing",
    }
    has_pending = any(blocker["code"] in pending_blockers for blocker in blockers)
    status = (
        "failed" if hard_failure
        else "pending_observation" if has_pending
        else "passed"
    )
    blockers = sorted(
        blockers,
        key=lambda blocker: (
            str(blocker.get("code")),
            str(blocker.get("fingerprint") or ""),
        ),
    )
    return {
        "schema_version": 1,
        "status": status,
        "as_of": as_of,
        "rollout": rollout_report,
        "window": window,
        "latency": latency,
        "fingerprints": fingerprints,
        "repairs": repairs,
        "safety": safety,
        "blockers": blockers,
        "next_verification_window": _acceptance_next_window(
            status=status,
            start=start,
            as_of=end,
            scheduled_slots=len(scheduled_slots),
        ),
    }


def build_convergence_report(
    daily_events: list[Mapping[str, Any]],
    convergence_events: list[Mapping[str, Any]],
    *,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    """Build a credential-safe daily convergence report from append-only rows."""

    start = _report_timestamp(period_start, field_name="period_start")
    end = _report_timestamp(period_end, field_name="period_end")
    if start > end:
        raise ProgressContractError("period_start must not be after period_end")
    daily = [
        row for row in daily_events
        if isinstance(row, Mapping) and _report_in_period(row, start, end)
    ]
    convergence = [
        row for row in convergence_events
        if isinstance(row, Mapping) and _report_in_period(row, start, end)
    ]
    all_daily = [
        row
        for row in daily_events
        if isinstance(row, Mapping) and _report_at_or_before(row, end)
    ]
    all_convergence = [
        row
        for row in convergence_events
        if isinstance(row, Mapping) and _report_at_or_before(row, end)
    ]
    scheduled_slots = {
        str(row.get("slot"))
        for row in daily
        if row.get("event") == "sweep_completed" and row.get("slot")
    }
    clean_slots = {
        str(row.get("slot"))
        for row in daily
        if row.get("event") == "sweep_completed"
        and row.get("health") == "healthy"
        and row.get("slot")
    }
    business_slots: set[str] = set()
    failure_codes: dict[str, int] = {}
    internal_categories = {
        "code_error",
        "schema_error",
        "environment_error",
        "provider_contract_error",
        "control_plane_handler_error",
        "local_runtime_error",
        "protocol_error",
        "internal_state_error",
    }
    internal_user_dependency = 0
    generic_waits = 0
    for row in daily:
        if row.get("event") != "sweep_completed":
            continue
        slot = str(row.get("slot") or "")
        for state in row.get("source_states") or []:
            if not isinstance(state, Mapping):
                continue
            if int(state.get("new_external_effect_count") or 0) > 0:
                business_slots.add(slot)
            failure = state.get("failure")
            if isinstance(failure, Mapping):
                code = str(failure.get("code") or "")
                if code:
                    failure_codes[code] = failure_codes.get(code, 0) + 1
                if (
                    state.get("user_action_required") is True
                    and str(failure.get("category") or "") in internal_categories
                ):
                    internal_user_dependency += 1
            progress = state.get("writer_progress")
            if isinstance(progress, Mapping):
                details = progress.get("details")
                if (
                    progress.get("status") == "wait_until"
                    and isinstance(details, Mapping)
                    and details.get("code") in {
                        "generic_wait_without_deadline",
                        "source_pending",
                    }
                ):
                    generic_waits += 1
    excluded_by_reason: dict[str, int] = {}
    for row in daily:
        if row.get("event") != "slot_excluded":
            continue
        reason = str(row.get("reason") or "unknown")
        _safe_token(reason, field_name="slot exclusion reason")
        excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1

    fingerprints = {
        str(row.get("failure_fingerprint"))
        for row in convergence
        if row.get("event") == "failure_observed"
        and str(row.get("failure_fingerprint") or "")
    }
    repair_required = sum(
        row.get("event") == "failure_observed" for row in convergence
    )
    repair_closed = len({
        str(row.get("failure_fingerprint"))
        for row in convergence
        if row.get("event") == "repair_closed"
        and str(row.get("failure_fingerprint") or "")
    })
    closed_fingerprints: set[str] = set()
    recurrence = 0
    for row in convergence:
        event = row.get("event")
        fingerprint = str(row.get("failure_fingerprint") or "")
        if event == "repair_closed" and fingerprint:
            closed_fingerprints.add(fingerprint)
        elif event == "failure_observed" and fingerprint in closed_fingerprints:
            recurrence += 1
        if event == "generic_wait" or row.get("code") in {
            "generic_wait_without_deadline",
            "source_pending",
        }:
            generic_waits += 1
        failure = row.get("failure")
        if isinstance(failure, Mapping):
            code = str(failure.get("code") or "")
            if code:
                failure_codes[code] = failure_codes.get(code, 0) + 1

    peer_attempts = sum(
        int(row.get("attempt_count") or 0)
        for row in convergence
        if row.get("event") == "peer_gate_observed"
    )
    peer_latency = sum(
        int(row.get("elapsed_ms") or 0)
        for row in convergence
        if row.get("event") == "peer_gate_observed"
    )
    runner_starts = sum(
        row.get("event") == "runner_started" for row in daily + convergence
    )
    reconciliations = sum(
        row.get("event") == "side_effect_reconciled"
        for row in daily + convergence
    )
    duplicate_audits = [
        row for row in daily + convergence
        if _is_sweep_duplicate_effect_audit(row)
    ]
    duplicate_findings = sum(
        int(row.get("duplicate_count") or 0) for row in duplicate_audits
    )
    rollout_rows = [
        row for row in all_convergence
        if row.get("event") == "rollout_readback"
    ]
    latest_rollout = rollout_rows[-1] if rollout_rows else None
    stability_start = (
        str(
            latest_rollout.get("stability_window_start")
            or latest_rollout.get("slot")
        )
        if latest_rollout is not None
        else None
    )
    latest_event = max(
        (
            row.get("slot") or row.get("occurred_at")
            for row in daily + convergence
            if row.get("slot") or row.get("occurred_at")
        ),
        default=period_end,
    )
    start_date = (
        _report_timestamp(stability_start, field_name="stability_window_start")
        if stability_start else None
    )
    all_scheduled_slots = {
        str(row.get("slot"))
        for row in all_daily
        if row.get("event") == "sweep_completed" and row.get("slot")
    }
    scheduled_after_start = sum(
        _report_timestamp(slot, field_name="scheduled slot") >= start_date
        for slot in all_scheduled_slots
    ) if stability_start and start_date is not None else 0
    end_date = _report_timestamp(latest_event, field_name="latest event")
    elapsed_days = (
        (end_date - start_date).total_seconds() / 86400
        if start_date is not None else 0
    )
    return {
        "schema_version": 1,
        "period": {"start": period_start, "end": period_end},
        "slots": {
            "scheduled": len(scheduled_slots),
            "clean": len(clean_slots),
            "business": len(business_slots),
            "excluded": sum(excluded_by_reason.values()),
            "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
        },
        "failure_codes": dict(sorted(failure_codes.items())),
        "rollout": (
            {
                "status": "accepted",
                "automation_id": latest_rollout["readback"]["automation_id"],
                "writer_task_id": latest_rollout["readback"]["writer_task_id"],
                "target_revision": latest_rollout["readback"]["target_revision"],
                "stability_window_start": latest_rollout[
                    "stability_window_start"
                ],
                "baseline": latest_rollout.get("baseline", {}),
            }
            if latest_rollout is not None
            else {"status": "not_recorded"}
        ),
        "metrics": {
            "failure_fingerprints": len(fingerprints),
            "repair_required": repair_required,
            "repair_closed": repair_closed,
            "repair_after_same_root_recurrence": recurrence,
            "generic_waits": generic_waits,
            "internal_failure_user_dependency": internal_user_dependency,
            "peer_gate_attempts": peer_attempts,
            "peer_gate_latency_ms": peer_latency,
            "runner_starts": runner_starts,
            "side_effect_reconciliations": reconciliations,
            "duplicate_effect_audits": len(duplicate_audits),
            "duplicate_effect_findings": duplicate_findings,
        },
        "stability_window": {
            "start": (
                start_date.isoformat(timespec="seconds")
                if start_date is not None
                else None
            ),
            "scheduled_slots": scheduled_after_start,
            "required_days": 7,
            "required_scheduled_slots": 50,
            "complete": bool(
                stability_start
                and elapsed_days >= 7
                and scheduled_after_start >= 50
            ),
        },
    }
