"""Offline, same-job correction of a transcription error before download.

Never edit a running source manager's ledger. Preserve IDs, baselines and all
historical rows; the downloader must reload and authoritatively create its task.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .capture import canonical_xiaoetong_source


def corrected_rows(item: dict, capture: dict, job: dict, page_url: str,
                   candidate: dict, evidence: dict, now: str) -> tuple[dict, dict, dict]:
    source = canonical_xiaoetong_source(page_url)
    old = capture.get("expected_source") or {}
    if (item.get("capture_job_id") != capture.get("job_id")
            or capture.get("source_job_id") != job.get("id")
            or old.get("source_identity") != item.get("source_identity")
            or old.get("source_resource_id") != job.get("live_id")
            or source["source_app_id"] != job.get("app_id")
            or source["source_identity"] == old.get("source_identity")):
        raise ValueError("repair identity binding mismatch")
    if (capture.get("status") != "awaiting_capture"
            or item.get("status") not in {"capture_armed", "awaiting_playback"}
            or job.get("status") != "awaiting_playback"
            or any(capture.get(k) for k in ("download_task_id", "source_task_id", "candidate"))
            or any(job.get(k) for k in ("candidate_id", "task_id", "error_code"))):
        raise ValueError("repair requires an untouched pre-download job")
    if any(item.get(key) for key in ("handoff_id", "handoff_path", "mailbox_message_id")):
        raise ValueError("repair cannot change an existing handoff")
    live = source["source_resource_id"]
    captured = datetime.fromisoformat(candidate["captured"])
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    if (candidate.get("live_id") != live or not candidate.get("id")
            or candidate["id"] in job["baseline"]["candidate_ids"]
            or f"live:{live}" in capture["baseline_candidate_keys"]
            or captured <= datetime.fromisoformat(job["armed_at"])
            or candidate.get("media_type") != "m3u8"
            or not urlsplit(candidate.get("url", "")).path.endswith("/playlist_eof.m3u8")
            or urlsplit(candidate.get("source_url", "")).hostname
            != f"{source['source_app_id']}.h5.xe-live.com"):
        raise ValueError("repair candidate is not a fresh bound finite replay")
    if (evidence.get("identity") != item["identity"]
            or evidence.get("source_identity") != source["source_identity"]
            or evidence.get("playback_surface") != "wechat_mini_program"
            or evidence.get("media_request_observed") is not True
            or evidence.get("playback_window_closed") is not True):
        raise ValueError("repair requires observed native media and window closure")
    audit = {"previous_source_identity": old["source_identity"],
             "source_identity": source["source_identity"],
             "candidate_id": candidate["id"], "corrected_at": now,
             "reason": "agent_identity_transcription_error"}
    new_job = {**job, "live_id": live, "canonical_page": page_url.split("?")[0],
               "updated_at": now, "identity_correction": audit}
    new_capture = {**capture, "expected_source": source,
                   "event": "source_identity_corrected", "updated_at": now,
                   "identity_correction": audit}
    new_item = {**item, "source_identity": source["source_identity"],
                "source_resource_id": live, "page_url": page_url,
                "status": "playback_activated", "updated_at": now,
                "playback_surface": "wechat_mini_program",
                "observed_page_state": "mini_program_media_observed",
                "media_request_observed": True, "playback_window_closed": True,
                "password_used": evidence.get("password_used") is True,
                "identity_correction": audit}
    return new_item, new_capture, new_job
