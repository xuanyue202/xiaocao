#!/usr/bin/env python3
"""Operationalize 小草's "death week" instinct as a falsifiable filter (refined XH-011).

XH-011 tested a SINGLE-day regime label and was REJECTED (no single regime is
clearly negative-EV for low-suck). 小草's actual call is sharper: not one bad day
but **连续 N 天广度恶化** — entering a tape that has been broadly red for several
straight sessions (连续跌 3000-4000 家 + 高开低走 + 无主线). This script tests the
consecutive-breadth-deterioration component, which XH-011 never isolated.

Cache-only. Breadth per day = positive_ratio over the cached date_kline universe
(~1685 codes/day). A trade day d is a DEATH WINDOW if the N trading days BEFORE d
(all pre-open-knowable, no lookahead) meet a deterioration test:
  - abs(N, tau): every one of the prior N days had positive_ratio < tau
  - mono(N)    : positive_ratio strictly worsened each of the prior N days

Filter-as-strategy framing for the guards (paired per trade):
  base_ret = the low-suck trade's realized return (take-all = current behavior)
  strat_ret = 0 (sit in cash) if the day is a death window, else base_ret
=> spread > 0 iff death windows are net-negative and skipping them helps.

Usage:
  python3 scripts/research_breadth_filter.py            # grid + conditional EV
  python3 scripts/research_breadth_filter.py --emit-primary out.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.research import guards  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
MIN_UNIV = 500  # require a real breadth sample for the day to count

# Pre-registered grid (honest n_tried for Bonferroni = len(GRID)).
# PRIMARY is abs(N=2, tau=0.40): "entering after 2 straight days of >60% decline".
GRID = [
    ("abs", 2, 0.40),  # PRIMARY
    ("abs", 2, 0.35),
    ("abs", 2, 0.45),
    ("abs", 3, 0.40),
    ("abs", 3, 0.35),
    ("abs", 3, 0.45),
    ("mono", 2, None),
    ("mono", 3, None),
]
PRIMARY = GRID[0]


def build_breadth() -> dict[str, dict]:
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td, code, pct = k.get("tradeDate"), k.get("code"), k.get("pctChangeRate")
            if td and code and isinstance(pct, (int, float)):
                by_date[td][code] = float(pct)
    breadth: dict[str, dict] = {}
    for d, codes in by_date.items():
        pcts = list(codes.values())
        n = len(pcts)
        if n < MIN_UNIV:
            continue
        pos = sum(1 for v in pcts if v > 0)
        breadth[d] = {"n": n, "pos_ratio": pos / n, "mean_pct": sum(pcts) / n}
    return breadth


def death_flags(breadth: dict[str, dict], kind: str, N: int, tau):
    """Return {date: bool} death-window flag using only the N PRIOR trading days."""
    days = sorted(breadth)
    pr = [breadth[d]["pos_ratio"] for d in days]
    flag: dict[str, bool] = {}
    for i, d in enumerate(days):
        if i < N:
            flag[d] = False  # not enough history -> never flag (conservative)
            continue
        prior = pr[i - N:i]  # chronological: prior[-1] is yesterday
        if kind == "abs":
            flag[d] = all(x < tau for x in prior)
        else:  # mono: strictly worsening each day
            flag[d] = all(prior[j] < prior[j - 1] for j in range(1, len(prior)))
    return flag, days


def load_trades() -> list[dict]:
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, return_pct FROM mode_history WHERE mode NOT LIKE '/stock/%'"
        ).fetchall()
    finally:
        con.close()
    return [{"day": d, "ret": float(r)} for d, r in rows]


def emit(breadth, flag, days, trades) -> list[dict]:
    """Skip-filter trades (paired) over the breadth-covered, has-N-priors window."""
    covered = set(days)
    out = []
    for t in trades:
        d = t["day"]
        if d not in covered or d not in flag:
            continue
        base = t["ret"]
        strat = 0.0 if flag[d] else base
        out.append({"day": d, "strat_ret": strat, "base_ret": base, "death": flag[d]})
    return out


def conditional_ev(emitted):
    death = [e["base_ret"] for e in emitted if e["death"]]
    live = [e["base_ret"] for e in emitted if not e["death"]]

    def stats(xs):
        if not xs:
            return (0, 0.0, 0.0)
        return (len(xs), sum(xs) / len(xs), sum(1 for x in xs if x > 0) / len(xs))

    dn, dm, dw = stats(death)
    ln, lm, lw = stats(live)
    death_days = len({e["day"] for e in emitted if e["death"]})
    all_days = len({e["day"] for e in emitted})
    return {
        "death": {"n": dn, "mean_pct": dm, "win": dw},
        "live": {"n": ln, "mean_pct": lm, "win": lw},
        "death_days": death_days, "all_days": all_days,
        "gap_pct": dm - lm,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit-primary", help="write the PRIMARY variant's guards trades to this jsonl")
    a = ap.parse_args()

    breadth = build_breadth()
    trades = load_trades()
    days_cov = sorted(breadth)
    print(f"breadth days: {len(breadth)} ({days_cov[0]}..{days_cov[-1]}, ~{MIN_UNIV}+ codes/day)")
    print(f"low-suck trades in mode_history: {len(trades)}")
    print(f"n_tried (Bonferroni) = {len(GRID)} pre-registered variants\n")

    print(f"{'variant':<14} {'deathTr':>7} {'deathd':>6} {'death_ret':>9} {'live_ret':>8} "
          f"{'gap':>7} {'spread':>7} {'wf_tr':>6} {'wf_te':>6} {'p':>7}  verdict")
    print("-" * 100)
    for kind, N, tau in GRID:
        flag, days = death_flags(breadth, kind, N, tau)
        emitted = emit(breadth, flag, days, trades)
        ev = conditional_ev(emitted)
        v = guards.evaluate_hypothesis(
            [{"day": e["day"], "strat_ret": e["strat_ret"], "base_ret": e["base_ret"]} for e in emitted],
            n_tried=len(GRID), cache_only=True,
        )
        name = f"{kind}(N={N}" + (f",t={tau})" if tau is not None else ")")
        mark = "PASS" if v["verdict"] == "PASS" else "rej:" + ",".join(
            k.replace("survives_per_trade_equal_weight", "spread").replace("walk_forward_consistent", "wf")
             .replace("significant", "sig").replace("enough_days", "days") for k in v["rejected_by"])
        print(f"{name:<14} {ev['death']['n']:>7} {ev['death_days']:>6} "
              f"{ev['death']['mean_pct']:>+9.3f} {ev['live']['mean_pct']:>+8.3f} {ev['gap_pct']:>+7.3f} "
              f"{v['per_trade']['spread']:>+7.3f} {v['walk_forward']['train_edge']:>+6.2f} "
              f"{v['walk_forward']['test_edge']:>+6.2f} {v['significance']['p']:>7.4f}  {mark}")

    # Primary detail + optional emit for research_run.py
    kind, N, tau = PRIMARY
    flag, days = death_flags(breadth, kind, N, tau)
    emitted = emit(breadth, flag, days, trades)
    ev = conditional_ev(emitted)
    print(f"\nPRIMARY = {kind}(N={N},tau={tau}):")
    print(f"  death-window trades: {ev['death']['n']} on {ev['death_days']}/{ev['all_days']} days "
          f"({100*ev['death_days']/max(ev['all_days'],1):.1f}% of days)")
    print(f"  death-window mean return {ev['death']['mean_pct']:+.3f}% (win {100*ev['death']['win']:.1f}%)  vs  "
          f"non-death {ev['live']['mean_pct']:+.3f}% (win {100*ev['live']['win']:.1f}%)")
    print(f"  conditional EV gap: {ev['gap_pct']:+.3f}% per trade")

    if a.emit_primary:
        p = Path(a.emit_primary)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for e in emitted:
                fh.write(json.dumps({"day": e["day"], "strat_ret": e["strat_ret"],
                                     "base_ret": e["base_ret"]}, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(emitted)} guards trades -> {p}")
        print(f"  run: python3 scripts/research_run.py --trades {p} --n-tried {len(GRID)}")


if __name__ == "__main__":
    main()
