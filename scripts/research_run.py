"""Run a hypothesis through the discipline guardrails and (optionally) record it.

The harness enforces the validation rules so the agent can't launder a weak or
day-weighting-inflated result into a "validated" headline. It judges a *results
file* you produce from cache (cache-only) — one trade per line:

    {"day": "2026-01-05", "strat_ret": 0.012, "base_ret": 0.008}

    # judge only
    python3 scripts/research_run.py --trades out.jsonl --n-tried 6
    # judge + append to the knowledge ledger
    python3 scripts/research_run.py --trades out.jsonl --n-tried 6 --record \
        --id kp50_p_top3 --claim "K50->P top3 beats take-all" --method "walk-forward OOS"

See kronos_screen/HYPOTHESES.jsonl and docs/OPERATING_CONTRACT.md §2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import guards, ledger  # noqa: E402


def _load_trades(path: Path) -> list[dict]:
    trades: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            trades.append({"day": r["day"], "strat_ret": float(r["strat_ret"]), "base_ret": float(r["base_ret"])})
    return trades


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trades", required=True, help="jsonl of {day, strat_ret, base_ret} (produced from cache)")
    ap.add_argument("--n-tried", type=int, default=1, help="hypotheses tried (Bonferroni multiple-comparison)")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--min-days", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="print the full structured verdict")
    ap.add_argument("--record", action="store_true", help="append the verdict to the knowledge ledger")
    ap.add_argument("--id", help="hypothesis id (required with --record)")
    ap.add_argument("--claim", default="", help="one-line claim")
    ap.add_argument("--method", default="", help="how it was measured")
    ap.add_argument("--supersedes", default=None)
    ap.add_argument("--ledger", default=str(ledger.DEFAULT_LEDGER_PATH))
    a = ap.parse_args()

    trades = _load_trades(Path(a.trades))
    verdict = guards.evaluate_hypothesis(
        trades, n_tried=a.n_tried, cache_only=True, alpha=a.alpha, min_days=a.min_days,
    )

    if a.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        pt, sig = verdict["per_trade"], verdict["significance"]
        mark = "✅ PASS" if verdict["verdict"] == "PASS" else "❌ REJECTED"
        print(f"{mark}  ({verdict['n_trades']} trades / {verdict['n_days']} days)")
        print(f"  per-trade spread {pt['spread']:+.4f}  (strat {pt['strat_mean']:+.4f} vs base {pt['base_mean']:+.4f})")
        print(f"  walk-forward train {verdict['walk_forward']['train_edge']:+.4f} / "
              f"test {verdict['walk_forward']['test_edge']:+.4f}")
        print(f"  p={sig['p']:.4f} (effective alpha {sig['effective_alpha']:.4f})")
        if verdict["rejected_by"]:
            print(f"  rejected by: {', '.join(verdict['rejected_by'])}")
        for w in verdict["warnings"]:
            print(f"  ⚠ {w}")

    if a.record:
        if not a.id:
            raise SystemExit("--record requires --id")
        entry = ledger.record_hypothesis(
            hypothesis_id=a.id, claim=a.claim, method=a.method, verdict=verdict,
            n_tried=a.n_tried, supersedes=a.supersedes, path=Path(a.ledger),
        )
        print(f"recorded -> {a.ledger}: {entry['id']} = {entry['verdict']}", file=sys.stderr)


if __name__ == "__main__":
    main()
