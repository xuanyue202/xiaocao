"""Grid-search adaptive (n_min, avg_threshold) params on March, validate on April.

Reads signals from /tmp/xc_v4_p1/signals_*.json (cold pass — all 31 signals).
Uses /tmp/xiaocao_cache.db's mode_history to compute rolling stats at signal-time.

Train: 2026-03-01 ~ 2026-03-31.  Test: 2026-04-01 ~ 2026-04-24.

Selection rule: pick the combo that maximizes March active_avg subject to
n_active >= 3 (avoid trivial "1 winning trade" overfits). Validate on April.
"""
from __future__ import annotations

import csv
import glob
import json
import statistics
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache
from xiaocao.strategy.adaptive import decide_mode_state


CACHE_DB = "/tmp/xiaocao_cache.db"
SIGNALS_DIR = "/tmp/xc_v4_p1"
TRADES_CSV = "/tmp/xc_v4_p1/trades.csv"


def load_signals_with_outcome() -> list[dict]:
    """Return list of {date, mode, code, returnPct} for every signal that has a trade outcome."""
    trades = list(csv.DictReader(open(TRADES_CSV, encoding="utf-8-sig")))
    keyed = {(t["buyDate"], t["mode"], t["code"]): float(t["returnPct"]) for t in trades}
    out = []
    for f in sorted(glob.glob(f"{SIGNALS_DIR}/signals_*.json")):
        date = f.split("signals_")[1].replace(".json", "")
        sigs = json.load(open(f))
        for s in sigs:
            ret = keyed.get((date, s["mode"], s["code"]))
            if ret is None:
                continue  # incomplete (last day, no next-day price)
            out.append({"date": date, "mode": s["mode"], "code": s["code"], "returnPct": ret})
    return out


def trade_days_from_signals(signals: list[dict]) -> list[str]:
    return sorted(set(s["date"] for s in signals))


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "avg": 0.0, "win": 0.0}
    wins = sum(1 for v in values if v > 0)
    return {"n": len(values), "avg": statistics.mean(values), "win": wins / len(values) * 100}


VALIDATED_EXCLUDE = {"接力低弱转2", "方向内绿盘低吸前3名"}


def evaluate(
    cache: SQLiteCache,
    signals: list[dict],
    trade_days: list[str],
    n_min: dict[int, int],
    thr: dict[int, float],
    apply_validated_exclude: bool = True,
) -> tuple[list[float], list[float]]:
    """Return (active_returns, shadow_returns).

    With apply_validated_exclude=True, signals from the two known-bad modes
    are auto-shadow (matching `--profile validated` baseline). Adaptive then
    runs on top of that filter.
    """
    active, shadow = [], []
    for sig in signals:
        if apply_validated_exclude and sig["mode"] in VALIDATED_EXCLUDE:
            shadow.append(sig["returnPct"])
            continue
        d = decide_mode_state(
            sig["mode"], sig["date"], cache,
            n_min_by_window=n_min,
            avg_threshold_by_window=thr,
            trade_days=trade_days,
        )
        (active if d.active else shadow).append(sig["returnPct"])
    return active, shadow


