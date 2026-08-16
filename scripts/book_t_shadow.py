#!/usr/bin/env python3
"""Run or inspect the Book T v2 shadow consumer.

Normal Book T paper trading remains the existing ``paper_record.py
--trend-only`` control path until Issue 06's evidence gate is accepted.  This
command consumes only a separately frozen v2 input and writes under
``output/research/book_t_v2_shadow``; it never writes the formal T account.

Examples::

    python3 scripts/book_t_shadow.py --runtime-check --json
    python3 scripts/book_t_shadow.py --input output/live/book_t_v2_shadow_input.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research.book_t_shadow import (  # noqa: E402
    BOOK_T_SHADOW_MIN_BURN_IN_DAYS,
    BOOK_T_SHADOW_MIN_STRATEGY_DAYS,
    BOOK_T_SHADOW_MIN_VALID_DECISIONS,
    BOOK_T_CONTROL_ARTIFACT_PATHS,
    BOOK_T_SHADOW_INPUT_NAMESPACE,
    BOOK_T_SHADOW_NAMESPACE,
    BOOK_T_SHADOW_PROTOCOL_ID,
    BookTShadowError,
    evaluate_book_t_shadow,
    run_book_t_shadow,
    write_book_t_shadow_artifacts,
)
from xiaocao.kol.publication import canonical_sha256  # noqa: E402


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BookTShadowError(f"cannot read JSON input {path}: {exc}") from exc


def _load_days(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("days"), list):
        days = payload["days"]
    elif isinstance(payload, dict):
        days = [payload]
    else:
        raise BookTShadowError("shadow input must be one object or an object with a days list")
    if not days or not all(isinstance(day, dict) for day in days):
        raise BookTShadowError("shadow input days must be non-empty objects")
    return [dict(day) for day in days]


def _load_historical_days(output_dir: Path) -> list[dict[str, Any]]:
    """Read prior isolated shadow inputs so the research floor accumulates."""

    if not output_dir.exists():
        return []
    historical: list[dict[str, Any]] = []
    for child in sorted(output_dir.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        frozen_path = child / "frozen_inputs.json"
        if not manifest_path.exists() and not frozen_path.exists():
            continue
        if not manifest_path.exists() or not frozen_path.exists():
            raise BookTShadowError(f"incomplete shadow artifact directory: {child}")
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise BookTShadowError(f"shadow manifest must be an object: {manifest_path}")
        if (
            manifest.get("namespace") != BOOK_T_SHADOW_NAMESPACE
            or manifest.get("protocol_id") != BOOK_T_SHADOW_PROTOCOL_ID
        ):
            raise BookTShadowError(f"unexpected shadow namespace in {manifest_path}")
        payload = _read_json(frozen_path)
        if not isinstance(payload, list) or not all(isinstance(day, dict) for day in payload):
            raise BookTShadowError(f"frozen_inputs must be a list of objects: {frozen_path}")
        inputs = manifest.get("inputs")
        if not isinstance(inputs, dict):
            raise BookTShadowError(f"shadow manifest inputs are missing: {manifest_path}")
        if inputs.get("frozen_input_sha256") != canonical_sha256(payload):
            raise BookTShadowError(f"frozen input manifest hash mismatch: {manifest_path}")
        try:
            manifest_days = int(inputs.get("n_days", -1))
        except (TypeError, ValueError) as exc:
            raise BookTShadowError(f"frozen input manifest count is invalid: {manifest_path}") from exc
        if manifest_days != len(payload):
            raise BookTShadowError(f"frozen input manifest count mismatch: {manifest_path}")
        if manifest.get("formal_ledger_mutations") != {"positions": 0, "account": 0, "trades": 0}:
            raise BookTShadowError(f"historical shadow artifact claims formal ledger mutation: {manifest_path}")
        historical.extend(dict(day) for day in payload)
    return historical


def _merge_days(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate replayed artifacts, while rejecting same-day divergence."""

    by_hash: dict[str, dict[str, Any]] = {}
    by_date: dict[str, str] = {}
    for day in days:
        run = run_book_t_shadow(day)
        digest = str(run["input_sha256"])
        market_date = str(run["market_date"])
        previous = by_date.get(market_date)
        if previous is not None and previous != digest:
            raise BookTShadowError(
                f"multiple frozen shadow inputs claim trading day {market_date}"
            )
        by_date[market_date] = digest
        by_hash.setdefault(digest, dict(day))
    return [
        by_hash[digest]
        for digest in sorted(
            by_hash,
            key=lambda value: str(run_book_t_shadow(by_hash[value])["market_date"]),
        )
    ]


