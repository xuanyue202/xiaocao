#!/usr/bin/env python3
"""Run Book T v2 daily-stability and engineering burn-in gates.

This command only consumes already-frozen shadow inputs and manifests.  It
does not create dates, call the market API, mutate formal ledgers, or count
rehearsal evidence as real trading days.  The five-day daily-stability soak
and twenty-day engineering burn-in are separate acceptances; neither is a
strategy-promotion gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.kol.publication import canonical_sha256  # noqa: E402
from xiaocao.research.book_t_shadow import (  # noqa: E402
    BookTShadowError,
    run_book_t_shadow,
)
from xiaocao.research.book_t_v2_lifecycle import (  # noqa: E402
    BookTV2EvidenceError,
    validate_lifecycle,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_inputs(root: Path) -> list[dict[str, Any]]:
    live = root / "output/live"
    rows: list[dict[str, Any]] = []
    for path in sorted(live.glob("book_t_v2_shadow_input_*.json")):
        value = _read_json(path)
        if not isinstance(value, dict):
            continue
        date_iso = path.stem.removeprefix("book_t_v2_shadow_input_")
        manifest_path = root / "output/research/book_t_v2_shadow" / f"{date_iso}-book-t-v2-shadow" / "manifest.json"
        if not manifest_path.exists():
            raise BookTShadowError(f"missing shadow manifest for {date_iso}: {manifest_path}")
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise BookTShadowError(f"shadow manifest is not an object: {manifest_path}")
        if manifest.get("namespace") != "book_t_v2_shadow":
            raise BookTShadowError(f"shadow manifest namespace is invalid: {manifest_path}")
        if manifest.get("formal_ledger_mutations") != {
            "positions": 0,
            "account": 0,
            "trades": 0,
        }:
            raise BookTShadowError(f"shadow manifest claims a formal ledger mutation: {manifest_path}")
        manifest_inputs = manifest.get("inputs")
        if not isinstance(manifest_inputs, dict):
            raise BookTShadowError(f"shadow manifest inputs are missing: {manifest_path}")
        frozen_path = Path(str(manifest_inputs.get("frozen_inputs") or ""))
        if not frozen_path.is_absolute():
            frozen_path = root / frozen_path
        frozen_rows = _read_json(frozen_path)
        if not isinstance(frozen_rows, list) or not any(
            isinstance(row, dict) and row.get("input_sha256") == value.get("input_sha256")
            for row in frozen_rows
        ):
            raise BookTShadowError(f"shadow manifest does not bind dated input {path}")
        rows.append(value)
    return rows


def _evaluate_soak(
    inputs: list[dict[str, Any]],
    *,
    required_days: int,
    minimum_days: int,
    minimum_label: str,
    gate: str,
) -> dict[str, Any]:
    if required_days < minimum_days:
        raise ValueError(
            f"required_days cannot be below {minimum_label} trading days"
        )
    runs: list[dict[str, Any]] = []
    for value in inputs:
        first = run_book_t_shadow(value)
        second = run_book_t_shadow(value)
        if canonical_sha256(first) != canonical_sha256(second):
            raise BookTShadowError(
                f"frozen input is not replayable: {value.get('as_of')}"
            )
        runs.append(first)
    lifecycles = [
        validate_lifecycle(value["evidence_lifecycle"])
        for value in inputs
        if isinstance(value.get("evidence_lifecycle"), dict)
    ]
    real = [
        row
        for row in lifecycles
        if row.get("run_mode") == "real"
        and row.get("provenance", {}).get("is_rehearsal") is False
    ]
    real.sort(key=lambda row: int(row["trading_day_index"]))
    indices = [int(row["trading_day_index"]) for row in real]
    contiguous = not indices or indices == list(range(indices[0], indices[-1] + 1))
    engineering_failures: list[str] = []
    for run in runs:
        engineering = run.get("engineering", {})
        if not isinstance(engineering, dict):
            engineering_failures.append("engineering_record_missing")
            continue
        if engineering.get("formal_ledger_mutations") != {
            "positions": 0,
            "account": 0,
            "trades": 0,
        }:
            engineering_failures.append("formal_ledger_mutation")
        if engineering.get("daily_reevaluation_complete") is not True:
            engineering_failures.append("daily_reevaluation_incomplete")
        if engineering.get("evidence_lifecycle_bound") is not True:
            engineering_failures.append("lifecycle_unbound")
        if engineering.get("engineering_day_valid") is not True:
            engineering_failures.append("engineering_day_invalid")
    for lifecycle in lifecycles:
        if lifecycle.get("engineering_day", {}).get("replayable") is not True:
            engineering_failures.append("lifecycle_not_replayable")
    if not contiguous:
        engineering_failures.append("real_trading_day_gap")
    engineering_failures = sorted(set(engineering_failures))
    accepted = (
        len(real) >= required_days
        and contiguous
        and not engineering_failures
    )
    return {
        "status": "accepted" if accepted else "pending",
        "gate": gate,
        "required_real_trading_days": required_days,
        "real_trading_days": len(real),
        "rehearsal_days_excluded": len(lifecycles) - len(real),
        "trading_day_indices": indices,
        "contiguous": contiguous,
        "engineering_failures": engineering_failures,
        "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0},
        "strategy_promotion": "not_in_scope",
        "strategy_promotion_authorized": False,
    }


def evaluate_daily_stability_soak(
    inputs: list[dict[str, Any]],
    *,
    required_days: int = 5,
) -> dict[str, Any]:
    """Evaluate stage 3 without weakening the stage-4 twenty-day gate."""

    return _evaluate_soak(
        inputs,
        required_days=required_days,
        minimum_days=5,
        minimum_label="five",
        gate="daily_stability_soak",
    )


def evaluate_engineering_burn_in(
    inputs: list[dict[str, Any]],
    *,
    required_days: int = 20,
) -> dict[str, Any]:
    """Evaluate the formal stage-4 twenty-real-trading-day burn-in."""

    return _evaluate_soak(
        inputs,
        required_days=required_days,
        minimum_days=20,
        minimum_label="twenty",
        gate="engineering_burn_in",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.environ.get("XIAOCAO_ROOT", str(ROOT)))
    parser.add_argument(
        "--gate",
        choices=("daily-stability", "engineering-burn-in"),
        default="engineering-burn-in",
    )
    parser.add_argument("--required-days", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        inputs = _load_inputs(root)
        if args.gate == "daily-stability":
            result = evaluate_daily_stability_soak(
                inputs,
                required_days=args.required_days if args.required_days is not None else 5,
            )
            verdict_name = "daily_stability_soak_verdict.json"
        else:
            result = evaluate_engineering_burn_in(
                inputs,
                required_days=args.required_days if args.required_days is not None else 20,
            )
            verdict_name = "engineering_burn_in_verdict.json"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, BookTShadowError, BookTV2EvidenceError) as exc:
        print(f"Book T v2 soak blocked: {exc}", file=sys.stderr)
        return 2
    output = root / "output/research/book_t_v2_shadow" / verdict_name
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"Book T v2 {result['gate']}: {result['status']} "
            f"(real_days={result['real_trading_days']}, "
            f"rehearsal_excluded={result['rehearsal_days_excluded']})"
        )
    return 0 if result["status"] in {"accepted", "pending"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
