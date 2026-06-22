#!/usr/bin/env python3
"""趋势长期主义: compounded return of a LOW-TURNOVER, LONG-HOLD trend book.

User critique (2026-06-22): the earlier REJECTED verdicts judged a CHURNING,
short-horizon (10-20d reselection), relative-to-average-theme strategy with the
SHORT-LINE per-day guards. But trend is a parallel system — you don't trade it
daily, you hold long-term (长期主义). 10-20d is also the momentum-REVERSAL zone;
multi-month is the persistence zone. So this measures the right thing:

  - rules-based, NO hindsight: each rebalance hold the top-M concepts by trailing
    L-day return (the sustained trend), equal-weight
  - LONG holds / slow rebalance (R days), report TURNOVER
  - ABSOLUTE COMPOUNDED return over the full year, vs benchmarks:
      * EW-all-concepts compounded (= "average theme" / beta)
      * the single strongest trend (算力芯片) buy-&-hold (ceiling reference)

NOT judged by the short-line per-day t-guards (wrong instrument for a trend book).
Concept returns = block_category_rank_v3 prePctChangeRate (verified sane: 算力芯片
cumulates +75%/yr). Cache-only.

Usage: python3 scripts/research_trend_longhold.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


def load_concepts():
    ret = defaultdict(dict)
    name = {}
    for pj, data in iter_cached_responses(str(DB), "/stock/xiao_cao_block_category_rank_v3", include_params=True):
        import json
        p = json.loads(pj).get("params", {})
        if p.get("model") != 0 or not isinstance(data, dict):
            continue
        d = p.get("date")
        lst = data.get("localCategoryRankList") or data.get("globalCategoryRankList")
        if isinstance(lst, list):
            for it in lst:
                cc = it.get("categoryCode")
                v = it.get("prePctChangeRate")
                if cc and isinstance(v, (int, float)):
                    ret[d][cc] = float(v)
                    name[cc] = it.get("name")
    days = sorted(d for d in ret if ret[d])
    return ret, name, days


def cum(ret, days, cc, i0, i1):
    """Compounded return (fraction) of concept cc over (days[i0], days[i1]]."""
    c = 1.0
    for j in range(i0 + 1, i1 + 1):
        v = ret[days[j]].get(cc)
        if v is None:
            return None
        c *= 1.0 + v / 100.0
    return c - 1.0


def trailing(ret, days, cc, i, L):
    return cum(ret, days, cc, i - L, i)


def simulate(ret, name, days, L, R, M):
    """Hold top-M by trailing-L, rebalance every R days. Returns (book, bench, turnover%)."""
    book, bench = 1.0, 1.0
    prev = set()
    rebals, changes = 0, 0
    i = L
    while i < len(days) - 1:
        j = min(i + R, len(days) - 1)
        # select top-M by trailing-L momentum among concepts with full history+forward
        cands = []
        for cc in ret[days[i]]:
            t = trailing(ret, days, cc, i, L)
            f = cum(ret, days, cc, i, j)
            if t is not None and f is not None:
                cands.append((t, cc, f))
        if len(cands) < M:
            i = j
            continue
        cands.sort(reverse=True)
        held = cands[:M]
        held_set = {cc for _, cc, _ in held}
        book *= 1.0 + sum(f for _, _, f in held) / M
        # benchmark: EW all concepts with a forward return this window
        allf = [cum(ret, days, cc, i, j) for cc in ret[days[i]]]
        allf = [x for x in allf if x is not None]
        if allf:
            bench *= 1.0 + sum(allf) / len(allf)
        rebals += 1
        changes += len(held_set - prev)
        prev = held_set
        i = j
    turnover = 100.0 * changes / max(1, rebals * M)
    return book - 1.0, bench - 1.0, turnover


def main():
    ret, name, days = load_concepts()
    span_days = len(days)
    yrs = span_days / 244.0
    print(f"concept panel: {span_days} days ({days[0]}..{days[-1]}) ≈ {yrs:.2f}yr, ~{len(ret[days[-1]])} concepts/day")

    # ceiling reference: single strongest trend buy & hold
    best = max(((cum(ret, days, cc, 0, len(days) - 1) or -1, name.get(cc, cc)) for cc in name),
              key=lambda t: t[0])
    print(f"reference — strongest single concept buy&hold ({best[1]}): {best[0]*100:+.1f}% over the year\n")

    print(f"{'L(trend)':>8} {'R(hold)':>8} {'M':>3} {'trend book':>11} {'avg-theme(beta)':>16} "
          f"{'spread':>8} {'turnover':>9}")
    print("-" * 72)
    for L in (20, 40, 60, 120):
        for R in (20, 60, 120):
            for M in (3,):
                if L + R >= len(days):
                    continue
                b, mk, to = simulate(ret, name, days, L, R, M)
                print(f"{L:>8} {R:>8} {M:>3} {b*100:>+10.1f}% {mk*100:>+15.1f}% "
                      f"{(b-mk)*100:>+7.1f}% {to:>8.0f}%")
    print("\nread: 'trend book' = hold top-3 trailing-L-momentum concepts, rebalance every R days,")
    print("compounded over the year. 'avg-theme(beta)' = hold ALL concepts EW, same cadence.")
    print("spread>0 AND low turnover => long-horizon trend-holding has real edge over participation.")


if __name__ == "__main__":
    main()
