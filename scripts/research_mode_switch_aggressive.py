#!/usr/bin/env python3
"""First-principles mode switching and same-mode breadth research.

The historical leg uses the expanding-OOS proxy panel.  The strict leg uses
the live executable opening-window labels and the production board-lot planner.
Every outcome is D+2 available.  This file is research-only: it does not change
the Book-B mode authority or allocation contract.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KRONOS_SCRIPTS = ROOT / "kronos_screen" / "scripts"
for path in (ROOT, ROOT / "src", KRONOS_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import research_mode_switch_proxy_6mo as proxy  # noqa: E402
from scripts import research_mode_switch_replay as exact  # noqa: E402
from xiaocao.backtest import list_trade_days  # noqa: E402
from xiaocao.strategy import mode_switch as ms  # noqa: E402


INITIAL_CAPITAL = 100_000.0
FEE_RATE = 0.0001
EVENT_LOOKBACK_DAYS = 20
EVENT_COUNT = 5
EVENT_WINDOW_KEY = 21

Decider = Callable[
    [str, str, Sequence[ms.ModeEvidenceRow], Sequence[str]],
    ms.ModeDecision,
]


@dataclass(frozen=True)
class Variant:
    name: str
    decider: Decider
    max_per_mode: int
    family: str
    allocation: str = "count_scaled"
    max_single_weight: float = ms.MAX_SINGLE_WEIGHT


def _num(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _recent_class(stats: ms.ModeWindowStats) -> str | None:
    """Return positive, negative, or mixed once the shared sample floor exists."""
    if (
        stats.signal_days < ms.FAST_MIN_DAYS
        or stats.signals < ms.FAST_MIN_SIGNALS
        or stats.market_days != stats.signal_days
        or stats.alpha_market_mean is None
    ):
        return None
    positive = (
        stats.alpha_pool_mean > 0
        and stats.alpha_market_mean > 0
        and stats.positive_alpha_days * 2 > stats.signal_days
        and stats.positive_market_alpha_days * 2 > stats.signal_days
    )
    negative = (
        stats.alpha_pool_mean <= 0
        or stats.alpha_market_mean <= 0
        or stats.positive_alpha_days * 2 < stats.signal_days
        or stats.positive_market_alpha_days * 2 < stats.signal_days
    )
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "mixed"


def _with_state(
    decision: ms.ModeDecision,
    *,
    state: str,
    selected_window: int,
    reason: str,
) -> ms.ModeDecision:
    return replace(
        decision,
        state=state,
        max_picks=3 if state == ms.ACTIVE else 1 if state == ms.PROVISIONAL else 0,
        selected_window=selected_window,
        reason=reason,
    )


def fast_promote_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Promote recent strength to ACTIVE; retain current one-slot cooling."""
    decision = ms.decide_mode(mode, asof, evidence, trade_days)
    fast = decision.windows[ms.FAST_WINDOW]
    recent = _recent_class(fast)
    if recent == "positive":
        return _with_state(
            decision,
            state=ms.ACTIVE,
            selected_window=ms.FAST_WINDOW,
            reason=(
                "5d aggressive promotion: recent dual-alpha mean and majority positive; "
                f"pool/market {fast.alpha_pool_mean:+.2f}/{fast.alpha_market_mean:+.2f}pp"
            ),
        )
    return decision


def robust_promote_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Promote only when recent strength survives removal of its best day."""
    decision = ms.decide_mode(mode, asof, evidence, trade_days)
    fast = decision.windows[ms.FAST_WINDOW]
    robust_positive = (
        _recent_class(fast) == "positive"
        and fast.alpha_pool_without_best is not None
        and fast.alpha_pool_without_best > 0
        and fast.alpha_market_without_best is not None
        and fast.alpha_market_without_best > 0
    )
    if robust_positive:
        return _with_state(
            decision,
            state=ms.ACTIVE,
            selected_window=ms.FAST_WINDOW,
            reason=(
                "5d robust promotion: recent dual-alpha breadth and best-day-removed "
                f"means positive; pool/market {fast.alpha_pool_mean:+.2f}/"
                f"{fast.alpha_market_mean:+.2f}pp"
            ),
        )
    return decision


def fast_early_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Promote after two unanimously positive mode days and three signals."""
    decision = ms.decide_mode(mode, asof, evidence, trade_days)
    fast = decision.windows[ms.FAST_WINDOW]
    early_floor = (
        fast.signal_days >= 2
        and fast.signals >= 3
        and fast.market_days == fast.signal_days
        and fast.alpha_market_mean is not None
    )
    early_positive = (
        early_floor
        and fast.alpha_pool_mean > 0
        and fast.alpha_market_mean > 0
        and fast.positive_alpha_days * 2 > fast.signal_days
        and fast.positive_market_alpha_days * 2 > fast.signal_days
    )
    if early_positive:
        return _with_state(
            decision,
            state=ms.ACTIVE,
            selected_window=ms.FAST_WINDOW,
            reason=(
                "5d early promotion: at least 2 mode days/3 signals with dual-alpha "
                f"mean and majority positive; pool/market {fast.alpha_pool_mean:+.2f}/"
                f"{fast.alpha_market_mean:+.2f}pp"
            ),
        )
    return decision


