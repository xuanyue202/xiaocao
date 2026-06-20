"""Executable validation guardrails (the discipline engine).

Input: a list of per-trade results, each a mapping with:
    {"day": "YYYY-MM-DD", "strat_ret": float, "base_ret": float}
where strat_ret is the hypothesis's realized return on that trade and base_ret
is the take-all / validated baseline's return on the same trade. Returns are in
the same unit (e.g. percent or fraction).

Guards (all must pass for a PASS verdict), grounded in kronos_screen/STATE.md and
hardened by an adversarial audit (2026-06):
  - cache_only                  : research must read cache, never the live API.
  - enough_days                 : the effective sample is the number of trading
                                  DAYS (not rows); too few days = high-variance.
  - survives_per_trade_equal_weight : the per-trade equal-weight spread must beat
                                  a configurable economic floor (default >0). This
                                  is the anti-"真的谎言" core — the +254% cum was a
                                  day-weighting artifact; the honest number was
                                  +0.098%/trade.
  - walk_forward_consistent     : split days into train (first half) / test
                                  (second half); the edge must be positive in
                                  BOTH AND the test half must RETAIN a meaningful
                                  fraction of the train edge (not merely share its
                                  sign) — "train+test both *improve*", not "both
                                  happen to be positive".
  - significant                 : a proper paired Student-t test (df = n_days-1,
                                  NOT a normal approximation) on the per-DAY edge,
                                  two-sided p (conservative) AND t>0 (directional),
                                  with a Bonferroni multiple-comparison correction.
                                  A zero-variance / degenerate edge is treated as
                                  NOT significant (insufficient information), never
                                  as maximally significant.

No third-party dependency: the Student-t CDF is computed from the regularized
incomplete beta function (Numerical-Recipes continued fraction), so this module
runs anywhere the core CLI runs.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

EPS = 1e-12


# --------------------------------------------------------------------------- #
# Student-t distribution, dependency-free (regularized incomplete beta).
# --------------------------------------------------------------------------- #
def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, TINY, STOP = 300, 1e-300, 1e-12
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < STOP:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: int) -> float:
    """P(|T| > |t|) for T ~ Student-t(df). The honest small-sample p-value
    (replaces the too-lax normal approximation)."""
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    return _betai(df / 2.0, 0.5, x)


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
        "strat_cum": math.prod(1.0 + r for r in day_strat) - 1.0 if day_strat else 0.0,
        "base_cum": math.prod(1.0 + r for r in day_base) - 1.0 if day_base else 0.0,
    }


def walk_forward(trades: Sequence[Mapping[str, Any]], *, retain_ratio: float = 0.5) -> dict[str, Any]:
    """Train = first half of days, test = second half. The edge must be positive
    in BOTH halves AND the test half must retain at least `retain_ratio` of the
    train edge — guarding against severe out-of-sample decay (sign-only is not
    enough). For an odd day count the extra day goes to TEST (more conservative)."""
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
    consistent = (
        train_edge > 0
        and test_edge > 0
        and test_edge >= retain_ratio * train_edge
    )
    return {
        "train_days": len(train_days),
        "test_days": len(test_days),
        "train_edge": train_edge,
        "test_edge": test_edge,
        "retain_ratio": retain_ratio,
        "consistent": consistent,
    }


def paired_ttest_by_day(trades: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Paired Student-t test on the per-DAY edge (the effective sample is days).
    A degenerate zero-variance edge is reported as NOT significant (p=1.0): a
    perfectly constant edge across a handful of days carries no statistical
    evidence of generalization and must never auto-pass."""
    by_day = _by_day(trades)
    diffs = [_mean([s for s, _ in v]) - _mean([b for _, b in v]) for v in by_day.values()]
    n = len(diffs)
    if n < 2:
        return {"t": 0.0, "p": 1.0, "n_days": n, "df": max(0, n - 1)}
    sd = _std(diffs, ddof=1)
    m = _mean(diffs)
    if sd <= EPS:
        # zero variance => no information about generalization; fail-closed.
        return {"t": 0.0, "p": 1.0, "n_days": n, "df": n - 1}
    t = m / (sd / math.sqrt(n))
    return {"t": t, "p": student_t_two_sided_p(t, n - 1), "n_days": n, "df": n - 1}


def evaluate_hypothesis(
    trades: Sequence[Mapping[str, Any]],
    *,
    n_tried: int = 1,
    cache_only: bool = True,
    alpha: float = 0.05,
    min_days: int = 8,
    min_effect: float = 0.0,
    retain_ratio: float = 0.5,
) -> dict[str, Any]:
    """Run every guard; PASS only if all pass. Returns a structured verdict.

    n_tried (Bonferroni divisor) MUST be >= 1; callers should pass the honest
    count of hypotheses tried in the research program (continuous_optimize derives
    a floor from the ledger). min_effect is an optional economic-significance floor
    on the per-trade spread.
    """
    if int(n_tried) < 1:
        raise ValueError(f"n_tried must be >= 1, got {n_tried}")

    pt = per_trade_stats(trades)
    dw = day_weighted_stats(trades)
    wf = walk_forward(trades, retain_ratio=retain_ratio)
    sig = paired_ttest_by_day(trades)

    n_days = int(dw["n_days"])
    effective_alpha = alpha / int(n_tried)  # Bonferroni
    guards = {
        "cache_only": bool(cache_only),
        "enough_days": n_days >= min_days,
        # economic floor (default >0); directional by construction.
        "survives_per_trade_equal_weight": pt["spread"] > min_effect,
        "walk_forward_consistent": bool(wf["consistent"]),
        # conservative: two-sided p under alpha AND positive direction.
        "significant": (sig["p"] < effective_alpha) and (sig["t"] > 0),
    }
    rejected_by = [k for k, ok in guards.items() if not ok]

    warnings: list[str] = []
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
