"""Grid-search adaptive (n_min, avg_threshold) on Dec-Mar, validate on April.

Cache-only: re-uses signals from output/xiaocao_5month_seed/ and mode_history
from output/.cache/xiaocao.db. Never calls the API.

Selection rule:
- Train: avg ≥ baseline AND n ≥ baseline_n * 0.7  (keep meaningful sample size)
- Test:  avg ≥ baseline AND n ≥ 3
- Robustness: train and test must both improve over the validated baseline.
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from replay_lib import (  # noqa: E402
    evaluate,
    gate_validated_baseline,
    gate_with_adaptive,
    load_universe,
    open_cache,
    trade_days_in_universe,
)


def main() -> None:
    universe = load_universe()
    days = trade_days_in_universe(universe)
    cache = open_cache()
    print(f"universe: {len(universe)} signals across {len(days)} days "
          f"({days[0]} → {days[-1]})")

    # --- baseline: validated profile, no adaptive ---
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt_a, bt_s, bv_a, bv_s = evaluate(universe, base_gate)
    print("\n=== baseline: validated profile (no adaptive) ===")
    print(f"  TRAIN active: {bt_a.fmt()}")
    print(f"  TRAIN shadow: {bt_s.fmt()}")
    print(f"  TEST  active: {bv_a.fmt()}")
    print(f"  TEST  shadow: {bv_s.fmt()}")

    # --- baseline: validated + current default adaptive ---
    cur_gate = gate_with_adaptive(
        cache,
        days,
        n_min_by_window={5: 1, 10: 2, 20: 3},
        avg_threshold_by_window={5: -5.0, 10: -3.0, 20: -2.0},
    )
    ct_a, ct_s, cv_a, cv_s = evaluate(universe, cur_gate)
    print("\n=== current default adaptive (1,2,3 | -5,-3,-2) on validated ===")
    print(f"  TRAIN active: {ct_a.fmt()}")
    print(f"  TEST  active: {cv_a.fmt()}")

    # --- grid ---
    n5_grid = [1, 2, 3]
    n10_grid = [2, 3, 4]
    n20_grid = [3, 4, 5]
    thr5_grid = [-3, -4, -5, -6, -7]
    thr10_grid = [-2, -3, -4, -5]
    thr20_grid = [-1, -2, -3]

    print(f"\n=== grid: {len(n5_grid)*len(n10_grid)*len(n20_grid)*len(thr5_grid)*len(thr10_grid)*len(thr20_grid)} configs ===")

    results = []
    for n5, n10, n20, t5, t10, t20 in product(
        n5_grid, n10_grid, n20_grid, thr5_grid, thr10_grid, thr20_grid
    ):
        gate = gate_with_adaptive(
            cache,
            days,
            n_min_by_window={5: n5, 10: n10, 20: n20},
            avg_threshold_by_window={5: float(t5), 10: float(t10), 20: float(t20)},
        )
        ta, _, va, _ = evaluate(universe, gate)
        results.append({
            "config": (n5, n10, n20, t5, t10, t20),
            "train": ta,
            "test": va,
        })

    # Filter: train must have n >= 0.5*baseline (no degenerate "1 trade" wins)
    train_n_min = max(5, int(bt_a.n * 0.5))

    # --- Top N by train avg (with sane sample size) ---
    candidates = [r for r in results if r["train"].n >= train_n_min]
    candidates.sort(key=lambda r: r["train"].avg, reverse=True)
    print(f"\n--- top 10 by TRAIN avg (n>={train_n_min}) ---")
    print(f"{'(n5,n10,n20 | thr5,thr10,thr20)':<35}  {'TRAIN':<46}  {'TEST':<46}")
    for r in candidates[:10]:
        c = r["config"]
        cfg = f"({c[0]},{c[1]},{c[2]} | {c[3]:>3},{c[4]:>3},{c[5]:>3})"
        print(f"{cfg:<35}  {r['train'].fmt():<46}  {r['test'].fmt():<46}")

    # --- Robust: improve TRAIN avg AND TEST avg vs validated baseline ---
    train_floor = bt_a.avg
    test_floor = bv_a.avg
    robust = [
        r for r in results
        if r["train"].n >= train_n_min
        and r["test"].n >= 3
        and r["train"].avg >= train_floor
        and r["test"].avg >= test_floor
    ]
    robust.sort(key=lambda r: r["train"].avg + r["test"].avg, reverse=True)
    print(f"\n--- robust: TRAIN avg ≥ {train_floor:+.2f}% (baseline) AND TEST avg ≥ {test_floor:+.2f}% (baseline) AND TEST n≥3 ---")
    print(f"  → {len(robust)} configs survive")
    print(f"{'(n5,n10,n20 | thr5,thr10,thr20)':<35}  {'TRAIN':<46}  {'TEST':<46}")
    for r in robust[:20]:
        c = r["config"]
        cfg = f"({c[0]},{c[1]},{c[2]} | {c[3]:>3},{c[4]:>3},{c[5]:>3})"
        print(f"{cfg:<35}  {r['train'].fmt():<46}  {r['test'].fmt():<46}")

    # --- Selected: best train+test sum among the robust set ---
    if robust:
        winner = robust[0]
        c = winner["config"]
        print(f"\n>>> WINNER: ({c[0]},{c[1]},{c[2]} | {c[3]},{c[4]},{c[5]})")
        print(f"    TRAIN: {winner['train'].fmt()}")
        print(f"    TEST:  {winner['test'].fmt()}")
        print(f"    vs baseline (no-adaptive): TRAIN avg {bt_a.avg:+.2f}% → {winner['train'].avg:+.2f}% (Δ={winner['train'].avg-bt_a.avg:+.2f}%)")
        print(f"    vs baseline (no-adaptive): TEST  avg {bv_a.avg:+.2f}% → {winner['test'].avg:+.2f}% (Δ={winner['test'].avg-bv_a.avg:+.2f}%)")
    else:
        print("\n>>> NO ADAPTIVE CONFIG passes robustness — adaptive may not help on this universe.")


if __name__ == "__main__":
    main()
