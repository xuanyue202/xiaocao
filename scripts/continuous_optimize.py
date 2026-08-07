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

    python3 scripts/continuous_optimize.py                 # judge A/B/C tracked variants
    python3 scripts/continuous_optimize.py --record         # also append to the ledger
    python3 scripts/continuous_optimize.py --n-tried 6      # honest multiple-comparison count
"""
from __future__ import annotations

import argparse
import json
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
    "mode_star": ("C_mode_rotation_k_survivors", "K survivors + mode-rotation rank (variant C) beats take-all"),
    "qibao_benchmark_star": (
        "D_qibao_benchmark_paper_promoted",
        "raw-qibao benchmark paper-promoted modes (variant D) beat take-all",
    ),
    "ai_intelligence_short_star": (
        "E_ai_intelligence_short_factor",
        "agent-reviewed AI intelligence short-factor bullish picks (variant E) beat take-all",
    ),
}

# A strategy-consumption verdict must use the same executable label contract as
# Book B.  Legacy A/B shadows remain descriptive on theoretical next-close
# returns, while variant C is the only tracked candidate currently eligible for
# paper-strategy consumption and therefore must be judged on fillable opening-
# window net returns.  This keeps a theoretical PASS from being promoted into
# the executable path.
VARIANT_RETURN_CONTRACTS = {
    "mode_star": {
        "return_col": "executable_net_ret",
        "eligible_col": "executable_fillable",
        "exclude_bjse": True,
        "method": (
            "live forward eval (opening-window executable net[D]->close[D+1]) "
            "vs same-day executable take-all, per-trade"
        ),
    },
}


def is_new_information(prev: dict | None, verdict: dict) -> bool:
    """Should this verdict be appended to the ledger?

    True when there is no prior entry for the hypothesis, or the verdict / the
    set of failing guards CHANGED. The flywheel RE-EVALUATES every variant each
    run (more accumulated days may flip a verdict), but the ledger is a CHANGELOG,
    not a heartbeat: re-recording an identical REJECTED every run would bury the
    real transitions under duplicates. This is what makes `ledger.already_refuted`
    load-bearing — a settled, unchanged verdict is consulted, not re-litigated."""
    if prev is None:
        return True
    if prev.get("verdict") != verdict.get("verdict"):
        return True
    return sorted(prev.get("rejected_by") or []) != sorted(verdict.get("rejected_by") or [])


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def build_results(
    df: pd.DataFrame,
    variant_col: str,
    *,
    return_col: str = "net_realized_ret",
    eligible_col: str | None = None,
    exclude_bjse: bool = False,
) -> list[dict]:
    """Per selected trade: strat_ret = the pick's realized next-close return;
    base_ret = that day's LEAVE-ONE-OUT take-all mean (the counterfactual of NOT
    selecting this pick — it excludes the pick itself, so the baseline is not
    contaminated by the very return being judged). Days with no non-pick row are
    skipped (no counterfactual exists). Per-trade spread therefore answers exactly
    STATE.md's honest question, not the day-weighted cum headline.

    The day key is normalized to one dtype on BOTH the groupby and the lookup: a
    Timestamp-typed `date` column would otherwise key the groupby on Timestamps
    while str(...) lookups miss, silently defaulting every baseline to 0.0 and
    passing a LOSING strategy as validated (an audited critical bug). A missing
    day now raises (fail loud) rather than fabricating a baseline."""
    if variant_col not in df.columns or return_col not in df.columns:
        return []
    scored = df[df[return_col].notna()].copy()
    if eligible_col is not None:
        if eligible_col not in scored.columns:
            return []
        scored = scored[scored[eligible_col].map(_truthy)]
    if exclude_bjse and "code" in scored.columns:
        scored = scored[~scored["code"].astype(str).str.endswith(".BJSE")]
    if scored.empty:
        return []
    scored["__day"] = scored["date"].astype(str)
    day_sum = scored.groupby("__day")[return_col].sum()
    day_cnt = scored.groupby("__day")[return_col].count()
    picks = scored[scored[variant_col].map(_truthy)]
    out: list[dict] = []
    for day, ret in zip(picks["__day"], picks[return_col]):
        n = int(day_cnt[day])  # KeyError if the day is absent — fail loud, never default to 0
        if n <= 1:
            continue  # no non-pick counterfactual that day
        base = (float(day_sum[day]) - float(ret)) / (n - 1)
        out.append({"day": str(day), "strat_ret": float(ret), "base_ret": base})
    return out


def write_results_jsonl(results: list[dict], path: Path) -> None:
    """Persist the exact guard input so research_run.py can bind a manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in results),
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default=str(TRAIN))
    ap.add_argument("--n-tried", type=int, default=6,
                    help="hypotheses tried across the research program (STATE.md ~6); Bonferroni")
    ap.add_argument("--min-days", type=int, default=8)
    ap.add_argument("--record", action="store_true", help="append verdicts to the knowledge ledger")
    ap.add_argument("--ledger", default=str(ledger.DEFAULT_LEDGER_PATH))
    ap.add_argument("--export-variant", choices=sorted(VARIANTS),
                    help="export one variant's exact guard rows for a protocol-bound research run")
    ap.add_argument("--export-trades", type=Path,
                    help="JSONL destination paired with --export-variant")
    a = ap.parse_args()
    if bool(a.export_variant) != bool(a.export_trades):
        raise SystemExit("--export-variant and --export-trades must be provided together")

    path = Path(a.train)
    if not path.exists():
        print(f"no accumulated data yet ({path}); run the daily eod loop first to grow training_rows")
        return
    df = pd.read_parquet(path)
    if "ai_intelligence_short_star" not in df.columns and "intelligence_long_star" in df.columns:
        df["ai_intelligence_short_star"] = df["intelligence_long_star"]

    # Honest multiple-comparison floor: at least the count of distinct hypotheses
    # ever judged (in the ledger) plus the variants tried now, so passing a small
    # --n-tried cannot launder a result that should fail Bonferroni.
    ledger_path = Path(a.ledger)
    prior_ids = {e.get("id") for e in ledger.read_all(ledger_path)}
    tried_ids = prior_ids | {h for h, _ in VARIANTS.values()}
    n_tried = max(int(a.n_tried), len(tried_ids))
    if n_tried > a.n_tried:
        print(f"note: n_tried raised {a.n_tried}->{n_tried} "
              f"(ledger has {len(prior_ids)} distinct prior hypotheses; multiple-comparison honesty)")

    any_recorded = False
    for variant_col, (hyp_id, claim) in VARIANTS.items():
        contract = VARIANT_RETURN_CONTRACTS.get(variant_col, {})
        results = build_results(
            df,
            variant_col,
            return_col=str(contract.get("return_col", "net_realized_ret")),
            eligible_col=contract.get("eligible_col"),
            exclude_bjse=bool(contract.get("exclude_bjse", False)),
        )
        if a.export_variant == variant_col:
            if not results:
                raise SystemExit(f"{hyp_id}: no guard rows available to export")
            write_results_jsonl(results, a.export_trades)
            print(f"{hyp_id}: exported {len(results)} guard rows -> {a.export_trades}")
        if not results:
            print(f"{hyp_id}: no live picks with outcomes yet — skip")
            continue
        verdict = guards.evaluate_hypothesis(results, n_tried=n_tried, cache_only=True, min_days=a.min_days)
        pt = verdict["per_trade"]
        mark = "PASS" if verdict["verdict"] == "PASS" else "REJECTED"
        # Consult the ledger BEFORE judging-as-new: a previously-refuted direction
        # is re-evaluated (data grows) but flagged so the operator sees continuity.
        prior = ledger.find(hyp_id, path=ledger_path)
        prev = prior[-1] if prior else None
        if prev is not None and ledger.already_refuted(hyp_id, path=ledger_path):
            print(f"   note: re-evaluating a previously-REJECTED direction "
                  f"(ledger.already_refuted={hyp_id}); more data may yet change the verdict")
        print(
            f"{hyp_id}: {mark}  ({verdict['n_trades']} trades / {verdict['n_days']} days)  "
            f"per-trade spread {pt['spread']:+.4f}%  p={verdict['significance']['p']:.3f}"
        )
        if verdict["rejected_by"]:
            print(f"   rejected by: {', '.join(verdict['rejected_by'])}")
        for w in verdict["warnings"]:
            print(f"   ⚠ {w}")
        if a.record:
            if is_new_information(prev, verdict):
                ledger.record_hypothesis(
                    hypothesis_id=hyp_id, claim=claim,
                    method=str(contract.get(
                        "method",
                        "live forward eval (open[D]->net close[D+1]) vs take-all, per-trade",
                    )),
                    verdict=verdict, n_tried=n_tried, path=ledger_path,
                )
                any_recorded = True
            else:
                print(f"   verdict unchanged vs ledger ({mark}) — not re-recording "
                      f"(the ledger is a changelog, not a heartbeat)")
    if any_recorded:
        print(f"recorded verdict(s) -> {a.ledger}")


if __name__ == "__main__":
    main()
