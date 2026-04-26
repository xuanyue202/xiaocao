"""Tune the open-pct cap (Category C).

小草 0419: "最喜欢 0-1 个点，2 个点勉强接受，更高就不舒服" — i.e. the open-pct
gate is the single most explicit nominal-level rule in the entire framework.

We test: per-mode caps (接力/弱转 → 3, 低吸 → 5) AND a global cap.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from replay_lib import (  # noqa: E402
    SignalRecord,
    VALIDATED_EXCLUDE,
    evaluate,
    gate_validated_baseline,
    load_universe,
)


def gate_global_cap(cap: float):
    def gate(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        return sig.open_pct < cap
    return gate


def gate_per_mode_cap(caps_by_class: dict[str, float], default_cap: float):
    """`caps_by_class` keys: 'jieli' (接力 / 弱转), 'dixi' (低吸 / 断 / 孕), 'direction' (方向内)."""

    def classify(mode: str) -> str:
        if "接力" in mode or "弱转" in mode or "连板" in mode:
            return "jieli"
        if "方向" in mode:
            return "direction"
        if "低吸" in mode or "断" in mode or "孕" in mode or "N字" in mode:
            return "dixi"
        return "other"

    def gate(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        cls = classify(sig.mode)
        cap = caps_by_class.get(cls, default_cap)
        return sig.open_pct < cap

    return gate


def report(label: str, gate, universe, baseline_train_avg, baseline_test_avg):
    ta, ts, va, vs = evaluate(universe, gate)
    delta_t = ta.avg - baseline_train_avg
    delta_v = va.avg - baseline_test_avg
    print(f"\n--- {label} ---")
    print(f"  TRAIN active: {ta.fmt()}  Δ={delta_t:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={delta_v:+.2f}%")
    return ta, va


def main() -> None:
    universe = load_universe()
    print(f"universe: {len(universe)} signals")

    # Histogram of open_pct in the universe
    print("\n=== open_pct histogram (universe) ===")
    bins = [(-100, 0), (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 100)]
    train = [s for s in universe if s.in_train()]
    test = [s for s in universe if s.in_test()]
    print(f"  {'bin':<10} {'train_n':>8} {'train_avg':>11} {'train_win':>11}   {'test_n':>8} {'test_avg':>11} {'test_win':>11}")
    for lo, hi in bins:
        tr = [s.return_pct for s in train if lo <= s.open_pct < hi]
        te = [s.return_pct for s in test if lo <= s.open_pct < hi]
        tr_avg = sum(tr)/len(tr) if tr else 0
        tr_win = sum(1 for v in tr if v > 0)/len(tr)*100 if tr else 0
        te_avg = sum(te)/len(te) if te else 0
        te_win = sum(1 for v in te if v > 0)/len(te)*100 if te else 0
        print(f"  [{lo:>2},{hi:>3})  {len(tr):>8} {tr_avg:>+10.2f}% {tr_win:>10.1f}%   {len(te):>8} {te_avg:>+10.2f}% {te_win:>10.1f}%")

    # Baselines
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (cap=6.0, validated profile) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    # Global caps
    print("\n=== global cap candidates ===")
    for cap in [2.0, 3.0, 4.0, 5.0, 6.0]:
        report(f"global cap={cap}", gate_global_cap(cap), universe, bt.avg, bv.avg)

    # Per-mode caps: 接力/弱转 strict, 低吸 looser, 方向 strict
    print("\n=== per-mode cap candidates ===")
    candidates = [
        # (jieli, dixi, direction, default)
        (3.0, 5.0, 4.0, 5.0),
        (2.0, 5.0, 3.0, 5.0),
        (3.0, 6.0, 4.0, 6.0),
        (2.0, 6.0, 3.0, 6.0),
        (4.0, 5.0, 4.0, 5.0),
        (3.0, 4.0, 3.0, 4.0),
    ]
    for jl, dx, dr, df in candidates:
        gate = gate_per_mode_cap({"jieli": jl, "dixi": dx, "direction": dr}, df)
        report(f"per-mode caps jl={jl}/dx={dx}/dir={dr} (other={df})", gate, universe, bt.avg, bv.avg)


if __name__ == "__main__":
    main()