def fast_hard_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Let an informative five-day window fully override the formal state."""
    decision = ms.decide_mode(mode, asof, evidence, trade_days)
    fast = decision.windows[ms.FAST_WINDOW]
    recent = _recent_class(fast)
    if recent is None:
        return decision
    state = {
        "positive": ms.ACTIVE,
        "negative": ms.COLD,
        "mixed": ms.PROVISIONAL,
    }[recent]
    return _with_state(
        decision,
        state=state,
        selected_window=ms.FAST_WINDOW,
        reason=(
            f"5d hard switch {recent}: pool/market mean "
            f"{fast.alpha_pool_mean:+.2f}/{(fast.alpha_market_mean or 0.0):+.2f}pp, "
            f"positive days {fast.positive_alpha_days}/"
            f"{fast.positive_market_alpha_days}/{fast.signal_days}"
        ),
    )


def _event_window_stats(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeWindowStats:
    available = set(
        ms._available_window_days(asof, EVENT_LOOKBACK_DAYS, trade_days, evidence)
    )
    by_day: dict[str, list[ms.ModeEvidenceRow]] = defaultdict(list)
    for row in evidence:
        if row.signal_date in available:
            by_day[row.signal_date].append(row)
    event_days = [
        day for day in sorted(by_day)
        if any(row.mode == mode for row in by_day[day])
    ][-EVENT_COUNT:]

    raw: list[float] = []
    pool_alpha: list[float] = []
    market_alpha: list[float] = []
    signals = 0
    for day in event_days:
        day_rows = by_day[day]
        mode_rows = [row for row in day_rows if row.mode == mode]
        signals += len(mode_rows)
        mode_return = statistics.mean(row.net_return_pct for row in mode_rows)
        pool_return = statistics.mean(row.net_return_pct for row in day_rows)
        markets = [row.market_return_pct for row in day_rows if row.market_return_pct is not None]
        raw.append(mode_return)
        pool_alpha.append(mode_return - pool_return)
        if markets:
            market_alpha.append(mode_return - statistics.mean(markets))

    # Half-life of two mode occurrences: recency matters without letting one day
    # become the entire decision.
    weights = [0.5 ** ((len(event_days) - 1 - index) / 2.0) for index in range(len(event_days))]
    pool_mean, pool_lcb, effective = ms._weighted_mean_lcb80(pool_alpha, weights)
    market_mean: float | None = None
    market_lcb: float | None = None
    if market_alpha:
        market_mean, market_lcb, _ = ms._weighted_mean_lcb80(
            market_alpha,
            weights[-len(market_alpha):],
        )
    return ms.ModeWindowStats(
        window_days=EVENT_WINDOW_KEY,
        signal_days=len(event_days),
        signals=signals,
        market_days=len(market_alpha),
        effective_days=effective,
        raw_return_mean=ms._weighted_mean(raw, weights),
        alpha_pool_mean=pool_mean,
        alpha_pool_lcb80=pool_lcb,
        positive_alpha_days=sum(value > 0 for value in pool_alpha),
        alpha_pool_without_best=ms._weighted_mean_without_best(pool_alpha, weights),
        alpha_market_mean=market_mean,
        alpha_market_lcb80=market_lcb,
        positive_market_alpha_days=sum(value > 0 for value in market_alpha),
        alpha_market_without_best=ms._weighted_mean_without_best(
            market_alpha,
            weights[-len(market_alpha):],
        ) if market_alpha else None,
        latest_signal_date=event_days[-1] if event_days else None,
        weighting="last_5_mode_occurrences_in_20d_half_life_2",
    )


def event_hard_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Hard-switch from recent mode occurrences instead of calendar density."""
    decision = ms.decide_mode(mode, asof, evidence, trade_days)
    event = _event_window_stats(mode, asof, evidence, trade_days)
    windows = dict(decision.windows)
    windows[EVENT_WINDOW_KEY] = event
    decision = replace(decision, windows=windows)
    recent = _recent_class(event)
    if recent is None:
        return decision
    state = {
        "positive": ms.ACTIVE,
        "negative": ms.COLD,
        "mixed": ms.PROVISIONAL,
    }[recent]
    return _with_state(
        decision,
        state=state,
        selected_window=EVENT_WINDOW_KEY,
        reason=(
            f"event-time hard switch {recent}: last {event.signal_days} mode days/"
            f"{event.signals} signals in {EVENT_LOOKBACK_DAYS}d, pool/market "
            f"{event.alpha_pool_mean:+.2f}/{(event.alpha_market_mean or 0.0):+.2f}pp"
        ),
    )


