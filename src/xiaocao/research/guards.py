"""Executable validation guardrails (the discipline engine).

Input: a list of per-trade results, each a mapping with:
    {"day": "YYYY-MM-DD", "strat_ret": float, "base_ret": float}
where strat_ret is the hypothesis's realized return on that trade and base_ret
is the take-all / validated baseline's return on the same trade. Returns are in
the same unit (e.g. percent or fraction) — the guards only use signs/means.

Guards (all must pass for a PASS verdict), grounded in kronos_screen/STATE.md:
  - cache_only                  : research must read cache, never the live API.
  - enough_days                 : the effective sample is the number of trading
                                  DAYS (not rows); too few days = high-variance.
  - survives_per_trade_equal_weight : the edge must survive PER-TRADE equal
                                  weighting, not only day-equal weighting. This
                                  is the anti-"真的谎言" core — the +254% cum was
                                  a day-weighting artifact; the honest number was
                                  +0.098%/trade.
  - walk_forward_consistent     : split days into train (first half) / test
                                  (second half); the edge must be positive on
                                  BOTH (train+test both improve).
  - significant                 : paired t-test on the per-DAY edge, with a
                                  Bonferroni multiple-comparison correction for
                                  the number of hypotheses tried.

This module has no third-party dependencies (a normal-approximation p-value via
math.erf) so it can run anywhere the core CLI runs.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

EPS = 1e-12


def _normal_two_sided_p(z: float) -> float:
    # P(|Z| > |z|) for a standard normal — a large-sample approximation to the
    # paired t-test p-value (n = #days is usually >= ~30 here).
    return math.erfc(abs(z) / math.sqrt(2.0))


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float], ddof: int = 1) -> float:
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - ddof))


def _by_day(trades: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for t in trades:
        out[str(t["day"])].append((float(t["strat_ret"]), float(t["base_ret"])))
    return dict(out)


def per_trade_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    strat = [float(t["strat_ret"]) for t in trades]
    base = [float(t["base_ret"]) for t in trades]
    return {
        "n": len(trades),
        "strat_mean": _mean(strat),
        "base_mean": _mean(base),
        "spread": _mean(strat) - _mean(base),
        "win_strat": _mean([1.0 if r > 0 else 0.0 for r in strat]) if strat else 0.0,
        "win_base": _mean([1.0 if r > 0 else 0.0 for r in base]) if base else 0.0,
    }


def day_weighted_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    by_day = _by_day(trades)
    day_strat = [_mean([s for s, _ in v]) for v in by_day.values()]
    day_base = [_mean([b for _, b in v]) for v in by_day.values()]
    return {
        "n_days": len(by_day),
        "strat_day_mean": _mean(day_strat),
        "base_day_mean": _mean(day_base),
        "spread": _mean(day_strat) - _mean(day_base),
        # cumulative product of day-mean returns (the inflating headline). Treats
        # ret as a fraction; for percent inputs this is illustrative only.
        "strat_cum": math.prod(1.0 + r for r in day_strat) - 1.0 if day_strat else 0.0,
        "base_cum": math.prod(1.0 + r for r in day_base) - 1.0 if day_base else 0.0,
    }


def walk_forward(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_day = _by_day(trades)
    days = sorted(by_day)
    mid = len(days) // 2
    train_days, test_days = days[:mid], days[mid:]

    def edge(day_set: list[str]) -> float:
        s = [v for d in day_set for v in by_day[d]]
        if not s:
            return 0.0
        return _mean([a for a, _ in s]) - _mean([b for _, b in s])

    train_edge, test_edge = edge(train_days), edge(test_days)
    return {
        "train_days": len(train_days),
        "test_days": len(test_days),
        "train_edge": train_edge,
        "test_edge": test_edge,
        "consistent": train_edge > 0 and test_edge > 0,
    }


def paired_ttest_by_day(trades: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    by_day = _by_day(trades)
    diffs = [_mean([s for s, _ in v]) - _mean([b for _, b in v]) for v in by_day.values()]
    n = len(diffs)
    if n < 2:
        return {"t": 0.0, "p": 1.0, "n_days": n}
    sd = _std(diffs, ddof=1)
    m = _mean(diffs)
    if sd <= EPS:
        # A perfectly consistent non-zero edge is maximally significant; a flat
        # edge is not. (Cap t finite so the verdict stays JSON-serializable.)
        if abs(m) <= EPS:
            return {"t": 0.0, "p": 1.0, "n_days": n}
        return {"t": 1e9 if m > 0 else -1e9, "p": 0.0, "n_days": n}
    t = m / (sd / math.sqrt(n))
    return {"t": t, "p": _normal_two_sided_p(t), "n_days": n}


def evaluate_hypothesis(
    trades: Sequence[Mapping[str, Any]],
    *,
    n_tried: int = 1,
    cache_only: bool = True,
    alpha: float = 0.05,
    min_days: int = 8,
) -> dict[str, Any]:
    """Run every guard; PASS only if all pass. Returns a structured verdict."""
    pt = per_trade_stats(trades)
    dw = day_weighted_stats(trades)
    wf = walk_forward(trades)
    sig = paired_ttest_by_day(trades)

    n_days = int(dw["n_days"])
    effective_alpha = alpha / max(1, int(n_tried))  # Bonferroni
    guards = {
        "cache_only": bool(cache_only),
        "enough_days": n_days >= min_days,
        "survives_per_trade_equal_weight": pt["spread"] > 0,
        "walk_forward_consistent": bool(wf["consistent"]),
        "significant": sig["p"] < effective_alpha,
    }
    rejected_by = [k for k, ok in guards.items() if not ok]

    warnings: list[str] = []
    # Flag the day-weighting inflation even when the per-trade edge survives.
    if pt["spread"] > EPS and dw["spread"] / pt["spread"] > 2.0:
        warnings.append(
            f"day-weighted spread {dw['spread']:.4f} is "
            f"{dw['spread'] / pt['spread']:.1f}x the per-trade spread {pt['spread']:.4f} "
            f"— report the per-trade number, not the cum/day-weighted headline"
        )
    if int(n_tried) > 1:
        warnings.append(
            f"multiple comparison: {n_tried} hypotheses tried -> effective alpha "
            f"{effective_alpha:.4f} (raw p={sig['p']:.4f})"
        )

    return {
        "n_trades": pt["n"],
        "n_days": n_days,
        "per_trade": pt,
        "day_weighted": dw,
        "walk_forward": wf,
        "significance": {**sig, "alpha": alpha, "effective_alpha": effective_alpha},
        "guards": guards,
        "verdict": "PASS" if not rejected_by else "REJECTED",
        "rejected_by": rejected_by,
        "warnings": warnings,
    }
