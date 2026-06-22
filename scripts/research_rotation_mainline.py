#!/usr/bin/env python3
"""XH-013 (faithful): does riding the 轮动频率主线 beat the average theme?

This is 小草's ACTUAL mainline signal, not a momentum strawman. From the playbook:
  "判主线生死用行业轮动频率:某板块轮动频率高=主线在(今天不轮明天轮);
   掉出前列被新材料/有色顶上=主线走弱" [XIAOCAO_PLAYBOOK.md L19]
i.e. the mainline is the concept that PERSISTENTLY returns to the top of the
ranking over a trailing window — NOT whatever had the highest trailing return
(that proxy failed: top-momentum reverses, see research_leader_select /
research_trend_mainline).

Data: block_category_rank_v3 (model=0) gives, per day (337 days, full year), ~52
NAMED concepts each with `num` (小草 strength score) and `prePctChangeRate` (the
concept's daily % return — verified: 算力芯片 cumulates +75% over the year).

Operationalization (cache-only, no lookahead):
  rotation_freq(concept, d, W) = fraction of trailing W days the concept was in
                                 the top-K by `num`
  mainline = the M concepts with highest rotation frequency through day d
  strat[window] = forward H-day return of the mainline concepts
                  (cumprod of prePctChangeRate over (d, d+H], strictly forward)
  base[window]  = mean forward H-day return across ALL concepts (the average theme)
  -> does selecting the persistent mainline beat holding the average theme?
Non-overlapping windows (honest independence). Guards judge it.

Usage: python3 scripts/research_rotation_mainline.py [--emit DIR]
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

# Pre-registered grid: (W rotation-lookback, K top-rank cutoff, M mainlines, H hold).
# PRIMARY = top-5 persistence over 20d, hold the 3 most-persistent, 10-day hold.
GRID = [
    (20, 5, 3, 10),   # PRIMARY
    (20, 5, 1, 10),
    (10, 5, 3, 10),
    (20, 10, 3, 20),
    (20, 3, 1, 20),
    (10, 10, 5, 10),
]
PRIMARY = GRID[0]


def load_concepts():
    num = defaultdict(dict)  # date -> code -> num
    ret = defaultdict(dict)  # date -> code -> daily % return
    for pj, data in iter_cached_responses(str(DB), "/stock/xiao_cao_block_category_rank_v3", include_params=True):
        p = json.loads(pj).get("params", {})
        if p.get("model") != 0 or not isinstance(data, dict):
            continue
        d = p.get("date")
        lst = data.get("localCategoryRankList") or data.get("globalCategoryRankList")
        if isinstance(lst, list):
            for it in lst:
                cc = it.get("categoryCode")
                if not cc:
                    continue
                num[d][cc] = it.get("num") or 0
                v = it.get("prePctChangeRate")
                if isinstance(v, (int, float)):
                    ret[d][cc] = float(v)
    days = sorted(d for d in num if num[d])
    return num, ret, days


def fwd(ret, days, code, i, H):
    """Forward H-day cumulative return of a concept, strictly after day i."""
    cum = 1.0
    seen = 0
    for j in range(i + 1, min(i + 1 + H, len(days))):
        v = ret[days[j]].get(code)
        if v is None:
            return None
        cum *= 1.0 + v / 100.0
        seen += 1
    return (cum - 1.0) * 100.0 if seen == H else None


def rotation_freq(num, days, i, W, K):
    """concept -> fraction of trailing W days it was in the top-K by num."""
    cnt = defaultdict(int)
    for j in range(max(0, i - W + 1), i + 1):
        top = sorted(num[days[j]].items(), key=lambda t: t[1], reverse=True)[:K]
        for cc, _ in top:
            cnt[cc] += 1
    return {cc: c / W for cc, c in cnt.items()}


def run_variant(num, ret, days, W, K, M, H):
    rows = []
    i = W
    while i < len(days) - H - 1:
        freq = rotation_freq(num, days, i, W, K)
        mains = [cc for cc, _ in sorted(freq.items(), key=lambda t: t[1], reverse=True)[:M]]
        sf = [fwd(ret, days, cc, i, H) for cc in mains]
        sf = [x for x in sf if x is not None]
        allf = [fwd(ret, days, cc, i, H) for cc in num[days[i]]]
        allf = [x for x in allf if x is not None]
        if sf and len(allf) >= 10:
            rows.append({"day": days[i], "strat_ret": sum(sf) / len(sf),
                         "base_ret": sum(allf) / len(allf)})
        i += H
    return rows


def fmt(v):
    pt = v["per_trade"]
    rej = "PASS" if v["verdict"] == "PASS" else "rej:" + ",".join(
        k.replace("survives_per_trade_equal_weight", "spr").replace("walk_forward_consistent", "wf")
         .replace("significant", "sig").replace("enough_days", "d") for k in v["rejected_by"])
    return (f"{v['n_days']:>3}w  mainline{pt['strat_mean']:>+6.2f}  avg-theme{pt['base_mean']:>+6.2f}  "
            f"spread{pt['spread']:>+6.2f}  wf{v['walk_forward']['train_edge']:>+5.1f}/{v['walk_forward']['test_edge']:>+5.1f}  "
            f"p={v['significance']['p']:.3f}  {rej}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit", help="dir for PRIMARY guards trades")
    a = ap.parse_args()

    num, ret, days = load_concepts()
    print(f"concept panel: {len(days)} days ({days[0]}..{days[-1]}), ~{len(num[days[-1]])} concepts/day")
    print(f"signal = 轮动频率 (persistence in top-K by num); convention = forward H-day concept return")
    print(f"n_tried (Bonferroni) = {len(GRID)}\n")
    print(f"{'variant':<18} verdict")
    print("-" * 100)
    for (W, K, M, H) in GRID:
        rows = run_variant(num, ret, days, W, K, M, H)
        v = guards.evaluate_hypothesis(rows, n_tried=len(GRID), cache_only=True)
        print(f"W{W}/K{K}/M{M}/H{H:<3}  {fmt(v)}")

    W, K, M, H = PRIMARY
    rows = run_variant(num, ret, days, W, K, M, H)
    v = guards.evaluate_hypothesis(rows, n_tried=len(GRID), cache_only=True)
    print(f"\nPRIMARY W{W}/K{K}/M{M}/H{H} (most-persistent top-5 mainline over 20d, hold 3, 10d):")
    print(f"  {fmt(v)}")
    print(f"  -> persistent mainline {v['per_trade']['strat_mean']:+.2f}% vs average theme "
          f"{v['per_trade']['base_mean']:+.2f}% per {H}d hold ({v['n_days']} windows)")

    if a.emit:
        d = Path(a.emit); d.mkdir(parents=True, exist_ok=True)
        p = d / "rotation_vs_avgtheme.jsonl"
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"  wrote {len(rows)} -> {p}")
        print(f"  run: python3 scripts/research_run.py --trades {p} --n-tried {len(GRID)}")


if __name__ == "__main__":
    main()
