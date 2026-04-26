"""Tune rules.py thresholds (SUPER_JW / STRONG_JW / QUALIFIED_JW) — Category E.

Rules in src/xiaocao/strategy/rules.py emit signals when:
    xcjw >= mode_threshold  OR  (direction AND xcjw >= mode_threshold / 1.3)

Per-mode threshold map (current defaults):
    接力低弱转1            : SUPER_JW (300)         dir≥230.77
    接力低弱转2            : STRONG_JW (200)        dir≥153.85
    绿断低吸 / 红断低吸 / 首红断低吸 : QUALIFIED_JW (150)   dir≥115.38
    全盘低位低吸             : STRONG_JW (200)        dir≥153.85
    N字低吸                : STRONG_JW * 1.3 (260)   dir≥200
    孕线低吸                : QUALIFIED_JW * 1.3 (195) dir≥150
    方向低位低吸             : STRONG_JW (200)        dir≥153.85
    方向内绿盘低吸前3名         : QUALIFIED_JW (150)   dir≥115.38

To test (s, t, q) candidates, we re-derive each signal's pass condition with the
new constants and only keep signals that still pass. This is a TIGHTENING-only
exercise (we can't add signals that didn't pass the original constants).

Cache-only: works on output/xiaocao_5month_seed/signals_*.json + trades.csv.
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from replay_lib import (  # noqa: E402
    SignalRecord,
    VALIDATED_EXCLUDE,
    evaluate,
    gate_validated_baseline,
    load_universe,
    stats,
)


def mode_threshold(mode: str, super_jw: float, strong_jw: float, qualified_jw: float) -> float:
    """The effective `_compare_jw` threshold for a given mode."""
    if mode == "接力低弱转1":
        return super_jw
    if mode == "接力低弱转2":
        return strong_jw
    if mode in {"绿断低吸", "红断低吸", "首红断低吸", "方向内绿盘低吸前3名"}:
        return qualified_jw
    if mode in {"全盘低位低吸", "方向低位低吸"}:
        return strong_jw
    if mode == "N字低吸":
        return strong_jw * 1.3
    if mode == "孕线低吸":
        return qualified_jw * 1.3
    return qualified_jw  # fallback


def passes_xcjw(sig: SignalRecord, super_jw: float, strong_jw: float, qualified_jw: float) -> bool:
    xcjw = float(sig.raw.get("xcjw") or 0.0)
    direction = bool(sig.raw.get("direction"))
    thr = mode_threshold(sig.mode, super_jw, strong_jw, qualified_jw)
    if xcjw >= thr:
        return True
    if direction and xcjw >= thr / 1.3:
        return True
    return False


def main() -> None:
    universe = load_universe()
    print(f"universe: {len(universe)} signals")

    # Current default constants
    DEF = (300.0, 200.0, 150.0)

    # Sanity check: every signal in the universe should pass the CURRENT defaults
    failing_default = [s for s in universe if not passes_xcjw(s, *DEF)]
    print(f"  signals passing current defaults (300/200/150): "
          f"{len(universe) - len(failing_default)}/{len(universe)}")
    if failing_default:
        # If any fail, the rule may have used additional gates not captured here.
        for s in failing_default[:5]:
            print(f"    fail: {s.mode} {s.code} xcjw={s.raw.get('xcjw')} dir={s.raw.get('direction')}")

    # Per-mode xcjw distribution: see if there's a quality/score correlation
    print(f"\n=== per-mode xcjw vs return (TRAIN only) ===")
    by_mode: dict[str, list[tuple[float, float]]] = {}
    for s in universe:
        if not s.in_train():
            continue
        xcjw = float(s.raw.get("xcjw") or 0.0)
        by_mode.setdefault(s.mode, []).append((xcjw, s.return_pct))
    print(f"  {'mode':<22} {'n':>4} {'xcjw range':<18} {'avg(low half)':>14} {'avg(high half)':>15}")
    for mode, pairs in sorted(by_mode.items()):
        if len(pairs) < 4:
            continue
        pairs_sorted = sorted(pairs, key=lambda p: p[0])
        mid = len(pairs_sorted) // 2
        lo_avg = sum(r for _, r in pairs_sorted[:mid]) / mid
        hi_avg = sum(r for _, r in pairs_sorted[mid:]) / (len(pairs_sorted) - mid)
        x_lo, x_hi = pairs_sorted[0][0], pairs_sorted[-1][0]
        print(f"  {mode:<22} {len(pairs):>4} [{x_lo:>6.0f}, {x_hi:>6.0f}]  {lo_avg:>+12.2f}%   {hi_avg:>+13.2f}%")

    # Baseline
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (validated, defaults 300/200/150) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    # Grid: try tightening each constant independently
    print(f"\n=== grid: tighten each constant ===")
    grid_super = [300, 350, 400, 500]
    grid_strong = [200, 250, 300, 350]
    grid_qual = [150, 175, 200, 250]

    print(f"{'(SUPER, STRONG, QUAL)':<24} {'TRAIN':<46} {'TEST':<46} Δtr Δte")
    results = []
    for s_jw, t_jw, q_jw in product(grid_super, grid_strong, grid_qual):
        if t_jw < q_jw or s_jw < t_jw:
            continue  # keep ordering invariant
        def gate(sig: SignalRecord, S=s_jw, T=t_jw, Q=q_jw) -> bool:
            if sig.mode in VALIDATED_EXCLUDE:
                return False
            if sig.open_pct >= 6.0:
                return False
            return passes_xcjw(sig, S, T, Q)
        ta, _, va, _ = evaluate(universe, gate)
        results.append({
            "config": (s_jw, t_jw, q_jw),
            "train": ta,
            "test": va,
        })
        cfg = f"({s_jw:>3}, {t_jw:>3}, {q_jw:>3})"
        print(f"{cfg:<24} {ta.fmt():<46} {va.fmt():<46} {ta.avg-bt.avg:+5.2f}% {va.avg-bv.avg:+5.2f}%")

    # Robust subset
    print(f"\n=== robust: TRAIN avg ≥ baseline AND TEST avg ≥ baseline AND TEST n≥3 ===")
    robust = [
        r for r in results
        if r["train"].n >= 30
        and r["test"].n >= 3
        and r["train"].avg >= bt.avg
        and r["test"].avg >= bv.avg
    ]
    robust.sort(key=lambda r: r["train"].avg + r["test"].avg, reverse=True)
    print(f"  → {len(robust)} configs survive")
    for r in robust[:15]:
        s_jw, t_jw, q_jw = r["config"]
        cfg = f"({s_jw:>3}, {t_jw:>3}, {q_jw:>3})"
        print(f"  {cfg:<24} TRAIN {r['train'].fmt()}  TEST {r['test'].fmt()}")


if __name__ == "__main__":
    main()
