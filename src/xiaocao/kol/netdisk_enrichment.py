"""Resumable Baidu Netdisk consumer-page video enrichment evidence."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .enrichment_store import EnrichmentJobStore
from .enrichment_types import (
    EnrichmentError,
    validate_decision_completion,
    validate_decision_process_result,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPENCLI_SESSION = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_OPENCLI_CAPTURE_PROBE = """(() => {
  const active = document.querySelector('.vp-tabs__header-item--active');
  const scroller = document.querySelector('.ai-draft__wrap-content');
  const list = document.querySelector('.ai-draft__wrap-list');
  const paragraphs = list ? [...list.querySelectorAll('.ai-draft__p-paragraph')] : [];
  const sentences = list ? [...list.querySelectorAll('.ai-draft__p-sentence')] : [];
  const last = sentences.at(-1);
  const lastRect = last?.getBoundingClientRect();
  const scrollerRect = scroller?.getBoundingClientRect();
  const markerNodes = list
    ? [...list.querySelectorAll(
        '[class*="virtual"], [class*="skeleton"], [class*="placeholder"], '
        + '[class*="loading"], [class*="load-more"]'
      )]
    : [];
  const markers = [...new Set(markerNodes.map(
    node => (node.className || '').toString()
  ).filter(Boolean))];
  const text = (list?.innerText || '').trim();
  return {
    url: location.href,
    active: {
      matches: document.querySelectorAll('.vp-tabs__header-item--active').length,
      text: active?.textContent || ''
    },
    transcript: {text: list?.innerText || ''},
    render: {
      list_matches: document.querySelectorAll('.ai-draft__wrap-list').length,
      scroll_top: scroller?.scrollTop,
      client_height: scroller?.clientHeight,
      scroll_height: scroller?.scrollHeight,
      paragraph_count: paragraphs.length,
      sentence_count: sentences.length,
      list_text_chars: text.length,
      sentence_text_chars: sentences.reduce(
        (total, node) => total + (node.textContent || '').length,
        0
      ),
      last_node_in_dom: !!last && document.contains(last),
      last_node_below_viewport: !!lastRect && !!scrollerRect
        && lastRect.bottom > scrollerRect.bottom,
      virtual_or_loading_markers: markers,
      has_load_more: /加载更多|正在加载|展开全部/.test(list?.innerText || '')
    }
  };
})()"""
_ACTIONS = {"upload", "transcript", "ai_note", "export", "download"}
_CAPABILITY_FAILURES = {
    "browser_security_policy_denied",
    "authentication_required",
    "captcha_required",
    "page_contract_changed",
}
_STATE_PREDECESSORS = {
    "transcript_requested": "transcript_claimed",
    "transcript_ready": "transcript_requested",
    "ai_note_requested": "ai_note_claimed",
    "ai_note_ready": "ai_note_requested",
    "export_ready": "export_claimed",
    "cloud_document_ready": "export_ready",
    "download_requested": "download_claimed",
}
_RECONCILIATION_PREDECESSORS = {
    "transcript_ready": {"video_ready", "transcript_claimed", "transcript_requested"},
    "ai_note_ready": {"transcript_ready", "ai_note_claimed", "ai_note_requested"},
}
_STATE_ORDER = [
    "prepared",
    "upload_claimed",
    "video_ready",
    "transcript_claimed",
    "transcript_requested",
    "transcript_ready",
    "ai_note_claimed",
    "ai_note_requested",
    "ai_note_ready",
    "export_claimed",
    "export_ready",
    "cloud_document_ready",
    "download_claimed",
    "download_requested",
    "downloaded",
    "verified",
    "decided",
]
_VISIBLE_STATE_MARKERS = {
    "video_ready": "video_present",
    "transcript_requested": "transcript_generating",
    "transcript_ready": "transcript_ready",
    "ai_note_requested": "ai_note_generating",
    "ai_note_ready": "ai_note_ready",
    "export_ready": "transcript_exported",
    "cloud_document_ready": "cloud_document_present",
    "download_requested": "download_started",
}
_PLAYER_STEPS = {
    "transcript_requested",
    "transcript_ready",
    "ai_note_requested",
    "ai_note_ready",
    "export_ready",
}
_VISIBLE_STATE_PATTERNS = {
    "video_ready": re.compile(
        r"(?:上传完成|目标视频|(?:^|\n)\s*[-*]?\s*"
        r"(?:row|listitem|checkbox)(?=\s|[\"':=])|role\s*=\s*[\"']?"
        r"(?:row|listitem|checkbox)(?=\s|[\"':=]))",
        re.IGNORECASE,
    ),
    "transcript_requested": re.compile(r"文稿.{0,24}(?:生成中|处理中)"),
    "transcript_ready": re.compile(
        r"文稿.{0,48}(?:已生成|生成完成|已完成|"
        r"content_chars=[1-9]\d{2,}.{0,32}export_available)"
    ),
    "ai_note_requested": re.compile(r"AI\s*笔记.{0,24}(?:生成中|处理中)", re.IGNORECASE),
    "ai_note_ready": re.compile(
        r"AI\s*笔记.{0,48}(?:已生成|生成完成|已完成|"
        r"content_chars=[1-9]\d{2,}.{0,32}export_available)",
        re.IGNORECASE,
    ),
    "export_ready": re.compile(r"(?:文稿.{0,24})?已导出"),
    "cloud_document_ready": re.compile(
        r"(?:同名文稿|(?:^|\n)\s*[-*]?\s*"
        r"(?:row|listitem|checkbox)(?=\s|[\"':=])|role\s*=\s*[\"']?"
        r"(?:row|listitem|checkbox)(?=\s|[\"':=]))",
        re.IGNORECASE,
    ),
    "download_requested": re.compile(
        r"(?:下载.{0,24}(?:已开始|下载中)|已添加.{0,24}传输|传输.{0,24}进行中)"
    ),
}
_TRANSIENT_FAILURE_FIELDS = {
    "error_type",
    "failure_stage",
    "reason",
    "rejected_operation",
    "surface",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clear_transient_failures(row: dict[str, Any]) -> None:
    for field in _TRANSIENT_FAILURE_FIELDS:
        row.pop(field, None)


class NetdiskEnrichmentService:
    """Record browser actions only when backed by real page/download evidence."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        runner: Callable[..., Any] = subprocess.run,
        now: Callable[[], datetime] | None = None,
        opencli_command: tuple[str, ...] | None = None,
    ):
        self.store = EnrichmentJobStore(output_dir)
        self.output_dir = self.store.output_dir
        self.events_path = self.store.events_path
        self.runner = runner
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self.opencli_command = opencli_command or (
            "npx",
            "--yes",
            "@jackwener/opencli@1.8.6",
        )

    def _time(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise EnrichmentError("enrichment clock must include a timezone")
        return value

    def _run(self, command: list[str], *, timeout_seconds: int = 30) -> Any:
        try:
            result = self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentError(
                f"external command timed out: {command[0]}"
            ) from exc
        if result.returncode != 0:
            raise EnrichmentError(f"external command failed: {command[0]}")
        return result

    def _run_opencli(self, session: str, *args: str) -> Any:
        command = [
            *self.opencli_command,
            "browser",
            session,
            *args,
        ]
        last_error: EnrichmentError | None = None
        for _attempt in range(3):
            try:
                return self._run(command, timeout_seconds=10)
            except EnrichmentError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def status(self, job_id: str | None = None) -> dict[str, Any]:
        return self.store.status(job_id)

    def record_capability_failure(
        self,
        job_id: str,
        *,
        surface: str,
        reason: str,
    ) -> dict[str, Any]:
        if surface not in {"codex_in_app_browser", "codex_chrome", "opencli"}:
            raise EnrichmentError("unsupported browser surface")
        if reason not in _CAPABILITY_FAILURES:
            raise EnrichmentError("unsupported capability failure reason")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            row = {
                **current,
                "event": "netdisk_capability_failed",
                "surface": surface,
                "reason": reason,
                "browser_control_blocked": True,
                "updated_at": self._time().isoformat(timespec="microseconds"),
            }
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def record_browser_liveness(
        self,
        job_id: str,
        *,
        surface: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        if surface not in {"codex_in_app_browser", "codex_chrome", "opencli"}:
            raise EnrichmentError("unsupported browser surface")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            normalized = self._browser_liveness_evidence(evidence)
            self._require_after_latest_capability_failure(
                job_id,
                observed_at=str(normalized["observed_at"]),
                evidence_kind="browser liveness",
            )
            row = {
                **current,
                "event": "netdisk_browser_liveness_ready",
                "browser_surface": surface,
                "browser_liveness": normalized,
                "browser_control_blocked": False,
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def prepare(self, video_path: Path | str) -> dict[str, Any]:
        video = Path(video_path).expanduser().resolve()
        if not video.is_file():
            raise EnrichmentError(f"source video not found: {video}")
        if not video.name.endswith("-compressed.mp4"):
            raise EnrichmentError("ticket 02 requires a completed -compressed.mp4 source")
        video_sha256 = _sha256_file(video)
        job_id = f"kol-netdisk-{video_sha256[:16]}"
        with self.store.job_lock(job_id):
            try:
                current = self.store.latest(job_id)
            except EnrichmentError as exc:
                if "not found" not in str(exc):
                    raise
                current = None
            if current and current.get("status") != "prepare_failed":
                if current.get("video_sha256") != video_sha256:
                    raise EnrichmentError("prepared source hash cannot change")
                return {**current, "idempotent_replay": True}
            try:
                probe = self._run([
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(video),
                ])
                duration = float(json.loads(probe.stdout)["format"]["duration"])
            except (EnrichmentError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.store.append({
                    "schema_version": 1,
                    "event": "netdisk_prepare_failed",
                    "status": "prepare_failed",
                    "provider": "baidu_consumer_page",
                    "job_id": job_id,
                    "video_path": str(video),
                    "video_basename": video.name,
                    "video_sha256": video_sha256,
                    "error_type": type(exc).__name__,
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise EnrichmentError("failed to inspect source video") from exc
            row = {
                "schema_version": 1,
                "event": "netdisk_video_prepared",
                "status": "prepared",
                "provider": "baidu_consumer_page",
                "job_id": job_id,
                "video_path": str(video),
                "video_basename": video.name,
                "video_sha256": video_sha256,
                "video_size_bytes": video.stat().st_size,
                "video_duration_seconds": duration,
                "created_at": self._time().isoformat(timespec="seconds"),
            }
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def _browser_evidence(
        self,
        current: dict[str, Any],
        evidence: dict[str, Any],
        *,
        expected_target: str,
        step: str,
    ) -> dict[str, str]:
        if not isinstance(evidence, dict):
            raise EnrichmentError("browser evidence must be a JSON object")
        parsed = urlsplit(str(evidence.get("page_url") or ""))
        allowed_pages = (
            {"/disk/main", "/pfile/video"}
            if step == "video_ready"
            else ({"/pfile/video"} if step in _PLAYER_STEPS else {"/disk/main"})
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "pan.baidu.com"
            or parsed.path not in allowed_pages
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise EnrichmentError("browser evidence page URL is invalid")
        if parsed.path == "/pfile/video":
            netdisk_paths = parse_qs(
                parsed.query, keep_blank_values=True
            ).get("path") or []
            if (
                len(netdisk_paths) != 1
                or PurePosixPath(netdisk_paths[0]).name != expected_target
            ):
                raise EnrichmentError("browser evidence page URL is invalid")
        target = str(evidence.get("target_name") or "").strip()
        visible = str(evidence.get("visible_state") or "").strip()
        snapshot_text = evidence.get("snapshot_text")
        if not isinstance(snapshot_text, str) or not snapshot_text:
            raise EnrichmentError("browser evidence snapshot text is required")
        if len(snapshot_text.encode("utf-8")) > 2 * 1024 * 1024:
            raise EnrichmentError("browser evidence snapshot text is too large")
        target_region = evidence.get("target_region_text")
        if not isinstance(target_region, str) or not target_region:
            raise EnrichmentError("browser evidence target region is required")
        if len(target_region.encode("utf-8")) > 16 * 1024:
            raise EnrichmentError("browser evidence target region is too large")
        if target_region not in snapshot_text:
            raise EnrichmentError("browser evidence target region is not in the snapshot")
        snapshot_sha = str(evidence.get("snapshot_sha256") or "").strip().lower()
        observed = str(evidence.get("observed_at") or "").strip()
        try:
            observed_at = datetime.fromisoformat(observed)
        except ValueError as exc:
            raise EnrichmentError("browser evidence observed_at is invalid") from exc
        if observed_at.tzinfo is None:
            raise EnrichmentError("browser evidence observed_at needs a timezone")
        age = self._time().astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)
        if age < -timedelta(minutes=2) or age > timedelta(minutes=30):
            raise EnrichmentError("browser evidence observed_at is not fresh")
        if target != expected_target:
            raise EnrichmentError("browser evidence target does not match the expected artifact")
        secret_pattern = re.compile(
            r"\b(?:bduss|stoken|cookie|authorization|access[_ -]?token|"
            r"refresh[_ -]?token|client[_ -]?secret|password)\b",
            re.IGNORECASE,
        )
        if secret_pattern.search(snapshot_text):
            raise EnrichmentError("browser evidence snapshot contains secret material")
        expected_marker = _VISIBLE_STATE_MARKERS[step]
        if visible != expected_marker:
            raise EnrichmentError("browser evidence visible state is not canonical")
        exact_target = re.compile(
            rf"(?<![\w.-]){re.escape(expected_target)}(?![\w.-])"
        )
        if exact_target.search(target_region) is None:
            raise EnrichmentError("browser evidence snapshot does not prove the target")
        state_region = exact_target.sub("", target_region)
        pattern = _VISIBLE_STATE_PATTERNS.get(step)
        if pattern is not None and not pattern.search(state_region):
            raise EnrichmentError("browser evidence snapshot does not prove the state")
        if (
            len(visible) > 64
            or secret_pattern.search(visible)
            or "http://" in visible.lower()
            or "https://" in visible.lower()
        ):
            raise EnrichmentError("browser evidence visible state is unsafe")
        if not _SHA256.fullmatch(snapshot_sha):
            raise EnrichmentError("browser evidence is incomplete")
        actual_snapshot_sha = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        if snapshot_sha != actual_snapshot_sha:
            raise EnrichmentError("browser evidence snapshot hash does not match its content")
        safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        return {
            "page_url": safe_url,
            "target_name": target,
            "visible_state": visible,
            "snapshot_sha256": snapshot_sha,
            "observed_at": observed_at.isoformat(timespec="microseconds"),
        }

    def _browser_liveness_evidence(self, evidence: dict[str, Any]) -> dict[str, str]:
        if not isinstance(evidence, dict):
            raise EnrichmentError("browser liveness evidence must be a JSON object")
        parsed = urlsplit(str(evidence.get("page_url") or ""))
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "pan.baidu.com"
            or parsed.path not in {"/disk/main", "/pfile/video"}
        ):
            raise EnrichmentError("browser liveness page URL is invalid")
        snapshot_text = evidence.get("snapshot_text")
        if not isinstance(snapshot_text, str) or not snapshot_text:
            raise EnrichmentError("browser liveness snapshot text is required")
        if len(snapshot_text.encode("utf-8")) > 2 * 1024 * 1024:
            raise EnrichmentError("browser liveness snapshot text is too large")
        secret_pattern = re.compile(
            r"\b(?:bduss|stoken|cookie|authorization|access[_ -]?token|"
            r"refresh[_ -]?token|client[_ -]?secret|password)\b",
            re.IGNORECASE,
        )
        if secret_pattern.search(snapshot_text):
            raise EnrichmentError("browser liveness snapshot contains secret material")
        snapshot_sha = str(evidence.get("snapshot_sha256") or "").strip().lower()
        if not _SHA256.fullmatch(snapshot_sha):
            raise EnrichmentError("browser liveness evidence is incomplete")
        actual_snapshot_sha = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        if snapshot_sha != actual_snapshot_sha:
            raise EnrichmentError(
                "browser liveness snapshot hash does not match its content"
            )
        observed = str(evidence.get("observed_at") or "").strip()
        try:
            observed_at = datetime.fromisoformat(observed)
        except ValueError as exc:
            raise EnrichmentError("browser liveness observed_at is invalid") from exc
        if observed_at.tzinfo is None:
            raise EnrichmentError("browser liveness observed_at needs a timezone")
        age = self._time().astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)
        if age < -timedelta(minutes=2) or age > timedelta(minutes=30):
            raise EnrichmentError("browser liveness observed_at is not fresh")
        return {
            "page_url": urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")),
            "snapshot_sha256": snapshot_sha,
            "observed_at": observed_at.isoformat(timespec="microseconds"),
        }

    def _has_fresh_browser_control(self, current: dict[str, Any]) -> bool:
        if current.get("event") == "netdisk_capability_failed" or current.get(
            "browser_control_blocked"
        ):
            return False
        proof = (
            current.get("browser_liveness")
            if current.get("event") == "netdisk_browser_liveness_ready"
            else current.get("browser_evidence")
        )
        if not isinstance(proof, dict):
            return False
        try:
            observed_at = datetime.fromisoformat(str(proof.get("observed_at") or ""))
        except ValueError:
            return False
        if observed_at.tzinfo is None:
            return False
        age = self._time().astimezone(timezone.utc) - observed_at.astimezone(timezone.utc)
        return -timedelta(minutes=2) <= age <= timedelta(minutes=30)

    @staticmethod
    def _event_time(value: Any, *, field: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except ValueError as exc:
            raise EnrichmentError(f"browser evidence predecessor {field} is invalid") from exc
        if parsed.tzinfo is None:
            raise EnrichmentError(
                f"browser evidence predecessor {field} needs a timezone"
            )
        return parsed.astimezone(timezone.utc)

    def _latest_capability_failure_at(self, job_id: str) -> datetime | None:
        for row in reversed(self.store.read()):
            if (
                row.get("job_id") == job_id
                and row.get("event") == "netdisk_capability_failed"
            ):
                return self._event_time(row.get("updated_at"), field="updated_at")
        return None

    def _require_after_latest_capability_failure(
        self,
        job_id: str,
        *,
        observed_at: str,
        evidence_kind: str,
    ) -> None:
        failure_at = self._latest_capability_failure_at(job_id)
        if failure_at is None:
            return
        observed = self._event_time(observed_at, field="observed_at")
        if observed <= failure_at:
            raise EnrichmentError(
                f"{evidence_kind} must post-date the latest capability failure"
            )

    def _require_transition_causality(
        self,
        current: dict[str, Any],
        *,
        step: str,
        observed_at: str,
        reconcile_existing: bool,
    ) -> None:
        observed = self._event_time(observed_at, field="observed_at")
        if reconcile_existing:
            return
        checkpoint: datetime | None = None
        checkpoint_name = ""
        if step == "video_ready" and current.get("status") == "upload_claimed":
            checkpoint = self._event_time(
                current.get("claimed_at"), field="upload claimed_at"
            )
            checkpoint_name = "upload claim"
        elif step in {
            "transcript_requested",
            "ai_note_requested",
            "export_ready",
            "download_requested",
        }:
            checkpoint = self._event_time(
                current.get("claimed_at"), field=f"{step} claimed_at"
            )
            checkpoint_name = "browser action claim"
        elif step in {"transcript_ready", "ai_note_ready", "cloud_document_ready"}:
            predecessor = current.get("browser_evidence")
            if not isinstance(predecessor, dict):
                raise EnrichmentError(
                    f"{step} requires timestamped predecessor browser evidence"
                )
            checkpoint = self._event_time(
                predecessor.get("observed_at"), field=f"{step} predecessor observed_at"
            )
            checkpoint_name = "predecessor browser evidence"
        if checkpoint is not None and observed < checkpoint:
            raise EnrichmentError(
                f"{step} evidence predates its {checkpoint_name}"
            )

    def _state_at_or_after(self, current: str, expected: str) -> bool:
        try:
            return _STATE_ORDER.index(current) >= _STATE_ORDER.index(expected)
        except ValueError:
            return False

    def _record_rejection(
        self,
        current: dict[str, Any],
        *,
        operation: str,
        reason: str,
    ) -> None:
        row = {
            **current,
            "event": "netdisk_transition_rejected",
            "rejected_operation": operation,
            "reason": reason,
            "updated_at": self._time().isoformat(timespec="seconds"),
        }
        if current.get("event") == "netdisk_capability_failed" or current.get(
            "browser_control_blocked"
        ):
            row["browser_control_blocked"] = True
        self.store.append(row)

    def claim_browser_action(self, job_id: str, *, action: str) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise EnrichmentError(f"unsupported browser action: {action}")
        expected = {
            "upload": {"prepared"},
            "transcript": {"video_ready"},
            "ai_note": {"transcript_ready"},
            "export": {"transcript_ready", "ai_note_ready"},
            "download": {"cloud_document_ready"},
        }[action]
        claimed_status = f"{action}_claimed"
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("provider") != "baidu_consumer_page":
                raise EnrichmentError("provider cannot change during a Netdisk job")
            if current.get("status") == claimed_status:
                return {**current, "idempotent_replay": True}
            if self._state_at_or_after(str(current.get("status")), claimed_status):
                return {**current, "idempotent_replay": True}
            if not self._has_fresh_browser_control(current):
                self._record_rejection(
                    current,
                    operation=f"claim:{action}",
                    reason="browser_control_not_live",
                )
                raise EnrichmentError(
                    f"{action} requires fresh browser claim/DOM liveness evidence"
                )
            if current.get("status") not in expected:
                self._record_rejection(
                    current,
                    operation=f"claim:{action}",
                    reason="invalid_predecessor",
                )
                raise EnrichmentError(
                    f"{action} requires one of {sorted(expected)}, "
                    f"got {current.get('status')}"
                )
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **current,
                "event": f"netdisk_{action}_claimed",
                "status": claimed_status,
                "claimed_at": now,
                "updated_at": now,
            }
            if action == "download":
                row["download_claimed_at"] = now
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def record_browser_state(
        self,
        job_id: str,
        *,
        step: str,
        evidence: dict[str, Any],
        source_mode: str | None = None,
        reconcile_existing: bool = False,
    ) -> dict[str, Any]:
        allowed_steps = {"video_ready", *_STATE_PREDECESSORS.keys()}
        if step not in allowed_steps:
            raise EnrichmentError(f"unsupported Netdisk browser state: {step}")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if reconcile_existing and step not in _RECONCILIATION_PREDECESSORS:
                self._record_rejection(
                    current,
                    operation=f"reconcile:{step}",
                    reason="unsupported_reconciliation_state",
                )
                raise EnrichmentError(
                    f"{step} cannot be reconciled as an existing durable state"
                )
            if current.get("status") == step:
                return {**current, "idempotent_replay": True}
            if self._state_at_or_after(str(current.get("status")), step):
                return {**current, "idempotent_replay": True}
            if step == "video_ready":
                if source_mode not in {"existing", "uploaded"}:
                    self._record_rejection(
                        current,
                        operation="record:video_ready",
                        reason="invalid_source_mode",
                    )
                    raise EnrichmentError("video_ready requires existing or uploaded source_mode")
                expected = "upload_claimed" if source_mode == "uploaded" else "prepared"
            else:
                expected = _STATE_PREDECESSORS[step]
            current_status = str(current.get("status") or "")
            reconciliation_allowed = (
                reconcile_existing
                and current_status in _RECONCILIATION_PREDECESSORS.get(step, set())
            )
            if current_status != expected and not reconciliation_allowed:
                self._record_rejection(
                    current,
                    operation=f"record:{step}",
                    reason=(
                        "invalid_reconciliation_predecessor"
                        if reconcile_existing
                        else "invalid_predecessor"
                    ),
                )
                raise EnrichmentError(f"{step} requires state {expected}")
            try:
                expected_target = str(current["video_basename"])
                if step in {"cloud_document_ready", "download_requested"}:
                    expected_target = f"{Path(expected_target).stem}.doc"
                normalized = self._browser_evidence(
                    current,
                    evidence,
                    expected_target=expected_target,
                    step=step,
                )
                self._require_after_latest_capability_failure(
                    job_id,
                    observed_at=str(normalized["observed_at"]),
                    evidence_kind=f"{step} browser evidence",
                )
                self._require_transition_causality(
                    current,
                    step=step,
                    observed_at=str(normalized["observed_at"]),
                    reconcile_existing=reconciliation_allowed,
                )
            except EnrichmentError:
                self._record_rejection(
                    current,
                    operation=f"record:{step}",
                    reason="invalid_browser_evidence",
                )
                raise
            now = self._time().isoformat(timespec="seconds")
            row = {
                **current,
                "event": (
                    f"netdisk_{step}_reconciled"
                    if reconciliation_allowed
                    else f"netdisk_{step}"
                ),
                "status": step,
                "browser_evidence": normalized,
                "browser_control_blocked": False,
                "updated_at": now,
            }
            if reconciliation_allowed:
                row["reconciled_existing"] = True
                row["reconciled_from_status"] = current_status
            if step == "video_ready":
                row["source_mode"] = source_mode
            if step == "download_requested":
                row["download_requested_at"] = now
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def import_transcript_download(
        self, job_id: str, download_path: Path | str
    ) -> dict[str, Any]:
        source = Path(download_path).expanduser().resolve()
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)

            def reject(reason: str, message: str) -> None:
                self.store.append({
                    **current,
                    "event": "netdisk_download_import_failed",
                    "status": current.get("status"),
                    "failure_stage": "import_download",
                    "reason": reason,
                    "error_type": "EnrichmentError",
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise EnrichmentError(message)

            if not source.is_file():
                reject("file_not_found", f"downloaded transcript not found: {source}")
            source_sha = _sha256_file(source)
            if current.get("status") in {"downloaded", "verified", "decided"}:
                if current.get("download_sha256") == source_sha:
                    return {**current, "idempotent_replay": True}
                reject(
                    "completed_download_mismatch",
                    "completed download cannot be silently replaced",
                )
            if current.get("status") != "download_requested":
                reject(
                    "invalid_predecessor",
                    "download import requires state download_requested",
                )
            suffix = source.suffix.lower()
            if suffix not in {".doc", ".docx", ".txt", ".md"}:
                reject(
                    "unsupported_format",
                    "downloaded transcript has an unsupported format",
                )
            video_stem = Path(str(current["video_basename"])).stem
            if source.stem != video_stem:
                reject(
                    "basename_mismatch",
                    "downloaded transcript name does not exactly match the video",
                )
            try:
                claimed_at = datetime.fromisoformat(
                    str(current.get("download_claimed_at") or "")
                )
            except ValueError:
                reject("missing_claim_time", "download claim time is invalid")
            if claimed_at.tzinfo is None:
                reject("missing_claim_time", "download claim time needs a timezone")
            modified_at = datetime.fromtimestamp(
                source.stat().st_mtime, tz=timezone.utc
            )
            if (
                modified_at < claimed_at.astimezone(timezone.utc) - timedelta(seconds=1)
                or modified_at
                > self._time().astimezone(timezone.utc) + timedelta(minutes=2)
            ):
                reject(
                    "stale_or_future_file",
                    "downloaded transcript is not fresh for this download request",
                )
            artifact_dir = self.output_dir / "artifacts" / job_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            durable_download = artifact_dir / source.name
            temporary = artifact_dir / f".{source.name}.partial"
            shutil.copyfile(source, temporary)
            temporary.replace(durable_download)
            try:
                if suffix in {".txt", ".md"}:
                    transcript = durable_download.read_text(encoding="utf-8")
                else:
                    converted = self._run([
                        "textutil",
                        "-convert",
                        "txt",
                        "-stdout",
                        str(durable_download),
                    ])
                    transcript = str(converted.stdout)
                if len(transcript.strip()) < 200:
                    raise EnrichmentError("downloaded transcript is implausibly short")
            except (EnrichmentError, OSError, UnicodeError) as exc:
                self.store.append({
                    **current,
                    "event": "netdisk_download_import_failed",
                    "status": "download_requested",
                    "download_sha256": source_sha,
                    "failure_stage": "read_download",
                    "reason": "read_or_conversion_failed",
                    "error_type": type(exc).__name__,
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise
            transcript_path = artifact_dir / f"{video_stem}.txt"
            transcript_bytes = (transcript.rstrip() + "\n").encode("utf-8")
            transcript_temp = artifact_dir / f".{video_stem}.partial.txt"
            transcript_temp.write_bytes(transcript_bytes)
            transcript_temp.replace(transcript_path)
            now = self._time().isoformat(timespec="seconds")
            row = {
                **current,
                "event": "netdisk_transcript_downloaded",
                "status": "downloaded",
                "download_path": str(durable_download),
                "download_sha256": _sha256_file(durable_download),
                "download_size_bytes": durable_download.stat().st_size,
                "transcript_path": str(transcript_path),
                "transcript_sha256": hashlib.sha256(transcript_bytes).hexdigest(),
                "transcript_character_count": len(transcript.strip()),
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def capture_opencli_transcript(
        self,
        job_id: str,
        *,
        session: str,
    ) -> dict[str, Any]:
        """Materialize a complete, already-rendered Netdisk transcript via OpenCLI."""
        if not _OPENCLI_SESSION.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            failure_recorded = False

            def reject(reason: str, message: str) -> None:
                nonlocal failure_recorded
                failure_recorded = True
                self.store.append({
                    **current,
                    "event": "netdisk_dom_capture_failed",
                    "status": current.get("status"),
                    "failure_stage": "capture_opencli_dom",
                    "reason": reason,
                    "error_type": "EnrichmentError",
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise EnrichmentError(message)

            if current.get("status") in {"downloaded", "verified", "decided"}:
                transcript_path = Path(str(current.get("transcript_path") or ""))
                if (
                    current.get("transcript_acquisition") == "opencli_dom"
                    and transcript_path.is_file()
                    and _sha256_file(transcript_path)
                    == current.get("transcript_sha256")
                ):
                    return {**current, "idempotent_replay": True}
                reject(
                    "completed_capture_mismatch",
                    "completed transcript capture cannot be silently replaced",
                )
            if current.get("status") not in {"transcript_ready", "ai_note_ready"}:
                reject(
                    "invalid_predecessor",
                    "OpenCLI DOM capture requires a ready transcript",
                )
            if current.get("browser_surface") != "opencli":
                reject(
                    "wrong_browser_surface",
                    "OpenCLI DOM capture requires an OpenCLI browser proof",
                )
            if not self._has_fresh_browser_control(current):
                reject(
                    "browser_control_not_live",
                    "OpenCLI DOM capture requires fresh browser evidence",
                )

            try:
                capture_output = self._run_opencli(
                    session,
                    "eval",
                    _OPENCLI_CAPTURE_PROBE,
                )
                capture_result = json.loads(str(capture_output.stdout))
                page_url = (
                    capture_result.get("url")
                    if isinstance(capture_result, dict)
                    else None
                )
                if not isinstance(page_url, str):
                    reject(
                        "invalid_opencli_url",
                        "OpenCLI did not return a page URL",
                    )
                parsed = urlsplit(page_url)
                query = parse_qs(parsed.query, keep_blank_values=True)
                netdisk_paths = query.get("path") or []
                if (
                    parsed.scheme != "https"
                    or parsed.netloc.lower() != "pan.baidu.com"
                    or parsed.path != "/pfile/video"
                    or parsed.username is not None
                    or parsed.password is not None
                    or len(netdisk_paths) != 1
                    or PurePosixPath(netdisk_paths[0]).name
                    != current.get("video_basename")
                ):
                    reject(
                        "target_url_mismatch",
                        "OpenCLI page does not match the prepared Netdisk video",
                    )

                active = capture_result.get("active")
                if (
                    not isinstance(active, dict)
                    or active.get("matches") != 1
                    or str(active.get("text") or "").strip() != "文稿"
                ):
                    reject(
                        "transcript_tab_not_active",
                        "OpenCLI transcript tab is not uniquely active",
                    )

                transcript_result = capture_result.get("transcript")
                transcript = (
                    transcript_result.get("text")
                    if isinstance(transcript_result, dict)
                    else None
                )
                if (
                    not isinstance(transcript_result, dict)
                    or not isinstance(transcript, str)
                    or len(transcript.strip()) < 200
                ):
                    reject(
                        "transcript_missing_or_short",
                        "OpenCLI did not return one nontrivial transcript",
                    )

                render = capture_result.get("render")
            except (EnrichmentError, json.JSONDecodeError, StopIteration) as exc:
                if isinstance(exc, EnrichmentError):
                    if not failure_recorded:
                        reject(
                            "opencli_command_failed",
                            "OpenCLI transcript capture command failed",
                        )
                    raise
                reject(
                    "invalid_opencli_response",
                    "OpenCLI returned invalid transcript evidence",
                )

            if not isinstance(render, dict):
                reject("invalid_render_proof", "OpenCLI render proof is invalid")
            numeric_fields = {
                "scroll_top",
                "list_matches",
                "client_height",
                "scroll_height",
                "paragraph_count",
                "sentence_count",
                "list_text_chars",
                "sentence_text_chars",
            }
            if any(
                not isinstance(render.get(field), (int, float))
                for field in numeric_fields
            ):
                reject("invalid_render_proof", "OpenCLI render proof is incomplete")
            markers = render.get("virtual_or_loading_markers")
            transcript_text = transcript.strip()
            content_fits = render["scroll_height"] <= render["client_height"] + 1
            if (
                render["scroll_top"] != 0
                or render["list_matches"] != 1
                or render["paragraph_count"] < 1
                or render["sentence_count"] < 3
                or render["list_text_chars"] != len(transcript_text)
                or render["sentence_text_chars"] <= 0
                or render["sentence_text_chars"] > render["list_text_chars"]
                or render.get("last_node_in_dom") is not True
                or (
                    not content_fits
                    and render.get("last_node_below_viewport") is not True
                )
                or not isinstance(markers, list)
                or markers
                or render.get("has_load_more") is not False
            ):
                reject(
                    "partial_or_virtualized_transcript",
                    "OpenCLI transcript is not proven fully rendered",
                )

            observed_at = self._time()
            self._require_after_latest_capability_failure(
                job_id,
                observed_at=observed_at.isoformat(timespec="microseconds"),
                evidence_kind="OpenCLI DOM capture",
            )
            predecessor = current.get("browser_evidence")
            if isinstance(predecessor, dict):
                predecessor_at = self._event_time(
                    predecessor.get("observed_at"),
                    field="OpenCLI capture predecessor observed_at",
                )
                if observed_at.astimezone(timezone.utc) < predecessor_at:
                    reject(
                        "capture_predates_predecessor",
                        "OpenCLI DOM capture predates its browser evidence",
                    )

            artifact_dir = self.output_dir / "artifacts" / job_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            video_stem = Path(str(current["video_basename"])).stem
            transcript_path = artifact_dir / f"{video_stem}.txt"
            transcript_bytes = (transcript_text.rstrip() + "\n").encode("utf-8")
            transcript_temp = artifact_dir / f".{video_stem}.partial.txt"
            transcript_temp.write_bytes(transcript_bytes)
            transcript_temp.replace(transcript_path)
            transcript_sha = hashlib.sha256(transcript_bytes).hexdigest()
            safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            render_proof = {
                key: render[key]
                for key in (
                    "scroll_top",
                    "list_matches",
                    "client_height",
                    "scroll_height",
                    "paragraph_count",
                    "sentence_count",
                    "list_text_chars",
                    "sentence_text_chars",
                    "last_node_in_dom",
                    "last_node_below_viewport",
                    "has_load_more",
                )
            }
            render_proof["virtual_or_loading_markers"] = []
            binding = {
                "page_url": safe_url,
                "target_name": current["video_basename"],
                "selector": ".ai-draft__wrap-list",
                "transcript_sha256": transcript_sha,
                "render_proof": render_proof,
                "observed_at": observed_at.isoformat(timespec="microseconds"),
            }
            binding_bytes = json.dumps(
                binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            row = {
                **current,
                "event": "netdisk_transcript_dom_captured",
                "status": "downloaded",
                "transcript_acquisition": "opencli_dom",
                "transcript_path": str(transcript_path),
                "transcript_sha256": transcript_sha,
                "transcript_character_count": len(transcript_text),
                "dom_page_url": safe_url,
                "dom_selector": ".ai-draft__wrap-list",
                "dom_render_proof": render_proof,
                "dom_capture_sha256": hashlib.sha256(binding_bytes).hexdigest(),
                "dom_capture_observed_at": observed_at.isoformat(
                    timespec="microseconds"
                ),
                "updated_at": observed_at.isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def verify_download(
        self, job_id: str, *, audit_path: Path | str
    ) -> dict[str, Any]:
        supplied = Path(audit_path).expanduser().resolve()
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)

            def reject(reason: str, message: str) -> None:
                self.store.append({
                    **current,
                    "event": "netdisk_content_verification_failed",
                    "status": current.get("status"),
                    "failure_stage": "verify_download",
                    "reason": reason,
                    "error_type": "EnrichmentError",
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise EnrichmentError(message)

            if not supplied.is_file():
                reject("audit_not_found", f"content audit not found: {supplied}")
            audit_bytes = supplied.read_bytes()
            audit_sha = hashlib.sha256(audit_bytes).hexdigest()
            if current.get("status") in {"verified", "decided"}:
                if current.get("audit_sha256") == audit_sha:
                    return {**current, "idempotent_replay": True}
                reject(
                    "completed_audit_mismatch",
                    "verified content audit cannot be replaced",
                )
            if current.get("status") != "downloaded":
                reject(
                    "invalid_predecessor",
                    "content verification requires state downloaded",
                )
            transcript_path = Path(str(current.get("transcript_path") or ""))
            if (
                not transcript_path.is_file()
                or _sha256_file(transcript_path) != current.get("transcript_sha256")
            ):
                reject(
                    "transcript_missing_or_changed",
                    "downloaded transcript is missing or changed",
                )
            try:
                audit = json.loads(audit_bytes)
            except json.JSONDecodeError as exc:
                self.store.append({
                    **current,
                    "event": "netdisk_content_verification_failed",
                    "status": current.get("status"),
                    "failure_stage": "verify_download",
                    "reason": "invalid_audit_json",
                    "error_type": type(exc).__name__,
                    "updated_at": self._time().isoformat(timespec="seconds"),
                })
                raise EnrichmentError("content audit is invalid JSON") from exc
            if not isinstance(audit, dict):
                reject("invalid_audit_shape", "content audit must be a JSON object")
            checks = audit.get("checks")
            positions = {"opening", "middle", "ending"}
            if (
                audit.get("video_sha256") != current.get("video_sha256")
                or audit.get("transcript_sha256") != current.get("transcript_sha256")
                or not isinstance(checks, list)
                or len(checks) != 3
                or any(not isinstance(check, dict) for check in checks)
                or {check.get("position") for check in checks} != positions
            ):
                reject(
                    "audit_binding_mismatch",
                    "content audit does not match the downloaded transcript",
                )
            text = transcript_path.read_text(encoding="utf-8")
            boundaries = {
                "opening": (0, len(text) / 3),
                "middle": (len(text) / 3, len(text) * 2 / 3),
                "ending": (len(text) * 2 / 3, len(text)),
            }
            for check in checks:
                excerpt = str(check.get("excerpt") or "").strip()
                begin, end = boundaries[str(check["position"])]
                matches = [
                    match.start()
                    for match in re.finditer(re.escape(excerpt), text)
                ] if excerpt else []
                if (
                    check.get("passed") is not True
                    or not any(begin <= position < end for position in matches)
                ):
                    reject(
                        "unverified_excerpt",
                        "content audit contains an unverified excerpt",
                    )
            artifact_dir = self.output_dir / "artifacts" / job_id
            durable_audit = artifact_dir / "content_audit.json"
            temporary = artifact_dir / ".content_audit.partial.json"
            temporary.write_bytes(audit_bytes)
            temporary.replace(durable_audit)
            row = {
                **current,
                "event": "netdisk_content_verified",
                "status": "verified",
                "content_checks": sorted(positions),
                "audit_path": str(durable_audit),
                "audit_sha256": audit_sha,
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def decide(
        self,
        job_id: str,
        *,
        bundle_path: Path | str,
        decision_output_dir: Path | str,
        sender: Callable[[str, str], dict[str, str]],
        pipeline: Any | None = None,
    ) -> dict[str, Any]:
        bundle_file = Path(bundle_path).expanduser().resolve()
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)

            def record_failure(
                stage: str,
                exc: BaseException,
                *,
                bundle_sha: str | None = None,
            ) -> None:
                row = {
                    **current,
                    "event": "netdisk_decision_failed",
                    "status": current.get("status"),
                    "failure_stage": stage,
                    "error_type": type(exc).__name__,
                    "updated_at": self._time().isoformat(timespec="seconds"),
                }
                if bundle_sha is not None:
                    row["decision_bundle_sha256"] = bundle_sha
                self.store.append(row)

            if not bundle_file.is_file():
                exc = EnrichmentError(f"decision bundle not found: {bundle_file}")
                record_failure("bundle_not_found", exc)
                raise exc
            try:
                bundle_bytes = bundle_file.read_bytes()
            except OSError as exc:
                record_failure("bundle_read", exc)
                raise EnrichmentError("decision bundle could not be read") from exc
            bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
            if (
                current.get("status") == "decided"
                and current.get("decision_bundle_sha256") == bundle_sha
            ):
                return {**current, "idempotent_replay": True}
            if current.get("status") != "verified":
                exc = EnrichmentError(
                    "only a verified Netdisk transcript can be decided"
                )
                record_failure("invalid_predecessor", exc, bundle_sha=bundle_sha)
                raise exc
            transcript_path = Path(str(current.get("transcript_path") or ""))
            if (
                not transcript_path.is_file()
                or _sha256_file(transcript_path) != current.get("transcript_sha256")
            ):
                exc = EnrichmentError("verified transcript is missing or changed")
                record_failure(
                    "transcript_missing_or_changed", exc, bundle_sha=bundle_sha
                )
                raise exc
            try:
                bundle = json.loads(bundle_bytes)
            except json.JSONDecodeError as exc:
                record_failure("invalid_bundle_json", exc, bundle_sha=bundle_sha)
                raise EnrichmentError("decision bundle is invalid JSON") from exc
            items = bundle.get("items") if isinstance(bundle, dict) else None
            if not isinstance(items, list) or len(items) != 1:
                exc = EnrichmentError(
                    "one Netdisk video requires exactly one decision item"
                )
                record_failure("invalid_bundle_items", exc, bundle_sha=bundle_sha)
                raise exc
            if not isinstance(items[0], dict):
                exc = EnrichmentError("decision bundle item must be a JSON object")
                record_failure("invalid_bundle_item", exc, bundle_sha=bundle_sha)
                raise exc
            evidence_path = Path(
                str(items[0].get("evidence_path") or "")
            ).expanduser().resolve()
            if evidence_path != transcript_path.resolve():
                exc = EnrichmentError(
                    "decision bundle evidence_path must be the verified transcript"
                )
                record_failure("evidence_path_mismatch", exc, bundle_sha=bundle_sha)
                raise exc
            if pipeline is None:
                from .decisions import DecisionPipeline
                from .household import LiangHuiMcpClient

                pipeline = DecisionPipeline(
                    Path(decision_output_dir),
                    household_context_loader=LiangHuiMcpClient.from_config().load_context,
                )

            try:
                result = pipeline.process(bundle)
            except Exception as exc:
                record_failure("process", exc, bundle_sha=bundle_sha)
                raise EnrichmentError("ticket 01 decision pipeline failed") from exc
            try:
                validate_decision_process_result(result)
            except EnrichmentError as exc:
                record_failure("process_result", exc, bundle_sha=bundle_sha)
                raise exc
            try:
                result["wechat_delivery"] = pipeline.deliver_wechat(
                    result, sender=sender
                )
            except Exception as exc:
                record_failure("wechat_delivery", exc, bundle_sha=bundle_sha)
                raise EnrichmentError("household advisory delivery failed") from exc
            try:
                notification, paper = validate_decision_completion(result)
            except EnrichmentError as exc:
                record_failure("completion_result", exc, bundle_sha=bundle_sha)
                raise
            result_bytes = (
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode("utf-8")
            artifact_dir = self.output_dir / "artifacts" / job_id
            result_path = artifact_dir / "decision_result.json"
            temporary = artifact_dir / ".decision_result.partial.json"
            temporary.write_bytes(result_bytes)
            temporary.replace(result_path)
            household_summary = {
                key: notification[key]
                for key in ("idempotency_key", "status", "receipt")
                if notification.get(key) is not None
            }
            paper_summary = {
                key: paper[key]
                for key in (
                    "status",
                    "book",
                    "paper_only",
                    "ticker",
                    "side",
                    "reason",
                    "idempotency_key",
                )
                if paper.get(key) is not None
            }
            row = {
                **current,
                "event": "netdisk_decisions_completed",
                "status": "decided",
                "decision_bundle_path": str(bundle_file),
                "decision_bundle_sha256": bundle_sha,
                "decision_result_path": str(result_path),
                "decision_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "household_notification": household_summary,
                "book_kol_us": paper_summary,
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}
