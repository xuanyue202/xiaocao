"""Discipline guards for the 趋势 (long-hold) book — the RIGHT instrument.

The short-line guards (research/guards.py) judge a per-DAY paired-t over many
short trades. A trend book is the opposite physics: few entries, multi-week
non-overlapping holds, position-level path dependence. Forcing it through the
per-day guards either fails it (enough_days, n<2→p=1.0) or launders a lucky 8-day
window as PASS. So the unit of evidence here is the HOLD (one non-overlapping
rebalance period), and the questions are the ones that matter for 长期主义:

  - did capital COMPOUND, and what was the MAX DRAWDOWN?
  - alpha vs BETA: does the trend basket beat the average-theme benchmark?
  - TURNOVER (reported; 10-20d churn destroyed the edge in XH-018)
  - WALK-FORWARD: is the compounded alpha positive in BOTH halves, test retaining?
  - SIGNIFICANCE: paired-t on per-HOLD (not per-day) alpha, Bonferroni-corrected
  - SURVIVES NON-BULL: is the alpha still ≥0 on holds entered in bear/divergence/
    neutral regimes? XH-018 was ONE bull sample — fail-closed if we can't check.

Same non-negotiables as guards.py: cache_only, multiple-comparison correction,
no auto-tune (a PASS is a candidate for the §10 human gate, never an auto-apply).
Dependency-free: reuses guards.py's Student-t.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from xiaocao.research.guards import _mean, _std, student_t_two_sided_p

NON_BULL = {"bear", "divergence", "neutral", "recovery"}


def _compounded(rets_pct: Sequence[float]) -> float:
    c = 1.0
    for r in rets_pct:
        c *= 1.0 + r / 100.0
    return (c - 1.0) * 100.0


def _max_drawdown(rets_pct: Sequence[float]) -> float:
    """Max peak-to-trough drawdown (percent, ≥0) of the compounded equity curve."""
    equity = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets_pct:
        equity *= 1.0 + r / 100.0
        peak = max(peak, equity)
        mdd = max(mdd, (peak - equity) / peak)
    return mdd * 100.0


def _paired_t(diffs: Sequence[float]) -> dict[str, float]:
    n = len(diffs)
    if n < 2:
        return {"t": 0.0, "p": 1.0, "n": n, "df": max(0, n - 1)}
    sd = _std(diffs, ddof=1)
    m = _mean(diffs)
    if sd <= 1e-12:
        return {"t": 0.0, "p": 1.0, "n": n, "df": n - 1}
    t = m / (sd / (n ** 0.5))
    return {"t": t, "p": student_t_two_sided_p(t, n - 1), "n": n, "df": n - 1}


def evaluate_trend(
    holds: Sequence[Mapping[str, Any]],
    *,
    n_tried: int = 1,
    cache_only: bool = True,
    alpha: float = 0.05,
    min_holds: int = 8,
    min_alpha: float = 0.0,        # compounded-alpha floor (percentage points)
    retain_ratio: float = 0.5,
    max_turnover: float = 0.95,    # only catches near-total churn; turnover is mainly reported
    min_nonbull_holds: int = 3,    # fewer than this => can't verify non-bull => fail-closed
) -> dict[str, Any]:
    """Judge a list of non-overlapping holds. Each hold is a mapping with:
        {"entry": date, "strat_ret": pct, "base_ret": pct,
         "regime": label (optional), "turnover": frac (optional)}
    strat_ret = the trend basket's return over the hold; base_ret = the benchmark
    (avg-theme / beta) over the same hold. PASS only if every guard passes.
    """
    if int(n_tried) < 1:
        raise ValueError(f"n_tried must be >= 1, got {n_tried}")

    ordered = sorted(holds, key=lambda h: str(h.get("entry", "")))
    strat = [float(h["strat_ret"]) for h in ordered]
    base = [float(h["base_ret"]) for h in ordered]
    diffs = [s - b for s, b in zip(strat, base)]
    n = len(ordered)

    strat_comp = _compounded(strat)
    base_comp = _compounded(base)
    alpha_comp = strat_comp - base_comp
    mdd = _max_drawdown(strat)
    turnovers = [float(h["turnover"]) for h in ordered if h.get("turnover") is not None]
    turnover = _mean(turnovers) if turnovers else 0.0

    # walk-forward on compounded ALPHA (train first half / test second half)
    mid = n // 2
    tr, te = diffs[:mid], diffs[mid:]
    train_alpha = _compounded([s for s in strat[:mid]]) - _compounded(base[:mid]) if mid else 0.0
    test_alpha = _compounded(strat[mid:]) - _compounded(base[mid:]) if n - mid else 0.0
    wf_consistent = (
        train_alpha > min_alpha and test_alpha > min_alpha
        and test_alpha >= retain_ratio * train_alpha
    )

    sig = _paired_t(diffs)
    effective_alpha = alpha / int(n_tried)

    # regime-conditional: does alpha survive OUT of trend (the non-bull proxy)?
    nb = [d for d, h in zip(diffs, ordered) if str(h.get("regime", "")).lower() in NON_BULL]
    nonbull_alpha_mean = _mean(nb) if nb else 0.0
    nonbull_known = len(nb) >= min_nonbull_holds
    survives_nonbull = nonbull_known and nonbull_alpha_mean >= min_alpha

    win = _mean([1.0 if d > 0 else 0.0 for d in diffs]) if diffs else 0.0

    guards = {
        "cache_only": bool(cache_only),
        "enough_holds": n >= min_holds,
        "compounded_alpha_positive": alpha_comp > min_alpha,
        "per_hold_alpha_positive": _mean(diffs) > min_alpha,
        "walk_forward_consistent": bool(wf_consistent),
        "significant": (sig["p"] < effective_alpha) and (sig["t"] > 0),
        "turnover_ok": turnover <= max_turnover,
        "survives_non_bull": bool(survives_nonbull),
    }
    rejected_by = [k for k, ok in guards.items() if not ok]

    warnings: list[str] = []
    if not nonbull_known:
        warnings.append(
            f"only {len(nb)} non-bull holds (<{min_nonbull_holds}) — cannot verify the alpha "
            f"survives outside a bull regime; fail-closed (survives_non_bull=False)")
    if turnover > 0.7:
        warnings.append(f"turnover {turnover:.0%} is high — XH-018 found churn erodes the edge")
    if int(n_tried) > 1:
        warnings.append(f"multiple comparison: {n_tried} tried -> eff alpha {effective_alpha:.4f} "
                        f"(raw p={sig['p']:.4f})")

    return {
        "n_holds": n,
        "compounded": {"strat": strat_comp, "base": base_comp, "alpha": alpha_comp},
        "max_drawdown": mdd,
        "turnover": turnover,
        "per_hold": {"alpha_mean": _mean(diffs), "win": win, "n": n},
        "walk_forward": {"train_alpha": train_alpha, "test_alpha": test_alpha,
                         "retain_ratio": retain_ratio, "consistent": wf_consistent},
        "significance": {**sig, "alpha": alpha, "effective_alpha": effective_alpha},
        "non_bull": {"n_holds": len(nb), "alpha_mean": nonbull_alpha_mean, "known": nonbull_known},
        "guards": guards,
        "verdict": "PASS" if not rejected_by else "REJECTED",
        "rejected_by": rejected_by,
        "warnings": warnings,
    }
