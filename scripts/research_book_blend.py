"""道→两体系→汇合, step 3: does BLENDING the two books beat either alone (Sharpe)?

The case for running two books is NOT that trend has selection alpha (Phase 1
showed it doesn't). It is DIVERSIFICATION: two imperfectly-correlated, positive-
drift books, blended at equal risk, have a higher Sharpe than either alone iff
their correlation ρ < 1. That is the only risk-adjusted reason 交易汇合 is worth
building — and it is scale-free measurable (correlation is scale-invariant), so it
sidesteps the units mismatch between a fast per-trade book and a slow MTM book.

Method (scale-free, so the books' different return magnitudes don't matter):
  - short-line daily series: mean trade return_pct per regime-known day
  - trend daily series: hold top-M trend concepts (rebalance R), daily mark-to-
    market = mean daily return of held concepts
  - standardize each to unit vol; equal-RISK blend = 0.5(z_short + z_trend)
  - Sharpe(blend) = (s_short + s_trend) / sqrt(2(1+ρ)); blend beats each iff ρ < 1
  - report on FULL sample AND each half (OOS stability of ρ and the Sharpes)

Honest caveats printed: short-line daily is per-trade-attributed (not a clean
1-day return); the trend daily series is autocorrelated (R-day holds) so its
effective independent n is far below the day count. Cache-only.
Usage: python3 scripts/research_book_blend.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.strategy import mainline_signal as ms  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
def _std(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
def _sharpe(xs):
    s = _std(xs)
    return (_mean(xs) / s) if s > 1e-12 else 0.0
def _corr(a, b):
    n = len(a)
    if n < 2:
        return 0.0
    ma, mb = _mean(a), _mean(b)
    sa, sb = _std(a), _std(b)
    if sa <= 1e-12 or sb <= 1e-12:
        return 0.0
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
    return cov / (sa * sb)


def regime_known():
    cnt = defaultdict(int)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate") and k.get("code"):
                    cnt[k["tradeDate"]] += 1
    return {d for d, c in cnt.items() if c >= 30}


def shortline_daily():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, return_pct FROM mode_history WHERE mode NOT LIKE '/stock/%'").fetchall()
    finally:
        con.close()
    by = defaultdict(list)
    for d, r in rows:
        by[d].append(float(r))
    return {d: _mean(v) for d, v in by.items()}


def trend_daily(*, L=60, R=20, M=3):
    panel = ms.load_concept_panel(DB)
    days, ret = panel["days"], panel["ret"]
    out: dict[str, float] = {}
    held: list[str] = []
    next_rebal = L
    for i in range(L, len(days)):
        if i >= next_rebal:
            held = ms.select_by_trend_strength(panel, i, L=L, M=M)
            next_rebal = i + R
        if not held:
            continue
        rs = [ret.get(days[i], {}).get(c) for c in held]
        rs = [x for x in rs if x is not None]
        if rs:
            out[days[i]] = _mean(rs)
    return out


def blend_stats(s_series, t_series):
    """s_series, t_series: dicts day->return. Aligned, standardized, equal-risk blend."""
    days = sorted(set(s_series) & set(t_series))
    s = [s_series[d] for d in days]
    t = [t_series[d] for d in days]
    ss, ts = _std(s), _std(t)
    if ss <= 1e-12 or ts <= 1e-12:
        return None
    zs = [x / ss for x in s]
    zt = [x / ts for x in t]
    blend = [0.5 * (a + b) for a, b in zip(zs, zt)]
    rho = _corr(s, t)
    return {
        "n": len(days), "rho": rho,
        "sharpe_short": _sharpe(s), "sharpe_trend": _sharpe(t),
        "sharpe_blend": _sharpe(blend),
        "best_single": max(_sharpe(s), _sharpe(t)),
        "days": days,
    }


def main():
    known = regime_known()
    s_all = shortline_daily()
    s_series = {d: v for d, v in s_all.items() if d in known}
    t_series = trend_daily()
    full = blend_stats(s_series, t_series)
    if not full:
        print("insufficient data")
        return
    days = full["days"]
    mid = len(days) // 2
    h1 = blend_stats({d: s_series[d] for d in days[:mid]}, {d: t_series[d] for d in days[:mid]})
    h2 = blend_stats({d: s_series[d] for d in days[mid:]}, {d: t_series[d] for d in days[mid:]})

    print(f"aligned daily obs: {full['n']} ({days[0]}..{days[-1]})")
    print("scale-free diversification test: blend (equal-risk) Sharpe vs best single book\n")
    print(f"{'window':<14} {'n':>4} {'ρ(corr)':>8} {'Sharpe short':>12} {'Sharpe trend':>12} "
          f"{'Sharpe blend':>12} {'blend>best?':>11}")
    print("-" * 78)
    for name, st in [("full", full), ("half-1", h1), ("half-2", h2)]:
        if not st:
            continue
        better = st["sharpe_blend"] > st["best_single"] + 1e-9
        print(f"{name:<14} {st['n']:>4} {st['rho']:>+8.3f} {st['sharpe_short']:>+12.3f} "
              f"{st['sharpe_trend']:>+12.3f} {st['sharpe_blend']:>+12.3f} {('YES' if better else 'no'):>11}")
    print()
    print(f"diversification gain (full): blend Sharpe {full['sharpe_blend']:+.3f} vs best single "
          f"{full['best_single']:+.3f}  =>  {'+' if full['sharpe_blend']>full['best_single'] else ''}"
          f"{(full['sharpe_blend']-full['best_single']):+.3f}")
    print("\ncaveats: short-line daily is per-trade-attributed (not a clean 1-day return); "
          "trend daily is autocorrelated (R-day holds) so effective independent n << day count. "
          "ρ and the Sharpe ORDERING are robust to the first; the second inflates significance — "
          "treat the blend gain as INDICATIVE, and require ρ stable across both halves before trusting it.")


if __name__ == "__main__":
    main()
