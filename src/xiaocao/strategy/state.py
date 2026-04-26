"""Per-date market state vector — 二生三 of the Mode × State framework.

State = (Reward Density, Risk Polarity, Continuity, Duan Ban Recovery).

The first three are universal (all modes consult them); duan_ban_recovery is
only consulted by 断板 modes (绿断/红断/首红断低吸) via per-mode preconditions.

All values ∈ [0, 1] for axis-aligned interpretability:
  Reward Density   = fraction of stocks with |pctChange| ≥ 2% (motion)
  Risk Polarity    = positive_ratio (up stocks / total)
  Continuity       = top-5 block_rank overlap (today vs yesterday) / 5
  Duan Ban Recov.  = median pctChange today of stocks that were yesterday's
                     near-限上 but failed (∈ [-1, +1] mapped to [0, 1])

All four are derived ONLY from cached data — no API calls. Backtest-safe.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_REWARD_PCT_THRESHOLD = 2.0
_DUAN_BAN_HIGH_PCT = 8.0  # yesterday's "near 涨停" cutoff
_DUAN_BAN_FAIL_PCT = 9.5  # yesterday's failed-涨停 must have CLOSED below this
_LIMITUP_PCT = 9.5        # pct ≥ 9.5 → 涨停 (or 近涨停)
_LIMITUP_SAT = 0.05       # 5% of market 涨停 saturates limitup_density to 1.0
_MOMENTUM_WINDOW = 5      # days in cumulative mean pct
_MOMENTUM_SCALE = 10.0    # ±10% cumulative move → maps to ±1 → [0,1] via (x+1)/2


@dataclass(frozen=True)
class StateVector:
    """Five observable market state dimensions per date.

    All values ∈ [0, 1]. NaN-equivalent missing values default to 0.5 (neutral).
    """
    reward: float          # 赚钱密度: motion-stock fraction
    risk: float            # 风险方向: positive_ratio
    continuity: float      # 连续性: top-K mainline overlap
    duan_ban_recovery: float  # 断板亏钱效应: median next-day pct of yesterday's failed-涨停
    momentum: float = 0.5  # 大盘 5d 累计 mean pct，标准化到 [0,1]，0.5 = 中性
    limitup_density: float = 0.0  # pct≥9.5 比例，标准化到 [0,1]（5%饱和）；0 = 罕见涨停

    n_samples: int = 0     # number of stocks contributing to (reward, risk)
    n_continuity: int = 0  # number of overlapping top-K blocks (0..5)
    n_duan_ban: int = 0    # number of yesterday's failed-涨停 stocks tracked
    n_momentum: int = 0    # number of days available in the 5d window (0..5)


def _normalize_date(s: str) -> str:
    s = str(s)[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _load_kline_pcts(cache_path: str | Path) -> dict[str, dict[str, float]]:
    """{date_iso: {code: pctChangeRate}}. De-dups per (date, code)."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        with sqlite3.connect(str(cache_path)) as conn:
            rows = conn.execute(
                "SELECT response_json FROM api_cache WHERE endpoint='/stock/date_kline'"
            ).fetchall()
    except sqlite3.Error:
        return {}
    for (rj,) in rows:
        try:
            data = json.loads(rj)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td = k.get("tradeDate", "")
            code = k.get("code", "")
            pct = k.get("pctChangeRate")
            if td and code and isinstance(pct, (int, float)):
                out[_normalize_date(td)][str(code)] = float(pct)
    return out


def _load_block_top5_by_date(cache_path: str | Path) -> dict[str, list[str]]:
    """{date_iso: [top-5 blockCode by num desc]}. Uses model=0 (FULL rank)."""
    out: dict[str, list[str]] = {}
    try:
        with sqlite3.connect(str(cache_path)) as conn:
            rows = conn.execute(
                "SELECT params_json, response_json FROM api_cache "
                "WHERE endpoint='/stock/xiao_cao_industry_block_rank'"
            ).fetchall()
    except sqlite3.Error:
        return {}
    for pj, rj in rows:
        try:
            params = json.loads(pj)
        except json.JSONDecodeError:
            continue
        inner = params.get("params", params) if isinstance(params, dict) else {}
        if not isinstance(inner, dict) or inner.get("model") != 0:
            continue
        d = _normalize_date(str(inner.get("date") or ""))
        if not d:
            continue
        try:
            data = json.loads(rj)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            data = data.get("data") or list(data.values())
        if not isinstance(data, list):
            continue
        ranked = []
        for r in data:
            if not isinstance(r, dict):
                continue
            code = r.get("blockCode") or r.get("code") or r.get("category_code")
            num = r.get("num") or r.get("value") or r.get("score")
            if code and isinstance(num, (int, float)):
                ranked.append((float(num), str(code)))
        ranked.sort(reverse=True)
        out[d] = [c for _, c in ranked[:5]]
    return out


def _compute_reward_density(pcts: list[float]) -> float:
    if not pcts:
        return 0.5
    motion = sum(1 for v in pcts if abs(v) >= _REWARD_PCT_THRESHOLD)
    return motion / len(pcts)


def _compute_risk_polarity(pcts: list[float]) -> float:
    if not pcts:
        return 0.5
    pos = sum(1 for v in pcts if v > 0)
    return pos / len(pcts)


def _compute_continuity(today_top5: list[str], yesterday_top5: list[str]) -> tuple[float, int]:
    if not yesterday_top5:
        return 0.5, 0
    overlap = len(set(today_top5) & set(yesterday_top5))
    denom = max(1, min(5, len(yesterday_top5)))
    return overlap / denom, overlap


