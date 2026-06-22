"""道→两体系→汇合: the REAL cross-cycle trend test — STOCK level, 2021-2026.

The concept panel serves no historical RETURNS (prePctChangeRate is 0 before
~2024-05), so it can't test a bear. date_kline DOES serve real prices back to
2021 (incl. the 2022 bear + Jan-Feb 2024 crash). After backfill_bigcap_history,
this runs a big-cap trend/momentum book across cycles and judges it with
trend_guards — finally answering: does trend selection survive bull AND bear?

big-cap trend book (long-hold, low-turnover):
  universe = the fetched big-caps (deep history only)
  pick     = top-M by trailing-L close-to-close momentum
  hold     = non-overlapping R days; strat = mean fwd return of picks
  base     = mean fwd return of the whole big-cap universe (beta)
  regime   = trailing-W mean big-cap return at entry (bear/divergence/neutral/trend_strong)

Cache-only. Usage: python3 scripts/research_trend_stock_crosscycle.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.research import trend_guards  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
MIN_UNIV = 100


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0


def build_panel():
    """Per code, use its DEEPEST date_kline series (the qfq 1300-bar backfill);
    by_date[date][code] = close. Only codes with history before 2023 (cross-cycle)."""
    best: dict[str, list] = {}
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            code = data[0].get("code")
            if code and (code not in best or len(data) > len(best[code])):
                best[code] = data
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for code, bars in best.items():
        ds = [b.get("tradeDate") for b in bars if isinstance(b, dict) and b.get("tradeDate")]
        if not ds or min(ds) >= "2023-01-01":   # need cross-cycle depth
            continue
        for b in bars:
            td, close = b.get("tradeDate"), b.get("close")
            if td and isinstance(close, (int, float)) and close > 0:
                by_date[td][code] = float(close)
    days = sorted(d for d in by_date if len(by_date[d]) >= MIN_UNIV)
    return by_date, days


def ret(by_date, days, code, i, j):
    a = by_date[days[i]].get(code) if 0 <= i < len(days) else None
    b = by_date[days[j]].get(code) if 0 <= j < len(days) else None
    return (b / a - 1.0) * 100.0 if a and b else None


def regime_at(by_date, days, i, W=20):
    rs = [ret(by_date, days, c, i - W, i) for c in by_date[days[i]]]
    rs = [x for x in rs if x is not None]
    if not rs:
        return "neutral"
    m = _mean(rs)
    return "bear" if m < -6 else "divergence" if m < 0 else "trend_strong" if m > 6 else "neutral"


def build_holds(by_date, days, *, L, R, M, W=20):
    holds = []
    i = max(L, W)
    while i < len(days) - R:
        cands = []
        for c in by_date[days[i]]:
            m = ret(by_date, days, c, i - L, i)
            f = ret(by_date, days, c, i, i + R)
            if m is not None and f is not None:
                cands.append((m, f))
        allf = [f for _, f in cands]
        if len(cands) >= M and len(allf) >= 20:
            cands.sort(reverse=True)
            top = cands[:M]
            holds.append({"entry": days[i], "strat_ret": _mean([f for _, f in top]),
                          "base_ret": _mean(allf), "regime": regime_at(by_date, days, i, W)})
        i += R
    return holds


def main():
    by_date, days = build_panel()
    if len(days) < 50:
        print(f"insufficient deep-history universe ({len(days)} days) — backfill still running?")
        return
    print(f"big-cap deep-history panel: {len(days)} days  {days[0]}..{days[-1]}  "
          f"(~{len(by_date[days[-1]])} codes/recent day)")
    dist = defaultdict(int)
    for i in range(20, len(days)):
        dist[regime_at(by_date, days, i)] += 1
    print("regime-day distribution:", dict(dist))

    for L, R, M in [(60, 40, 5), (120, 60, 5), (60, 60, 5)]:
        holds = build_holds(by_date, days, L=L, R=R, M=M)
        v = trend_guards.evaluate_trend(holds, n_tried=3, cache_only=True)
        c, wf, nb = v["compounded"], v["walk_forward"], v["non_bull"]
        print(f"\n=== big-cap momentum L{L}/R{R}/M{M} ===  holds={v['n_holds']}")
        print(f"  compounded strat {c['strat']:+.1f}% base {c['base']:+.1f}% alpha {c['alpha']:+.1f}pp  "
              f"max_dd {v['max_drawdown']:.1f}%")
        print(f"  per-hold alpha {v['per_hold']['alpha_mean']:+.2f}% win {v['per_hold']['win']:.0%} "
              f"t={v['significance']['t']:+.2f} p={v['significance']['p']:.3f}  "
              f"wf train {wf['train_alpha']:+.1f}/test {wf['test_alpha']:+.1f}pp")
        print(f"  non-bull n={nb['n_holds']} alpha {nb['alpha_mean']:+.2f}% (known={nb['known']})")
        print(f"  verdict: {'✅PASS' if v['verdict']=='PASS' else '❌REJECTED ('+','.join(v['rejected_by'])+')'}")
        by_year = defaultdict(lambda: [[], []])
        for h in holds:
            by_year[h["entry"][:4]][0].append(h["strat_ret"])
            by_year[h["entry"][:4]][1].append(h["base_ret"])
        print("  by year (strat/base/alpha per-hold mean):")
        for y in sorted(by_year):
            s, b = by_year[y]
            print(f"    {y}: {_mean(s):+6.2f}% / {_mean(b):+6.2f}% / {_mean(s)-_mean(b):+6.2f}pp (n={len(s)})")


if __name__ == "__main__":
    main()