def main() -> None:
    cache = SQLiteCache(CACHE_DB)
    signals = load_signals_with_outcome()
    trade_days = trade_days_from_signals(signals)
    march = [s for s in signals if s["date"] < "2026-04-01"]
    april = [s for s in signals if s["date"] >= "2026-04-01"]
    print(f"signals: {len(signals)} total ({len(march)} March, {len(april)} April)")

    # Grid: n_min × thr
    n5_grid = [1, 2, 3]
    n10_grid = [1, 2, 3]
    n20_grid = [2, 3, 4]
    thr5_grid = [-3, -4, -5, -6, -7]
    thr10_grid = [-2, -3, -4, -5]
    thr20_grid = [-1, -2, -3]

    results = []
    for n5, n10, n20, t5, t10, t20 in product(n5_grid, n10_grid, n20_grid, thr5_grid, thr10_grid, thr20_grid):
        n_min = {5: n5, 10: n10, 20: n20}
        thr = {5: float(t5), 10: float(t10), 20: float(t20)}
        m_active, m_shadow = evaluate(cache, march, trade_days, n_min, thr)
        a_active, a_shadow = evaluate(cache, april, trade_days, n_min, thr)
        results.append({
            "config": (n5, n10, n20, t5, t10, t20),
            "march_active": stats(m_active),
            "march_shadow": stats(m_shadow),
            "april_active": stats(a_active),
            "april_shadow": stats(a_shadow),
        })

    # Filter for non-trivial March activity
    candidates = [r for r in results if r["march_active"]["n"] >= 1]
    candidates.sort(key=lambda r: r["march_active"]["avg"], reverse=True)

    print(f"\nGrid search: {len(results)} configs, {len(candidates)} with March active n>=1 (validated exclude applied)")
    print(f"\nTop 10 by March active avg (training set):")
    print(f"{'(n5,n10,n20, thr5,thr10,thr20)':<32}  {'M.act':<22}  {'M.shadow':<14}  {'A.act':<22}  {'A.shadow':<14}")
    for r in candidates[:10]:
        c = r["config"]
        ma = r["march_active"]; ms = r["march_shadow"]
        aa = r["april_active"]; as_ = r["april_shadow"]
        cfg = f"({c[0]},{c[1]},{c[2]} | {c[3]:>3},{c[4]:>3},{c[5]:>3})"
        ma_s = f"n={ma['n']:>2} avg={ma['avg']:+5.2f}% win={ma['win']:>4.0f}%"
        ms_s = f"n={ms['n']:>2} avg={ms['avg']:+5.2f}%"
        aa_s = f"n={aa['n']:>2} avg={aa['avg']:+5.2f}% win={aa['win']:>4.0f}%"
        as_s = f"n={as_['n']:>2} avg={as_['avg']:+5.2f}%"
        print(f"{cfg:<32}  {ma_s:<22}  {ms_s:<14}  {aa_s:<22}  {as_s:<14}")

    # Robustness: pick configs that pass BOTH windows with positive avg.
    # April is held-out validation.
    print(f"\nConfigs robust on BOTH windows (March act_avg ≥ +2% AND April act_avg ≥ +2% AND April n ≥ 3):")
    robust = [
        r for r in candidates
        if r["march_active"]["avg"] >= 2.0
        and r["april_active"]["avg"] >= 2.0
        and r["april_active"]["n"] >= 3
    ]
    robust.sort(key=lambda r: (r["march_active"]["avg"] + r["april_active"]["avg"]) / 2, reverse=True)
    for r in robust[:15]:
        c = r["config"]
        ma = r["march_active"]; aa = r["april_active"]
        cfg = f"({c[0]},{c[1]},{c[2]} | {c[3]:>3},{c[4]:>3},{c[5]:>3})"
        print(f"{cfg:<32}  M.act n={ma['n']:>2} avg={ma['avg']:+5.2f}% win={ma['win']:>4.0f}%  |  A.act n={aa['n']:>2} avg={aa['avg']:+5.2f}% win={aa['win']:>4.0f}%")

    print(f"\nConfigs robust w/ stricter April bar (≥ +5% & ≥3 trades):")
    strong = [
        r for r in candidates
        if r["march_active"]["avg"] >= 2.0
        and r["april_active"]["avg"] >= 5.0
        and r["april_active"]["n"] >= 3
    ]
    strong.sort(key=lambda r: (r["march_active"]["avg"] + r["april_active"]["avg"]) / 2, reverse=True)
    for r in strong[:15]:
        c = r["config"]
        ma = r["march_active"]; aa = r["april_active"]
        cfg = f"({c[0]},{c[1]},{c[2]} | {c[3]:>3},{c[4]:>3},{c[5]:>3})"
        print(f"{cfg:<32}  M.act n={ma['n']:>2} avg={ma['avg']:+5.2f}% win={ma['win']:>4.0f}%  |  A.act n={aa['n']:>2} avg={aa['avg']:+5.2f}% win={aa['win']:>4.0f}%")

    # Compare against current default
    cur_n = {5: 1, 10: 2, 20: 3}
    cur_t = {5: -5.0, 10: -3.0, 20: -2.0}
    m_a, _ = evaluate(cache, march, trade_days, cur_n, cur_t)
    a_a, _ = evaluate(cache, april, trade_days, cur_n, cur_t)
    print(f"\nCurrent default (1,2,3 | -5,-3,-2): March active {stats(m_a)}, April active {stats(a_a)}")


if __name__ == "__main__":
    main()
