"""Evidence-bound acceptance checks for native WeChat Xiaocao captures."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen


JsonFetcher = Callable[[str], dict[str, Any]]
MediaProbe = Callable[[Path], bool]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict) or int(value.get("code", -1)) != 0:
        raise ValueError(f"unexpected sniffer response: {url}")
    return value


def _probe_media(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return False
    try:
        value = json.loads(result.stdout)
        duration = float((value.get("format") or {}).get("duration") or 0)
        streams = value.get("streams") or []
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return duration > 0 and any(
        isinstance(stream, dict) and stream.get("codec_type") == "video"
        for stream in streams
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reconciled_full_artifact(capture: dict[str, Any], labels: dict[str, Any]) -> bool:
    """Independently recheck a full artifact, without rewriting provider pause."""
    if (
        capture.get("event") != "download_completed_reconciled"
        or capture.get("provider_status_observed") != "pause"
        or capture.get("reconciliation_reason") != "sniffer_interrupted_after_complete_media"
    ):
        return False
    media = Path(str(capture.get("media_path") or "")).expanduser()
    task = capture.get("download_task") or {}
    task_options = (task.get("meta") or {}).get("opts") or {}
    task_name = str(task.get("name") or task_options.get("name") or "")
    if not media.is_file() or not media.name.endswith("-compressed.mp4"):
        return False
    if task_name != media.name:
        return False
    if media.with_name(media.name.removesuffix("-compressed.mp4") + ".mp4").exists():
        return False
    try:
        expected = float(labels.get("hls_duration_sec") or 0)
        recorded_expected = float(capture.get("expected_duration_seconds") or 0)
        recorded_duration = float(capture.get("media_duration_seconds") or 0)
        if (
            not all(math.isfinite(v) for v in (expected, recorded_expected, recorded_duration))
            or expected < 60 or recorded_expected != expected
            or media.stat().st_size != capture.get("media_size_bytes")
        ):
            return False
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(media)],
            check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False
        actual = float(json.loads(result.stdout)["format"]["duration"])
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        return False
    tolerance = max(15.0, expected * 0.01)
    return (
        math.isfinite(actual) and actual >= 60
        and abs(actual - expected) <= tolerance
        and abs(recorded_duration - actual) <= 1.0
    )


def _at_or_after(value: Any, not_before: str | None) -> bool:
    if not not_before:
        return True
    try:
        return datetime.fromisoformat(str(value)) >= datetime.fromisoformat(not_before)
    except ValueError:
        return False


def inspect_identity(
    subscription_dir: Path,
    identity: str,
    *,
    sniffer_url: str = "http://127.0.0.1:2022",
    not_before: str | None = None,
    fetch_json: JsonFetcher = _fetch_json,
    probe_media: MediaProbe = _probe_media,
) -> dict[str, Any]:
    """Return an auditable verdict for one manifest identity."""

    manifest = _read_json(subscription_dir / "manifest.json")
    item = (manifest.get("items") or {}).get(identity)
    if not isinstance(item, dict):
        return {
            "identity": identity,
            "passed": False,
            "checks": {"manifest_item": False},
        }

    source_identity = str(item.get("source_identity") or "")
    live_id = source_identity.rsplit(":", 1)[-1] if source_identity else ""
    capture_job_id = str(item.get("capture_job_id") or "")
    item_dir = subscription_dir / "items" / identity
    capture_rows = _read_jsonl(item_dir / "capture_jobs.jsonl")
    capture_rows = [row for row in capture_rows if row.get("job_id") == capture_job_id]
    capture = capture_rows[-1] if capture_rows else {}
    event_rows = _read_jsonl(item_dir / "events.jsonl")

    source_job_id = next(
        (
            str(row.get("source_job_id") or "")
            for row in reversed(capture_rows)
            if row.get("source_job_id")
        ),
        "",
    )
    source_job: dict[str, Any] = {}
    completed_snapshot = capture.get("status") == "downloaded"
    snapshot_task = capture.get("download_task") or {}
    snapshot_meta = snapshot_task.get("meta") or {}
    snapshot_labels = snapshot_meta.get("labels") or (snapshot_meta.get("req") or {}).get("labels") or {}
    snapshot_candidate = capture.get("candidate") or {}
    reconciled_artifact = (
        completed_snapshot and snapshot_task.get("status") == "pause"
        and _reconciled_full_artifact(capture, snapshot_labels)
    )
    snapshot_bound = (
        completed_snapshot
        and bool(capture.get("download_task_id"))
        and snapshot_task.get("id") == capture.get("download_task_id")
        and (snapshot_task.get("status") == "done" or reconciled_artifact)
        and (capture.get("expected_source") or {}).get("source_identity") == source_identity
        and bool(snapshot_candidate.get("id"))
        and snapshot_candidate.get("live_id") == live_id
        and capture.get("candidate_key") == f"live:{live_id}"
        and capture.get("candidate_key") not in (capture.get("baseline_candidate_keys") or [])
        and snapshot_labels.get("capture_id") == snapshot_candidate.get("id")
        and snapshot_labels.get("live_id") == live_id
        and snapshot_labels.get("type") == "live_capture"
        and str(snapshot_labels.get("compress")).lower() == "true"
        and str(snapshot_labels.get("compress_inline")).lower() == "true"
    )
    if snapshot_bound and source_job_id and capture.get("source_task_id") == snapshot_task.get("id"):
        # Projection of the persisted capture receipt, not a fabricated live API response.
        source_job = {
            "id": source_job_id, "live_id": snapshot_candidate.get("live_id"),
            "status": capture.get("source_job_status"),
            "task_id": capture.get("source_task_id"),
        }
    elif source_job_id and not completed_snapshot:
        value = fetch_json(
            f"{sniffer_url.rstrip('/')}/api/elive/source-jobs/{source_job_id}"
        )
        data = value.get("data")
        if isinstance(data, dict):
            source_job = data

    task_id = str(source_job.get("task_id") or capture.get("download_task_id") or "")
    task: dict[str, Any] = snapshot_task if snapshot_bound else {}
    if task_id and not completed_snapshot:
        value = fetch_json(
            f"{sniffer_url.rstrip('/')}/api/task/list?page_size=500"
        )
        rows = (value.get("data") or {}).get("list") or []
        task = next(
            (
                row
                for row in rows
                if isinstance(row, dict) and str(row.get("id") or "") == task_id
            ),
            {},
        )

    media = next(
        (
            row
            for row in reversed(event_rows)
            if row.get("event") == "media_validated"
            and str(row.get("capture_job_id") or "") == capture_job_id
            and str(row.get("live_id") or "") == live_id
        ),
        {},
    )
    handoff = next(
        (
            row
            for row in reversed(event_rows)
            if row.get("event") == "cloud_handoff_published"
            and str(row.get("capture_job_id") or "") == capture_job_id
            and str(row.get("live_id") or "") == live_id
        ),
        {},
    )
    media_path = Path(str(media.get("media_path") or "")).expanduser()
    media_exists = media_path.is_file()
    expected_sha256 = str(media.get("media_sha256") or "")
    hash_matches = (
        media_exists
        and len(expected_sha256) == 64
        and _sha256_file(media_path) == expected_sha256
    )
    media_is_valid = media_exists and probe_media(media_path)
    if reconciled_artifact:
        reconciled_artifact = (
            media_path.resolve() == Path(str(capture.get("media_path") or "")).expanduser().resolve()
        )
    task_meta = task.get("meta") or {}
    task_labels = task_meta.get("labels") or (task_meta.get("req") or {}).get("labels") or {}
    native_source_bound = (
        item.get("entry_kind") == "wechat_mini_program"
        and any(row.get("event") == "mini_program_source_bound" for row in capture_rows)
        and (capture.get("expected_source") or {}).get("source_identity") == source_identity
        and (capture.get("candidate") or {}).get("live_id") == live_id
        and bool(item.get("candidate_id"))
        and (capture.get("candidate") or {}).get("id") == item.get("candidate_id")
        and task_labels.get("capture_id") == item.get("candidate_id")
        and task_labels.get("live_id") == live_id
        and task_labels.get("type") == "live_capture"
        and str(task_labels.get("compress")).lower() == "true"
    )

    checks = {
        "manifest_item": True,
        "wechat_mini_program_surface": (
            item.get("playback_surface") == "wechat_mini_program"
        ),
        "media_request_observed": item.get("media_request_observed") is True,
        "no_protection_terminal": item.get("observed_page_state")
        in {"mini_program_media_observed", "playable"},
        "source_job_bound": native_source_bound or (
            bool(source_job_id)
            and source_job.get("id") == source_job_id
            and source_job.get("live_id") == live_id
        ),
        "source_task_created": bool(task_id) and (
            native_source_bound or source_job.get("status") == "task_created"
        ),
        "download_completion_verified": task.get("status") == "done" or (
            snapshot_bound and reconciled_artifact
        ),
        "media_validated": bool(media),
        "media_file_exists": media_exists,
        "media_sha256_matches": hash_matches,
        "media_probe_valid": media_is_valid,
        "cloud_handoff_published": bool(handoff),
        "manifest_closed": item.get("status") in {"handoff_ready", "completed"},
        "accepted_after_boundary": _at_or_after(
            media.get("updated_at"), not_before
        ),
    }
    return {
        "identity": identity,
        "live_id": live_id,
        "capture_job_id": capture_job_id,
        "source_job_id": source_job_id,
        "task_id": task_id,
        "download_task_status": str(snapshot_task.get("status") or task.get("status") or ""),
        "download_completion_basis": (
            "reconciled_full_artifact" if snapshot_bound and reconciled_artifact
            else "provider_done" if task.get("status") == "done" else "unverified"
        ),
        "task_evidence_origin": "capture_ledger" if completed_snapshot else "live_sniffer",
        "media_path": str(media_path) if media_exists else "",
        "checks": checks,
        "passed": all(checks.values()),
    }


def inspect_acceptance(
    subscription_dir: Path,
    identities: list[str],
    *,
    required_count: int,
    sniffer_url: str = "http://127.0.0.1:2022",
    not_before: str | None = None,
    fetch_json: JsonFetcher = _fetch_json,
    probe_media: MediaProbe = _probe_media,
) -> dict[str, Any]:
    rows = [
        inspect_identity(
            subscription_dir,
            identity,
            sniffer_url=sniffer_url,
            not_before=not_before,
            fetch_json=fetch_json,
            probe_media=probe_media,
        )
        for identity in identities
    ]
    live_ids = [str(row.get("live_id") or "") for row in rows]
    passed_rows = [row for row in rows if row.get("passed") is True]
    distinct_live_ids = {live_id for live_id in live_ids if live_id}
    passed = (
        len(identities) >= required_count
        and len(passed_rows) == len(identities)
        and len(distinct_live_ids) == len(identities)
    )
    return {
        "status": "passed" if passed else "failed",
        "required_count": required_count,
        "identity_count": len(identities),
        "distinct_live_id_count": len(distinct_live_ids),
        "items": rows,
    }
