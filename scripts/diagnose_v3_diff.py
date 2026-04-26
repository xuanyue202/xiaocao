"""For every signal where v2 and v3 disagree on active/shadow, dump:
  - mode, code, returnPct
  - state for that day (reward, risk, continuity, duan_ban_recovery)
  - fitness computed by v3's ModeProfile
  - which Tier rule v3 fired
  - whether the trade was a winner/loser

This tells us if v3's pessimism was JUSTIFIED (those trades were losers)
or WRONG (those trades were winners).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache
from xiaocao.strategy.regime import MODE_PROFILE, mode_fitness
from xiaocao.strategy.state import build_state_index, get_state


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    v2 = load(ROOT / "output" / "xiaocao_8mo_v2_adaptive" / "trades.csv")
    v3 = load(ROOT / "output" / "xiaocao_8mo_v3_adaptive" / "trades.csv")

    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    state_index = build_state_index(cache)

    # Pair by (buyDate, mode, code)
    v2_by = {(r["buyDate"], r["mode"], r["code"]): r for r in v2}
    v3_by = {(r["buyDate"], r["mode"], r["code"]): r for r in v3}

    # Find disagreements
    diffs = []
    for k, r2 in v2_by.items():
        r3 = v3_by.get(k)
        if r3 is None:
            continue
        a2 = r2.get("adaptiveActive", "")
        a3 = r3.get("adaptiveActive", "")
        if a2 != a3:
            diffs.append((k, r2, r3))

    print(f"Diff count: {len(diffs)}")
    print(f"\n{'date':<12} {'mode':<22} {'code':<14} {'ret%':>7}  {'v2':<7} {'v3':<7} {'state (R,Risk,Cont)':<22} {'fitness':>7} {'v3 reason':<60}")
    print("-" * 160)

    correct_calls_by_v3 = 0  # v3 shadowed a loser
    wrong_calls_by_v3 = 0    # v3 shadowed a winner
    total_v3_extra_shadows = 0
    total_ret_diff = 0.0
    by_mode_diff: dict[str, list[float]] = {}

    for k, r2, r3 in diffs:
        date, mode, code = k
        ret = float(r3["returnPct"])
        state = state_index.get(date)
        if state is None:
            print(f"{date:<12} {mode:<22} {code:<14} {ret:>+6.2f}%  (no state)")
            continue
        f = mode_fitness(mode, state)
        f_str = f"{f:>+5.2f}" if isinstance(f, (int, float)) and f != float("-inf") else "FAIL"
        # v3 went stricter (shadow when v2 active)?
        v3_stricter = (r2.get("adaptiveActive") == "True" and r3.get("adaptiveActive") == "False")
        if v3_stricter:
            total_v3_extra_shadows += 1
            total_ret_diff += ret  # what v2 captured but v3 missed
            by_mode_diff.setdefault(mode, []).append(ret)
            if ret > 0:
                wrong_calls_by_v3 += 1
            else:
                correct_calls_by_v3 += 1

        v3_reason = (r3.get("adaptiveReason") or "").split(";")[0][:60]
        print(f"{date:<12} {mode:<22} {code:<14} {ret:>+6.2f}%  "
              f"{r2.get('adaptiveActive', ''):<7} {r3.get('adaptiveActive', ''):<7} "
              f"({state.reward:.2f},{state.risk:.2f},{state.continuity:.2f})    "
              f"{f_str:>7} {v3_reason:<60}")

    print(f"\nv3 shadowed {total_v3_extra_shadows} extra trades (vs v2)")
    print(f"  correct (those would have been losers):  {correct_calls_by_v3}")
    print(f"  WRONG (those were actually winners):     {wrong_calls_by_v3}")
    print(f"  net P&L missed by v3: {total_ret_diff:+.2f}% (negative = v3 was right to shadow)")

    print(f"\nBy mode (v3 over-shadowed):")
    for mode, rets in sorted(by_mode_diff.items(), key=lambda t: -sum(t[1])):
        avg = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        print(f"  {mode:<22} n={len(rets)} avg={avg:+5.2f}% wins={wins}/{len(rets)} sum={sum(rets):+.1f}%")


if __name__ == "__main__":
    main()
