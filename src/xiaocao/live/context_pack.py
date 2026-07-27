"""Read-only context pack for agent/human situational awareness."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from xiaocao.live import data_health, status as live_status
from xiaocao.live.agent_signals import read_signals
from xiaocao.live.intelligence_review_queue import build_review_queue


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def file_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "state": "missing", "bytes": 0, "mtime": None}
    stat = path.stat()
    return {
        "path": str(path),
        "state": "available" if stat.st_size else "empty",
        "bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _date_rows(rows: list[dict[str, Any]], market_date: str) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get("date") or r.get("market_date") or "")[:10] == market_date]


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def _compact_signal(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(row, (
        "date", "book", "code", "name", "mode", "rank_score", "primary_score",
        "kp_star", "vb_star", "mode_star", "ai_intelligence_short_star",
        "ai_intelligence_short_score", "stock_sentiment_label",
        "stock_sentiment_data_quality", "intelligence_factor_score_source",
    ))


def _compact_stock_intelligence(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(row, (
        "date", "code", "name", "score_source", "agent_short_score",
        "agent_trend_score", "label", "summary", "data_quality",
        "evidence_state", "authority", "target_set", "target_rank",
        "evidence_freeze_ref",
    ))


def _compact_agent_signal(row: dict[str, Any]) -> dict[str, Any]:
    subject = row.get("subject") if isinstance(row.get("subject"), dict) else {}
    out = _pick(row, (
        "market_date", "signal_type", "direction", "score", "label",
        "authority", "horizon_days", "expires_at", "status", "evidence_ref",
    ))
    out["code"] = subject.get("code")
    out["name"] = subject.get("name")
    return out


def _position_block(live_dir: Path) -> dict[str, Any]:
    rows = _read_jsonl(live_dir / "positions.jsonl")
    open_rows = [r for r in rows if r.get("status", "open") == "open"]
    by_book = Counter(str(r.get("book") or "B") for r in open_rows)
    return {
        "file": file_state(live_dir / "positions.jsonl"),
        "rows": len(rows),
        "open_positions": len(open_rows),
        "open_by_book": dict(by_book),
        "open_sample": open_rows[:8],
    }


def _signal_block(live_dir: Path, market_date: str) -> dict[str, Any]:
    path = live_dir / "signal_snapshots.jsonl"
    rows = _date_rows(_read_jsonl(path), market_date)
    by_book = Counter(str(r.get("book") or "B") for r in rows)
    sentiment_attached = sum(1 for r in rows if "stock_sentiment_score" in r)
    return {
        "file": file_state(path),
        "rows_for_date": len(rows),
        "by_book": dict(by_book),
        "sentiment_attached": sentiment_attached,
        "sample": [_compact_signal(r) for r in rows[:6]],
    }


def _sentiment_block(live_dir: Path, market_date: str) -> dict[str, Any]:
    current_path = live_dir / "stock_sentiment.json"
    history_path = live_dir / "stock_sentiment_history.jsonl"
    rows = _date_rows(_read_jsonl(history_path), market_date)
    return {
        "current_file": file_state(current_path),
        "history_file": file_state(history_path),
        "rows_for_date": len(rows),
        "data_quality": dict(Counter(str(r.get("data_quality") or "legacy") for r in rows)),
        "evidence_state": dict(Counter(str(r.get("evidence_state") or "legacy") for r in rows)),
        "authority": dict(Counter(str(r.get("authority", "legacy")) for r in rows)),
        "sample": [_compact_stock_intelligence(r) for r in rows[:6]],
    }


def _intelligence_evidence_block(live_dir: Path, market_date: str) -> dict[str, Any]:
    path = live_dir / f"intelligence_evidence_{market_date}.jsonl"
    rows = _date_rows(_read_jsonl(path), market_date)
    return {
        "file": file_state(path),
        "rows_for_date": len(rows),
        "data_quality": dict(Counter(str(r.get("data_quality") or "unknown") for r in rows)),
        "universe": dict(Counter(str(r.get("universe") or "unknown") for r in rows)),
    }


def _run_flow_block(live_dir: Path, market_date: str, phase: str) -> dict[str, Any]:
    path = live_dir / f"run_flow_{market_date}_{phase}.json"
    payload = _read_json(path)
    ledger_path = live_dir / "run_flow.jsonl"
    return {
        "snapshot_file": file_state(path),
        "ledger_file": file_state(ledger_path),
        "snapshot": payload or {},
    }


def _agent_signal_block(live_dir: Path, market_date: str) -> dict[str, Any]:
    path = live_dir / "agent_signals.jsonl"
    rows = [r for r in read_signals(path, as_of=market_date) if str(r.get("market_date") or "")[:10] == market_date]
    return {
        "file": file_state(path),
        "rows_for_date": len(rows),
        "by_type": dict(Counter(str(r.get("signal_type") or "unknown") for r in rows)),
        "by_status": dict(Counter(str(r.get("status") or "unknown") for r in rows)),
        "authority": dict(Counter(str(r.get("authority", "unknown")) for r in rows)),
        "sample": [_compact_agent_signal(r) for r in rows[:8]],
    }


def _intelligence_status_block(live_dir: Path, market_date: str, *, review_queue: dict[str, Any] | None = None) -> dict[str, Any]:
    stock_rows = _date_rows(_read_jsonl(live_dir / "stock_sentiment_history.jsonl"), market_date)
    snapshot_rows = _date_rows(_read_jsonl(live_dir / "signal_snapshots.jsonl"), market_date)
    evidence_rows = _date_rows(_read_jsonl(live_dir / f"intelligence_evidence_{market_date}.jsonl"), market_date)
    queue_path = live_dir / f"intelligence_review_queue_{market_date}.json"
    queue_payload = review_queue if isinstance(review_queue, dict) else _read_json(queue_path)
    reviewed = [
        r for r in stock_rows
        if str(r.get("score_source") or "") == "agent_review"
    ]
    actionable_short = [
        r for r in reviewed
        if r.get("agent_short_score") not in (None, "")
        and str(r.get("data_quality") or "legacy") in {"ok", "legacy"}
    ]
    snapshot_actionable = [
        r for r in snapshot_rows
        if str(r.get("intelligence_factor_score_source") or "") == "agent_review"
        and r.get("ai_intelligence_short_score") not in (None, "")
    ]
    hard_veto_reviews = [
        r for r in reviewed
        if isinstance(r.get("veto_flags"), list) and r.get("veto_flags")
    ]
    fallback_to_base = bool(evidence_rows and not actionable_short and not snapshot_actionable)
    if actionable_short or snapshot_actionable:
        status = "actionable_agent_review"
    elif evidence_rows and stock_rows:
        status = "pending_agent_review"
    elif evidence_rows:
        status = "evidence_only"
    else:
        status = "no_evidence"
    queue_counts = queue_payload.get("counts") if isinstance(queue_payload, dict) and isinstance(queue_payload.get("counts"), dict) else {}
    return {
        "status": status,
        "fallback_to_base_pick": fallback_to_base,
        "evidence_rows": len(evidence_rows),
        "stock_intelligence_rows": len(stock_rows),
        "agent_review_rows": len(reviewed),
        "pending_agent_review_rows": sum(1 for r in stock_rows if str(r.get("score_source") or "") == "pending_agent_review"),
        "actionable_short_review_rows": len(actionable_short),
        "snapshot_actionable_rows": len(snapshot_actionable),
        "ai_intelligence_short_star_rows": sum(1 for r in snapshot_rows if bool(r.get("ai_intelligence_short_star"))),
        "hard_veto_review_rows": len(hard_veto_reviews),
        "score_source": dict(Counter(str(r.get("score_source") or "unknown") for r in stock_rows)),
        "review_queue": {
            "file": file_state(queue_path),
            "status": queue_payload.get("status") if isinstance(queue_payload, dict) else "missing",
            "selected_items": queue_counts.get("selected_items", 0),
            "pending_items": queue_counts.get("pending_items", 0),
        },
    }


def build_context_pack(
    *,
    live_dir: Path,
    market_date: str | None = None,
    phase: str = "snapshot",
    now: datetime | None = None,
) -> dict[str, Any]:
    market_date = (market_date or date.today().isoformat())[:10]
    now = now or datetime.now()
    health = data_health.check(live_dir, today=market_date)
    digest = live_status.build_digest(live_dir=live_dir, market_date=market_date, now=now)
    review_queue = build_review_queue(live_dir=live_dir, market_date=market_date, limit=8, now=now)
    return {
        "schema_version": 1,
        "market_date": market_date,
        "phase": phase,
        "generated_at": now.isoformat(timespec="seconds"),
        "read_only": True,
        "fetch_policy": "zero_fetch_existing_artifacts_only",
        "status_digest": digest,
        "data_health": health,
        "positions": _position_block(live_dir),
        "signals": _signal_block(live_dir, market_date),
        "intelligence_status": _intelligence_status_block(live_dir, market_date, review_queue=review_queue),
        "intelligence_evidence": _intelligence_evidence_block(live_dir, market_date),
        "stock_intelligence": _sentiment_block(live_dir, market_date),
        "agent_signals": _agent_signal_block(live_dir, market_date),
        "intelligence_review_queue": review_queue,
        "run_flow": _run_flow_block(live_dir, market_date, phase),
    }


def write_context_pack(path: Path, pack: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
