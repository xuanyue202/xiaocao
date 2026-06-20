"""Capability flywheel — judge the live K->P pipeline on accumulated data with
the research-discipline guards, and record the verdict to the knowledge ledger.

This is the strategy-compounding half of the flywheel. Every run asks: "does the
deployed secondary screen still beat take-all under the FULL discipline
(cache-only, enough trading days, per-trade-not-day-weighted, walk-forward
train+test, multiple-comparison significance)?" and appends the honest answer to
kronos_screen/HYPOTHESES.jsonl. A PASS gives confidence to keep/retrain; a
REJECTED tells the operator the edge has not (yet) survived — with no one
re-deriving the checks by hand. (On today's data this will faithfully reproduce
STATE.md's "marginal, not robustly significant" conclusion.)

    python3 scripts/continuous_optimize.py                 # judge A (kp_star) & B (vb_star)
    python3 scripts/continuous_optimize.py --record         # also append to the ledger
    python3 scripts/continuous_optimize.py --n-tried 6      # honest multiple-comparison count
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import guards, ledger  # noqa: E402

TRAIN = ROOT / "output" / "live" / "training_rows.parquet"

VARIANTS = {
    "kp_star": ("A_kp_star", "K->P top picks (variant A) beats take-all"),
    "vb_star": ("B_vb_star", "K->P + auction tiebreak (variant B) beats take-all"),
}


def build_results(df: pd.DataFrame, variant_col: str) -> list[dict]:
    """Per selected trade: strat_ret = the pick's realized next-close return;
    base_ret = that day's take-all mean (the counterfactual of selecting nothing).
    Per-trade spread therefore answers exactly STATE.md's honest question, not the
    day-weighted cum headline."""
    scored = df[df["net_realized_ret"].notna()].copy()
    if scored.empty or variant_col not in scored.columns:
        return []
    day_takeall = scored.groupby("date")["net_realized_ret"].mean().to_dict()
    out: list[dict] = []
    for r in scored[scored[variant_col] == True].itertuples():  # noqa: E712
        out.append({
            "day": str(r.date),
            "strat_ret": float(r.net_realized_ret),
            "base_ret": float(day_takeall.get(str(r.date), 0.0)),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=str(TRAIN))
    ap.add_argument("--n-tried", type=int, default=6,
                    help="hypotheses tried across the research program (STATE.md ~6); Bonferroni")
    ap.add_argument("--min-days", type=int, default=8)
    ap.add_argument("--record", action="store_true", help="append verdicts to the knowledge ledger")
    ap.add_argument("--ledger", default=str(ledger.DEFAULT_LEDGER_PATH))
    a = ap.parse_args()

    path = Path(a.train)
    if not path.exists():
        print(f"no accumulated data yet ({path}); run the daily eod loop first to grow training_rows")
        return
    df = pd.read_parquet(path)

    any_recorded = False
    for variant_col, (hyp_id, claim) in VARIANTS.items():
        results = build_results(df, variant_col)
        if not results:
            print(f"{hyp_id}: no live picks with outcomes yet — skip")
            continue
        verdict = guards.evaluate_hypothesis(results, n_tried=a.n_tried, cache_only=True, min_days=a.min_days)
        pt = verdict["per_trade"]
        mark = "PASS" if verdict["verdict"] == "PASS" else "REJECTED"
        print(
            f"{hyp_id}: {mark}  ({verdict['n_trades']} trades / {verdict['n_days']} days)  "
            f"per-trade spread {pt['spread']:+.4f}%  p={verdict['significance']['p']:.3f}"
        )
        if verdict["rejected_by"]:
            print(f"   rejected by: {', '.join(verdict['rejected_by'])}")
        for w in verdict["warnings"]:
            print(f"   ⚠ {w}")
        if a.record:
            ledger.record_hypothesis(
                hypothesis_id=hyp_id, claim=claim,
                method="live forward eval (open[D]->net close[D+1]) vs take-all, per-trade",
                verdict=verdict, n_tried=a.n_tried, path=Path(a.ledger),
            )
            any_recorded = True
    if any_recorded:
        print(f"recorded verdict(s) -> {a.ledger}")


if __name__ == "__main__":
    main()
