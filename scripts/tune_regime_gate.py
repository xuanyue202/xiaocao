"""Test regime-gating using the proxy regime — Category D.

Reads `output/proxy_regime.json` (built by build_proxy_regime.py) and tests
whether dropping signals in adverse regimes (bear / divergence) on top of
validated_v2 improves train+test outcomes.

Hypothesis (from 0410 / 0415):
  bear  → skip everything, especially 接力/弱转 modes
  divergence → only do 低吸 (passive) modes
  trend / bull → all modes OK
  neutral → all modes OK

Cache-only.
"""
from __future__ import annotations

import json
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


def load_regime() -> dict[str, str]:
    raw = json.loads((ROOT / "output" / "proxy_regime.json").read_text(encoding="utf-8"))
    return {d: v.get("regime", "unknown") for d, v in raw.items()}


# Per-regime mode allow set
ALLOW = {
    "bull": "ALL",
    "trend": "ALL",
    "neutral": "ALL",
    "divergence": {  # only conservative 低吸
        "绿断低吸", "红断低吸", "首红断低吸", "孕线低吸", "N字低吸",
        "全盘低位低吸", "方向低位低吸",
    },
    "bear": set(),    # skip everything
    "unknown": "ALL", # fallback
}


def gate_regime(regime_by_date: dict[str, str], allow_map=ALLOW):
    def gate(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= 6.0:
            return False
        regime = regime_by_date.get(sig.date, "unknown")
        allowed = allow_map.get(regime, "ALL")
        if allowed == "ALL":
            return True
        return sig.mode in allowed
    return gate


def main() -> None:
    universe = load_universe()
    regime_by_date = load_regime()
    print(f"universe: {len(universe)} signals")

    # Distribution of signals by regime
    print("\n=== signals per regime ===")
    by_regime: dict[str, list[float]] = {}
    by_regime_train: dict[str, list[float]] = {}
    by_regime_test: dict[str, list[float]] = {}
    for s in universe:
        r = regime_by_date.get(s.date, "unknown")
        by_regime.setdefault(r, []).append(s.return_pct)
        if s.in_train():
            by_regime_train.setdefault(r, []).append(s.return_pct)
        if s.in_test():
            by_regime_test.setdefault(r, []).append(s.return_pct)
    print(f"  {'regime':<14} {'all n / avg':<22} {'train n / avg':<22} {'test n / avg':<22}")
    for r in ["bull", "trend", "neutral", "divergence", "bear", "unknown"]:
        all_v = by_regime.get(r, [])
        tr = by_regime_train.get(r, [])
        te = by_regime_test.get(r, [])
        all_str = f"n={len(all_v):>3} avg={sum(all_v)/len(all_v):+5.2f}%" if all_v else "n=  0"
        tr_str = f"n={len(tr):>3} avg={sum(tr)/len(tr):+5.2f}%" if tr else "n=  0"
        te_str = f"n={len(te):>3} avg={sum(te)/len(te):+5.2f}%" if te else "n=  0"
        print(f"  {r:<14} {all_str:<22} {tr_str:<22} {te_str:<22}")

    # Baseline: validated_v2 minus mainline (we don't have mainline data here)
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (validated, no regime gate) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    # Variant 1: full regime gate (drop bear, restrict divergence)
    gate = gate_regime(regime_by_date, ALLOW)
    ta, _, va, _ = evaluate(universe, gate)
    print(f"\n=== variant: full regime gate (drop bear, restrict divergence to dixi-only) ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")

    # Variant 2: drop bear only
    allow_bear_only = {**ALLOW, "divergence": "ALL"}
    gate = gate_regime(regime_by_date, allow_bear_only)
    ta, _, va, _ = evaluate(universe, gate)
    print(f"\n=== variant: drop bear only ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")

    # Variant 3: drop bear + divergence (no signals on weak days)
    allow_no_weak = {**ALLOW, "divergence": set()}
    gate = gate_regime(regime_by_date, allow_no_weak)
    ta, _, va, _ = evaluate(universe, gate)
    print(f"\n=== variant: drop bear + divergence entirely ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")

    # Variant 4: drop bear + 接力 in divergence (per 0410 — connlianban dies in分歧)
    allow_no_jieli_in_div = {**ALLOW}
    allow_no_jieli_in_div["divergence"] = {
        m for m in {"绿断低吸", "红断低吸", "首红断低吸", "孕线低吸", "N字低吸",
                    "全盘低位低吸", "方向低位低吸", "接力低弱转1"}
    }
    gate = gate_regime(regime_by_date, allow_no_jieli_in_div)
    ta, _, va, _ = evaluate(universe, gate)
    print(f"\n=== variant: drop bear + drop 接力(only) in divergence ===")
    print(f"  TRAIN active: {ta.fmt()}  Δ={ta.avg-bt.avg:+.2f}%")
    print(f"  TEST  active: {va.fmt()}  Δ={va.avg-bv.avg:+.2f}%")


if __name__ == "__main__":
    main()