def _verify_control_receipts(days: list[dict[str, Any]], *, root: Path = ROOT) -> None:
    """Prove the frozen control receipt still matches the v1 T artifacts."""

    for day in days:
        control = day.get("control")
        if not isinstance(control, dict):
            raise BookTShadowError("control receipt is missing from frozen input")
        receipt = control.get("control_receipt")
        if not isinstance(receipt, dict):
            raise BookTShadowError("control receipt is missing from frozen input")
        date_label = str(day.get("as_of") or "")[:10]
        emitted_path = root / f"output/live/book_t_v1_control_receipt_{date_label}.json"
        emitted = _read_json(emitted_path)
        if not isinstance(emitted, dict) or canonical_sha256(emitted) != canonical_sha256(receipt):
            raise BookTShadowError(
                f"v1 control receipt does not match dated paper_record receipt: {emitted_path}"
            )
        hashes = receipt.get("artifact_hashes")
        if not isinstance(hashes, dict):
            raise BookTShadowError("control receipt artifact hashes are missing")
        for artifact, relative_path in BOOK_T_CONTROL_ARTIFACT_PATHS.items():
            path = root / relative_path
            try:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise BookTShadowError(
                    f"cannot read v1 control artifact for receipt: {path}"
                ) from exc
            if actual != str(hashes.get(artifact) or "").strip().lower():
                raise BookTShadowError(
                    f"v1 control receipt hash mismatch for {artifact}: {path}"
                )


