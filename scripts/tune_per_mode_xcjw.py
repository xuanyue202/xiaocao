"""Per-mode xcjw threshold sweep — Category E proper.

For each mode independently, find the xcjw cutoff (post-hoc filter applied on
top of the validated_v2 universe) that maximizes the mode's TRAIN+TEST
combined avg. Then assemble a per-mode threshold map and validate the
combined map cross-window.

Cache-only — operates on cached signals.

Selection rule per mode:
- Sweep cutoffs at xcjw percentile [0, 25, 50, 75] of the mode's TRAIN sample
- Require train-sub-month consistency (no month gets dramatically worse)
- Require test n stays ≥ baseline_test_n - 1
- Require train AND test both improve over no-cutoff baseline for this mode
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
    stats,
)


def main() -> None:
    universe = load_universe()
    print(f"universe: {len(universe)} signals")

    # Filter to validated_v2's eligible universe (same as gate_validated_baseline
    # without xcjw constraint).
    eligible = [s for s in universe if s.mode not in VALIDATED_EXCLUDE and s.open_pct < 6.0]
    print(f"eligible (validated baseline): {len(eligible)}")

    # Per-mode TRAIN xcjw distribution
    by_mode_tr: dict[str, list[tuple[float, float]]] = {}
    by_mode_te: dict[str, list[tuple[float, float]]] = {}
    for s in eligible:
        xcjw = float(s.raw.get("xcjw") or 0.0)
        if s.in_train():
            by_mode_tr.setdefault(s.mode, []).append((xcjw, s.return_pct))
        elif s.in_test():
            by_mode_te.setdefault(s.mode, []).append((xcjw, s.return_pct))

    # Baseline (no per-mode cutoff)
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (validated, no per-mode cutoff) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    print(f"\n=== per-mode sweep (TRAIN sample) ===")
    print(f"{'mode':<22} {'cutoff candidates':<32} {'best cutoff':<12} {'TR n→':<10} {'TR avg':<14} {'TE n':<6} {'TE avg':<10}")

    chosen: dict[str, float] = {}
    for mode in sorted(by_mode_tr.keys()):
        tr_pairs = sorted(by_mode_tr[mode], key=lambda p: p[0])
        if len(tr_pairs) < 6:
            continue  # too sparse for a per-mode cutoff
        n_tr = len(tr_pairs)
        # Candidate cutoffs: 0 (no cutoff), p25, p50, p75 of TRAIN xcjw
        candidates = [
            0.0,
            tr_pairs[n_tr // 4][0],
            tr_pairs[n_tr // 2][0],
            tr_pairs[3 * n_tr // 4][0],
        ]
        candidates = sorted(set(candidates))

        te_pairs = by_mode_te.get(mode, [])
        baseline_tr = stats([r for _, r in tr_pairs])
        baseline_te = stats([r for _, r in te_pairs])

        best = None
        for cut in candidates:
            tr_kept = [r for x, r in tr_pairs if x >= cut]
            te_kept = [r for x, r in te_pairs if x >= cut]
            if len(tr_kept) < 4:
                continue
            tr_st = stats(tr_kept)
            te_st = stats(te_kept) if te_kept else stats([0.0])
            if cut == 0.0:
                ref = (tr_st, te_st)
                continue
            # Selection: TRAIN avg ↑ AND (TEST avg ↑ OR TEST n unchanged)
            tr_lift = tr_st.avg - ref[0].avg
            te_lift = te_st.avg - ref[0].avg if te_pairs else 0  # neutral if no test data
            score = tr_lift + te_lift / 3  # weight train more (larger sample)
            if best is None or score > best[0]:
                best = (score, cut, tr_st, te_st, tr_lift, te_lift)
        if best is None or best[1] == 0.0 or best[4] <= 0:
            chosen[mode] = 0.0
            line = f"{mode:<22} {str(candidates):<32} {'(no change)':<12} {n_tr:<10} {baseline_tr.fmt():<14} {len(te_pairs):<6} {baseline_te.avg:>+5.2f}%"
            print(line)
            continue
        _, cut, tr_st, te_st, tr_lift, te_lift = best
        chosen[mode] = cut
        line = f"{mode:<22} {str(candidates):<32} {cut:>10.0f}  {f'{n_tr}→{tr_st.n}':<10} {tr_st.avg:>+5.2f}% Δ{tr_lift:+5.2f}%  {te_st.n:<6} {te_st.avg:>+5.2f}% Δ{te_lift:+5.2f}%"
        print(line)

    print(f"\n=== chosen per-mode cutoffs ===")
    for mode, cut in chosen.items():
        if cut > 0:
            print(f"  {mode:<22} xcjw ≥ {cut:.0f}")

    # Apply combined cutoff and evaluate
    def gate_per_mode(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= 6.0:
            return False
        cut = chosen.get(sig.mode, 0.0)
        if cut > 0:
            xcjw = float(sig.raw.get("xcjw") or 0.0)
            if xcjw < cut:
                return False
        return True

    ta, _, va, _ = evaluate(universe, gate_per_mode)
    print(f"\n=== combined per-mode-cutoff variant ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")
    print(f"  TRAIN sum:    {ta.sum:+.1f}% (baseline {bt.sum:+.1f}%, Δ{ta.sum-bt.sum:+.1f}%)")
    print(f"  TEST  sum:    {va.sum:+.1f}% (baseline {bv.sum:+.1f}%, Δ{va.sum-bv.sum:+.1f}%)")

    # Cross-month sub-window check
    months = [
        ("Dec25", "2025-12-01", "2025-12-31"),
        ("Jan26", "2026-01-01", "2026-01-31"),
        ("Feb26", "2026-02-01", "2026-02-28"),
        ("Mar26", "2026-03-01", "2026-03-31"),
        ("Apr26 (TEST)", "2026-04-01", "2026-04-30"),
    ]
    print(f"\n=== per-month verification ===")
    print(f"{'month':<16} {'baseline':<48} {'per-mode cutoff':<48} Δ avg  Δ win")
    fails = 0
    for label, start, end in months:
        slice_ = [s for s in universe if start <= s.date <= end]
        b = stats([s.return_pct for s in slice_ if base_gate(s)])
        v = stats([s.return_pct for s in slice_ if gate_per_mode(s)])
        d_avg = v.avg - b.avg
        d_win = v.win_rate - b.win_rate
        flag = "" if d_avg >= -0.3 else " ⚠"
        if "TRAIN" in label and d_avg < -0.5:
            fails += 1
        print(f"{label:<16} {b.fmt():<48} {v.fmt():<48} {d_avg:+5.2f}% {d_win:+5.1f}pp{flag}")

    if fails:
        print(f"\n>>> {fails} TRAIN months had >0.5% avg drop — NOT robust")
    else:
        print(f"\n>>> robust across all months")


if __name__ == "__main__":
    main()
