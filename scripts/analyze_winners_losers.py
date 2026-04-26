"""First-principles trade analysis Sep25-Mar26 (TRAIN window).

For every trade in mode_history within TRAIN, joins:
  - signal context (signals_*.json from latest backtest)
  - state vector (from cached date_kline)
  - mode, openPctChange, xcjw/jssb/cjs scores

Then classifies:
  - Winners (returnPct > +1%): what state + score + mode patterns paid?
  - Losers (returnPct < -1%): what state + score + mode patterns failed?
  - In-between (-1% .. +1%): noise / wash trades

Outputs:
  - Patterns to reinforce (recurring positive setups)
  - Anti-patterns to flag (recurring negative setups)
  - Asymmetric setups (high upside / limited downside or vice versa)

This is a pure data analysis — no API, no rule changes.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache
from xiaocao.strategy.regime import mode_fitness
from xiaocao.strategy.state import build_state_index

TRAIN_START = "2025-09-01"
TRAIN_END = "2026-03-31"

# Use 8-month seed with v3 result as canonical signal source
SIGNAL_DIRS = [
    ROOT / "output" / "xiaocao_8mo_v3_adaptive",
    ROOT / "output" / "xiaocao_8mo_v2_adaptive",
    ROOT / "output" / "xiaocao_8month_seed",
]


def load_trades_with_context() -> list[dict]:
    """Join mode_history with cached signals to recover full per-trade context."""
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    state_index = build_state_index(cache)

    # Load trades.csv from any of the seed dirs (they should have the same trades)
    trades = []
    for d in SIGNAL_DIRS:
        p = d / "trades.csv"
        if p.exists():
            with p.open(encoding="utf-8-sig") as f:
                trades = list(csv.DictReader(f))
            break
    if not trades:
        raise SystemExit("no trades.csv found in seed dirs")

    # Filter to TRAIN window
    trades = [t for t in trades if TRAIN_START <= t["buyDate"] <= TRAIN_END]
    print(f"TRAIN trades: {len(trades)}")

    # Load signals to recover state/score context
    signals_by_key: dict[tuple[str, str, str], dict] = {}
    seed_dir = SIGNAL_DIRS[0]
    for sf in sorted(seed_dir.glob("signals_*.json")):
        date = sf.stem.replace("signals_", "")
        if not (TRAIN_START <= date <= TRAIN_END):
            continue
        for sig in json.loads(sf.read_text(encoding="utf-8")):
            k = (date, sig.get("mode", ""), str(sig.get("code", "")))
            signals_by_key[k] = sig

    # Enrich trades
    enriched = []
    for t in trades:
        try:
            ret = float(t["returnPct"])
        except (ValueError, KeyError):
            continue
        date = t["buyDate"]
        mode = t["mode"]
        code = t["code"]
        sig = signals_by_key.get((date, mode, code), {})
        state = state_index.get(date)
        enriched.append({
            "date": date,
            "mode": mode,
            "code": code,
            "name": sig.get("name") or t.get("name") or "",
            "ret": ret,
            "open_pct": float(t.get("openPctChange") or 0.0),
            "xcjw": float(sig.get("xcjw") or 0.0),
            "cjs": float(sig.get("cjs") or 0.0),
            "jsjl": float(sig.get("jsjl") or 0.0),
            "jssb": float(sig.get("jssb") or 0.0),
            "direction": bool(sig.get("direction", False)),
            "is_main_line": bool(sig.get("is_main_line", False)),
            "is_big_cap": bool(sig.get("is_big_cap", False)),
            "state": state,
            "fitness": mode_fitness(mode, state) if state else 0.0,
        })
    return enriched


def fmt_state(s) -> str:
    if s is None:
        return "(no state)"
    return f"R={s.reward:.2f} Risk={s.risk:.2f} Cont={s.continuity:.2f} DBR={s.duan_ban_recovery:.2f}"


def section(title: str) -> None:
    print(f"\n{'='*90}\n{title}\n{'='*90}")


def main() -> None:
    trades = load_trades_with_context()
    if not trades:
        print("No trades.")
        return

    winners = [t for t in trades if t["ret"] > +1.0]
    losers = [t for t in trades if t["ret"] < -1.0]
    washes = [t for t in trades if -1.0 <= t["ret"] <= +1.0]

    section(f"Cohort split (TRAIN {TRAIN_START} → {TRAIN_END})")
    print(f"  total: {len(trades)}")
    print(f"  winners (>+1%):  {len(winners)} avg={statistics.mean(t['ret'] for t in winners):+.2f}%")
    print(f"  losers (<-1%):   {len(losers)} avg={statistics.mean(t['ret'] for t in losers):+.2f}%")
    print(f"  washes (±1%):    {len(washes)}")

    # --- per-mode breakdown -------------------------------------------------
    section("Per-mode WIN/LOSE pattern")
    by_mode = defaultdict(list)
    for t in trades:
        by_mode[t["mode"]].append(t)
    print(f"{'mode':<22} {'n':>3} {'win':>4} {'lose':>4} {'wash':>4} {'avg':>7} {'best':>7} {'worst':>7}")
    for mode, ts in sorted(by_mode.items(), key=lambda x: -statistics.mean(t["ret"] for t in x[1])):
        wins = sum(1 for t in ts if t["ret"] > +1.0)
        loses = sum(1 for t in ts if t["ret"] < -1.0)
        washes_n = len(ts) - wins - loses
        avg = statistics.mean(t["ret"] for t in ts)
        best = max(t["ret"] for t in ts)
        worst = min(t["ret"] for t in ts)
        print(f"  {mode:<22} {len(ts):>3} {wins:>4} {loses:>4} {washes_n:>4} {avg:>+6.2f}% {best:>+6.1f}% {worst:>+6.1f}%")

    # --- winners: what's the modal pattern? ---------------------------------
    section("BIG WINNERS (top 15 by return)")
    sorted_win = sorted(winners, key=lambda t: -t["ret"])[:15]
    print(f"{'date':<12} {'mode':<22} {'code':<14} {'ret%':>7} {'open%':>6} {'xcjw':>6} {'jssb':>6} {'dir':>4} state")
    for t in sorted_win:
        print(f"  {t['date']:<12} {t['mode']:<22} {t['code']:<14} {t['ret']:>+6.2f}% "
              f"{t['open_pct']:>+5.1f}% {t['xcjw']:>5.0f} {t['jssb']:>5.0f} "
              f"{('dir' if t['direction'] else '-'):>4} {fmt_state(t['state'])}")

    section("BIG LOSERS (bottom 15 by return)")
    sorted_lose = sorted(losers, key=lambda t: t["ret"])[:15]
    print(f"{'date':<12} {'mode':<22} {'code':<14} {'ret%':>7} {'open%':>6} {'xcjw':>6} {'jssb':>6} {'dir':>4} state")
    for t in sorted_lose:
        print(f"  {t['date']:<12} {t['mode']:<22} {t['code']:<14} {t['ret']:>+6.2f}% "
              f"{t['open_pct']:>+5.1f}% {t['xcjw']:>5.0f} {t['jssb']:>5.0f} "
              f"{('dir' if t['direction'] else '-'):>4} {fmt_state(t['state'])}")

    # --- score quartile analysis --------------------------------------------
    section("Per-mode SCORE QUARTILE returns (winners only at top quartile?)")
    for mode, ts in by_mode.items():
        if len(ts) < 8:
            continue
        # primary score: lianban → xcjw, qibao → jssb, dixi → cjs
        if "接力" in mode:
            score_field = "xcjw"
        elif "起爆" in mode:
            score_field = "jssb"
        else:
            score_field = "cjs"
        scored = sorted(ts, key=lambda t: t[score_field])
        n = len(scored)
        q_size = n // 4
        if q_size < 2:
            continue
        quartiles = [
            ("Q1 (low)", scored[:q_size]),
            ("Q2", scored[q_size:2*q_size]),
            ("Q3", scored[2*q_size:3*q_size]),
            ("Q4 (high)", scored[3*q_size:]),
        ]
        print(f"\n  {mode} (score={score_field}):")
        for label, qs in quartiles:
            if qs:
                avg = statistics.mean(t["ret"] for t in qs)
                wins = sum(1 for t in qs if t["ret"] > +1.0) / len(qs) * 100
                rng = (qs[0][score_field], qs[-1][score_field])
                print(f"    {label:<10} n={len(qs):>2} score=[{rng[0]:>4.0f},{rng[1]:>4.0f}] avg={avg:>+6.2f}% win={wins:>4.0f}%")

    # --- open_pct quartile analysis -----------------------------------------
    section("Open_pct distribution within winners vs losers")
    win_open = [t["open_pct"] for t in winners]
    lose_open = [t["open_pct"] for t in losers]
    if win_open:
        print(f"  winners open_pct: median={statistics.median(win_open):+.2f}% mean={statistics.mean(win_open):+.2f}%  q1={sorted(win_open)[len(win_open)//4]:+.2f}% q3={sorted(win_open)[len(win_open)*3//4]:+.2f}%")
    if lose_open:
        print(f"  losers  open_pct: median={statistics.median(lose_open):+.2f}% mean={statistics.mean(lose_open):+.2f}%  q1={sorted(lose_open)[len(lose_open)//4]:+.2f}% q3={sorted(lose_open)[len(lose_open)*3//4]:+.2f}%")

    # --- direction support ---------------------------------------------------
    section("Direction-support effect (in mainline direction vs not)")
    in_dir = [t for t in trades if t["direction"]]
    out_dir = [t for t in trades if not t["direction"]]
    if in_dir:
        print(f"  in-direction:  n={len(in_dir)} avg={statistics.mean(t['ret'] for t in in_dir):+.2f}% win={sum(1 for t in in_dir if t['ret'] > +1.0)/len(in_dir)*100:.0f}%")
    if out_dir:
        print(f"  off-direction: n={len(out_dir)} avg={statistics.mean(t['ret'] for t in out_dir):+.2f}% win={sum(1 for t in out_dir if t['ret'] > +1.0)/len(out_dir)*100:.0f}%")

    # --- mainline membership ------------------------------------------------
    section("Mainline membership effect")
    in_main = [t for t in trades if t["is_main_line"]]
    off_main = [t for t in trades if not t["is_main_line"]]
    if in_main:
        print(f"  in-mainline:   n={len(in_main)} avg={statistics.mean(t['ret'] for t in in_main):+.2f}% win={sum(1 for t in in_main if t['ret'] > +1.0)/len(in_main)*100:.0f}%")
    if off_main:
        print(f"  off-mainline:  n={len(off_main)} avg={statistics.mean(t['ret'] for t in off_main):+.2f}% win={sum(1 for t in off_main if t['ret'] > +1.0)/len(off_main)*100:.0f}%")

    # --- big-cap effect -----------------------------------------------------
    section("Big-cap vs small-cap")
    big = [t for t in trades if t["is_big_cap"]]
    small = [t for t in trades if not t["is_big_cap"]]
    if big:
        print(f"  big-cap:   n={len(big)} avg={statistics.mean(t['ret'] for t in big):+.2f}% win={sum(1 for t in big if t['ret'] > +1.0)/len(big)*100:.0f}%")
    if small:
        print(f"  small-cap: n={len(small)} avg={statistics.mean(t['ret'] for t in small):+.2f}% win={sum(1 for t in small if t['ret'] > +1.0)/len(small)*100:.0f}%")

    # --- state-axis correlation with returns --------------------------------
    section("State-axis correlation: do specific axis values predict returns?")
    for axis in ["reward", "risk", "continuity", "duan_ban_recovery"]:
        rows = [(getattr(t["state"], axis), t["ret"]) for t in trades if t["state"] is not None]
        rows.sort()
        n = len(rows)
        if n < 20:
            continue
        # Tertile means
        third = n // 3
        low = [r for _, r in rows[:third]]
        mid = [r for _, r in rows[third:2*third]]
        high = [r for _, r in rows[2*third:]]
        print(f"  {axis:<22} low avg={statistics.mean(low):+.2f}% (n={len(low)})  mid={statistics.mean(mid):+.2f}% (n={len(mid)})  high={statistics.mean(high):+.2f}% (n={len(high)})")

    # --- monthly performance -----------------------------------------------
    section("Per-month performance pattern")
    by_month: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_month[t["date"][:7]].append(t["ret"])
    for m in sorted(by_month):
        rets = by_month[m]
        wins = sum(1 for r in rets if r > +1.0)
        avg = statistics.mean(rets)
        print(f"  {m}: n={len(rets):>3} avg={avg:>+6.2f}% wins={wins:>3} ({wins/len(rets)*100:.0f}%) sum={sum(rets):>+7.1f}%")

    # --- Asymmetric setups --------------------------------------------------
    section("Mode × condition combos with skewed (≥3:1) win/loss")
    print("  combo                                          n  win%   avg     median")
    combos = [
        ("xcjw≥400", lambda t: t["xcjw"] >= 400),
        ("xcjw<200", lambda t: t["xcjw"] < 200 and t["xcjw"] > 0),
        ("jssb≥300", lambda t: t["jssb"] >= 300),
        ("open_pct<=0", lambda t: t["open_pct"] <= 0),
        ("open_pct in [0,2)", lambda t: 0 < t["open_pct"] < 2),
        ("open_pct≥4", lambda t: t["open_pct"] >= 4),
        ("in_direction & open<2", lambda t: t["direction"] and t["open_pct"] < 2),
        ("off_mainline", lambda t: not t["is_main_line"]),
        ("state.risk≥0.6", lambda t: t["state"] and t["state"].risk >= 0.6),
        ("state.risk<0.4", lambda t: t["state"] and t["state"].risk < 0.4),
        ("state.reward≥0.6", lambda t: t["state"] and t["state"].reward >= 0.6),
        ("state.continuity≥0.6", lambda t: t["state"] and t["state"].continuity >= 0.6),
    ]
    for label, fn in combos:
        sub = [t for t in trades if fn(t)]
        if len(sub) < 5:
            continue
        wins = sum(1 for t in sub if t["ret"] > +1.0)
        loses = sum(1 for t in sub if t["ret"] < -1.0)
        avg = statistics.mean(t["ret"] for t in sub)
        med = statistics.median(t["ret"] for t in sub)
        wpct = wins / len(sub) * 100
        flag = ""
        if wins >= 3 * max(loses, 1):
            flag = " ⭐ reinforce"
        elif loses >= 3 * max(wins, 1):
            flag = " ⚠ anti-pattern"
        print(f"  {label:<42} {len(sub):>4} {wpct:>4.0f}%  {avg:>+6.2f}%  {med:>+6.2f}%{flag}")


if __name__ == "__main__":
    main()
