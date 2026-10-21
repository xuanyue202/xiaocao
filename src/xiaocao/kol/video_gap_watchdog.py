"""Read-only business checks independent of capture source execution/locks."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .xiaocao_wechat import DEFAULT_CONTACT, parse_xiaocao_live_messages

CHINA = ZoneInfo("Asia/Shanghai")
SHA256 = re.compile(r"[0-9a-f]{64}")


def completed_trade_days(rows: list[dict[str, Any]], now: datetime, count: int = 2) -> list[str]:
    """Require exchange evidence; the video day completes at22:00 China time."""
    local = now.astimezone(CHINA)
    cutoff = local.date() if local.time() >= time(22) else local.date() - timedelta(days=1)
    days = set()
    for row in rows:
        raw = str(row.get("calDate") or row.get("tradeDate") or row.get("date") or "")
        if re.fullmatch(r"\d{8}", raw):
            raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        day = date.fromisoformat(raw)
        if row.get("isOpen", row.get("is_open")) not in (1, "1", True, "true", "TRUE", "open", "OPEN"):
            raise ValueError("calendar_open_status_unproven")
        if day <= cutoff:
            days.add(day.isoformat())
    selected = sorted(days)[-count:]
    if count < 1 or len(selected) != count:
        raise ValueError("calendar_coverage_incomplete")
    return selected


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    # A concurrent partial append is degraded evidence; never silently skip it.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _item_state(root: Path, item: dict[str, Any], acknowledgments: list[dict[str, Any]]) -> dict[str, Any]:
    identity = item["identity"]
    if not re.fullmatch(r"kol-wechat-[0-9a-f]{24}", identity):
        raise ValueError("subscription_identity_invalid")
    capture_id = str(item.get("capture_job_id") or "")
    events = _rows(root / "items" / identity / "events.jsonl")
    captures = [r for r in _rows(root / "items" / identity / "capture_jobs.jsonl")
                if r.get("job_id") == capture_id]
    capture = captures[-1] if captures else {}
    validated = [r for r in events if r.get("capture_job_id") == capture_id
                 and r.get("event") == "media_validated"
                 and SHA256.fullmatch(str(r.get("media_sha256") or ""))]
    media = validated[-1] if validated else {}
    # Historical rejected bytes never count after a same-item repair version.
    acquired = bool(media and capture.get("status") == "downloaded"
                    and media.get("media_path") == capture.get("media_path")
                    and not any(r.get("event") == "media_integrity_rejected"
                                and r.get("media_sha256") == media["media_sha256"] for r in events))
    cloud_recorded = any(r.get("event") == "cloud_handoff_published"
                         and r.get("capture_job_id") == capture_id
                         and r.get("media_sha256") == media.get("media_sha256") for r in events)
    handoff = bool(acquired and cloud_recorded and item.get("status") == "completed"
                   and item.get("mailbox_readback_status") in {"created", "already_present", "pending", "acked"}
                   and item.get("handoff_id") == item.get("mailbox_message_id")
                   and SHA256.fullmatch(str(item.get("mailbox_message_id") or ""))
                   and SHA256.fullmatch(str(item.get("mailbox_content_sha256") or "")))
    ack = any(r.get("event") == "mailbox_ack_observed"
              and r.get("handoff_id") == item.get("mailbox_message_id")
              and r.get("content_sha256") == item.get("mailbox_content_sha256")
              and (r.get("receipt") or {}).get("operation") == "ack_mailbox_message"
              and (r.get("receipt") or {}).get("mailbox_id") == "kol.handoff"
              and (r.get("receipt") or {}).get("message_id") == item.get("mailbox_message_id")
              and (r.get("receipt") or {}).get("content_sha256") == item.get("mailbox_content_sha256")
              for r in acknowledgments)
    progress_times = [capture.get("updated_at")]
    progress_times.extend(r.get("updated_at") for r in events if capture_id and r.get("capture_job_id") == capture_id)
    progress = [datetime.fromisoformat(t) for t in progress_times if t]
    timestamps = [item.get("updated_at") or item["published_at"], *progress_times]
    last_evidence_at = max(datetime.fromisoformat(t) for t in timestamps if t).isoformat()
    return {"identity": identity, "published_at": item["published_at"], "last_evidence_at": last_evidence_at,
            "capture_progress_at": max(progress).isoformat() if progress else None,
            "capture_job_id": capture_id, "stage": item.get("status", "not_discovered"),
            "media_receipted": acquired, "handoff_recorded": handoff,
            "media_received_at": media.get("updated_at") if acquired else None,
            "remote_ack_recorded": bool(handoff and ack),
            "user_excluded": item.get("manual_backfill_excluded") is True}


def inspect_video_gaps(root: Path, trade_days: list[str], now: datetime,
                       history: dict[str, Any], grace_hours: int = 6, *,
                       coverage_start: str | None = None,
                       acknowledgments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """No native, source claims, capture, media validation writes, or MCP effects."""
    if history.get("chat") != DEFAULT_CONTACT:
        raise ValueError("history_contact_mismatch")
    observed = parse_xiaocao_live_messages(history)
    manifest = json.loads((root / "manifest.json").read_text())
    items = manifest["items"]
    start = datetime.combine(date.fromisoformat(coverage_start or trade_days[0]), time(), CHINA)
    snapshots = [_item_state(root, i, acknowledgments or []) for i in items.values()]
    states = {s["identity"]: s for s in snapshots if datetime.fromisoformat(s["published_at"]) >= start
              or (s["capture_progress_at"] and datetime.fromisoformat(s["capture_progress_at"]) >= start)}
    for original in observed:
        if datetime.fromisoformat(original["published_at"]) < start:
            continue
        stored = items.get(original["identity"])
        if stored is not None and any(stored.get(k) != original.get(k) for k in
                                      ("contact_username", "published_at", "message_sha256")):
            raise ValueError("history_original_binding_changed")
        if stored is None:
            states[original["identity"]] = {"identity": original["identity"],
                "published_at": original["published_at"], "capture_job_id": "",
                "stage": "not_discovered", "media_receipted": False,
                "media_received_at": None, "remote_ack_recorded": False,
                "handoff_recorded": False, "user_excluded": False}
    eligible = [s for s in states.values() if not s["user_excluded"]]
    source_counts = {day: sum(s["media_receipted"] and s["published_at"][:10] == day for s in eligible)
              for day in trade_days}
    counts = {day: sum(bool(s["media_received_at"]) and datetime.fromisoformat(s["media_received_at"]).astimezone(CHINA).date().isoformat() == day for s in eligible)
              for day in trade_days}
    received_today = sum(bool(s["media_received_at"]) and datetime.fromisoformat(s["media_received_at"]).astimezone(CHINA).date() == now.astimezone(CHINA).date() for s in eligible)
    gaps = [s for s in eligible if not s["handoff_recorded"]
            and datetime.fromisoformat(s["published_at"]) <= now - timedelta(hours=grace_hours)]
    gaps.sort(key=lambda s: (s["published_at"], s["identity"]))
    excluded_days = [day for day in trade_days if any(s["published_at"][:10] == day for s in states.values())
                     and all(s["user_excluded"] for s in states.values() if s["published_at"][:10] == day)]
    zero_streak = all(counts[day] == 0 and day not in excluded_days for day in trade_days) and received_today == 0
    return {"status": "action_required" if zero_streak or gaps else "healthy",
            "observed_at": now.isoformat(), "completed_trade_days": trade_days,
            "media_receipt_counts": counts, "consecutive_no_video": zero_streak,
            "source_day_media_coverage": source_counts, "media_receipts_today": received_today,
            "explicitly_excluded_days": excluded_days,
            "gaps": gaps, "history_checked": True, "coverage_start": start.date().isoformat(),
            "items": sorted(states.values(), key=lambda s: (s["published_at"], s["identity"])),
            "acceptance_note": "Recorded local receipts only; authoritative cloud/mailbox acceptance remains separate."}


def notification_transition(result: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Persist dedupe only in watchdog output; never mutate source ledgers."""
    stable = {k: result[k] for k in ("status", "completed_trade_days", "media_receipt_counts") if k in result}
    stable["gaps"] = [{k: item.get(k) for k in ("identity", "capture_job_id", "stage",
        "media_receipted", "handoff_recorded", "remote_ack_recorded", "user_excluded")}
        for item in result.get("gaps", [])]
    stable["receipt_states"] = [{k: item.get(k) for k in
        ("identity", "media_receipted", "handoff_recorded", "remote_ack_recorded")}
        for item in result.get("items", [])]
    if result.get("status") == "degraded":
        stable["failure_code"] = result["failure_code"]
    fingerprint = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
    changed = fingerprint != (previous or {}).get("fingerprint")
    recovery = result["status"] == "healthy" and (previous or {}).get("status") in {"degraded", "action_required"}
    return {**result, "fingerprint": fingerprint,
            "notify": changed and (result["status"] != "healthy" or recovery)}
