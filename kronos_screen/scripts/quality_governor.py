"""Quality-governor helpers for live K->P paper trading.

This module intentionally keeps the v1 governor conservative: primary score is
the only executable guard candidate, while P-tail is only a warning tag. The
default live mode should remain shadow until forward evidence is strong enough
to enable it.
"""
from __future__ import annotations

import math
from typing import Any

PRIMARY_THRESHOLD = 150.0
P_TAIL_WARNING_THRESHOLD = -2.0
try:
    from xiaocao.strategy.rules import RAW_QIBAO_BENCHMARK_MODES
except Exception:  # pragma: no cover - standalone script fallback
    RAW_QIBAO_BENCHMARK_MODES = {"标杆短线起爆", "高开标杆起爆", "强攻标杆起爆"}


def num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out):
        return None
    return out


def primary_score(row: dict[str, Any]) -> tuple[float, str]:
    mode = str(row.get("mode") or "")
    xcjw = num(row.get("xcjw")) or 0.0
    cjs = num(row.get("cjs")) or 0.0
    jsjl = num(row.get("jsjl")) or 0.0
    jssb = num(row.get("jssb")) or 0.0
    if mode in RAW_QIBAO_BENCHMARK_MODES or row.get("qibaoBenchmarkKind"):
        return num(row.get("qibaoRankScore")) or 0.0, "qibaoRankScore"
    if "起爆" in mode:
        return jssb, "jssb"
    if mode.startswith("接力"):
        return xcjw + max(jsjl, 0.0) * 0.5, "xcjw+0.5*jsjl"
    if mode in {"N字低吸", "孕线低吸"}:
        return xcjw + cjs * 0.6, "xcjw+0.6*cjs"
    return xcjw + cjs * 0.8, "xcjw+0.8*cjs"


def alpha_score_fit(primary: float) -> float:
    return min(140.0, primary / 350.0 * 100.0)


def fallback_rank_score(row: dict[str, Any], primary: float) -> float:
    confidence = num(row.get("mode_confidence"))
    if confidence is None:
        confidence = 50.0
    macro_score = num(row.get("macro_focus_score")) or 0.0
    open_risk_penalty = num(row.get("open_risk_penalty")) or 0.0
    return alpha_score_fit(primary) * 0.60 + confidence * 0.25 + macro_score * 0.18 - open_risk_penalty


def ensure_quality_fields(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    primary = num(out.get("primary_score"))
    fallback = primary is None
    if primary is None:
        primary, label = primary_score(out)
    else:
        label = str(out.get("primary_score_label") or primary_score(out)[1])
    out["primary_score"] = round(primary, 2)
    out["primary_score_label"] = label
    if num(out.get("mode_confidence")) is None:
        out["mode_confidence"] = 50.0
        fallback = True
    rank_score = num(out.get("rank_score"))
    if rank_score is None:
        rank_score = fallback_rank_score(out, primary)
        fallback = True
    out["rank_score"] = round(rank_score, 2)
    out["quality_fields_fallback"] = bool(out.get("quality_fields_fallback") or fallback)
    out["quality_tag"] = quality_tag(out)
    return out


def quality_flags(row: dict[str, Any]) -> list[str]:
    row = ensure_quality_fields(row) if "primary_score" not in row else row
    flags: list[str] = []
    primary = num(row.get("primary_score")) or 0.0
    p_score = num(row.get("p_score"))
    if primary < PRIMARY_THRESHOLD:
        flags.append("weak_primary")
    if p_score is not None and p_score <= P_TAIL_WARNING_THRESHOLD:
        flags.append("p_tail_warning")
    return flags


def quality_tag(row: dict[str, Any]) -> str:
    flags = quality_flags(row) if "quality_tag" not in row else []
    if "quality_tag" in row and row.get("quality_tag"):
        return str(row["quality_tag"])
    return "+".join(flags) if flags else "normal"


def governor_slot_weight(row: dict[str, Any]) -> float:
    row = ensure_quality_fields(row)
    primary = num(row.get("primary_score")) or 0.0
    return 1.0 if primary >= PRIMARY_THRESHOLD else 0.0


def governor_shadow_action(row: dict[str, Any]) -> tuple[str, str, float]:
    row = ensure_quality_fields(row)
    weight = governor_slot_weight(row)
    if weight >= 1.0:
        return "BUY_SLOT", "primary>=150", weight
    return "CASH_SLOT", "primary<150", weight


def annotate_quality_governor(row: dict[str, Any], mode: str) -> dict[str, Any]:
    out = ensure_quality_fields(row)
    action, reason, weight = governor_shadow_action(out)
    out["quality_governor_mode"] = mode
    out["quality_governor_action"] = action
    out["quality_governor_reason"] = reason
    out["quality_slot_weight"] = weight
    return out
