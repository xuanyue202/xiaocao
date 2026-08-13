"""Portable capture-node primitives for the KOL intelligence pipeline.

The capture service is intentionally treated as an external adapter.  This
module owns only lightweight metadata and an append-only transition ledger; it
never stores passwords, cookies, or media payloads.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from base64 import urlsafe_b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


DEFAULT_SNIFFER_URL = "http://127.0.0.1:2022"
CANDIDATES_MIN_TIMEOUT_SECONDS = 15.0
TERMINAL_DOWNLOAD_STATUSES = {"done", "complete", "completed"}
FAILED_DOWNLOAD_STATUSES = {"error", "failed"}
CHECKPOINT_STATUSES = {
    "uploading",
    "uploaded",
    "ai_processing",
    "enriched",
    "analysis_completed",
    "notified",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _candidate_key(row: dict[str, Any]) -> str:
    live_id = str(row.get("live_id") or "").strip()
    if live_id:
        return f"live:{live_id}"
    candidate_id = str(row.get("id") or "").strip()
    if candidate_id:
        return f"id:{candidate_id}"
    raw_url = str(row.get("url") or "").strip()
    parsed = urlsplit(raw_url)
    stable_path = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    digest = hashlib.sha256(stable_path.encode("utf-8")).hexdigest()
    return f"url-sha256:{digest}"


def _captured_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("captured") or ""), _candidate_key(row))


def _safe_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only restartable identity metadata, never a signed media URL."""
    allowed = {
        "captured",
        "content_type",
        "date_prefix",
        "file_size",
        "filename",
        "host",
        "id",
        "live_id",
        "media_type",
        "recommended",
        "title",
        "updated",
    }
    return {key: row[key] for key in sorted(allowed) if key in row}


def _safe_expected_source(row: dict[str, Any]) -> dict[str, str]:
    allowed = {
        "source_app_id",
        "source_host",
        "source_identity",
        "source_kind",
        "source_resource_id",
    }
    return {
        key: str(row[key])
        for key in sorted(allowed)
        if row.get(key) is not None
    }


def _safe_sniffer_status(row: dict[str, Any]) -> dict[str, Any]:
    channels = row.get("channels")
    safe: dict[str, Any] = {}
    if isinstance(channels, dict):
        safe["channels"] = {
            key: channels[key]
            for key in ("available", "running")
            if key in channels
        }
    for key in ("proxy_port", "running", "version"):
        if key in row:
            safe[key] = row[key]
    return safe


def _safe_download_task(row: dict[str, Any]) -> dict[str, Any]:
    """Reduce a downloader response to the fields needed for recovery."""
    meta = row.get("meta")
    opts = meta.get("opts") if isinstance(meta, dict) else None
    req = meta.get("req") if isinstance(meta, dict) else None
    persisted_labels = meta.get("labels") if isinstance(meta, dict) else None
    labels = (
        persisted_labels
        if isinstance(persisted_labels, dict)
        else req.get("labels")
        if isinstance(req, dict)
        else None
    )
    safe_labels = {
        key: labels[key]
        for key in (
            "capture_id",
            "compress",
            "compress_inline",
            "compressed_estimated_size",
            "hls_duration_sec",
            "live_id",
            "media_type",
            "source",
            "source_estimated_size",
            "transcode_progress_percent",
            "type",
        )
        if isinstance(labels, dict) and key in labels
    }
    safe_opts = {
        key: opts[key]
        for key in ("name", "path")
        if isinstance(opts, dict) and key in opts
    }
    progress = row.get("progress")
    safe_progress = {
        key: progress[key]
        for key in ("downloaded", "speed", "used")
        if isinstance(progress, dict) and key in progress
    }
    safe: dict[str, Any] = {
        key: row[key]
        for key in (
            "createdAt",
            "id",
            "name",
            "protocol",
            "status",
            "updatedAt",
        )
        if key in row
    }
    if safe_opts or safe_labels:
        safe["meta"] = {"opts": safe_opts, "labels": safe_labels}
    if safe_progress:
        safe["progress"] = safe_progress
    return safe


