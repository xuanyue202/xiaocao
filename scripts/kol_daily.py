#!/usr/bin/env python3
"""Run or inspect the short-lived Ticket 07 KOL daytime operation."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import stat
import subprocess
import sys
import termios
from collections.abc import Collection
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep as _cloud_handoff_sleep
from typing import Any

from xiaocao.kol._shared import DecisionError
from xiaocao.kol.daily import (
    AGENT_OWNED_FAILURE_CATEGORIES,
    build_initial_projection_candidate,
    build_triggered_evaluation_candidate,
    DailyCoordinator,
    DailyError,
    DailyPublicationContext,
    DailyPublicationPipeline,
    initial_projection_terminal,
    TransientSourceError,
    UserActionBlocker,
    triggered_evaluation_terminal,
    validate_source_event,
)
from xiaocao.kol.decisions import DecisionPipeline
from xiaocao.kol.claim_coverage import build_claim_extraction_request
from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
    validate_decision_completion,
)
from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.kol.lv_subscription import (
    BLOCKED_DOWNLOAD_PROVIDER_CONTRACT_VERSION,
    LvSubscriptionService,
)
from xiaocao.kol.mailbox import (
    LiangHuiMailboxClient,
    MailboxLedger,
    RemoteMailboxDrain,
)
from xiaocao.kol.publication import PublicationLedger, read_published_publication
from xiaocao.kol.semantic_bundle import (
    read_validated_bundle,
    validate_receipt_bindings,
)
from xiaocao.kol.subscription_video import LV_SOURCE, SubscriptionVideoService
from xiaocao.kol.wechat_official import (
    DEFAULT_PUBLISHERS as DEFAULT_WECHAT_OFFICIAL_PUBLISHERS,
    DEFAULT_WITHIN as DEFAULT_WECHAT_OFFICIAL_WITHIN,
    OfficialAccountInbox,
    OfficialAccountOpenCliAcquirer,
    OfficialAccountSubscription,
    WechatCliOfficialAccountReader,
)
from xiaocao.kol.xiaocao_live import (
    XiaocaoLiveService,
    validate_decision_bundle,
)
from xiaocao.kol.xiaocao_wechat import (
    DEFAULT_CONTACT as DEFAULT_XIAOCAO_WECHAT_CONTACT,
    DEFAULT_WECHAT_CLI,
    WechatCliHistoryReader,
    XiaocaoLiveCaptureDriver,
    XiaocaoWechatLiveSubscription,
)
from xiaocao.kol.writer_progress import (
    affected_set_digest,
    FailureFingerprint,
    ProgressContractError,
    RepairValidationLedger,
    RepairValidationService,
    RolloutReadback,
    normalize_source_result,
    resolve_repository_revision,
    WriterProgress,
)
from xiaocao.live.notify import notify


@dataclass(frozen=True)
class SourceAdapter:
    """Typed coordinator adapter; optional operations stay explicit."""

    name: str
    priority: int
    run: Any
    narrow_resume: Any
    reconcile: Any
    structured_input: Any | None = None

    def coordinator_entry(self) -> dict[str, Any]:
        entry = {
            "name": self.name,
            "priority": self.priority,
            "run": self.run,
            "narrow_resume": self.narrow_resume,
            "reconcile": self.reconcile,
        }
        if self.structured_input is not None:
            entry["structured_input"] = self.structured_input
        return entry


DEFAULT_OUTPUT = Path("output/live/kol_daily")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")
DEFAULT_LV_OUTPUT = Path("output/live/kol_lv_subscription")
DEFAULT_VIDEO_OUTPUT = Path("output/live/kol_subscription_videos")
DEFAULT_XIAOCAO_OUTPUT = Path("output/live/kol_xiaocao_live")
DEFAULT_XIAOCAO_WECHAT_OUTPUT = (
    DEFAULT_XIAOCAO_OUTPUT / "wechat_subscription"
)


def _load_household_context_with_retry(
    client: LiangHuiMcpClient,
) -> dict[str, Any]:
    """Retry one transient read-only provider failure in the same task."""

    try:
        return client.load_context()
    except DecisionError as exc:
        if str(exc) != "亮灰 MCP request failed":
            raise
    return client.load_context()
DEFAULT_WECHAT_OFFICIAL_OUTPUT = Path("output/live/kol_wechat_official")
DEFAULT_MAILBOX_OUTPUT = Path("output/live/kol_mailbox")
MAX_HANDOFF_BYTES = 1024 * 1024
CLOUD_HANDOFF_POLL_SECONDS = 30
BOUNDED_SOURCE_FAILURES = frozenset({
    ("source_error", "source_temporarily_unavailable"),
})
_STRUCTURED_INPUT_STATE: ContextVar[dict[str, Any] | None] = ContextVar(
    "kol_structured_input_state",
    default=None,
)


@functools.lru_cache(maxsize=1)
def _writer_failure_revision() -> str:
    """Resolve the exact code revision bound into a repair fingerprint."""

    try:
        return resolve_repository_revision(Path(__file__).resolve().parents[1])
    except ValueError as exc:
        raise DailyError("writer failure revision cannot be resolved") from exc


def _claim_summary_from_failure_audit(audit: dict[str, Any]) -> dict[str, int]:
    claim_status = str(audit.get("claim_status") or "missing")
    if claim_status == "completed":
        return {
            "claim_count": 1,
            "receipt_count": 1,
            "uncertain_effect_count": 0,
        }
    if claim_status == "claimed":
        return {
            "claim_count": 1,
            "receipt_count": 0,
            "uncertain_effect_count": 0,
        }
    return {
        "claim_count": int(claim_status != "missing"),
        "receipt_count": 0,
        "uncertain_effect_count": int(claim_status in {"invalid", "unknown"}),
    }


def _requires_bounded_source_repair(failure: dict[str, Any]) -> bool:
    """Keep deterministic adapter faults from fanning out as ordinary waits."""

    return (
        str(failure.get("category") or "") in AGENT_OWNED_FAILURE_CATEGORIES
        or str(failure.get("code") or "") == "blocked_download_frame_missing"
    )


def _source_failure_repair_progress(
    *,
    adapter: str,
    item: dict[str, Any],
    affected_items: list[dict[str, Any]],
    failure: dict[str, Any],
    failure_audit: dict[str, Any] | None,
    provider_contract_version: str,
    targeted_test_profile: str,
    retryability: str = "retryable",
) -> WriterProgress:
    fingerprint = FailureFingerprint(
        adapter=adapter,
        category=str(failure["category"]),
        code=str(failure["code"]),
        stage=str(failure["stage"]),
        failure_revision=_writer_failure_revision(),
        provider_contract_version=provider_contract_version,
    )
    summary = _claim_summary_from_failure_audit(
        failure_audit or {"claim_status": "missing"}
    )
    return WriterProgress.repair_required(
        item_identity=str(item["identity"]),
        fingerprint=fingerprint,
        repair_revision=None,
        affected_set_digest=affected_set_digest([
            {
                "identity": str(row["identity"]),
                "version_key": str(row.get("version_key") or "current"),
            }
            for row in affected_items
        ]),
        claim_receipt_summary=summary,
        targeted_test_profile=targeted_test_profile,
        narrow_resume_surface=f"{adapter}:{item['identity']}",
        retryability=retryability,
    )


class SemanticInputUnavailable(DailyError):
    """The current source could not obtain its requested agent input."""

    def __init__(
        self,
        request_or_message: dict[str, Any] | str,
        field: str | None = None,
    ):
        if isinstance(request_or_message, dict):
            message = f"daily runner is waiting for {field} on stdin"
            self.request = request_or_message
            self.field = str(field or "")
        else:
            message = str(request_or_message)
            self.request = {}
            self.field = str(field or "")
        super().__init__(message)


def _isolated_item_failure(
    exc: EnrichmentError,
    *,
    default_stage: str,
) -> tuple[dict[str, Any], bool]:
    if isinstance(exc, EnrichmentDiagnosticError):
        failure: dict[str, Any] = {
            "category": str(exc.diagnostic_category),
            "code": str(exc.diagnostic_code),
            "stage": str(exc.diagnostic_stage),
        }
        if exc.diagnostic_exit_code is not None:
            failure["exit_code"] = exc.diagnostic_exit_code
        operation = str(
            getattr(exc, "diagnostic_operation", "") or ""
        ).strip()
        if operation:
            failure["operation"] = operation
        return (
            failure,
            exc.diagnostic_code != "provider_download_filtered",
        )
    message = str(exc)
    known = {
        "subscription browser download receipt is not evidence-bound": (
            "state_error",
            "download_receipt_not_evidence_bound",
            "download_reconciliation",
            False,
        ),
        "subscription browser download receipt is invalid": (
            "state_error",
            "download_receipt_invalid",
            "download_reconciliation",
            False,
        ),
        "subscription browser download claim is invalid": (
            "state_error",
            "download_claim_invalid",
            "download_reconciliation",
            False,
        ),
        "subscription browser command timed out": (
            "timeout",
            "opencli_timeout",
            "browser_command",
            True,
        ),
        "OpenCLI browser command timed out": (
            "timeout",
            "opencli_timeout",
            "browser_command",
            True,
        ),
        "subscription browser command failed": (
            "transport_error",
            "opencli_command_failed",
            "browser_command",
            True,
        ),
        "OpenCLI browser command failed": (
            "transport_error",
            "opencli_command_failed",
            "browser_command",
            True,
        ),
        "OpenCLI returned invalid JSON": (
            "protocol_error",
            "opencli_invalid_json",
            "browser_command",
            True,
        ),
        "OpenCLI returned a non-object result": (
            "protocol_error",
            "opencli_non_object",
            "browser_command",
            True,
        ),
        "subscription browser download outcome is uncertain": (
            "uncertain_state",
            "download_receipt_reconciliation_required",
            "download_reconciliation",
            True,
        ),
        "subscription browser download waiter did not start": (
            "local_runtime_error",
            "download_waiter_not_started",
            "download_pretrigger",
            True,
        ),
    }
    category, code, stage, retryable = known.get(
        message,
        (
            "item_error",
            "item_processing_failed",
            default_stage,
            False,
        ),
    )
    return {"category": category, "code": code, "stage": stage}, retryable


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _latest_lv_video_goal(
    video_output_dir: Path,
    coordinator_events: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_path = video_output_dir / "manifest.json"
    if not manifest_path.is_file():
        return {
            "status": "not_observed",
            "success": False,
            "stage": "discovery",
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_state",
            "success": False,
            "stage": "manifest_validation",
        }
    items = manifest.get("items")
    if not isinstance(items, dict):
        return {
            "status": "invalid_state",
            "success": False,
            "stage": "manifest_validation",
        }
    candidates = [
        item
        for item in items.values()
        if isinstance(item, dict)
        and item.get("author") == "吕晓彤"
        and item.get("media_type") == "video"
        and item.get("present") is True
    ]
    if not candidates:
        return {
            "status": "not_observed",
            "success": False,
            "stage": "discovery",
        }
    latest = max(
        candidates,
        key=lambda item: (
            int(item.get("modified_at") or 0),
            str(item.get("version_first_seen_at") or ""),
            str(item.get("identity") or ""),
        ),
    )
    identity = str(latest.get("identity") or "")
    version = str(latest.get("version_key") or "")
    goal: dict[str, Any] = {
        "status": "pending",
        "success": False,
        "stage": "discovery",
        "identity": identity,
        "version_key": version,
        "name": str(latest.get("name") or ""),
        "modified_at": int(latest.get("modified_at") or 0),
    }
    for row in reversed(coordinator_events):
        if row.get("event") != "source_completed":
            continue
        for event in reversed((row.get("result") or {}).get("events") or []):
            if not isinstance(event, dict) or event.get("kind") != "source_event":
                continue
            binding = event.get("source_binding") or {}
            if (
                str(binding.get("source_identity") or event.get("event_id") or "")
                != identity
                or str(binding.get("publication_version") or "") != version
            ):
                continue
            report = event.get("gray_report") or {}
            if (
                report.get("status") == "published"
                and str(report.get("receipt") or "").strip()
                and str(report.get("detail_url") or "").strip()
            ):
                return {
                    **goal,
                    "status": "succeeded",
                    "success": True,
                    "stage": "report_published",
                    "analysis_status": "completed",
                    "report_status": "published",
                    "report_receipt": str(report["receipt"]),
                    "report_url": str(report["detail_url"]),
                    "coordinator_slot": str(row.get("slot") or ""),
                }
            return {
                **goal,
                "status": "incomplete",
                "stage": "report_publication",
                "analysis_status": "completed",
                "report_status": str(report.get("status") or "missing"),
            }
    decision_result_value = str(
        latest.get("decision_result_path") or ""
    ).strip()
    if decision_result_value:
        decision_result_path = Path(decision_result_value).expanduser()
        try:
            decision_result_bytes = decision_result_path.read_bytes()
            expected_result_sha256 = str(
                latest.get("decision_result_sha256") or ""
            )
            if (
                not expected_result_sha256
                or hashlib.sha256(decision_result_bytes).hexdigest()
                != expected_result_sha256
            ):
                raise ValueError("decision result hash mismatch")
            decision_result = json.loads(
                decision_result_bytes.decode("utf-8")
            )
            terminal = decision_result["items"][0]["daily_terminal"]
            binding = terminal["source_binding"]
            report = terminal["gray_report"]
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):
            return {
                **goal,
                "status": "invalid_state",
                "stage": "decision_result_validation",
            }
        if (
            terminal.get("kind") == "source_event"
            and str(binding.get("source_identity") or "") == identity
            and str(binding.get("publication_version") or "") == version
            and report.get("status") == "published"
            and str(report.get("receipt") or "").strip()
            and str(report.get("detail_url") or "").strip()
        ):
            return {
                **goal,
                "status": "succeeded",
                "success": True,
                "stage": "report_published",
                "analysis_status": "completed",
                "report_status": "published",
                "report_receipt": str(report["receipt"]),
                "report_url": str(report["detail_url"]),
                "coordinator_slot": "recovered_from_decision_result",
            }
        return {
            **goal,
            "status": "incomplete",
            "stage": "report_publication",
            "analysis_status": "completed",
            "report_status": str(report.get("status") or "missing"),
        }
    if str(latest.get("enrichment_job_id") or "").strip():
        return {
            **goal,
            "status": "processing",
            "stage": "cloud_enrichment",
        }
    receipt_path = (
        video_output_dir / "receipts" / f"lv_transfer_{version}.json"
    )
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                **goal,
                "status": "invalid_state",
                "stage": "cloud_transfer_receipt_validation",
            }
        if (
            receipt.get("status") == "completed"
            and str(receipt.get("source_identity") or "") == identity
            and str(receipt.get("source_version_key") or "") == version
        ):
            return {
                **goal,
                "status": "processing",
                "stage": "cloud_enrichment_registration",
                "transfer_status": "completed",
                "target_path": str(receipt.get("target_path") or ""),
                "target_size": int(receipt.get("target_size") or 0),
            }
        return {
            **goal,
            "status": "invalid_state",
            "stage": "cloud_transfer_receipt_validation",
        }
    claim_path = video_output_dir / "claims" / f"lv_transfer_{version}.json"
    if claim_path.is_file():
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                **goal,
                "status": "invalid_state",
                "stage": "cloud_transfer_claim_validation",
            }
        claim_status = str(claim.get("status") or "")
        if str(claim.get("source_identity") or "") != identity:
            return {
                **goal,
                "status": "invalid_state",
                "stage": "cloud_transfer_claim_validation",
            }
        if str(claim.get("source_version_key") or "") != version:
            return {
                **goal,
                "status": "invalid_state",
                "stage": "cloud_transfer_claim_validation",
            }
        if claim_status == "blocked":
            return {
                **goal,
                "status": "blocked",
                "stage": str(
                    claim.get("stage") or "cloud_transfer_confirmation"
                ),
                "transfer_status": claim_status,
                "trigger_attempt": int(claim.get("trigger_attempt") or 1),
                "user_action_required": True,
                "blocker_key": str(claim.get("blocker_key") or ""),
                "failure_reason": str(claim.get("failure_reason") or ""),
                "reconciliation_status": str(
                    claim.get("reconciliation_status") or ""
                ),
                **(
                    {"blocked_at": str(claim["blocked_at"])}
                    if claim.get("blocked_at")
                    else {}
                ),
            }
        return {
            **goal,
            "status": "processing",
            "stage": "cloud_transfer_confirmation",
            "transfer_status": claim_status,
            "trigger_attempt": int(claim.get("trigger_attempt") or 1),
            **(
                {"triggered_at": str(claim["triggered_at"])}
                if claim.get("triggered_at")
                else {}
            ),
            **(
                {
                    "next_poll_not_before": str(
                        claim["next_poll_not_before"]
                    )
                }
                if claim.get("next_poll_not_before")
                else {}
            ),
            **(
                {
                    "reconciliation_status": str(
                        claim["reconciliation_status"]
                    )
                }
                if claim.get("reconciliation_status")
                else {}
            ),
        }
    return {
        **goal,
        "status": "pending",
        "stage": "source_acquisition",
    }


def _read_agent_line(request: dict[str, Any]) -> str:
    """Read one complete agent response, including long JSON over a PTY."""

    descriptor: int | None = None
    original_attributes: list[Any] | None = None
    if sys.stdin.isatty():
        descriptor = sys.stdin.fileno()
        original_attributes = termios.tcgetattr(descriptor)
        response_attributes = list(original_attributes)
        response_attributes[6] = list(original_attributes[6])
        response_attributes[3] &= ~(termios.ICANON | termios.ECHO)
        response_attributes[6][termios.VMIN] = 1
        response_attributes[6][termios.VTIME] = 0
        termios.tcsetattr(descriptor, termios.TCSANOW, response_attributes)
    try:
        print(json.dumps(request, ensure_ascii=False, sort_keys=True), flush=True)
        return sys.stdin.readline()
    finally:
        if descriptor is not None and original_attributes is not None:
            termios.tcsetattr(
                descriptor,
                termios.TCSANOW,
                original_attributes,
            )


def _record_structured_input_consumption(
    request: dict[str, Any],
    *,
    field: str,
    path: Path,
) -> None:
    """Record one bound response, including a durable bundle reuse path."""

    structured_state = _STRUCTURED_INPUT_STATE.get()
    if structured_state is None:
        return
    progress = structured_state["progress"]
    details = progress.details
    request_values = {
        str(value)
        for value in request.values()
        if isinstance(value, (str, int)) and not isinstance(value, bool)
    }
    bindings = details["immutable_bindings"]
    if (
        structured_state.get("receipt") is not None
        or request.get("event") != details["request_kind"]
        or field != details["response_field"]
        or any(str(value) not in request_values for value in bindings.values())
    ):
        raise DailyError(
            "structured input does not match its persisted request binding"
        )
    structured_state["receipt"] = {
        "event": "structured_input_consumed",
        "request_id": details["request_id"],
        "request_schema_version": details["request_schema_version"],
        "response_field": details["response_field"],
        "immutable_bindings_sha256": hashlib.sha256(
            _canonical(bindings).encode("utf-8")
        ).hexdigest(),
        "request_sha256": hashlib.sha256(
            _canonical(request).encode("utf-8")
        ).hexdigest(),
        "response_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read_agent_path(request: dict[str, Any], field: str) -> Path:
    response = _read_agent_line(request)
    if not response:
        if request.get("analysis_request_path") or request.get("image_request_path"):
            raise SemanticInputUnavailable(request, field)
        raise SemanticInputUnavailable(
            f"daily runner requires {field} on stdin"
        )
    raw = response.strip()
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SemanticInputUnavailable(request, field) from exc
        raw = str(value.get(field) or "").strip()
    if not raw:
        raise SemanticInputUnavailable(request, field)
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise SemanticInputUnavailable(request, field)
    _record_structured_input_consumption(request, field=field, path=path)
    return path


def _persisted_validated_bundle(request: dict[str, Any]) -> Path | None:
    """Reuse a bundle already persisted for this semantic request."""

    artifact_dir = str(request.get("artifact_dir") or "").strip()
    if not artifact_dir:
        return None
    candidate = (
        Path(artifact_dir).expanduser().resolve()
        / "validated_bundle.json"
    )
    return candidate if candidate.is_file() else None


def _transcript_audit_contract(state: dict[str, Any]) -> dict[str, Any]:
    """Describe the exact character thirds consumed by transcript audit."""

    character_count = int(state.get("transcript_character_count") or 0)
    if character_count < 3:
        raise DailyError("transcript audit requires a nontrivial character count")
    first_boundary = (character_count + 2) // 3
    second_boundary = (character_count * 2 + 2) // 3
    return {
        "character_count": character_count,
        "excerpt_rule": "exact_contiguous_substring",
        "normalization": "none",
        "ranges": [
            {
                "position": "opening",
                "start_char_inclusive": 0,
                "end_char_exclusive": first_boundary,
            },
            {
                "position": "middle",
                "start_char_inclusive": first_boundary,
                "end_char_exclusive": second_boundary,
            },
            {
                "position": "ending",
                "start_char_inclusive": second_boundary,
                "end_char_exclusive": character_count,
            },
        ],
    }


def _require_canonical_semantic_artifact(
    bundle_path: Path,
    request: dict[str, Any],
) -> Path:
    """Fail closed unless the hourly response has a bound v2 receipt."""

    binding_request = request
    request_path_value = request.get("analysis_request_path") or request.get(
        "request_path"
    )
    if request_path_value:
        request_path = Path(str(request_path_value)).expanduser().resolve()
        try:
            persisted = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyError("canonical semantic request is invalid") from exc
        if not isinstance(persisted, dict):
            raise DailyError("canonical semantic request is invalid")
        binding_request = persisted
    receipt, _bundle = read_validated_bundle(bundle_path)
    validate_receipt_bindings(
        receipt,
        {
            "message_sha256": binding_request.get("message_sha256"),
            "content_sha256": binding_request.get("content_sha256"),
            "handoff_id": binding_request.get("handoff_id"),
            "media_identity": binding_request.get("media_identity"),
            "media_sha256": binding_request.get("media_sha256"),
            "transcript_sha256": (
                binding_request.get("evidence_sha256")
                or binding_request.get("transcript_sha256")
            ),
            "source_identity": (
                binding_request.get("source_identity")
                or binding_request.get("identity")
            ),
            "source_version_key": (
                binding_request.get("source_version_key")
                or binding_request.get("version_key")
            ),
        },
    )
    return bundle_path


def _persist_semantic_request(
    request: dict[str, Any],
    *,
    output_dir: Path,
    request_id: str,
) -> dict[str, Any]:
    artifact_dir = (output_dir / "semantic_requests" / request_id).resolve()
    request_path = artifact_dir / "analysis_request.json"
    value = {
        **request,
        "artifact_dir": str(artifact_dir),
        "analysis_request_path": str(request_path),
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if request_path.is_file():
        try:
            prior = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyError("persisted semantic request is invalid") from exc
        if prior != value:
            raise DailyError("persisted semantic request changed after claim")
        return value
    temporary = request_path.with_name(f".{request_path.name}.partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(request_path)
    return value


def _verify_rollout_evidence(
    readback: RolloutReadback,
    evidence: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> None:
    """Verify local rollout facts and one self-hashed Automation readback."""

    required = {
        "schema_version",
        "automation_id",
        "writer_task_id",
        "active_writer_task_ids",
        "duplicate_automation_ids",
        "automation_owner",
        "cwd",
        "target_revision",
        "observed_at",
        "enabled",
        "schedule",
        "prompt_sha256",
        "receipt_sha256",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise DailyError("rollout Automation readback evidence is incomplete")
    unsigned = {key: evidence[key] for key in required - {"receipt_sha256"}}
    receipt_sha = hashlib.sha256(
        _canonical(unsigned).encode("utf-8")
    ).hexdigest()
    if evidence["receipt_sha256"] != receipt_sha:
        raise DailyError("rollout Automation readback receipt hash changed")
    observed_at = str(evidence["observed_at"])
    try:
        if datetime.fromisoformat(observed_at.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise DailyError("rollout Automation readback time is invalid") from exc
    active_ids = evidence["active_writer_task_ids"]
    duplicate_ids = evidence["duplicate_automation_ids"]
    repository_root = Path(__file__).resolve().parents[1]
    if (
        evidence["schema_version"] != 1
        or evidence["automation_id"] != readback.automation_id
        or evidence["writer_task_id"] != readback.writer_task_id
        or active_ids != [readback.writer_task_id]
        or duplicate_ids != []
        or evidence["automation_owner"] != readback.automation_id
        or Path(str(evidence["cwd"])).resolve() != repository_root
        or evidence["target_revision"] != readback.target_revision
        or evidence["enabled"] is not True
        or not str(evidence["schedule"] or "").startswith("RRULE:")
        or not re.fullmatch(r"[0-9a-f]{64}", str(evidence["prompt_sha256"] or ""))
    ):
        raise DailyError("rollout Automation readback does not prove one writer")

    head = resolve_repository_revision(repository_root)
    remote = subprocess.run(
        ("git", "rev-parse", "--verify", "origin/main^{commit}"),
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=15,
    )
    remote_revision = remote.stdout.strip()
    if remote.returncode != 0 or head != readback.target_revision or remote_revision != head:
        raise DailyError("rollout target revision is not current pushed main")
    status_result = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=15,
    )
    if status_result.returncode != 0:
        raise DailyError("rollout worktree readback failed")
    unsafe_wip = [
        line
        for line in status_result.stdout.splitlines()
        if line and not line[3:].startswith(".scratch/")
    ]
    if unsafe_wip:
        raise DailyError("rollout worktree contains unprotected source WIP")
    config_path = Path(args.config).expanduser().resolve()
    if (
        not config_path.is_file()
        or stat.S_IMODE(config_path.stat().st_mode) & 0o077
    ):
        raise DailyError("rollout private config is missing or not private")
    if not Path(sys.executable).is_file():
        raise DailyError("rollout dependency runtime is unavailable")
    events_path = Path(args.output_dir).expanduser().resolve() / "events.jsonl"
    if not events_path.is_file():
        raise DailyError("rollout restored writer state is unavailable")


def _require_rollout_peer_gate(
    service: DailyCoordinator,
    *,
    automation_observed_at: str,
) -> dict[str, Any]:
    """Bind rollout acceptance to a recent persisted pass from the real gate."""

    rows = [
        row
        for row in service.convergence.events()
        if row.get("event") == "peer_gate_observed"
    ]
    if not rows or rows[-1].get("gate_result") != "pass":
        raise DailyError("rollout requires a persisted passing peer gate")
    gate = rows[-1]
    try:
        gate_time = datetime.fromisoformat(
            str(gate["observed_at"]).replace("Z", "+00:00")
        )
        automation_time = datetime.fromisoformat(
            automation_observed_at.replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as exc:
        raise DailyError("rollout peer gate time is invalid") from exc
    if (
        gate_time.tzinfo is None
        or automation_time.tzinfo is None
        or gate_time > automation_time
        or (automation_time - gate_time).total_seconds() > 600
    ):
        raise DailyError("rollout peer gate is stale or out of order")
    return gate


def _semantic_waiting_item(
    request: dict[str, Any],
    *,
    identity: str,
    version_key: str,
    name: str,
    author: str,
) -> dict[str, Any]:
    request_path = Path(
        str(request.get("analysis_request_path") or "")
    ).expanduser().resolve()
    if not request_path.is_file():
        raise DailyError("persisted semantic request is missing")
    try:
        persisted = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyError("persisted semantic request is invalid") from exc
    if not isinstance(persisted, dict):
        raise DailyError("persisted semantic request is invalid")
    evidence_path = Path(
        str(persisted.get("evidence_path") or request.get("evidence_path") or "")
    ).expanduser().resolve()
    evidence_sha256 = str(
        persisted.get("evidence_sha256") or request.get("evidence_sha256") or ""
    )
    if (
        not evidence_path.is_file()
        or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)
        or hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        != evidence_sha256
    ):
        raise DailyError("persisted semantic request changed evidence")
    return {
        "identity": identity,
        "version_key": version_key,
        "name": name,
        "author": author,
        "status": "waiting_semantic_input",
        "stage": "waiting_semantic_input",
        "analysis_request_path": str(request_path),
        "evidence_path": str(evidence_path),
        "evidence_sha256": evidence_sha256,
        "semantic_request_preserved": True,
        "external_business_effects_replayed": False,
    }


def _persisted_video_analysis_request(
    output_dir: Path,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    request_path = (
        output_dir
        / "artifacts"
        / str(item.get("version_key") or "")
        / "analysis_request.json"
    ).resolve()
    if not request_path.is_file():
        return None
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyError("persisted video semantic request is invalid") from exc
    if not isinstance(request, dict):
        raise DailyError("persisted video semantic request is invalid")
    evidence_path = Path(str(request.get("evidence_path") or "")).expanduser()
    if not evidence_path.is_absolute():
        evidence_path = evidence_path.resolve()
    evidence_sha256 = str(request.get("evidence_sha256") or "")
    if (
        request.get("event") != "subscription_video_analysis_input_required"
        or request.get("source_identity") != item.get("identity")
        or request.get("source_version_key") != item.get("version_key")
        or request.get("source") != item.get("source")
        or request.get("author") != item.get("author")
        or not evidence_path.is_file()
        or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)
        or hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        != evidence_sha256
    ):
        raise DailyError("persisted video semantic request changed evidence")
    return {
        **request,
        "analysis_request_path": str(request_path),
    }


def _read_agent_json(request: dict[str, Any]) -> dict[str, Any]:
    response = _read_agent_line(request)
    if not response:
        raise DailyError("daily runner requires a browser response on stdin")
    try:
        value = json.loads(response)
    except json.JSONDecodeError as exc:
        raise DailyError("daily browser response is invalid JSON") from exc
    if not isinstance(value, dict):
        raise DailyError("daily browser response must be a JSON object")
    return value


def _video_publication_context(
    item: dict[str, Any],
    state: dict[str, Any],
) -> DailyPublicationContext:
    """Bind a video decision to normalized request metadata.

    The provider manifest stores ``modified_at`` as epoch seconds, while the
    analysis request already exposes a timezone-aware publication time.  The
    request value is authoritative for publication; the epoch is only a
    compatibility fallback.
    """

    published_at = str(
        state.get("publication_time")
        or item.get("published_at")
        or ""
    ).strip()
    if not published_at:
        try:
            published_at = datetime.fromtimestamp(
                int(item["modified_at"]),
                tz=timezone.utc,
            ).isoformat(timespec="seconds")
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise DailyError(
                "subscription video lacks a publication timestamp"
            ) from exc
    evidence_sha256 = str(
        state.get("transcript_sha256")
        or state.get("episode_evidence_sha256")
        or state.get("evidence_sha256")
        or ""
    )
    if len(evidence_sha256) != 64:
        raise DailyError(
            "subscription video request lacks an evidence hash"
        )
    parts = item.get("parts") or [item]
    return DailyPublicationContext(
        adapter="subscription_video",
        source_identity=str(item["identity"]),
        publication_version=str(item["version_key"]),
        kol_id=(
            "kol-lucifer"
            if item["author"] == "路西法"
            else "kol-lv-xiaotong"
        ),
        source=str(item["source"]),
        source_published_at=published_at,
        media_types=("video",),
        source_parts=tuple(
            {
                "identity": str(part["identity"]),
                "version": str(part["version_key"]),
                "order": index,
                "size": int(part.get("size") or 0),
                "evidence_sha256": evidence_sha256,
            }
            for index, part in enumerate(parts, start=1)
        ),
    )


def _lv_publication_context(
    ingest: dict[str, Any],
    bundle_path: Path,
) -> DailyPublicationContext:
    """Build one source-neutral event, including an evidence-bound companion."""
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        decision_item = bundle["items"][0]
    except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise DailyError("Lv decision bundle is invalid") from exc
    parts = [{
        "identity": str(ingest["identity"]),
        "version": str(ingest["version_key"]),
        "order": 1,
        "size": int(Path(str(ingest["original_path"])).stat().st_size),
        "evidence_sha256": str(ingest["evidence_sha256"]),
    }]
    media_types = [str(ingest["media_type"])]
    relationship = decision_item.get("episode_relationship")
    if (
        ingest.get("media_type") == "pdf"
        and isinstance(relationship, dict)
        and relationship.get("document_role") == "video_summary"
        and relationship.get("primary_source_status") == "complete"
        and (
            relationship.get("semantic_comparison") or {}
        ).get("substantive_new_points") is True
    ):
        related = relationship.get("related_source_part")
        if not isinstance(related, dict):
            raise DailyError("Lv PDF companion source part is invalid")
        parts.append({
            "identity": str(related.get("identity") or ""),
            "version": str(related.get("version_key") or ""),
            "order": 2,
            "size": int(related.get("size") or 0),
            "evidence_sha256": str(
                related.get("transcript_sha256")
                or related.get("evidence_sha256")
                or ""
            ),
        })
        media_types.append(str(related.get("media_type") or "video"))
    if any(
        not part["identity"]
        or not part["version"]
        or not re.fullmatch(r"[0-9a-f]{64}", part["evidence_sha256"])
        for part in parts
    ):
        raise DailyError("Lv publication source parts are incomplete")
    if len(parts) > 1:
        source_identity = hashlib.sha256(
            ("lv-source-neutral-episode\n" + _canonical([
                {"identity": row["identity"]} for row in parts
            ])).encode("utf-8")
        ).hexdigest()
        publication_version = hashlib.sha256(
            (source_identity + "\n" + _canonical([
                {
                    "version": row["version"],
                    "evidence_sha256": row["evidence_sha256"],
                }
                for row in parts
            ])).encode("utf-8")
        ).hexdigest()
    else:
        source_identity = str(ingest["identity"])
        publication_version = str(ingest["version_key"])
    return DailyPublicationContext(
        adapter="lv_text_image",
        source_identity=source_identity,
        publication_version=publication_version,
        kol_id="kol-lv-xiaotong",
        source="吕晓彤订阅",
        source_published_at=str(ingest["published_at"]),
        media_types=tuple(dict.fromkeys(media_types)),
        source_parts=tuple(parts),
    )


def _lv_suppressed_companion_terminal(
    relationship: dict[str, Any],
) -> dict[str, Any]:
    effects = relationship.get("business_effects") or {}
    if (
        relationship.get("status") != "completed"
        or relationship.get("route") != "companion_suppressed"
        or not str(relationship.get("identity") or "")
        or not str(relationship.get("version_key") or "")
        or effects != {
            "report": "not_created",
            "notification": "not_created",
            "book_kol_us": "not_created",
            "durable_knowledge": "not_created",
        }
    ):
        raise DailyError("suppressed Lv companion terminal is incomplete")
    identity = str(relationship["identity"])
    version = str(relationship["version_key"])
    return {
        "kind": "source_event",
        "event_id": identity,
        "source_binding": {
            "source_identity": identity,
            "publication_version": version,
        },
        "content_value": {
            "status": "low_density",
            "reason": (
                "完整主视频已覆盖该伴随摘要，且语义比较确认没有新增观点。"
            ),
        },
        "gray_report": {"status": "not_created"},
        "alert": {"status": "not_created"},
        "book_kol_us": {
            "book": "KOL-US",
            "paper_only": True,
            "status": "no_trade",
            "reason": "同一真实事件已完成纸面终态；伴随摘要不重复建仓。",
        },
        "knowledge_effect": {
            "status": "no_reusable_knowledge",
            "reason": "完整主视频已覆盖该摘要，未形成新增知识。",
        },
        "relationship_receipt_sha256": hashlib.sha256(
            _canonical(relationship).encode("utf-8")
        ).hexdigest(),
        "coordinator_source_video_bytes": 0,
    }


def _sender(title: str, body: str) -> dict[str, str]:
    result = notify(title, body, macos=False, audience="kol")
    if not isinstance(result, dict):
        raise DailyError("KOL notification relay returned an invalid result")
    return {str(key): str(value) for key, value in result.items()}


def _standalone_writer_result(adapter: str, runner) -> dict[str, Any]:
    """Keep manual source/maintenance commands on the writer contract."""

    user_action: dict[str, str] | None = None
    try:
        outcome = runner()
    except UserActionBlocker as exc:
        identity = f"{adapter}:source"
        user_action = {
            "action": exc.action,
            "blocker_identity": f"{adapter}:{exc.blocker_key}",
            "dedup_key": f"{adapter}:{exc.blocker_key}",
        }
        waiting_items = exc.waiting_items or [{
            "identity": identity,
            "stage": "external_authorization",
            "user_action_required": True,
            **user_action,
        }]
        outcome = {
            "status": "waiting",
            "user_action_required": True,
            "waiting_count": len(waiting_items),
            "waiting_items": waiting_items,
        }
        if exc.claim_receipt_summary is not None:
            outcome["claim_receipt_summary"] = exc.claim_receipt_summary
    except SemanticInputUnavailable as exc:
        outcome = {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [exc.request] if exc.request else [{
                "stage": "semantic_input",
                "failure": {
                    "category": "input_error",
                    "code": "semantic_input_unavailable",
                    "stage": "semantic_input",
                    "retryable": True,
                },
            }],
        }
    except EnrichmentDiagnosticError as exc:
        outcome = {
            "status": "waiting",
            "failure": {
                "category": exc.diagnostic_category,
                "code": exc.diagnostic_code,
                "stage": exc.diagnostic_stage,
                "retryable": True,
            },
        }
    except EnrichmentError:
        outcome = {
            "status": "waiting",
            "failure": {
                "category": "source_error",
                "code": "standalone_source_error",
                "stage": "source_run",
                "retryable": True,
            },
        }
    except Exception:
        outcome = {
            "status": "waiting",
            "failure": {
                "category": "code_error",
                "code": "standalone_runner_exception",
                "stage": "standalone_run",
                "retryable": True,
            },
        }
    if not isinstance(outcome, dict):
        outcome = {
            "status": "waiting",
            "failure": {
                "category": "schema_error",
                "code": "standalone_result_invalid",
                "stage": "standalone_run",
                "retryable": True,
            },
        }
    progress = normalize_source_result(
        adapter,
        outcome,
        failure_revision=_writer_failure_revision(),
        provider_contract_version="xiaocao_writer_v1",
        user_action=user_action,
    )
    return {
        **{key: value for key, value in outcome.items() if key != "retryable"},
        "resume_policy": progress.next_action,
        "writer_progress": progress.to_dict(),
    }


def _classified_source(name: str, runner):
    def run():
        try:
            return runner()
        except SemanticInputUnavailable as exc:
            raise TransientSourceError(
                "semantic input unavailable",
                category="input_error",
                code="semantic_input_unavailable",
                stage="semantic_input",
            ) from exc
        except DailyError:
            raise
        except EnrichmentError as exc:
            message = str(exc)
            if message == "Lv subscription share URL is invalid":
                raise UserActionBlocker(
                    "lv-share-url-invalid",
                    "请更新 xiaocao.yaml 中吕晓彤唯一百度分享链接。",
                ) from exc
            if message == "Lv subscription share code is missing":
                raise UserActionBlocker(
                    "lv-share-code-missing",
                    "请补全 xiaocao.yaml 中吕晓彤唯一百度分享提取码。",
                ) from exc
            if message == "Lv subscription share is expired":
                raise UserActionBlocker(
                    "lv-share-expired",
                    "请更新 xiaocao.yaml 中吕晓彤唯一百度分享链接和提取码；当前分享页已失效。",
                ) from exc
            if message == "subscription share authorization requires user confirmation":
                raise UserActionBlocker(
                    f"{name}-share-authorization",
                    "请在已授权百度网盘页面完成当前分享的访问确认，并保持既有"
                    " OpenCLI 会话可访问；完成后下一小时会复核同一来源。",
                ) from exc
            diagnostic_code = str(
                getattr(exc, "diagnostic_code", "")
            )
            if diagnostic_code == "provider_authentication_required":
                raise UserActionBlocker(
                    f"{name}-provider-authentication",
                    "请在已授权百度网盘页面重新完成登录或访问授权，并保持既有"
                    " OpenCLI 会话可访问；完成后下一小时会复核同一来源。",
                ) from exc
            if diagnostic_code == "provider_captcha_required":
                raise UserActionBlocker(
                    f"{name}-provider-captcha",
                    "请在已授权百度网盘页面完成验证码和访问授权，并保持既有"
                    " OpenCLI 会话可访问；"
                    "完成后下一小时会复核同一来源。",
                ) from exc
            if message in {
                "OpenCLI session is not authenticated",
                "OpenCLI login is required",
            }:
                raise UserActionBlocker(
                    f"{name}-opencli-login",
                    "请在已授权浏览器中重新登录百度网盘，并保持既有 OpenCLI 会话可访问。",
                ) from exc
            if message == "Xiaoetong account login is required":
                raise UserActionBlocker(
                    "xiaocao-wechat-live-xiaoetong-login",
                    "请在本次保留的页面完成小鹅通账号登录，并保持该 Browser "
                    "标签页可用；不要把直播口令填入账号密码框。完成后，下一小时"
                    "会复核同一视频。",
                ) from exc
            if message == "captcha_required":
                raise UserActionBlocker(
                    f"{name}-captcha",
                    "请在已授权百度网盘页面完成验证码，然后等待下一小时自动恢复。",
                ) from exc
            if message == "wechat_official_captcha_required":
                raise UserActionBlocker(
                    "wechat-official-opencli-captcha",
                    "请在远端现有 OpenCLI Edge 会话中打开对应公众号文章并完成"
                    "微信验证；不要新建抓取器或循环重试。完成后保持该会话可用，"
                    "下一小时会重新验收同一文章。",
                ) from exc
            if message == (
                "Lv cloud transfer did not materialize after bounded "
                "exact reconciliation"
            ):
                raise UserActionBlocker(
                    "lv-cloud-transfer-not-materialized",
                    "百度网盘已两次确认转存，但目标目录和全局精确搜索均无"
                    "对应文件。请检查网盘容量或转存限制，并手动把最新吕晓彤"
                    "视频保存到 /课程/自己的课/吕晓彤；完成后保持 Edge "
                    "登录，下一小时会只读对账并继续解析。",
                ) from exc
            if message == "Lv cloud transfer was rejected by provider":
                raise UserActionBlocker(
                    "lv-cloud-transfer-provider-rejected",
                    "百度网盘明确拒绝了吕晓彤视频转存。请检查网盘容量、"
                    "会员文件大小或转存上限，处理后手动把最新视频保存到 "
                    "/课程/自己的课/吕晓彤；保持 Edge 登录后，下一小时"
                    "会只读对账并继续解析。",
                ) from exc
            raise TransientSourceError(
                message,
                category=str(
                    getattr(exc, "diagnostic_category", "source_error")
                ),
                code=str(
                    getattr(exc, "diagnostic_code", "source_temporarily_unavailable")
                ),
                stage=str(getattr(exc, "diagnostic_stage", "source_run")),
            ) from exc

    return run


def _next_source_poll_not_before() -> str:
    """Bound a provider retry to the next local wall-clock hour."""

    observed = datetime.now().astimezone()
    deadline = (observed + timedelta(hours=1)).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    return deadline.isoformat(timespec="seconds")


def _classified_narrow_source(name: str, runner):
    def run(surface: str):
        user_action: dict[str, str] | None = None
        try:
            outcome = _classified_source(name, lambda: runner(surface))()
        except UserActionBlocker as exc:
            user_action = {
                "action": exc.action,
                "blocker_identity": exc.blocker_key,
                "dedup_key": exc.blocker_key,
            }
            waiting_items = exc.waiting_items or [{
                "identity": f"{name}:source",
                "stage": "external_authorization",
                "user_action_required": True,
                **user_action,
            }]
            outcome = {
                "status": "waiting",
                "user_action_required": True,
                "waiting_count": len(waiting_items),
                "waiting_items": waiting_items,
            }
            if exc.claim_receipt_summary is not None:
                outcome["claim_receipt_summary"] = (
                    exc.claim_receipt_summary
                )
        except TransientSourceError as exc:
            failure = exc.diagnostic()
            waiting_item = {
                "identity": f"{name}:source",
                "stage": failure["stage"],
                "failure": failure,
            }
            if failure["category"] in {
                "provider_error",
                "timeout",
                "transport_error",
            } or (
                failure["category"], failure["code"]
            ) in BOUNDED_SOURCE_FAILURES:
                waiting_item["next_poll_not_before"] = (
                    _next_source_poll_not_before()
                )
            outcome = {
                "status": "waiting",
                "failure": failure,
                "waiting_items": [waiting_item],
            }
        if isinstance(outcome.get("writer_progress"), dict):
            return outcome
        progress = normalize_source_result(
            name,
            outcome,
            failure_revision=_writer_failure_revision(),
            provider_contract_version="xiaocao_writer_v1",
            user_action=user_action,
        )
        return {
            **{key: value for key, value in outcome.items() if key != "retryable"},
            "resume_policy": progress.next_action,
            "writer_progress": progress.to_dict(),
        }

    return run


def _classified_progress_source(name: str, runner):
    def run(progress: WriterProgress):
        return _classified_source(name, lambda: runner(progress))()

    return run


def _source_cli_narrow_runner(runtime: "DailyRuntime", adapter: str):
    if adapter == "lv_text_image":
        return runtime.lv_narrow_resume
    if adapter == "subscription_video":
        return runtime.videos_narrow_resume
    if adapter == "xiaocao_wechat_live":
        return runtime.xiaocao_wechat_narrow_resume
    raise DailyError("source repair adapter has no CLI narrow resume")


def _subscription_video_structured_progress(
    runtime: "DailyRuntime",
    identity: str,
) -> WriterProgress:
    service = SubscriptionVideoService(
        runtime.args.video_output_dir,
        config_path=runtime.args.config,
    )
    exact = _one_exact_pending(
        service.pending_items(),
        identity,
        label="video structured input",
    )
    if len(exact) != 1:
        raise DailyError("video structured input target is not pending")
    item = exact[0]
    request = _persisted_video_analysis_request(
        runtime.args.video_output_dir,
        item,
    )
    if request is None:
        raise DailyError("video structured input request is missing")
    waiting_item = _semantic_waiting_item(
        request,
        identity=str(item["identity"]),
        version_key=str(item["version_key"]),
        name=str(item.get("name") or ""),
        author=str(item.get("author") or "吕晓彤"),
    )
    progress = normalize_source_result(
        "subscription_video",
        {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [waiting_item],
        },
        failure_revision=_writer_failure_revision(),
        provider_contract_version="xiaocao_writer_v1",
    )
    if progress.status != "structured_input":
        raise DailyError("video structured input request did not normalize")
    return progress


def _lv_text_image_structured_progress(
    runtime: "DailyRuntime",
    identity: str,
) -> WriterProgress:
    service = runtime._lv_service_for_sweep()
    exact = _one_exact_pending(
        service.pending_items(),
        identity,
        label="Lv structured input",
    )
    if len(exact) != 1:
        raise DailyError("Lv structured input target is not pending")
    item = exact[0]
    request_path = (
        runtime.args.lv_output_dir
        / "artifacts"
        / str(item["version_key"])
        / "analysis_request.json"
    )
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyError("Lv structured input request is missing") from exc
    if (
        not isinstance(request, dict)
        or request.get("identity") != item.get("identity")
        or request.get("version_key") != item.get("version_key")
        or not re.fullmatch(
            r"[0-9a-f]{64}",
            str(request.get("evidence_sha256") or ""),
        )
    ):
        raise DailyError("Lv structured input request changed")
    request = {
        **request,
        "analysis_request_path": str(request_path.resolve()),
    }
    waiting_item = _semantic_waiting_item(
        request,
        identity=str(item["identity"]),
        version_key=str(item["version_key"]),
        name=str(item.get("name") or ""),
        author=str(item.get("author") or "吕晓彤"),
    )
    progress = normalize_source_result(
        "lv_text_image",
        {
            "status": "waiting",
            "waiting_count": 1,
            "waiting_items": [waiting_item],
        },
        failure_revision=_writer_failure_revision(),
        provider_contract_version="xiaocao_writer_v1",
    )
    if progress.status != "structured_input":
        raise DailyError("Lv structured input request did not normalize")
    return progress


def _source_cli_structured_input_binding(
    runtime: "DailyRuntime",
    adapter: str,
    identity: str,
) -> tuple[WriterProgress, Any]:
    if adapter == "lv_text_image":
        return (
            _lv_text_image_structured_progress(runtime, identity),
            runtime.lv_structured_input,
        )
    if adapter == "subscription_video":
        return (
            _subscription_video_structured_progress(runtime, identity),
            runtime.videos_structured_input,
        )
    raise DailyError("resume-source-input adapter has no exact CLI binding")


def _subscription_video_terminal_progress(
    runtime: "DailyRuntime",
    identity: str,
) -> WriterProgress:
    manifest = SubscriptionVideoService(
        runtime.args.video_output_dir,
        config_path=runtime.args.config,
    ).status()
    candidates = []
    for collection_name in ("items", "episodes"):
        collection = manifest.get(collection_name)
        if isinstance(collection, dict):
            candidate = collection.get(identity)
            if isinstance(candidate, dict):
                candidates.append(candidate)
    if len(candidates) != 1:
        raise DailyError("video terminal reconciliation target changed")
    item = candidates[0]
    result_sha256 = str(item.get("decision_result_sha256") or "")
    if (
        item.get("completed_version_key") != item.get("version_key")
        or not re.fullmatch(r"[0-9a-f]{64}", result_sha256)
    ):
        raise DailyError("video terminal reconciliation is not complete")
    return WriterProgress.reconcile_required(
        item_identity=identity,
        stage="business_terminal_reconciliation",
        effect_kind="source_terminal",
        claim_identity=(
            f"subscription_video_terminal:{identity}:{result_sha256}"
        ),
        readback_operation="read_subscription_video_terminal_receipts",
        claim_receipt_summary={
            "claim_count": 2,
            "receipt_count": 2,
            "uncertain_effect_count": 0,
        },
    )


def _lv_text_image_terminal_decision(
    runtime: "DailyRuntime",
    identity: str,
) -> dict[str, Any]:
    service = runtime._lv_service_for_sweep()
    item = (service.status().get("items") or {}).get(identity)
    if not isinstance(item, dict):
        raise DailyError("Lv terminal reconciliation target changed")
    version = str(item.get("version_key") or "")
    artifact_dir = (
        runtime.args.lv_output_dir / "artifacts" / version
    ).expanduser().resolve()
    state_path = artifact_dir / "decision_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyError("Lv terminal decision state is incomplete") from exc
    result_path = Path(
        str(state.get("decision_result_path") or "")
    ).expanduser().resolve()
    result_sha256 = str(state.get("decision_result_sha256") or "")
    if (
        state.get("status") != "decided"
        or state.get("identity") != identity
        or state.get("version_key") != version
        or result_path != artifact_dir / "decision_result.json"
        or not result_path.is_file()
        or not re.fullmatch(r"[0-9a-f]{64}", result_sha256)
        or hashlib.sha256(result_path.read_bytes()).hexdigest()
        != result_sha256
    ):
        raise DailyError("Lv terminal decision receipt is incomplete")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        validate_decision_completion(result)
        terminal = dict(result["items"][0]["daily_terminal"])
        validate_source_event(terminal)
    except (
        OSError,
        json.JSONDecodeError,
        EnrichmentError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise DailyError("Lv terminal result lacks a valid daily receipt") from exc
    source_binding = terminal.get("source_binding") or {}
    if (
        terminal.get("event_id") != identity
        or source_binding.get("source_identity") != identity
        or source_binding.get("publication_version") != version
    ):
        raise DailyError("Lv terminal result changed its source binding")
    return {
        "item": item,
        "state": state,
        "terminal": terminal,
        "result_sha256": result_sha256,
    }


def _lv_text_image_terminal_progress(
    runtime: "DailyRuntime",
    identity: str,
) -> WriterProgress:
    decision = _lv_text_image_terminal_decision(runtime, identity)
    terminal = decision["terminal"]
    promoted = (terminal.get("gray_report") or {}).get("status") == "published"
    effect_count = 2 if promoted else 0
    return WriterProgress.reconcile_required(
        item_identity=identity,
        stage="business_terminal_reconciliation",
        effect_kind="source_terminal",
        claim_identity=(
            f"lv_text_image_terminal:{identity}:"
            f"{decision['result_sha256']}"
        ),
        readback_operation="read_lv_text_image_terminal_receipts",
        claim_receipt_summary={
            "claim_count": effect_count,
            "receipt_count": effect_count,
            "uncertain_effect_count": 0,
        },
    )


def _source_cli_terminal_binding(
    runtime: "DailyRuntime",
    adapter: str,
    identity: str,
) -> tuple[WriterProgress, Any]:
    if adapter == "lv_text_image":
        return (
            _lv_text_image_terminal_progress(runtime, identity),
            runtime.lv_terminal_reconcile,
        )
    if adapter == "subscription_video":
        return (
            _subscription_video_terminal_progress(runtime, identity),
            runtime.videos_terminal_reconcile,
        )
    raise DailyError(
        "reconcile-source-terminal adapter has no exact CLI binding"
    )


def _exact_progress_surface(adapter: str, surface: str) -> str:
    prefix = f"{adapter}:"
    value = str(surface or "")
    if not value.startswith(prefix) or value == prefix:
        raise DailyError(f"{adapter} narrow progress surface is invalid")
    value = value[len(prefix):]
    while value.startswith(prefix):
        value = value[len(prefix):]
    if not value:
        raise DailyError(f"{adapter} narrow progress surface is invalid")
    return value


def _adapter_scope_resume(adapter: str, surface: str, runner):
    if _exact_progress_surface(adapter, surface) != "source":
        raise DailyError(f"{adapter} cannot widen an exact narrow resume")
    return runner()


def _missing_progress_operation(adapter: str, operation: str):
    def missing(*_args, **_kwargs):
        raise DailyError(f"{adapter} lacks {operation} progress handler")

    return missing


def _one_exact_pending(
    rows: list[dict[str, Any]],
    identity: str | None,
    *,
    label: str,
) -> list[dict[str, Any]]:
    if identity is None:
        return rows
    exact = [
        row
        for row in rows
        if str(row.get("identity") or "") == identity
    ]
    if len(exact) != 1:
        raise DailyError(f"{label} target is not one exact pending item")
    return exact


def _lv_transfer_claim_binding(
    output_dir: Path,
    item: dict[str, Any],
) -> dict[str, str]:
    version = str(item.get("version_key") or "")
    identity = str(item.get("identity") or "")
    claim_path = output_dir / "claims" / f"lv_transfer_{version}.json"
    if not claim_path.is_file():
        return {}
    try:
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyError("Lv transfer claim is invalid") from exc
    claim_id = str(claim.get("claim_id") or "")
    if (
        not claim_id
        or str(claim.get("source_identity") or "") != identity
        or str(claim.get("source_version_key") or "") != version
    ):
        raise DailyError("Lv transfer claim binding changed")
    return {
        "effect_kind": "cloud_transfer",
        "claim_identity": f"lv_transfer:{version}:{claim_id}",
        "readback_operation": "read_lv_transfer_claim_receipt",
    }


def _lv_transfer_blocked_item_projection(
    output_dir: Path,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Expose blocked Lv objects without touching their external claims."""

    blocked_items: list[dict[str, Any]] = []
    for item in items:
        if (
            item.get("source") != LV_SOURCE
            or item.get("media_type") != "video"
        ):
            continue
        version = str(item.get("version_key") or "")
        claim_path = output_dir / "claims" / f"lv_transfer_{version}.json"
        if not claim_path.is_file():
            continue
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyError("Lv transfer claim is invalid") from exc
        if (
            not str(claim.get("claim_id") or "")
            or str(claim.get("source_identity") or "")
            != str(item.get("identity") or "")
            or str(claim.get("source_version_key") or "") != version
        ):
            raise DailyError("Lv transfer claim binding changed")
        if claim.get("status") != "blocked":
            continue
        blocker_key = str(claim.get("blocker_key") or "")
        if blocker_key not in {
            "lv-cloud-transfer-not-materialized",
            "lv-cloud-transfer-provider-rejected",
        }:
            continue
        side_effect_uncertain = (
            claim.get("side_effect_uncertain") is True
            or claim.get("provider_outcome") == "unobserved"
        )
        blocked_items.append({
            "identity": str(item.get("identity") or ""),
            "version_key": version,
            "name": str(item.get("name") or ""),
            "stage": str(
                claim.get("stage") or "cloud_transfer_confirmation"
            ),
            "status": "blocked",
            "blocker_key": blocker_key,
            "reconciliation_status": str(
                claim.get("reconciliation_status") or ""
            ),
            "trigger_attempt": int(claim.get("trigger_attempt") or 0),
            "side_effect_uncertain": side_effect_uncertain,
        })
    blocked_items.sort(
        key=lambda row: (
            -int(next(
                (
                    item.get("remote_activity_at")
                    or item.get("modified_at")
                    or 0
                    for item in items
                    if str(item.get("identity") or "") == row["identity"]
                ),
                0,
            )),
            row["name"],
        )
    )
    return blocked_items, {
        "claim_count": len(blocked_items),
        "receipt_count": 0,
        "uncertain_effect_count": sum(
            int(row["side_effect_uncertain"])
            for row in blocked_items
        ),
    }


