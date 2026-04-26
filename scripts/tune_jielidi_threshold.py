"""Test ONLY raising 接力低弱转1's xcjw threshold (the one mode with clearest
xcjw correlation). Keep everything else as-is.

接力低弱转1 TRAIN xcjw distribution: low half (≤ 304) avg +1.46%, high half +5.03%.
At cutoff 410 (75th percentile), TRAIN n drops 32→7 with avg +8.47% (Δ +5.70%).

Cache-only.
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
    stats,
)


def main() -> None:
    universe = load_universe()
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"=== baseline (validated) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    months = [
        ("Dec25", "2025-12-01", "2025-12-31"),
        ("Jan26", "2026-01-01", "2026-01-31"),
        ("Feb26", "2026-02-01", "2026-02-28"),
        ("Mar26", "2026-03-01", "2026-03-31"),
        ("Apr26 (TEST)", "2026-04-01", "2026-04-30"),
    ]

    # Try multiple cutoffs for 接力低弱转1
    print(f"\n=== sweep 接力低弱转1 xcjw cutoff ===")
    for cutoff in [0, 300, 350, 400, 410, 450, 500, 600]:
        def gate(sig: SignalRecord, c=cutoff) -> bool:
            if sig.mode in VALIDATED_EXCLUDE:
                return False
            if sig.open_pct >= 6.0:
                return False
            if sig.mode == "接力低弱转1":
                if float(sig.raw.get("xcjw") or 0.0) < c:
                    return False
            return True

        ta, _, va, _ = evaluate(universe, gate)
        delta_tr = ta.avg - bt.avg
        delta_te = va.avg - bv.avg
        delta_n_tr = ta.n - bt.n
        delta_n_te = va.n - bv.n
        # Per-month check
        month_lifts = []
        for label, start, end in months:
            slice_ = [s for s in universe if start <= s.date <= end]
            b = stats([s.return_pct for s in slice_ if base_gate(s)])
            v = stats([s.return_pct for s in slice_ if gate(s)])
            month_lifts.append((label, v.avg - b.avg, v.win_rate - b.win_rate, v.n - b.n))

        print(f"\n  cutoff={cutoff}: TRAIN n={ta.n} ({delta_n_tr:+d}) avg={ta.avg:+.2f}% (Δ{delta_tr:+.2f}%) win={ta.win_rate:.1f}%  "
              f"TEST n={va.n} ({delta_n_te:+d}) avg={va.avg:+.2f}% (Δ{delta_te:+.2f}%) win={va.win_rate:.1f}%")
        print(f"    sum TRAIN {ta.sum:+.1f}% (Δ{ta.sum-bt.sum:+.1f}%)  TEST {va.sum:+.1f}% (Δ{va.sum-bv.sum:+.1f}%)")
        for label, d_avg, d_win, d_n in month_lifts:
            print(f"    {label:<14} Δavg={d_avg:+5.2f}% Δwin={d_win:+5.1f}pp Δn={d_n:+d}")


if __name__ == "__main__":
    main()