def _variants() -> list[Variant]:
    families: list[tuple[str, Decider]] = [
        ("current", ms.decide_mode),
        ("fast_promote", fast_promote_decide_mode),
        ("fast_hard", fast_hard_decide_mode),
        ("event_hard", event_hard_decide_mode),
    ]
    variants = [
        Variant(
            name=f"{family}_modecap{cap}",
            decider=decider,
            max_per_mode=cap,
            family=family,
        )
        for family, decider in families
        for cap in (1, 2, 3)
    ]
    variants.extend([
        Variant(
            name="current_modesleeve25",
            decider=ms.decide_mode,
            max_per_mode=3,
            family="current",
            allocation="mode_sleeve_25",
        ),
        Variant(
            name="fast_promote_modesleeve25",
            decider=fast_promote_decide_mode,
            max_per_mode=3,
            family="fast_promote",
            allocation="mode_sleeve_25",
        ),
        Variant(
            name="robust_promote_modecap1",
            decider=robust_promote_decide_mode,
            max_per_mode=1,
            family="robust_promote",
        ),
        Variant(
            name="robust_promote_modesleeve25",
            decider=robust_promote_decide_mode,
            max_per_mode=3,
            family="robust_promote",
            allocation="mode_sleeve_25",
        ),
        Variant(
            name="fast_early_modecap1",
            decider=fast_early_decide_mode,
            max_per_mode=1,
            family="fast_early",
        ),
        Variant(
            name="fast_promote_modecap1_batch25_50_50",
            decider=fast_promote_decide_mode,
            max_per_mode=1,
            family="fast_promote",
            allocation="batch_25_50_50",
        ),
        Variant(
            name="fast_promote_modecap1_batch33_50_50",
            decider=fast_promote_decide_mode,
            max_per_mode=1,
            family="fast_promote",
            allocation="batch_33_50_50",
            max_single_weight=1.0 / 3.0,
        ),
        Variant(
            name="fast_promote_modecap1_batch50",
            decider=fast_promote_decide_mode,
            max_per_mode=1,
            family="fast_promote",
            allocation="batch_50_50_50",
            max_single_weight=0.50,
        ),
        Variant(
            name="fast_early_modecap1_batch33_50_50",
            decider=fast_early_decide_mode,
            max_per_mode=1,
            family="fast_early",
            allocation="batch_33_50_50",
            max_single_weight=1.0 / 3.0,
        ),
    ])
    return variants


def _mode_sleeve_weights(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    """Budget risk by mode, then diversify that sleeve across its stocks."""
    if not rows:
        return []
    by_mode: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_mode[str(row.get("mode") or "")].append(index)
    mode_totals: dict[str, float] = {}
    for mode, indices in by_mode.items():
        states = {str(rows[index].get("mode_state") or ms.UNKNOWN) for index in indices}
        mode_totals[mode] = (
            ms.PROVISIONAL_TARGET_WEIGHT
            if states == {ms.PROVISIONAL}
            else ms.MAX_SINGLE_WEIGHT
        )
    total = sum(mode_totals.values())
    if total > 0.50:
        scale = 0.50 / total
        mode_totals = {mode: weight * scale for mode, weight in mode_totals.items()}
    weights = [0.0] * len(rows)
    for mode, indices in by_mode.items():
        per_stock = mode_totals[mode] / len(indices)
        for index in indices:
            weights[index] = per_stock
    return weights


def _variant_weights(
    rows: Sequence[Mapping[str, Any]],
    variant: Variant,
) -> list[float]:
    if variant.allocation == "mode_sleeve_25":
        return _mode_sleeve_weights(rows)
    aggressive_totals = {
        "batch_25_50_50": {1: 0.25, 2: 0.50, 3: 0.50},
        "batch_33_50_50": {1: 1.0 / 3.0, 2: 0.50, 3: 0.50},
        "batch_50_50_50": {1: 0.50, 2: 0.50, 3: 0.50},
    }
    if variant.allocation in aggressive_totals:
        count = len(rows)
        if count == 0:
            return []
        provisional = sum(
            str(row.get("mode_state") or ms.UNKNOWN) == ms.PROVISIONAL
            for row in rows
        )
        active = count - provisional
        if active == 0:
            return [ms.PROVISIONAL_TARGET_WEIGHT] * count
        total = aggressive_totals[variant.allocation][count]
        active_total = min(
            total - provisional * ms.PROVISIONAL_TARGET_WEIGHT,
            variant.max_single_weight * active,
        )
        active_weight = max(0.0, active_total) / active
        return [
            ms.PROVISIONAL_TARGET_WEIGHT
            if str(row.get("mode_state") or ms.UNKNOWN) == ms.PROVISIONAL
            else active_weight
            for row in rows
        ]
    return ms.target_weights([str(row.get("mode_state") or ms.UNKNOWN) for row in rows])


def _ranked_candidates(
    candidates: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, ms.ModeDecision],
    *,
    max_per_mode: int,
) -> list[dict[str, Any]]:
    annotated = ms.annotate_candidates(candidates, decisions)
    ranked = ms.select_executable_candidates(annotated, top_n=3)
    ranked.sort(key=lambda row: (
        int(_num(row.get("mode_exec_candidate_rank"), 9999)),
        str(row.get("code") or ""),
    ))
    output: list[dict[str, Any]] = []
    mode_counts: dict[str, int] = defaultdict(int)
    for row in ranked:
        if not row.get("mode_trade_eligible"):
            continue
        mode = str(row.get("mode") or "")
        cap = 1 if row.get("mode_state") == ms.PROVISIONAL else max_per_mode
        if mode_counts[mode] >= cap:
            continue
        mode_counts[mode] += 1
        output.append(dict(row))
    return output


