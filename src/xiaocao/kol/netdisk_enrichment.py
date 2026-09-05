"""Resumable Baidu Netdisk consumer-page video enrichment evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from .enrichment_store import EnrichmentJobStore
from .enrichment_types import (
    EnrichmentDiagnosticError,
    EnrichmentError,
    validate_decision_completion,
    validate_decision_process_result,
)
from .netdisk_opencli_templates import (
    NETDISK_OPENCLI_TEMPLATE_VERSION,
    render_netdisk_opencli_template,
)
from .runtime_paths import resolve_repo_owned_path
from .semantic_bundle import (
    SemanticBundleError,
    ValidatedBundleReceipt,
    read_validated_bundle,
    validate_receipt_bindings,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPENCLI_SESSION = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_OPENCLI_PROFILE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_OPENCLI_UPLOAD_TIMEOUT_SECONDS = 300
_OPENCLI_UPLOAD_TEMPLATE_SESSION = "site:baidu-netdisk"
_OPENCLI_FOLDER_READY_ATTEMPTS = 6
_OPENCLI_FOLDER_READY_WAIT_SECONDS = 2
_OPENCLI_READBACK_REBIND_CODES = frozenset(
    {"opencli_timeout", "opencli_command_failed"}
)
_OPENCLI_READBACK_REBIND_STAGES = frozenset(
    {"browser_open", "browser_eval", "browser_wait"}
)
_NETDISK_GENERATION_POLL_INTERVAL = timedelta(minutes=1)
_AI_NOTE_MAX_TRIGGER_ATTEMPTS = 2
_AI_NOTE_POSTCLICK_ZERO_MIN_AGE = timedelta(minutes=5)
_NETDISK_DIRECTORY = "/课程/自己的课/小草"
_NETDISK_FOLDER_URL = (
    "https://pan.baidu.com/disk/main#/index?category=all&path="
    "%2F%E8%AF%BE%E7%A8%8B%2F%E8%87%AA%E5%B7%B1%E7%9A%84%E8%AF%BE%2F%E5%B0%8F%E8%8D%89"
)


_OPENCLI_PLAYER_PAUSE_GUARD = r"""(async () => {
  const expectedPath = __EXPECTED_NETDISK_PATH__;
  const currentUrl = new URL(location.href);
  const targetBound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!targetBound) {
    return {
      target_bound: false,
      video_count: 0,
      playing_before_pause: 0,
      all_video_paused: false,
      pause_guard_installed: false
    };
  }
  const guardKey = '__xiaocaoNetdiskPauseGuardV1';
  const pauseVideo = node => {
    if (!(node instanceof HTMLVideoElement)) return;
    node.autoplay = false;
    node.removeAttribute('autoplay');
    if (!node.paused) node.pause();
  };
  if (!window[guardKey]) {
    const onPlay = event => pauseVideo(event.target);
    document.addEventListener('play', onPlay, true);
    const observer = new MutationObserver(() => {
      document.querySelectorAll('video').forEach(pauseVideo);
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
    window[guardKey] = {observer, onPlay};
  }
  const deadline = Date.now() + 10000;
  let videos = [];
  let playingBeforePause = 0;
  while (Date.now() < deadline) {
    videos = [...document.querySelectorAll('video')];
    playingBeforePause += videos.filter(node => !node.paused).length;
    videos.forEach(pauseVideo);
    if (videos.length > 0 && videos.every(node => node.paused)) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  videos = [...document.querySelectorAll('video')];
  videos.forEach(pauseVideo);
  return {
    target_bound: true,
    video_count: videos.length,
    playing_before_pause: playingBeforePause,
    all_video_paused: videos.length > 0 && videos.every(node => node.paused),
    pause_guard_installed: !!window[guardKey]
  };
})()"""


def _validate_canonical_semantic_artifact(
    bundle_file: Path,
    bundle: dict[str, Any],
    *,
    expected_bindings: dict[str, Any] | None = None,
) -> ValidatedBundleReceipt | None:
    """Reconcile a v2 artifact before any Netdisk consumer side effect."""

    if bundle.get("schema_version") != 2:
        return None
    receipt, _ = read_validated_bundle(bundle_file)
    if expected_bindings:
        validate_receipt_bindings(receipt, expected_bindings)
    return receipt


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


_OPENCLI_CAPTURE_PROBE = r"""(async () => {
  const expectedPath = __EXPECTED_NETDISK_PATH__;
  const currentUrl = new URL(location.href);
  const targetBound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!targetBound) return {url: location.href, target_bound: false};
  const pauseVideos = () => {
    const videos = [...document.querySelectorAll('video')];
    videos.forEach(node => {
      node.autoplay = false;
      node.removeAttribute('autoplay');
      if (!node.paused) node.pause();
    });
    return videos;
  };
  pauseVideos();
  const visible = node => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const adPattern = /广告|运营图片|限时特惠|下载客户端|开通\s*(?:SVIP|超级会员)|SVIP\s*(?:活动|特惠|优惠)/i;
  const overlaySelector = [
    '.nd-operate-guidance',
    '[role="dialog"]',
    '[class*="modal"]',
    '[class*="popup"]',
    '[class*="advert"]',
    '[class*="promotion"]',
    '[class*="pay-revolution"]',
    '[class*="vip-dialog"]'
  ].join(',');
  let ad_overlays_dismissed = 0;
  for (const overlay of [...document.querySelectorAll(overlaySelector)]) {
    const text = (overlay.innerText || '').trim();
    const imageLabels = [...overlay.querySelectorAll('img')].map(
      node => `${node.getAttribute('alt') || ''} ${node.className || ''}`
    ).join(' ');
    const identity = `${overlay.className || ''} ${text} ${imageLabels}`;
    if (!visible(overlay) || !adPattern.test(identity)) continue;
    const close = [...overlay.querySelectorAll(
      'button,[role="button"],[aria-label],[title],[class*="close"],img[alt="close"]'
    )].find(node => {
      const label = `${node.getAttribute('aria-label') || ''} `
        + `${node.getAttribute('title') || ''} `
        + `${node.getAttribute('alt') || ''} `
        + `${node.className || ''} ${(node.textContent || '').trim()}`;
      return visible(node) && /关闭|close|×|^x$/i.test(label);
    });
    if (close) {
      close.click();
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (document.contains(overlay) && visible(overlay)) {
      overlay.style.setProperty('display', 'none', 'important');
      overlay.setAttribute('aria-hidden', 'true');
    }
    ad_overlays_dismissed += 1;
  }
  const tabs = [...document.querySelectorAll('.vp-tabs__header-item')];
  const transcriptTabs = tabs.filter(
    node => (node.textContent || '').trim() === '文稿'
  );
  if (transcriptTabs.length === 1
      && !transcriptTabs[0].classList.contains('vp-tabs__header-item--active')) {
    transcriptTabs[0].click();
  }
  const deadline = Date.now() + 20000;
  let active = null;
  let scroller = null;
  let list = null;
  while (Date.now() < deadline) {
    active = document.querySelector('.vp-tabs__header-item--active');
    scroller = document.querySelector('.ai-draft__wrap-content');
    list = document.querySelector('.ai-draft__wrap-list');
    if ((active?.textContent || '').trim() === '文稿'
        && (list?.innerText || '').trim().length >= 200) break;
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  if (scroller) {
    scroller.scrollTop = 0;
    scroller.dispatchEvent(new Event('scroll', {bubbles: true}));
    const topDeadline = Date.now() + 3000;
    while (Date.now() < topDeadline && Math.abs(scroller.scrollTop) > 1) {
      scroller.scrollTop = 0;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
  }
  list = document.querySelector('.ai-draft__wrap-list');
  const paragraphs = list ? [...list.querySelectorAll('.ai-draft__p-paragraph')] : [];
  const sentences = list ? [...list.querySelectorAll('.ai-draft__p-sentence')] : [];
  const segments = [];
  const paragraphTexts = [];
  for (const [paragraphIndex, paragraph] of paragraphs.entries()) {
    const paragraphSegments = [...paragraph.querySelectorAll(
      '.ai-draft__p-sentence'
    )].map(node => {
      const rawIndex = node.getAttribute('data-index') || '';
      const index = /^\d+$/.test(rawIndex) ? Number(rawIndex) : null;
      const text = (node.textContent || '').trim();
      const row = {index, paragraph_index: paragraphIndex, text};
      segments.push(row);
      return row;
    });
    paragraphTexts.push(paragraphSegments.map(row => row.text).join(''));
  }
  const transcriptText = paragraphTexts.join('\n\n').trim();
  const first = sentences.at(0);
  const last = sentences.at(-1);
  const firstRect = first?.getBoundingClientRect();
  const lastRect = last?.getBoundingClientRect();
  const scrollerRect = scroller?.getBoundingClientRect();
  const listRect = list?.getBoundingClientRect();
  const markerNodes = list
    ? [...list.querySelectorAll(
        '[class*="virtual"], [class*="skeleton"], [class*="placeholder"], '
        + '[class*="loading"], [class*="load-more"]'
      )]
    : [];
  const markers = [...new Set(markerNodes.map(
    node => (node.className || '').toString()
  ).filter(Boolean))];
  const finalVideos = pauseVideos();
  return {
    url: location.href,
    target_bound: true,
    ad_overlays_dismissed,
    active: {
      matches: document.querySelectorAll('.vp-tabs__header-item--active').length,
      text: active?.textContent || ''
    },
    transcript: {text: transcriptText, segments},
    playback: {
      video_count: finalVideos.length,
      all_video_paused: finalVideos.length > 0
        && finalVideos.every(node => node.paused),
      pause_guard_installed: !!window.__xiaocaoNetdiskPauseGuardV1
    },
    render: {
      list_matches: document.querySelectorAll('.ai-draft__wrap-list').length,
      scroll_top: scroller?.scrollTop,
      client_height: scroller?.clientHeight,
      scroll_height: scroller?.scrollHeight,
      paragraph_count: paragraphs.length,
      sentence_count: sentences.length,
      segment_count: segments.length,
      segment_terminal_index: segments.at(-1)?.index,
      list_text_chars: transcriptText.length,
      sentence_text_chars: segments.reduce(
        (total, row) => total + row.text.length,
        0
      ),
      first_node_in_dom: !!first && document.contains(first),
      last_node_in_dom: !!last && document.contains(last),
      first_node_at_viewport_start: !!firstRect && !!scrollerRect
        && firstRect.top >= scrollerRect.top - 1
        && firstRect.top < scrollerRect.bottom,
      first_node_near_list_start: !!firstRect && !!listRect
        && firstRect.top >= listRect.top - 1
        && firstRect.top - listRect.top <= 256,
      last_node_below_viewport: !!lastRect && !!scrollerRect
        && lastRect.bottom > scrollerRect.bottom,
      last_node_near_list_end: !!lastRect && !!listRect
        && lastRect.bottom <= listRect.bottom + 1
        && listRect.bottom - lastRect.bottom <= 256,
      virtual_or_loading_markers: markers,
      has_load_more: /加载更多|正在加载|展开全部/.test(list?.innerText || '')
    }
  };
})()"""
_ACTIONS = {"upload", "transcript", "ai_note"}
_CAPABILITY_FAILURES = {
    "browser_security_policy_denied",
    "authentication_required",
    "captcha_required",
    "page_contract_changed",
}
_OPENCLI_UPLOAD_FAILURES = {
    "file_access_denied",
    "browser_command_failed",
    "file_chooser_not_opened",
}
_STATE_PREDECESSORS = {
    "transcript_requested": "transcript_claimed",
    "transcript_ready": "transcript_requested",
    "ai_note_requested": "ai_note_claimed",
    "ai_note_ready": "ai_note_requested",
}
_RECONCILIATION_PREDECESSORS = {
    "transcript_ready": {"video_ready", "transcript_claimed", "transcript_requested"},
    "ai_note_ready": {"transcript_ready", "ai_note_claimed", "ai_note_requested"},
}
_DIRECT_READY_PREDECESSORS = {
    "transcript_ready": "transcript_claimed",
    "ai_note_ready": "ai_note_claimed",
}
_STATE_ORDER = [
    "prepared",
    "upload_claimed",
    "video_ready",
    "transcript_claimed",
    "transcript_requested",
    "transcript_ready",
    "ai_note_claimed",
    "ai_note_pretrigger_failed",
    "ai_note_requested",
    "ai_note_ready",
    "transcript_captured",
    "verified",
    "decided",
]
_VISIBLE_STATE_MARKERS = {
    "video_ready": "video_present",
    "transcript_requested": "transcript_generating",
    "transcript_ready": "transcript_ready",
    "ai_note_requested": "ai_note_generating",
    "ai_note_ready": "ai_note_ready",
}
_PLAYER_STEPS = {
    "transcript_requested",
    "transcript_ready",
    "ai_note_requested",
    "ai_note_ready",
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
    "ai_note_requested": re.compile(
        r"AI\s*笔记.{0,24}(?:生成中|处理中|生成已提交)", re.IGNORECASE
    ),
    "ai_note_ready": re.compile(
        r"AI\s*笔记.{0,48}(?:已生成|生成完成|已完成|"
        r"content_chars=[1-9]\d{2,}.{0,32}export_available)",
        re.IGNORECASE,
    ),
}
_TRANSIENT_FAILURE_FIELDS = {
    "diagnostic",
    "cause_diagnostic",
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


def _sha256_handle(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    handle.seek(0)
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _clear_transient_failures(row: dict[str, Any]) -> None:
    for field in _TRANSIENT_FAILURE_FIELDS:
        row.pop(field, None)


def _opencli_diagnostic(error: EnrichmentDiagnosticError) -> dict[str, Any]:
    return {
        "category": error.diagnostic_category,
        "code": error.diagnostic_code,
        "stage": error.diagnostic_stage,
        "exit_code": error.diagnostic_exit_code,
    }


def _normalize_ordered_transcript_segments(
    value: Any,
) -> tuple[str, dict[str, Any]]:
    """Deduplicate and prove one complete, ordered provider segment sequence."""
    if not isinstance(value, list) or len(value) < 3:
        raise EnrichmentError("OpenCLI transcript segment evidence is incomplete")
    unique: dict[int, tuple[int, str]] = {}
    duplicate_count = 0
    observed_indices: list[int] = []
    for row in value:
        if not isinstance(row, dict):
            raise EnrichmentError("OpenCLI transcript segment evidence is invalid")
        index = row.get("index")
        paragraph_index = row.get("paragraph_index")
        text = row.get("text")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or isinstance(paragraph_index, bool)
            or not isinstance(paragraph_index, int)
            or paragraph_index < 0
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise EnrichmentError("OpenCLI transcript segment evidence is invalid")
        normalized = (paragraph_index, text.strip())
        observed_indices.append(index)
        prior = unique.get(index)
        if prior is not None:
            if prior != normalized:
                raise EnrichmentError(
                    "OpenCLI transcript has conflicting duplicate segments"
                )
            duplicate_count += 1
            continue
        unique[index] = normalized
    indices = sorted(unique)
    terminal_index = indices[-1]
    if indices != list(range(terminal_index + 1)):
        raise EnrichmentError("OpenCLI transcript terminal coverage is incomplete")
    paragraphs: list[list[str]] = []
    last_paragraph = -1
    ordered_rows: list[dict[str, Any]] = []
    for index in indices:
        paragraph_index, text = unique[index]
        if paragraph_index < last_paragraph or paragraph_index > last_paragraph + 1:
            raise EnrichmentError("OpenCLI transcript paragraph order is invalid")
        if paragraph_index == last_paragraph + 1:
            paragraphs.append([])
            last_paragraph = paragraph_index
        paragraphs[paragraph_index].append(text)
        ordered_rows.append({
            "index": index,
            "paragraph_index": paragraph_index,
            "text": text,
        })
    transcript = "\n\n".join("".join(parts) for parts in paragraphs).strip()
    if len(transcript) < 200:
        raise EnrichmentError("OpenCLI transcript segment evidence is incomplete")
    segment_bytes = json.dumps(
        ordered_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return transcript, {
        "segment_count": len(indices),
        "segment_first_index": indices[0],
        "segment_terminal_index": terminal_index,
        "duplicate_segment_count": duplicate_count,
        "ordered_by_index": True,
        "observed_order_was_monotonic": observed_indices == sorted(observed_indices),
        "paragraph_count": len(paragraphs),
        "segment_sequence_sha256": hashlib.sha256(segment_bytes).hexdigest(),
    }


class NetdiskEnrichmentService:
    """Record browser actions only when backed by real page/DOM evidence."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        runner: Callable[..., Any] = subprocess.run,
        now: Callable[[], datetime] | None = None,
        opencli_command: tuple[str, ...] | None = None,
        use_opencli_upload_template: bool = False,
        netdisk_directory: str = _NETDISK_DIRECTORY,
    ):
        self.store = EnrichmentJobStore(output_dir)
        self.output_dir = self.store.output_dir
        self.events_path = self.store.events_path
        self.runner = runner
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        directory = str(netdisk_directory or "").strip()
        if (
            not directory.startswith("/")
            or directory.endswith("/")
            and directory != "/"
            or "//" in directory
            or "?" in directory
            or "#" in directory
        ):
            raise EnrichmentError("Netdisk directory is invalid")
        self.netdisk_directory = directory
        self.use_opencli_upload_template = bool(use_opencli_upload_template)
        installed_opencli = shutil.which("opencli")
        self.opencli_command = opencli_command or (
            (installed_opencli,)
            if installed_opencli
            else ("npx", "--yes", "@jackwener/opencli@1.8.6")
        )

    def _netdisk_folder_url(self) -> str:
        return (
            "https://pan.baidu.com/disk/main#/index?category=all&path="
            + quote(self.netdisk_directory, safe="")
        )

    def _netdisk_path(self, target_name: str) -> str:
        name = str(target_name or "").strip()
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise EnrichmentError("Netdisk target basename is invalid")
        if self.netdisk_directory == "/":
            return f"/{name}"
        return f"{self.netdisk_directory}/{name}"

    def _time(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise EnrichmentError("enrichment clock must include a timezone")
        return value

    def _runtime_path(self, value: Path | str) -> Path:
        return resolve_repo_owned_path(value, anchor=self.output_dir)

    @staticmethod
    def _opencli_stage(args: tuple[str, ...]) -> str:
        operation = str(args[0] if args else "unknown").strip().lower()
        return {
            "bind": "browser_bind",
            "click": "browser_click",
            "eval": "browser_eval",
            "open": "browser_open",
            "wait": "browser_wait",
        }.get(operation, "browser_command")

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

    def _opencli_process(
        self,
        session: str,
        *args: str,
        profile: str | None = None,
        timeout_seconds: int = 30,
    ) -> Any:
        if not _OPENCLI_SESSION.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        if profile is not None and not _OPENCLI_PROFILE.fullmatch(profile):
            raise EnrichmentError("OpenCLI profile name is invalid")
        command = [
            *self.opencli_command,
            *(["--profile", profile] if profile else []),
            "browser",
            session,
            *args,
        ]
        runner_kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": timeout_seconds,
        }
        if timeout_seconds > 30:
            runner_kwargs["env"] = {
                **os.environ,
                "OPENCLI_BROWSER_COMMAND_TIMEOUT": str(
                    max(1, timeout_seconds - 10)
                ),
            }
        try:
            return self.runner(command, **runner_kwargs)
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentDiagnosticError(
                "OpenCLI browser command timed out",
                category="timeout",
                code="opencli_timeout",
                stage=self._opencli_stage(args),
            ) from exc

    def _run_opencli(
        self,
        session: str,
        *args: str,
        profile: str | None = None,
        timeout_seconds: int = 10,
        attempts: int = 3,
    ) -> Any:
        last_error: EnrichmentError | None = None
        for _attempt in range(attempts):
            try:
                result = self._opencli_process(
                    session,
                    *args,
                    profile=profile,
                    timeout_seconds=timeout_seconds,
                )
                if result.returncode != 0:
                    raise EnrichmentDiagnosticError(
                        "OpenCLI browser command failed",
                        category="transport_error",
                        code="opencli_command_failed",
                        stage=self._opencli_stage(args),
                        exit_code=int(result.returncode),
                    )
                return result
            except EnrichmentError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def _opencli_upload_template_process(
        self,
        *,
        session: str,
        profile: str | None,
        video_path: Path,
        target_name: str,
        claim_id: str,
        inspect_only: bool = False,
    ) -> Any:
        if session != _OPENCLI_UPLOAD_TEMPLATE_SESSION:
            raise EnrichmentError(
                "Baidu Netdisk upload template requires OpenCLI session "
                f"{_OPENCLI_UPLOAD_TEMPLATE_SESSION}"
            )
        command = [
            *self.opencli_command,
            *(["--profile", profile] if profile else []),
            "baidu-netdisk",
            "upload",
            "--file",
            str(video_path),
            "--directory",
            self.netdisk_directory,
            "--target-name",
            target_name,
            "--claim-id",
            claim_id,
            "--site-session",
            "persistent",
            "--keep-tab",
            "true",
            "--window",
            "foreground",
            "--format",
            "json",
            *(["--inspect-only", "true"] if inspect_only else []),
        ]
        try:
            return self.runner(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_OPENCLI_UPLOAD_TIMEOUT_SECONDS,
                env={
                    **os.environ,
                    "OPENCLI_BROWSER_COMMAND_TIMEOUT": str(
                        _OPENCLI_UPLOAD_TIMEOUT_SECONDS - 10
                    ),
                },
            )
        except subprocess.TimeoutExpired as exc:
            raise EnrichmentError("OpenCLI upload template timed out") from exc

    @staticmethod
    def _validate_opencli_upload_template_receipt(
        result: Any,
        *,
        target_name: str,
        directory: str,
        claim_id: str,
    ) -> dict[str, Any]:
        if result.returncode != 0:
            diagnostic = f"{result.stdout}\n{result.stderr}".lower()
            if "page.filechooseropened not received within 5s" in diagnostic:
                raise EnrichmentDiagnosticError(
                    "OpenCLI file chooser did not open; no file attachment occurred",
                    category="transport_error",
                    code="file_chooser_not_opened",
                    stage="upload_before_attachment",
                    exit_code=int(result.returncode),
                )
            if "not allowed" in diagnostic or "file access" in diagnostic:
                raise EnrichmentError(
                    "OpenCLI local file access denied; enable "
                    "Allow access to file URLs for the OpenCLI extension"
                )
            raise EnrichmentError("OpenCLI Baidu Netdisk upload template failed")
        try:
            rows = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template returned invalid JSON"
            ) from exc
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template returned an invalid receipt"
            )
        row = rows[0]
        status = row.get("status")
        if status not in {"upload_submitted", "already_present"}:
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template status is invalid"
            )
        if (
            row.get("directory") != directory
            or row.get("targetName") != target_name
            or row.get("claimId") != claim_id
        ):
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template receipt identity mismatch"
            )
        if status == "upload_submitted" and (
            row.get("exactCountBefore") != 0
            or row.get("uploaded") is not True
            or not str(row.get("uploadTarget") or "").startswith("input[")
        ):
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template did not prove one submission"
            )
        if status == "already_present" and (
            row.get("exactCountBefore") != 1
            or row.get("uploaded") is not False
        ):
            raise EnrichmentError(
                "OpenCLI Baidu Netdisk upload template existing-file proof is invalid"
            )
        return row

    def _opencli_json(
        self,
        session: str,
        *args: str,
        profile: str | None = None,
        timeout_seconds: int = 10,
        attempts: int = 3,
    ) -> dict[str, Any]:
        result = self._run_opencli(
            session,
            *args,
            profile=profile,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
        )
        try:
            payload = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            raise EnrichmentDiagnosticError(
                "OpenCLI returned invalid JSON",
                category="protocol_error",
                code="opencli_invalid_json",
                stage=self._opencli_stage(args),
            ) from exc
        if not isinstance(payload, dict):
            raise EnrichmentDiagnosticError(
                "OpenCLI returned a non-object result",
                category="protocol_error",
                code="opencli_non_object",
                stage=self._opencli_stage(args),
            )
        return payload

    def _bind_opencli(
        self,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, str]:
        bound = self._opencli_json(
            session,
            "bind",
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        if bound.get("session") != session:
            raise EnrichmentError(
                "OpenCLI bootstrap did not bind the requested session"
            )
        return {"status": "bound", "session": session}

    def _opencli_template_json(
        self,
        session: str,
        template_name: str,
        *,
        expected_path: str,
        profile: str | None,
    ) -> dict[str, Any]:
        script = render_netdisk_opencli_template(
            template_name,
            expected_path=expected_path,
        )
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        expected_name = f"baidu-netdisk/{template_name.replace('_', '-')}"
        if (
            payload.get("template_name") != expected_name
            or payload.get("template_version")
            != NETDISK_OPENCLI_TEMPLATE_VERSION
        ):
            raise EnrichmentError("Netdisk OpenCLI template contract mismatch")
        return payload

    @staticmethod
    def _browser_proof(
        *,
        target_name: str,
        visible_state: str,
        state_text: str,
        observed_at: datetime,
        page_url: str,
    ) -> dict[str, str]:
        snapshot_text = f"{target_name}\n{state_text}"
        return {
            "page_url": page_url,
            "target_name": target_name,
            "visible_state": visible_state,
            "snapshot_text": snapshot_text,
            "target_region_text": snapshot_text,
            "snapshot_sha256": hashlib.sha256(
                snapshot_text.encode("utf-8")
            ).hexdigest(),
            "observed_at": observed_at.isoformat(timespec="microseconds"),
        }

    def _inspect_opencli_target(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> dict[str, Any]:
        script = """(async () => {
  const dir = %s;
  const target = %s;
  const currentUrl = new URL(location.href);
  const hashQuery = currentUrl.hash.includes('?')
    ? currentUrl.hash.slice(currentUrl.hash.indexOf('?') + 1)
    : '';
  const currentDir = new URLSearchParams(hashQuery).get('path');
  const folderBound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/disk/main'
    && currentDir === dir;
  if (!folderBound) {
    return {
      page_url: location.origin + location.pathname,
      errno: 0,
      exact_count: 0,
      target_name: target,
      target_index: -1,
      pages_scanned: 0,
      complete_scan: false,
      folder_bound: false
    };
  }
  const visible = node => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden'
      && Number(style.opacity) !== 0;
  };
  const adPattern = /广告|运营图片|限时特惠|下载客户端|开通\\s*(?:SVIP|超级会员)|SVIP\\s*(?:活动|特惠|优惠)/i;
  const overlaySelector = [
    '.nd-operate-guidance',
    '[role="dialog"]',
    '[class*="modal"]',
    '[class*="popup"]',
    '[class*="advert"]',
    '[class*="promotion"]',
    '[class*="pay-revolution"]',
    '[class*="vip-dialog"]'
  ].join(',');
  let adOverlaysDismissed = 0;
  for (const overlay of [...document.querySelectorAll(overlaySelector)]) {
    const text = (overlay.innerText || '').trim();
    const imageLabels = [...overlay.querySelectorAll('img')].map(
      node => `${node.getAttribute('alt') || ''} ${node.className || ''}`
    ).join(' ');
    const identity = `${overlay.className || ''} ${text} ${imageLabels}`;
    if (!visible(overlay) || !adPattern.test(identity)) continue;
    const close = [...overlay.querySelectorAll(
      'button,[role="button"],[aria-label],[title],[class*="close"],img[alt="close"]'
    )].find(node => {
      const label = `${node.getAttribute('aria-label') || ''} `
        + `${node.getAttribute('title') || ''} `
        + `${node.getAttribute('alt') || ''} `
        + `${node.className || ''} ${(node.textContent || '').trim()}`;
      return visible(node) && /关闭|close|×|^x$/i.test(label);
    });
    if (close) {
      close.click();
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (document.contains(overlay) && visible(overlay)) {
      overlay.style.setProperty('display', 'none', 'important');
      overlay.setAttribute('aria-hidden', 'true');
    }
    adOverlaysDismissed += 1;
  }
  const pageSize = 1000;
  const maxPages = 100;
  let page = 1;
  let errno = 0;
  let exactCount = 0;
  let targetIndex = -1;
  let scanned = 0;
  let completeScan = false;
  while (page <= maxPages) {
    const url = '/api/list?clienttype=0&app_id=250528&web=1'
      + '&order=name&desc=1&dir=' + encodeURIComponent(dir)
      + '&num=' + pageSize + '&page=' + page;
    const response = await fetch(url, {credentials: 'include'});
    const body = await response.json();
    errno = body.errno;
    if (errno !== 0) break;
    const items = body.list || [];
    items.forEach((item, index) => {
      if (item.server_filename === target) {
        exactCount += 1;
        if (targetIndex < 0) targetIndex = scanned + index;
      }
    });
    scanned += items.length;
    const hasMore = body.has_more === 1 || body.has_more === true;
    if (!hasMore && items.length < pageSize) {
      completeScan = true;
      break;
    }
    if (items.length === 0) {
      completeScan = true;
      break;
    }
    page += 1;
  }
  return {
    page_url: location.origin + location.pathname,
    errno,
    exact_count: exactCount,
    target_name: target,
    target_index: targetIndex,
    pages_scanned: page,
    complete_scan: completeScan,
    folder_bound: true,
    ad_overlays_dismissed: adOverlaysDismissed
  };
})()""" % (json.dumps(self.netdisk_directory), json.dumps(target_name))
        payload: dict[str, Any] = {}
        for ready_attempt in range(_OPENCLI_FOLDER_READY_ATTEMPTS):
            self._opencli_json(
                session,
                "open",
                self._netdisk_folder_url(),
                profile=profile,
                timeout_seconds=30,
            )
            payload = self._opencli_json(
                session,
                "eval",
                script,
                profile=profile,
                timeout_seconds=30,
                attempts=3,
            )
            if (
                payload.get("folder_bound") is True
                and payload.get("errno") == 0
                and payload.get("complete_scan") is True
            ):
                break
            if ready_attempt + 1 < _OPENCLI_FOLDER_READY_ATTEMPTS:
                self._opencli_json(
                    session,
                    "wait",
                    "time",
                    str(_OPENCLI_FOLDER_READY_WAIT_SECONDS),
                    profile=profile,
                    timeout_seconds=10,
                    attempts=1,
                )
        if payload.get("errno") != 0:
            raise EnrichmentError("Netdisk file-list API inspection failed")
        if payload.get("target_name") != target_name:
            raise EnrichmentError("Netdisk target inspection was not exact")
        if payload.get("folder_bound") is not True:
            raise EnrichmentError("OpenCLI is not in the prepared Netdisk folder")
        if payload.get("complete_scan") is not True:
            raise EnrichmentError("Netdisk target inspection did not scan the full folder")
        try:
            exact_count = int(payload.get("exact_count"))
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("Netdisk target inspection count is invalid") from exc
        if exact_count not in {0, 1}:
            raise EnrichmentError("Netdisk target name is ambiguous")
        try:
            target_index = int(payload.get("target_index", -1))
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("Netdisk target inspection index is invalid") from exc
        if exact_count == 1 and target_index < 0:
            target_index = 0
        return {
            "exact_count": exact_count,
            "target_index": target_index,
            "observed_at": self._time(),
        }

    def _assert_opencli_folder(
        self,
        *,
        session: str,
        profile: str | None,
    ) -> None:
        script = """(() => {
  const expectedDir = %s;
  const currentUrl = new URL(location.href);
  const hashQuery = currentUrl.hash.includes('?')
    ? currentUrl.hash.slice(currentUrl.hash.indexOf('?') + 1)
    : '';
  const currentDir = new URLSearchParams(hashQuery).get('path');
  return {
    folder_bound: currentUrl.origin === 'https://pan.baidu.com'
      && currentUrl.pathname === '/disk/main'
      && currentDir === expectedDir
  };
})()""" % json.dumps(self.netdisk_directory)
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        if payload.get("folder_bound") is not True:
            raise EnrichmentError("OpenCLI is not in the prepared Netdisk folder")

    def _mark_opencli_upload_input(
        self,
        *,
        session: str,
        profile: str | None,
        marker: str,
    ) -> str:
        script = """(() => {
  const expectedDir = %s;
  const marker = %s;
  const folderBound = () => {
    const currentUrl = new URL(location.href);
    const hashQuery = currentUrl.hash.includes('?')
      ? currentUrl.hash.slice(currentUrl.hash.indexOf('?') + 1)
      : '';
    return currentUrl.origin === 'https://pan.baidu.com'
      && currentUrl.pathname === '/disk/main'
      && new URLSearchParams(hashQuery).get('path') === expectedDir;
  };
  if (!folderBound()) return {marked: false, reason: 'wrong_folder'};
  const inputs = [...document.querySelectorAll(
    'input[type="file"][title="点击选择文件"][accept="*/*"]'
  )].filter(input => !input.hasAttribute('webkitdirectory'));
  if (inputs.length < 1) return {marked: false, reason: 'input_missing'};
  const input = inputs[0];
  input.setAttribute('data-xiaocao-upload-marker', marker);
  const blockWrongFolder = event => {
    if (folderBound()) return;
    input.value = '';
    event.stopImmediatePropagation();
  };
  input.addEventListener('input', blockWrongFolder, {capture: true, once: true});
  input.addEventListener('change', blockWrongFolder, {capture: true, once: true});
  window.addEventListener('hashchange', () => {
    input.removeAttribute('data-xiaocao-upload-marker');
    input.value = '';
  }, {once: true});
  return {marked: true, matches: 1};
})()""" % (json.dumps(self.netdisk_directory), json.dumps(marker))
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        if payload.get("marked") is not True or payload.get("matches") != 1:
            raise EnrichmentError("OpenCLI upload input could not be bound to the folder")
        return f'input[data-xiaocao-upload-marker="{marker}"]'

    def _record_opencli_liveness(
        self,
        job_id: str,
        *,
        target_name: str,
        target_present: bool,
        observed_at: datetime,
    ) -> dict[str, Any]:
        snapshot_text = (
            "https://pan.baidu.com/disk/main|"
            f"{self.netdisk_directory}|opencli|target_"
            f"{'present' if target_present else 'absent'}:{target_name}"
        )
        return self.record_browser_liveness(
            job_id,
            surface="opencli",
            evidence={
                "page_url": "https://pan.baidu.com/disk/main",
                "snapshot_text": snapshot_text,
                "snapshot_sha256": hashlib.sha256(
                    snapshot_text.encode("utf-8")
                ).hexdigest(),
                "observed_at": observed_at.isoformat(timespec="microseconds"),
            },
        )

    def _record_opencli_upload_failure(
        self,
        job_id: str,
        *,
        reason: object,
    ) -> None:
        safe_reason = (
            reason
            if isinstance(reason, str) and reason in _OPENCLI_UPLOAD_FAILURES
            else "browser_command_failed"
        )
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") != "upload_claimed":
                return
            self.store.append({
                **current,
                "event": "netdisk_upload_failed",
                "status": "upload_claimed",
                "failure_stage": (
                    "upload_before_attachment"
                    if safe_reason == "file_chooser_not_opened" else "opencli_cdp"
                ),
                "reason": safe_reason,
                "error_type": "EnrichmentError",
                "updated_at": self._time().isoformat(timespec="microseconds"),
            })

    def _submit_opencli_upload(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        current = self.store.latest(job_id)
        video_path = Path(str(current["video_path"])).expanduser().resolve()
        self._assert_opencli_folder(session=session, profile=profile)
        try:
            source = video_path.open("rb")
        except OSError as exc:
            raise EnrichmentError("prepared upload source is unavailable") from exc
        with source:
            source_stat = os.fstat(source.fileno())
            if (
                source_stat.st_size != current.get("video_size_bytes")
                or _sha256_handle(source) != current.get("video_sha256")
            ):
                raise EnrichmentError("prepared upload source changed")
            if self.use_opencli_upload_template:
                try:
                    result = self._opencli_upload_template_process(
                        session=session,
                        profile=profile,
                        video_path=video_path,
                        target_name=str(current["video_basename"]),
                        claim_id=job_id,
                    )
                    receipt = self._validate_opencli_upload_template_receipt(
                        result,
                        target_name=str(current["video_basename"]),
                        directory=self.netdisk_directory,
                        claim_id=job_id,
                    )
                except EnrichmentError as exc:
                    self._record_opencli_upload_failure(
                        job_id,
                        reason=(
                            "file_chooser_not_opened"
                            if getattr(exc, "diagnostic_code", "") == "file_chooser_not_opened"
                            else "file_access_denied"
                            if "file access denied" in str(exc).lower()
                            else "browser_command_failed"
                        ),
                    )
                    raise
                if receipt["status"] == "already_present":
                    observed_at = self._time()
                    return self.record_browser_state(
                        job_id,
                        step="video_ready",
                        evidence=self._browser_proof(
                            target_name=str(current["video_basename"]),
                            visible_state="video_present",
                            state_text="目标视频 row 已存在",
                            observed_at=observed_at,
                            page_url="https://pan.baidu.com/disk/main",
                        ),
                        source_mode="existing",
                    )
                transport = "opencli_template"
            else:
                marker = secrets.token_urlsafe(18)
                selector = self._mark_opencli_upload_input(
                    session=session,
                    profile=profile,
                    marker=marker,
                )
                try:
                    result = self._opencli_process(
                        session,
                        "upload",
                        selector,
                        str(video_path),
                        "--nth",
                        "0",
                        profile=profile,
                        timeout_seconds=_OPENCLI_UPLOAD_TIMEOUT_SECONDS,
                    )
                except EnrichmentError:
                    self._record_opencli_upload_failure(
                        job_id,
                        reason="browser_command_failed",
                    )
                    raise
                if result.returncode != 0:
                    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
                    if "not allowed" in diagnostic:
                        self._record_opencli_upload_failure(
                            job_id,
                            reason="file_access_denied",
                        )
                        raise EnrichmentError(
                            "OpenCLI local file access denied; enable "
                            "Allow access to file URLs for the OpenCLI extension"
                        )
                    self._record_opencli_upload_failure(
                        job_id,
                        reason="browser_command_failed",
                    )
                    raise EnrichmentError("OpenCLI file upload failed")
                transport = "opencli_cdp"
        with self.store.job_lock(job_id):
            latest = self.store.latest(job_id)
            if latest.get("status") != "upload_claimed":
                raise EnrichmentError("upload submission lost its durable claim")
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **latest,
                "event": "netdisk_upload_started",
                "upload_transport": transport,
                "upload_started_at": now,
                "updated_at": now,
            }
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def _player_url(self, target_name: str) -> str:
        path = self._netdisk_path(target_name)
        return f"https://pan.baidu.com/pfile/video?path={quote(path, safe='')}"

    def _validate_player_url(self, page_url: str, *, target_name: str) -> str:
        parsed = urlsplit(page_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        netdisk_paths = query.get("path") or []
        expected_path = self._netdisk_path(target_name)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "pan.baidu.com"
            or parsed.path != "/pfile/video"
            or parsed.username is not None
            or parsed.password is not None
            or len(netdisk_paths) != 1
            or netdisk_paths[0] != expected_path
        ):
            raise EnrichmentDiagnosticError(
                "OpenCLI player does not match the prepared Netdisk path",
                category="identity_mismatch",
                code="target_url_mismatch",
                stage="player_binding",
            )
        return page_url

    def _find_opencli_player_page(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> str | None:
        for row in self._opencli_tab_list(session=session, profile=profile):
            page = row.get("page")
            url = row.get("url")
            if not isinstance(url, str):
                continue
            try:
                self._validate_player_url(url, target_name=target_name)
            except EnrichmentError:
                continue
            if not isinstance(page, str) or not page.strip():
                raise EnrichmentError("OpenCLI did not return the exact player tab identity")
            return page
        return None

    def _open_opencli_player_receipt(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> dict[str, Any]:
        page = self._find_opencli_player_page(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        open_error: EnrichmentDiagnosticError | None = None
        try:
            if page is None:
                try:
                    opened = self._opencli_json(
                        session,
                        "open",
                        self._player_url(target_name),
                        profile=profile,
                        timeout_seconds=30,
                        attempts=1,
                    )
                    page = opened.get("page")
                except EnrichmentDiagnosticError as exc:
                    if not (
                        exc.diagnostic_code == "opencli_timeout"
                        and exc.diagnostic_stage == "browser_open"
                    ):
                        raise
                    # Navigation may have completed despite a lost open receipt.
                    # Reconcile once by full path; never repeat that navigation.
                    open_error = exc
                    page = self._find_opencli_player_page(
                        session=session,
                        profile=profile,
                        target_name=target_name,
                    )
                    if page is None:
                        raise
            if not isinstance(page, str) or not page.strip():
                raise EnrichmentError("OpenCLI did not return the exact player tab identity")
            selected = self._opencli_json(
                session,
                "tab", "select", page, "--window", "foreground",
                profile=profile,
                timeout_seconds=10,
                attempts=1,
            )
            if selected.get("selected") != page:
                raise EnrichmentDiagnosticError(
                    "OpenCLI did not select the exact player tab",
                    category="provider_contract_error",
                    code="opencli_tab_activation_failed",
                    stage="player_binding",
                )
            observed = self._opencli_json(
                session,
                "eval",
                "(() => ({current_url: location.href}))()",
                profile=profile,
                timeout_seconds=10,
                attempts=2,
            )
            actual_url = observed.get("current_url")
            if not isinstance(actual_url, str):
                raise EnrichmentError("OpenCLI did not return the current player URL")
            validated_url = self._validate_player_url(
                actual_url,
                target_name=target_name,
            )
            pause_receipt = self._opencli_json(
                session,
                "eval",
                _OPENCLI_PLAYER_PAUSE_GUARD.replace(
                    "__EXPECTED_NETDISK_PATH__",
                    json.dumps(self._netdisk_path(target_name)),
                ),
                profile=profile,
                timeout_seconds=20,
                attempts=1,
            )
            if (
                pause_receipt.get("target_bound") is not True
                or pause_receipt.get("pause_guard_installed") is not True
                or not isinstance(pause_receipt.get("video_count"), int)
                or pause_receipt["video_count"] < 1
                or pause_receipt.get("all_video_paused") is not True
            ):
                raise EnrichmentDiagnosticError(
                    "Netdisk player video is not proven paused",
                    category="provider_contract_error",
                    code="player_not_paused",
                    stage="player_pause",
                )
        except EnrichmentError as exc:
            if open_error is not None and exc is not open_error:
                raise exc from open_error
            raise
        return {
            "player_url": validated_url,
            "page": page,
            "recovered_from": _opencli_diagnostic(open_error) if open_error else None,
            "pause_receipt": {
                "video_count": pause_receipt["video_count"],
                "playing_before_pause": int(
                    pause_receipt.get("playing_before_pause") or 0
                ),
                "all_video_paused": True,
                "pause_guard_installed": True,
            },
        }

    def _open_opencli_player(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> str:
        receipt = self._open_opencli_player_receipt(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        return str(receipt["player_url"])

    def _opencli_tab_list(
        self,
        *,
        session: str,
        profile: str | None,
        attempts: int = 1,
    ) -> list[dict[str, Any]]:
        result = self._run_opencli(
            session,
            "tab",
            "list",
            profile=profile,
            timeout_seconds=30,
            attempts=attempts,
        )
        try:
            payload = json.loads(str(result.stdout))
        except (TypeError, json.JSONDecodeError) as exc:
            raise EnrichmentError("OpenCLI returned an invalid tab list") from exc
        if not isinstance(payload, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("page"), str)
            or not row["page"].strip()
            or not isinstance(row.get("url"), str)
            or not row["url"].strip()
            for row in payload
        ):
            raise EnrichmentError("OpenCLI returned an invalid tab list")
        return payload

    def _close_opencli_player(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
        page: str,
    ) -> dict[str, Any]:
        if not page.strip():
            raise EnrichmentError("OpenCLI player tab identity is invalid")
        closed_pages: list[str] = []
        rows = self._opencli_tab_list(session=session, profile=profile, attempts=2)
        # Reconcile before each close: a saved page ID can now be absent or
        # point elsewhere. Never close an unrelated tab or repeat a close.
        for _attempt in range(17):
            exact_matches: list[str] = []
            for row in rows:
                row_url = row.get("url")
                if not isinstance(row_url, str):
                    continue
                try:
                    self._validate_player_url(row_url, target_name=target_name)
                except EnrichmentError:
                    continue
                row_page = row.get("page")
                if not isinstance(row_page, str) or not row_page.strip():
                    raise EnrichmentError("OpenCLI did not return the exact player tab identity")
                exact_matches.append(row_page)
            if not exact_matches:
                return {
                    "capture_page": page,
                    "closed_page": closed_pages[0] if closed_pages else None,
                    "closed_pages": closed_pages,
                    "exact_player_absent": True,
                }
            if _attempt == 16:
                break
            target_page = page if page in exact_matches else exact_matches[0]
            if target_page in closed_pages:
                raise EnrichmentError("Exact Netdisk player tab remains open")
            close_error: EnrichmentError | None = None
            try:
                result = self._opencli_json(
                    session,
                    "tab",
                    "close",
                    target_page,
                    profile=profile,
                    timeout_seconds=30,
                    attempts=1,
                )
            except EnrichmentError as exc:
                close_error = exc
            else:
                if result.get("closed") != target_page:
                    close_error = EnrichmentError(
                        "OpenCLI did not confirm the exact player tab close"
                    )
            try:
                rows = self._opencli_tab_list(session=session, profile=profile, attempts=2)
            except EnrichmentError as exc:
                if close_error is not None:
                    raise exc from close_error
                raise
            if any(row.get("page") == target_page for row in rows):
                if close_error is not None:
                    raise close_error
                raise EnrichmentError("Exact Netdisk player tab remains open")
            closed_pages.append(target_page)
        raise EnrichmentError("Netdisk player close exceeded its bounded tab limit")

    def _select_opencli_tab(
        self,
        *,
        session: str,
        profile: str | None,
        label: str,
        target_name: str,
    ) -> None:
        script = """(async () => {
  const label = %s;
  const expectedPath = %s;
  const currentUrl = new URL(location.href);
  const targetBound = currentUrl.origin === 'https://pan.baidu.com'
    && currentUrl.pathname === '/pfile/video'
    && currentUrl.searchParams.getAll('path').length === 1
    && currentUrl.searchParams.get('path') === expectedPath;
  if (!targetBound) {
    return {scheduled: false, tab: label, matches: 0, target_bound: false};
  }
  const deadline = Date.now() + 10000;
  let matches = [];
  while (Date.now() < deadline) {
    const tabs = [...document.querySelectorAll('.vp-tabs__header-item')];
    matches = tabs.filter(node => {
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return (node.textContent || '').trim() === label
        && rect.width > 0
        && rect.height > 0
        && style.display !== 'none'
        && style.visibility !== 'hidden';
    });
    if (matches.length === 1) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (matches.length !== 1) {
    return {scheduled: false, tab: label, matches: matches.length};
  }
  if (matches[0].classList.contains('vp-tabs__header-item--active')) {
    return {scheduled: false, already_active: true, tab: label, matches: 1};
  }
  setTimeout(() => matches[0].click(), 0);
  return {scheduled: true, tab: label, matches: 1};
})()""" % (
            json.dumps(label),
            json.dumps(self._netdisk_path(target_name)),
        )
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        if payload.get("target_bound") is False:
            raise EnrichmentError("OpenCLI player path changed before tab activation")
        if payload.get("matches") != 1:
            raise EnrichmentError(f"Netdisk {label} tab was not uniquely located")

    def _wait_opencli_active_tab(
        self,
        *,
        session: str,
        profile: str | None,
        label: str,
        target_name: str,
    ) -> None:
        script = """(async () => {
  const expected_tab = %s;
  const expectedPath = %s;
  const deadline = Date.now() + 10000;
  let active_tab = '';
  let target_bound = false;
  while (Date.now() < deadline) {
    const currentUrl = new URL(location.href);
    target_bound = currentUrl.origin === 'https://pan.baidu.com'
      && currentUrl.pathname === '/pfile/video'
      && currentUrl.searchParams.getAll('path').length === 1
      && currentUrl.searchParams.get('path') === expectedPath;
    if (!target_bound) break;
    const videos = [...document.querySelectorAll('video')];
    videos.forEach(node => {
      node.autoplay = false;
      node.removeAttribute('autoplay');
      if (!node.paused) node.pause();
    });
    const active = document.querySelector('.vp-tabs__header-item--active');
    active_tab = (active?.textContent || '').trim();
    if (active_tab === expected_tab) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  const finalVideos = [...document.querySelectorAll('video')];
  finalVideos.forEach(node => {
    if (!node.paused) node.pause();
  });
  return {
    active_tab,
    expected_tab,
    target_bound,
    video_count: finalVideos.length,
    all_video_paused: finalVideos.length > 0
      && finalVideos.every(node => node.paused),
    pause_guard_installed: !!window.__xiaocaoNetdiskPauseGuardV1
  };
})()""" % (
            json.dumps(label),
            json.dumps(self._netdisk_path(target_name)),
        )
        payload = self._opencli_json(
            session,
            "eval",
            script,
            profile=profile,
            timeout_seconds=30,
            attempts=1,
        )
        if payload.get("target_bound") is not True:
            raise EnrichmentError("OpenCLI player path changed while activating tab")
        if payload.get("active_tab") != label:
            raise EnrichmentError(f"Netdisk {label} tab did not become active")
        if (
            not isinstance(payload.get("video_count"), int)
            or payload["video_count"] < 1
            or payload.get("all_video_paused") is not True
            or payload.get("pause_guard_installed") is not True
        ):
            raise EnrichmentError(
                f"Netdisk {label} tab did not preserve paused playback"
            )

    def _probe_opencli_transcript(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> dict[str, Any]:
        payload = self._opencli_template_json(
            session,
            "probe_transcript",
            expected_path=self._netdisk_path(target_name),
            profile=profile,
        )
        if payload.get("target_bound") is not True:
            raise EnrichmentError("OpenCLI player path changed during transcript probe")
        if payload.get("active_tab") != "文稿":
            raise EnrichmentError("Netdisk transcript tab did not become active")
        state = payload.get("transcript_state")
        if state not in {"missing", "generating", "ready"}:
            raise EnrichmentError("Netdisk transcript state is invalid")
        if state == "ready":
            try:
                content_chars = int(payload.get("content_chars"))
            except (TypeError, ValueError) as exc:
                raise EnrichmentError("Netdisk transcript length is invalid") from exc
            if content_chars < 200 or payload.get("export_available") is not True:
                raise EnrichmentError("Netdisk transcript ready proof is incomplete")
        return payload

    def _record_opencli_still_generating(
        self,
        job_id: str,
        *,
        kind: str,
        target_name: str,
        page_url: str,
    ) -> dict[str, Any]:
        if kind not in {"transcript", "ai_note"}:
            raise EnrichmentError("unsupported Netdisk generation kind")
        step = f"{kind}_requested"
        visible_state = f"{kind}_generating"
        label = "文稿" if kind == "transcript" else "AI笔记"
        observed_at = self._time()
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") != step:
                raise EnrichmentError("generation poll lost its requested state")
            evidence = self._browser_proof(
                target_name=target_name,
                visible_state=visible_state,
                state_text=f"{label} 生成中",
                observed_at=observed_at,
                page_url=page_url,
            )
            normalized = self._browser_evidence(
                current,
                evidence,
                expected_target=target_name,
                step=step,
            )
            self._require_after_latest_capability_failure(
                job_id,
                observed_at=str(normalized["observed_at"]),
                evidence_kind=f"{step} browser evidence",
            )
            prior = current.get("browser_evidence")
            if isinstance(prior, dict):
                prior_at = self._event_time(
                    prior.get("observed_at"), field=f"{step} prior observed_at"
                )
                if observed_at.astimezone(timezone.utc) < prior_at:
                    raise EnrichmentError("generation poll predates prior evidence")
            next_poll = observed_at + _NETDISK_GENERATION_POLL_INTERVAL
            row = {
                **current,
                "event": f"netdisk_{kind}_still_generating",
                "browser_evidence": normalized,
                "next_poll_not_before": next_poll.isoformat(timespec="microseconds"),
                "updated_at": observed_at.isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {
                **row,
                "pending": True,
                "idempotent_replay": False,
            }

    def _advance_opencli_transcript(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        current = self.store.latest(job_id)
        status = str(current.get("status") or "")
        reconcile_claim = False
        readback_rebind_allowed = False
        if status == "video_ready":
            claim = self.claim_browser_action(job_id, action="transcript")
            if claim.get("idempotent_replay") is True:
                return {
                    **self.store.latest(job_id),
                    "pending": True,
                    "side_effect_uncertain": True,
                    "idempotent_replay": True,
                }
            readback_rebind_allowed = True
        elif status == "transcript_claimed":
            # The claim is an uncertain browser-side effect, so recovery may
            # only read the exact player state.  If the request was dispatched
            # before the process failed, this readback advances the durable
            # checkpoint without clicking generation again.
            reconcile_claim = True
            readback_rebind_allowed = True
        elif status == "transcript_requested":
            raw_not_before = current.get("next_poll_not_before")
            try:
                not_before = datetime.fromisoformat(str(raw_not_before or ""))
            except ValueError as exc:
                raise EnrichmentError("transcript poll checkpoint is invalid") from exc
            if not_before.tzinfo is None:
                raise EnrichmentError("transcript poll checkpoint needs a timezone")
            if self._time().astimezone(timezone.utc) < not_before.astimezone(timezone.utc):
                return {**current, "pending": True, "idempotent_replay": True}
            readback_rebind_allowed = True
        target_name = str(current["video_basename"])
        for attempt in range(2):
            try:
                player_url = self._open_opencli_player(
                    session=session,
                    profile=profile,
                    target_name=target_name,
                )
                self._select_opencli_tab(
                    session=session,
                    profile=profile,
                    label="文稿",
                    target_name=target_name,
                )
                self._wait_opencli_active_tab(
                    session=session,
                    profile=profile,
                    label="文稿",
                    target_name=target_name,
                )
                probe = self._probe_opencli_transcript(
                    session=session,
                    profile=profile,
                    target_name=target_name,
                )
                break
            except EnrichmentDiagnosticError as exc:
                if (
                    attempt == 0
                    and readback_rebind_allowed
                    and exc.diagnostic_code in _OPENCLI_READBACK_REBIND_CODES
                    and exc.diagnostic_stage in _OPENCLI_READBACK_REBIND_STAGES
                ):
                    self._bind_opencli(session=session, profile=profile)
                    continue
                raise
        observed_at = self._time()
        if probe["transcript_state"] == "generating":
            if status == "transcript_requested":
                return self._record_opencli_still_generating(
                    job_id,
                    kind="transcript",
                    target_name=target_name,
                    page_url=player_url,
                )
            return self.record_browser_state(
                job_id,
                step="transcript_requested",
                evidence=self._browser_proof(
                    target_name=target_name,
                    visible_state="transcript_generating",
                    state_text="文稿 生成中",
                    observed_at=observed_at,
                    page_url=player_url,
                ),
            )
        if probe["transcript_state"] == "ready":
            return self.record_browser_state(
                job_id,
                step="transcript_ready",
                evidence=self._browser_proof(
                    target_name=target_name,
                    visible_state="transcript_ready",
                    state_text=(
                        "文稿 已生成 "
                        f"content_chars={int(probe['content_chars'])} export_available"
                    ),
                    observed_at=observed_at,
                    page_url=player_url,
                ),
                reconcile_existing=reconcile_claim,
            )
        if reconcile_claim:
            return {
                **self.store.latest(job_id),
                "pending": True,
                "side_effect_uncertain": True,
                "idempotent_replay": True,
            }
        raise EnrichmentError("Netdisk transcript generation did not start")

    def _probe_opencli_ai_note(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> dict[str, Any]:
        payload = self._opencli_template_json(
            session,
            "probe_ai_note",
            expected_path=self._netdisk_path(target_name),
            profile=profile,
        )
        if payload.get("target_bound") is not True:
            raise EnrichmentError("OpenCLI player path changed during AI-note probe")
        if payload.get("active_tab") != "笔记":
            raise EnrichmentError("Netdisk AI-note tab did not become active")
        state = payload.get("ai_note_state")
        if state not in {"missing", "generating", "ready"}:
            raise EnrichmentError("Netdisk AI-note state is invalid")
        if state == "ready":
            try:
                content_chars = int(payload.get("content_chars"))
            except (TypeError, ValueError) as exc:
                raise EnrichmentError("Netdisk AI-note length is invalid") from exc
            if content_chars < 200:
                raise EnrichmentError("Netdisk AI-note ready proof is incomplete")
        return payload

    def _trigger_opencli_ai_note(
        self,
        *,
        session: str,
        profile: str | None,
        target_name: str,
    ) -> dict[str, Any]:
        expected_path = self._netdisk_path(target_name)
        preview = self._opencli_template_json(
            session,
            "prepare_ai_note",
            expected_path=expected_path,
            profile=profile,
        )
        if preview.get("target_bound") is False:
            raise EnrichmentError("OpenCLI player path changed before AI-note preview")
        if preview.get("scheduled") is not True:
            return {
                "submitted": False,
                "template_no": 1,
                "target_bound": preview.get("target_bound") is True,
                "button_matches": 0,
                "click_dispatched": False,
                "preflight_reason": "template_modal_not_ready",
            }
        if (
            preview.get("modal_ready") is not True
            or preview.get("template_matches") != 1
            or preview.get("template_selected") != "文稿笔记"
            or preview.get("button_matches") != 1
        ):
            return {
                "submitted": False,
                "template_no": 1,
                "target_bound": True,
                "button_matches": 0,
                "click_dispatched": False,
                "preflight_reason": "text_template_not_selected",
            }
        submitted = self._opencli_template_json(
            session,
            "submit_ai_note",
            expected_path=expected_path,
            profile=profile,
        )
        if submitted.get("target_bound") is False:
            raise EnrichmentError("OpenCLI player path changed before AI-note submission")
        if submitted.get("submitted") is not True:
            if submitted.get("click_dispatched") is True:
                return {
                    **submitted,
                    "submitted": True,
                    "confirmed_state": "dispatched",
                }
            return submitted
        if submitted.get("click_dispatched") is not True:
            raise EnrichmentError("Netdisk AI-note submission did not dispatch a click")
        return submitted

    def _record_ai_note_pretrigger_failure(
        self,
        job_id: str,
        *,
        trigger_proof: dict[str, Any],
    ) -> dict[str, Any]:
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") != "ai_note_claimed":
                raise EnrichmentError("AI-note pretrigger failure lost its durable claim")
            if trigger_proof.get("click_dispatched") is True:
                raise EnrichmentError(
                    "AI-note pretrigger recovery cannot accept a dispatched click"
                )
            if trigger_proof.get("submitted") is True:
                raise EnrichmentError(
                    "AI-note pretrigger recovery cannot accept a submitted request"
                )
            try:
                button_matches = int(trigger_proof.get("button_matches") or 0)
                template_no = int(trigger_proof.get("template_no") or 0)
            except (TypeError, ValueError) as exc:
                raise EnrichmentError("AI-note pretrigger proof is invalid") from exc
            if button_matches != 0 or template_no != 1:
                raise EnrichmentError("AI-note pretrigger proof is not retryable")
            attempt = int(current.get("ai_note_trigger_attempt") or 1)
            if attempt > _AI_NOTE_MAX_TRIGGER_ATTEMPTS:
                raise EnrichmentError("AI-note trigger attempt count is invalid")
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **current,
                "event": "netdisk_ai_note_pretrigger_failed",
                "status": "ai_note_pretrigger_failed",
                "ai_note_trigger_attempt": attempt,
                "ai_note_pretrigger_proof": {
                    "button_matches": button_matches,
                    "click_dispatched": False,
                    "template_no": template_no,
                    "target_bound": trigger_proof.get("target_bound") is True,
                },
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return row

    def _claim_ai_note_pretrigger_retry(self, job_id: str) -> dict[str, Any]:
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") != "ai_note_pretrigger_failed":
                raise EnrichmentError("AI-note pretrigger retry requires failed state")
            proof = current.get("ai_note_pretrigger_proof")
            if not isinstance(proof, dict) or proof.get("click_dispatched") is not False:
                raise EnrichmentError("AI-note pretrigger retry proof is missing")
            attempt = int(current.get("ai_note_trigger_attempt") or 0)
            if attempt >= _AI_NOTE_MAX_TRIGGER_ATTEMPTS:
                return {
                    **current,
                    "pending": True,
                    "retry_exhausted": True,
                    "idempotent_replay": True,
                }
            if not self._has_fresh_browser_control(current):
                self._record_rejection(
                    current,
                    operation="claim:ai_note_pretrigger_retry",
                    reason="browser_control_not_live",
                )
                raise EnrichmentError(
                    "ai_note retry requires fresh browser claim/DOM liveness evidence"
                )
            retry_of = str(current.get("claimed_at") or "")
            if not retry_of:
                raise EnrichmentError("AI-note pretrigger retry lost its original claim")
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **current,
                "event": "netdisk_ai_note_retry_claimed",
                "status": "ai_note_claimed",
                "claimed_at": now,
                "ai_note_trigger_attempt": attempt + 1,
                "ai_note_retry_of": retry_of,
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def _record_ai_note_triggered(
        self,
        job_id: str,
        *,
        target_name: str,
        page_url: str,
        trigger_proof: dict[str, Any],
    ) -> dict[str, Any]:
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") != "ai_note_claimed":
                raise EnrichmentError("AI-note trigger lost its durable claim")
            observed_at = self._time()
            confirmed_state = str(trigger_proof.get("confirmed_state") or "")
            if confirmed_state not in {"dispatched", "generating", "ready"}:
                raise EnrichmentError("AI-note trigger proof has no confirmed state")
            if confirmed_state == "ready":
                visible_state = "ai_note_ready"
                state_text = (
                    "AI笔记 已生成 "
                    f"content_chars={int(trigger_proof.get('content_chars') or 0)}"
                )
            elif confirmed_state == "generating":
                visible_state = "ai_note_generating"
                state_text = "AI笔记 生成中"
            else:
                visible_state = "ai_note_submission_dispatched"
                state_text = "AI笔记 生成已提交"
            normalized = self._browser_evidence(
                current,
                self._browser_proof(
                    target_name=target_name,
                    visible_state=visible_state,
                    state_text=state_text,
                    observed_at=observed_at,
                    page_url=page_url,
                ),
                expected_target=target_name,
                step="ai_note_requested",
            )
            self._require_after_latest_capability_failure(
                job_id,
                observed_at=str(normalized["observed_at"]),
                evidence_kind="ai_note_requested browser evidence",
            )
            self._require_transition_causality(
                current,
                step="ai_note_requested",
                observed_at=str(normalized["observed_at"]),
                reconcile_existing=False,
            )
            now = observed_at.isoformat(timespec="microseconds")
            row = {
                **current,
                "event": "netdisk_ai_note_triggered",
                "status": "ai_note_requested",
                "ai_note_template": "文稿笔记",
                "ai_note_template_no": 1,
                "ai_note_completion_required": False,
                "ai_note_triggered_at": now,
                "ai_note_submission_proof": {
                    "control_text": "生成该笔记",
                    "click_dispatched": trigger_proof.get("click_dispatched") is True,
                    "modal_visible": trigger_proof.get("modal_visible") is True,
                    "confirmed_state": confirmed_state,
                    "content_chars": int(trigger_proof.get("content_chars") or 0),
                    "reconciled_after_claim": (
                        trigger_proof.get("reconciled_after_claim") is True
                    ),
                },
                "browser_evidence": normalized,
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def _advance_opencli_ai_note(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None,
    ) -> dict[str, Any]:
        current = self.store.latest(job_id)
        status = str(current.get("status") or "")
        if status == "transcript_ready":
            claim = self.claim_browser_action(job_id, action="ai_note")
            if claim.get("idempotent_replay") is True:
                return {
                    **self.store.latest(job_id),
                    "pending": True,
                    "side_effect_uncertain": True,
                    "idempotent_replay": True,
                }
        elif status == "ai_note_pretrigger_failed":
            claim = self._claim_ai_note_pretrigger_retry(job_id)
            if claim.get("retry_exhausted") is True:
                return claim
        reconcile_claim = status == "ai_note_claimed"
        target_name = str(current["video_basename"])
        player_url = self._open_opencli_player(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        self._select_opencli_tab(
            session=session,
            profile=profile,
            label="笔记",
            target_name=target_name,
        )
        self._wait_opencli_active_tab(
            session=session,
            profile=profile,
            label="笔记",
            target_name=target_name,
        )
        self._run_opencli(
            session,
            "wait",
            "selector",
            "#noteIframe",
            "--timeout",
            "10000",
            profile=profile,
            timeout_seconds=20,
        )
        probe = self._probe_opencli_ai_note(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        observed_at = self._time()
        if probe["ai_note_state"] == "missing":
            if reconcile_claim:
                return {
                    **self.store.latest(job_id),
                    "pending": True,
                    "side_effect_uncertain": True,
                    "idempotent_replay": True,
                }
            latest = self.store.latest(job_id)
            if latest.get("ai_note_triggered_at"):
                return {**latest, "pending": True, "idempotent_replay": True}
            trigger_proof = self._trigger_opencli_ai_note(
                session=session,
                profile=profile,
                target_name=target_name,
            )
            if trigger_proof.get("submitted") is not True:
                self._record_ai_note_pretrigger_failure(
                    job_id,
                    trigger_proof=trigger_proof,
                )
                raise EnrichmentError("Netdisk AI-note template submission failed")
            return self._record_ai_note_triggered(
                job_id,
                target_name=target_name,
                page_url=player_url,
                trigger_proof=trigger_proof,
            )
        if reconcile_claim:
            return self._record_ai_note_triggered(
                job_id,
                target_name=target_name,
                page_url=player_url,
                trigger_proof={
                    "click_dispatched": False,
                    "modal_visible": False,
                    "confirmed_state": probe["ai_note_state"],
                    "content_chars": int(probe.get("content_chars") or 0),
                    "reconciled_after_claim": True,
                },
            )
        if probe["ai_note_state"] == "generating":
            return self.record_browser_state(
                job_id,
                step="ai_note_requested",
                evidence=self._browser_proof(
                    target_name=target_name,
                    visible_state="ai_note_generating",
                    state_text="AI笔记 生成中",
                    observed_at=observed_at,
                    page_url=player_url,
                ),
            )
        return self.record_browser_state(
            job_id,
            step="ai_note_ready",
            evidence=self._browser_proof(
                target_name=target_name,
                visible_state="ai_note_ready",
                state_text=(
                    "AI笔记 已生成 "
                    f"content_chars={int(probe['content_chars'])} export_available"
                ),
                observed_at=observed_at,
                page_url=player_url,
            ),
        )

    def advance_opencli(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Advance one durable Netdisk browser checkpoint without scheduling."""
        if not _OPENCLI_SESSION.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        if profile is not None and not _OPENCLI_PROFILE.fullmatch(profile):
            raise EnrichmentError("OpenCLI profile name is invalid")
        current = self.store.latest(job_id)
        status = str(current.get("status") or "")
        claimable_statuses = {
            "video_ready",
            "transcript_ready",
            "ai_note_pretrigger_failed",
        }
        if (
            status in claimable_statuses
            and not self._has_fresh_browser_control(current)
        ):
            target_name = str(current["video_basename"])
            inspection = self._inspect_opencli_target(
                session=session,
                profile=profile,
                target_name=target_name,
            )
            if inspection["exact_count"] != 1:
                raise EnrichmentError(
                    "remote handoff target is not exactly present in Netdisk"
                )
            self._record_opencli_liveness(
                job_id,
                target_name=target_name,
                target_present=True,
                observed_at=inspection["observed_at"],
            )
        if status in {
            "video_ready",
            "transcript_claimed",
            "transcript_requested",
        }:
            return self._advance_opencli_transcript(
                job_id,
                session=session,
                profile=profile,
            )
        if status in {
            "transcript_ready",
            "ai_note_pretrigger_failed",
        }:
            return self._advance_opencli_ai_note(
                job_id,
                session=session,
                profile=profile,
            )
        if status in {
            "ai_note_claimed",
            "ai_note_requested",
            "ai_note_ready",
            "transcript_captured",
        }:
            return self.capture_opencli_transcript(
                job_id,
                session=session,
                profile=profile,
            )
        if status not in {"prepared", "upload_claimed"}:
            raise EnrichmentError(f"OpenCLI advance does not support state {status} yet")
        target_name = str(current["video_basename"])
        inspection = self._inspect_opencli_target(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        present = inspection["exact_count"] == 1
        observed_at = inspection["observed_at"]
        if status == "prepared":
            self._record_opencli_liveness(
                job_id,
                target_name=target_name,
                target_present=present,
                observed_at=observed_at,
            )
            if present:
                return self.record_browser_state(
                    job_id,
                    step="video_ready",
                    evidence=self._browser_proof(
                        target_name=target_name,
                        visible_state="video_present",
                        state_text="目标视频 row 已存在",
                        observed_at=observed_at,
                        page_url="https://pan.baidu.com/disk/main",
                    ),
                    source_mode="existing",
                )
            claim = self.claim_browser_action(job_id, action="upload")
            if claim.get("idempotent_replay") is True:
                return {
                    **self.store.latest(job_id),
                    "pending": True,
                    "side_effect_uncertain": True,
                    "idempotent_replay": True,
                }
            return self._submit_opencli_upload(
                job_id,
                session=session,
                profile=profile,
            )
        if present:
            return self.record_browser_state(
                job_id,
                step="video_ready",
                evidence=self._browser_proof(
                    target_name=target_name,
                    visible_state="video_present",
                    state_text="上传完成 目标视频 row 可见",
                    observed_at=observed_at,
                    page_url="https://pan.baidu.com/disk/main",
                ),
                source_mode="uploaded",
            )
        if current.get("upload_started_at"):
            return {**current, "pending": True, "idempotent_replay": True}
        return {
            **current,
            "pending": True,
            "side_effect_uncertain": True,
            "idempotent_replay": True,
        }

    def resume_pre_attachment_upload(
        self, job_id: str, *, session: str, profile: str | None = None,
        file_access_restored: bool = False,
    ) -> dict[str, Any]:
        """One narrow repair after a proven chooser failure before file assignment.

        Never called by the ordinary sweep. Unknown failures remain uncertain;
        a repaired claim is durable before attachment and can never be replayed.
        """
        def eligible(row: dict[str, Any]) -> bool:
            chooser_failure = (
                row.get("reason") == "file_chooser_not_opened"
                and row.get("failure_stage") == "upload_before_attachment"
                and not row.get("upload_repair_attempts")
            )
            permission_restored = (
                file_access_restored is True
                and row.get("reason") == "file_access_denied"
                and not row.get("file_access_repair_claimed_at")
                and int(row.get("upload_repair_attempts") or 0) <= 1
            )
            return (
                self.use_opencli_upload_template
                and row.get("status") == "upload_claimed"
                and row.get("event") == "netdisk_upload_failed"
                and not row.get("upload_started_at")
                and (chooser_failure or permission_restored)
            )

        if session != _OPENCLI_UPLOAD_TEMPLATE_SESSION or (
            profile is not None and not _OPENCLI_PROFILE.fullmatch(profile)
        ):
            raise EnrichmentError("pre-attachment repair requires the existing upload session")
        current = self.store.latest(job_id)
        if not eligible(current):
            raise EnrichmentError("upload has no eligible proven pre-attachment failure")
        inspection = self._inspect_opencli_target(
            session=session, profile=profile, target_name=str(current["video_basename"]),
        )
        if inspection["exact_count"] == 1:
            return self.advance_opencli(job_id, session=session, profile=profile)
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if not eligible(current):
                raise EnrichmentError("upload has no eligible proven pre-attachment failure")
            now = self._time().isoformat(timespec="microseconds")
            permission_repair = current.get("reason") == "file_access_denied"
            self.store.append({
                **current,
                "event": "netdisk_upload_repair_claimed",
                "upload_repair_attempts": int(current.get("upload_repair_attempts") or 0) + 1,
                "repair_basis": (
                    "user_restored_file_access" if permission_repair
                    else "file_chooser_failed_before_file_assignment"
                ),
                **({"file_access_repair_claimed_at": now} if permission_repair else {}),
                "repair_claimed_at": now,
                "updated_at": now,
            })
        return self._submit_opencli_upload(job_id, session=session, profile=profile)

    def resume_reconciled_failed_upload(
        self, job_id: str, *, session: str, profile: str | None = None,
        repair_authorized: bool = False,
    ) -> dict[str, Any]:
        """Agent-owned one-item repair, after full cloud AND retained queue proof.

        Generic failures are not relabeled as pre-attachment failures. This
        explicit repair requires the same persistent uploader, an entirely
        rendered queue with a successful control upload, and no target in the
        queue, cloud, attachment receipt, or any file input. Never sweep it.
        """
        def eligible(row: dict[str, Any]) -> bool:
            return (
                repair_authorized is True and self.use_opencli_upload_template
                and row.get("event") == "netdisk_upload_failed"
                and row.get("status") == "upload_claimed"
                and row.get("reason") == "browser_command_failed"
                and not row.get("upload_started_at")
                and not row.get("upload_reconciled_repair_claimed_at")
                and not row.get("upload_repair_attempts")
            )

        if session != _OPENCLI_UPLOAD_TEMPLATE_SESSION or (
            profile is not None and not _OPENCLI_PROFILE.fullmatch(profile)
        ):
            raise EnrichmentError("reconciled repair requires the existing upload session")
        current = self.store.latest(job_id)
        if not eligible(current):
            raise EnrichmentError("upload is not eligible for reconciled repair")
        failed_at = datetime.fromisoformat(str(current["updated_at"]))
        if self._time() - failed_at < timedelta(minutes=5):
            raise EnrichmentError("upload failure is too recent for reconciled repair")
        result = self._opencli_upload_template_process(
            session=session, profile=profile,
            video_path=Path(str(current["video_path"])).expanduser().resolve(),
            target_name=str(current["video_basename"]), claim_id=job_id,
            inspect_only=True,
        )
        try:
            rows = json.loads(str(result.stdout))
            row = rows[0] if isinstance(rows, list) and len(rows) == 1 else {}
            surface = row.get("surfaceState") or {}
            queue = surface.get("transferQueue") or {}
            inputs = surface.get("inputs") or []
            safe = (
                result.returncode == 0 and row.get("status") == "ready_to_upload"
                and row.get("directory") == self.netdisk_directory
                and row.get("targetName") == current["video_basename"]
                and row.get("claimId") == job_id and row.get("uploaded") is False
                and row.get("exactCountBefore") == 0
                and queue.get("complete") is True
                and int(queue.get("successfulCount") or 0) >= 1
                and queue.get("targetCount") == 0
                and surface.get("targetInTransferUi") is False
                and surface.get("targetUiRows") == []
                and surface.get("receiptMatchesTarget") is False
                and inputs and all(item.get("targetAttached") is False for item in inputs)
            )
        except (ValueError, TypeError, AttributeError):
            safe = False
        if not safe:
            raise EnrichmentError("upload cloud/queue reconciliation is incomplete or uncertain")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if not eligible(current):
                raise EnrichmentError("upload is not eligible for reconciled repair")
            now = self._time().isoformat(timespec="microseconds")
            self.store.append({
                **current, "event": "netdisk_upload_repair_claimed",
                "upload_reconciled_repair_claimed_at": now,
                "upload_repair_attempts": 1,
                "repair_basis": "authorized_complete_cloud_and_retained_queue_absence",
                "upload_reconciliation_proof": row,
                "updated_at": now,
            })
        return self._submit_opencli_upload(job_id, session=session, profile=profile)

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

    def prepare_cloud(
        self,
        *,
        netdisk_path: str,
        provider_identity_sha256: str,
        size: int,
        modified_at: int,
        source: str,
        author: str,
        observed_at: datetime,
    ) -> dict[str, Any]:
        """Register one exact cloud video without reading its large payload."""
        source_author = {
            "baidu_subscription_share_browser": "吕晓彤",
            "baidu_private_folder": "路西法",
        }
        source_name = str(source or "").strip()
        author_name = str(author or "").strip()
        if source_author.get(source_name) != author_name:
            raise EnrichmentError("cloud video source and author do not match")
        path = str(netdisk_path or "").strip()
        expected_prefix = (
            "/" if self.netdisk_directory == "/" else f"{self.netdisk_directory}/"
        )
        if (
            not path.startswith(expected_prefix)
            or PurePosixPath(path).parent
            != PurePosixPath(self.netdisk_directory)
        ):
            raise EnrichmentError("cloud video is outside the configured Netdisk directory")
        basename = path.removeprefix(expected_prefix)
        if "/" in basename or "\\" in basename:
            raise EnrichmentError("cloud video path is not an exact directory child")
        if Path(basename).suffix.lower() not in {
            ".avi",
            ".flv",
            ".m4v",
            ".mkv",
            ".mov",
            ".mp4",
        }:
            raise EnrichmentError("cloud source is not a supported video")
        identity = str(provider_identity_sha256 or "").strip().lower()
        if not _SHA256.fullmatch(identity):
            raise EnrichmentError("cloud provider identity hash is invalid")
        try:
            source_size = int(size)
            source_modified_at = int(modified_at)
        except (TypeError, ValueError) as exc:
            raise EnrichmentError("cloud video metadata is invalid") from exc
        if source_size <= 0 or source_modified_at <= 0:
            raise EnrichmentError("cloud video metadata is incomplete")
        if observed_at.tzinfo is None:
            raise EnrichmentError("cloud video observation needs a timezone")
        age = self._time().astimezone(timezone.utc) - observed_at.astimezone(
            timezone.utc
        )
        if age < -timedelta(minutes=2) or age > timedelta(minutes=30):
            raise EnrichmentError("cloud video observation is not fresh")
        version_payload = {
            "author": author_name,
            "modified_at": source_modified_at,
            "netdisk_path": path,
            "provider_identity_sha256": identity,
            "size": source_size,
            "source": source_name,
        }
        source_version_sha256 = hashlib.sha256(
            json.dumps(
                version_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        job_id = f"kol-netdisk-cloud-{source_version_sha256[:16]}"
        with self.store.job_lock(job_id):
            try:
                current = self.store.latest(job_id)
            except EnrichmentError as exc:
                if "not found" not in str(exc):
                    raise
                current = None
            if current is not None:
                if (
                    current.get("source_version_sha256")
                    != source_version_sha256
                    or current.get("netdisk_path") != path
                    or current.get("provider_identity_sha256") != identity
                ):
                    raise EnrichmentError("registered cloud video identity changed")
                return {**current, "idempotent_replay": True}
            snapshot_text = f"{basename}\n目标视频 row 已存在"
            proof = self._browser_proof(
                target_name=basename,
                visible_state="video_present",
                state_text="目标视频 row 已存在",
                observed_at=observed_at,
                page_url="https://pan.baidu.com/disk/main",
            )
            row = {
                "schema_version": 1,
                "event": "netdisk_cloud_video_registered",
                "status": "video_ready",
                "provider": "baidu_consumer_page",
                "job_id": job_id,
                "source": source_name,
                "author": author_name,
                "netdisk_path": path,
                "netdisk_directory": self.netdisk_directory,
                "video_basename": basename,
                "video_sha256": source_version_sha256,
                "video_sha256_kind": "cloud_metadata_version",
                "source_version_sha256": source_version_sha256,
                "provider_identity_sha256": identity,
                "video_size_bytes": source_size,
                "source_modified_at": source_modified_at,
                "source_mode": "cloud_existing",
                "browser_surface": "opencli",
                "browser_evidence": self._browser_evidence(
                    {},
                    {
                        **proof,
                        "snapshot_text": snapshot_text,
                        "target_region_text": snapshot_text,
                    },
                    expected_target=basename,
                    step="video_ready",
                ),
                "large_payload_local_bytes": 0,
                "created_at": self._time().isoformat(timespec="seconds"),
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def register_verified_composite(
        self,
        *,
        episode_identity: str,
        episode_version_key: str,
        title: str,
        source: str,
        author: str,
        transcript_path: Path | str,
        components: list[dict[str, Any]],
        observed_at: datetime,
    ) -> dict[str, Any]:
        """Bind verified component transcripts into one logical decision input."""
        identity = str(episode_identity or "").strip().lower()
        version_key = str(episode_version_key or "").strip().lower()
        episode_title = str(title or "").strip()
        if (
            not _SHA256.fullmatch(identity)
            or not _SHA256.fullmatch(version_key)
            or not episode_title
            or "/" in episode_title
            or "\\" in episode_title
        ):
            raise EnrichmentError("logical episode identity is invalid")
        if observed_at.tzinfo is None:
            raise EnrichmentError("logical episode observation needs a timezone")
        if {
            "baidu_subscription_share_browser": "吕晓彤",
            "baidu_private_folder": "路西法",
        }.get(str(source or "").strip()) != str(author or "").strip():
            raise EnrichmentError(
                "logical episode source and author do not match"
            )
        if len(components) < 2:
            raise EnrichmentError(
                "logical episode requires at least two verified components"
            )
        normalized_components = []
        for component in components:
            try:
                part_index = int(component.get("part_index"))
                source_size = int(component.get("source_size") or 0)
            except (TypeError, ValueError) as exc:
                raise EnrichmentError(
                    "logical episode component order is invalid"
                ) from exc
            evidence_path = Path(
                str(component.get("transcript_path") or "")
            ).expanduser().resolve()
            evidence_sha256 = str(
                component.get("transcript_sha256") or ""
            ).lower()
            if (
                part_index <= 0
                or source_size <= 0
                or component.get("status") not in {"verified", "decided"}
                or int(component.get("large_payload_local_bytes") or 0) != 0
                or not evidence_path.is_file()
                or not _SHA256.fullmatch(evidence_sha256)
                or _sha256_file(evidence_path) != evidence_sha256
                or not str(component.get("identity") or "").strip()
                or not str(component.get("version_key") or "").strip()
            ):
                raise EnrichmentError(
                    "logical episode component evidence is invalid"
                )
            normalized_components.append(
                {
                    "identity": str(component["identity"]),
                    "version_key": str(component["version_key"]),
                    "part_index": part_index,
                    "part_label": str(component.get("part_label") or part_index),
                    "source_path": str(component.get("source_path") or ""),
                    "source_size": source_size,
                    "transcript_path": str(evidence_path),
                    "transcript_sha256": evidence_sha256,
                    "job_id": str(component.get("job_id") or ""),
                    "large_payload_local_bytes": 0,
                }
            )
        normalized_components.sort(key=lambda row: row["part_index"])
        if [row["part_index"] for row in normalized_components] != list(
            range(1, len(normalized_components) + 1)
        ):
            raise EnrichmentError(
                "logical episode components must be contiguous and unique"
            )
        expected_version = hashlib.sha256(
            (
                identity
                + "\n"
                + json.dumps(
                    [
                        {
                            "identity": row["identity"],
                            "part_index": row["part_index"],
                            "version_key": row["version_key"],
                        }
                        for row in normalized_components
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            ).encode("utf-8")
        ).hexdigest()
        if expected_version != version_key:
            raise EnrichmentError(
                "logical episode version does not match its components"
            )
        merged_path = Path(transcript_path).expanduser().resolve()
        if not merged_path.is_file():
            raise EnrichmentError("logical episode transcript is missing")
        transcript_sha256 = _sha256_file(merged_path)
        job_id = f"kol-netdisk-episode-{version_key[:16]}"
        binding = {
            "episode_identity": identity,
            "episode_version_key": version_key,
            "source": str(source or "").strip(),
            "author": str(author or "").strip(),
            "title": episode_title,
            "components": normalized_components,
            "transcript_sha256": transcript_sha256,
        }
        binding_sha256 = hashlib.sha256(
            json.dumps(
                binding,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self.store.job_lock(job_id):
            try:
                current = self.store.latest(job_id)
            except EnrichmentError as exc:
                if "not found" not in str(exc):
                    raise
                current = None
            if current is not None:
                if (
                    current.get("source_version_sha256") != version_key
                    or current.get("composite_binding_sha256")
                    != binding_sha256
                    or current.get("transcript_sha256")
                    != transcript_sha256
                ):
                    raise EnrichmentError(
                        "registered logical episode identity changed"
                    )
                return {**current, "idempotent_replay": True}
            timestamp = self._time().isoformat(timespec="seconds")
            row = {
                "schema_version": 1,
                "event": "netdisk_logical_episode_verified",
                "status": "verified",
                "provider": "baidu_consumer_page",
                "job_id": job_id,
                "source": binding["source"],
                "author": binding["author"],
                "netdisk_directory": self.netdisk_directory,
                "netdisk_path": "",
                "video_basename": f"{episode_title}.episode",
                "video_sha256": version_key,
                "video_sha256_kind": "logical_episode_metadata_version",
                "source_version_sha256": version_key,
                "provider_identity_sha256": identity,
                "video_size_bytes": sum(
                    component["source_size"]
                    for component in normalized_components
                ),
                "source_mode": "cloud_logical_episode",
                "transcript_path": str(merged_path),
                "transcript_sha256": transcript_sha256,
                "component_evidence": normalized_components,
                "component_count": len(normalized_components),
                "composite_binding_sha256": binding_sha256,
                "browser_surface": "opencli",
                "browser_evidence": {
                    "page_url": "https://pan.baidu.com/disk/main",
                    "target_name": episode_title,
                    "visible_state": "component_transcripts_verified",
                    "snapshot_sha256": binding_sha256,
                    "observed_at": observed_at.isoformat(
                        timespec="microseconds"
                    ),
                },
                "large_payload_local_bytes": 0,
                "created_at": timestamp,
                "updated_at": timestamp,
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
                or netdisk_paths[0] != self._netdisk_path(expected_target)
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
        allowed_markers = (
            {expected_marker, "ai_note_submission_dispatched"}
            if step == "ai_note_requested"
            else {expected_marker}
        )
        if visible not in allowed_markers:
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
        }:
            checkpoint = self._event_time(
                current.get("claimed_at"), field=f"{step} claimed_at"
            )
            checkpoint_name = "browser action claim"
        elif step in {"transcript_ready", "ai_note_ready"}:
            if current.get("status") == _DIRECT_READY_PREDECESSORS.get(step):
                checkpoint = self._event_time(
                    current.get("claimed_at"), field=f"{step} claimed_at"
                )
                checkpoint_name = "browser action claim"
            else:
                predecessor = current.get("browser_evidence")
                if not isinstance(predecessor, dict):
                    raise EnrichmentError(
                        f"{step} requires timestamped predecessor browser evidence"
                    )
                checkpoint = self._event_time(
                    predecessor.get("observed_at"),
                    field=f"{step} predecessor observed_at",
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

    def reconcile_ai_note_pretrigger_failure(
        self,
        job_id: str,
        *,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        """Recover a legacy AI-note claim proven to have failed before click."""
        required = {
            "schema_version",
            "job_id",
            "action",
            "claimed_at",
            "command",
            "exit_code",
            "error",
            "click_dispatched",
            "source_thread_id",
            "source_turn_id",
            "observed_at",
        }
        if set(evidence) != required:
            raise EnrichmentError("AI-note pretrigger evidence fields are invalid")
        if evidence.get("schema_version") != 1:
            raise EnrichmentError("AI-note pretrigger evidence schema is invalid")
        if evidence.get("job_id") != job_id or evidence.get("action") != "ai_note":
            raise EnrichmentError("AI-note pretrigger evidence target is invalid")
        if evidence.get("exit_code") != 2:
            raise EnrichmentError("AI-note pretrigger evidence exit code is invalid")
        if evidence.get("error") != "Netdisk AI-note template submission failed":
            raise EnrichmentError("AI-note pretrigger evidence error is invalid")
        if evidence.get("click_dispatched") is not False:
            raise EnrichmentError("AI-note pretrigger evidence includes a click")
        command = str(evidence.get("command") or "")
        if (
            "scripts/kol_netdisk_video.py advance-opencli" not in command
            or f"--job-id {job_id}" not in command
        ):
            raise EnrichmentError("AI-note pretrigger evidence command is invalid")
        for field in ("source_thread_id", "source_turn_id"):
            if not re.fullmatch(r"[0-9a-f-]{36}", str(evidence.get(field) or "")):
                raise EnrichmentError(f"AI-note pretrigger evidence {field} is invalid")
        observed_at = self._event_time(
            evidence.get("observed_at"), field="AI-note pretrigger observed_at"
        )
        canonical = json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n"
        evidence_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if current.get("status") == "ai_note_pretrigger_failed":
                if current.get("ai_note_pretrigger_evidence_sha256") != evidence_sha256:
                    raise EnrichmentError(
                        "AI-note pretrigger failure was reconciled with different evidence"
                    )
                return {**current, "idempotent_replay": True}
            if current.get("status") != "ai_note_claimed":
                raise EnrichmentError(
                    "AI-note pretrigger reconciliation requires claimed state"
                )
            claimed_at = str(current.get("claimed_at") or "")
            if evidence.get("claimed_at") != claimed_at:
                raise EnrichmentError("AI-note pretrigger evidence claim does not match")
            claim_time = self._event_time(
                claimed_at, field="AI-note pretrigger claimed_at"
            )
            if observed_at < claim_time:
                raise EnrichmentError("AI-note pretrigger evidence predates the claim")
            if current.get("ai_note_triggered_at") or current.get(
                "ai_note_submission_proof"
            ):
                raise EnrichmentError("AI-note claim already has submission evidence")
            attempt = int(current.get("ai_note_trigger_attempt") or 1)
            if attempt != 1:
                raise EnrichmentError(
                    "legacy AI-note pretrigger reconciliation requires first attempt"
                )
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **current,
                "event": "netdisk_ai_note_pretrigger_failed",
                "status": "ai_note_pretrigger_failed",
                "ai_note_trigger_attempt": attempt,
                "ai_note_pretrigger_proof": {
                    "button_matches": None,
                    "click_dispatched": False,
                    "template_no": 1,
                    "target_bound": True,
                    "proof_kind": "captured_cli_error",
                },
                "reconciled_legacy_pretrigger": True,
                "ai_note_pretrigger_evidence_sha256": evidence_sha256,
                "ai_note_pretrigger_source_thread_id": evidence["source_thread_id"],
                "ai_note_pretrigger_source_turn_id": evidence["source_turn_id"],
                "ai_note_pretrigger_observed_at": evidence["observed_at"],
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def recover_ai_note_postclick_zero(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None = None,
        operator_confirmed_no_click: bool = False,
    ) -> dict[str, Any]:
        """Perform one final submit after a stale claim has a fresh zero-effect proof."""
        if not operator_confirmed_no_click:
            raise EnrichmentError(
                "AI-note postclick-zero recovery requires operator confirmation"
            )
        if not _OPENCLI_SESSION.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        if profile is not None and not _OPENCLI_PROFILE.fullmatch(profile):
            raise EnrichmentError("OpenCLI profile name is invalid")

        current = self.store.latest(job_id)
        status = str(current.get("status") or "")
        if status in {"ai_note_requested", "ai_note_ready"}:
            return {**current, "idempotent_replay": True}
        if status != "ai_note_claimed":
            raise EnrichmentError(
                "AI-note postclick-zero recovery requires claimed state"
            )
        attempt = int(current.get("ai_note_trigger_attempt") or 1)
        target_name = str(current["video_basename"])
        player_url = self._open_opencli_player(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        self._select_opencli_tab(
            session=session,
            profile=profile,
            label="笔记",
            target_name=target_name,
        )
        self._wait_opencli_active_tab(
            session=session,
            profile=profile,
            label="笔记",
            target_name=target_name,
        )
        self._run_opencli(
            session,
            "wait",
            "selector",
            "#noteIframe",
            "--timeout",
            "10000",
            profile=profile,
            timeout_seconds=20,
        )
        probe = self._probe_opencli_ai_note(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        if probe["ai_note_state"] in {"generating", "ready"}:
            return self._record_ai_note_triggered(
                job_id,
                target_name=target_name,
                page_url=player_url,
                trigger_proof={
                    "click_dispatched": False,
                    "modal_visible": False,
                    "confirmed_state": probe["ai_note_state"],
                    "content_chars": int(probe.get("content_chars") or 0),
                    "reconciled_after_claim": True,
                },
            )
        if attempt >= _AI_NOTE_MAX_TRIGGER_ATTEMPTS:
            return {
                **self.store.latest(job_id),
                "pending": True,
                "side_effect_uncertain": True,
                "retry_exhausted": True,
                "idempotent_replay": True,
            }
        claim_time = self._event_time(
            current.get("claimed_at"), field="AI-note postclick-zero claimed_at"
        )
        observed_at = self._time()
        if observed_at - claim_time < _AI_NOTE_POSTCLICK_ZERO_MIN_AGE:
            raise EnrichmentError(
                "AI-note postclick-zero recovery claim is not old enough"
            )
        preview = self._opencli_template_json(
            session,
            "prepare_ai_note",
            expected_path=self._netdisk_path(target_name),
            profile=profile,
        )
        if (
            preview.get("target_bound") is not True
            or preview.get("scheduled") is not True
            or preview.get("modal_ready") is not True
            or preview.get("template_matches") != 1
            or preview.get("template_selected") != "文稿笔记"
            or preview.get("button_matches") != 1
            or preview.get("click_dispatched") is not False
        ):
            raise EnrichmentError(
                "AI-note postclick-zero recovery lacks exact modal proof"
            )

        with self.store.job_lock(job_id):
            latest = self.store.latest(job_id)
            if (
                latest.get("status") != "ai_note_claimed"
                or int(latest.get("ai_note_trigger_attempt") or 1) != attempt
                or latest.get("claimed_at") != current.get("claimed_at")
            ):
                raise EnrichmentError("AI-note postclick-zero claim changed")
            now = self._time().isoformat(timespec="microseconds")
            row = {
                **latest,
                "event": "netdisk_ai_note_postclick_zero_retry_claimed",
                "status": "ai_note_claimed",
                "claimed_at": now,
                "ai_note_trigger_attempt": attempt + 1,
                "ai_note_retry_of": str(current.get("claimed_at") or ""),
                "ai_note_recovery_kind": "stale_claim_exact_zero_effect",
                "ai_note_operator_confirmed_no_click": True,
                "ai_note_postclick_zero_proof": {
                    "observed_at": observed_at.isoformat(timespec="microseconds"),
                    "ai_note_state": "missing",
                    "content_chars": int(probe.get("content_chars") or 0),
                    "target_bound": True,
                    "template_name": preview.get("template_name"),
                    "template_version": preview.get("template_version"),
                    "template_selected": "文稿笔记",
                    "button_matches": 1,
                    "click_dispatched": False,
                },
                "updated_at": now,
            }
            _clear_transient_failures(row)
            self.store.append(row)

        trigger_proof = self._trigger_opencli_ai_note(
            session=session,
            profile=profile,
            target_name=target_name,
        )
        if trigger_proof.get("submitted") is not True:
            self._record_ai_note_pretrigger_failure(
                job_id,
                trigger_proof=trigger_proof,
            )
            raise EnrichmentError("Netdisk AI-note template submission failed")
        return self._record_ai_note_triggered(
            job_id,
            target_name=target_name,
            page_url=player_url,
            trigger_proof=trigger_proof,
        )

    def claim_browser_action(self, job_id: str, *, action: str) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise EnrichmentError(f"unsupported browser action: {action}")
        expected = {
            "upload": {"prepared"},
            "transcript": {"video_ready"},
            "ai_note": {"transcript_ready"},
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
            if action == "ai_note":
                row["ai_note_trigger_attempt"] = 1
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
            direct_ready_allowed = (
                current_status == _DIRECT_READY_PREDECESSORS.get(step)
            )
            if (
                current_status != expected
                and not reconciliation_allowed
                and not direct_ready_allowed
            ):
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
            if step in {"transcript_requested", "ai_note_requested"}:
                observed_at = datetime.fromisoformat(normalized["observed_at"])
                row["next_poll_not_before"] = (
                    observed_at + _NETDISK_GENERATION_POLL_INTERVAL
                ).isoformat(timespec="microseconds")
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def capture_opencli_transcript(
        self,
        job_id: str,
        *,
        session: str,
        profile: str | None = None,
    ) -> dict[str, Any]:
        """Materialize the complete, initially rendered Netdisk transcript via OpenCLI."""
        if not _OPENCLI_SESSION.fullmatch(session):
            raise EnrichmentError("OpenCLI session name is invalid")
        if profile is not None and not _OPENCLI_PROFILE.fullmatch(profile):
            raise EnrichmentError("OpenCLI profile name is invalid")
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            failure_recorded = False

            def reject(
                reason: str,
                message: str,
                *,
                error: EnrichmentError | None = None,
            ) -> None:
                nonlocal failure_recorded
                failure_recorded = True
                row = {
                    **current,
                    "event": "netdisk_dom_capture_failed",
                    "status": current.get("status"),
                    "failure_stage": "capture_opencli_dom",
                    "reason": reason,
                    "error_type": type(error).__name__ if error else "EnrichmentError",
                    "updated_at": self._time().isoformat(timespec="seconds"),
                }
                row.pop("diagnostic", None)
                row.pop("cause_diagnostic", None)
                if isinstance(error, EnrichmentDiagnosticError):
                    row["diagnostic"] = _opencli_diagnostic(error)
                if isinstance(getattr(error, "__cause__", None), EnrichmentDiagnosticError):
                    row["cause_diagnostic"] = _opencli_diagnostic(error.__cause__)
                self.store.append(row)
                if error is not None:
                    raise error
                raise EnrichmentError(message)

            def finish_close() -> dict[str, Any]:
                transcript_path = Path(str(current.get("transcript_path") or ""))
                expected_path_sha = hashlib.sha256(
                    self._netdisk_path(str(current["video_basename"])).encode("utf-8")
                ).hexdigest()
                if (
                    current.get("player_session") != session
                    or current.get("player_profile") != profile
                    or current.get("player_path_sha256") != expected_path_sha
                    or not transcript_path.is_file()
                    or _sha256_file(transcript_path) != current.get("transcript_sha256")
                    or not current.get("dom_capture_sha256")
                    or any(
                        not isinstance(current.get(field), dict)
                        or current[field].get("all_video_paused") is not True
                        or current[field].get("pause_guard_installed") is not True
                        or not isinstance(current[field].get("video_count"), int)
                        or current[field]["video_count"] < 1
                        for field in ("player_pause_receipt", "player_capture_pause_receipt")
                    )
                ):
                    reject(
                        "completed_capture_mismatch",
                        "pending transcript close lost its exact capture binding",
                    )
                try:
                    close_receipt = self._close_opencli_player(
                        session=session,
                        profile=profile,
                        target_name=str(current["video_basename"]),
                        page=str(current.get("player_page") or ""),
                    )
                except EnrichmentError as exc:
                    reject("player_close_unverified", str(exc), error=exc)
                row = {
                    **current,
                    "event": "netdisk_transcript_dom_captured",
                    "status": "transcript_captured",
                    "player_close_receipt": close_receipt,
                    "updated_at": self._time().isoformat(timespec="seconds"),
                }
                row.pop("transcript_close_pending", None)
                _clear_transient_failures(row)
                self.store.append(row)
                return {**row, "idempotent_replay": False}

            if current.get("status") in {"transcript_captured", "verified", "decided"}:
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
            if current.get("status") not in {
                "ai_note_claimed",
                "ai_note_requested",
                "ai_note_ready",
            }:
                reject(
                    "invalid_predecessor",
                    "OpenCLI DOM capture requires an AI-note submission trigger attempt after transcript readiness",
                )
            if current.get("browser_surface") != "opencli":
                reject(
                    "wrong_browser_surface",
                    "OpenCLI DOM capture requires an OpenCLI browser proof",
                )
            if current.get("transcript_close_pending") is True:
                return finish_close()
            try:
                player_receipt = self._open_opencli_player_receipt(
                    session=session,
                    profile=profile,
                    target_name=str(current["video_basename"]),
                )
                capture_output = self._run_opencli(
                    session,
                    "eval",
                    _OPENCLI_CAPTURE_PROBE.replace(
                        "__EXPECTED_NETDISK_PATH__",
                        json.dumps(
                            self._netdisk_path(
                                str(current["video_basename"])
                            )
                        ),
                    ),
                    profile=profile,
                    timeout_seconds=30,
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
                try:
                    self._validate_player_url(
                        page_url,
                        target_name=str(current["video_basename"]),
                    )
                except EnrichmentError:
                    reject(
                        "target_url_mismatch",
                        "OpenCLI page does not match the prepared Netdisk video",
                    )
                if capture_result.get("target_bound") is not True:
                    reject(
                        "target_url_mismatch",
                        "OpenCLI page changed before transcript DOM capture",
                    )
                playback = capture_result.get("playback")
                if (
                    not isinstance(playback, dict)
                    or not isinstance(playback.get("video_count"), int)
                    or playback["video_count"] < 1
                    or playback.get("all_video_paused") is not True
                    or playback.get("pause_guard_installed") is not True
                ):
                    reject(
                        "player_not_paused",
                        "Netdisk player video is not proven paused during transcript capture",
                    )
                parsed = urlsplit(page_url)

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
                browser_transcript = (
                    transcript_result.get("text")
                    if isinstance(transcript_result, dict)
                    else None
                )
                if (
                    not isinstance(transcript_result, dict)
                    or not isinstance(browser_transcript, str)
                    or len(browser_transcript.strip()) < 200
                ):
                    reject(
                        "transcript_missing_or_short",
                        "OpenCLI did not return one nontrivial transcript",
                    )
                try:
                    transcript_text, segment_proof = (
                        _normalize_ordered_transcript_segments(
                            transcript_result.get("segments")
                        )
                    )
                except EnrichmentError as exc:
                    reject("invalid_segment_coverage", str(exc))
                if browser_transcript.strip() != transcript_text:
                    reject(
                        "segment_text_mismatch",
                        "OpenCLI transcript text does not match ordered segments",
                    )

                render = capture_result.get("render")
            except (EnrichmentError, json.JSONDecodeError, StopIteration) as exc:
                if isinstance(exc, EnrichmentError):
                    if not failure_recorded:
                        reject(
                            exc.diagnostic_code
                            if isinstance(exc, EnrichmentDiagnosticError)
                            else "opencli_command_failed",
                            str(exc),
                            error=exc,
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
                "segment_count",
                "segment_terminal_index",
                "list_text_chars",
                "sentence_text_chars",
            }
            if any(
                not isinstance(render.get(field), (int, float))
                for field in numeric_fields
            ):
                reject("invalid_render_proof", "OpenCLI render proof is incomplete")
            markers = render.get("virtual_or_loading_markers")
            assert isinstance(segment_proof, dict)
            content_fits = render["scroll_height"] <= render["client_height"] + 1
            if (
                abs(render["scroll_top"]) > 1
                or render["list_matches"] != 1
                or render["paragraph_count"] < 1
                or render["sentence_count"] < 3
                or render["sentence_count"] != render["segment_count"]
                or render["segment_count"] != segment_proof["segment_count"]
                or render["segment_terminal_index"]
                != segment_proof["segment_terminal_index"]
                or render["paragraph_count"] != segment_proof["paragraph_count"]
                or render["list_text_chars"] != len(transcript_text)
                or render["sentence_text_chars"] <= 0
                or render["sentence_text_chars"] > render["list_text_chars"]
                or render.get("first_node_in_dom") is not True
                or render.get("last_node_in_dom") is not True
                or render.get("first_node_at_viewport_start") is not True
                or render.get("first_node_near_list_start") is not True
                or (
                    not content_fits
                    and render.get("last_node_below_viewport") is not True
                )
                or render.get("last_node_near_list_end") is not True
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
            if transcript_path.exists():
                if transcript_path.read_bytes() != transcript_bytes:
                    reject(
                        "existing_transcript_mismatch",
                        "existing transcript cannot be replaced during capture recovery",
                    )
            else:
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
                    "segment_count",
                    "segment_terminal_index",
                    "list_text_chars",
                    "sentence_text_chars",
                    "first_node_in_dom",
                    "last_node_in_dom",
                    "first_node_at_viewport_start",
                    "first_node_near_list_start",
                    "last_node_below_viewport",
                    "last_node_near_list_end",
                    "has_load_more",
                )
            }
            render_proof.update(segment_proof)
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
                "event": "netdisk_transcript_dom_capture_pending_close",
                "transcript_close_pending": True,
                "ai_note_completion_required": False,
                "ai_note_submission_status": (
                    "claimed_non_gating"
                    if current.get("status") == "ai_note_claimed"
                    else "requested"
                ),
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
                "dom_ad_overlays_dismissed": int(
                    capture_result.get("ad_overlays_dismissed") or 0
                ),
                "player_pause_receipt": player_receipt["pause_receipt"],
                "player_open_recovery": player_receipt["recovered_from"],
                "player_capture_pause_receipt": {
                    "video_count": playback["video_count"],
                    "all_video_paused": True,
                    "pause_guard_installed": True,
                },
                "player_page": player_receipt["page"],
                "player_session": session,
                "player_profile": profile,
                "player_path_sha256": hashlib.sha256(
                    self._netdisk_path(str(current["video_basename"])).encode("utf-8")
                ).hexdigest(),
                "updated_at": observed_at.isoformat(timespec="seconds"),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            current = row
            return finish_close()

    def verify_transcript(
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
                    "failure_stage": "verify_transcript",
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
            if current.get("status") != "transcript_captured":
                reject(
                    "invalid_predecessor",
                    "content verification requires state transcript_captured",
                )
            transcript_path = Path(str(current.get("transcript_path") or ""))
            if (
                not transcript_path.is_file()
                or _sha256_file(transcript_path) != current.get("transcript_sha256")
            ):
                reject(
                    "transcript_missing_or_changed",
                    "captured transcript is missing or changed",
                )
            try:
                audit = json.loads(audit_bytes)
            except json.JSONDecodeError as exc:
                self.store.append({
                    **current,
                    "event": "netdisk_content_verification_failed",
                    "status": current.get("status"),
                    "failure_stage": "verify_transcript",
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
                    "content audit does not match the captured transcript",
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
            row["browser_evidence"] = {
                "page_url": str(current.get("dom_page_url") or ""),
                "target_name": str(current.get("video_basename") or ""),
                "visible_state": "transcript_dom_captured",
                "snapshot_sha256": str(current.get("dom_capture_sha256") or ""),
                "observed_at": str(current.get("dom_capture_observed_at") or ""),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}

    def reconcile_semantic_duplicate(
        self,
        job_id: str,
        *,
        bundle_path: Path | str,
        reconciliation_path: Path | str,
        decision_output_dir: Path | str,
    ) -> dict[str, Any]:
        """Bind a new verified transcript to prior receipted outcomes, without resend."""
        bundle_file = Path(bundle_path).expanduser().resolve()
        reconciliation_file = Path(reconciliation_path).expanduser().resolve()
        with self.store.job_lock(job_id):
            current = self.store.latest(job_id)
            if not bundle_file.is_file() or not reconciliation_file.is_file():
                raise EnrichmentError("semantic duplicate evidence is missing")
            bundle_bytes = bundle_file.read_bytes()
            reconciliation_bytes = reconciliation_file.read_bytes()
            bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
            reconciliation_sha = hashlib.sha256(
                reconciliation_bytes
            ).hexdigest()
            if (
                current.get("status") == "decided"
                and current.get("decision_bundle_sha256") == bundle_sha
                and current.get("semantic_reconciliation_sha256")
                == reconciliation_sha
            ):
                return {**current, "idempotent_replay": True}
            if current.get("status") != "verified":
                raise EnrichmentError(
                    "only a verified transcript can be duplicate-reconciled"
                )
            transcript_path = Path(str(current.get("transcript_path") or ""))
            if (
                not transcript_path.is_file()
                or _sha256_file(transcript_path)
                != current.get("transcript_sha256")
            ):
                raise EnrichmentError("verified transcript is missing or changed")
            try:
                bundle = json.loads(bundle_bytes)
                reconciliation = json.loads(reconciliation_bytes)
            except json.JSONDecodeError as exc:
                raise EnrichmentError(
                    "semantic duplicate input is invalid JSON"
                ) from exc
            items = bundle.get("items") if isinstance(bundle, dict) else None
            if (
                not isinstance(items, list)
                or len(items) != 1
                or not isinstance(items[0], dict)
            ):
                raise EnrichmentError(
                    "semantic duplicate requires one decision item"
                )
            item = items[0]
            evidence_path = Path(
                str(item.get("evidence_path") or "")
            ).expanduser().resolve()
            if (
                evidence_path != transcript_path.resolve()
                or item.get("evidence_sha256")
                != current.get("transcript_sha256")
            ):
                raise EnrichmentError(
                    "semantic duplicate bundle is not bound to this transcript"
                )
            from .decisions import DecisionPipeline

            validation_pipeline = DecisionPipeline(
                Path(decision_output_dir),
                household_context_loader=lambda: {},
            )
            failures = validation_pipeline._failures(bundle)
            if failures:
                raise EnrichmentError(
                    "semantic duplicate analysis failed: "
                    + ",".join(failures)
                )
            try:
                validation_pipeline._validate_cross_source(bundle)
                document = validation_pipeline._validate_item(item)
                validation_pipeline.book.validate(
                    item.get("book_kol_us") or {}
                )
            except Exception as exc:
                raise EnrichmentError(
                    "semantic duplicate analysis contract is invalid"
                ) from exc
            if (
                document.path.resolve() != transcript_path.resolve()
                or document.sha256 != current.get("transcript_sha256")
            ):
                raise EnrichmentError(
                    "semantic duplicate analysis document is not current"
                )
            coverage = item.get("coverage_matrix")
            required_coverage = {
                "todays_market_diagnosis",
                "next_session_playbook",
                "next_several_session_base_case",
                "style_market_cap_regime",
                "market_board_sector_hierarchy",
                "position_risk_budget",
                "named_asset_inventory",
            }
            if (
                not isinstance(coverage, list)
                or {row.get("row_id") for row in coverage if isinstance(row, dict)}
                != required_coverage
                or any(
                    not str(row.get("conclusion") or "").strip()
                    or not isinstance(row.get("evidence"), list)
                    or not row["evidence"]
                    for row in coverage
                    if isinstance(row, dict)
                )
            ):
                raise EnrichmentError(
                    "semantic duplicate analysis coverage is incomplete"
                )
            if not isinstance(reconciliation, dict):
                raise EnrichmentError(
                    "semantic duplicate reconciliation must be an object"
                )
            current_text = re.sub(
                r"\s+",
                "",
                transcript_path.read_text(encoding="utf-8"),
            )
            prior_path = Path(
                str(reconciliation.get("prior_evidence_path") or "")
            ).expanduser().resolve()
            prior_sha = str(
                reconciliation.get("prior_evidence_sha256") or ""
            )
            if (
                reconciliation.get("current_evidence_path")
                != str(transcript_path.resolve())
                or reconciliation.get("current_evidence_sha256")
                != current.get("transcript_sha256")
                or not prior_path.is_file()
                or not _SHA256.fullmatch(prior_sha)
                or _sha256_file(prior_path) != prior_sha
            ):
                raise EnrichmentError(
                    "semantic duplicate evidence binding is invalid"
                )
            prior_text = re.sub(
                r"\s+",
                "",
                prior_path.read_text(encoding="utf-8"),
            )
            similarity = SequenceMatcher(
                None,
                current_text,
                prior_text,
                autojunk=False,
            ).ratio()
            containment = current_text in prior_text or prior_text in current_text
            if (
                len(current_text) < 2_000
                or len(prior_text) < 2_000
                or similarity < 0.995
                or not containment
                or reconciliation.get("normalized_containment") is not True
                or abs(
                    float(reconciliation.get("normalized_similarity") or 0)
                    - similarity
                )
                > 1e-12
            ):
                raise EnrichmentError(
                    "semantic duplicate transcript proof did not match"
                )
            notification = reconciliation.get("household_notification") or {}
            paper = reconciliation.get("book_kol_us") or {}
            result_item = {
                **item,
                "notification": {
                    **notification,
                    "reconciled_existing": True,
                },
                "book_kol_us": {
                    **paper,
                    "idempotent_replay": True,
                    "reconciled_existing": True,
                },
                "decision_status": "semantic_duplicate_reconciled",
                "decision_reason": (
                    "完整文稿与同作者同标题的既有证据一致；复用已送达家庭"
                    "建议和既有 Book KOL-US 纸面结果，未产生新副作用。"
                ),
            }
            result = {
                "status": "completed",
                "items": [result_item],
                "semantic_duplicate_reconciliation": {
                    "prior_evidence_path": str(prior_path),
                    "prior_evidence_sha256": prior_sha,
                    "normalized_similarity": similarity,
                    "normalized_containment": True,
                    "side_effects_reused": [
                        "household_notification",
                        "book_kol_us",
                    ],
                    "new_external_side_effect_count": 0,
                },
                "processed_at": self._time().isoformat(timespec="seconds"),
            }
            validated_notification, validated_paper = (
                validate_decision_completion(result)
            )
            claim_path = (
                self.output_dir
                / "artifacts"
                / job_id
                / "semantic_duplicate_claim.json"
            )
            receipt_path = claim_path.with_name(
                "semantic_duplicate_receipt.json"
            )
            claim = {
                "schema_version": 1,
                "event": "semantic_duplicate_reconciliation_claimed",
                "job_id": job_id,
                "decision_bundle_sha256": bundle_sha,
                "semantic_reconciliation_sha256": reconciliation_sha,
                "current_evidence_sha256": current["transcript_sha256"],
                "prior_evidence_sha256": prior_sha,
                "claimed_at": self._time().isoformat(timespec="seconds"),
            }
            if claim_path.is_file():
                try:
                    existing_claim = json.loads(
                        claim_path.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError as exc:
                    raise EnrichmentError(
                        "semantic duplicate claim is invalid"
                    ) from exc
                if {
                    key: existing_claim.get(key)
                    for key in (
                        "job_id",
                        "decision_bundle_sha256",
                        "semantic_reconciliation_sha256",
                        "current_evidence_sha256",
                        "prior_evidence_sha256",
                    )
                } != {
                    key: claim.get(key)
                    for key in (
                        "job_id",
                        "decision_bundle_sha256",
                        "semantic_reconciliation_sha256",
                        "current_evidence_sha256",
                        "prior_evidence_sha256",
                    )
                }:
                    raise EnrichmentError(
                        "semantic duplicate claim conflicts with prior state"
                    )
            else:
                _atomic_write_json(claim_path, claim)
            result_bytes = (
                json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8")
            result_path = (
                self.output_dir
                / "artifacts"
                / job_id
                / "decision_result.json"
            )
            temporary = result_path.with_name(
                ".decision_result.partial.json"
            )
            temporary.write_bytes(result_bytes)
            temporary.replace(result_path)
            receipt = {
                **claim,
                "event": "semantic_duplicate_reconciliation_completed",
                "status": "completed",
                "decision_result_path": str(result_path),
                "decision_result_sha256": hashlib.sha256(
                    result_bytes
                ).hexdigest(),
                "household_notification": {
                    key: validated_notification[key]
                    for key in (
                        "idempotency_key",
                        "status",
                        "receipt",
                    )
                    if validated_notification.get(key) is not None
                },
                "book_kol_us": {
                    key: validated_paper[key]
                    for key in (
                        "idempotency_key",
                        "status",
                        "book",
                        "paper_only",
                        "reason",
                    )
                    if validated_paper.get(key) is not None
                },
                "new_external_side_effect_count": 0,
                "completed_at": self._time().isoformat(timespec="seconds"),
            }
            _atomic_write_json(receipt_path, receipt)
            row = {
                **current,
                "event": "netdisk_semantic_duplicate_reconciled",
                "status": "decided",
                "decision_bundle_path": str(bundle_file),
                "decision_bundle_sha256": bundle_sha,
                "semantic_reconciliation_path": str(reconciliation_file),
                "semantic_reconciliation_sha256": reconciliation_sha,
                "semantic_duplicate_claim_path": str(claim_path),
                "semantic_duplicate_receipt_path": str(receipt_path),
                "decision_result_path": str(result_path),
                "decision_result_sha256": receipt[
                    "decision_result_sha256"
                ],
                "household_notification": receipt[
                    "household_notification"
                ],
                "book_kol_us": receipt["book_kol_us"],
                "new_external_side_effect_count": 0,
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
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
        reconcile_daily_terminal: bool = False,
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
                    if current.get("status") == "decided":
                        row["attempted_decision_bundle_sha256"] = bundle_sha
                    else:
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
                replay = {**current}
                for field in (
                    "transcript_path",
                    "decision_bundle_path",
                    "decision_result_path",
                ):
                    resolved = self._runtime_path(
                        str(replay.get(field) or "")
                    )
                    if resolved.is_file():
                        replay[field] = str(resolved)
                result_path = Path(
                    str(replay.get("decision_result_path") or "")
                ).expanduser()
                has_daily_terminal = False
                if result_path.is_file():
                    try:
                        prior_result = json.loads(
                            result_path.read_text(encoding="utf-8")
                        )
                        prior_items = prior_result.get("items") or []
                        has_daily_terminal = bool(
                            prior_items
                            and isinstance(prior_items[0], dict)
                            and isinstance(
                                prior_items[0].get("daily_terminal"), dict
                            )
                        )
                    except (OSError, json.JSONDecodeError):
                        has_daily_terminal = False
                if not reconcile_daily_terminal or has_daily_terminal:
                    return {**replay, "idempotent_replay": True}
                if pipeline is None:
                    exc = EnrichmentError(
                        "daily terminal reconciliation requires a publication pipeline"
                    )
                    record_failure(
                        "daily_terminal_reconciliation",
                        exc,
                        bundle_sha=bundle_sha,
                    )
                    raise exc
            is_revision = current.get("status") == "decided"
            if not is_revision and current.get("status") != "verified":
                exc = EnrichmentError(
                    "only a verified Netdisk transcript can be decided"
                )
                record_failure("invalid_predecessor", exc, bundle_sha=bundle_sha)
                raise exc
            transcript_path = self._runtime_path(
                str(current.get("transcript_path") or "")
            )
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
            validated_receipt = None
            try:
                validated_receipt = _validate_canonical_semantic_artifact(
                    bundle_file,
                    bundle,
                    expected_bindings={
                        "transcript_sha256": current.get("transcript_sha256"),
                        "handoff_id": current.get("handoff_id"),
                        "source_identity": current.get("source_identity"),
                        "source_version_key": current.get("source_version_key"),
                    },
                )
            except SemanticBundleError as exc:
                record_failure(
                    "validated_bundle_receipt",
                    exc,
                    bundle_sha=bundle_sha,
                )
                raise
            evidence_path = self._runtime_path(
                str(items[0].get("evidence_path") or "")
            )
            if evidence_path != transcript_path.resolve():
                exc = EnrichmentError(
                    "decision bundle evidence_path must be the verified transcript"
                )
                record_failure("evidence_path_mismatch", exc, bundle_sha=bundle_sha)
                raise exc
            if is_revision:
                from .book import BookKolUs

                prior_book = current.get("book_kol_us") or {}
                prior_book_key = str(prior_book.get("idempotency_key") or "")
                revision_book = BookKolUs(
                    Path(decision_output_dir).expanduser().resolve()
                    / "book_kol_us"
                )
                try:
                    revision_intent = items[0].get("book_kol_us") or {}
                    revision_book.validate(revision_intent)
                    revision_book_key = revision_book.resolve_identity(
                        str(current["transcript_sha256"]),
                        revision_intent,
                    )
                except Exception as exc:
                    record_failure(
                        "revision_book_validation",
                        exc,
                        bundle_sha=bundle_sha,
                    )
                    raise EnrichmentError(
                        "decision revision has an invalid Book KOL-US intent"
                    ) from exc
                if not prior_book_key or revision_book_key != prior_book_key:
                    exc = EnrichmentError(
                        "message-only revision cannot change Book KOL-US intent"
                    )
                    record_failure(
                        "revision_book_changed",
                        exc,
                        bundle_sha=bundle_sha,
                    )
                    raise exc
                prior_completion = next(
                    (
                        row
                        for row in reversed(self.store.read())
                        if row.get("job_id") == job_id
                        and row.get("event")
                        == "netdisk_decision_revision_completed"
                        and row.get("decision_bundle_sha256") == bundle_sha
                    ),
                    None,
                )
                if prior_completion is not None:
                    return {**prior_completion, "idempotent_replay": True}
                prior_claim = next(
                    (
                        row
                        for row in reversed(self.store.read())
                        if row.get("job_id") == job_id
                        and row.get("event")
                        == "netdisk_decision_revision_claimed"
                        and row.get("pending_decision_bundle_sha256")
                        == bundle_sha
                    ),
                    None,
                )
                if prior_claim is None:
                    prior_bundle_sha = str(
                        current.get("decision_bundle_sha256") or ""
                    )
                    current = {
                        **current,
                        "event": "netdisk_decision_revision_claimed",
                        "status": "decided",
                        "decision_revision_idempotency_key": hashlib.sha256(
                            f"decision-revision:{job_id}:{bundle_sha}".encode()
                        ).hexdigest(),
                        "previous_decision_bundle_sha256": prior_bundle_sha,
                        "pending_decision_bundle_path": str(bundle_file),
                        "pending_decision_bundle_sha256": bundle_sha,
                        "updated_at": self._time().isoformat(timespec="seconds"),
                    }
                    self.store.append(current)
                else:
                    current = prior_claim
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
            artifact_dir.mkdir(parents=True, exist_ok=True)
            result_name = (
                f"decision_result.{bundle_sha[:16]}.json"
                if is_revision
                else "decision_result.json"
            )
            result_path = artifact_dir / result_name
            temporary = artifact_dir / f".{result_name}.partial"
            temporary.write_bytes(result_bytes)
            temporary.replace(result_path)
            household_summary = {
                key: notification[key]
                for key in ("idempotency_key", "status", "receipt", "reason")
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
                "event": (
                    "netdisk_decision_revision_completed"
                    if is_revision
                    else "netdisk_decisions_completed"
                ),
                "status": "decided",
                "decision_bundle_path": str(bundle_file),
                "decision_bundle_sha256": bundle_sha,
                **(
                    {
                        "validated_bundle_receipt_path": str(
                            bundle_file.with_name("validated_bundle_receipt.json")
                        ),
                        "validated_bundle_receipt_sha256": hashlib.sha256(
                            bundle_file.with_name(
                                "validated_bundle_receipt.json"
                            ).read_bytes()
                        ).hexdigest(),
                    }
                    if validated_receipt is not None
                    else {}
                ),
                "decision_result_path": str(result_path),
                "decision_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "household_notification": household_summary,
                "book_kol_us": paper_summary,
                "new_external_side_effect_count": (
                    int(result["items"][0].get("idempotent_replay") is not True)
                    if is_revision
                    else 2
                ),
                "updated_at": self._time().isoformat(timespec="seconds"),
            }
            row.pop("pending_decision_bundle_path", None)
            row.pop("pending_decision_bundle_sha256", None)
            row.pop("attempted_decision_bundle_sha256", None)
            row["browser_evidence"] = {
                "page_url": str(current.get("dom_page_url") or ""),
                "target_name": str(current.get("video_basename") or ""),
                "visible_state": "transcript_dom_captured",
                "snapshot_sha256": str(current.get("dom_capture_sha256") or ""),
                "observed_at": str(current.get("dom_capture_observed_at") or ""),
            }
            _clear_transient_failures(row)
            self.store.append(row)
            return {**row, "idempotent_replay": False}
