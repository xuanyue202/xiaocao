#!/usr/bin/env python3
"""Six-month walk-forward proxy comparison for short-line mode switching.

This is a historical proxy, not an executable-fill replay. It uses the existing
expanding-OOS candidate panel and its net open[D] -> close[D+1] label, applies
every mode decision with D+2 availability, and compares allocation policies on
the same 25%/45%/50% NAV schedule. Real live authority still comes only from
``training_rows.parquet`` executable labels.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KRONOS_SCRIPTS = ROOT / "kronos_screen" / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(KRONOS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(KRONOS_SCRIPTS))

import forward_eval  # type: ignore  # noqa: E402

from scripts import research_mode_switch_replay as exact_replay  # noqa: E402
from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.backtest import list_trade_days  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.strategy import mode_switch as ms  # noqa: E402


DEFAULT_PANEL = ROOT / "output" / "research" / "kp_mode_rotation_oos_rows_2025-09-29_2026-06-29.parquet"
DEFAULT_START = "2026-01-01"
DEFAULT_END = "2026-06-30"
INITIAL_CAPITAL = 100_000.0


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    return XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db"),
    )


def _num(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _load_panel(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).copy()
    required = {"date", "code", "mode", "ret", "rank_score", "k_score", "p_score"}
    if frame.empty or not required.issubset(frame.columns):
        missing = sorted(required - set(frame.columns))
        raise SystemExit(f"historical panel missing columns: {missing}")
    frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame[~frame["code"].astype(str).str.endswith(".BJSE")]
    for column in ("ret", "rank_score", "k_score", "p_score", "mode_confidence"):
        if column not in frame.columns:
            frame[column] = 50.0 if column == "mode_confidence" else 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["ret", "rank_score", "k_score", "p_score"]).sort_values(
        ["date", "code"]
    ).drop_duplicates(["date", "code", "mode"], keep="last")


def _market_map(client: XiaocaoClient, dates: Sequence[str]) -> dict[str, float]:
    return forward_eval._market_return_map(
        client,
        sorted({str(day)[:10] for day in dates}),
        forward_eval._load_reconstructed_daily(),
    )


def _evidence(frame: pd.DataFrame, market: Mapping[str, float]) -> list[ms.ModeEvidenceRow]:
    rows: list[ms.ModeEvidenceRow] = []
    for row in frame.itertuples():
        market_return = market.get(str(row.date))
        if market_return is None:
            continue
        rows.append(ms.ModeEvidenceRow(
            signal_date=str(row.date),
            code=str(row.code),
            mode=str(row.mode),
            net_return_pct=float(row.ret),
            source="historical_expanding_oos_proxy",
            market_return_pct=float(market_return),
        ))
    return rows


def _mean_lcb(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, float("-inf")
    mean = statistics.mean(values)
    if len(values) <= 1:
        return mean, float("-inf")
    return mean, mean - ms.LCB80_Z * statistics.stdev(values) / math.sqrt(len(values))


def _legacy_window_stats(
    mode: str,
    asof: str,
    window: int,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeWindowStats:
    days = set(ms._available_window_days(asof, window, trade_days, evidence))
    by_day: dict[str, list[ms.ModeEvidenceRow]] = defaultdict(list)
    for row in evidence:
        if row.signal_date in days:
            by_day[row.signal_date].append(row)
    raw_returns: list[float] = []
    alpha_pool: list[float] = []
    signals = 0
    latest: str | None = None
    for day in sorted(by_day):
        mode_rows = [row for row in by_day[day] if row.mode == mode]
        if not mode_rows:
            continue
        latest = day
        signals += len(mode_rows)
        mode_return = statistics.mean(row.net_return_pct for row in mode_rows)
        pool_return = statistics.mean(row.net_return_pct for row in by_day[day])
        raw_returns.append(mode_return)
        alpha_pool.append(mode_return - pool_return)
    mean, lower = _mean_lcb(alpha_pool)
    without_best = None
    if len(alpha_pool) > 1:
        remaining = list(alpha_pool)
        remaining.remove(max(remaining))
        without_best = statistics.mean(remaining)
    return ms.ModeWindowStats(
        window_days=window,
        signal_days=len(alpha_pool),
        signals=signals,
        market_days=len(alpha_pool),
        effective_days=float(len(alpha_pool)),
        raw_return_mean=statistics.mean(raw_returns) if raw_returns else 0.0,
        alpha_pool_mean=mean,
        alpha_pool_lcb80=lower,
        positive_alpha_days=sum(value > 0 for value in alpha_pool),
        alpha_pool_without_best=without_best,
        # Legacy confidence and gate only used alpha_pool. Mirror it here so
        # current annotation reconstructs the historical confidence faithfully.
        alpha_market_mean=mean,
        alpha_market_lcb80=lower,
        positive_market_alpha_days=sum(value > 0 for value in alpha_pool),
        alpha_market_without_best=without_best,
        latest_signal_date=latest,
        weighting="legacy_equal_signal_day_pool_only",
    )


def legacy_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    windows = {
        window: _legacy_window_stats(mode, asof, window, evidence, trade_days)
        for window, _, _ in ms.FORMAL_WINDOWS
    }
    state = ms.UNKNOWN
    selected: ms.ModeWindowStats | None = None
    reason = "no legacy executable window meets the sample floor"
    for window, min_days, min_signals in ms.FORMAL_WINDOWS:
        stats = windows[window]
        if stats.signal_days < min_days or stats.signals < min_signals:
            continue
        selected = stats
        state = ms.ACTIVE if stats.alpha_pool_lcb80 > 0 else ms.COLD
        reason = (
            f"legacy {window}d equal-day pool alpha mean/LCB80 "
            f"{stats.alpha_pool_mean:+.2f}/{stats.alpha_pool_lcb80:+.2f}pp"
        )
        break
    fast = _legacy_window_stats(mode, asof, ms.FAST_WINDOW, evidence, trade_days)
    windows[ms.FAST_WINDOW] = fast
    if (
        state != ms.ACTIVE
        and fast.signal_days >= ms.FAST_MIN_DAYS
        and fast.signals >= ms.FAST_MIN_SIGNALS
        and fast.positive_alpha_days >= ms.FAST_MIN_POSITIVE_DAYS
        and fast.alpha_pool_without_best is not None
        and fast.alpha_pool_without_best > 0
    ):
        state = ms.PROVISIONAL
        selected = fast
        reason = "legacy 5d fast pool-only reactivation"
    usable_days = set(ms._available_window_days(asof, 120, trade_days, evidence))
    latest = max(
        (row.signal_date for row in evidence if row.mode == mode and row.signal_date in usable_days),
        default=None,
    )
    return ms.ModeDecision(
        mode=mode,
        state=state,
        max_picks=3 if state == ms.ACTIVE else 1 if state == ms.PROVISIONAL else 0,
        selected_window=selected.window_days if selected else None,
        reason=reason,
        windows=windows,
        evidence_source="historical_legacy_proxy",
        latest_evidence_date=latest,
    )


def _daily_alpha_values(
    mode: str,
    asof: str,
    window: int,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> tuple[list[float], list[float]]:
    days = set(ms._available_window_days(asof, window, trade_days, evidence))
    by_day: dict[str, list[ms.ModeEvidenceRow]] = defaultdict(list)
    for row in evidence:
        if row.signal_date in days:
            by_day[row.signal_date].append(row)
    pool_values: list[float] = []
    market_values: list[float] = []
    for day in sorted(by_day):
        mode_rows = [row for row in by_day[day] if row.mode == mode]
        if not mode_rows:
            continue
        mode_return = statistics.mean(row.net_return_pct for row in mode_rows)
        pool_return = statistics.mean(row.net_return_pct for row in by_day[day])
        markets = [row.market_return_pct for row in by_day[day] if row.market_return_pct is not None]
        pool_values.append(mode_return - pool_return)
        if markets:
            market_values.append(mode_return - statistics.mean(markets))
    return pool_values, market_values


def robust_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
    *,
    uncertainty_provisional: bool = False,
    soft_recent_reactivation: bool = False,
) -> ms.ModeDecision:
    windows = {
        window: ms._window_stats(mode, asof, window, evidence, trade_days)
        for window, _, _ in ms.FORMAL_WINDOWS
    }
    state = ms.UNKNOWN
    selected: ms.ModeWindowStats | None = None
    reason = "no robust executable window meets the sample floor"
    for window, min_days, min_signals in ms.FORMAL_WINDOWS:
        stats = windows[window]
        if stats.signal_days < min_days or stats.signals < min_signals:
            continue
        selected = stats
        complete = stats.market_days == stats.signal_days
        robust_positive = (
            complete
            and stats.alpha_pool_lcb80 > 0
            and stats.alpha_market_lcb80 is not None
            and stats.alpha_market_lcb80 > 0
            and stats.alpha_pool_without_best is not None
            and stats.alpha_pool_without_best > 0
            and stats.alpha_market_without_best is not None
            and stats.alpha_market_without_best > 0
        )
        pool_upper = 2 * stats.alpha_pool_mean - stats.alpha_pool_lcb80
        market_upper = (
            2 * stats.alpha_market_mean - stats.alpha_market_lcb80
            if stats.alpha_market_mean is not None and stats.alpha_market_lcb80 is not None
            else float("-inf")
        )
        robust_negative = pool_upper < 0 or market_upper < 0
        if robust_positive:
            state = ms.ACTIVE
        elif not complete:
            state = ms.UNKNOWN
        elif uncertainty_provisional and not robust_negative:
            state = ms.PROVISIONAL
        else:
            state = ms.COLD
        reason = (
            f"robust {window}d dual alpha with best-day removal "
            f"pool {stats.alpha_pool_mean:+.2f}/{stats.alpha_pool_lcb80:+.2f}, "
            f"market {(stats.alpha_market_mean or 0.0):+.2f}/"
            f"{(stats.alpha_market_lcb80 or float('-inf')):+.2f}pp; "
            f"uncertainty={'PROVISIONAL' if uncertainty_provisional else 'COLD'}"
        )
        break

    fast = ms._window_stats(mode, asof, ms.FAST_WINDOW, evidence, trade_days)
    windows[ms.FAST_WINDOW] = fast
    pool_values, market_values = _daily_alpha_values(
        mode, asof, ms.FAST_WINDOW, evidence, trade_days
    )
    market_complete = len(market_values) == len(pool_values)
    dense_floor = fast.signal_days >= 3 and fast.signals >= 5 and market_complete
    sparse_floor = fast.signal_days >= 3 and fast.signals >= 3 and market_complete
    pool_majority_bad = (
        bool(pool_values)
        and statistics.median(pool_values) <= 0
        and fast.positive_alpha_days * 2 < fast.signal_days
    )
    market_majority_bad = (
        bool(market_values)
        and statistics.median(market_values) <= 0
        and fast.positive_market_alpha_days * 2 < fast.signal_days
    )
    sparse_streak_bad = sparse_floor and (
        fast.positive_alpha_days == 0 or fast.positive_market_alpha_days == 0
    )
    cooling = state == ms.ACTIVE and (
        (
            dense_floor
            and (
                fast.alpha_pool_mean <= 0
                or fast.alpha_market_mean is None
                or fast.alpha_market_mean <= 0
                or pool_majority_bad
                or market_majority_bad
            )
        )
        or sparse_streak_bad
    )
    strict_reactivation = (
        state != ms.ACTIVE
        and dense_floor
        and fast.positive_alpha_days >= ms.FAST_MIN_POSITIVE_DAYS
        and fast.positive_market_alpha_days >= ms.FAST_MIN_POSITIVE_DAYS
        and fast.alpha_pool_without_best is not None
        and fast.alpha_pool_without_best > 0
        and fast.alpha_market_without_best is not None
        and fast.alpha_market_without_best > 0
    )
    recent_majority_positive = (
        state != ms.ACTIVE
        and sparse_floor
        and fast.alpha_pool_mean > 0
        and fast.alpha_market_mean is not None
        and fast.alpha_market_mean > 0
        and fast.positive_alpha_days * 2 > fast.signal_days
        and fast.positive_market_alpha_days * 2 > fast.signal_days
        and statistics.median(pool_values) > 0
        and statistics.median(market_values) > 0
    )
    reactivation = strict_reactivation or (
        soft_recent_reactivation and recent_majority_positive
    )
    if cooling:
        state = ms.PROVISIONAL
        selected = fast
        reason = (
            "robust 5d cooling: negative mean/median-majority or sparse three-day streak; "
            f"pool positives {fast.positive_alpha_days}/{fast.signal_days}, "
            f"market positives {fast.positive_market_alpha_days}/{fast.signal_days}"
        )
    elif reactivation:
        state = ms.PROVISIONAL
        selected = fast
        reason = "robust 5d dual reactivation"

    usable_days = set(ms._available_window_days(asof, 120, trade_days, evidence))
    latest = max(
        (row.signal_date for row in evidence if row.mode == mode and row.signal_date in usable_days),
        default=None,
    )
    return ms.ModeDecision(
        mode=mode,
        state=state,
        max_picks=3 if state == ms.ACTIVE else 1 if state == ms.PROVISIONAL else 0,
        selected_window=selected.window_days if selected else None,
        reason=reason,
        windows=windows,
        evidence_source="historical_robust_proxy",
        latest_evidence_date=latest,
    )


def balanced_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Reserve COLD for robust harm; route statistical uncertainty to one slot."""
    return robust_decide_mode(
        mode,
        asof,
        evidence,
        trade_days,
        uncertainty_provisional=True,
    )


