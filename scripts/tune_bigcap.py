"""Test bigcap filter — Category H.

Universe is already tagged with `is_big_cap` (from enrich=True default).
Test: drop bigcap signals OR keep only bigcap. Both directions tested.

Hypothesis from data: bigcap_summary in 39-day window shows
big_cap +0.59% vs small_cap +2.33% — small wins. Worth checking on the
4-month TRAIN whether this is robust.
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
    print(f"universe: {len(universe)} signals")

    # Sanity: how many tagged bigcap?
    tagged = sum(1 for s in universe if s.raw.get("is_big_cap") is not None)
    bigcap = sum(1 for s in universe if s.raw.get("is_big_cap") is True)
    print(f"  signals with is_big_cap tag: {tagged}/{len(universe)} ({100*tagged/len(universe):.0f}%)")
    print(f"  signals tagged big_cap: {bigcap}/{tagged} ({100*bigcap/tagged:.0f}%)" if tagged else "  no tagged signals")

    # Stats on bigcap vs small-cap split (TRAIN)
    train_big = [s.return_pct for s in universe if s.in_train() and s.raw.get("is_big_cap") is True]
    train_small = [s.return_pct for s in universe if s.in_train() and s.raw.get("is_big_cap") is False]
    test_big = [s.return_pct for s in universe if s.in_test() and s.raw.get("is_big_cap") is True]
    test_small = [s.return_pct for s in universe if s.in_test() and s.raw.get("is_big_cap") is False]
    print(f"\n=== bigcap split ===")
    print(f"  TRAIN big_cap:  {stats(train_big).fmt()}")
    print(f"  TRAIN small_cap:{stats(train_small).fmt()}")
    print(f"  TEST  big_cap:  {stats(test_big).fmt()}")
    print(f"  TEST  small_cap:{stats(test_small).fmt()}")

    # Baseline
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (validated, no bigcap filter) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    # Variant 1: exclude bigcap
    def gate_no_bigcap(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= 6.0:
            return False
        if sig.raw.get("is_big_cap") is True:
            return False
        return True

    ta, _, va, _ = evaluate(universe, gate_no_bigcap)
    print(f"\n=== variant: validated + EXCLUDE bigcap ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")

    # Variant 2: only bigcap
    def gate_only_bigcap(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= 6.0:
            return False
        if sig.raw.get("is_big_cap") is not True:
            return False
        return True

    ta, _, va, _ = evaluate(universe, gate_only_bigcap)
    print(f"\n=== variant: validated + ONLY bigcap ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")


if __name__ == "__main__":
    main()
