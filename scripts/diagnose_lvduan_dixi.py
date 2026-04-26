"""Within-mode discriminator search for 绿断低吸.

Goal: find what distinguishes winners (ret > +1%) from losers (ret < -1%) within
绿断低吸 trades on TRAIN. Tests features:
  - cjs (mode score): Q1/Q2/Q3/Q4
  - xcjw, jsjl, jssb (other scores)
  - openPctChange
  - direction (in-direction / off)
  - is_big_cap
  - state vector axes (reward, risk, continuity, DBR)
  - day-of-week
  - month

If a clear discriminator with n >= 10 in each side emerges → consider per-mode rule.
If everything looks uniform → confirm adaptive is doing the right thing.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache
from xiaocao.strategy.state import build_state_index

TARGET_MODE = "绿断低吸"
TRAIN_START = "2025-09-01"
TRAIN_END = "2026-03-31"

SIGNAL_DIR = ROOT / "output" / "xiaocao_8mo_v3_adaptive"


def load_target_trades() -> list[dict]:
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    state_index = build_state_index(cache)

    with (SIGNAL_DIR / "trades.csv").open(encoding="utf-8-sig") as f:
        trades = [r for r in csv.DictReader(f) if r["mode"] == TARGET_MODE
                  and TRAIN_START <= r["buyDate"] <= TRAIN_END]

    # Join signals to recover state context + scores
    sigs_by_key: dict[tuple[str, str], dict] = {}
    for sf in sorted(SIGNAL_DIR.glob("signals_*.json")):
        date = sf.stem.replace("signals_", "")
        if not (TRAIN_START <= date <= TRAIN_END):
            continue
        for s in json.loads(sf.read_text(encoding="utf-8")):
            if s.get("mode") == TARGET_MODE:
                sigs_by_key[(date, str(s.get("code", "")))] = s

    enriched = []
    for t in trades:
        sig = sigs_by_key.get((t["buyDate"], t["code"]), {})
        state = state_index.get(t["buyDate"])
        try:
            ret = float(t["returnPct"])
        except (ValueError, KeyError):
            continue
        # Day of week for Chinese A-share market
        try:
            dow = _date.fromisoformat(t["buyDate"]).weekday()  # Mon=0
        except ValueError:
            dow = -1
        enriched.append({
            "date": t["buyDate"],
            "code": t["code"],
            "ret": ret,
            "open_pct": float(t.get("openPctChange") or 0.0),
            "xcjw": float(sig.get("xcjw") or 0.0),
            "cjs": float(sig.get("cjs") or 0.0),
            "jsjl": float(sig.get("jsjl") or 0.0),
            "jssb": float(sig.get("jssb") or 0.0),
            "direction": bool(sig.get("direction", False)),
            "is_big_cap": bool(sig.get("is_big_cap", False)),
            "is_main_line": bool(sig.get("is_main_line", False)),
            "state": state,
            "dow": dow,
            "month": t["buyDate"][:7],
        })
    return enriched


def fmt_split(label: str, vals: list[float]) -> str:
    if not vals:
        return f"  {label:<30} n=0"
    n = len(vals)
    avg = statistics.mean(vals)
    wins = sum(1 for v in vals if v > 1)
    return f"  {label:<30} n={n:>2} avg={avg:>+6.2f}% win={wins/n*100:>4.0f}% sum={sum(vals):>+6.1f}%"


def main():
    trades = load_target_trades()
    print(f"\n{TARGET_MODE} TRAIN trades: {len(trades)}")
    if len(trades) < 10:
        print("Too few — analysis not meaningful")
        return

    rets = [t["ret"] for t in trades]
    overall_avg = statistics.mean(rets)
    overall_win = sum(1 for r in rets if r > 1) / len(rets) * 100
    print(f"Overall: avg={overall_avg:+.2f}% win={overall_win:.0f}%")

    print("\n--- Per-trade dump (sorted by ret) ---")
    print(f"{'date':<12} {'code':<14} {'ret':>7} {'open':>6} {'cjs':>5} {'xcjw':>5} {'dir':>4} {'main':>5} {'big':>4} state")
    for t in sorted(trades, key=lambda x: x["ret"]):
        s = t["state"]
        st = f"R={s.reward:.2f} Risk={s.risk:.2f} Cont={s.continuity:.2f} DBR={s.duan_ban_recovery:.2f}" if s else ""
        print(f"{t['date']:<12} {t['code']:<14} {t['ret']:>+6.2f}% {t['open_pct']:>+5.1f}% "
              f"{t['cjs']:>5.0f} {t['xcjw']:>5.0f} {('dir' if t['direction'] else '-'):>4} "
              f"{('main' if t['is_main_line'] else '-'):>5} {('big' if t['is_big_cap'] else '-'):>4} {st}")

    # Discriminators
    def split_on(name, fn, threshold=None):
        if threshold is None:
            true_grp = [t for t in trades if fn(t)]
            false_grp = [t for t in trades if not fn(t)]
            print(f"\n{name}:")
            print(fmt_split(f"  TRUE", [t["ret"] for t in true_grp]))
            print(fmt_split(f"  FALSE", [t["ret"] for t in false_grp]))
        else:
            high = [t for t in trades if fn(t) >= threshold]
            low = [t for t in trades if fn(t) < threshold]
            print(f"\n{name} (split at {threshold}):")
            print(fmt_split(f"  >={threshold}", [t["ret"] for t in high]))
            print(fmt_split(f"  <{threshold}", [t["ret"] for t in low]))

    print("\n=== Discriminator hunt ===")
    split_on("direction support", lambda t: t["direction"])
    split_on("is_main_line (off=False)", lambda t: t["is_main_line"])
    split_on("is_big_cap", lambda t: t["is_big_cap"])
    split_on("xcjw split @200", lambda t: t["xcjw"], 200)
    split_on("xcjw split @300", lambda t: t["xcjw"], 300)
    split_on("xcjw split @500", lambda t: t["xcjw"], 500)
    split_on("cjs split @22 (drops Q1)", lambda t: t["cjs"], 22)
    split_on("cjs split @100", lambda t: t["cjs"], 100)
    split_on("open_pct < -2 (deep low open)", lambda t: t["open_pct"] < -2)
    split_on("open_pct < 0 (any low open)", lambda t: t["open_pct"] < 0)
    split_on("state.continuity >= 0.5", lambda t: t["state"] and t["state"].continuity >= 0.5)
    split_on("state.risk < 0.4 (oversold)", lambda t: t["state"] and t["state"].risk < 0.4)
    split_on("state.duan_ban_recovery >= 0.55", lambda t: t["state"] and t["state"].duan_ban_recovery >= 0.55)

    # By month
    print("\n=== By month ===")
    by_m = defaultdict(list)
    for t in trades:
        by_m[t["month"]].append(t["ret"])
    for m in sorted(by_m):
        print(fmt_split(m, by_m[m]))


if __name__ == "__main__":
    main()
