#!/usr/bin/env python3
"""Run or inspect the short-lived Ticket 07 KOL daytime operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xiaocao.kol.daily import (
    build_triggered_evaluation_candidate,
    DailyCoordinator,
    DailyError,
    DailyPublicationContext,
    DailyPublicationPipeline,
    TransientSourceError,
    UserActionBlocker,
    triggered_evaluation_terminal,
)
from xiaocao.kol.decisions import DecisionPipeline
from xiaocao.kol.enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
)
from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.kol.lv_subscription import LvSubscriptionService
from xiaocao.kol.publication import PublicationLedger, read_published_publication
from xiaocao.kol.subscription_video import LV_SOURCE, SubscriptionVideoService
from xiaocao.kol.xiaocao_live import (
    XiaocaoLiveService,
    validate_decision_bundle,
)
from xiaocao.live.notify import notify


DEFAULT_OUTPUT = Path("output/live/kol_daily")
DEFAULT_DECISIONS = Path("output/live/kol_intelligence")
DEFAULT_LV_OUTPUT = Path("output/live/kol_lv_subscription")
DEFAULT_VIDEO_OUTPUT = Path("output/live/kol_subscription_videos")
DEFAULT_XIAOCAO_OUTPUT = Path("output/live/kol_xiaocao_live")
MAX_HANDOFF_BYTES = 1024 * 1024


class SemanticInputUnavailable(DailyError):
    """A persisted semantic request has no coordinator response yet."""

    def __init__(self, request: dict[str, Any], field: str):
        super().__init__(f"daily runner is waiting for {field} on stdin")
        self.request = request
        self.field = field


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
        return (
            failure,
            True,
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


def _read_agent_path(request: dict[str, Any], field: str) -> Path:
    print(json.dumps(request, ensure_ascii=False, sort_keys=True), flush=True)
    response = sys.stdin.readline()
    if not response:
        if field == "bundle_path" and request.get("analysis_request_path"):
            raise SemanticInputUnavailable(request, field)
        raise DailyError(f"daily runner requires {field} on stdin")
    raw = response.strip()
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DailyError("daily runner response is invalid JSON") from exc
        raw = str(value.get(field) or "").strip()
    if not raw:
        raise DailyError(f"daily runner response lacks {field}")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise DailyError(f"daily runner {field} is missing")
    return path


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


def _sender(title: str, body: str) -> dict[str, str]:
    result = notify(title, body, macos=False, audience="kol")
    if not isinstance(result, dict):
        raise DailyError("KOL notification relay returned an invalid result")
    return {str(key): str(value) for key, value in result.items()}


def _classified_source(name: str, runner):
    def run():
        try:
            return runner()
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
            if message in {
                "OpenCLI session is not authenticated",
                "OpenCLI login is required",
            }:
                raise UserActionBlocker(
                    f"{name}-opencli-login",
                    "请在已授权浏览器中重新登录百度网盘，并保持既有 OpenCLI 会话可访问。",
                ) from exc
            if message == "captcha_required":
                raise UserActionBlocker(
                    f"{name}-captcha",
                    "请在已授权百度网盘页面完成验证码，然后等待下一小时自动恢复。",
                ) from exc
            if message == (
                "Lv cloud transfer did not materialize after bounded "
                "exact reconciliation"
            ):
                raise UserActionBlocker(
                    "lv-cloud-transfer-not-materialized",
                    "百度网盘已两次确认转存，但目标目录和全局精确搜索均无"
                    "对应文件。请检查网盘容量或转存限制，并手动把最新吕晓彤"
                    "视频保存到 /课程/自己的课/吕晓彤；完成后保持 Chrome "
                    "登录，下一小时会只读对账并继续解析。",
                ) from exc
            if message == "Lv cloud transfer was rejected by provider":
                raise UserActionBlocker(
                    "lv-cloud-transfer-provider-rejected",
                    "百度网盘明确拒绝了吕晓彤视频转存。请检查网盘容量、"
                    "会员文件大小或转存上限，处理后手动把最新视频保存到 "
                    "/课程/自己的课/吕晓彤；保持 Chrome 登录后，下一小时"
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


class DailyRuntime:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = (
            LiangHuiMcpClient.from_config(args.lianghui_config)
            if args.lianghui_config is not None
            else LiangHuiMcpClient.from_config()
        )
        self.publications = PublicationLedger(args.output_dir / "publications")
        self._lv_service: LvSubscriptionService | None = None
        self._lv_listing: dict[str, Any] | None = None
        self._lv_listing_error: EnrichmentError | None = None

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
        delegate = DecisionPipeline(
            self.args.decision_output_dir,
            household_context_loader=self.client.load_context,
        )
        return DailyPublicationPipeline(
            delegate,
            ledger=self.publications,
            client=self.client,
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

    def lv(self) -> dict[str, Any]:
        service = self._lv_service_for_sweep()
        listing = self._lv_listing_for_sweep()
        service.poll_opencli(
            session=self.args.lv_session,
            profile=self.args.opencli_profile,
            listing=listing,
        )
        pending = service.pending_items()
        pending.sort(
            key=lambda row: (
                -int(row.get("modified_at") or 0),
                str(row.get("path") or ""),
                str(row.get("identity") or ""),
            )
        )
        complete_video_transcripts = self._complete_lv_video_transcripts()
        for row in pending:
            if row.get("media_type") != "pdf":
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
        if not pending:
            return {"status": "no_update"}
        events = []
        waiting = 0
        waiting_items = []
        suppressed = 0
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
                service.record_item_failure(
                    identity,
                    failure=failure,
                    retryable=retryable,
                )
                waiting += 1
                waiting_items.append({
                    "identity": identity,
                    "version_key": str(row.get("version_key") or ""),
                    "name": str(row.get("name") or ""),
                    "stage": failure["stage"],
                    "failure": {**failure, "retryable": retryable},
                })
                continue
            ingest = service.ingest_browser_download(identity)
            request = service.prepare_analysis_request(ingest)
            semantic_request = {
                    "event": "daily_analysis_input_required",
                    "adapter": "lv_text_image",
                    "identity": ingest["identity"],
                    "version_key": ingest["version_key"],
                    "analysis_request_path": request["request_path"],
                    "evidence_path": ingest["evidence_path"],
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                }
            try:
                bundle_path = _read_agent_path(
                    semantic_request,
                    "bundle_path",
                )
            except SemanticInputUnavailable as exc:
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
            if ingest["media_type"] == "pdf":
                relationship = service.record_pdf_relationship(
                    identity,
                    bundle_path=bundle_path,
                )
                if relationship["route"] == "companion_suppressed":
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
            }
        if waiting:
            return {
                "status": "waiting",
                "waiting_count": waiting,
                "waiting_items": waiting_items,
                "suppressed_companion_count": suppressed,
            }
        return {
            "status": "no_update",
            "suppressed_companion_count": suppressed,
        }

    def videos(self) -> dict[str, Any]:
        lv_listing = self._lv_listing_for_sweep()
        service = SubscriptionVideoService(
            self.args.video_output_dir,
            config_path=self.args.config,
        )
        service.scan_opencli(
            lv_session=self.args.lv_session,
            private_session=self.args.private_session,
            profile=self.args.opencli_profile,
            lv_listing=lv_listing,
        )
        pending = service.pending_items()
        if not pending:
            return {"status": "no_update"}
        pending.sort(
            key=lambda row: (
                0 if row.get("source") == LV_SOURCE else 1,
                -int(row.get("modified_at") or 0),
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
                    )
            except EnrichmentError as exc:
                if str(exc) in {
                    "Lv cloud transfer did not materialize after bounded exact reconciliation",
                    "Lv cloud transfer was rejected by provider",
                }:
                    raise
                failure, retryable = _isolated_item_failure(
                    exc,
                    default_stage="source_acquisition",
                )
                if "uncertain" in str(exc).casefold():
                    failure = {
                        "category": "uncertain_state",
                        "code": "transfer_receipt_reconciliation_required",
                        "stage": "cloud_transfer_reconciliation",
                    }
                    retryable = False
                service.record_item_failure(
                    item,
                    failure=failure,
                    retryable=retryable,
                )
                waiting += 1
                waiting_items.append({
                    "identity": str(item.get("identity") or ""),
                    "version_key": str(item.get("version_key") or ""),
                    "name": str(item.get("name") or ""),
                    "stage": failure["stage"],
                    "failure": {**failure, "retryable": retryable},
                })
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
            try:
                bundle_path = _read_agent_path(
                    semantic_request,
                    "bundle_path",
                )
            except SemanticInputUnavailable as exc:
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

    def xiaocao(self) -> dict[str, Any]:
        service = XiaocaoLiveService(
            self.args.xiaocao_output_dir,
            decision_output=self.args.decision_output_dir,
        )
        handoffs = sorted(
            (self.args.xiaocao_output_dir / "handoffs").glob("*.json")
        )
        events = []
        waiting = 0
        for path in handoffs:
            handoff = self._handoff(path)
            if handoff.get("schema_version") == 2:
                service.import_handoff_capsule(handoff)
            job_id = str(handoff["netdisk_job_id"])
            state = service.netdisk.status(job_id)
            if state.get("status") == "decided":
                result_path = Path(str(state.get("decision_result_path") or ""))
                if result_path.is_file():
                    value = json.loads(result_path.read_text(encoding="utf-8"))
                    if (value.get("items") or [{}])[0].get("daily_terminal"):
                        continue
                # Historical completed work is never replayed.
                continue
            if state.get("status") not in {"transcript_captured", "verified"}:
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
                    },
                    "audit_path",
                )
                state = service.netdisk.verify_transcript(
                    job_id,
                    audit_path=audit_path,
                )
            if state.get("status") != "verified":
                waiting += 1
                continue
            bundle_path = _read_agent_path(
                {
                    "event": "daily_analysis_input_required",
                    "adapter": "xiaocao_live",
                    "capture_job_id": handoff["capture_job_id"],
                    "transcript_path": state["transcript_path"],
                    "transcript_sha256": state["transcript_sha256"],
                    "required_content_value": (
                        "low_density|promoted(report_only|alert_eligible)"
                    ),
                },
                "bundle_path",
            )
            validate_decision_bundle(
                bundle_path,
                transcript_path=Path(state["transcript_path"]),
                transcript_sha256=str(state["transcript_sha256"]),
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
        if events:
            return {"status": "completed", "events": events}
        if waiting:
            return {"status": "waiting", "waiting_count": waiting}
        return {"status": "no_update"}

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
                self.client,
                str(request.get("report_id") or ""),
            )
            candidate = build_triggered_evaluation_candidate(current, request)
            self.publications.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
            state = self.publications.run(
                candidate["publication_key"],
                self.client,
            )
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "audit"))
    parser.add_argument("--config", type=Path, default=Path("xiaocao.yaml"))
    parser.add_argument("--lianghui-config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--decision-output-dir", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--lv-output-dir", type=Path, default=DEFAULT_LV_OUTPUT)
    parser.add_argument("--video-output-dir", type=Path, default=DEFAULT_VIDEO_OUTPUT)
    parser.add_argument(
        "--xiaocao-output-dir", type=Path, default=DEFAULT_XIAOCAO_OUTPUT
    )
    parser.add_argument("--opencli-profile")
    parser.add_argument("--lv-session", default="xiaocao-lv-subscription")
    parser.add_argument("--private-session", default="xiaocao-lv-subscription")
    parser.add_argument("--enrichment-session", default="xiaocao-lv-subscription")
    args = parser.parse_args()
    service = DailyCoordinator(args.output_dir)
    if args.command == "status":
        value = service.status()
        value["latest_lv_video_goal"] = _latest_lv_video_goal(
            args.video_output_dir,
            service.events(),
        )
        _print(value)
        return 0
    if args.command == "audit":
        value = service.audit()
        value["latest_lv_video_goal"] = _latest_lv_video_goal(
            args.video_output_dir,
            service.events(),
        )
        _print(value)
        return 0
    runtime = DailyRuntime(args)
    result = service.run(
        [
            {
                "name": "lv_text_image",
                "priority": 10,
                "run": _classified_source("lv_text_image", runtime.lv),
            },
            {
                "name": "subscription_video",
                "priority": 20,
                "run": _classified_source(
                    "subscription_video", runtime.videos
                ),
            },
            {
                "name": "xiaocao_handoff",
                "priority": 30,
                "run": _classified_source(
                    "xiaocao_handoff", runtime.xiaocao
                ),
            },
            {
                "name": "viewpoint_maintenance",
                "priority": 40,
                "run": _classified_source(
                    "viewpoint_maintenance", runtime.viewpoints
                ),
            },
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
    except (DailyError, EnrichmentError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc
