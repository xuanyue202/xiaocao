"""Adaptive mode gating based on rolling N-day per-mode performance.

Reads per-trade outcomes from `SQLiteCache.mode_history` and decides whether
each mode is currently *active* (counts toward the user's actual P&L) or
*shadow* (signal still emitted, scored, and recorded — just not for real
trading).

This is the critical design point: adaptive does NOT drop signals. Shadow
signals are fully simulated so mode_history accumulates outcomes for both
active and shadow trades. That means:

- No chicken-egg cold-start: even with empty cache, all candidate signals
  fire on day 1, all outcomes get recorded, adaptive's rolling windows are
  populated for subsequent days.
- Adaptive's rolling windows always reflect the *true* performance of each
  mode, not just the modes adaptive happened to allow through.
- The user's actual returns come from the `active` subset; `shadow` is
  reference / diagnostic.

Per-window thresholds (default — calibrated from t-stat ≈ -10/√n with a -2%
floor for transaction cost):

   window  n_min  bad if avg ≤
     5d      1      -5%   ← short, single-point recency probe needs strong signal
    10d      2      -3%   ← short-mid term, needs persistence
    20d      3      -2%   ← mid-term baseline, must beat trading friction

Decision rule (tiered fallback — windows count in trading days when a
trade_days list is supplied):

  Tier 1: 5d AND 10d both informative
          → BOTH 5d.avg ≤ -5% AND 10d.avg ≤ -3% → SHADOW (dual confirmation)

  Tier 2: only 5d or only 10d informative
          → that window's avg ≤ its threshold → SHADOW

  Tier 3: 5d/10d both uninformative, 20d informative
          → 20d.avg ≤ -2% → SHADOW

  Tier 4: 20d also uninformative (mode dormant)
          → SHADOW — no evidence to bet on, but signal still recorded

(Why no 30-day window: 30 trading days ≈ 6 weeks; market regime typically
shifts within that window.)

Pure logic — the only side effect is reading from the supplied cache.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

DEFAULT_WINDOWS: tuple[int, ...] = (5, 10, 20)
# Per-window n_min: short windows are recency probes (n=1 acceptable), long
# windows are statistical baselines (need ≥3). One-size-fits-all (3/3/3) made
# adaptive permanently dormant for sparse modes.
DEFAULT_N_MIN_BY_WINDOW: dict[int, int] = {5: 1, 10: 2, 20: 3}

# Per-window avg threshold: smaller n requires a STRONGER negative signal to
# justify shadow (compensates for high standard error). Floor at ~-2% covers
# transaction cost + slippage + opportunity cost — anything closer to 0 has no
# real investment meaning. Calibrated to roughly -10/sqrt(n) (t-stat target),
# bounded by the -2% floor.
DEFAULT_AVG_THRESHOLD_BY_WINDOW: dict[int, float] = {5: -5.0, 10: -3.0, 20: -2.0}

AUXILIARY_MODE_AUTHORITY = "shadow_ranking_only"


def regime_modulated_thresholds(
    base: dict[int, float] | None,
    fitness: float | int,
) -> dict[int, float]:
    """Return unchanged return-evidence thresholds.

    `fitness` is retained for API compatibility and shadow telemetry. The
    2026-07-10 gray-zone OOS checks rejected auxiliary mode confirmation, so an
    environment-fit score has no authority to relax or tighten qualification.
    A future modulation rule needs its own research PASS and human promotion.
    """
    del fitness
    thresholds = base if base is not None else DEFAULT_AVG_THRESHOLD_BY_WINDOW
    return dict(thresholds)


@dataclass(frozen=True)
class ModeDecision:
    """`active`: signal counts toward real P&L (`True`) vs shadow-only (`False`).

    Shadow signals are still emitted, scored against next-day kline, and
    recorded into mode_history — they just don't contribute to the strategy's
    "actual" returns.
    """
    mode: str
    active: bool
    reason: str
    windows: dict[int, dict[str, Any]]  # window_days -> {"n": int, "avg": float}

    # Backwards-compat shim: some old code/tests read .enabled. Remove once
    # callers migrate.
    @property
    def enabled(self) -> bool:
        return self.active


def decide_mode_state(
    mode: str,
    asof_iso: str,
    cache: Any,
    *,
    windows: Sequence[int] = DEFAULT_WINDOWS,
    n_min_by_window: dict[int, int] | None = None,
    avg_threshold_by_window: dict[int, float] | None = None,
    trade_days: list[str] | None = None,
    regime_fitness: float | int = 0,
) -> ModeDecision:
    """Return a decision for whether `mode` should be allowed on `asof_iso`.

    Per-window n_min and avg_threshold (default: 5d/10d/20d → 1/2/3 minimum
    samples; ≤ -5%/-3%/-2% to mark shadow). Smaller windows require stronger
    negative signals (effect-size compensates for high standard error); the
    -2% floor in 20d covers transaction cost so "near 0" never disables.

    When `trade_days` is provided, windows are counted in trading days; when
    None they fall back to calendar days.
    """
    if cache is None or not hasattr(cache, "mode_window_stats"):
        return ModeDecision(mode, True, "no cache available", {})

    n_min_map = n_min_by_window if n_min_by_window is not None else DEFAULT_N_MIN_BY_WINDOW
    thr_map_base = avg_threshold_by_window if avg_threshold_by_window is not None else DEFAULT_AVG_THRESHOLD_BY_WINDOW
    # `regime_fitness` is compatibility-only. Auxiliary state is observable but
    # cannot change mode qualification without a separately promoted OOS PASS.
    thr_map = regime_modulated_thresholds(thr_map_base, regime_fitness)

    win_stats: dict[int, dict[str, Any]] = {}
    for w in windows:
        win_stats[w] = cache.mode_window_stats(mode, asof_iso, w, trade_days=trade_days)
    s5 = win_stats.get(5, {"n": 0, "avg": 0.0})
    s10 = win_stats.get(10, {"n": 0, "avg": 0.0})
    s20 = win_stats.get(20, {"n": 0, "avg": 0.0})

    n5_min = n_min_map.get(5, 1)
    n10_min = n_min_map.get(10, 2)
    n20_min = n_min_map.get(20, 3)
    thr5 = thr_map.get(5, -5.0)
    thr10 = thr_map.get(10, -3.0)
    thr20 = thr_map.get(20, -2.0)

    inf5 = s5["n"] >= n5_min
    inf10 = s10["n"] >= n10_min
    inf20 = s20["n"] >= n20_min

    # Tier 1: dual confirmation (5d + 10d both have evidence per their bars)
    if inf5 and inf10:
        if s5["avg"] <= thr5 and s10["avg"] <= thr10:
            return ModeDecision(
                mode, False,
                f"Tier1 双窗口确认: 5d avg={s5['avg']:+.2f}%≤{thr5:.0f}% AND 10d avg={s10['avg']:+.2f}%≤{thr10:.0f}% (n={s5['n']}/{s10['n']})",
                win_stats,
            )
        return ModeDecision(
            mode, True,
            f"Tier1 双窗口未一致: 5d avg={s5['avg']:+.2f}% / 10d avg={s10['avg']:+.2f}% (阈值 {thr5:.0f}%/{thr10:.0f}%)",
            win_stats,
        )

    # Tier 2: single short-window evidence (5d xor 10d)
    if inf5 and not inf10:
        if s5["avg"] <= thr5:
            return ModeDecision(
                mode, False,
                f"Tier2 5d 单窗口保守: avg={s5['avg']:+.2f}%≤{thr5:.0f}% n={s5['n']} (10d n<{n10_min})",
                win_stats,
            )
        return ModeDecision(mode, True, f"Tier2 5d 单窗口正向 (avg={s5['avg']:+.2f}% > {thr5:.0f}%)", win_stats)
    if inf10 and not inf5:
        if s10["avg"] <= thr10:
            return ModeDecision(
                mode, False,
                f"Tier2 10d 单窗口保守: avg={s10['avg']:+.2f}%≤{thr10:.0f}% n={s10['n']} (5d n<{n5_min})",
                win_stats,
            )
        return ModeDecision(mode, True, f"Tier2 10d 单窗口正向 (avg={s10['avg']:+.2f}% > {thr10:.0f}%)", win_stats)

    # Tier 3: 5d/10d empty → fall to 20d
    if inf20:
        if s20["avg"] <= thr20:
            return ModeDecision(
                mode, False,
                f"Tier3 20d 兜底: avg={s20['avg']:+.2f}%≤{thr20:.0f}% n={s20['n']} (5d/10d 数据不足)",
                win_stats,
            )
        return ModeDecision(mode, True, f"Tier3 20d 兜底正向 (avg={s20['avg']:+.2f}% > {thr20:.0f}%)", win_stats)

    # Tier 4: 20d also uninformative — mode dormant, mark SHADOW.
    return ModeDecision(
        mode, False,
        f"Tier4 dormant: 20 个交易日样本不足 (n5={s5['n']}/n10={s10['n']}/n20={s20['n']}, 需 {n5_min}/{n10_min}/{n20_min})",
        win_stats,
    )


def tag_signals(
    rows: list[dict[str, Any]],
    asof_iso: str,
    cache: Any,
    *,
    trade_days: list[str] | None = None,
    regime: str | None = None,
    state: Any | None = None,
    mode_profiles: dict[str, Any] | None = None,
    **decision_kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, ModeDecision]]:
    """Tag every signal row with `adaptive_active` (bool) + `adaptive_reason`.

    Auxiliary fitness lookup priority (shadow telemetry only):
      1. `state` (StateVector): use `mode_fitness(mode, state)` — continuous,
         capturing per-day Reward / Risk / Continuity axes.
      2. `regime` (str): legacy 5-bucket label → integer fitness from
         `mode_regime_fitness`. Used when running live `strategy run` with
         only market_overview-derived label available.
      3. neither → fitness=0.

    Fitness is written to each row for audit/ranking research. It never changes
    `adaptive_active`; only rolling return evidence does.

    Same-mode signals on the same date share one ModeDecision (memoized).

    Crucially, this does NOT drop rows. All candidate signals stay in the
    output; the only change is the new annotation. Downstream layers (the
    backtest scorer + summary) split active vs shadow based on the tag.

    Returns (tagged_rows, decisions_by_mode) — decisions_by_mode covers every
    mode that appeared in `rows`.
    """
    # Lazy-import to avoid circular dependency: regime.py imports nothing here,
    # but adaptive is imported by runner which also imports regime.
    from .regime import PRECONDITION_FAIL, mode_fitness, mode_regime_fitness

    decisions: dict[str, ModeDecision] = {}
    fitness_by_mode: dict[str, float | int] = {}
    tagged: list[dict[str, Any]] = []
    for row in rows:
        mode = row.get("mode") or ""
        if mode and mode not in decisions:
            if state is not None:
                fitness: float | int = mode_fitness(mode, state, profiles=mode_profiles)
            else:
                fitness = mode_regime_fitness(mode, regime)
            fitness_by_mode[mode] = fitness
            decisions[mode] = decide_mode_state(
                mode, asof_iso, cache,
                trade_days=trade_days,
                regime_fitness=fitness,
                **decision_kwargs,
            )
        decision = decisions.get(mode)
        annotated = dict(row)
        if mode:
            fitness = fitness_by_mode.get(mode, 0)
            annotated["adaptive_regime_fitness"] = (
                "PRECONDITION_FAIL" if fitness == PRECONDITION_FAIL else float(fitness)
            )
            annotated["adaptive_auxiliary_authority"] = AUXILIARY_MODE_AUTHORITY
        prev_active = annotated.get("adaptive_active")
        if decision is not None:
            # adaptive_active is sticky-False: once any upstream gate marks a
            # signal shadow, this gate can only ADD context (never re-enable).
            if prev_active is False:
                prev_reason = annotated.get("adaptive_reason") or ""
                annotated["adaptive_reason"] = (
                    f"{prev_reason}; {decision.reason}" if prev_reason else decision.reason
                )
            else:
                annotated["adaptive_active"] = bool(decision.active)
                annotated["adaptive_reason"] = decision.reason
        elif prev_active is None:
            annotated["adaptive_active"] = True
        tagged.append(annotated)
    return tagged, decisions


# Back-compat alias: existing callers used adaptive_mode_filter() which
# dropped rows. The new behavior is tag-only — rows always pass through.
adaptive_mode_filter = tag_signals