def _select_proxy(
    candidates: Sequence[Mapping[str, Any]],
    *,
    day: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
    variant: Variant,
) -> list[dict[str, Any]]:
    modes = sorted({str(row.get("mode") or "") for row in candidates if row.get("mode")})
    decisions = {
        mode: variant.decider(mode, day, evidence, trade_days)
        for mode in modes
    }
    ranked = _ranked_candidates(candidates, decisions, max_per_mode=variant.max_per_mode)[:3]
    weights = _variant_weights(ranked, variant)
    return [dict(row, mode_exec_target_weight=weight) for row, weight in zip(ranked, weights)]


def _monthly_returns(daily: Sequence[Mapping[str, Any]], final_equity: float) -> dict[str, float]:
    by_month: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in daily:
        by_month[str(row["date"])[:7]].append(row)
    output: dict[str, float] = {}
    previous = INITIAL_CAPITAL
    months = sorted(by_month)
    for index, month in enumerate(months):
        end_equity = float(by_month[month][-1]["equity_close"])
        if index == len(months) - 1:
            end_equity = final_equity
        output[month] = (end_equity / previous - 1.0) * 100.0 if previous else 0.0
        previous = end_equity
    return output


def run_proxy_variant(
    *,
    variant: Variant,
    frame: pd.DataFrame,
    evidence: Sequence[ms.ModeEvidenceRow],
    market: Mapping[str, float],
    trade_days: Sequence[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    replay_days = [day for day in trade_days if start <= day <= end]
    candidates_by_day = {
        day: group.to_dict(orient="records")
        for day, group in frame[frame["date"].between(start, end)].groupby("date")
    }
    cohorts: list[dict[str, float | int | str]] = []
    daily: list[dict[str, Any]] = []
    positions = 0
    same_mode_extra_positions = 0
    for day_index, day in enumerate(replay_days):
        settled_pnl = sum(float(row["pnl"]) for row in cohorts if int(row["exit_index"]) < day_index)
        nav = INITIAL_CAPITAL + settled_pnl
        open_cost = sum(float(row["cost"]) for row in cohorts if int(row["exit_index"]) >= day_index)
        cash = max(0.0, nav - open_cost)
        selected = _select_proxy(
            candidates_by_day.get(day, []),
            day=day,
            evidence=evidence,
            trade_days=trade_days,
            variant=variant,
        )
        target_cost = sum(_num(row.get("mode_exec_target_weight")) * nav for row in selected)
        available = min(cash, nav * 0.50)
        scale = min(1.0, available / target_cost) if target_cost > 0 else 0.0
        cost = pnl = market_pnl = 0.0
        position_rows: list[dict[str, Any]] = []
        mode_counts: dict[str, int] = defaultdict(int)
        for row in selected:
            cash_out = _num(row.get("mode_exec_target_weight")) * nav * scale
            if cash_out <= 0:
                continue
            mode = str(row.get("mode") or "")
            mode_counts[mode] += 1
            ret = _num(row.get("ret"))
            market_ret = _num(market.get(day))
            cost += cash_out
            pnl += cash_out * ret / 100.0
            market_pnl += cash_out * market_ret / 100.0
            positions += 1
            position_rows.append({
                "code": row.get("code"),
                "mode": mode,
                "state": row.get("mode_state"),
                "weight": _num(row.get("mode_exec_target_weight")) * scale,
                "ret": ret,
                "market_ret": market_ret,
            })
        same_mode_extra_positions += sum(max(0, count - 1) for count in mode_counts.values())
        if cost > 0:
            cohorts.append({
                "signal_date": day,
                "exit_index": day_index + 1,
                "cost": cost,
                "pnl": pnl,
                "market_pnl": market_pnl,
            })
        equity_close = INITIAL_CAPITAL + sum(
            float(row["pnl"]) for row in cohorts if int(row["exit_index"]) <= day_index
        )
        daily.append({
            "date": day,
            "batch_exposure_pct": cost / nav * 100.0 if nav else 0.0,
            "batch_pnl": pnl,
            "equity_close": equity_close,
            "positions": position_rows,
        })

    final_equity = INITIAL_CAPITAL + sum(float(row["pnl"]) for row in cohorts)
    market_equity = INITIAL_CAPITAL + sum(float(row["market_pnl"]) for row in cohorts)
    deployed_notional = sum(float(row["cost"]) for row in cohorts)
    peak = INITIAL_CAPITAL
    max_drawdown = 0.0
    for row in daily:
        equity = float(row["equity_close"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
    peak = max(peak, final_equity)
    max_drawdown = max(max_drawdown, (peak - final_equity) / peak if peak else 0.0)
    monthly = _monthly_returns(daily, final_equity)
    return {
        "name": variant.name,
        "family": variant.family,
        "max_per_mode": variant.max_per_mode,
        "allocation": variant.allocation,
        "return_pct": (final_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "market_return_same_exposure_pct": (market_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "alpha_market_pp": (final_equity - market_equity) / INITIAL_CAPITAL * 100.0,
        "deployed_return_pct": (
            (final_equity - INITIAL_CAPITAL) / deployed_notional * 100.0
            if deployed_notional else 0.0
        ),
        "max_drawdown_pct": max_drawdown * 100.0,
        "return_to_drawdown": (
            ((final_equity / INITIAL_CAPITAL - 1.0) * 100.0) / (max_drawdown * 100.0)
            if max_drawdown else 0.0
        ),
        "trade_days": sum(bool(row["positions"]) for row in daily),
        "positions": positions,
        "same_mode_extra_positions": same_mode_extra_positions,
        "average_daily_new_exposure_pct": statistics.mean(
            row["batch_exposure_pct"] for row in daily
        ) if daily else 0.0,
        "positive_months": sum(value > 0 for value in monthly.values()),
        "worst_month_pct": min(monthly.values(), default=0.0),
        "monthly_returns": monthly,
        "daily": daily,
    }


def run_exact_variant(
    *,
    variant: Variant,
    training_path: Path,
    trade_days: Sequence[str],
    start: str,
    end: str,
) -> dict[str, Any]:
    frame = exact._load_candidates(training_path)
    evidence = ms.load_live_executable_evidence(training_path)
    replay_days = [day for day in trade_days if start <= day <= end]
    candidates_by_day = {
        day: group.to_dict(orient="records")
        for day, group in frame[frame["date"].between(start, end)].groupby("date")
    }
    cohorts: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    positions = 0
    same_mode_extra_positions = 0
    for day_index, day in enumerate(replay_days):
        settled_pnl = sum(row["pnl"] for row in cohorts if row["exit_index"] < day_index)
        nav = INITIAL_CAPITAL + settled_pnl
        open_cost = sum(row["cost"] for row in cohorts if row["exit_index"] >= day_index)
        cash = max(0.0, nav - open_cost)
        candidates = candidates_by_day.get(day, [])
        modes = sorted({str(row.get("mode") or "") for row in candidates if row.get("mode")})
        decisions = {
            mode: variant.decider(mode, day, evidence, trade_days)
            for mode in modes
        }
        ranked = _ranked_candidates(candidates, decisions, max_per_mode=variant.max_per_mode)
        fillable: list[dict[str, Any]] = []
        for row in ranked:
            if not exact._truthy(row.get("executable_fillable")):
                continue
            price = exact._float(row.get("executable_entry_price"))
            ret = exact._float(row.get("executable_net_ret"), float("nan"))
            if price <= 0 or pd.isna(ret):
                continue
            fillable.append(dict(row, execution_price=price))
        orders = ms.plan_board_lot_orders(
            fillable,
            nav=nav,
            cash_limit=min(cash, nav * 0.50),
            fee_rate=FEE_RATE,
            price_key="execution_price",
            max_batch_ratio=0.50,
            weight_resolver=lambda subset: _variant_weights(subset, variant),
            max_single_weight=variant.max_single_weight,
        )
        cost = pnl = market_pnl = 0.0
        mode_counts: dict[str, int] = defaultdict(int)
        position_rows: list[dict[str, Any]] = []
        for row in orders:
            cash_out = exact._float(row.get("mode_exec_planned_cash_out"))
            ret = exact._float(row.get("executable_net_ret"))
            market_ret = exact._float(row.get("market_return_pct"))
            mode = str(row.get("mode") or "")
            mode_counts[mode] += 1
            cost += cash_out
            pnl += cash_out * ret / 100.0
            market_pnl += cash_out * market_ret / 100.0
            positions += 1
            position_rows.append({
                "code": row.get("code"),
                "mode": mode,
                "state": row.get("mode_state"),
                "ret": ret,
                "market_ret": market_ret,
                "cash_out": cash_out,
            })
        same_mode_extra_positions += sum(max(0, count - 1) for count in mode_counts.values())
        if cost > 0:
            cohorts.append({
                "signal_date": day,
                "exit_index": day_index + 1,
                "cost": cost,
                "pnl": pnl,
                "market_pnl": market_pnl,
            })
        equity_close = INITIAL_CAPITAL + sum(
            row["pnl"] for row in cohorts if row["exit_index"] <= day_index
        )
        daily.append({
            "date": day,
            "batch_exposure_pct": cost / nav * 100.0 if nav else 0.0,
            "batch_pnl": pnl,
            "equity_close": equity_close,
            "positions": position_rows,
        })

    final_equity = INITIAL_CAPITAL + sum(row["pnl"] for row in cohorts)
    market_equity = INITIAL_CAPITAL + sum(row["market_pnl"] for row in cohorts)
    deployed_notional = sum(row["cost"] for row in cohorts)
    peak = INITIAL_CAPITAL
    max_drawdown = 0.0
    for row in daily:
        equity = float(row["equity_close"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
    peak = max(peak, final_equity)
    max_drawdown = max(max_drawdown, (peak - final_equity) / peak if peak else 0.0)
    return {
        "name": variant.name,
        "window": f"{start}..{end}",
        "return_pct": (final_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "market_return_same_exposure_pct": (market_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "alpha_market_pp": (final_equity - market_equity) / INITIAL_CAPITAL * 100.0,
        "deployed_return_pct": (
            (final_equity - INITIAL_CAPITAL) / deployed_notional * 100.0
            if deployed_notional else 0.0
        ),
        "max_drawdown_pct": max_drawdown * 100.0,
        "trade_days": sum(bool(row["positions"]) for row in daily),
        "positions": positions,
        "same_mode_extra_positions": same_mode_extra_positions,
        "average_daily_new_exposure_pct": statistics.mean(
            row["batch_exposure_pct"] for row in daily
        ) if daily else 0.0,
        "daily": daily,
    }


def _marginal_stats(
    *,
    variant_result: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in variant_result["daily"]:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in day["positions"]:
            grouped[str(row.get("mode") or "")].append(row)
        for mode, mode_rows in grouped.items():
            if len(mode_rows) < 2:
                continue
            for rank, row in enumerate(mode_rows, 1):
                rows.append({
                    "date": day["date"],
                    "mode": mode,
                    "rank": rank,
                    "ret": _num(row.get("ret")),
                    "alpha": _num(row.get("ret")) - _num(row.get("market_ret")),
                })
    output: list[dict[str, Any]] = []
    for rank in sorted({row["rank"] for row in rows}):
        scoped = [row for row in rows if row["rank"] == rank]
        output.append({
            "rank": rank,
            "n": len(scoped),
            "mean_return_pct": statistics.mean(row["ret"] for row in scoped),
            "mean_alpha_market_pp": statistics.mean(row["alpha"] for row in scoped),
            "hit_rate": sum(row["ret"] > 0 for row in scoped) / len(scoped) if scoped else 0.0,
        })
    return output


def _pareto_names(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    output: list[str] = []
    for row in rows:
        dominated = any(
            other["name"] != row["name"]
            and other["return_pct"] >= row["return_pct"]
            and other["alpha_market_pp"] >= row["alpha_market_pp"]
            and other["deployed_return_pct"] >= row["deployed_return_pct"]
            and other["max_drawdown_pct"] <= row["max_drawdown_pct"]
            and (
                other["return_pct"] > row["return_pct"]
                or other["alpha_market_pp"] > row["alpha_market_pp"]
                or other["deployed_return_pct"] > row["deployed_return_pct"]
                or other["max_drawdown_pct"] < row["max_drawdown_pct"]
            )
            for other in rows
        )
        if not dominated:
            output.append(str(row["name"]))
    return output


def _paired_block_stability(
    challenger: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    block_size: int,
    samples: int = 20_000,
) -> dict[str, Any]:
    """Bootstrap paired daily PnL differences without claiming IID sessions."""
    challenger_daily = {
        str(row["date"]): _num(row.get("batch_pnl")) / INITIAL_CAPITAL * 100.0
        for row in challenger["daily"]
    }
    baseline_daily = {
        str(row["date"]): _num(row.get("batch_pnl")) / INITIAL_CAPITAL * 100.0
        for row in baseline["daily"]
    }
    days = sorted(set(challenger_daily) | set(baseline_daily))
    differences = [
        challenger_daily.get(day, 0.0) - baseline_daily.get(day, 0.0)
        for day in days
    ]
    if not differences:
        return {}
    rng = random.Random(20260710 + block_size + len(days))
    boot_means: list[float] = []
    for _ in range(samples):
        sample: list[float] = []
        while len(sample) < len(differences):
            start = rng.randrange(len(differences))
            sample.extend(
                differences[(start + offset) % len(differences)]
                for offset in range(block_size)
            )
        boot_means.append(statistics.mean(sample[:len(differences)]))
    boot_means.sort()
    best = max(differences)
    return {
        "days": len(days),
        "block_size": block_size,
        "mean_daily_delta_pp": statistics.mean(differences),
        "sum_daily_delta_pp": sum(differences),
        "sum_without_best_delta_pp": sum(differences) - best,
        "best_delta_date": days[differences.index(best)],
        "best_delta_pp": best,
        "positive_probability": sum(value > 0 for value in boot_means) / samples,
        "ci95_daily_delta_pp": [
            boot_means[int(samples * 0.025)],
            boot_means[int(samples * 0.975)],
        ],
    }


def markdown(result: Mapping[str, Any]) -> str:
    proxy_rows = result["proxy"]
    exact_rows = {row["name"]: row for row in result["exact"]}
    current = next(row for row in proxy_rows if row["name"] == "current_modecap1")
    lines = [
        "# Aggressive Mode Switch and Same-Mode Breadth Research",
        "",
        "## Boundary",
        "",
        f"- Historical proxy: {result['start']}..{result['end']}, expanding-OOS open[D] -> close[D+1].",
        f"- Strict executable: {result['exact_start']}..{result['exact_end']}, opening-window fills and board lots.",
        "- Every mode outcome is delayed to D+2. No variant changes Book-B production authority.",
        "- The core matrix is pre-defined as 4 switch families x same-mode caps 1/2/3; targeted sleeve and best-day-robust variants test the mechanism, not a threshold grid.",
        "",
        "## Six-Month Proxy",
        "",
        "| variant | return | market | alpha | deployed | MDD | R/MDD | +months | worst month | days | positions | same-mode extras | exposure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(proxy_rows, key=lambda item: item["return_pct"], reverse=True):
        lines.append(
            f"| {row['name']} | {row['return_pct']:+.2f}% | "
            f"{row['market_return_same_exposure_pct']:+.2f}% | {row['alpha_market_pp']:+.2f}pp | "
            f"{row['deployed_return_pct']:+.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['return_to_drawdown']:.2f} | {row['positive_months']}/{len(row['monthly_returns'])} | "
            f"{row['worst_month_pct']:+.2f}% | {row['trade_days']} | {row['positions']} | "
            f"{row['same_mode_extra_positions']} | {row['average_daily_new_exposure_pct']:.2f}% |"
        )
    lines.extend([
        "",
        "## Strict Executable Cross-Check",
        "",
        "| variant | return | market | alpha | deployed | MDD | days | positions | same-mode extras | exposure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in sorted(result["exact"], key=lambda item: item["return_pct"], reverse=True):
        lines.append(
            f"| {row['name']} | {row['return_pct']:+.2f}% | "
            f"{row['market_return_same_exposure_pct']:+.2f}% | {row['alpha_market_pp']:+.2f}pp | "
            f"{row['deployed_return_pct']:+.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['trade_days']} | {row['positions']} | {row['same_mode_extra_positions']} | "
            f"{row['average_daily_new_exposure_pct']:.2f}% |"
        )
    lines.extend([
        "",
        "## Monthly Proxy Returns",
        "",
    ])
    months = sorted({month for row in proxy_rows for month in row["monthly_returns"]})
    lines.append("| variant | " + " | ".join(months) + " |")
    lines.append("|---|" + "---:|" * len(months))
    for row in sorted(proxy_rows, key=lambda item: item["return_pct"], reverse=True):
        lines.append(
            f"| {row['name']} | "
            + " | ".join(
                f"{row['monthly_returns'].get(month, 0.0):+.2f}%" for month in months
            )
            + " |"
        )
    lines.extend([
        "",
        "## Same-Mode Marginal Evidence",
        "",
        "The ranks below are conditional on days where the production variant bought at least two names from one mode.",
        "",
        "| same-mode rank | n | mean return | market alpha | hit rate |",
        "|---:|---:|---:|---:|---:|",
    ])
    for row in result["marginal_proxy"]:
        lines.append(
            f"| {row['rank']} | {row['n']} | {row['mean_return_pct']:+.2f}% | "
            f"{row['mean_alpha_market_pp']:+.2f}pp | {row['hit_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Decision Audit",
        "",
        f"- Production baseline: return {current['return_pct']:+.2f}%, alpha "
        f"{current['alpha_market_pp']:+.2f}pp, MDD {current['max_drawdown_pct']:.2f}%.",
        "- Six-month Pareto frontier: " + ", ".join(result["proxy_pareto"]) + ".",
        "- A candidate is not promotable merely for topping the proxy table; it must also avoid a strict executable alpha reversal.",
    ])
    strict_current = exact_rows["current_modecap1"]
    qualifying = [
        row for row in proxy_rows
        if row["return_pct"] > current["return_pct"]
        and row["alpha_market_pp"] > current["alpha_market_pp"]
        and exact_rows[row["name"]]["return_pct"] > strict_current["return_pct"]
        and exact_rows[row["name"]]["alpha_market_pp"] >= strict_current["alpha_market_pp"]
    ]
    if qualifying:
        lines.append(
            "- Cross-horizon improvement candidates: "
            + ", ".join(row["name"] for row in qualifying)
            + "."
        )
    else:
        lines.append("- No variant improves both proxy return/alpha and strict executable return/alpha.")
    stability = result["stability"]
    lines.extend([
        "",
        "## Stability Check",
        "",
        "| comparison | daily delta | bootstrap P(delta>0) | 95% interval | delta without best day | best delta day |",
        "|---|---:|---:|---:|---:|---|",
    ])
    for label, row in stability.items():
        lines.append(
            f"| {label} | {row['mean_daily_delta_pp']:+.3f}pp | "
            f"{row['positive_probability']:.1%} | "
            f"[{row['ci95_daily_delta_pp'][0]:+.3f}, {row['ci95_daily_delta_pp'][1]:+.3f}]pp | "
            f"{row['sum_without_best_delta_pp']:+.2f}pp | "
            f"{row['best_delta_date']} ({row['best_delta_pp']:+.2f}pp) |"
        )
    lines.extend([
        "",
        "- The block bootstrap is a sensitivity check, not a formal PASS. An interval crossing zero keeps the production gate unchanged.",
    ])
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `modecap1` treats each mode as one correlated sleeve: extra names diversify stock risk but do not increase mode risk budget.",
        "- `modesleeve25` keeps multiple names but splits a fixed 25% ACTIVE mode sleeve among them; distinct modes can still lift the batch toward 50%.",
        "- `modecap2/3` progressively treats same-mode breadth as evidence that more mode capital should be deployed.",
        "- `fast_promote` is upside-aggressive only; `fast_hard` also exits recent weakness; `event_hard` uses the last five mode occurrences within 20 sessions for sparse modes.",
        "- `fast_early` lowers only the upside promotion floor to 2 mode days/3 signals; aggressive batch variants separately test capital concentration without changing the signal gate.",
        "- The historical proxy has broader coverage but theoretical fills. The strict leg has correct fills but a small sample. Disagreement means more forward evidence, not parameter selection by taste.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=proxy.DEFAULT_PANEL)
    parser.add_argument("--training", type=Path, default=exact.DEFAULT_TRAINING)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--exact-start", default="2026-06-02")
    parser.add_argument("--exact-end", default="2026-07-09")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    frame = proxy._load_panel(args.panel)
    client = proxy._client()
    market = proxy._market_map(client, sorted(frame["date"].unique()))
    evidence = proxy._evidence(frame, market)
    trade_days = list_trade_days(
        client,
        min("2025-08-01", args.start),
        max(args.end, args.exact_end, "2026-07-13"),
    )
    if not trade_days:
        raise SystemExit("trade calendar unavailable")

    variants = _variants()
    proxy_rows = [
        run_proxy_variant(
            variant=variant,
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
        )
        for variant in variants
    ]
    exact_rows = [
        run_exact_variant(
            variant=variant,
            training_path=args.training,
            trade_days=trade_days,
            start=args.exact_start,
            end=args.exact_end,
        )
        for variant in variants
    ]
    current = next(row for row in proxy_rows if row["name"] == "current_modecap1")
    exact_by_name = {row["name"]: row for row in exact_rows}
    proxy_by_name = {row["name"]: row for row in proxy_rows}
    challenger = next(row for row in proxy_rows if row["name"] == "fast_promote_modecap1")
    result = {
        "start": args.start,
        "end": args.end,
        "exact_start": args.exact_start,
        "exact_end": args.exact_end,
        "proxy": proxy_rows,
        "exact": exact_rows,
        "proxy_pareto": _pareto_names(proxy_rows),
        "marginal_proxy": _marginal_stats(variant_result=current),
        "stability": {
            "proxy fast_promote_modecap1 - production": _paired_block_stability(
                challenger,
                current,
                block_size=5,
            ),
            "strict fast_promote_modecap1 - production": _paired_block_stability(
                exact_by_name["fast_promote_modecap1"],
                exact_by_name["current_modecap1"],
                block_size=3,
            ),
            "proxy batch33 - production": _paired_block_stability(
                proxy_by_name["fast_promote_modecap1_batch33_50_50"],
                current,
                block_size=5,
            ),
            "strict batch33 - production": _paired_block_stability(
                exact_by_name["fast_promote_modecap1_batch33_50_50"],
                exact_by_name["current_modecap1"],
                block_size=3,
            ),
            "proxy batch50 - batch33": _paired_block_stability(
                proxy_by_name["fast_promote_modecap1_batch50"],
                proxy_by_name["fast_promote_modecap1_batch33_50_50"],
                block_size=5,
            ),
            "strict batch50 - batch33": _paired_block_stability(
                exact_by_name["fast_promote_modecap1_batch50"],
                exact_by_name["fast_promote_modecap1_batch33_50_50"],
                block_size=3,
            ),
        },
    }
    suffix = f"{args.start}_{args.end}"
    output = args.output or ROOT / "output" / "research" / f"mode_switch_aggressive_{suffix}.md"
    json_output = args.json_output or ROOT / "output" / "research" / f"mode_switch_aggressive_{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(result), encoding="utf-8")
    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(markdown(result))
    print(f"wrote {output}")
    print(f"wrote {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