def _lv_transfer_user_action_blocker(
    output_dir: Path,
    pending: list[dict[str, Any]],
    current: dict[str, Any],
    *,
    blocker_key: str,
    action: str,
) -> UserActionBlocker:
    blocked_items, summary = _lv_transfer_blocked_item_projection(
        output_dir,
        pending,
    )
    if not blocked_items:
        blocked_items = [{
            "identity": str(current.get("identity") or ""),
            "version_key": str(current.get("version_key") or ""),
            "name": str(current.get("name") or ""),
            "stage": "cloud_transfer_confirmation",
            "status": "blocked",
            "blocker_key": blocker_key,
            "side_effect_uncertain": (
                blocker_key != "lv-cloud-transfer-provider-rejected"
            ),
        }]
        summary = {
            "claim_count": 0,
            "receipt_count": 0,
            "uncertain_effect_count": 1,
        }
    return UserActionBlocker(
        blocker_key,
        action,
        waiting_items=[{
            "identity": "subscription_video:source",
            "stage": "cloud_transfer_confirmation",
            "user_action_required": True,
            "blocked_items": blocked_items,
        }],
        claim_receipt_summary=summary,
    )


def _reconciliation_result(
    progress: WriterProgress,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    if outcome.get("events"):
        raise DailyError(
            "authoritative readback must not replay an external business effect"
        )
    evidence_sha256 = hashlib.sha256(
        _canonical(outcome).encode("utf-8")
    ).hexdigest()
    return {
        "outcome": outcome,
        "reconciliation_receipt": {
            "event": "reconciliation_completed",
            "claim_identity": progress.details["claim_identity"],
            "readback_operation": progress.details["readback_operation"],
            "readback_evidence_sha256": evidence_sha256,
            "external_business_effects_replayed": False,
        },
    }


def _reconciliation_pending(progress: WriterProgress) -> dict[str, Any]:
    return {
        "status": "waiting",
        "waiting_count": 1,
        "waiting_items": [{
            "identity": progress.item_identity,
            "stage": progress.stage,
            "failure": {
                "category": "uncertain_state",
                "code": "authoritative_readback_still_uncertain",
                "stage": progress.stage,
                "retryable": False,
            },
        }],
        "writer_progress": progress.to_dict(),
    }


def _consume_structured_input(
    progress: WriterProgress,
    runner,
) -> dict[str, Any]:
    state: dict[str, Any] = {"progress": progress, "receipt": None}
    token = _STRUCTURED_INPUT_STATE.set(state)
    try:
        outcome = runner()
    finally:
        _STRUCTURED_INPUT_STATE.reset(token)
    receipt = state.get("receipt")
    if not isinstance(receipt, dict):
        raise DailyError(
            "structured input handler did not consume its bound response"
        )
    return {
        "outcome": outcome,
        "structured_input_receipt": receipt,
    }


def _cloud_handoff_binding(
    result: dict[str, Any],
) -> tuple[str, str] | None:
    rows = result.get("source_results")
    if not isinstance(rows, list):
        rows = [result]
    bindings: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("name") not in {None, "xiaocao_wechat_live"}:
            continue
        waiting_items = row.get("waiting_items")
        if not isinstance(waiting_items, list):
            continue
        for item in waiting_items:
            if not isinstance(item, dict) or item.get("stage") != "cloud_handoff":
                continue
            identity = str(item.get("identity") or "")
            capture_job_id = str(item.get("capture_job_id") or "")
            if not identity or not capture_job_id:
                raise DailyError("cloud handoff wait lacks an exact binding")
            bindings.append((identity, capture_job_id))
    if len(bindings) > 1:
        raise DailyError("capture-local found multiple cloud handoff bindings")
    return bindings[0] if bindings else None


def _follow_cloud_handoff(
    runtime: "DailyRuntime",
    sweep_result: dict[str, Any],
) -> dict[str, Any] | None:
    binding = _cloud_handoff_binding(sweep_result)
    if binding is None:
        return None
    identity, capture_job_id = binding
    while True:
        result = runtime.xiaocao_cloud_handoff(identity, capture_job_id)
        if result.get("handoff_dispatched") or result.get("already_completed"):
            return result
        current = _cloud_handoff_binding(result)
        if current != binding:
            raise DailyError("cloud handoff follow-up lost its exact binding")
        _cloud_handoff_sleep(CLOUD_HANDOFF_POLL_SECONDS)


class DailyRuntime:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self._client: LiangHuiMcpClient | None = None
        self.publications = PublicationLedger(args.output_dir / "publications")
        self._lv_service: LvSubscriptionService | None = None
        self._lv_listing: dict[str, Any] | None = None
        self._lv_listing_error: EnrichmentError | None = None

    def _lianghui_client(self) -> LiangHuiMcpClient:
        client = getattr(self, "_client", None)
        if client is None:
            client = (
                LiangHuiMcpClient.from_config(self.args.lianghui_config)
                if self.args.lianghui_config is not None
                else LiangHuiMcpClient.from_config()
            )
            self._client = client
        return client

    def _mailbox(self) -> LiangHuiMailboxClient:
        return LiangHuiMailboxClient(
            MailboxLedger(self.args.mailbox_output_dir),
            exchange=_read_agent_json,
        )

    @staticmethod
    def _mailbox_terminal_progress(
        handoff_id: str,
        result: dict[str, Any],
    ) -> WriterProgress:
        """Bind the source terminal to the mailbox ack progress snapshot."""

        raw_progress = result.get("writer_progress")
        if isinstance(raw_progress, dict):
            progress = WriterProgress.from_dict(raw_progress)
            if progress.status != "terminal":
                raise DailyError(
                    "completed mailbox result has non-terminal writer progress"
                )
            return progress

        events = result.get("events")
        if (
            not isinstance(events, list)
            or len(events) != 1
            or not isinstance(events[0], dict)
        ):
            raise DailyError(
                "completed mailbox result lacks one source terminal event"
            )
        terminal = events[0]
        validate_source_event(terminal)

        def terminal_status(field: str) -> str:
            value = terminal.get(field)
            if not isinstance(value, dict):
                raise DailyError(
                    f"mailbox source terminal lacks {field} status"
                )
            status = str(value.get("status") or "")
            if not status or status == "not_applicable":
                raise DailyError(
                    f"mailbox source terminal has invalid {field} status"
                )
            return status

        content = terminal.get("content_value")
        if not isinstance(content, dict):
            raise DailyError("mailbox source terminal lacks content value")
        content_status = str(content.get("status") or "")
        if not content_status or content_status == "not_applicable":
            raise DailyError("mailbox source terminal has invalid content status")

        gray_status = terminal_status("gray_report")
        alert_status = terminal_status("alert")
        book_status = terminal_status("book_kol_us")
        knowledge_status = terminal_status("knowledge_effect")
        inferred_effect_count = sum(
            status in {"published", "delivered", "filled"}
            for status in (gray_status, alert_status, book_status)
        )
        inferred_summary = {
            "claim_count": inferred_effect_count,
            "receipt_count": inferred_effect_count,
            "uncertain_effect_count": 0,
        }
        supplied_summary = result.get("claim_receipt_summary")
        summary = (
            inferred_summary
            if supplied_summary is None
            else dict(supplied_summary)
        )
        if summary != inferred_summary:
            raise DailyError(
                "mailbox source terminal claim summary does not match receipts"
            )

        return WriterProgress.terminal(
            item_identity=handoff_id,
            stage="mailbox_ack",
            content_terminal=content_status,
            gray_report_terminal=gray_status,
            reminder_terminal=alert_status,
            book_terminal=book_status,
            knowledge_terminal=knowledge_status,
            ack_status="acked",
            new_external_effect_count=inferred_effect_count,
            claim_receipt_summary=summary,
        )

    def _repair_validation(self) -> RepairValidationService:
        return RepairValidationService(
            Path(__file__).resolve().parents[1],
            ledger=RepairValidationLedger(
                self.args.mailbox_output_dir / "repair_validation.jsonl"
            ),
        )

    def reconcile_local_mailbox(self) -> list[dict[str, str]]:
        return self._mailbox().reconcile_local()

    def publish_mailbox_handoff(
        self,
        capsule: dict[str, Any],
        *,
        object_kind: str,
        title: str,
    ) -> dict[str, Any]:
        return self._mailbox().publish_handoff(
            capsule,
            object_kind=object_kind,
            title=title,
        )

    def _process_mailbox_message(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        handoff_id = str(message.get("message_id") or "")
        capsule = message.get("payload")
        if not isinstance(capsule, dict) or capsule.get("handoff_id") != handoff_id:
            raise EnrichmentDiagnosticError(
                "mailbox message is not bound to its handoff capsule",
                category="contract_error",
                code="mailbox_message_binding_invalid",
                stage="mailbox_validation",
            )
        if capsule.get("content_transport") == "public_url_only":
            try:
                imported = OfficialAccountInbox(
                    self.args.wechat_official_output_dir
                ).import_capsule(capsule)
            except EnrichmentError as exc:
                raise EnrichmentDiagnosticError(
                    "official mailbox handoff import was rejected",
                    category="contract_error",
                    code="official_handoff_import_rejected",
                    stage="mailbox_import",
                ) from exc
            if imported.get("status") not in {"accepted", "already_present"}:
                raise EnrichmentDiagnosticError(
                    "official mailbox handoff import is not durable",
                    category="contract_error",
                    code="official_handoff_import_not_durable",
                    stage="mailbox_import",
                )
            result = self.wechat_official(handoff_id=handoff_id)
        elif (
            capsule.get("source_mode") == "cloud_handoff"
            or (
                isinstance(capsule.get("netdisk_job_snapshot"), dict)
                and capsule["netdisk_job_snapshot"].get("source_mode")
                == "cloud_handoff"
            )
        ):
            try:
                XiaocaoLiveService(
                    self.args.xiaocao_output_dir,
                    decision_output=self.args.decision_output_dir,
                ).import_handoff_capsule(capsule)
            except EnrichmentError as exc:
                raise EnrichmentDiagnosticError(
                    "Xiaocao mailbox handoff import was rejected",
                    category="contract_error",
                    code="xiaocao_handoff_import_rejected",
                    stage="mailbox_import",
                ) from exc
            result = self.xiaocao(handoff_id=handoff_id)
        else:
            raise EnrichmentDiagnosticError(
                "mailbox handoff capsule type is unsupported",
                category="contract_error",
                code="mailbox_capsule_route_unsupported",
                stage="mailbox_routing",
            )
        completed = {
            str(value) for value in result.get("completed_handoff_ids", [])
        }
        response = {
            **result,
            "business_complete": handoff_id in completed,
        }
        if handoff_id in completed and (
            isinstance(result.get("writer_progress"), dict)
            or isinstance(result.get("events"), list)
        ):
            response["writer_progress"] = self._mailbox_terminal_progress(
                handoff_id,
                result,
            ).to_dict()
        return response

    def mailbox(self) -> dict[str, Any]:
        return RemoteMailboxDrain(
            self._mailbox(),
            processor=self._process_mailbox_message,
            failure_revision=_writer_failure_revision(),
        ).run()

    def resume_mailbox(
        self,
        message_id: str,
        *,
        repair_revision: str | None = None,
    ) -> dict[str, Any]:
        mailbox = self._mailbox()
        context = mailbox.ledger.repair_resume_context(message_id)
        validation = self._repair_validation()
        resolved_revision = repair_revision or validation.resolve_head()
        repair_authorizer = None
        if context.get("category") != "provider_wait":
            validation.require_current(
                context,
                repair_revision=resolved_revision,
            )
            repair_authorizer = (
                lambda claim, revision: validation.require_current(
                    claim,
                    repair_revision=revision,
                )
            )
        return RemoteMailboxDrain(
            mailbox,
            processor=self._process_mailbox_message,
            failure_revision=resolved_revision,
            repair_authorizer=repair_authorizer,
        ).run(
            only_message_id=message_id,
            repair_revision=resolved_revision,
        )

    def validate_repair(
        self,
        message_id: str,
        *,
        repair_revision: str | None = None,
    ) -> dict[str, Any]:
        mailbox = self._mailbox()
        context = mailbox.ledger.repair_resume_context(message_id)
        receipt = self._repair_validation().validate(
            context,
            repair_revision=repair_revision,
        )
        return receipt.to_dict()

    def _lv_service_for_sweep(self) -> LvSubscriptionService:
        if self._lv_service is None:
            self._lv_service = LvSubscriptionService.from_config(
                self.args.lv_output_dir,
                config_path=self.args.config,
            )
        return self._lv_service

    def _lv_listing_for_sweep(self) -> dict[str, Any]:
        if self._lv_listing is not None:
            return self._lv_listing
        if self._lv_listing_error is not None:
            raise self._lv_listing_error
        service = self._lv_service_for_sweep()
        try:
            self._lv_listing = service._read_opencli_listing(
                session=self.args.lv_session,
                profile=self.args.opencli_profile,
            )
        except EnrichmentError as exc:
            self._lv_listing_error = exc
            raise
        return self._lv_listing

    def _complete_lv_video_transcripts(self) -> list[dict[str, Any]]:
        manifest_path = self.args.video_output_dir / "manifest.json"
        if not manifest_path.is_file():
            return []
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        completed = []
        for item in (manifest.get("items") or {}).values():
            if (
                not isinstance(item, dict)
                or item.get("author") != "吕晓彤"
                or item.get("media_type") != "video"
                or item.get("present") is not True
            ):
                continue
            events_path = (
                self.args.video_output_dir
                / "enrichment"
                / str(item.get("version_key") or "")
                / "events.jsonl"
            )
            if not events_path.is_file():
                continue
            try:
                states = [
                    json.loads(line)
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (OSError, json.JSONDecodeError):
                continue
            state = next(
                (
                    row
                    for row in reversed(states)
                    if row.get("status") in {"verified", "decided"}
                    and row.get("transcript_path")
                    and row.get("transcript_sha256")
                ),
                None,
            )
            if not isinstance(state, dict):
                continue
            transcript_path = Path(str(state["transcript_path"])).expanduser()
            if not transcript_path.is_absolute():
                transcript_path = transcript_path.resolve()
            transcript_sha256 = str(state["transcript_sha256"])
            if (
                not transcript_path.is_file()
                or not re.fullmatch(r"[0-9a-f]{64}", transcript_sha256)
                or hashlib.sha256(transcript_path.read_bytes()).hexdigest()
                != transcript_sha256
            ):
                continue
            completed.append(
                {
                    key: item[key]
                    for key in (
                        "identity",
                        "version_key",
                        "provider_identity_sha256",
                        "path",
                        "name",
                        "size",
                        "modified_at",
                    )
                }
                | {
                    "transcript_complete": True,
                    "transcript_path": str(transcript_path.resolve()),
                    "transcript_sha256": transcript_sha256,
                }
            )
        return completed

    def _pipeline(
        self,
        context: DailyPublicationContext,
    ) -> DailyPublicationPipeline:
        lianghui = self._lianghui_client()
        delegate = DecisionPipeline(
            self.args.decision_output_dir,
            household_context_loader=functools.partial(
                _load_household_context_with_retry,
                lianghui,
            ),
        )
        return DailyPublicationPipeline(
            delegate,
            ledger=self.publications,
            client=lianghui,
            context=context,
        )

    @staticmethod
    def _terminal(result_path: Path | str) -> dict[str, Any]:
        value = json.loads(Path(result_path).read_text(encoding="utf-8"))
        try:
            terminal = value["items"][0]["daily_terminal"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DailyError("source result lacks a Ticket 07 terminal") from exc
        if not isinstance(terminal, dict):
            raise DailyError("source Ticket 07 terminal is invalid")
        return terminal

    @staticmethod
    def _metadata_companion_suppression_is_safe(
        row: dict[str, Any],
    ) -> bool:
        """Allow companion suppression only before acquisition begins."""
        return (
            row.get("media_type") == "pdf"
            and row.get("stage") == "discovered"
        )

    def lv(
        self,
        *,
        only_identity: str | None = None,
        refresh_listing: bool = True,
    ) -> dict[str, Any]:
        service = self._lv_service_for_sweep()
        if refresh_listing:
            listing = self._lv_listing_for_sweep()
            service.poll_opencli(
                session=self.args.lv_session,
                profile=self.args.opencli_profile,
                listing=listing,
            )
        migration_handler = getattr(
            service,
            "retire_packaged_historical_backlog",
            None,
        )
        eligibility_migration = (
            migration_handler() if callable(migration_handler) else None
        )
        if (
            eligibility_migration is not None
            and eligibility_migration.get("status") == "blocked"
        ):
            raise DailyError(
                "Lv historical eligibility migration did not pass its CAS gate"
            )
        pending = service.pending_items()
        if only_identity is not None and not any(
            str(row.get("identity") or "") == only_identity for row in pending
        ):
            retired = (
                service.status().get("items", {}).get(only_identity)
            )
            if (
                isinstance(retired, dict)
                and retired.get("pause_reason")
                == "historical_backlog_retired"
            ):
                return {
                    "status": "no_update",
                    "historical_retirement": {
                        "identity": only_identity,
                        "version_key": str(retired.get("version_key") or ""),
                        "pause_reason": "historical_backlog_retired",
                    },
                }
        pending.sort(
            key=lambda row: (
                -int(row.get("modified_at") or 0),
                str(row.get("path") or ""),
                str(row.get("identity") or ""),
            )
        )
        pending = _one_exact_pending(
            pending,
            only_identity,
            label="lv narrow repair",
        )
        complete_video_transcripts = self._complete_lv_video_transcripts()
        for row in pending:
            if not self._metadata_companion_suppression_is_safe(row):
                continue
            proof = service.metadata_companion_proof(
                str(row["identity"]),
                complete_video_transcripts=complete_video_transcripts,
            )
            if proof is not None:
                service.record_metadata_companion_suppression(
                    str(row["identity"]),
                    proof=proof,
                )
        pending = service.pending_items()
        pending.sort(
            key=lambda row: (
                -int(row.get("modified_at") or 0),
                str(row.get("path") or ""),
                str(row.get("identity") or ""),
            )
        )
        pending = _one_exact_pending(
            pending,
            only_identity,
            label="lv narrow repair",
        )
        if not pending:
            return {"status": "no_update"}
        events = []
        waiting = 0
        waiting_items = []
        suppressed = 0
        claim_receipt_summary = {
            "claim_count": 0,
            "receipt_count": 0,
            "uncertain_effect_count": 0,
        }
        for row in pending:
            identity = str(row["identity"])
            try:
                service.download_opencli(
                    identity,
                    session=self.args.lv_session,
                    profile=self.args.opencli_profile,
                )
            except EnrichmentError as exc:
                failure, retryable = _isolated_item_failure(
                    exc,
                    default_stage="small_item_processing",
                )
                failure_audit = service.record_item_failure(
                    identity,
                    failure=failure,
                    retryable=retryable,
                )
                item_summary = _claim_summary_from_failure_audit(
                    failure_audit or {}
                )
                for key in claim_receipt_summary:
                    claim_receipt_summary[key] += item_summary[key]
                waiting += 1
                waiting_item = {
                    "identity": identity,
                    "version_key": str(row.get("version_key") or ""),
                    "name": str(row.get("name") or ""),
                    "stage": failure["stage"],
                    "failure": {**failure, "retryable": retryable},
                }
                waiting_items.append(waiting_item)
                if failure["code"] in {
                    "blocked_download_frame_missing",
                    "provider_download_filtered",
                }:
                    affected = [
                        candidate
                        for candidate in pending
                        if candidate.get("media_type") == row.get("media_type")
                    ]
                    progress = _source_failure_repair_progress(
                        adapter="lv_text_image",
                        item=row,
                        affected_items=affected,
                        failure=failure,
                        failure_audit=failure_audit,
                        provider_contract_version=(
                            BLOCKED_DOWNLOAD_PROVIDER_CONTRACT_VERSION
                        ),
                        targeted_test_profile="kol_lv_download_recovery",
                        retryability=(
                            "retryable" if retryable else "not_retryable"
                        ),
                    )
                    return {
                        "status": "waiting",
                        "waiting_count": waiting,
                        "waiting_items": waiting_items,
                        "suppressed_companion_count": suppressed,
                        "resume_policy": progress.next_action,
                        "repair_key": progress.failure_fingerprint,
                        "repair_required": True,
                        "user_action_required": False,
                        "writer_progress": progress.to_dict(),
                        "claim_receipt_summary": (
                            progress.details["claim_receipt_summary"]
                        ),
                    }
                continue
            ingest = service.ingest_browser_download(identity)
            request = service.prepare_analysis_request(ingest)
            semantic_request = {
                **request,
                "event": "daily_analysis_input_required",
                "adapter": "lv_text_image",
                "analysis_request_path": request["request_path"],
                "required_content_value": (
                    "low_density|promoted(report_only|alert_eligible)"
                ),
            }
            bundle_path = _persisted_validated_bundle(semantic_request)
            reused_bundle = bundle_path is not None
            if bundle_path is None:
                try:
                    bundle_path = _read_agent_path(
                        semantic_request,
                        "bundle_path",
                    )
                except SemanticInputUnavailable as exc:
                    if not exc.request:
                        raise
                    waiting += 1
                    waiting_items.append(_semantic_waiting_item(
                        exc.request,
                        identity=identity,
                        version_key=str(row.get("version_key") or ""),
                        name=str(row.get("name") or ""),
                        author=str(row.get("author") or "吕晓彤"),
                    ))
                    # stdin EOF closes the semantic channel for this sweep. Do not
                    # acquire more pending items that cannot receive a bundle.
                    break
            bundle_path = _require_canonical_semantic_artifact(
                bundle_path,
                semantic_request,
            )
            if reused_bundle:
                _record_structured_input_consumption(
                    semantic_request,
                    field="bundle_path",
                    path=bundle_path,
                )
            if ingest["media_type"] == "pdf":
                relationship = service.record_pdf_relationship(
                    identity,
                    bundle_path=bundle_path,
                    complete_video_transcripts=complete_video_transcripts,
                )
                if relationship["route"] == "companion_suppressed":
                    events.append(
                        _lv_suppressed_companion_terminal(relationship)
                    )
                    suppressed += 1
                    continue
                if relationship["route"] == "waiting_primary_source":
                    waiting += 1
                    continue
            context = _lv_publication_context(ingest, bundle_path)
            state = service.decide(
                identity,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(state["decision_result_path"]))
        if events:
            return {
                "status": "completed",
                "events": events,
                "waiting_count": waiting,
                "waiting_items": waiting_items,
                "suppressed_companion_count": suppressed,
                "claim_receipt_summary": claim_receipt_summary,
            }
        if waiting:
            return {
                "status": "waiting",
                "waiting_count": waiting,
                "waiting_items": waiting_items,
                "suppressed_companion_count": suppressed,
                "claim_receipt_summary": claim_receipt_summary,
            }
        return {
            "status": "no_update",
            "suppressed_companion_count": suppressed,
        }

    def lv_narrow_resume(self, surface: str) -> dict[str, Any]:
        identity = _exact_progress_surface("lv_text_image", surface)
        if identity == "source":
            return self.lv()
        return self.lv(only_identity=identity, refresh_listing=False)

    def lv_filtered_image_reconcile(self, surface: str) -> dict[str, Any]:
        identity = _exact_progress_surface("lv_text_image", surface)
        if identity == "source":
            raise DailyError(
                "filtered image preview requires one exact item identity"
            )
        service = self._lv_service_for_sweep()
        item = service.status().get("items", {}).get(identity)
        if not isinstance(item, dict):
            raise DailyError("filtered image preview identity is unknown")
        listing = service._read_opencli_listing(
            session=self.args.lv_session,
            profile=self.args.opencli_profile,
            exact_path=str(item.get("path") or ""),
        )
        service.poll_opencli(
            session=self.args.lv_session,
            profile=self.args.opencli_profile,
            listing=listing,
        )
        service.reconcile_filtered_image_preview(
            identity,
            session=self.args.lv_session,
            profile=self.args.opencli_profile,
            listing=listing,
        )
        return self.lv(only_identity=identity, refresh_listing=False)

    def lv_reconcile(self, progress: WriterProgress) -> dict[str, Any]:
        raise DailyError(
            f"Lv has no authoritative {progress.details['readback_operation']}"
        )

    def lv_terminal_reconcile(
        self,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        if (
            progress.details["effect_kind"] != "source_terminal"
            or progress.details["readback_operation"]
            != "read_lv_text_image_terminal_receipts"
        ):
            raise DailyError("Lv terminal readback operation is unsupported")
        decision = _lv_text_image_terminal_decision(
            self,
            progress.item_identity,
        )
        terminal = decision["terminal"]
        report = terminal.get("gray_report") or {}
        publication_receipt_id = ""
        if report.get("status") == "published":
            publication_key = publication_id_for_source(
                adapter="lv_text_image",
                source_identity=progress.item_identity,
            )
            publication = self.publications.status(publication_key)
            receipt = publication.get("publish_receipt") or {}
            if (
                publication.get("completed") is not True
                or receipt.get("detailUrl") != report.get("detail_url")
            ):
                raise DailyError("Lv terminal publication receipt changed")
            publication_receipt_id = str(
                receipt.get("idempotencyKey")
                or receipt.get("receiptId")
                or ""
            )
        outcome = {
            "status": "no_update",
            "terminal_event": terminal,
            "authoritative_readback": {
                "decision_result_sha256": decision["result_sha256"],
                "publication_receipt_id": publication_receipt_id,
                "book_terminal": str(
                    (terminal.get("book_kol_us") or {}).get("status") or ""
                ),
                "knowledge_terminal": str(
                    (terminal.get("knowledge_effect") or {}).get("status")
                    or ""
                ),
                "external_business_effects_replayed": False,
            },
        }
        return _reconciliation_result(progress, outcome)

    def lv_structured_input(self, progress: WriterProgress) -> dict[str, Any]:
        return _consume_structured_input(
            progress,
            lambda: self.lv(
                only_identity=progress.item_identity,
                refresh_listing=False,
            ),
        )

    def videos(
        self,
        *,
        only_identity: str | None = None,
        refresh_listing: bool = True,
        observability_repair_revision: str | None = None,
    ) -> dict[str, Any]:
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        if refresh_listing:
            service.scan_opencli(
                lv_session=self.args.lv_session,
                private_session=self.args.private_session,
                profile=self.args.opencli_profile,
                lv_listing=self._lv_listing_for_sweep(),
            )
        pending = service.pending_items()
        pending = _one_exact_pending(
            pending,
            only_identity,
            label="video progress",
        )
        if not pending:
            return {"status": "no_update"}
        pending.sort(
            key=lambda row: (
                0 if row.get("source") == LV_SOURCE else 1,
                -int(
                    row.get("remote_activity_at")
                    or row.get("modified_at")
                    or 0
                ),
                str(row.get("path") or ""),
            )
        )
        events = []
        waiting = 0
        waiting_items = []
        for item in pending:
            state = _persisted_video_analysis_request(
                self.args.video_output_dir,
                item,
            )
            try:
                if state is None:
                    state = service.advance_item(
                        item,
                        lv_session=self.args.lv_session,
                        private_session=self.args.private_session,
                        enrichment_session=self.args.enrichment_session,
                        profile=self.args.opencli_profile,
                        observability_repair_revision=(
                            observability_repair_revision
                        ),
                    )
            except EnrichmentError as exc:
                if str(exc) == (
                    "Lv cloud transfer did not materialize after bounded "
                    "exact reconciliation"
                ):
                    raise _lv_transfer_user_action_blocker(
                        self.args.video_output_dir,
                        pending,
                        item,
                        blocker_key="lv-cloud-transfer-not-materialized",
                        action=(
                            "百度网盘已两次确认转存，但目标目录和全局精确搜索均无"
                            "对应文件。该外部效果暂未可证实，本次运行已停止自动重试并"
                            "保留精确账本；如果当前任务已有明确代理接管授权，应由代理执行"
                            "一次受限修复，不要求用户代做。"
                        ),
                    ) from exc
                if str(exc) == "Lv cloud transfer was rejected by provider":
                    raise _lv_transfer_user_action_blocker(
                        self.args.video_output_dir,
                        pending,
                        item,
                        blocker_key="lv-cloud-transfer-provider-rejected",
                        action=(
                            "百度网盘明确拒绝了吕晓彤视频转存。请检查网盘容量、会员"
                            "文件大小或转存上限；这是提供方明确拒绝，代理不会绕过拒绝"
                            "重试或要求用户代做。处理后由代理只读对账。"
                        ),
                    ) from exc
                failure, retryable = _isolated_item_failure(
                    exc,
                    default_stage="source_acquisition",
                )
                reconciliation_binding: dict[str, str] = {}
                if "uncertain" in str(exc).casefold():
                    failure = {
                        "category": "uncertain_state",
                        "code": "transfer_receipt_reconciliation_required",
                        "stage": "cloud_transfer_reconciliation",
                    }
                    retryable = False
                    reconciliation_binding = _lv_transfer_claim_binding(
                        self.args.video_output_dir,
                        item,
                    )
                failure_audit = service.record_item_failure(
                    item,
                    failure=failure,
                    retryable=retryable,
                )
                waiting += 1
                waiting_item = {
                    "identity": str(item.get("identity") or ""),
                    "version_key": str(item.get("version_key") or ""),
                    "name": str(item.get("name") or ""),
                    "stage": failure["stage"],
                    "failure": {**failure, "retryable": retryable},
                    **reconciliation_binding,
                }
                waiting_items.append(waiting_item)
                if _requires_bounded_source_repair(failure):
                    affected = [
                        candidate
                        for candidate in pending
                        if candidate.get("source") == item.get("source")
                        and candidate.get("media_type") == item.get("media_type")
                    ]
                    progress = _source_failure_repair_progress(
                        adapter="subscription_video",
                        item=item,
                        affected_items=affected,
                        failure=failure,
                        failure_audit=(
                            failure_audit
                            if isinstance(failure_audit, dict)
                            else None
                        ),
                        provider_contract_version="subscription_video_source_v1",
                        targeted_test_profile="kol_subscription_video_source_run",
                    )
                    return {
                        "status": "waiting",
                        "waiting_count": waiting,
                        "waiting_items": waiting_items,
                        "resume_policy": progress.next_action,
                        "repair_key": progress.failure_fingerprint,
                        "repair_required": True,
                        "user_action_required": False,
                        "writer_progress": progress.to_dict(),
                    }
                continue
            if state.get("event") != "subscription_video_analysis_input_required":
                waiting += 1
                waiting_items.append(
                    {
                        key: value
                        for key, value in {
                            "identity": str(item.get("identity") or ""),
                            "version_key": str(
                                item.get("version_key") or ""
                            ),
                            "name": str(item.get("name") or ""),
                            "author": str(item.get("author") or ""),
                            "status": str(state.get("status") or "waiting"),
                            "stage": str(
                                state.get("stage")
                                or "cloud_enrichment"
                            ),
                            "trigger_attempt": state.get("trigger_attempt"),
                            "next_poll_not_before": state.get(
                                "next_poll_not_before"
                            ),
                            "reconciliation_status": state.get(
                                "reconciliation_status"
                            ),
                            "failure_reason": state.get("failure_reason"),
                        }.items()
                        if value not in (None, "")
                    }
                )
                continue
            semantic_request = {
                    **state,
                    "adapter": "subscription_video",
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                }
            bundle_path = _persisted_validated_bundle(semantic_request)
            reused_bundle = bundle_path is not None
            if bundle_path is None:
                try:
                    bundle_path = _read_agent_path(
                        semantic_request,
                        "bundle_path",
                    )
                except SemanticInputUnavailable as exc:
                    if not exc.request:
                        raise
                    waiting += 1
                    waiting_items.append(_semantic_waiting_item(
                        exc.request,
                        identity=str(item.get("identity") or ""),
                        version_key=str(item.get("version_key") or ""),
                        name=str(item.get("name") or ""),
                        author=str(item.get("author") or ""),
                    ))
                    # A TTY can report EOF for only the current read. Treat it as
                    # closing the channel for the whole adapter sweep so historical
                    # backlog cannot trigger more acquisition work.
                    break
            bundle_path = _require_canonical_semantic_artifact(
                bundle_path,
                semantic_request,
            )
            if reused_bundle:
                _record_structured_input_consumption(
                    semantic_request,
                    field="bundle_path",
                    path=bundle_path,
                )
            context = _video_publication_context(item, state)
            decision = service.decide_item(
                item,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(decision["decision_result_path"]))
        if events:
            return {
                "status": "completed",
                "events": events,
                "waiting_count": waiting,
                "waiting_items": waiting_items,
            }
        return {
            "status": "waiting",
            "waiting_count": waiting,
            "waiting_items": waiting_items,
        }

    def videos_reconcile(self, progress: WriterProgress) -> dict[str, Any]:
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        exact = [
            row
            for row in service.pending_items()
            if str(row.get("identity") or "") == progress.item_identity
        ]
        if len(exact) > 1:
            raise DailyError("video readback found duplicate exact pending items")
        if (
            progress.details["effect_kind"] != "cloud_transfer"
            or progress.details["readback_operation"]
            != "read_lv_transfer_claim_receipt"
            or not str(progress.details["claim_identity"]).startswith(
                "lv_transfer:"
            )
        ):
            raise DailyError("video readback operation is unsupported")
        if not exact:
            raise DailyError("video readback lost its exact pending item")
        binding = _lv_transfer_claim_binding(
            self.args.video_output_dir,
            exact[0],
        )
        if binding.get("claim_identity") != progress.details["claim_identity"]:
            raise DailyError("video readback claim identity changed")
        version = str(exact[0].get("version_key") or "")
        claim_path = (
            self.args.video_output_dir
            / "claims"
            / f"lv_transfer_{version}.json"
        )
        try:
            claim_before = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyError("video readback claim is invalid") from exc
        legacy_observability_gap = (
            claim_before.get("status") == "blocked"
            and claim_before.get("blocker_key")
            == "lv-cloud-transfer-not-materialized"
            and claim_before.get("provider_outcome") == "unobserved"
            and "provider_request_observed" not in claim_before
            and "provider_response_observed" not in claim_before
        )
        service.transfer_lv_video(
            exact[0],
            lv_session=self.args.lv_session,
            private_session=self.args.private_session,
            profile=self.args.opencli_profile,
            readback_only=True,
        )
        receipt_path = (
            self.args.video_output_dir
            / "receipts"
            / f"lv_transfer_{version}.json"
        )
        resolved = receipt_path.is_file()
        readback = {
            "claim_identity": progress.details["claim_identity"],
            "receipt_sha256": (
                hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                if resolved
                else None
            ),
            "effect_observed": "completed" if resolved else "absent",
        }
        if resolved:
            outcome = {
                "status": "no_update",
                "authoritative_readback": readback,
            }
        elif legacy_observability_gap:
            outcome = {
                "status": "waiting",
                "waiting_count": 1,
                "waiting_items": [{
                    "identity": progress.item_identity,
                    "version_key": version,
                    "stage": "cloud_transfer_confirmation",
                    "failure": {
                        "category": "provider_contract_error",
                        "code": "lv_transfer_response_unobserved_legacy",
                        "stage": "cloud_transfer_confirmation",
                        "retryable": True,
                    },
                }],
                "failure": {
                    "category": "provider_contract_error",
                    "code": "lv_transfer_response_unobserved_legacy",
                    "stage": "cloud_transfer_confirmation",
                    "retryable": True,
                },
                "authoritative_readback": readback,
            }
        else:
            readback_evidence_sha256 = hashlib.sha256(
                _canonical(readback).encode("utf-8")
            ).hexdigest()
            claim_id = str(progress.details["claim_identity"]).rsplit(
                ":", 1
            )[-1]
            service.record_lv_transfer_absence_reconciliation(
                exact[0],
                claim_id=claim_id,
                readback_evidence_sha256=readback_evidence_sha256,
            )
            outcome = {
                "status": "waiting",
                "waiting_count": 1,
                "waiting_items": [{
                    "identity": progress.item_identity,
                    "version_key": version,
                    "stage": "source_run",
                    "failure": {
                        "category": "internal_state_error",
                        "code": (
                            "cloud_transfer_unobserved_reconciled_absent"
                        ),
                        "stage": "source_run",
                        "retryable": False,
                    },
                }],
                "authoritative_readback": readback,
            }
        return _reconciliation_result(
            progress,
            outcome,
        )

    def videos_blocked_reconciliation_progress(
        self,
        identity: str,
    ) -> WriterProgress:
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        exact = _one_exact_pending(
            service.pending_items(),
            identity,
            label="blocked video readback",
        )
        item = exact[0]
        binding = _lv_transfer_claim_binding(
            self.args.video_output_dir,
            item,
        )
        if set(binding) != {
            "effect_kind",
            "claim_identity",
            "readback_operation",
        }:
            raise DailyError("blocked video readback lost its claim binding")
        version = str(item.get("version_key") or "")
        claim_path = (
            self.args.video_output_dir
            / "claims"
            / f"lv_transfer_{version}.json"
        )
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DailyError("blocked video readback claim is invalid") from exc
        if not (
            claim.get("status") == "blocked"
            and claim.get("blocker_key")
            == "lv-cloud-transfer-not-materialized"
            and claim.get("provider_outcome") == "unobserved"
            and "provider_request_observed" not in claim
            and "provider_response_observed" not in claim
        ):
            raise DailyError(
                "blocked video is not a legacy observability repair target"
            )
        return WriterProgress.reconcile_required(
            item_identity=identity,
            stage="cloud_transfer_reconciliation",
            effect_kind=binding["effect_kind"],
            claim_identity=binding["claim_identity"],
            readback_operation=binding["readback_operation"],
            claim_receipt_summary={
                "claim_count": 1,
                "receipt_count": 0,
                "uncertain_effect_count": 1,
            },
        )

    def videos_terminal_reconcile(
        self,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        if (
            progress.details["effect_kind"] != "source_terminal"
            or progress.details["readback_operation"]
            != "read_subscription_video_terminal_receipts"
        ):
            raise DailyError("video terminal readback operation is unsupported")
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        manifest = service.status()
        candidates = []
        for collection_name in ("items", "episodes"):
            collection = manifest.get(collection_name)
            if isinstance(collection, dict):
                candidate = collection.get(progress.item_identity)
                if isinstance(candidate, dict):
                    candidates.append(candidate)
        if len(candidates) != 1:
            raise DailyError("video terminal readback target changed")
        item = candidates[0]
        result_path = Path(
            str(item.get("decision_result_path") or "")
        ).expanduser().resolve()
        result_sha256 = str(item.get("decision_result_sha256") or "")
        if (
            item.get("completed_version_key") != item.get("version_key")
            or not result_path.is_file()
            or not re.fullmatch(r"[0-9a-f]{64}", result_sha256)
            or hashlib.sha256(result_path.read_bytes()).hexdigest()
            != result_sha256
        ):
            raise DailyError("video terminal decision receipt is incomplete")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        try:
            terminal = dict(result["items"][0]["daily_terminal"])
        except (KeyError, IndexError, TypeError) as exc:
            raise DailyError("video terminal result lacks daily receipt") from exc
        content = dict(terminal.get("content_value") or {})
        if not str(content.get("reason") or "").strip():
            content["reason"] = str(
                content.get("no_alert_reason") or ""
            ).strip()
        terminal["content_value"] = content
        publication_key = (
            "xiaocao:subscription_video:" + progress.item_identity
        )
        publication = self.publications.status(publication_key)
        receipt = publication.get("publish_receipt") or {}
        if (
            publication.get("completed") is not True
            or receipt.get("detailUrl")
            != (terminal.get("gray_report") or {}).get("detail_url")
        ):
            raise DailyError("video terminal publication receipt changed")
        outcome = {
            "status": "no_update",
            "terminal_event": terminal,
            "authoritative_readback": {
                "decision_result_sha256": result_sha256,
                "publication_receipt_id": str(
                    receipt.get("idempotencyKey")
                    or receipt.get("receiptId")
                    or ""
                ),
                "book_terminal": str(
                    (terminal.get("book_kol_us") or {}).get("status") or ""
                ),
                "external_business_effects_replayed": False,
            },
        }
        return _reconciliation_result(progress, outcome)

    def videos_narrow_resume(self, surface: str) -> dict[str, Any]:
        identity = _exact_progress_surface("subscription_video", surface)
        if identity == "source":
            return self.videos()
        return self.videos(
            only_identity=identity,
            refresh_listing=False,
            observability_repair_revision=getattr(
                self.args,
                "repair_revision",
                None,
            ),
        )

    def videos_structured_input(
        self,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        return _consume_structured_input(
            progress,
            lambda: self.videos(
                only_identity=progress.item_identity,
                refresh_listing=False,
            ),
        )

    @staticmethod
    def _handoff(path: Path) -> dict[str, Any]:
        if path.stat().st_size > MAX_HANDOFF_BYTES:
            raise DailyError("Xiaocao handoff exceeds the lightweight boundary")
        value = json.loads(path.read_text(encoding="utf-8"))
        expected = str(value.get("handoff_sha256") or "")
        unsigned = dict(value)
        unsigned.pop("handoff_sha256", None)
        actual = hashlib.sha256(_canonical(unsigned).encode()).hexdigest()
        if (
            expected != actual
            or value.get("large_payload_local_bytes") != 0
            or "media_path" in value
            or "video_path" in value
        ):
            raise DailyError("Xiaocao lightweight handoff is invalid")
        return value

    def xiaocao(
        self,
        handoff_id: str | None = None,
        *,
        only_identity: str | None = None,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        service = XiaocaoLiveService(
            self.args.xiaocao_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        handoff_paths = sorted({
            *self.args.xiaocao_output_dir.rglob("handoffs/*.json"),
            *self.args.xiaocao_output_dir.rglob("imported_handoffs/*.json"),
        })
        handoffs: dict[str, dict[str, Any]] = {}
        for path in handoff_paths:
            handoff = self._handoff(path)
            handoff_key = str(handoff.get("handoff_id") or "") or (
                "legacy:"
                f"{handoff.get('capture_job_id')}:"
                f"{handoff.get('netdisk_job_id')}"
            )
            existing = handoffs.get(handoff_key)
            if existing is not None and existing != handoff:
                raise DailyError("conflicting Xiaocao handoff capsules")
            handoffs[handoff_key] = handoff
        ordered_handoffs = sorted(
            handoffs.values(),
            key=lambda row: str(row.get("published_at") or ""),
            reverse=True,
        )
        excluded = {str(value) for value in exclude_handoff_ids}
        if handoff_id is not None and only_identity is not None:
            raise DailyError("Xiaocao exact selectors are mutually exclusive")
        if only_identity is not None:
            ordered_handoffs = [
                row
                for row in ordered_handoffs
                if str(row.get("capture_job_id") or "") == only_identity
            ]
            if len(ordered_handoffs) != 1:
                raise DailyError(
                    "target Xiaocao capture is not one exact durable handoff"
                )
        elif handoff_id is not None:
            ordered_handoffs = [
                row
                for row in ordered_handoffs
                if row.get("handoff_id") == handoff_id
            ]
            if not ordered_handoffs:
                raise DailyError("target Xiaocao handoff is not locally durable")
        elif excluded:
            ordered_handoffs = [
                row
                for row in ordered_handoffs
                if str(row.get("handoff_id") or "") not in excluded
            ]
        events = []
        completed_handoff_ids: list[str] = []
        waiting = 0
        waiting_items: list[dict[str, Any]] = []
        for handoff_index, handoff in enumerate(ordered_handoffs):
            if handoff.get("schema_version") == 2:
                service.import_handoff_capsule(handoff)
            job_id = str(handoff["netdisk_job_id"])
            state = service.netdisk.status(job_id)
            if state.get("status") == "decided":
                result_path = Path(str(state.get("decision_result_path") or ""))
                if result_path.is_file():
                    value = json.loads(result_path.read_text(encoding="utf-8"))
                    if (value.get("items") or [{}])[0].get("daily_terminal"):
                        if (
                            hashlib.sha256(result_path.read_bytes()).hexdigest()
                            != state.get("decision_result_sha256")
                        ):
                            raise DailyError(
                                "Xiaocao decision result changed"
                            )
                        completed_handoff_ids.append(str(handoff["handoff_id"]))
                        continue
                else:
                    # A legacy or synthetic decided receipt without a bound
                    # result cannot be upgraded automatically.
                    continue
                # Only the newest handoff may upgrade an earlier bare Ticket 03
                # decision into the Ticket 07 publication terminal. Older
                # historical decisions remain reconciliation-only.
                if handoff_index != 0:
                    continue
                bundle_path = Path(
                    str(state.get("decision_bundle_path") or "")
                ).expanduser().resolve()
                if (
                    not bundle_path.is_file()
                    or hashlib.sha256(bundle_path.read_bytes()).hexdigest()
                    != state.get("decision_bundle_sha256")
                ):
                    raise DailyError(
                        "latest Xiaocao decision bundle receipt is missing"
                    )
                context = DailyPublicationContext(
                    adapter="xiaocao_live",
                    source_identity=str(handoff["capture_job_id"]),
                    publication_version=str(state["transcript_sha256"]),
                    kol_id="kol-xiaocao",
                    source="小草直播",
                    source_published_at=str(handoff["published_at"]),
                    media_types=("video",),
                    source_parts=({
                        "identity": str(handoff["capture_job_id"]),
                        "version": str(state["transcript_sha256"]),
                        "order": 1,
                        "size": 0,
                        "evidence_sha256": str(state["transcript_sha256"]),
                    },),
                )
                decided = service.netdisk.decide(
                    job_id,
                    bundle_path=bundle_path,
                    decision_output_dir=self.args.decision_output_dir,
                    sender=_sender,
                    pipeline=self._pipeline(context),
                    reconcile_daily_terminal=True,
                )
                events.append(self._terminal(decided["decision_result_path"]))
                completed_handoff_ids.append(str(handoff["handoff_id"]))
                continue
            if state.get("status") not in {"transcript_captured", "verified"}:
                try:
                    state = service.netdisk.advance_opencli(
                        job_id,
                        session=self.args.enrichment_session,
                        profile=self.args.opencli_profile,
                    )
                except EnrichmentError:
                    failed = service.netdisk.status(job_id)
                    proof = failed.get("ai_note_pretrigger_proof")
                    safe_pretrigger_retry = (
                        failed.get("status") == "ai_note_pretrigger_failed"
                        and isinstance(proof, dict)
                        and proof.get("click_dispatched") is False
                        and proof.get("target_bound") is True
                        and int(proof.get("template_no") or 0) == 1
                        and int(proof.get("button_matches") or 0) == 0
                        and int(
                            failed.get("ai_note_trigger_attempt") or 0
                        ) == 1
                    )
                    safe_claimed_capture_resume = (
                        failed.get("status") == "ai_note_claimed"
                        and int(
                            failed.get("ai_note_trigger_attempt") or 0
                        ) == 1
                        and not failed.get("ai_note_triggered_at")
                        and not failed.get("ai_note_submission_proof")
                    )
                    if not (
                        safe_pretrigger_retry
                        or safe_claimed_capture_resume
                    ):
                        raise
                    state = service.netdisk.advance_opencli(
                        job_id,
                        session=self.args.enrichment_session,
                        profile=self.args.opencli_profile,
                    )
            if state.get("status") == "transcript_captured":
                audit_path = _read_agent_path(
                    {
                        "event": "daily_xiaocao_audit_input_required",
                        "capture_job_id": handoff["capture_job_id"],
                        "transcript_path": state["transcript_path"],
                        "transcript_sha256": state["transcript_sha256"],
                        "audit_contract": _transcript_audit_contract(state),
                    },
                    "audit_path",
                )
                state = service.netdisk.verify_transcript(
                    job_id,
                    audit_path=audit_path,
                )
            if state.get("status") != "verified":
                waiting += 1
                state_status = str(state.get("status") or "provider_wait")
                waiting_item = {
                    "identity": str(handoff["capture_job_id"]),
                    "version_key": str(handoff.get("media_sha256") or job_id),
                    "name": str(
                        handoff.get("media_basename")
                        or state.get("video_basename")
                        or job_id
                    ),
                    "author": "小草",
                    "status": state_status,
                    "category": "provider_wait",
                    "code": (
                        "transcript_pending"
                        if state_status
                        in {"transcript_claimed", "transcript_requested"}
                        else state_status
                    ),
                    "stage": (
                        "cloud_transcript"
                        if state_status
                        in {"transcript_claimed", "transcript_requested"}
                        else "cloud_enrichment"
                    ),
                    "reconciliation": "exact_job_pending",
                }
                next_poll = state.get("next_poll_not_before")
                if isinstance(next_poll, str) and next_poll:
                    waiting_item["next_poll_not_before"] = next_poll
                waiting_items.append(waiting_item)
                continue
            semantic_request = _persist_semantic_request(
                {
                    "schema_version": 2,
                    "event": "daily_analysis_input_required",
                    "adapter": "xiaocao_live",
                    "source": "小草直播",
                    "author": "小草",
                    "title": str(
                        handoff.get("media_basename")
                        or handoff["capture_job_id"]
                    ),
                    "published_at": handoff["published_at"],
                    "captured_at": str(
                        handoff.get("captured_at") or handoff["published_at"]
                    ),
                    "media_type": "video",
                    "capture_job_id": handoff["capture_job_id"],
                    "source_identity": handoff["capture_job_id"],
                    "source_version_key": state["transcript_sha256"],
                    "handoff_id": str(
                        handoff.get("handoff_id") or handoff["capture_job_id"]
                    ),
                    "message_sha256": str(
                        handoff.get("handoff_sha256")
                        or handoff.get("media_sha256")
                    ),
                    "content_sha256": str(
                        handoff.get("handoff_sha256")
                        or handoff.get("media_sha256")
                    ),
                    "media_sha256": handoff.get("media_sha256"),
                    "media_identity": str(handoff.get("media_sha256") or ""),
                    "evidence_path": state["transcript_path"],
                    "evidence_sha256": state["transcript_sha256"],
                    "investment_claim_extraction": build_claim_extraction_request(
                        state["transcript_path"],
                        evidence_sha256=str(state["transcript_sha256"]),
                    ),
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                },
                output_dir=Path(self.args.xiaocao_output_dir),
                request_id=str(handoff["capture_job_id"]),
            )
            bundle_path = _read_agent_path(semantic_request, "bundle_path")
            bundle_path = _require_canonical_semantic_artifact(
                bundle_path,
                semantic_request,
            )
            validate_decision_bundle(
                bundle_path,
                transcript_path=Path(state["transcript_path"]),
                transcript_sha256=str(state["transcript_sha256"]),
                handoff_id=str(
                    handoff.get("handoff_id") or handoff["capture_job_id"]
                ),
                source_identity=str(handoff["capture_job_id"]),
                source_version_key=str(state["transcript_sha256"]),
                media_identity=str(handoff.get("media_sha256") or "") or None,
            )
            context = DailyPublicationContext(
                adapter="xiaocao_live",
                source_identity=str(handoff["capture_job_id"]),
                publication_version=str(state["transcript_sha256"]),
                kol_id="kol-xiaocao",
                source="小草直播",
                source_published_at=str(handoff["published_at"]),
                media_types=("video",),
                source_parts=({
                    "identity": str(handoff["capture_job_id"]),
                    "version": str(state["transcript_sha256"]),
                    "order": 1,
                    "size": 0,
                    "evidence_sha256": str(state["transcript_sha256"]),
                },),
            )
            decided = service.netdisk.decide(
                job_id,
                bundle_path=bundle_path,
                decision_output_dir=self.args.decision_output_dir,
                sender=_sender,
                pipeline=self._pipeline(context),
            )
            events.append(self._terminal(decided["decision_result_path"]))
            completed_handoff_ids.append(str(handoff["handoff_id"]))
        if events:
            return {
                "status": "completed",
                "events": events,
                "completed_handoff_ids": completed_handoff_ids,
            }
        if completed_handoff_ids:
            return {
                "status": "completed",
                "events": [],
                "completed_handoff_ids": completed_handoff_ids,
            }
        if waiting:
            return {
                "status": "waiting",
                "waiting_count": waiting,
                "waiting_items": waiting_items,
            }
        return {"status": "no_update"}

    def xiaocao_narrow_resume(
        self,
        surface: str,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        identity = _exact_progress_surface("xiaocao_handoff", surface)
        if identity == "source":
            return self.xiaocao(exclude_handoff_ids=exclude_handoff_ids)
        return self.xiaocao(
            only_identity=identity,
            exclude_handoff_ids=exclude_handoff_ids,
        )

    def xiaocao_structured_input(
        self,
        progress: WriterProgress,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        return _consume_structured_input(
            progress,
            lambda: self.xiaocao(
                only_identity=progress.item_identity,
                exclude_handoff_ids=exclude_handoff_ids,
            ),
        )

    def xiaocao_reconcile(
        self,
        progress: WriterProgress,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        raise DailyError(
            "Xiaocao has no authoritative "
            f"{progress.details['readback_operation']}"
        )

    def xiaocao_wechat(
        self,
        *,
        only_identity: str | None = None,
    ) -> dict[str, Any]:
        history = WechatCliHistoryReader(
            self.args.xiaocao_wechat_contact,
            executable=self.args.wechat_cli,
            limit=self.args.wechat_history_limit,
        )
        capture = XiaocaoLiveCaptureDriver(
            self.args.xiaocao_wechat_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        subscription = XiaocaoWechatLiveSubscription(
            self.args.xiaocao_wechat_output_dir,
            history_reader=history,
            browser_exchange=_read_agent_json,
            handoff_exchange=self.publish_mailbox_handoff,
            capture_driver=capture,
            contact=self.args.xiaocao_wechat_contact,
            password=self.args.xiaocao_live_password,
        )
        run_kwargs: dict[str, Any] = {
            "opencli_session": getattr(
                self.args,
                "xiaocao_enrichment_session",
                self.args.enrichment_session,
            ),
            "opencli_profile": self.args.opencli_profile,
        }
        if only_identity is not None:
            run_kwargs["only_identity"] = only_identity
        return subscription.run_once(**run_kwargs)

    def xiaocao_wechat_narrow_resume(
        self,
        surface: str,
    ) -> dict[str, Any]:
        identity = _exact_progress_surface(
            "xiaocao_wechat_live",
            surface,
        )
        if identity == "source":
            return self.xiaocao_wechat()
        return self.xiaocao_wechat(only_identity=identity)

    def xiaocao_handoff_local(self) -> dict[str, Any]:
        capture = XiaocaoLiveCaptureDriver(
            self.args.xiaocao_wechat_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        subscription = XiaocaoWechatLiveSubscription(
            self.args.xiaocao_wechat_output_dir,
            history_reader=lambda: {},
            browser_exchange=_read_agent_json,
            handoff_exchange=self.publish_mailbox_handoff,
            capture_driver=capture,
            contact=self.args.xiaocao_wechat_contact,
            password=self.args.xiaocao_live_password,
        )
        return subscription.dispatch_published_handoff()

    def xiaocao_cloud_handoff(
        self,
        identity: str,
        capture_job_id: str,
    ) -> dict[str, Any]:
        capture = XiaocaoLiveCaptureDriver(
            self.args.xiaocao_wechat_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        subscription = XiaocaoWechatLiveSubscription(
            self.args.xiaocao_wechat_output_dir,
            history_reader=lambda: {},
            browser_exchange=_read_agent_json,
            handoff_exchange=self.publish_mailbox_handoff,
            capture_driver=capture,
            contact=self.args.xiaocao_wechat_contact,
            password=self.args.xiaocao_live_password,
        )
        return subscription.continue_cloud_handoff(
            identity,
            capture_job_id,
            opencli_session=getattr(
                self.args,
                "xiaocao_enrichment_session",
                self.args.enrichment_session,
            ),
            opencli_profile=self.args.opencli_profile,
        )

    def wechat_official_local(self) -> dict[str, Any]:
        publishers = tuple(self.args.wechat_official_publishers)
        reader = WechatCliOfficialAccountReader(
            publishers,
            executable=self.args.wechat_cli,
            within=self.args.wechat_official_within,
        )
        subscription = OfficialAccountSubscription(
            self.args.wechat_official_output_dir,
            reader=reader,
            handoff_exchange=self.publish_mailbox_handoff,
            publishers=publishers,
        )
        return subscription.run_once()

    def wechat_official(
        self,
        handoff_id: str | None = None,
        *,
        only_identity: str | None = None,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        inbox = OfficialAccountInbox(self.args.wechat_official_output_dir)
        acquirer = OfficialAccountOpenCliAcquirer(
            self.args.wechat_official_output_dir / "opencli",
            opencli_profile=getattr(self.args, "opencli_profile", None),
        )
        if handoff_id is not None and only_identity is not None:
            raise DailyError("official exact selectors are mutually exclusive")
        if handoff_id is not None:
            target = inbox.get_item(handoff_id)
            if target is None:
                raise DailyError("official mailbox handoff import is missing")
            if target.get("status") == "decided":
                inbox.verify_completed(handoff_id)
                return {
                    "status": "completed",
                    "events": [],
                    "completed_handoff_ids": [handoff_id],
                    "already_completed": True,
                }
            pending_items = [target]
        else:
            excluded = {str(value) for value in exclude_handoff_ids}
            pending_items = [
                item
                for item in inbox.pending_items()
                if str(item.get("handoff_id") or "") not in excluded
            ]
            if only_identity is not None:
                pending_items = [
                    item
                    for item in pending_items
                    if str(item.get("source_identity") or "") == only_identity
                ]
                if len(pending_items) != 1:
                    raise DailyError(
                        "official narrow target is not one exact pending item"
                    )
        pending = sorted(
            pending_items,
            key=lambda row: (
                str(row.get("published_at") or ""),
                str(row.get("source_identity") or ""),
            ),
        )
        if not pending:
            return {"status": "no_update"}
        events: list[dict[str, Any]] = []
        completed_handoff_ids: list[str] = []
        waiting_items: list[dict[str, Any]] = []
        for discovered in pending:
            item = inbox.acquire(discovered, acquirer=acquirer)
            image_request = inbox.prepare_image_request(item)
            if image_request is not None:
                try:
                    image_notes_path = _read_agent_path(
                        image_request,
                        "image_notes_path",
                    )
                except SemanticInputUnavailable as exc:
                    waiting_items.append({
                        "identity": str(item["source_identity"]),
                        "version_key": str(item["raw_markdown_sha256"]),
                        "name": str(item["title"]),
                        "author": str(item["author"]),
                        "status": "waiting_image_notes",
                        "stage": "waiting_image_notes",
                        "image_request_path": str(
                            exc.request.get("image_request_path") or ""
                        ),
                        "raw_markdown_path": str(item["raw_markdown_path"]),
                        "raw_markdown_sha256": str(
                            item["raw_markdown_sha256"]
                        ),
                        "image_count": int(item["image_count"]),
                        "external_business_effects_replayed": False,
                    })
                    break
                item = inbox.materialize_evidence(
                    item,
                    image_notes_path=image_notes_path,
                )
            elif item.get("status") != "evidence_ready":
                item = inbox.materialize_evidence(item)
            request = inbox.prepare_analysis_request(item)
            bundle_path = _persisted_validated_bundle(request)
            reused_bundle = bundle_path is not None
            if bundle_path is None:
                try:
                    bundle_path = _read_agent_path(request, "bundle_path")
                except SemanticInputUnavailable as exc:
                    waiting_items.append(
                        _semantic_waiting_item(
                            exc.request,
                            identity=str(item["source_identity"]),
                            version_key=str(item["publication_version"]),
                            name=str(item["title"]),
                            author=str(item["author"]),
                        )
                    )
                    break
            bundle_path = _require_canonical_semantic_artifact(
                bundle_path,
                request,
            )
            if reused_bundle:
                _record_structured_input_consumption(
                    request,
                    field="bundle_path",
                    path=bundle_path,
                )
            evidence_path = Path(str(item["evidence_path"])).resolve()
            context = DailyPublicationContext(
                adapter="wechat_official_account",
                source_identity=str(item["source_identity"]),
                publication_version=str(item["publication_version"]),
                kol_id=str(item["kol_id"]),
                source="微信公众号",
                source_published_at=str(item["published_at"]),
                media_types=("text",),
                source_parts=({
                    "identity": str(item["source_identity"]),
                    "version": str(item["publication_version"]),
                    "order": 1,
                    "size": evidence_path.stat().st_size,
                    "evidence_sha256": str(item["evidence_sha256"]),
                },),
            )
            decided = inbox.decide(
                item,
                bundle_path=bundle_path,
                pipeline=self._pipeline(context),
                sender=_sender,
            )
            events.append(self._terminal(decided["decision_result_path"]))
            completed_handoff_ids.append(str(item["handoff_id"]))
        if events:
            return {
                "status": "completed",
                "events": events,
                "completed_handoff_ids": completed_handoff_ids,
                "waiting_count": len(waiting_items),
                "waiting_items": waiting_items,
            }
        return {
            "status": "waiting",
            "waiting_count": len(waiting_items),
            "waiting_items": waiting_items,
        }

    def wechat_official_narrow_resume(
        self,
        surface: str,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        identity = _exact_progress_surface(
            "wechat_official_accounts",
            surface,
        )
        if identity == "source":
            return self.wechat_official(
                exclude_handoff_ids=exclude_handoff_ids
            )
        return self.wechat_official(
            only_identity=identity,
            exclude_handoff_ids=exclude_handoff_ids,
        )

    def wechat_official_structured_input(
        self,
        progress: WriterProgress,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        return _consume_structured_input(
            progress,
            lambda: self.wechat_official(
                only_identity=progress.item_identity,
                exclude_handoff_ids=exclude_handoff_ids,
            ),
        )

    def wechat_official_reconcile(
        self,
        progress: WriterProgress,
        *,
        exclude_handoff_ids: Collection[str] = (),
    ) -> dict[str, Any]:
        raise DailyError(
            "official adapter has no authoritative "
            f"{progress.details['readback_operation']}"
        )

    def viewpoints(self) -> dict[str, Any]:
        trigger_dir = self.args.output_dir / "viewpoint_triggers"
        receipt_dir = self.args.output_dir / "viewpoint_receipts"
        if not trigger_dir.is_dir():
            return {"status": "no_update"}
        terminals = []
        for path in sorted(trigger_dir.glob("*.json")):
            if path.stat().st_size > MAX_HANDOFF_BYTES:
                raise DailyError("viewpoint trigger exceeds the small-payload boundary")
            trigger_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            receipt_path = receipt_dir / f"{trigger_sha}.json"
            if receipt_path.is_file():
                try:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    terminal = receipt["terminal"]
                except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise DailyError(
                        "viewpoint maintenance receipt is invalid"
                    ) from exc
                terminals.append(terminal)
                continue
            request = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(request, dict):
                raise DailyError("viewpoint trigger must be a JSON object")
            current = read_published_publication(
                self._lianghui_client(),
                str(request.get("report_id") or ""),
            )
            if request.get("operation") == "initial_projection":
                candidate = build_initial_projection_candidate(current, request)
            else:
                candidate = build_triggered_evaluation_candidate(current, request)
            self.publications.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
            state = self.publications.run(
                candidate["publication_key"],
                self._lianghui_client(),
            )
            if request.get("operation") == "initial_projection":
                terminal = initial_projection_terminal(candidate, state)
            else:
                terminal = triggered_evaluation_terminal(candidate, state)
            terminals.append(terminal)
            receipt_dir.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "trigger_sha256": trigger_sha,
                        "terminal": terminal,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return (
            {"status": "completed", "events": terminals}
            if terminals
            else {"status": "no_update"}
        )

    def viewpoints_reconcile(
        self,
        progress: WriterProgress,
    ) -> dict[str, Any]:
        raise DailyError(
            "viewpoint adapter has no authoritative "
            f"{progress.details['readback_operation']}"
        )


def _source_repair_context(progress: WriterProgress) -> dict[str, Any]:
    failure = progress.failure
    adapter = str(failure.get("adapter") or "")
    subject_id = hashlib.sha256(
        (
            "kol-source-repair\n"
            f"{adapter}\n"
            f"{progress.item_identity}"
        ).encode("utf-8")
    ).hexdigest()
    return {
        "adapter": adapter,
        "message_id": subject_id,
        "content_sha256": str(progress.details["affected_set_digest"]),
        "failure_fingerprint": progress.failure_fingerprint,
        "failure_revision": str(failure["failure_revision"]),
        "category": str(failure["category"]),
        "code": str(failure["code"]),
        "stage": str(failure["stage"]),
        "claim_receipt_summary": dict(
            progress.details["claim_receipt_summary"]
        ),
        "targeted_test_profile": str(
            progress.details["targeted_test_profile"]
        ),
    }


def _source_repair_slot(service: DailyCoordinator) -> str:
    return service._beijing_now().strftime("%Y-%m-%dT%H:00+08:00")


def _source_effect_reconciliation_progress(
    service: DailyCoordinator,
    adapter: str,
    identity: str,
    *,
    runtime: DailyRuntime | None = None,
) -> WriterProgress:
    status = service.status()
    last_sweep = status.get("last_sweep")
    states = (
        last_sweep.get("source_states")
        if isinstance(last_sweep, dict)
        else None
    )
    matches = [
        row
        for row in (states if isinstance(states, list) else [])
        if isinstance(row, dict) and row.get("name") == adapter
    ]
    if len(matches) != 1 or not isinstance(
        matches[0].get("writer_progress"),
        dict,
    ):
        raise DailyError("source effect readback lost its active progress")
    progress = WriterProgress.from_dict(matches[0]["writer_progress"])
    if (
        progress.status == "reconcile_required"
        and progress.item_identity == identity
    ):
        return progress
    progress_value = progress.to_dict()
    if (
        adapter == "subscription_video"
        and progress.status == "user_action_required"
        and progress_value.get("blocker_identity")
        == "lv-cloud-transfer-not-materialized"
        and runtime is not None
    ):
        return runtime.videos_blocked_reconciliation_progress(identity)
    raise DailyError("source effect readback target is not active")


def _source_repair_validation_progress(
    service: DailyCoordinator,
    adapter: str,
    failure_fingerprint: str,
) -> WriterProgress:
    progress = service.convergence.active_progress(adapter)
    if progress is None:
        pending = service.convergence.pending_resume(adapter)
        if pending is not None:
            progress = pending[0]
    if progress is None:
        status = service.status()
        last_sweep = status.get("last_sweep")
        states = (
            last_sweep.get("source_states")
            if isinstance(last_sweep, dict)
            else None
        )
        matches = [
            row
            for row in (states if isinstance(states, list) else [])
            if isinstance(row, dict) and row.get("name") == adapter
        ]
        if (
            len(matches) == 1
            and isinstance(matches[0].get("writer_progress"), dict)
            and isinstance(last_sweep, dict)
        ):
            candidate = WriterProgress.from_dict(
                matches[0]["writer_progress"]
            )
            if (
                candidate.status == "repair_required"
                and candidate.failure_fingerprint == failure_fingerprint
            ):
                service.convergence.record(
                    candidate,
                    slot=str(last_sweep.get("slot") or ""),
                )
                progress = candidate
    if (
        progress is None
        or progress.failure_fingerprint != failure_fingerprint
    ):
        raise DailyError("source repair target is not the active fingerprint")
    return progress


def _resume_source_repair_outcome(
    runtime: DailyRuntime,
    adapter: str,
    surface: str,
    *,
    failure_code: str | None = None,
) -> dict[str, Any]:
    narrow_runner = (
        runtime.lv_filtered_image_reconcile
        if (
            adapter == "lv_text_image"
            and failure_code == "provider_download_filtered"
        )
        else _source_cli_narrow_runner(runtime, adapter)
    )
    outcome = _classified_narrow_source(adapter, narrow_runner)(surface)
    if adapter != "xiaocao_wechat_live":
        return outcome
    followed = _follow_cloud_handoff(runtime, outcome)
    if followed is None:
        return outcome
    return _classified_narrow_source(
        adapter,
        lambda _surface: followed,
    )(surface)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "run",
            "viewpoints",
            "capture-local",
            "capture-xiaocao-handoff",
            "capture-wechat-official",
            "import-wechat-official",
            "process-xiaocao-handoff",
            "process-wechat-official",
            "resume-mailbox",
            "validate-repair",
            "validate-source-repair",
            "resume-source-repair",
            "resume-source-wait",
            "resume-source-user-action",
            "resume-source-input",
            "reconcile-source-effect",
            "reconcile-source-terminal",
            "status",
            "audit",
            "convergence-report",
            "stability-acceptance",
            "record-peer-gate",
            "rollout-readback",
        ),
    )
    parser.add_argument("--config", type=Path, default=Path("xiaocao.yaml"))
    parser.add_argument("--lianghui-config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--lv-output-dir", type=Path, default=DEFAULT_LV_OUTPUT)
    parser.add_argument("--video-output-dir", type=Path, default=DEFAULT_VIDEO_OUTPUT)
    parser.add_argument(
        "--xiaocao-output-dir", type=Path, default=DEFAULT_XIAOCAO_OUTPUT
    )
    parser.add_argument(
        "--xiaocao-wechat-output-dir",
        type=Path,
        default=DEFAULT_XIAOCAO_WECHAT_OUTPUT,
    )
    parser.add_argument(
        "--wechat-official-output-dir",
        type=Path,
        default=DEFAULT_WECHAT_OFFICIAL_OUTPUT,
    )
    parser.add_argument(
        "--mailbox-output-dir",
        type=Path,
        default=DEFAULT_MAILBOX_OUTPUT,
    )
    parser.add_argument("--mailbox-message-id")
    parser.add_argument("--source-adapter")
    parser.add_argument("--source-identity")
    parser.add_argument("--failure-fingerprint")
    parser.add_argument("--repair-revision")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument(
        "--wechat-official-publisher",
        dest="wechat_official_publishers",
        action="append",
        default=list(DEFAULT_WECHAT_OFFICIAL_PUBLISHERS),
    )
    parser.add_argument(
        "--wechat-official-within",
        default=DEFAULT_WECHAT_OFFICIAL_WITHIN,
    )
    parser.add_argument("--wechat-cli", type=Path, default=DEFAULT_WECHAT_CLI)
    parser.add_argument(
        "--xiaocao-wechat-contact",
        default=DEFAULT_XIAOCAO_WECHAT_CONTACT,
    )
    parser.add_argument("--wechat-history-limit", type=int, default=80)
    parser.add_argument("--xiaocao-live-password", default="666")
    parser.add_argument("--opencli-profile")
    parser.add_argument("--lv-session", default="xiaocao-lv-subscription")
    parser.add_argument("--private-session", default="xiaocao-lv-subscription")
    parser.add_argument("--enrichment-session", default="xiaocao-lv-subscription")
    parser.add_argument(
        "--xiaocao-enrichment-session",
        default="site:baidu-netdisk",
    )
    args = parser.parse_args()
    if args.command == "import-wechat-official":
        try:
            line = sys.stdin.readline()
            capsule = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DailyError(
                "official-account import requires one JSON capsule line on stdin"
            ) from exc
        _print(
            OfficialAccountInbox(
                args.wechat_official_output_dir
            ).import_capsule(capsule)
        )
        return 0
    if args.command == "process-wechat-official":
        runtime = DailyRuntime(args)
        result = _standalone_writer_result(
            "wechat_official_accounts",
            runtime.wechat_official,
        )
        if result.get("status") != "no_update":
            _print(result)
        return 0
    if args.command == "process-xiaocao-handoff":
        runtime = DailyRuntime(args)
        result = _standalone_writer_result(
            "xiaocao_handoff",
            runtime.xiaocao,
        )
        if result.get("status") != "no_update":
            _print(result)
        return 0
    if args.command == "resume-mailbox":
        if not args.mailbox_message_id:
            raise DailyError("resume-mailbox requires message id")
        result = DailyRuntime(args).resume_mailbox(
            args.mailbox_message_id,
            repair_revision=args.repair_revision,
        )
        _print({"mailbox_repair_resume": result})
        return 0
    if args.command == "resume-source-wait":
        if not args.source_adapter or not args.source_identity:
            raise DailyError(
                "resume-source-wait requires source adapter and identity"
            )
        runtime = DailyRuntime(args)
        result = DailyCoordinator(args.output_dir).resume_wait(
            {
                "name": args.source_adapter,
                "narrow_resume": lambda surface: _resume_source_repair_outcome(
                    runtime,
                    args.source_adapter,
                    surface,
                ),
            },
            item_identity=args.source_identity,
        )
        _print({"source_wait_resume": result})
        return 0
    if args.command == "resume-source-user-action":
        if not args.source_adapter or not args.source_identity:
            raise DailyError(
                "resume-source-user-action requires source adapter and identity"
            )
        if args.source_adapter != "subscription_video":
            raise DailyError(
                "resume-source-user-action adapter has no exact CLI binding"
            )
        runtime = DailyRuntime(args)
        result = DailyCoordinator(args.output_dir).resume_user_action(
            {
                "name": args.source_adapter,
                "narrow_resume": lambda surface: _resume_source_repair_outcome(
                    runtime,
                    args.source_adapter,
                    surface,
                ),
            },
            item_identity=args.source_identity,
        )
        _print({"source_user_action_resume": result})
        return 0
    if args.command == "resume-source-input":
        if not args.source_adapter or not args.source_identity:
            raise DailyError(
                "resume-source-input requires source adapter and identity"
            )
        runtime = DailyRuntime(args)
        progress, structured_input = _source_cli_structured_input_binding(
            runtime,
            args.source_adapter,
            args.source_identity,
        )
        result = DailyCoordinator(args.output_dir).resume_structured_input(
            {
                "name": args.source_adapter,
                "structured_input": structured_input,
            },
            progress=progress,
        )
        _print({"source_input_resume": result})
        return 0
    if args.command == "reconcile-source-effect":
        if not args.source_adapter or not args.source_identity:
            raise DailyError(
                "reconcile-source-effect requires source adapter and identity"
            )
        if args.source_adapter != "subscription_video":
            raise DailyError(
                "reconcile-source-effect adapter has no exact CLI binding"
            )
        service = DailyCoordinator(args.output_dir)
        runtime = DailyRuntime(args)
        progress = _source_effect_reconciliation_progress(
            service,
            args.source_adapter,
            args.source_identity,
            runtime=runtime,
        )
        result = service.resume_reconciliation(
            {
                "name": args.source_adapter,
                "reconcile": runtime.videos_reconcile,
            },
            progress=progress,
        )
        _print({"source_effect_reconciliation": result})
        return 0
    if args.command == "reconcile-source-terminal":
        if not args.source_adapter or not args.source_identity:
            raise DailyError(
                "reconcile-source-terminal requires source adapter and identity"
            )
        runtime = DailyRuntime(args)
        progress, reconcile = _source_cli_terminal_binding(
            runtime,
            args.source_adapter,
            args.source_identity,
        )
        result = DailyCoordinator(args.output_dir).resume_reconciliation(
            {
                "name": args.source_adapter,
                "reconcile": reconcile,
            },
            progress=progress,
        )
        _print({"source_terminal_reconciliation": result})
        return 0
    if args.command == "validate-repair":
        if not args.mailbox_message_id:
            raise DailyError("validate-repair requires message id")
        result = DailyRuntime(args).validate_repair(
            args.mailbox_message_id,
            repair_revision=args.repair_revision,
        )
        _print({"repair_validation": result})
        return 0
    if args.command == "validate-source-repair":
        if not args.source_adapter or not args.failure_fingerprint:
            raise DailyError(
                "validate-source-repair requires source adapter and fingerprint"
        )
        service = DailyCoordinator(args.output_dir)
        progress = _source_repair_validation_progress(
            service,
            args.source_adapter,
            args.failure_fingerprint,
        )
        ledger = RepairValidationLedger(
            args.mailbox_output_dir / "repair_validation.jsonl"
        )
        validator = RepairValidationService(
            Path(__file__).resolve().parents[1],
            ledger=ledger,
        )
        receipt = validator.validate(
            _source_repair_context(progress),
            repair_revision=args.repair_revision,
        )
        closure = service.convergence.close_repair(
            progress.failure_fingerprint,
            repair_receipt=receipt,
            validation_ledger=ledger,
            slot=_source_repair_slot(service),
        )
        _print({
            "source_repair_validation": receipt.to_dict(),
            "repair_closure": closure,
        })
        return 0
    if args.command == "resume-source-repair":
        if not args.source_adapter or not args.failure_fingerprint:
            raise DailyError(
                "resume-source-repair requires source adapter and fingerprint"
            )
        service = DailyCoordinator(args.output_dir)
        pending = service.convergence.pending_resume(args.source_adapter)
        if pending is None:
            raise DailyError("source repair has no validated narrow resume")
        progress, closure = pending
        if progress.failure_fingerprint != args.failure_fingerprint:
            raise DailyError("source repair fingerprint changed before resume")
        repair_revision = str(
            (closure.get("repair_receipt") or {}).get("repair_revision") or ""
        )
        if not re.fullmatch(r"[0-9a-f]{40}", repair_revision):
            raise DailyError("source repair closure lost its repair revision")
        if args.repair_revision and args.repair_revision != repair_revision:
            raise DailyError("source repair revision changed before resume")
        args.repair_revision = repair_revision
        runtime = DailyRuntime(args)
        surface = str(progress.details["narrow_resume_surface"])
        outcome = _resume_source_repair_outcome(
            runtime,
            args.source_adapter,
            surface,
            failure_code=str(progress.details["failure"]["code"]),
        )
        following = WriterProgress.from_dict(outcome["writer_progress"])
        resume_receipt = service.convergence.record_resume(
            progress.failure_fingerprint,
            following=following,
            slot=_source_repair_slot(service),
        )
        _print({
            "source_repair_resume": outcome,
            "repair_resume_receipt": resume_receipt,
        })
        return 0
    service = DailyCoordinator(args.output_dir)
    if args.command == "status":
        value = service.status()
        value["latest_lv_video_goal"] = _latest_lv_video_goal(
            args.video_output_dir,
            service.events(),
        )
        value["wechat_official_accounts"] = OfficialAccountInbox(
            args.wechat_official_output_dir
        ).status()
        _print(value)
        return 0
    if args.command == "audit":
        value = service.audit()
        value["latest_lv_video_goal"] = _latest_lv_video_goal(
            args.video_output_dir,
            service.events(),
        )
        value["wechat_official_accounts"] = OfficialAccountInbox(
            args.wechat_official_output_dir
        ).status()
        _print(value)
        return 0
    if args.command == "convergence-report":
        _print(service.convergence_report(
            period_start=args.period_start,
            period_end=args.period_end,
        ))
        return 0
    if args.command == "stability-acceptance":
        _print(service.stability_acceptance_report(as_of=args.period_end))
        return 0
    if args.command == "record-peer-gate":
        try:
            payload = json.loads(sys.stdin.readline())
        except json.JSONDecodeError as exc:
            raise DailyError(
                "record-peer-gate requires one JSON object on stdin"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {
            "gate_result",
            "attempt_count",
            "elapsed_ms",
        }:
            raise DailyError(
                "record-peer-gate requires gate_result, attempt_count, and elapsed_ms"
            )
        receipt = service.convergence.record_peer_gate(payload)
        _print({"peer_gate_observed": receipt})
        return 0
    if args.command == "rollout-readback":
        try:
            payload = json.loads(sys.stdin.readline())
        except json.JSONDecodeError as exc:
            raise DailyError(
                "rollout-readback requires one JSON object on stdin"
            ) from exc
        rollout_fields = {
            "readback",
            "automation_evidence",
            "baseline",
            "slot",
        }
        if not isinstance(payload, dict) or not (
            set(payload) <= rollout_fields | {"restart_after_failed_acceptance"}
            and rollout_fields <= set(payload)
        ):
            raise DailyError(
                "rollout-readback requires readback, Automation evidence, baseline, and slot"
            )
        readback = RolloutReadback.from_dict(payload["readback"])
        _verify_rollout_evidence(
            readback,
            payload["automation_evidence"],
            args=args,
        )
        _require_rollout_peer_gate(
            service,
            automation_observed_at=str(
                payload["automation_evidence"]["observed_at"]
            ),
        )
        receipt = service.convergence.record_rollout_readback(
            readback,
            slot=str(payload["slot"]),
            baseline=payload["baseline"],
            restart_after_failed_acceptance=payload.get(
                "restart_after_failed_acceptance",
                False,
            ),
        )
        _print({"rollout_readback": receipt})
        return 0
    if args.command == "capture-local":
        runtime = DailyRuntime.__new__(DailyRuntime)
        runtime.args = args
        mailbox_reconciliation = runtime.reconcile_local_mailbox()
        if mailbox_reconciliation:
            _print({"mailbox_reconciliation": mailbox_reconciliation})
        result = service.run(
            [
                SourceAdapter(**source).coordinator_entry()
                for source in [{
                "name": "xiaocao_wechat_live",
                "priority": 10,
                "run": _classified_source(
                    "xiaocao_wechat_live", runtime.xiaocao_wechat
                ),
                "narrow_resume": _classified_narrow_source(
                    "xiaocao_wechat_live",
                    lambda surface: _adapter_scope_resume(
                        "xiaocao_wechat_live",
                        surface,
                        runtime.xiaocao_wechat,
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "xiaocao_wechat_live",
                    _missing_progress_operation(
                        "xiaocao_wechat_live", "authoritative reconciliation"
                    ),
                ),
            }, {
                "name": "wechat_official_accounts",
                "priority": 20,
                "run": _classified_source(
                    "wechat_official_accounts", runtime.wechat_official_local
                ),
                "narrow_resume": _classified_narrow_source(
                    "wechat_official_accounts",
                    lambda surface: _adapter_scope_resume(
                        "wechat_official_accounts",
                        surface,
                        runtime.wechat_official_local,
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "wechat_official_accounts",
                    _missing_progress_operation(
                        "wechat_official_accounts",
                        "authoritative reconciliation",
                    ),
                ),
            }]
            ],
            blocker_sender=_sender,
        )
        if not result.get("silent"):
            _print(result)
        follow_result = _follow_cloud_handoff(runtime, result)
        if follow_result is not None:
            _print(follow_result)
        return 0
    if args.command == "capture-wechat-official":
        runtime = DailyRuntime.__new__(DailyRuntime)
        runtime.args = args
        result = runtime.wechat_official_local()
        if result.get("status") != "no_update":
            _print(result)
        return 0
    if args.command == "capture-xiaocao-handoff":
        runtime = DailyRuntime.__new__(DailyRuntime)
        runtime.args = args
        result = runtime.xiaocao_handoff_local()
        if result.get("status") != "no_update" or result.get(
            "handoff_dispatched"
        ):
            _print(result)
        return 0
    if args.command == "viewpoints":
        runtime = DailyRuntime(args)
        result = _standalone_writer_result(
            "viewpoint_maintenance",
            runtime.viewpoints,
        )
        if result.get("status") != "no_update":
            _print(result)
        return 0
    runtime = DailyRuntime(args)
    mailbox_result = runtime.mailbox()
    attempted_handoff_ids = frozenset(
        str(value)
        for value in mailbox_result.get("attempted_message_ids", [])
    )
    if mailbox_result.get("attempted_message_ids"):
        _print({"mailbox_drain": mailbox_result})
    result = service.run(
        [
            SourceAdapter(**source).coordinator_entry()
            for source in [
            {
                "name": "lv_text_image",
                "priority": 10,
                "run": _classified_source("lv_text_image", runtime.lv),
                "narrow_resume": _classified_narrow_source(
                    "lv_text_image",
                    getattr(
                        runtime,
                        "lv_narrow_resume",
                        _missing_progress_operation(
                            "lv_text_image", "narrow resume"
                        ),
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "lv_text_image",
                    getattr(
                        runtime,
                        "lv_reconcile",
                        _missing_progress_operation(
                            "lv_text_image", "reconciliation"
                        ),
                    ),
                ),
                "structured_input": _classified_progress_source(
                    "lv_text_image",
                    getattr(
                        runtime,
                        "lv_structured_input",
                        _missing_progress_operation(
                            "lv_text_image", "structured input"
                        ),
                    ),
                ),
            },
            {
                "name": "subscription_video",
                "priority": 20,
                "run": _classified_source(
                    "subscription_video", runtime.videos
                ),
                "narrow_resume": _classified_narrow_source(
                    "subscription_video",
                    getattr(
                        runtime,
                        "videos_narrow_resume",
                        _missing_progress_operation(
                            "subscription_video", "narrow resume"
                        ),
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "subscription_video",
                    getattr(
                        runtime,
                        "videos_reconcile",
                        _missing_progress_operation(
                            "subscription_video", "reconciliation"
                        ),
                    ),
                ),
                "structured_input": _classified_progress_source(
                    "subscription_video",
                    getattr(
                        runtime,
                        "videos_structured_input",
                        _missing_progress_operation(
                            "subscription_video", "structured input"
                        ),
                    ),
                ),
            },
            {
                "name": "wechat_official_accounts",
                "priority": 25,
                "run": _classified_source(
                    "wechat_official_accounts",
                    lambda: runtime.wechat_official(
                        exclude_handoff_ids=attempted_handoff_ids
                    ),
                ),
                "narrow_resume": _classified_narrow_source(
                    "wechat_official_accounts",
                    lambda surface: runtime.wechat_official_narrow_resume(
                        surface,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "wechat_official_accounts",
                    lambda progress: runtime.wechat_official_reconcile(
                        progress,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
                "structured_input": _classified_progress_source(
                    "wechat_official_accounts",
                    lambda progress: runtime.wechat_official_structured_input(
                        progress,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
            },
            {
                "name": "xiaocao_handoff",
                "priority": 30,
                "run": _classified_source(
                    "xiaocao_handoff",
                    lambda: runtime.xiaocao(
                        exclude_handoff_ids=attempted_handoff_ids
                    ),
                ),
                "narrow_resume": _classified_narrow_source(
                    "xiaocao_handoff",
                    lambda surface: runtime.xiaocao_narrow_resume(
                        surface,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "xiaocao_handoff",
                    lambda progress: runtime.xiaocao_reconcile(
                        progress,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
                "structured_input": _classified_progress_source(
                    "xiaocao_handoff",
                    lambda progress: runtime.xiaocao_structured_input(
                        progress,
                        exclude_handoff_ids=attempted_handoff_ids,
                    ),
                ),
            },
            {
                "name": "viewpoint_maintenance",
                "priority": 40,
                "run": _classified_source(
                    "viewpoint_maintenance", runtime.viewpoints
                ),
                "narrow_resume": _classified_narrow_source(
                    "viewpoint_maintenance",
                    lambda surface: _adapter_scope_resume(
                        "viewpoint_maintenance",
                        surface,
                        runtime.viewpoints,
                    ),
                ),
                "reconcile": _classified_progress_source(
                    "viewpoint_maintenance",
                    getattr(
                        runtime,
                        "viewpoints_reconcile",
                        _missing_progress_operation(
                            "viewpoint_maintenance", "reconciliation"
                        ),
                    ),
                ),
            },
        ]
        ],
        blocker_sender=_sender,
    )
    result["latest_lv_video_goal"] = _latest_lv_video_goal(
        args.video_output_dir,
        service.events(),
    )
    if not result.get("silent"):
        _print(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DailyError, EnrichmentError, ProgressContractError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc
