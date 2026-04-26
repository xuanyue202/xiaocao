"""Build a per-date proxy regime from cached endpoints — Category D groundwork.

`market_overview` is live state with no per-date variant; we derive a proxy
from data that IS date-anchored:

  1. /stock/xiao_cao_index_v2: per-stock pctChange (positive_ratio, mean_pct)
  2. /stock/xiao_cao_industry_block_rank: top-K block strength sum (`num`)

The proxy maps each date to one of:
   bull       — broad strength (positive_ratio high AND top-K strong)
   trend      — moderate strength (mean_pct ≥ 0)
   neutral    — flat
   divergence — mixed (low positive_ratio + low strength)
   bear       — broad weakness

Thresholds tuned to spread across the 5-month universe roughly 20/30/30/15/5.

Outputs `output/proxy_regime.json`: {date: {regime, positive_ratio, mean_pct,
top_block_sum}}.

Cache-only.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from replay_lib import CACHE_DB, trade_days_in_universe, load_universe  # noqa: E402

OUT_PATH = ROOT / "output" / "proxy_regime.json"


def aggregate_kline_sentiment() -> dict[str, list[float]]:
    """For each date, collect pctChangeRate from every cached daily kline row.

    Cached date_kline calls span ~157 distinct stocks; for each (date, code)
    pair we get one pctChangeRate sample. Per-date sample size 300-900 across
    Dec-April. Much more comprehensive than xiao_cao_index_v2 which is
    strategy-selected (and biased toward 弱-候选 stocks).

    De-dups per (date, code) so a stock that appears in multiple kline fetches
    contributes only once per date.
    """
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    with sqlite3.connect(CACHE_DB) as conn:
        rows = conn.execute(
            "SELECT response_json FROM api_cache "
            "WHERE endpoint='/stock/date_kline'"
        ).fetchall()
    for (rj,) in rows:
        try:
            data = json.loads(rj)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            td = k.get("tradeDate", "")
            code = k.get("code", "")
            pct = k.get("pctChangeRate")
            if td and code and isinstance(pct, (int, float)):
                by_date[td][code] = float(pct)
    return {d: list(codes.values()) for d, codes in by_date.items()}


def aggregate_block_rank_strength(model: int = 0) -> dict[str, float]:
    """For each date, sum the top-10 block `num` strengths."""
    out: dict[str, float] = {}
    with sqlite3.connect(CACHE_DB) as conn:
        rows = conn.execute(
            "SELECT params_json, response_json FROM api_cache "
            "WHERE endpoint='/stock/xiao_cao_industry_block_rank'"
        ).fetchall()
    for pj, rj in rows:
        p = json.loads(pj)
        inner = p.get("params", p)
        d = str(inner.get("date") or "")
        if len(d) == 8 and d.isdigit():
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if inner.get("model") != model:
            continue
        try:
            data = json.loads(rj)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data = data.get("data") or list(data.values())
        if not isinstance(data, list):
            continue
        nums = []
        for r in data:
            if not isinstance(r, dict):
                continue
            v = r.get("num") or r.get("value") or r.get("score")
            if isinstance(v, (int, float)):
                nums.append(float(v))
        nums.sort(reverse=True)
        out[d] = sum(nums[:10])
    return out


def classify(positive_ratio: float, mean_pct: float, top_block_sum: float,
             *, p70_block: float, p30_block: float) -> str:
    """Map proxy metrics to a regime label."""
    # Bear: very weak across all three
    if positive_ratio < 0.30 and mean_pct < -1.0:
        return "bear"
    # Bull: very strong across all three
    if positive_ratio >= 0.65 and mean_pct >= 1.0 and top_block_sum >= p70_block:
        return "bull"
    # Trend: positive but not blowout
    if positive_ratio >= 0.55 and mean_pct >= 0.0:
        return "trend"
    # Divergence: low positive_ratio without bear-level weakness
    if positive_ratio < 0.40 or top_block_sum < p30_block:
        return "divergence"
    return "neutral"


def main() -> None:
    universe = load_universe()
    days = trade_days_in_universe(universe)
    print(f"universe days: {len(days)} ({days[0]} → {days[-1]})")

    pct_by_date = aggregate_kline_sentiment()
    block_strength = aggregate_block_rank_strength(model=0)

    # Compute thresholds
    block_vals = [v for d, v in block_strength.items() if d in days]
    if not block_vals:
        print("!!! no block strength data — abort")
        return
    block_vals.sort()
    p30 = block_vals[len(block_vals) * 30 // 100]
    p70 = block_vals[len(block_vals) * 70 // 100]
    print(f"block_strength p30={p30:.0f}, p70={p70:.0f}, range [{block_vals[0]:.0f}, {block_vals[-1]:.0f}]")

    # Classify each day
    out: dict[str, dict] = {}
    counter: dict[str, int] = defaultdict(int)
    for d in days:
        pcts = pct_by_date.get(d, [])
        n = len(pcts)
        if n == 0:
            out[d] = {"regime": "unknown", "n_samples": 0}
            counter["unknown"] += 1
            continue
        positive_ratio = sum(1 for v in pcts if v > 0) / n
        mean_pct = statistics.mean(pcts)
        block_sum = block_strength.get(d, 0.0)
        regime = classify(
            positive_ratio, mean_pct, block_sum,
            p70_block=p70, p30_block=p30,
        )
        out[d] = {
            "regime": regime,
            "n_samples": n,
            "positive_ratio": round(positive_ratio, 3),
            "mean_pct": round(mean_pct, 3),
            "top_block_sum": round(block_sum, 1),
        }
        counter[regime] += 1

    print(f"\nregime distribution across {len(days)} days:")
    for regime, n in sorted(counter.items(), key=lambda t: -t[1]):
        print(f"  {regime:<14} {n:>3} ({100*n/len(days):.0f}%)")

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nproxy regime → {OUT_PATH}")


if __name__ == "__main__":
    main()
