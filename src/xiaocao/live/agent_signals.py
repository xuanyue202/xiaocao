"""Appendable ledger for agent/AI-side signals.

Signals here have authority metadata and expiry by construction. They are
shadow/evidence inputs until a separate research gate promotes a deterministic
rule elsewhere.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


def _json_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _stable_key_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_date": str(row.get("market_date") or "")[:10],
        "source": str(row.get("source") or ""),
        "signal_type": str(row.get("signal_type") or ""),
        "scope": str(row.get("scope") or ""),
        "subject": row.get("subject") if isinstance(row.get("subject"), dict) else {},
    }


def stable_key(row: dict[str, Any]) -> str:
    """Revision-stable identity for one agent signal subject.

    Direction/score/label are deliberately excluded so a corrected agent review
    replaces the older active signal instead of leaving contradictory entries.
    """
    return _json_hash(_stable_key_payload(row))


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def make_signal(
    *,
    market_date: str,
    source: str,
    signal_type: str,
    scope: str,
    subject: dict[str, Any],
    direction: str,
    score: float,
    label: str,
    summary: str,
    evidence_ref: str,
    authority: int = 0,
    horizon_days: int = 1,
    expires_at: str | None = None,
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market_d = _parse_date(market_date) or date.today()
    expiry = expires_at or (market_d + timedelta(days=max(1, horizon_days + 1))).isoformat()
    core = {
        "market_date": market_d.isoformat(),
        "source": source,
        "signal_type": signal_type,
        "scope": scope,
        "subject": subject,
        "direction": direction,
        "score": round(float(score), 4),
        "label": label,
    }
    identity = stable_key(core)
    return {
        "schema_version": 1,
        "id": identity,
        "stable_key": identity,
        "revision_id": _json_hash(core),
        **core,
        "summary": summary,
        "evidence_ref": evidence_ref,
        "authority": int(authority),
        "horizon_days": int(horizon_days),
        "expires_at": expiry,
        "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
        "status": "active",
        "metadata": metadata or {},
    }


def read_signals(path: Path, *, as_of: str | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    now_d = _parse_date(as_of or date.today().isoformat())
    by_id: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = str(row.get("id") or "")
            if not sid:
                continue
            by_id[sid] = row
    rows = list(by_id.values())
    if now_d:
        for row in rows:
            expiry = _parse_date(str(row.get("expires_at") or ""))
            if expiry and expiry < now_d and row.get("status") == "active":
                row["status"] = "expired"
    rows.sort(key=lambda r: (str(r.get("market_date") or ""), str(r.get("id") or "")))
    return rows


def upsert_signals(path: Path, signals: list[dict[str, Any]]) -> None:
    if not signals:
        return
    existing: dict[str, dict[str, Any]] = {}
    for row in read_signals(path):
        key = str(row.get("stable_key") or stable_key(row))
        if key:
            row["stable_key"] = key
            existing[key] = row
    for signal in signals:
        key = str(signal.get("stable_key") or stable_key(signal))
        if key:
            signal["stable_key"] = key
            signal["id"] = key
            existing[key] = signal
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(existing.values(), key=lambda r: (str(r.get("market_date") or ""), str(r.get("id") or "")))
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def signals_from_intelligence_records(
    records: list[dict[str, Any]],
    *,
    evidence_path: str = "output/live/stock_sentiment_history.jsonl",
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in records:
        code = str(row.get("code") or "")
        market_date = str(row.get("date") or "")[:10]
        if not code or not market_date:
            continue
        ref = f"{evidence_path}#date={market_date}&code={code}"
        has_short = str(row.get("score_source") or "") == "agent_review" and row.get("agent_short_score") not in (None, "")
        if has_short:
            score = float(row.get("agent_short_score") or 0.0)
            if score >= 0.2:
                direction = "bullish"
            elif score <= -0.2:
                direction = "bearish"
            else:
                direction = "neutral"
            out.append(make_signal(
                market_date=market_date,
                source="stock_intelligence",
                signal_type="ai_intelligence_short_factor",
                scope="stock",
                subject={"kind": "stock", "code": code, "name": row.get("name", "")},
                direction=direction,
                score=score,
                label=str(row.get("label") or ""),
                summary=str(row.get("summary") or ""),
                evidence_ref=ref,
                authority=int(row.get("authority", 0) or 0),
                horizon_days=1,
                created_at=created_at,
                metadata={
                    "source": row.get("source"),
                    "target_set": row.get("target_set"),
                    "data_quality": row.get("data_quality"),
                    "score_source": row.get("score_source"),
                    "action_bias": row.get("agent_action_bias"),
                    "horizon": row.get("horizon") or row.get("agent_horizon"),
                    "usage": row.get("usage") if isinstance(row.get("usage"), dict) else {},
                    "veto_flags": row.get("veto_flags") or [],
                },
            ))
        trend_score_raw = row.get("agent_trend_score")
        if trend_score_raw not in (None, ""):
            trend_score = float(trend_score_raw or 0.0)
            if trend_score >= 0.2:
                trend_direction = "bullish"
            elif trend_score <= -0.2:
                trend_direction = "bearish"
            else:
                trend_direction = "neutral"
            out.append(make_signal(
                market_date=market_date,
                source="stock_intelligence",
                signal_type="ai_intelligence_trend_factor",
                scope="stock",
                subject={"kind": "stock", "code": code, "name": row.get("name", "")},
                direction=trend_direction,
                score=trend_score,
                label=str(row.get("trend_label") or ""),
                summary=str(row.get("trend_summary") or row.get("agent_thesis") or row.get("summary") or ""),
                evidence_ref=ref,
                authority=int(row.get("authority", 0) or 0),
                horizon_days=20,
                created_at=created_at,
                metadata={
                    "source": row.get("source"),
                    "target_set": row.get("target_set"),
                    "data_quality": row.get("data_quality"),
                    "score_source": row.get("score_source"),
                    "action_bias": row.get("agent_action_bias"),
                    "horizon": "trend",
                    "usage": row.get("usage") if isinstance(row.get("usage"), dict) else {},
                    "veto_flags": row.get("veto_flags") or [],
                },
            ))
    return out


def score_signals_against_training_rows(
    signals: list[dict[str, Any]],
    training_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    returns: dict[tuple[str, str], float] = {}
    for row in training_rows:
        key = (str(row.get("date") or "")[:10], str(row.get("code") or ""))
        if not key[0] or not key[1]:
            continue
        value = row.get("net_realized_ret", row.get("realized_ret"))
        try:
            returns[key] = float(value)
        except (TypeError, ValueError):
            continue

    outcomes: list[dict[str, Any]] = []
    for signal in signals:
        subject = signal.get("subject") if isinstance(signal.get("subject"), dict) else {}
        key = (str(signal.get("market_date") or "")[:10], str(subject.get("code") or ""))
        if key not in returns:
            outcomes.append({"signal_id": signal.get("id"), "status": "open", "return": None})
            continue
        ret = returns[key]
        direction = str(signal.get("direction") or "neutral")
        if direction == "bullish":
            correct = ret > 0
        elif direction == "bearish":
            correct = ret <= 0
        else:
            correct = None
        outcomes.append({
            "signal_id": signal.get("id"),
            "status": "scored" if correct is not None else "neutral",
            "return": ret,
            "correct": correct,
            "direction": direction,
        })

    scored = [o for o in outcomes if o.get("status") == "scored"]
    by_direction = Counter(str(o.get("direction")) for o in scored)
    correct_n = sum(1 for o in scored if o.get("correct") is True)
    mean_ret = sum(float(o.get("return") or 0.0) for o in scored) / len(scored) if scored else None
    return {
        "n_signals": len(signals),
        "n_scored": len(scored),
        "n_open": sum(1 for o in outcomes if o.get("status") == "open"),
        "hit_rate": (correct_n / len(scored)) if scored else None,
        "mean_return": mean_ret,
        "by_direction": dict(by_direction),
        "outcomes": outcomes,
    }
