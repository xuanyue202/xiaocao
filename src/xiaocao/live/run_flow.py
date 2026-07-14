"""Structured diagnostics for automation run flow.

The automation shell remains the source of execution; this module turns its log
lines into machine-readable step events and snapshots.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_LINE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<message>.*)$")


def classify_message(message: str) -> str:
    text = message.lower()
    if ("data health" in text and ("critical" in text or "skip" in text)) or "fallback_timeout" in text:
        return "degraded"
    if "hard_stop" in text or "critical" in text or "failed" in text or "error" in text:
        return "failed"
    if "skipping" in text or "skip" in text:
        return "skipped"
    if "done" in text or "complete" in text or "完成" in message:
        return "succeeded"
    return "info"


def step_key(message: str) -> str:
    text = re.sub(r"`[^`]+`", "", message)
    text = re.split(r"[:：(|（]", text, maxsplit=1)[0]
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_")
    return text[:80] or "event"


def event(
    *,
    automation: str,
    market_date: str,
    step: str,
    status: str,
    message: str = "",
    ts: str | None = None,
    log_path: str = "",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "automation": automation,
        "market_date": market_date[:10],
        "step": step,
        "status": status,
        "message": message,
        "ts": ts or datetime.now().isoformat(timespec="seconds"),
        "log_path": log_path,
        "detail": detail or {},
    }


def events_from_log(*, automation: str, market_date: str, log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return [event(
            automation=automation,
            market_date=market_date,
            step="log_missing",
            status="failed",
            message=f"log missing: {log_path}",
            log_path=str(log_path),
        )]
    out: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = LOG_LINE_RE.match(line)
            if not m:
                continue
            message = m.group("message").strip()
            if not message:
                continue
            out.append(event(
                automation=automation,
                market_date=market_date,
                step=step_key(message),
                status=classify_message(message),
                message=message,
                ts=m.group("ts"),
                log_path=str(log_path),
            ))
    return out


def build_snapshot(
    *,
    automation: str,
    market_date: str,
    events: list[dict[str, Any]],
    exit_code: int = 0,
    supporting_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    counts = Counter(str(e.get("status") or "unknown") for e in events)
    if exit_code != 0:
        deterministic_status = "failed"
    elif counts.get("failed", 0) > 0:
        deterministic_status = "failed"
    elif counts.get("skipped", 0) > 0:
        deterministic_status = "completed_with_skips"
    else:
        deterministic_status = "succeeded"
    health = dict(supporting_health or {"status": "healthy", "issues": []})
    health.setdefault("issues", [])
    if counts.get("degraded", 0) > 0:
        health["status"] = "degraded"
        health["issues"] = list(health["issues"]) + [
            {
                "surface": "run_log",
                "detail": str(row.get("message") or row.get("step") or "degraded event"),
            }
            for row in events if row.get("status") == "degraded"
        ]
    health.setdefault("status", "healthy")
    if deterministic_status == "failed":
        status = "failed"
    elif health.get("status") == "degraded":
        status = "degraded"
    else:
        status = deterministic_status
    return {
        "schema_version": 1,
        "automation": automation,
        "market_date": market_date[:10],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "exit_code": exit_code,
        "status": status,
        "deterministic_status": deterministic_status,
        "supporting_health": health,
        "counts": dict(counts),
        "steps": events,
    }


def supporting_health_from_live(
    *,
    live_dir: Path,
    market_date: str,
    posture_path: Path | None = None,
) -> dict[str, Any]:
    """Summarize optional sensor/cortex health without changing main-chain truth."""
    from xiaocao.live import data_health

    issues: list[dict[str, Any]] = []
    health = data_health.check(live_dir, today=market_date)
    if health.get("critical") or health.get("warn"):
        issues.append({
            "surface": "data_health",
            "severity": "critical" if health.get("critical") else "warn",
            "detail": f"critical={health.get('critical', 0)} warn={health.get('warn', 0)}",
        })

    history = live_dir / "stock_sentiment_history.jsonl"
    reviewed_codes: set[str] = set()
    legacy_pending_codes: set[str] = set()
    if history.exists():
        for line in history.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("date") or "")[:10] != market_date[:10]:
                continue
            if row.get("score_source") == "agent_review":
                reviewed_codes.add(str(row.get("code") or ""))
            elif row.get("score_source") == "pending_agent_review":
                legacy_pending_codes.add(str(row.get("code") or ""))
    queue_path = live_dir / f"intelligence_review_queue_{market_date[:10]}.json"
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        queue = {}
    selected_codes = {
        str(item.get("code") or "")
        for item in (queue.get("items") or [])
        if item.get("code")
    }
    pending_codes = (
        selected_codes - reviewed_codes
        if selected_codes
        else legacy_pending_codes - reviewed_codes
    )
    reviewed = len(reviewed_codes)
    pending = len(pending_codes)
    if pending:
        issues.append({
            "surface": "agent_review",
            "severity": "warn",
            "detail": f"reviewed={reviewed} pending={pending}; base-pick fallback active",
        })

    if posture_path is None:
        posture_path = Path(__file__).resolve().parents[3] / "reference" / "experience" / "posture_current.json"
    try:
        posture = json.loads(posture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        posture = {}
    valid_until = str(posture.get("valid_until") or "")[:10]
    if not valid_until or market_date[:10] > valid_until:
        issues.append({
            "surface": "posture",
            "severity": "warn",
            "detail": f"valid_until={valid_until or 'missing'} market_date={market_date[:10]}",
        })
    return {
        "status": "degraded" if issues else "healthy",
        "issues": issues,
        "agent_review": {
            "selected": len(selected_codes),
            "reviewed": reviewed,
            "pending": pending,
        },
        "posture_valid_until": valid_until or None,
    }


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def upsert_snapshot_event(path: Path, snapshot: dict[str, Any], *, snapshot_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    key = (snapshot.get("market_date"), snapshot.get("automation"))
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("market_date"), row.get("automation")) == key:
                    continue
                rows.append(row)
    rows.append({
        "schema_version": 1,
        "type": "run_flow_snapshot",
        "market_date": snapshot.get("market_date"),
        "automation": snapshot.get("automation"),
        "status": snapshot.get("status"),
        "deterministic_status": snapshot.get("deterministic_status"),
        "supporting_health": snapshot.get("supporting_health"),
        "exit_code": snapshot.get("exit_code"),
        "counts": snapshot.get("counts"),
        "snapshot_path": str(snapshot_path),
        "generated_at": snapshot.get("generated_at"),
    })
    rows.sort(key=lambda r: (str(r.get("market_date") or ""), str(r.get("automation") or "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