def sanitize_capture_event(row: dict[str, Any]) -> dict[str, Any]:
    """Whitelist nested capture state before it reaches disk or stdout."""
    safe = dict(row)
    candidate = safe.get("candidate")
    if isinstance(candidate, dict):
        safe["candidate"] = _safe_candidate(candidate)
    expected_source = safe.get("expected_source")
    if isinstance(expected_source, dict):
        safe["expected_source"] = _safe_expected_source(expected_source)
    task = safe.get("download_task")
    if isinstance(task, dict):
        safe["download_task"] = _safe_download_task(task)
    sniffer_status = safe.get("sniffer_status")
    if isinstance(sniffer_status, dict):
        safe["sniffer_status"] = _safe_sniffer_status(sniffer_status)
    for key in list(safe):
        lowered = key.lower()
        if any(
            marker in lowered
            for marker in (
                "cookie",
                "credential",
                "header",
                "password",
                "query",
                "source_url",
                "token",
                "url",
            )
        ):
            safe.pop(key, None)
    return safe


def resolve_candidate(
    current: dict[str, Any],
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Rehydrate a signed candidate only in memory for the local API call."""
    expected = str(current.get("candidate_key") or "")
    matches = [row for row in candidates if _candidate_key(row) == expected]
    return max(matches, key=_captured_sort_key) if matches else None


class SnifferError(RuntimeError):
    """The local capture adapter is unavailable or returned invalid data."""


class InvalidCheckpoint(ValueError):
    """A requested pipeline checkpoint is not part of the stable state model."""


class InvalidSourcePage(ValueError):
    """A page URL is not a supported Xiaocao capture source."""


_XIAOETONG_LIVE_RESOURCE = re.compile(r"^l_[A-Za-z0-9_-]+$")
_XIAOETONG_VIDEO_RESOURCE = re.compile(r"^v_[A-Za-z0-9_-]+$")
_XIAOETONG_PAGE_VERSION = re.compile(r"^v[0-9]+$")


def canonical_xiaoetong_source(page_url: str) -> dict[str, str]:
    """Return a credential-free stable identity for one Xiaoetong replay page."""
    parsed = urlsplit(str(page_url or "").strip())
    host = (parsed.hostname or "").lower()
    pieces = [piece for piece in parsed.path.split("/") if piece]
    live_page = (
        len(pieces) == 4
        and _XIAOETONG_PAGE_VERSION.fullmatch(pieces[0]) is not None
        and pieces[1:3] == ["course", "alive"]
        and _XIAOETONG_LIVE_RESOURCE.fullmatch(pieces[3]) is not None
    )
    recorded_video_page = (
        len(pieces) == 4
        and pieces[:3] == ["p", "course", "video"]
        and _XIAOETONG_VIDEO_RESOURCE.fullmatch(pieces[3]) is not None
    )
    if (
        parsed.scheme != "https"
        or not host.endswith(".xiaoeknow.com")
        or not (live_page or recorded_video_page)
    ):
        raise InvalidSourcePage("unsupported Xiaoetong replay page")
    app_id = host.split(".", 1)[0]
    resource_id = pieces[3]
    return {
        "source_kind": "xiaoetong",
        "source_host": host,
        "source_app_id": app_id,
        "source_resource_id": resource_id,
        "source_identity": f"xiaoetong:{app_id}:{resource_id}",
    }


def resolve_xiaoetong_h5_page(page_url: str) -> str:
    """Resolve a trusted MP wrapper or H5 URL to a query-free H5 page.

    Xiaoetong's ``*.mp.xiaoeknow.com`` wrapper embeds a base64 JSON payload
    containing the real H5 page.  Every outer/inner app and resource binding is
    checked before the embedded URL is accepted.
    """
    raw = str(page_url or "").strip()
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise InvalidSourcePage("unsupported Xiaoetong replay page")
    if host.endswith(".h5.xiaoeknow.com"):
        canonical_xiaoetong_source(raw)
        return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))
    if not host.endswith(".mp.xiaoeknow.com"):
        raise InvalidSourcePage("unsupported Xiaoetong replay page")

    outer_app_id = host.split(".", 1)[0]
    query = parse_qs(parsed.query, keep_blank_values=False)
    query_app_id = str((query.get("app_id") or [""])[0]).strip()
    encoded = str((query.get("params") or [""])[0]).strip()
    if not encoded or query_app_id != outer_app_id:
        raise InvalidSourcePage("Xiaoetong MP wrapper binding is invalid")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode("utf-8"))
    except (Base64Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InvalidSourcePage("Xiaoetong MP wrapper params are invalid") from exc
    if not isinstance(payload, dict):
        raise InvalidSourcePage("Xiaoetong MP wrapper params are invalid")

    payload_app_id = str(
        payload.get("apparid")
        or payload.get("app_id")
        or payload.get("appid")
        or ""
    ).strip()
    payload_resource_id = str(payload.get("resource_id") or "").strip()
    h5_url = str(payload.get("h5_url") or "").strip()
    source = canonical_xiaoetong_source(h5_url)
    if (
        payload_app_id != outer_app_id
        or source["source_app_id"] != outer_app_id
        or payload_resource_id != source["source_resource_id"]
    ):
        raise InvalidSourcePage("Xiaoetong MP wrapper binding is invalid")
    h5 = urlsplit(h5_url)
    return urlunsplit(
        ("https", source["source_host"], h5.path.rstrip("/"), "", "")
    )


@dataclass(frozen=True)
class SnifferClient:
    base_url: str = DEFAULT_SNIFFER_URL
    timeout: float = 5.0
    opener: Callable[..., Any] = urlopen

    def _json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self.opener(
                request,
                timeout=self.timeout if timeout is None else timeout,
            ) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise SnifferError(f"sniffer request failed: {path}: {exc}") from exc
        if not isinstance(parsed, dict) or int(parsed.get("code", -1)) != 0:
            message = parsed.get("msg") if isinstance(parsed, dict) else "invalid response"
            raise SnifferError(f"sniffer rejected {path}: {message}")
        return parsed

    def status(self) -> dict[str, Any]:
        return dict(self._json("/api/status").get("data") or {})

    def candidates(self) -> list[dict[str, Any]]:
        data = self._json(
            "/api/elive/live/candidates?all=1",
            timeout=max(self.timeout, CANDIDATES_MIN_TIMEOUT_SECONDS),
        ).get("data") or {}
        rows = data.get("list") if isinstance(data, dict) else []
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def tasks(self) -> list[dict[str, Any]]:
        data = self._json("/api/task/list?page_size=500").get("data") or {}
        rows = data.get("list") if isinstance(data, dict) else []
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def arm_xiaoetong_source(self, page_url: str) -> dict[str, str]:
        source = canonical_xiaoetong_source(page_url)
        data = self._json(
            "/api/elive/source-jobs",
            method="POST",
            payload={
                "page_url": page_url,
                "compress": True,
                "source": "xiaocao",
            },
        ).get("data") or {}
        if not isinstance(data, dict):
            raise SnifferError("sniffer returned an invalid source job")
        safe = {
            key: str(data[key])
            for key in ("id", "status", "live_id", "task_id")
            if data.get(key) is not None and str(data[key]).strip()
        }
        if not safe.get("id") or safe.get("live_id") != source["source_resource_id"]:
            raise SnifferError("sniffer source job binding is invalid")
        return safe

    def xiaoetong_source_job(self, job_id: str) -> dict[str, str]:
        expected_id = str(job_id or "").strip()
        if not expected_id:
            raise SnifferError("Xiaoetong source job id is required")
        data = self._json(
            f"/api/elive/source-jobs/{quote(expected_id, safe='')}"
        ).get("data") or {}
        if not isinstance(data, dict):
            raise SnifferError("sniffer returned an invalid source job")
        safe = {
            key: str(data[key])
            for key in (
                "id",
                "status",
                "live_id",
                "candidate_id",
                "task_id",
                "updated_at",
                "error_code",
            )
            if data.get(key) is not None and str(data[key]).strip()
        }
        if safe.get("id") != expected_id or not safe.get("status"):
            raise SnifferError("sniffer source job status binding is invalid")
        return safe

    def retry_xiaoetong_source_job(self, job_id: str) -> dict[str, str]:
        expected_id = str(job_id or "").strip()
        if not expected_id:
            raise SnifferError("Xiaoetong source job id is required")
        data = self._json(
            f"/api/elive/source-jobs/{quote(expected_id, safe='')}/retry",
            method="POST",
        ).get("data") or {}
        if not isinstance(data, dict):
            raise SnifferError("sniffer returned an invalid source job retry")
        safe = {
            key: str(data[key])
            for key in (
                "id",
                "status",
                "live_id",
                "candidate_id",
                "task_id",
                "updated_at",
                "error_code",
            )
            if data.get(key) is not None and str(data[key]).strip()
        }
        if safe.get("id") != expected_id or not safe.get("status"):
            raise SnifferError("sniffer source job retry binding is invalid")
        return safe

    def start_download(self, candidate: dict[str, Any], *, force: bool = False) -> str:
        payload = {
            "url": candidate.get("url"),
            "filename": candidate.get("filename") or "xiaocao-livestream.mp4",
            "dir": "鹅直播视频",
            "extra": {
                # Match the proven /download/live "保存" action. The sniffer
                # only enables inline transcoding and the -compressed output
                # name for this exact task type + flag pair.
                "type": "live_capture",
                "compress": "true",
                "source": "xiaocao",
                "capture_id": str(candidate.get("id") or ""),
                "live_id": str(candidate.get("live_id") or ""),
                "media_type": str(candidate.get("media_type") or "video"),
            },
        }
        if force:
            payload["force"] = True
        data = self._json("/api/task/create2", method="POST", payload=payload).get("data") or {}
        task_id = str(data.get("id") or "") if isinstance(data, dict) else ""
        if not task_id:
            raise SnifferError("sniffer created a download without a task id")
        return task_id


class CaptureJobStore:
    """Append-only state transitions for capture/enrichment jobs."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        row = sanitize_capture_event(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("job_id"):
                    rows.append(sanitize_capture_event(row))
        return rows

    def sanitize_ledger(self) -> dict[str, int]:
        """Atomically remove legacy signed URLs while preserving event order."""
        if not self.path.exists():
            return {"events": 0, "changed": 0}
        raw_lines = self.path.read_text(encoding="utf-8").splitlines()
        clean_rows: list[dict[str, Any]] = []
        changed = 0
        for line in raw_lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not row.get("job_id"):
                continue
            clean = sanitize_capture_event(row)
            clean_rows.append(clean)
            if clean != row:
                changed += 1
        temporary = self.path.with_name(f".{self.path.name}.sanitize-{uuid4().hex}")
        mode = self.path.stat().st_mode
        with temporary.open("x", encoding="utf-8") as handle:
            for row in clean_rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        temporary.replace(self.path)
        return {"events": len(clean_rows), "changed": changed}

    def latest(self, job_id: str | None = None) -> dict[str, Any] | None:
        rows = self.events()
        if job_id is None:
            return rows[-1] if rows else None
        matches = [row for row in rows if row.get("job_id") == job_id]
        return matches[-1] if matches else None

    def arm(
        self,
        candidates: Iterable[dict[str, Any]],
        *,
        source: str = "xiaocao",
        author: str = "小草",
        sniffer_status: dict[str, Any] | None = None,
        expected_source: dict[str, Any] | None = None,
        source_job_id: str | None = None,
    ) -> dict[str, Any]:
        baseline = sorted({_candidate_key(row) for row in candidates})
        now = _now_iso()
        row = {
                "schema_version": 1,
                "event": "armed",
                "job_id": f"kol-{uuid4().hex[:12]}",
                "source": source,
                "author": author,
                "status": "awaiting_capture",
                "created_at": now,
                "updated_at": now,
                "baseline_candidate_keys": baseline,
            }
        if sniffer_status is not None:
            row["sniffer_status"] = _safe_sniffer_status(sniffer_status)
        if expected_source is not None:
            row["expected_source"] = _safe_expected_source(expected_source)
        if source_job_id:
            row["source_job_id"] = str(source_job_id)
        return self._append(row)

    def transition(self, current: dict[str, Any], event: str, **changes: Any) -> dict[str, Any]:
        row = dict(current)
        row.update(changes)
        row["event"] = event
        row["updated_at"] = _now_iso()
        return self._append(row)

    def checkpoint(
        self,
        current: dict[str, Any],
        *,
        status: str,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        if status not in CHECKPOINT_STATUSES:
            raise InvalidCheckpoint(f"unsupported checkpoint status: {status}")
        changes: dict[str, Any] = {"status": status}
        if artifact_path:
            changes["artifact_path"] = artifact_path
        return self.transition(current, f"checkpoint_{status}", **changes)

    def detect_capture(
        self,
        current: dict[str, Any],
        candidates: Iterable[dict[str, Any]],
    ) -> dict[str, Any] | None:
        baseline = set(current.get("baseline_candidate_keys") or [])
        unseen = [row for row in candidates if _candidate_key(row) not in baseline]
        expected_source = current.get("expected_source") or {}
        expected_resource_id = str(expected_source.get("source_resource_id") or "")
        if expected_resource_id:
            unseen = [
                row
                for row in unseen
                if str(row.get("live_id") or row.get("source_resource_id") or "")
                == expected_resource_id
            ]
        if not unseen:
            return None
        candidate = max(unseen, key=_captured_sort_key)
        return self.transition(
            current,
            "capture_detected",
            status="captured",
            candidate=_safe_candidate(candidate),
            candidate_key=_candidate_key(candidate),
        )

    def bind_source_candidate(
        self,
        current: dict[str, Any],
        candidates: Iterable[dict[str, Any]],
        *,
        candidate_id: str,
        allow_latest: bool = False,
    ) -> dict[str, Any] | None:
        """Bind the exact candidate selected by a page-scoped source job."""
        expected_id = str(candidate_id or "").strip()
        expected_source = current.get("expected_source") or {}
        expected_resource_id = str(expected_source.get("source_resource_id") or "")
        source_matches = [
            row
            for row in candidates
            if (
                not expected_resource_id
                or str(row.get("live_id") or row.get("source_resource_id") or "")
                == expected_resource_id
            )
        ]
        matches = [
            row
            for row in source_matches
            if str(row.get("id") or "") == expected_id
        ]
        if not matches and allow_latest:
            matches = source_matches
        if not matches:
            return None
        candidate = max(matches, key=_captured_sort_key)
        return self.transition(
            current,
            "capture_detected",
            status="captured",
            candidate=_safe_candidate(candidate),
            candidate_key=_candidate_key(candidate),
        )

    def reconcile_download(
        self,
        current: dict[str, Any],
        tasks: Iterable[dict[str, Any]],
    ) -> dict[str, Any] | None:
        task_id = str(current.get("download_task_id") or "")
        task = next((row for row in tasks if str(row.get("id") or "") == task_id), None)
        if task is None:
            return None
        status = str(task.get("status") or "").lower()
        if status in TERMINAL_DOWNLOAD_STATUSES:
            next_status = "downloaded"
            event = "download_completed"
        elif status in FAILED_DOWNLOAD_STATUSES:
            next_status = "download_failed"
            event = "download_failed"
        else:
            next_status = "downloading"
            event = "download_progress"
        if next_status == current.get("status") and event == current.get("event"):
            return current
        safe_task = _safe_download_task(task)
        changes: dict[str, Any] = {
            "status": next_status,
            "download_task": safe_task,
        }
        if next_status == "downloaded":
            opts = ((safe_task.get("meta") or {}).get("opts") or {})
            directory = str(opts.get("path") or "").strip()
            filename = str(safe_task.get("name") or opts.get("name") or "").strip()
            if directory and filename:
                changes["media_path"] = str(Path(directory) / filename)
        return self.transition(current, event, **changes)
