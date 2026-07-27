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
import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import guards, ledger  # noqa: E402

ATTRIBUTION_FIELDS = ("pick_alpha", "entry_slippage", "exit_timing")
EXPOSURE_FIELDS = ("exposure", "gross_exposure", "net_exposure")
TURNOVER_FIELDS = ("turnover", "turnover_pct")
WEIGHT_FIELDS = ("weight", "position_weight")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_state() -> dict[str, Any]:
    def run(cmd: list[str]) -> str | None:
        try:
            cp = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
        except OSError:
            return None
        if cp.returncode != 0:
            return None
        return cp.stdout.strip()

    status = run(["git", "status", "--porcelain"])
    return {
        "commit": run(["git", "rev-parse", "--short", "HEAD"]),
        "dirty": bool(status),
        "status_porcelain": status.splitlines() if status else [],
    }


def _load_trades(path: Path) -> list[dict]:
    trades: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            r["day"] = r["day"]
            r["strat_ret"] = float(r["strat_ret"])
            r["base_ret"] = float(r["base_ret"])
            trades.append(r)
    return trades


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%")
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "sum": sum(values),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def _field_summary(trades: list[dict], fields: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field in fields:
        values = [v for row in trades if (v := _as_float(row.get(field))) is not None]
        if values:
            out[field] = _summary(values)
    return out


def _row_weight(row: dict) -> float | None:
    for field in WEIGHT_FIELDS:
        v = _as_float(row.get(field))
        if v is not None:
            return v
    return None


def _concentration(trades: list[dict]) -> dict[str, Any]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    by_code: dict[str, int] = defaultdict(int)
    for row in trades:
        by_day[str(row["day"])].append(row)
        code = row.get("code")
        if code:
            by_code[str(code)] += 1

    daily_hhi: list[float] = []
    daily_max_weight: list[float] = []
    daily_positions: list[int] = []
    for rows in by_day.values():
        if not rows:
            continue
        weights = [_row_weight(row) for row in rows]
        if all(w is not None for w in weights):
            abs_weights = [abs(float(w)) for w in weights if w is not None]
            gross = sum(abs_weights)
            normalized = [w / gross for w in abs_weights] if gross else []
        else:
            normalized = [1.0 / len(rows)] * len(rows)
        if not normalized:
            continue
        daily_positions.append(len(rows))
        daily_hhi.append(sum(w * w for w in normalized))
        daily_max_weight.append(max(normalized))

    total_rows = len(trades)
    top_code_share = max(by_code.values()) / total_rows if by_code and total_rows else None
    return {
        "days": len(by_day),
        "mean_positions_per_day": _summary([float(x) for x in daily_positions]).get("mean", 0.0),
        "mean_hhi": _summary(daily_hhi).get("mean", 0.0),
        "mean_max_weight": _summary(daily_max_weight).get("mean", 0.0),
        "top_code_share": top_code_share,
        "code_count": len(by_code),
    }


def _diagnostics(trades: list[dict]) -> dict[str, Any]:
    coverage_fields = ATTRIBUTION_FIELDS + EXPOSURE_FIELDS + TURNOVER_FIELDS + WEIGHT_FIELDS + ("code",)
    coverage = {field: sum(1 for row in trades if row.get(field) not in (None, "")) for field in coverage_fields}
    return {
        "coverage": coverage,
        "attribution": _field_summary(trades, ATTRIBUTION_FIELDS),
        "exposure": _field_summary(trades, EXPOSURE_FIELDS),
        "turnover": _field_summary(trades, TURNOVER_FIELDS),
        "concentration": _concentration(trades),
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_run_artifacts(
    *,
    run_dir: Path,
    trades_path: Path,
    trades: list[dict],
    verdict: dict[str, Any],
    args: argparse.Namespace,
    ledger_entry: dict[str, Any] | None,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    trades_artifact = run_dir / "trades.jsonl"
    if trades_path.resolve() != trades_artifact.resolve():
        shutil.copy2(trades_path, trades_artifact)
    verdict_artifact = run_dir / "verdict.json"
    _write_json(verdict_artifact, verdict)

    manifest = {
        "schema_version": 1,
        "created_at": _now_iso(),
        "run_id": args.run_id,
        "hypothesis_id": args.id,
        "claim": args.claim,
        "method": args.method,
        "protocol_id": args.protocol_id,
        "supersedes": args.supersedes,
        "parameters": {
            "n_tried": args.n_tried,
            "alpha": args.alpha,
            "min_days": args.min_days,
            "cache_only": True,
        },
        "inputs": {
            "trades_source": str(trades_path),
            "trades_artifact": str(trades_artifact),
            "trades_sha256": _sha256(trades_artifact),
            "n_rows": len(trades),
        },
        "artifacts": {
            "run_dir": str(run_dir),
            "manifest": str(run_dir / "manifest.json"),
            "verdict": str(verdict_artifact),
            "trades": str(trades_artifact),
        },
        "verdict": {
            "status": verdict.get("verdict"),
            "rejected_by": verdict.get("rejected_by", []),
            "n_trades": verdict.get("n_trades"),
            "n_days": verdict.get("n_days"),
        },
        "diagnostics": verdict.get("diagnostics", {}),
        "ledger_entry": ledger_entry,
        "git": _git_state(),
    }
    manifest_path = run_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


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
    ap.add_argument("--run-dir", help="write a versioned research run directory with trades, verdict, and manifest")
    ap.add_argument("--run-id", help="stable run id stored in manifest; defaults to the run directory name")
    ap.add_argument("--protocol-id", help="strategy/research protocol id stored in manifest")
    a = ap.parse_args()
    if a.run_dir and not a.run_id:
        a.run_id = Path(a.run_dir).name

    if a.n_tried <= 1:
        print("⚠ no multiple-comparison correction (n_tried=1) — pass --n-tried with the honest "
              "count of hypotheses tried in this research program, or significance is overstated.",
              file=sys.stderr)
    trades_path = Path(a.trades)
    trades = _load_trades(trades_path)
    verdict = guards.evaluate_hypothesis(
        trades, n_tried=a.n_tried, cache_only=True, alpha=a.alpha, min_days=a.min_days,
    )
    verdict["diagnostics"] = _diagnostics(trades)

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

    ledger_entry = None
    if a.record:
        if not a.id:
            raise SystemExit("--record requires --id")
        ledger_entry = ledger.record_hypothesis(
            hypothesis_id=a.id, claim=a.claim, method=a.method, verdict=verdict,
            n_tried=a.n_tried, supersedes=a.supersedes, path=Path(a.ledger),
        )
        print(f"recorded -> {a.ledger}: {ledger_entry['id']} = {ledger_entry['verdict']}", file=sys.stderr)

    if a.run_dir:
        manifest_path = _write_run_artifacts(
            run_dir=Path(a.run_dir),
            trades_path=trades_path,
            trades=trades,
            verdict=verdict,
            args=a,
            ledger_entry=ledger_entry,
        )
        print(f"research run manifest -> {manifest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
