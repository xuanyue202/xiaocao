"""道→两体系→汇合: the cross-cycle trend test (un-shelving XH-018/XH-020).

Now that the concept panel is backfilled to ~2023 (incl. the Jan-Feb 2024
small-cap crash and 2023 weakness), the trend book can be tested ACROSS CYCLES
with the same machinery — enough independent holds to satisfy enough_holds, and a
real down-market to test survives-non-bull.

Self-contained (no date_kline breadth needed for 2023-24): the market regime at
each hold's entry is derived from the CONCEPT PANEL — the trailing-W equal-weight
average concept return (the avg-theme momentum). Mapped onto trend_guards' labels:
  trailing-W avg < -3% -> bear ; < 0 -> divergence ; > +3% -> trend_strong ; else neutral
(bear/divergence/neutral are in trend_guards.NON_BULL, so the non-bull check bites.)

Reports the full trend_guards verdict AND a per-year strat-vs-base breakdown so the
crash year is visible. Cache-only. Usage: python3 scripts/research_trend_crosscycle.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import trend_guards  # noqa: E402
from xiaocao.strategy import mainline_signal as ms  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0


def market_state(panel, i, W=20):
    """Trailing-W equal-weight avg concept return at day i -> regime label."""
    days = panel["days"]
    vals = [ms.cum_return(panel["ret"], days, c, i - W, i) for c in panel["num"].get(days[i], {})]
    vals = [v for v in vals if v is not None]
    if not vals:
        return "neutral", None
    m = _mean(vals)
    if m < -3.0:
        return "bear", m
    if m < 0.0:
        return "divergence", m
    if m > 3.0:
        return "trend_strong", m
    return "neutral", m


def build_holds(panel, *, L=60, R=60, M=3, W=20):
    days = panel["days"]
    holds = []
    i = max(L, W)
    while i < len(days) - R:
        picks = ms.select_by_trend_strength(panel, i, L=L, M=M)
        sf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in picks]
        sf = [x for x in sf if x is not None]
        allf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in panel["num"][days[i]]]
        allf = [x for x in allf if x is not None]
        if sf and len(allf) >= 10:
            reg, _ = market_state(panel, i, W)
            holds.append({"entry": days[i], "strat_ret": _mean(sf), "base_ret": _mean(allf),
                          "regime": reg})
        i += R
    return holds


def _real_return_panel(panel):
    """Drop days whose concept returns are all 0 — block_category_rank serves
    historical RANKINGS but prePctChangeRate is 0 before ~2024-05-13 (API gotcha).
    Building holds over zero-return days is invalid (it diluted the first verdict)."""
    ret = panel["ret"]
    good = [d for d in panel["days"] if any(v != 0 for v in ret.get(d, {}).values())]
    return {"num": {d: panel["num"][d] for d in good if d in panel["num"]},
            "ret": {d: ret[d] for d in good if d in ret},
            "name": panel["name"], "days": good}


def main():
    panel = _real_return_panel(ms.load_concept_panel(DB))
    days = panel["days"]
    print(f"concept panel (REAL-return days only): {len(days)} days  {days[0]}..{days[-1]}")

    # regime distribution across the panel (sanity: is there a real down-market?)
    dist = defaultdict(int)
    for i in range(20, len(days)):
        dist[market_state(panel, i, 20)[0]] += 1
    print("regime-day distribution:", dict(dist))

    for R in (40, 60):
        holds = build_holds(panel, L=60, R=R, M=3, W=20)
        v = trend_guards.evaluate_trend(holds, n_tried=2, cache_only=True)
        c, wf, nb = v["compounded"], v["walk_forward"], v["non_bull"]
        print(f"\n=== trend-strength L60/R{R}/M3 ===  holds={v['n_holds']}")
        print(f"  compounded: strat {c['strat']:+.1f}%  base {c['base']:+.1f}%  alpha {c['alpha']:+.1f}pp"
              f"   max_dd {v['max_drawdown']:.1f}%")
        print(f"  per-hold alpha {v['per_hold']['alpha_mean']:+.2f}%  win {v['per_hold']['win']:.0%}"
              f"  t={v['significance']['t']:+.2f} p={v['significance']['p']:.3f}")
        print(f"  walk-forward train {wf['train_alpha']:+.1f} / test {wf['test_alpha']:+.1f}pp")
        print(f"  non-bull: n={nb['n_holds']} alpha {nb['alpha_mean']:+.2f}% (known={nb['known']})")
        mark = "✅PASS" if v["verdict"] == "PASS" else "❌REJECTED (" + ",".join(v["rejected_by"]) + ")"
        print(f"  verdict: {mark}")
        for w in v["warnings"]:
            print(f"    ⚠ {w}")
        # per-year breakdown
        by_year = defaultdict(lambda: [[], []])
        for h in holds:
            y = h["entry"][:4]
            by_year[y][0].append(h["strat_ret"])
            by_year[y][1].append(h["base_ret"])
        print("  by year (strat vs base, per-hold mean):")
        for y in sorted(by_year):
            s, b = by_year[y]
            print(f"    {y}: strat {_mean(s):+6.2f}%  base {_mean(b):+6.2f}%  "
                  f"alpha {_mean(s)-_mean(b):+6.2f}pp  (n={len(s)})")


if __name__ == "__main__":
    main()