def recent_confirmed_decide_mode(
    mode: str,
    asof: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
) -> ms.ModeDecision:
    """Keep uncertainty out unless recent dual-alpha breadth confirms it."""
    return robust_decide_mode(
        mode,
        asof,
        evidence,
        trade_days,
        soft_recent_reactivation=True,
    )


Decider = Callable[[str, str, Sequence[ms.ModeEvidenceRow], Sequence[str]], ms.ModeDecision]


def _mode_selector(
    candidates: list[dict[str, Any]],
    day: str,
    evidence: Sequence[ms.ModeEvidenceRow],
    trade_days: Sequence[str],
    decider: Decider,
) -> tuple[list[dict[str, Any]], list[ms.ModeDecision]]:
    decisions = {
        mode: decider(mode, day, evidence, trade_days)
        for mode in sorted({str(row.get("mode") or "") for row in candidates if row.get("mode")})
    }
    annotated = ms.annotate_candidates(candidates, decisions)
    selected = [
        row for row in ms.select_executable_candidates(annotated, top_n=3)
        if row.get("mode_exec_star")
    ]
    return selected, list(decisions.values())


def _pipe_selector(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [row for row in candidates if bool(row.get("kp_keep"))]
    selected = sorted(
        eligible,
        key=lambda row: (-_num(row.get("p_score")), -_num(row.get("rank_score")), str(row.get("code"))),
    )[:3]
    weights = ms.target_weights([ms.ACTIVE] * len(selected))
    return [dict(row, mode_exec_target_weight=weight) for row, weight in zip(selected, weights)]


def _monthly_returns(daily: list[dict[str, Any]], final_equity: float) -> dict[str, float]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        by_month[str(row["date"])[:7]].append(row)
    out: dict[str, float] = {}
    previous = INITIAL_CAPITAL
    months = sorted(by_month)
    for index, month in enumerate(months):
        end_equity = float(by_month[month][-1]["equity_close"])
        if index == len(months) - 1:
            end_equity = final_equity
        out[month] = (end_equity / previous - 1.0) * 100.0 if previous else 0.0
        previous = end_equity
    return out


def simulate(
    *,
    name: str,
    frame: pd.DataFrame,
    evidence: Sequence[ms.ModeEvidenceRow],
    market: Mapping[str, float],
    trade_days: Sequence[str],
    start: str,
    end: str,
    decider: Decider | None,
) -> dict[str, Any]:
    replay_days = [day for day in trade_days if start <= day <= end]
    candidates_by_day = {
        day: group.to_dict(orient="records")
        for day, group in frame[frame["date"].between(start, end)].groupby("date")
    }
    cohorts: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    cooling_events: list[dict[str, Any]] = []
    positions = 0
    for day_index, day in enumerate(replay_days):
        settled_pnl = sum(row["pnl"] for row in cohorts if row["exit_index"] < day_index)
        nav = INITIAL_CAPITAL + settled_pnl
        open_cost = sum(row["cost"] for row in cohorts if row["exit_index"] >= day_index)
        cash = max(0.0, nav - open_cost)
        candidates = candidates_by_day.get(day, [])
        decisions: list[ms.ModeDecision] = []
        if decider is None:
            selected = _pipe_selector(candidates)
        else:
            selected, decisions = _mode_selector(candidates, day, evidence, trade_days, decider)
        for decision in decisions:
            if "cooling" in decision.reason:
                cooling_events.append({
                    "date": day,
                    "mode": decision.mode,
                    "state": decision.state,
                    "window": decision.selected_window,
                    "reason": decision.reason,
                })

        target_cost = sum(_num(row.get("mode_exec_target_weight")) * nav for row in selected)
        available = min(cash, nav * 0.50)
        scale = min(1.0, available / target_cost) if target_cost > 0 else 0.0
        cost = 0.0
        pnl = 0.0
        market_pnl = 0.0
        position_rows = []
        for row in selected:
            cash_out = _num(row.get("mode_exec_target_weight")) * nav * scale
            if cash_out <= 0:
                continue
            ret = _num(row.get("ret"))
            market_ret = _num(market.get(day))
            cost += cash_out
            pnl += cash_out * ret / 100.0
            market_pnl += cash_out * market_ret / 100.0
            positions += 1
            position_rows.append({
                "code": row.get("code"),
                "mode": row.get("mode"),
                "state": row.get("mode_state", ms.ACTIVE if decider is None else ms.UNKNOWN),
                "weight": _num(row.get("mode_exec_target_weight")) * scale,
                "ret": ret,
            })
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
            "nav": nav,
            "batch_exposure_pct": cost / nav * 100.0 if nav else 0.0,
            "batch_pnl": pnl,
            "batch_return_nav_pct": pnl / nav * 100.0 if nav else 0.0,
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
    max_drawdown = max(max_drawdown, (peak - final_equity) / peak if peak else 0.0)
    return {
        "name": name,
        "return_pct": (final_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "final_equity": final_equity,
        "market_return_same_exposure_pct": (market_equity / INITIAL_CAPITAL - 1.0) * 100.0,
        "alpha_market_pp": (final_equity - market_equity) / INITIAL_CAPITAL * 100.0,
        "deployed_return_pct": (
            sum(row["pnl"] for row in cohorts) / deployed_notional * 100.0
            if deployed_notional else 0.0
        ),
        "deployed_notional": deployed_notional,
        "max_drawdown_pct": max_drawdown * 100.0,
        "trade_days": sum(bool(row["positions"]) for row in daily),
        "positions": positions,
        "average_daily_new_exposure_pct": statistics.mean(
            row["batch_exposure_pct"] for row in daily
        ) if daily else 0.0,
        "monthly_returns": _monthly_returns(daily, final_equity),
        "cooling_events": cooling_events,
        "daily": daily,
    }


def strict_live_comparison(
    *,
    trade_days: Sequence[str],
    current_decider: Decider,
) -> list[dict[str, Any]]:
    training = ROOT / "output" / "live" / "training_rows.parquet"
    variants: list[tuple[str, Decider]] = [
        ("legacy_equal_pool_gate", legacy_decide_mode),
        ("current_weighted_dual_mean_cooling", current_decider),
        ("robust_tail_and_sparse_cooling_candidate", robust_decide_mode),
        ("balanced_uncertainty_provisional_candidate", balanced_decide_mode),
        ("recent_dual_majority_provisional_candidate", recent_confirmed_decide_mode),
    ]
    output: list[dict[str, Any]] = []
    original = ms.decide_mode
    try:
        for name, decider in variants:
            ms.decide_mode = decider
            for label, start in (("strict_20d", "2026-06-11"), ("all_executable", "2026-06-02")):
                result = exact_replay.run_replay(
                    training_path=training,
                    start=start,
                    end="2026-07-09",
                    initial_capital=INITIAL_CAPITAL,
                    fee_rate=0.0001,
                    trade_days=list(trade_days),
                )
                output.append({"variant": name, "window": label, **result["summary"]})
    finally:
        ms.decide_mode = original
    return output


def markdown(result: dict[str, Any]) -> str:
    variants = result["variants"]
    by_name = {row["name"]: row for row in variants}
    strict = {
        (row["variant"], row["window"]): row
        for row in result.get("strict_live_comparison", [])
    }
    lines = [
        "# Six-Month Mode-Switch Historical Proxy",
        "",
        "## Data Boundary",
        "",
        f"- Evaluation: {result['start']}..{result['end']}; warm-up evidence starts {result['evidence_start']}.",
        "- Candidate panel: expanding-OOS K/P rows; return is theoretical net open[D] -> close[D+1].",
        "- This is not the live opening-window executable-fill label and cannot replace the strict June live replay.",
        "- BJSE is excluded; mode outcomes become visible only on D+2; all variants use the same NAV 25%/45%/50% batch schedule.",
        "",
        "## Summary",
        "",
        "| variant | return | same-exposure market | alpha | deployed return | MDD | trade days | positions | avg new exposure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants:
        lines.append(
            f"| {row['name']} | {row['return_pct']:+.2f}% | "
            f"{row['market_return_same_exposure_pct']:+.2f}% | {row['alpha_market_pp']:+.2f}pp | "
            f"{row['deployed_return_pct']:+.2f}% | {row['max_drawdown_pct']:.2f}% | "
            f"{row['trade_days']} | {row['positions']} | "
            f"{row['average_daily_new_exposure_pct']:.2f}% |"
        )
    lines.extend(["", "## Monthly Returns", ""])
    months = sorted({month for row in variants for month in row["monthly_returns"]})
    lines.append("| variant | " + " | ".join(months) + " |")
    lines.append("|---|" + "---:|" * len(months))
    for row in variants:
        lines.append(
            f"| {row['name']} | "
            + " | ".join(f"{row['monthly_returns'].get(month, 0.0):+.2f}%" for month in months)
            + " |"
        )
    lines.extend([
        "",
        "## Strict Executable Cross-Check",
        "",
        "| window | variant | return | market | alpha | MDD | trade days | positions |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in result.get("strict_live_comparison", []):
        lines.append(
            f"| {row['window']} | {row['variant']} | {row['return_pct']:+.2f}% | "
            f"{row['same_exposure_market_return_pct']:+.2f}% | {row['alpha_market_pp']:+.2f}pp | "
            f"{row['max_drawdown_pct']:.2f}% | {row['trade_days']} | {row['positions']} |"
        )
    legacy = by_name.get("legacy_equal_pool_gate", {})
    current = by_name.get("current_weighted_dual_mean_cooling", {})
    legacy_live = strict.get(("legacy_equal_pool_gate", "all_executable"), {})
    current_live = strict.get(("current_weighted_dual_mean_cooling", "all_executable"), {})
    balanced_live = strict.get(("balanced_uncertainty_provisional_candidate", "all_executable"), {})
    recent_live = strict.get(("recent_dual_majority_provisional_candidate", "all_executable"), {})
    lines.extend([
        "",
        "## Verdict",
        "",
        f"- Six-month proxy: current {current.get('return_pct', 0.0):+.2f}% / MDD "
        f"{current.get('max_drawdown_pct', 0.0):.2f}% versus legacy "
        f"{legacy.get('return_pct', 0.0):+.2f}% / {legacy.get('max_drawdown_pct', 0.0):.2f}%. "
        "The current gate is more defensive but not a superior growth policy over this proxy.",
        f"- Strict all-executable period: current {current_live.get('return_pct', 0.0):+.2f}% / alpha "
        f"{current_live.get('alpha_market_pp', 0.0):+.2f}pp versus legacy "
        f"{legacy_live.get('return_pct', 0.0):+.2f}% / {legacy_live.get('alpha_market_pp', 0.0):+.2f}pp. "
        "The defensive gate is better in the recent weak regime.",
        f"- Uncertainty-as-PROVISIONAL is rejected despite its six-month gain: strict executable return "
        f"{balanced_live.get('return_pct', 0.0):+.2f}% and alpha "
        f"{balanced_live.get('alpha_market_pp', 0.0):+.2f}pp.",
        f"- Recent-majority reactivation improves the strict executable period to "
        f"{recent_live.get('return_pct', 0.0):+.2f}% but loses six-month return, deployed efficiency, "
        "and drawdown versus current. It does not dominate and remains research-only.",
        "- No tested candidate dominates current on both horizons; production mode authority is unchanged.",
        "",
        "## Sudden-Decay Semantics",
        "",
        "- Old wins outside the latest five trading sessions cannot keep an ACTIVE mode from cooling.",
        "- Cooling requires at least three recent mode days and five signals; either pool or market weighted mean <= 0 reduces the mode to PROVISIONAL (one pick).",
        "- Because the label exits at D+1 close, a D loss is first actionable on D+2 morning. This two-session observation lag is unavoidable without introducing an earlier proxy label.",
        "- The problem is only partially solved: a large winner still inside the five-day window can mask several losses, and a sparse mode with fewer than five signals is not cooled by the hard rule. Robust median/sparse alternatives were tested but did not improve both horizons.",
    ])
    lines.extend(["", "## Cooling Audit", ""])
    for row in variants:
        events = row["cooling_events"]
        if not events:
            continue
        lines.append(f"### {row['name']} ({len(events)} mode-days)")
        lines.append("")
        lines.append("| date | mode | state | reason |")
        lines.append("|---|---|---|---|")
        for event in events[:40]:
            lines.append(
                f"| {event['date']} | {event['mode']} | {event['state']} | {event['reason']} |"
            )
        lines.append("")
    lines.extend([
        "## Interpretation Guard",
        "",
        "- Prefer a policy only if improvement is not concentrated in one month and drawdown, deployed efficiency, and market alpha also improve.",
        "- A six-month proxy winner is rejected when it fails the strict executable cross-check; theoretical breadth cannot overrule current fill-aware evidence.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    frame = _load_panel(args.panel)
    client = _client()
    market = _market_map(client, frame["date"].unique().tolist())
    missing_market = sorted(set(frame["date"]) - set(market))
    if missing_market:
        raise SystemExit(f"four-index benchmark missing {len(missing_market)} days: {missing_market[:5]}")
    evidence = _evidence(frame, market)
    trade_days = list_trade_days(client, min(frame["date"]), max(args.end, "2026-07-13"))
    if not trade_days:
        raise SystemExit("trade calendar unavailable")

    current_decider = ms.decide_mode
    variants = [
        simulate(
            name="pipe_k50_p_top3_baseline",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=None,
        ),
        simulate(
            name="legacy_equal_pool_gate",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=legacy_decide_mode,
        ),
        simulate(
            name="current_weighted_dual_mean_cooling",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=current_decider,
        ),
        simulate(
            name="robust_tail_and_sparse_cooling_candidate",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=robust_decide_mode,
        ),
        simulate(
            name="balanced_uncertainty_provisional_candidate",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=balanced_decide_mode,
        ),
        simulate(
            name="recent_dual_majority_provisional_candidate",
            frame=frame,
            evidence=evidence,
            market=market,
            trade_days=trade_days,
            start=args.start,
            end=args.end,
            decider=recent_confirmed_decide_mode,
        ),
    ]
    result = {
        "start": args.start,
        "end": args.end,
        "evidence_start": min(frame["date"]),
        "panel_rows": len(frame),
        "evidence_rows": len(evidence),
        "market_days": len(market),
        "variants": variants,
        "strict_live_comparison": strict_live_comparison(
            trade_days=trade_days,
            current_decider=current_decider,
        ),
    }
    suffix = f"{args.start}_{args.end}"
    output = args.output or ROOT / "output" / "research" / f"mode_switch_proxy_6mo_{suffix}.md"
    json_output = args.json_output or ROOT / "output" / "research" / f"mode_switch_proxy_6mo_{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(result), encoding="utf-8")
    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(markdown(result))
    print(f"wrote {output}")
    print(f"wrote {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
