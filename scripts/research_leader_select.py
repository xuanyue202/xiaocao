#!/usr/bin/env python3
"""XH-013: is there systematic TREND-LEADER selection alpha? (execution-neutral)

The June counterfactual (小草's named leaders 6/1->6/19 +29.5% vs the system's
low-suck -6%) claimed the lever is the *universe* — ride trending leaders, not
oversold dips. This systematizes it over the full cached year.

CRITICAL METHODOLOGY NOTE (why v1 was wrong): mode_history.return_pct is the
low-suck strategy's *execution-juiced realized PnL* (mean +2.3% but MEDIAN -1.3%;
matches no raw date_kline price-change convention). Comparing it to a leader
basket's raw forward price change mixes universe alpha with execution convention
— the same unpaired-book "真实的谎言" the guards exist to refuse. So here EVERY
universe is measured on ONE identical convention: H-day forward close-to-close
return from date_kline. This isolates SELECTION (universe) from EXECUTION.

No lookahead: leaders are chosen by trailing R-day momentum through day i's close
(liquidity-gated to approximate big-cap leaders, not small-cap rockets), then held
close[i]->close[i+H].

Two paired-by-day comparisons, both judged by the guards:
  (A) leader vs MARKET  : strat = leader fwd, base = liquid-universe mean fwd
                          -> is there trend-leader selection alpha at all?
  (B) leader vs LOW-SUCK : base = low-suck picks repriced on the SAME convention
                          -> which universe's raw stock returns are higher?

Caveat kept explicit: "momentum leader" is a transparent PROXY for 小草's
mainline leaders (the opaque block_rank can't reconstruct his actual picks).

Cache-only. Usage:
  python3 scripts/research_leader_select.py
  python3 scripts/research_leader_select.py --emit out/dir
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
MIN_UNIV = 500

# Pre-registered grid: (R lookback, M leaders, H hold days, liquidity quantile).
# PRIMARY = sustained 60-day trend leaders, top-10, 5-day hold, liquid top-30%.
GRID = [
    (60, 10, 5, 0.70),   # PRIMARY
    (20, 10, 5, 0.70),
    (120, 10, 5, 0.70),
    (60, 10, 1, 0.70),
    (60, 5, 5, 0.70),
    (20, 10, 1, 0.70),
]
PRIMARY = GRID[0]


def build_panel():
    by_date: dict[str, dict[str, tuple]] = defaultdict(dict)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td, code = k.get("tradeDate"), k.get("code")
            pct, amt, close = k.get("pctChangeRate"), k.get("amt"), k.get("close")
            if td and code and isinstance(close, (int, float)) and close > 0:
                by_date[td][code] = (float(pct) if isinstance(pct, (int, float)) else 0.0,
                                     float(amt or 0.0), float(close))
    days = sorted(d for d in by_date if len(by_date[d]) >= MIN_UNIV)
    return by_date, days


def fwd_return(by_date, days, code, i, H):
    """H-day forward close-to-close return (percent), entered at close[i]."""
    if i + H >= len(days):
        return None
    a = by_date[days[i]].get(code)
    b = by_date[days[i + H]].get(code)
    if not a or not b:
        return None
    return (b[2] / a[2] - 1.0) * 100.0


def momentum(by_date, days, code, i, R):
    a = by_date[days[i - R]].get(code) if i - R >= 0 else None
    b = by_date[days[i]].get(code)
    if not a or not b:
        return None
    return (b[2] / a[2] - 1.0) * 100.0


def run_variant(by_date, days, R, M, H, liq_q, low_suck_picks):
    """Return (leader[d], market[d], lowsuck[d]) per selection-day."""
    leader, market, lowsuck = {}, {}, {}
    for i in range(R, len(days) - H):
        sel = by_date[days[i]]
        amts = sorted(a for _, a, _ in sel.values())
        thr = amts[int(liq_q * (len(amts) - 1))]
        # market = liquid-universe mean forward return
        mfwd = [fwd_return(by_date, days, c, i, H) for c, (_, a, _) in sel.items() if a >= thr]
        mfwd = [x for x in mfwd if x is not None]
        if len(mfwd) < 20:
            continue
        market[days[i]] = sum(mfwd) / len(mfwd)
        # leaders = top-M trailing-momentum among liquid names
        cands = []
        for c, (_, a, _) in sel.items():
            if a < thr:
                continue
            m = momentum(by_date, days, c, i, R)
            f = fwd_return(by_date, days, c, i, H)
            if m is not None and f is not None:
                cands.append((m, f))
        if len(cands) >= M:
            cands.sort(reverse=True)
            top = cands[:M]
            leader[days[i]] = sum(f for _, f in top) / len(top)
        # low-suck picks repriced on the SAME convention
        picks = low_suck_picks.get(days[i])
        if picks:
            lf = [fwd_return(by_date, days, c, i, H) for c in picks]
            lf = [x for x in lf if x is not None]
            if lf:
                lowsuck[days[i]] = sum(lf) / len(lf)
    return leader, market, lowsuck


def low_suck_picks_by_day():
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, code FROM mode_history WHERE mode NOT LIKE '/stock/%'"
        ).fetchall()
    finally:
        con.close()
    out = defaultdict(list)
    for d, c in rows:
        out[d].append(c)
    return out


def pair(a: dict, b: dict):
    return [{"day": d, "strat_ret": a[d], "base_ret": b[d]} for d in sorted(set(a) & set(b))]


def judge(rows, n_tried):
    return guards.evaluate_hypothesis(rows, n_tried=n_tried, cache_only=True)


def fmt(v):
    pt = v["per_trade"]
    rej = "PASS" if v["verdict"] == "PASS" else "rej:" + ",".join(
        k.replace("survives_per_trade_equal_weight", "spr").replace("walk_forward_consistent", "wf")
         .replace("significant", "sig").replace("enough_days", "d") for k in v["rejected_by"])
    return (f"{v['n_days']:>4}d  strat {pt['strat_mean']:>+6.3f} base {pt['base_mean']:>+6.3f} "
            f"spread {pt['spread']:>+6.3f}  wf {v['walk_forward']['train_edge']:>+5.2f}/"
            f"{v['walk_forward']['test_edge']:>+5.2f}  p={v['significance']['p']:.4f}  {rej}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", help="dir to write PRIMARY guards trades (leader_vs_market.jsonl, leader_vs_lowsuck.jsonl)")
    a = ap.parse_args()

    by_date, days = build_panel()
    lsp = low_suck_picks_by_day()
    print(f"date_kline panel: {len(days)} days ({days[0]}..{days[-1]})")
    print(f"convention: H-day forward close-to-close, IDENTICAL for every universe")
    print(f"n_tried (Bonferroni) = {len(GRID)}\n")

    print(f"{'variant':<20} {'(A) leader vs MARKET':<58} {'(B) leader vs LOW-SUCK'}")
    print("-" * 120)
    for (R, M, H, q) in GRID:
        leader, market, lowsuck = run_variant(by_date, days, R, M, H, q, lsp)
        vA = judge(pair(leader, market), len(GRID))
        vB = judge(pair(leader, lowsuck), len(GRID))
        print(f"R{R}/M{M}/H{H}/liq{int(q*100):<3}  {fmt(vA):<58} {fmt(vB)}")

    R, M, H, q = PRIMARY
    leader, market, lowsuck = run_variant(by_date, days, R, M, H, q, lsp)
    rA, rB = pair(leader, market), pair(leader, lowsuck)
    vA, vB = judge(rA, len(GRID)), judge(rB, len(GRID))
    print(f"\nPRIMARY R{R}/M{M}/H{H}/liq{int(q*100)} (sustained 60d trend leaders, top-10, 5-day hold):")
    print(f"  (A) leader vs market : {fmt(vA)}")
    print(f"      -> leader {vA['per_trade']['strat_mean']:+.3f}% vs market {vA['per_trade']['base_mean']:+.3f}% per 5d hold")
    print(f"  (B) leader vs low-suck (same convention): {fmt(vB)}")
    print(f"      -> leader {vB['per_trade']['strat_mean']:+.3f}% vs low-suck-picks {vB['per_trade']['base_mean']:+.3f}% per 5d hold")

    if a.emit:
        d = Path(a.emit); d.mkdir(parents=True, exist_ok=True)
        for name, rows in [("leader_vs_market", rA), ("leader_vs_lowsuck", rB)]:
            p = d / f"{name}.jsonl"
            with p.open("w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  wrote {len(rows)} -> {p}")


if __name__ == "__main__":
    main()