def _compute_limitup_density(pcts: list[float]) -> float:
    """Fraction of stocks with pct ≥ _LIMITUP_PCT (9.5%), normalized so that
    5% of market 涨停 → 1.0. Empty input → 0.0 (no signal != neutral).
    """
    if not pcts:
        return 0.0
    n_lu = sum(1 for v in pcts if v >= _LIMITUP_PCT)
    raw = n_lu / len(pcts)
    return min(1.0, raw / _LIMITUP_SAT)


def _compute_momentum(daily_mean_pcts: list[float]) -> tuple[float, int]:
    """5-day cumulative mean-pct → [0, 1].

    `daily_mean_pcts` is the most-recent-N (len ≤ _MOMENTUM_WINDOW) sequence,
    chronological order doesn't matter for the sum. Returns (momentum, n_used).
    Empty input → (0.5, 0) neutral.
    """
    if not daily_mean_pcts:
        return 0.5, 0
    total = sum(daily_mean_pcts)
    # Map ±_MOMENTUM_SCALE → ±1 → [0,1] via (x+1)/2, clamp.
    scaled = max(-1.0, min(1.0, total / _MOMENTUM_SCALE))
    return (scaled + 1.0) / 2.0, len(daily_mean_pcts)


def _compute_duan_ban_recovery(
    today_pcts: dict[str, float],
    yesterday_pcts: dict[str, float],
) -> tuple[float, int]:
    """Stocks that yesterday were 8% < pct < 9.5% (近涨停但断板) — what's their
    pctChange today? Median > 0 = market is repairing breaks; median < 0 = bad.
    Mapped from [-10, +10] roughly to [0, 1] via (median + 10) / 20.
    """
    candidates = [
        c for c, v in yesterday_pcts.items()
        if _DUAN_BAN_HIGH_PCT <= v < _DUAN_BAN_FAIL_PCT
    ]
    today_pct_for_them = [
        today_pcts[c] for c in candidates if c in today_pcts
    ]
    if not today_pct_for_them:
        return 0.5, 0
    today_pct_for_them.sort()
    n = len(today_pct_for_them)
    median = (
        today_pct_for_them[n // 2]
        if n % 2 == 1
        else (today_pct_for_them[n // 2 - 1] + today_pct_for_them[n // 2]) / 2
    )
    # Map median ∈ [-10, +10] → recovery ∈ [0, 1]; clamp.
    recovery = max(0.0, min(1.0, (median + 10.0) / 20.0))
    return recovery, n


def build_state_index(cache: Any) -> dict[str, StateVector]:
    """One-shot derivation of StateVector for every date with sufficient cache.

    Memoization is the caller's responsibility (this function reads SQLite each
    call). For typical use within run_backtest, call once and cache.

    Dates with < 30 stock samples for reward/risk are skipped (returned as
    neutral 0.5/0.5/0.5/0.5 if the date is queried later).
    """
    if cache is None or not hasattr(cache, "path"):
        return {}
    cache_path = cache.path

    pct_index = _load_kline_pcts(cache_path)
    block_top5 = _load_block_top5_by_date(cache_path)

    sorted_dates = sorted(pct_index.keys())
    out: dict[str, StateVector] = {}

    # Pre-compute daily mean pct for the momentum window.
    daily_mean: dict[str, float] = {}
    for d, pcts_dict in pct_index.items():
        if len(pcts_dict) >= 30:
            vals = list(pcts_dict.values())
            daily_mean[d] = sum(vals) / len(vals)

    for i, d in enumerate(sorted_dates):
        pcts_dict = pct_index[d]
        pcts = list(pcts_dict.values())
        if len(pcts) < 30:
            continue

        reward = _compute_reward_density(pcts)
        risk = _compute_risk_polarity(pcts)
        limitup = _compute_limitup_density(pcts)
        today_top5 = block_top5.get(d, [])
        yesterday = sorted_dates[i - 1] if i > 0 else None
        yesterday_top5 = block_top5.get(yesterday, []) if yesterday else []
        continuity, n_cont = _compute_continuity(today_top5, yesterday_top5)
        yesterday_pcts = pct_index.get(yesterday, {}) if yesterday else {}
        duan_ban, n_db = _compute_duan_ban_recovery(pcts_dict, yesterday_pcts)

        # Momentum: prior W days' (incl today) mean pct sum, normalized.
        window_dates = sorted_dates[max(0, i - _MOMENTUM_WINDOW + 1): i + 1]
        window_means = [daily_mean[wd] for wd in window_dates if wd in daily_mean]
        momentum, n_mom = _compute_momentum(window_means)

        out[d] = StateVector(
            reward=reward,
            risk=risk,
            continuity=continuity,
            duan_ban_recovery=duan_ban,
            momentum=momentum,
            limitup_density=limitup,
            n_samples=len(pcts),
            n_continuity=n_cont,
            n_duan_ban=n_db,
            n_momentum=n_mom,
        )
    return out


NEUTRAL_STATE = StateVector(
    reward=0.5, risk=0.5, continuity=0.5, duan_ban_recovery=0.5,
    momentum=0.5, limitup_density=0.0,
    n_samples=0, n_continuity=0, n_duan_ban=0, n_momentum=0,
)


def get_state(date_iso: str, state_index: dict[str, StateVector]) -> StateVector:
    """Lookup with neutral fallback for missing dates."""
    return state_index.get(date_iso, NEUTRAL_STATE)