def _git_state() -> dict[str, Any]:
    def run(args: list[str]) -> str | None:
        try:
            completed = subprocess.run(
                args,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError:
            return None
        return completed.stdout.strip() if completed.returncode == 0 else None

    status = run(["git", "status", "--porcelain"])
    return {
        "commit": run(["git", "rev-parse", "--short", "HEAD"]),
        "dirty": bool(status),
        "status_porcelain": status.splitlines() if status else [],
    }


def _position_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    invalid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            invalid += 1
    return rows, invalid


def runtime_check(*, root: Path = ROOT, target_date: str | None = None) -> dict[str, Any]:
    """Read-only consumer preflight for the next Book T paper run."""

    live = root / "output" / "live"
    required = {
        "automation": root / "scripts" / "auto_daily.sh",
        "paper_record": root / "kronos_screen" / "scripts" / "paper_record.py",
        "monitor": root / "scripts" / "live_monitor.py",
        "settle": root / "kronos_screen" / "scripts" / "settle_book_t.py",
        "positions": live / "positions.jsonl",
        "account": live / "paper_account_T.json",
    }
    checks: dict[str, dict[str, Any]] = {}
    for name, path in required.items():
        checks[name] = {"path": str(path), "exists": path.exists()}
    automation = required["automation"].read_text(encoding="utf-8") if required["automation"].exists() else ""
    paper_record = required["paper_record"].read_text(encoding="utf-8") if required["paper_record"].exists() else ""
    monitor = required["monitor"].read_text(encoding="utf-8") if required["monitor"].exists() else ""
    checks["automation"]["has_trend_only_consumer"] = "paper_record.py" in automation and "--trend-only" in automation
    checks["paper_record"]["has_trend_only_mode"] = "--trend-only" in paper_record
    checks["monitor"]["has_explicit_book_t"] = "--book T" in monitor or 'choices=["B", "T"]' in monitor

    positions, invalid_json_rows = _position_rows(required["positions"])
    open_positions = [
        row for row in positions if row.get("book") == "T" and row.get("status", "open") == "open"
    ]
    checks["state"] = {
        "target_date": target_date or (date.today() + timedelta(days=1)).isoformat(),
        "open_positions": len(open_positions),
        "target_slots": 3,
        "full_slots": len(open_positions) >= 3,
        "invalid_book_rows": sum(1 for row in positions if row.get("book") not in {"A", "B", "T"}),
        "invalid_json_rows": invalid_json_rows,
        "pending_ledger_transaction": (live / ".ledger_txn" / "pending.json").exists(),
    }

    failures: list[str] = []
    for name, item in checks.items():
        if name == "state":
            continue
        if not item.get("exists"):
            failures.append(f"missing_{name}")
    if not checks["automation"].get("has_trend_only_consumer"):
        failures.append("automation_missing_trend_only")
    if not checks["paper_record"].get("has_trend_only_mode"):
        failures.append("paper_record_missing_trend_only")
    if not checks["monitor"].get("has_explicit_book_t"):
        failures.append("monitor_missing_explicit_book_t")
    if checks["state"]["pending_ledger_transaction"]:
        failures.append("pending_ledger_transaction")
    if checks["state"]["invalid_book_rows"]:
        failures.append("invalid_book_rows")
    if checks["state"]["invalid_json_rows"]:
        failures.append("invalid_positions_json")

    return {
        "namespace": BOOK_T_SHADOW_NAMESPACE,
        "consumer": "book_t_v1_control",
        "v2_shadow": "separate_research_namespace_only",
        "status": "ready" if not failures else "blocked",
        "failures": failures,
        "checks": checks,
        "next_command": "bash scripts/auto_daily.sh morning-execute",
        "v2_input_namespace": BOOK_T_SHADOW_INPUT_NAMESPACE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="hash-bound daily JSON or {days:[...]} shadow input")
    parser.add_argument("--output-dir", default="output/research/book_t_v2_shadow")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--min-burn-in-days", type=int, default=BOOK_T_SHADOW_MIN_BURN_IN_DAYS)
    parser.add_argument("--min-strategy-days", type=int, default=BOOK_T_SHADOW_MIN_STRATEGY_DAYS)
    parser.add_argument("--min-valid-decisions", type=int, default=BOOK_T_SHADOW_MIN_VALID_DECISIONS)
    parser.add_argument("--n-tried", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="print structured output")
    parser.add_argument("--runtime-check", action="store_true", help="read-only next-run preflight")
    args = parser.parse_args()

    try:
        if args.runtime_check:
            result = runtime_check()
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if result["status"] == "ready" else 2
        if not args.input:
            parser.error("--input is required unless --runtime-check is used")
        input_path = Path(args.input)
        output_dir = Path(args.output_dir)
        new_days = _load_days(input_path)
        _verify_control_receipts(new_days)
        frozen_inputs = _merge_days(
            _load_historical_days(output_dir) + new_days
        )
        runs = [run_book_t_shadow(day) for day in frozen_inputs]
        evaluation = evaluate_book_t_shadow(
            runs,
            min_burn_in_days=args.min_burn_in_days,
            min_strategy_days=args.min_strategy_days,
            min_valid_decisions=args.min_valid_decisions,
            n_tried=args.n_tried,
        )
        run_id = args.run_id or f"{runs[-1]['market_date']}-book-t-v2-shadow"
        paths = write_book_t_shadow_artifacts(
            runs,
            evaluation,
            output_dir=output_dir,
            run_id=run_id,
            frozen_inputs=frozen_inputs,
            git_state=_git_state(),
        )
        result = {"evaluation": evaluation, "artifacts": {key: str(value) for key, value in paths.items()}}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        else:
            print(
                f"Book T v2 shadow: {evaluation['status']} "
                f"(days={evaluation['sample']['trading_days']}, "
                f"valid_decisions={evaluation['sample']['valid_theme_decisions']})"
            )
            print(f"artifacts: {paths['root']}")
        # REJECTED is a normal research terminal state.  The optional shadow
        # consumer must not block the v1 paper writer; malformed or unbound
        # input still raises BookTShadowError and returns 2 above.
        return 0 if evaluation["status"] in {"PASS", "pending_observation", "REJECTED"} else 1
    except BookTShadowError as exc:
        print(f"Book T v2 shadow blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
