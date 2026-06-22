#!/usr/bin/env python3
"""XH-013 (corrected): does riding the 趋势主线 beat the system's 短线低吸?

User correction (2026-06-22): it is NOT about 龙头 (the emotional/连板-height
leader). 小草's object is the **趋势主线** — the core BIG-CAPS (中军/核心大票) of
the dominant direction, in a SUSTAINED medium-to-long-term uptrend, HELD through
the trend. Grounded in docs/XIAOCAO_PLAYBOOK.md:
  - 趋势与短线是两套独立体系 ("趋势跟短线没关系")            [playbook L14]
  - 看中军/核心大票,不看杂毛;主线中军>主线大票>...>后排补涨  [playbook L28-29]
  - 大票单独排名,平铺 2-3 只最强                            [playbook L31, bigcap.py]
  - 方向还在就扛 / 卖趋势不必等破位 (medium-long hold)        [playbook L59,62]
  - 跌>4000家但大小票分化=资金聚焦大票=机构 → 站趋势大票     [playbook L108]

So the faithful definition (NOT my earlier momentum proxy):
  universe  = 大票  : top-`bigcap_pct` by FLOAT MKTCAP (tradableAShare*close)
  trend     = sustained: top-M by L-day momentum WITHIN big-caps (L long: 40-120d)
  hold      = 中长期 : H trading days, NON-OVERLAPPING (honest independence)
  size      = 平铺 2-3 最强 : small M (default 3)

Every universe is measured on ONE identical convention (H-day fwd close-to-close
from date_kline) so this is not the unpaired-PnL "真实的谎言" v1 fell into.

Two paired-by-window comparisons, judged by the guards:
  (A) trend-bigcap vs BIG-CAP MARKET  -> is there trend-selection alpha in 大票?
  (B) trend-bigcap vs LOW-SUCK picks  -> 做趋势主线 vs 做短线低吸 (same convention)

Cache-only. Usage: python3 scripts/research_trend_mainline.py [--emit DIR]
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
BIGCAP_PCT = 0.20  # top-20% by float mktcap = 大票 (bigcap.py default)

# Pre-registered grid: (L trend-lookback, M leaders, H hold). Non-overlapping holds.
# PRIMARY = 60-day trend, 平铺 3 最强, 10-day (~2wk 中期) hold.
GRID = [
    (60, 3, 10),   # PRIMARY
    (60, 3, 20),
    (40, 3, 10),
    (120, 3, 20),
    (60, 5, 10),
    (40, 5, 20),
]
PRIMARY = GRID[0]


def shares_map():
    out = {}
    for data in iter_cached_responses(str(DB), "/stock/stock_info"):
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict):
                    c, s = r.get("code"), r.get("tradableAShare")
                    if c and isinstance(s, (int, float)) and s > 0:
                        out[c] = float(s)
    return out


def build_panel():
    by_date = defaultdict(dict)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td, code, close = k.get("tradeDate"), k.get("code"), k.get("close")
            if td and code and isinstance(close, (int, float)) and close > 0:
                by_date[td][code] = float(close)
    days = sorted(d for d in by_date if len(by_date[d]) >= MIN_UNIV)
    return by_date, days


def bigcaps_on(by_date, shares, day):
    """Top-BIGCAP_PCT codes by float mktcap (tradableAShare*close) on `day`."""
    caps = [(shares.get(c, 0.0) * px, c) for c, px in by_date[day].items() if c in shares]
    caps = [(v, c) for v, c in caps if v > 0]
    if not caps:
        return set()
    caps.sort(reverse=True)
    cut = max(1, int(len(caps) * BIGCAP_PCT))
    return {c for _, c in caps[:cut]}


def ret(by_date, days, code, i, j):
    a = by_date[days[i]].get(code)
    b = by_date[days[j]].get(code) if 0 <= j < len(days) else None
    if a and b:
        return (b / a - 1.0) * 100.0
    return None


def low_suck_picks():
    import sqlite3
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT trade_date, code FROM mode_history WHERE mode NOT LIKE '/stock/%'").fetchall()
    finally:
        con.close()
    out = defaultdict(list)
    for d, c in rows:
        out[d].append(c)
    return out


def run_variant(by_date, days, shares, lsp, L, M, H):
    """Non-overlapping windows. Returns lists of (trend, bigmkt, lowsuck) per window."""
    rows_market, rows_lowsuck = [], []
    i = L
    while i < len(days) - H:
        sel = days[i]
        bc = bigcaps_on(by_date, shares, sel)
        if len(bc) < 20:
            i += H
            continue
        # trend = top-M big-caps by L-day momentum, still present at horizon
        cands = []
        for c in bc:
            m = ret(by_date, days, c, i - L, i)
            f = ret(by_date, days, c, i, i + H)
            if m is not None and f is not None:
                cands.append((m, f))
        bigmkt = [ret(by_date, days, c, i, i + H) for c in bc]
        bigmkt = [x for x in bigmkt if x is not None]
        if len(cands) >= M and bigmkt:
            cands.sort(reverse=True)
            trend = sum(f for _, f in cands[:M]) / M
            rows_market.append({"day": sel, "strat_ret": trend,
                                "base_ret": sum(bigmkt) / len(bigmkt)})
            # low-suck: picks entered within the window, repriced H-day fwd
            lf = []
            for k in range(i, i + H):
                for c in lsp.get(days[k], []):
                    r = ret(by_date, days, c, k, min(k + H, len(days) - 1))
                    if r is not None:
                        lf.append(r)
            if lf:
                rows_lowsuck.append({"day": sel, "strat_ret": trend, "base_ret": sum(lf) / len(lf)})
        i += H
    return rows_market, rows_lowsuck


def fmt(v):
    pt = v["per_trade"]
    rej = "PASS" if v["verdict"] == "PASS" else "rej:" + ",".join(
        k.replace("survives_per_trade_equal_weight", "spr").replace("walk_forward_consistent", "wf")
         .replace("significant", "sig").replace("enough_days", "d") for k in v["rejected_by"])
    return (f"{v['n_days']:>3}w strat{pt['strat_mean']:>+6.2f} base{pt['base_mean']:>+6.2f} "
            f"spr{pt['spread']:>+6.2f} wf{v['walk_forward']['train_edge']:>+5.1f}/{v['walk_forward']['test_edge']:>+5.1f} "
            f"p{v['significance']['p']:>6.3f} {rej}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", help="dir for PRIMARY guards trades")
    a = ap.parse_args()

    shares = shares_map()
    by_date, days = build_panel()
    lsp = low_suck_picks()
    print(f"big-caps: {len(shares)} coded; panel {len(days)} days ({days[0]}..{days[-1]})")
    print(f"universe=top-{int(BIGCAP_PCT*100)}% float-mktcap; NON-overlapping holds; convention=H-day fwd c2c")
    print(f"n_tried (Bonferroni) = {len(GRID)}\n")
    print(f"{'variant':<16} {'(A) trend-bigcap vs BIG-CAP MARKET':<46} (B) vs LOW-SUCK")
    print("-" * 110)
    for (L, M, H) in GRID:
        rm, rl = run_variant(by_date, days, shares, lsp, L, M, H)
        vA = guards.evaluate_hypothesis(rm, n_tried=len(GRID), cache_only=True)
        vB = guards.evaluate_hypothesis(rl, n_tried=len(GRID), cache_only=True)
        print(f"L{L}/M{M}/H{H:<3}  {fmt(vA):<46} {fmt(vB)}")

    L, M, H = PRIMARY
    rm, rl = run_variant(by_date, days, shares, lsp, L, M, H)
    vA = guards.evaluate_hypothesis(rm, n_tried=len(GRID), cache_only=True)
    vB = guards.evaluate_hypothesis(rl, n_tried=len(GRID), cache_only=True)
    print(f"\nPRIMARY L{L}/M{M}/H{H} (60d trend, 平铺3最强大票, {H}d hold):")
    print(f"  (A) vs big-cap market : {fmt(vA)}")
    print(f"      trend-bigcap {vA['per_trade']['strat_mean']:+.2f}% vs big-cap-market "
          f"{vA['per_trade']['base_mean']:+.2f}% per {H}d hold ({vA['n_days']} windows)")
    print(f"  (B) vs low-suck       : {fmt(vB)}")
    print(f"      trend-bigcap {vB['per_trade']['strat_mean']:+.2f}% vs low-suck "
          f"{vB['per_trade']['base_mean']:+.2f}% per {H}d hold ({vB['n_days']} windows)")

    if a.emit:
        d = Path(a.emit); d.mkdir(parents=True, exist_ok=True)
        for name, rows in [("trend_vs_bigmarket", rm), ("trend_vs_lowsuck", rl)]:
            p = d / f"{name}.jsonl"
            p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            print(f"  wrote {len(rows)} -> {p}")


if __name__ == "__main__":
    main()
