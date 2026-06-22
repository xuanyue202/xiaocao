"""Regime classification + Mode × State fitness framework.

Two layers coexist here:

1. **Legacy regime labels** (`classify_regime`, `derive_proxy_regime`,
   `mode_allowed_in`): backward-compatible 5-bucket labels for the
   live `strategy run` path that has access to market_overview, plus the
   binary hard-gate fallback. Discouraged for new code.

2. **State-fitness framework** (`MODE_PROFILE`, `mode_fitness`,
   `align`): the 道-level abstraction. Each mode declares its preferred
   ranges across 3 universal axes (reward density / risk polarity /
   continuity) plus optional preconditions; `mode_fitness(mode, state)`
   returns a continuous score ∈ [-1, +1] that adaptive uses to modulate
   per-window thresholds. See docs and reports/strategy_state_framework_*.md
   for the full first-principles derivation.

Regimes still emitted (legacy, for live overview-based path):
- `bear`, `divergence`, `recovery`, `trend_continuing`, `trend_strong`, `neutral`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .state import StateVector

REGIME_LABELS = (
    "bear",
    "divergence",
    "neutral",
    "recovery",
    "trend_continuing",
    "trend_strong",
)


def _level_sum(overview: dict[str, Any], side: str, levels: range) -> int:
    return sum(int(overview.get(f"{side}Level{_LEVEL_NAMES[i]}", 0) or 0) for i in levels)


_LEVEL_NAMES = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
}


def positive_total(overview: dict[str, Any]) -> int:
    return _level_sum(overview, "positive", range(1, 8))


def negative_total(overview: dict[str, Any]) -> int:
    return _level_sum(overview, "negative", range(1, 8))


def limit_up_count(overview: dict[str, Any]) -> int:
    """Treat the top tier (positiveLevelSeven) as limit-ups.

    Some bundle versions emit limit-up counts under a separate key; if a future
    schema adds e.g. `limitUpCount`, prefer it.
    """
    explicit = overview.get("limitUpCount")
    if isinstance(explicit, (int, float)):
        return int(explicit)
    return int(overview.get("positiveLevelSeven", 0) or 0)


def limit_down_count(overview: dict[str, Any]) -> int:
    explicit = overview.get("limitDownCount")
    if isinstance(explicit, (int, float)):
        return int(explicit)
    return int(overview.get("negativeLevelSeven", 0) or 0)


def classify_regime(
    overview: dict[str, Any] | None,
    big_cap_avg_open_pct: float | None = None,
) -> str:
    """Return a regime label given today's market_overview snapshot.

    The thresholds below are intentionally conservative defaults derived from
    the docs, not from backtest cherry-picking. Adjust via parameters if a
    later study justifies it.
    """
    if not overview:
        return "neutral"

    pos = positive_total(overview)
    neg = negative_total(overview)
    lu = limit_up_count(overview)
    ld = limit_down_count(overview)

    # Bear: 跌停明显 OR 跌多于涨 ≥ 3:1 (强跌势, 0410 主跌环境)
    if ld >= 50 or (neg > 0 and pos > 0 and neg / max(pos, 1) >= 3):
        return "bear"

    # 大票普遍低开 ≤ -2 → 0413-B "兑现/分歧"
    if big_cap_avg_open_pct is not None and big_cap_avg_open_pct <= -2.0:
        return "divergence"

    # 涨停扩散 (≥30 个涨停) + 涨多 → 趋势/情绪强
    if lu >= 30 and pos > neg:
        return "trend_strong"

    # 大票核心抗跌 + 涨多 → 趋势延续
    if pos > neg and (big_cap_avg_open_pct is None or big_cap_avg_open_pct >= -1.0):
        return "trend_continuing"

    # 涨多于跌但大票偏弱：修复
    if pos > neg:
        return "recovery"

    # 跌多于涨但不够 bear：高分歧
    if neg > pos:
        return "divergence"

    return "neutral"


# --- Proxy regime derived from cached per-date data (no live state) ----------
# Used by backtest where market_overview is unavailable per-date. Computes
# `positive_ratio` + `mean_pct` from cached date_kline data and maps to the
# same six labels classify_regime emits.
_PROXY_CACHE: dict[tuple[str, int], dict[str, str]] = {}


def derive_proxy_regime(date_iso: str, cache: Any) -> str:
    """Return a per-date regime label from cached date_kline data.

    Reads `api_cache` rows for /stock/date_kline once per cache instance and
    memoizes. Returns "neutral" when the cache is unavailable or has too few
    samples for the date.
    """
    if cache is None or not hasattr(cache, "path"):
        return "neutral"
    cache_key = (str(getattr(cache, "path", "")), id(cache))
    bundle = _PROXY_CACHE.get(cache_key)
    if bundle is None:
        bundle = _build_proxy_index(cache)
        _PROXY_CACHE[cache_key] = bundle
    return bundle.get(date_iso, "neutral")


def _build_proxy_index(cache: Any) -> dict[str, str]:
    import sqlite3
    from collections import defaultdict
    from xiaocao.api.cache import iter_cached_responses

    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        rows = list(iter_cached_responses(cache.path, "/stock/date_kline"))
    except sqlite3.Error:
        return {}
    for data in rows:
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td = k.get("tradeDate", "")
            code = k.get("code", "")
            pct = k.get("pctChangeRate")
            if td and code and isinstance(pct, (int, float)):
                by_date[td][code] = float(pct)
    out: dict[str, str] = {}
    for d, codes in by_date.items():
        pcts = list(codes.values())
        n = len(pcts)
        if n < 30:
            continue
        pos = sum(1 for v in pcts if v > 0)
        positive_ratio = pos / n
        mean_pct = sum(pcts) / n
        out[d] = _classify_proxy(positive_ratio, mean_pct)
    return out


def _classify_proxy(positive_ratio: float, mean_pct: float) -> str:
    if positive_ratio < 0.30 and mean_pct < -1.0:
        return "bear"
    if positive_ratio >= 0.65 and mean_pct >= 1.5:
        return "trend_strong"
    if positive_ratio >= 0.55 and mean_pct >= 0.5:
        return "trend_continuing"
    if positive_ratio < 0.40 or mean_pct < -0.5:
        return "divergence"
    if mean_pct >= 0.0:
        return "recovery"
    return "neutral"


# --- Mode × State Fitness Framework (the 三生万物) ---------------------------
#
# Each mode declares ITS preferred range on each of 3 universal axes:
#   - wants_reward     ∈ {"low", "mid", "high", "very_high", "any"}
#   - wants_risk       ∈ {"low", "mid", "high", "very_high", "any"}
#   - wants_continuity ∈ {"low", "mid", "high", "any"}
#
# Plus an optional `precondition(state) -> bool` for special cases (断板 modes
# need yesterday's failed-涨停 to have rebounded — see state.duan_ban_recovery).
#
# Encoded values come from synthesis of reference/experience/transcripts/2026-04/0410..0419 +
# standard short-term quant intuition. Each cell is auditable; disagree freely.

@dataclass(frozen=True)
class ModeProfile:
    """Static profile of a strategy mode's structural fit conditions.

    Axes 1-3 (reward, risk, continuity) are mandatory and form the base
    fitness. Axes 4-5 (momentum, limitup_density) default to "any" for
    backward-compat with v3.3 — when set to a non-"any" value they
    contribute as a 30%-weighted bonus on top of the base 3-axis mean.
    """
    direction_bet: str   # "continuation" / "rebound" / "rotation"
    wants_reward: str
    wants_risk: str
    wants_continuity: str
    wants_momentum: str = "any"          # 大盘 5d 累计 momentum 期望
    wants_limitup_density: str = "any"   # 涨停密度期望
    precondition: Callable[[StateVector], bool] | None = None


# 断板 precondition: yesterday's failed-涨停 stocks must have median pctChange
# today >= +1% (recovery >= 0.55). 0415: "断板亏钱效应低 → 断板模式可做"
#
# Threshold calibration (2026-04-26 win/loss analysis on 125-trade TRAIN):
# state.duan_ban_recovery tertile averages were:
#   low  (n=41) avg=-0.17%   ← skip
#   mid  (n=41) avg=-0.39%   ← skip
#   high (n=43) avg=+8.11%   ← keep
# i.e. only the "high" tertile (≥0.55 in our scaling) is real signal.
# The earlier 0.45 threshold included noise-band trades (mid tertile).
def _duan_ban_recovery_ok(state: StateVector) -> bool:
    return state.duan_ban_recovery >= 0.55


MODE_PROFILE: dict[str, ModeProfile] = {
    # === v3.3 baseline — preserved exactly for backward-compat ===
    # 接力 — continuation bets on 情绪 momentum carrying overnight
    "接力低弱转1": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="high"
    ),
    "接力低弱转2": ModeProfile(  # 高开追涨 — most regime-sensitive
        "continuation", wants_reward="high", wants_risk="very_high", wants_continuity="high",
        # Don't chase highs in risk-off regimes. 0410: "弱环境里追涨是垃圾场".
        precondition=lambda state: state.risk >= 0.45,
    ),
    # 红盘起爆 — continuation bets on attack money activated
    "红盘起爆主攻": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="mid"
    ),
    "方向红盘起爆": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="high"
    ),
    # 断板 (绿/红/首红) — rebound bets, gated by 断板亏钱效应 (v3.3 default)
    "绿断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="low", wants_continuity="any",
        precondition=_duan_ban_recovery_ok,
    ),
    "红断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="any",
        precondition=_duan_ban_recovery_ok,
    ),
    "首红断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="any",
        precondition=_duan_ban_recovery_ok,
    ),
    # N字 — direction-internal continuation, needs main-line stability
    "N字低吸": ModeProfile(
        "continuation", wants_reward="mid", wants_risk="mid", wants_continuity="high"
    ),
    # 孕线 — small-range rebound, low-motion territory
    "孕线低吸": ModeProfile(
        "rebound", wants_reward="low", wants_risk="mid", wants_continuity="high"
    ),
    # 全盘 — broad oversold rebound, thrives in rotational selloffs
    "全盘低位低吸": ModeProfile(
        "rebound", wants_reward="high", wants_risk="low", wants_continuity="low"
    ),
    # 方向低位 / 方向内绿盘 — direction-anchored rebound
    "方向低位低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="high"
    ),
    "方向内绿盘低吸前3名": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="low", wants_continuity="high"
    ),
}


# === v3.4 candidate (Plan A8) — opt-in via STRATEGY_PROFILES["validated_v3_4"]. ===
#
# Two structural changes vs v3.3:
#
# 1. **DBR preconditions dropped** (per A3 calibration on
#    output/calibrate_dbr_per_mode.md): for all 6 modes with sufficient sample,
#    DBR distribution between winners and losers overlap (Δ_med ∈ [-0.14, +0.00]),
#    sometimes anti-predictive. 绿断/红断/首红断 lose hard precondition; rely on
#    adaptive fitness modulation only.
#
# 2. **Two new bonus axes** wired in:
#    - wants_momentum (5d cumulative 大盘 mean pct, normalized to [0,1])
#    - wants_limitup_density (focus pool 涨停 ratio, normalized to [0,1])
#    First-principles per report §4 "1-day backtest里 bear 日 best mode = 低吸；
#    trend_strong 日 best mode = 接力". So 接力 wants high momentum + high limitup;
#    断板低吸 wants low momentum (oversold rebound).
#
# NOTE on 红盘起爆主攻 (A1 finding): EOD jssb is decayed (p99=60 vs xcjw p99=624);
# STRONG_JW=200 filters out 99.7% of qibao pool. This mode is structurally
# intraday-only. The v3.4 profile is best-effort but real fix is Phase C R2.
MODE_PROFILE_V3_4: dict[str, ModeProfile] = {
    "接力低弱转1": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="high",
        wants_momentum="high", wants_limitup_density="high",
    ),
    "接力低弱转2": ModeProfile(
        "continuation", wants_reward="high", wants_risk="very_high", wants_continuity="high",
        wants_momentum="very_high", wants_limitup_density="high",
        precondition=lambda state: state.risk >= 0.45,  # NOT a DBR precondition; kept
    ),
    "红盘起爆主攻": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="mid",
        wants_momentum="high", wants_limitup_density="high",
    ),
    "方向红盘起爆": ModeProfile(
        "continuation", wants_reward="high", wants_risk="high", wants_continuity="high",
        wants_momentum="high", wants_limitup_density="high",
    ),
    "绿断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="low", wants_continuity="any",
        wants_momentum="low", wants_limitup_density="low",
        # precondition dropped — A3 found anti-predictive
    ),
    "红断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="any",
        wants_momentum="low", wants_limitup_density="mid",
        # precondition dropped — A3 found overlap
    ),
    "首红断低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="any",
        wants_momentum="low", wants_limitup_density="mid",
        # precondition dropped — A3 found overlap
    ),
    "N字低吸": ModeProfile(
        "continuation", wants_reward="mid", wants_risk="mid", wants_continuity="high",
        wants_momentum="mid", wants_limitup_density="mid",
    ),
    "孕线低吸": ModeProfile(
        "rebound", wants_reward="low", wants_risk="mid", wants_continuity="high",
        wants_momentum="mid", wants_limitup_density="low",
    ),
    "全盘低位低吸": ModeProfile(
        "rebound", wants_reward="high", wants_risk="low", wants_continuity="low",
        wants_momentum="low", wants_limitup_density="low",
    ),
    "方向低位低吸": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="mid", wants_continuity="high",
        wants_momentum="mid", wants_limitup_density="mid",
    ),
    "方向内绿盘低吸前3名": ModeProfile(
        "rebound", wants_reward="mid", wants_risk="low", wants_continuity="high",
        wants_momentum="low", wants_limitup_density="mid",
    ),
}


# Target levels for each "wants" qualifier
_TARGET_LEVEL: dict[str, float] = {
    "low": 0.25,
    "mid": 0.50,
    "high": 0.70,
    "very_high": 0.85,
}


def align(want: str, observed: float) -> float:
    """Linear-distance alignment ∈ [-1, +1] between desired level and observation.

    `want="any"` always returns 0 (no preference, no penalty).
    """
    if want == "any":
        return 0.0
    target = _TARGET_LEVEL.get(want)
    if target is None:
        return 0.0
    return max(-1.0, 1.0 - 2.5 * abs(observed - target))


# Sentinel returned by mode_fitness when a precondition fails — adaptive
# layer interprets this as "force shadow on any mild loss" (threshold → 0).
PRECONDITION_FAIL = float("-inf")


def mode_fitness(
    mode: str,
    state: StateVector | None,
    profiles: dict[str, ModeProfile] | None = None,
) -> float:
    """Continuous fitness ∈ [-1, +1], or PRECONDITION_FAIL when state-gated out.

    Base = 3-axis mean of (reward, risk, continuity) alignments — preserves
    v3.3 backward-compat exactly when wants_momentum / wants_limitup_density
    are "any" (the default in MODE_PROFILE).

    When wants_momentum and/or wants_limitup_density are non-"any" (v3.4
    via MODE_PROFILE_V3_4), they contribute as a 30%-weighted bonus on top
    of the 70%-weighted base:

        fitness = 0.7 * base_3axis + 0.3 * mean(active_new_axes)

    `profiles` defaults to MODE_PROFILE (v3.3 BC). Pass MODE_PROFILE_V3_4
    when running the v3.4 candidate.
    """
    if state is None:
        return 0.0
    profile_dict = profiles if profiles is not None else MODE_PROFILE
    profile = profile_dict.get(mode)
    if profile is None:
        return 0.0
    if profile.precondition is not None and not profile.precondition(state):
        return PRECONDITION_FAIL

    base = (
        align(profile.wants_reward, state.reward)
        + align(profile.wants_risk, state.risk)
        + align(profile.wants_continuity, state.continuity)
    ) / 3.0

    bonus_aligns: list[float] = []
    if profile.wants_momentum != "any":
        bonus_aligns.append(align(profile.wants_momentum, state.momentum))
    if profile.wants_limitup_density != "any":
        bonus_aligns.append(align(profile.wants_limitup_density, state.limitup_density))

    if not bonus_aligns:
        return base

    bonus = sum(bonus_aligns) / len(bonus_aligns)
    return 0.7 * base + 0.3 * bonus


# --- Legacy 5-tier discrete fitness (kept for back-compat) -------------------
# Old code paths (regime: str instead of state: StateVector) still work.
# Maps the discrete regime label to a 1-axis "expected fitness" for each mode
# by sampling state values that prototypically belong to that regime.

_REGIME_PROTOTYPE_STATE: dict[str, StateVector] = {
    "bear":             StateVector(reward=0.55, risk=0.20, continuity=0.40, duan_ban_recovery=0.30),
    "divergence":       StateVector(reward=0.45, risk=0.35, continuity=0.45, duan_ban_recovery=0.45),
    "neutral":          StateVector(reward=0.40, risk=0.50, continuity=0.50, duan_ban_recovery=0.50),
    "recovery":         StateVector(reward=0.50, risk=0.55, continuity=0.55, duan_ban_recovery=0.55),
    "trend_continuing": StateVector(reward=0.60, risk=0.65, continuity=0.65, duan_ban_recovery=0.55),
    "trend_strong":     StateVector(reward=0.70, risk=0.75, continuity=0.55, duan_ban_recovery=0.55),
}


def mode_regime_fitness(mode: str, regime: str | None) -> int:
    """Legacy: return integer fitness {-2..+2} for (mode, regime).

    Implementation: derive from continuous mode_fitness using prototype state
    vectors per regime, then bucket into integer scores. Preserves prior API
    so existing `tag_signals(..., regime=label)` calls keep working.
    """
    if not regime:
        return 0
    proto = _REGIME_PROTOTYPE_STATE.get(regime)
    if proto is None:
        return 0
    f = mode_fitness(mode, proto)
    if f == PRECONDITION_FAIL:
        return -2
    if f >= 0.4:
        return +2
    if f >= 0.15:
        return +1
    if f <= -0.4:
        return -2
    if f <= -0.15:
        return -1
    return 0


# Legacy hard-gate map — derived from the integer fitness >= 0 cells.
MODE_REGIME_FIT: dict[str, set[str]] = {
    mode: {r for r in _REGIME_PROTOTYPE_STATE if mode_regime_fitness(mode, r) >= 0}
    for mode in MODE_PROFILE
}


def mode_allowed_in(mode: str, regime: str) -> bool:
    """Legacy hard-gate. Discouraged — use mode_fitness() with state instead."""
    fit = MODE_REGIME_FIT.get(mode)
    if fit is None:
        return regime != "bear"
    return regime in fit
