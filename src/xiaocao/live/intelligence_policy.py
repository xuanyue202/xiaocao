"""Deterministic consumers for agent-reviewed intelligence.

This module never calls a model. It only interprets structured `agent_review`
fields already written into live artifacts, so paper trading and monitoring stay
replayable and auditable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from xiaocao.live import intelligence_evidence


@dataclass(frozen=True)
class IntelligenceTradeConfig:
    mode: str = "on"  # off | shadow | on
    buy_threshold: float = 0.2
    score_bonus: float = 20.0
    veto_min_confidence: float = 0.7
    veto_max_age_days: int = intelligence_evidence.HARD_VETO_DECAY["short_max_age_days"]


@dataclass(frozen=True)
class BuySelection:
    selected: list[dict[str, Any]]
    vetoed: list[dict[str, Any]]
    annotated: list[dict[str, Any]]
    slot_count: int
    mode: str


_PICK_RANK_FIELD = {
    "vb_star": "vb_rank",
    "kp_star": "kp_rank",
    "mode_star": "mode_rank",
}
_SEVERE_TEXT = {"high", "critical", "severe", "major", "material"}


def _num(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_present(row: dict[str, Any], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _flags_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("veto_flags")
    if raw in (None, ""):
        raw = row.get("intelligence_veto_flags")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _severity_ok(value: object) -> bool:
    if isinstance(value, (int, float)):
        return float(value) >= 0.7
    text = str(value or "").strip().lower()
    if not text:
        return False
    if text in _SEVERE_TEXT:
        return True
    return _num(text, 0.0) >= 0.7


def _flag_age_ok(flag: dict[str, Any], *, asof: str | None, max_age_days: int) -> bool:
    if bool(flag.get("ongoing")):
        return True
    raw_date = (
        flag.get("event_time")
        or flag.get("event_date")
        or flag.get("published_at")
        or flag.get("detected_at")
        or flag.get("reviewed_at")
    )
    if raw_date in (None, ""):
        return True
    age = intelligence_evidence.age_days(raw_date, asof=asof)
    return age is not None and age <= max_age_days


def valid_hard_veto_flags(
    row: dict[str, Any],
    *,
    config: IntelligenceTradeConfig = IntelligenceTradeConfig(),
    asof: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for flag in _flags_from_row(row):
        event_type = str(flag.get("event_type") or "").strip()
        if event_type not in intelligence_evidence.HARD_VETO_EVENT_TYPES:
            continue
        if _num(flag.get("confidence"), 0.0) < config.veto_min_confidence:
            continue
        if not _severity_ok(flag.get("severity")):
            continue
        if not _flag_age_ok(flag, asof=asof, max_age_days=config.veto_max_age_days):
            continue
        clean = dict(flag)
        clean["event_type"] = event_type
        out.append(clean)
    return out


def hard_veto_state(
    row: dict[str, Any],
    *,
    config: IntelligenceTradeConfig = IntelligenceTradeConfig(),
    asof: str | None = None,
) -> dict[str, Any]:
    flags = valid_hard_veto_flags(row, config=config, asof=asof)
    event_types = sorted({str(flag.get("event_type") or "") for flag in flags if flag.get("event_type")})
    reasons = [
        str(flag.get("reason") or flag.get("summary") or flag.get("event_type") or "")
        for flag in flags
    ]
    return {
        "hard_veto": bool(flags),
        "flags": flags,
        "event_types": event_types,
        "reason": "; ".join(reason for reason in reasons if reason),
    }


def agent_short_score(row: dict[str, Any]) -> float | None:
    score_source = str(row.get("score_source") or row.get("intelligence_factor_score_source") or "")
    if score_source != "agent_review":
        return None
    raw = _first_present(
        row,
        "agent_short_score",
        "intelligence_factor_short_score",
        "ai_intelligence_short_score",
        "stock_sentiment_score",
        "score",
    )
    try:
        return max(-1.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return None


def _data_quality_ok(row: dict[str, Any]) -> bool:
    return str(row.get("data_quality") or row.get("stock_sentiment_data_quality") or "legacy") in {"ok", "legacy"}


def _base_rank(row: dict[str, Any], pick_col: str) -> int:
    rank_field = _PICK_RANK_FIELD.get(pick_col, f"{pick_col}_rank")
    rank = _num(row.get(rank_field), 9999.0)
    return int(rank if rank > 0 else 9999)


def annotate_buy_candidate(
    row: dict[str, Any],
    *,
    pick_col: str,
    config: IntelligenceTradeConfig = IntelligenceTradeConfig(),
    asof: str | None = None,
) -> dict[str, Any]:
    out = dict(row)
    base_selected = bool(row.get(pick_col))
    score = agent_short_score(row)
    score_valid = score is not None and _data_quality_ok(row)
    score_bonus = (score or 0.0) * config.score_bonus if score_valid else 0.0
    base_score = _num(row.get("rank_score"), _num(row.get("primary_score"), _num(row.get("p_score"), 0.0)))
    veto = hard_veto_state(row, config=config, asof=asof)
    buy_eligible = score_valid and float(score or 0.0) >= config.buy_threshold
    trade_score = base_score + score_bonus
    if base_selected:
        reason = "base_pick"
    elif buy_eligible:
        reason = "ai_short_score"
    else:
        reason = "not_buy_candidate"
    if veto["hard_veto"]:
        reason = "hard_veto"
    out.update({
        "ai_intelligence_trade_mode": config.mode,
        "ai_intelligence_base_pick": base_selected,
        "ai_intelligence_base_pick_col": pick_col,
        "ai_intelligence_base_rank": _base_rank(row, pick_col),
        "ai_intelligence_base_score": round(base_score, 4),
        "ai_intelligence_short_score": None if score is None else round(float(score), 4),
        "ai_intelligence_short_threshold": config.buy_threshold,
        "ai_intelligence_score_bonus": round(score_bonus, 4),
        "ai_intelligence_trade_score": round(trade_score, 4),
        "ai_intelligence_buy_eligible": bool(buy_eligible),
        "ai_intelligence_trade_reason": reason,
        "ai_hard_veto": bool(veto["hard_veto"]),
        "ai_hard_veto_event_types": veto["event_types"],
        "ai_hard_veto_reason": veto["reason"],
        "ai_hard_veto_flags": veto["flags"],
    })
    return out


def select_buy_candidates(
    rows: list[dict[str, Any]],
    *,
    pick_col: str,
    config: IntelligenceTradeConfig = IntelligenceTradeConfig(),
    asof: str | None = None,
) -> BuySelection:
    mode = config.mode if config.mode in {"off", "shadow", "on"} else "off"
    cfg = IntelligenceTradeConfig(
        mode=mode,
        buy_threshold=config.buy_threshold,
        score_bonus=config.score_bonus,
        veto_min_confidence=config.veto_min_confidence,
        veto_max_age_days=config.veto_max_age_days,
    )
    annotated = [annotate_buy_candidate(row, pick_col=pick_col, config=cfg, asof=asof) for row in rows]
    base = [row for row in annotated if row.get("ai_intelligence_base_pick")]
    slot_count = len(base)
    has_actionable_ai = any(
        (row.get("ai_intelligence_base_pick") and row.get("ai_intelligence_short_score") is not None)
        or row.get("ai_intelligence_buy_eligible")
        or (
            row.get("ai_hard_veto")
            and (row.get("ai_intelligence_base_pick") or row.get("ai_intelligence_buy_eligible"))
        )
        for row in annotated
    )

    if mode in {"off", "shadow"} or slot_count <= 0 or not has_actionable_ai:
        selected = list(base)
        for rank, row in enumerate(selected, 1):
            row["ai_intelligence_trade_rank"] = rank
            row["ai_intelligence_buy_ranking_used"] = False
        return BuySelection(selected=selected, vetoed=[], annotated=annotated, slot_count=slot_count, mode=mode)

    active_pool = [
        row for row in annotated
        if (row.get("ai_intelligence_base_pick") or row.get("ai_intelligence_buy_eligible"))
        and not row.get("ai_hard_veto")
    ]
    vetoed = [
        row for row in annotated
        if (row.get("ai_intelligence_base_pick") or row.get("ai_intelligence_buy_eligible"))
        and row.get("ai_hard_veto")
    ]
    active_pool.sort(key=lambda r: (
        -float(r.get("ai_intelligence_trade_score") or 0.0),
        int(r.get("ai_intelligence_base_rank") or 9999),
        str(r.get("code") or ""),
    ))
    selected = active_pool[:slot_count]
    selected_codes = {str(row.get("code") or "") for row in selected}
    for rank, row in enumerate(selected, 1):
        row["ai_intelligence_trade_rank"] = rank
        row["ai_intelligence_buy_ranking_used"] = True
        row["ai_intelligence_replaced_base_pick"] = not bool(row.get("ai_intelligence_base_pick"))
    for row in annotated:
        if str(row.get("code") or "") not in selected_codes:
            row.setdefault("ai_intelligence_trade_rank", 9999)
    return BuySelection(selected=selected, vetoed=vetoed, annotated=annotated, slot_count=slot_count, mode=mode)


def event_risk_exit(
    row: dict[str, Any] | None,
    *,
    config: IntelligenceTradeConfig = IntelligenceTradeConfig(),
    asof: str | None = None,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        row = {}
    state = hard_veto_state(row, config=config, asof=asof)
    return {
        "triggered": bool(state["hard_veto"]),
        "sell_reason": "AI_EVENT_RISK_EXIT" if state["hard_veto"] else None,
        "event_types": state["event_types"],
        "reason": state["reason"],
        "flags": state["flags"],
    }
