"""Find systematically bad modes on the TRAIN window.

Per 小草 0410: "昨天某模式赚钱，今天就重仓；昨天某模式亏钱，今天就不做" — anti-pattern.
But on a 4-month TRAIN window with N>=10 samples per mode, a strongly negative
avg is real signal, not result-bias.

Selection rule for adding to exclude_modes:
- TRAIN n >= 10
- TRAIN avg <= -1.0%
- (mode does NOT need to confirm on TEST — that would be peeking)

Then check: do the proposed exclusions improve TEST avg without removing too
many trades?
"""
from __future__ import annotations

import statistics
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


def main() -> None:
    universe = load_universe()
    train = [s for s in universe if s.in_train()]
    test = [s for s in universe if s.in_test()]
    print(f"universe: {len(universe)} ({len(train)} TRAIN / {len(test)} TEST)")

    # Per-mode aggregation on TRAIN
    by_mode_tr: dict[str, list[float]] = {}
    by_mode_te: dict[str, list[float]] = {}
    for s in train:
        by_mode_tr.setdefault(s.mode, []).append(s.return_pct)
    for s in test:
        by_mode_te.setdefault(s.mode, []).append(s.return_pct)

    print(f"\n=== TRAIN mode summary (sorted by avg ASC) ===")
    print(f"{'mode':<22} {'TR_n':>5} {'TR_avg':>8} {'TR_win':>7} {'TR_med':>8}  | {'TE_n':>5} {'TE_avg':>8} {'TE_win':>7}")
    rows = []
    for mode, returns in by_mode_tr.items():
        n = len(returns)
        avg = statistics.mean(returns)
        win = sum(1 for v in returns if v > 0) / n * 100
        med = statistics.median(returns)
        te = by_mode_te.get(mode, [])
        te_n = len(te)
        te_avg = statistics.mean(te) if te else 0.0
        te_win = sum(1 for v in te if v > 0)/te_n*100 if te_n else 0
        rows.append((mode, n, avg, win, med, te_n, te_avg, te_win))
    rows.sort(key=lambda r: r[2])  # by train avg
    for mode, n, avg, win, med, te_n, te_avg, te_win in rows:
        flag = " ⚠" if (n >= 10 and avg <= -1.0) else ""
        print(f"{mode:<22} {n:>5} {avg:>+7.2f}% {win:>6.1f}% {med:>+7.2f}%  | {te_n:>5} {te_avg:>+7.2f}% {te_win:>6.1f}%{flag}")

    # Candidate exclusion set: train n>=10 & train avg <= -1
    candidates = [r[0] for r in rows if r[1] >= 10 and r[2] <= -1.0]
    print(f"\n=== candidate exclusion modes (TRAIN n>=10 AND TRAIN avg <= -1.0%) ===")
    for m in candidates:
        print(f"  {m}")

    if not candidates:
        print("(none)")
        return

    # Compare: validated baseline vs validated + extended exclusions
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== validated baseline ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    extended = set(VALIDATED_EXCLUDE) | set(candidates)

    def gate_extended(sig: SignalRecord) -> bool:
        if sig.mode in extended:
            return False
        return sig.open_pct < 6.0

    et, _, ev, _ = evaluate(universe, gate_extended)
    print(f"\n=== validated + bad-mode exclusion ({sorted(extended)}) ===")
    print(f"  TRAIN active: {et.fmt()}  Δ={et.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {ev.fmt()}  Δ={ev.avg-bv.avg:+.2f}%")

    # Sanity: try each candidate INDIVIDUALLY too
    print(f"\n=== marginal effect of each candidate (added on top of validated) ===")
    for m in candidates:
        if m in VALIDATED_EXCLUDE:
            continue
        excl = set(VALIDATED_EXCLUDE) | {m}

        def gate(sig: SignalRecord, excl=excl) -> bool:
            if sig.mode in excl:
                return False
            return sig.open_pct < 6.0

        ti, _, vi, _ = evaluate(universe, gate)
        print(f"  + exclude {m}: TRAIN {ti.fmt()}  TEST {vi.fmt()}  ΔTR={ti.avg-bt.avg:+.2f}% ΔTE={vi.avg-bv.avg:+.2f}%")


if __name__ == "__main__":
    main()
