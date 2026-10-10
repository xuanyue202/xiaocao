"""Append-only correction of the legacy twice-sliced Book T budget.

No API, formal ledger writer or outcome generation is used here. Consumers
resolve only registered corrections whose original and derived bytes verify.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xiaocao.kol.publication import canonical_sha256
from xiaocao.strategy.book_t_budget import budget_contract, constrain_shadow_fills
from xiaocao.strategy.book_t_selector import select_book_t
from .book_t_shadow import BookTShadowError, bind_book_t_shadow_input, run_book_t_shadow, validate_book_t_shadow_input, validate_book_t_lifecycle_events
from .book_t_v2_lifecycle import (
    build_initial_lifecycle, read_events, build_daily_mark_event,
    build_exit_event, build_matured_outcome_event,
)
from .book_t_v2_producer import _shadow_fill_rows

REPAIR_VERSION = "book-t-independent-budget-repair-v1"
REPAIR_ROOT = "output/research/book_t_v2_budget_repairs"


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except (OSError, ValueError) as exc:
        raise BookTShadowError(f"cannot read budget repair JSON {path}: {exc}") from exc


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BookTShadowError(f"cannot read budget repair source {path}: {exc}") from exc


def _original(root: Path, value: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    validate_book_t_shadow_input(value)
    day = str(value["as_of"])[:10]
    path = root / f"output/live/book_t_v2_shadow_input_{day}.json"
    original = validate_book_t_shadow_input(_read(path))
    source_hash = value.get("budget_repair", {}).get("original_input_sha256", value["input_sha256"])
    if original["input_sha256"] != source_hash:
        raise BookTShadowError("budget repair original dated input identity mismatch")
    receipt_path = root / f"output/live/book_t_v1_control_receipt_{day}.json"
    if canonical_sha256(_read(receipt_path)) != canonical_sha256(original["control"]["control_receipt"]):
        raise BookTShadowError("budget repair dated control receipt mismatch")
    return path, original


def _validate_source_events(original: dict[str, Any], events: list[dict[str, Any]]) -> None:
    lifecycle = original["evidence_lifecycle"]
    builders = {"daily_mark": (build_daily_mark_event, "marks"),
                "exit": (build_exit_event, "exits"),
                "matured": (build_matured_outcome_event, "outcomes")}
    for event in events:
        if event["decision_id"] != lifecycle["decision_id"]:
            continue
        builder, argument = builders[event["stage"]]
        try:
            rebuilt = builder(lifecycle, observed_at=event["observed_at"],
                              **{argument: event["data"]["rows"]})
            if canonical_sha256(rebuilt) != canonical_sha256(event):
                raise ValueError("source event does not match canonical stage semantics")
        except (ValueError, KeyError, TypeError) as exc:
            raise BookTShadowError(f"budget repair source lifecycle event is invalid: {exc}") from exc


def _derive(original: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    if original["assumptions"].get("budget_ratio") != .30 or "budget_contract" in original["assumptions"]:
        raise BookTShadowError("budget repair requires the frozen legacy 30% T-account model")
    body = copy.deepcopy(original)
    body.pop("input_sha256", None)
    portfolio = body["bindings"]["portfolio"]
    budget = budget_contract(portfolio)
    plan = select_book_t(portfolio, body["bindings"]["snapshot"], body["bindings"]["universe"]).to_dict()
    body["bindings"]["selection_plan"] = plan
    body["assumptions"].update(budget_contract=budget, budget_ratio=budget["target_ratio"])
    day = str(body["as_of"])[:10]
    # Catalog facts are restricted to instrument identities already frozen.
    instruments = body["bindings"]["universe"].get("instruments", [])
    catalog = {"stocks": [row for row in instruments if row.get("instrument_type") != "etf"],
               "etfs": [row for row in instruments if row.get("instrument_type") == "etf"]}
    shadow = body["shadow"]
    fills = _shadow_fill_rows(plan, date_iso=day, market_hash=body["market_input"]["market_input_sha256"],
                              catalog=catalog, control_fills=body["control"]["fills"], source_roles=shadow["source_roles"])
    fills = constrain_shadow_fills(plan, portfolio, fills)
    shadow.update(selection_plan=plan, fills=fills, holds=[],
                  expected_fill_codes=sorted({row["code"] for row in fills}))
    body["evidence_lifecycle"] = build_initial_lifecycle(
        decision_id=f"book-t-v2:{day}:{plan['selection_plan_sha256'][:16]}", as_of=day,
        observed_at=body["as_of"], trading_day_index=body["market_input"]["trading_day_index"],
        run_mode="rehearsal", snapshot_sha256=plan["snapshot_sha256"],
        universe_sha256=plan["universe_sha256"], selection_plan_sha256=plan["selection_plan_sha256"],
        portfolio_sha256=plan["portfolio_sha256"], control_receipt_sha256=body["control"]["control_receipt"]["receipt_sha256"],
        fills=fills, daily_reevaluation_complete=plan["daily_reevaluation_complete"])
    body["producer"]["run_mode"] = "rehearsal"
    body["budget_repair"] = reference
    corrected = bind_book_t_shadow_input(body)
    run_book_t_shadow(corrected)
    return corrected


def resolve_budget_input(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    """Resolve a registered correction; never create one during consumption."""
    validate_book_t_shadow_input(value)
    if "budget_contract" in value["assumptions"] and not value.get("budget_repair"):
        return value
    path, original = _original(root, value)
    directory = root / REPAIR_ROOT / original["input_sha256"]
    if not directory.exists():
        if value.get("budget_repair"):
            raise BookTShadowError("budget repair registration is missing")
        # Unregistered legacy evidence remains explicit and subject to its old
        # validation; a bad old budget cannot silently disappear.
        return value
    manifest = _read(directory / "manifest.json")
    sealed = dict(manifest)
    digest = sealed.pop("manifest_sha256", None)
    if canonical_sha256(sealed) != digest or manifest.get("version") != REPAIR_VERSION:
        raise BookTShadowError("budget repair manifest hash/version mismatch")
    reference = manifest["reference"]
    if reference["original_file_sha256"] != _digest(path) or reference["original_input_sha256"] != original["input_sha256"]:
        raise BookTShadowError("budget repair original file hash mismatch")
    if (reference.get("version") != REPAIR_VERSION
            or reference.get("original_path") != str(path.relative_to(root))
            or reference.get("original_decision_id") != original["evidence_lifecycle"]["decision_id"]
            or reference.get("original_lifecycle_sha256") != canonical_sha256(original["evidence_lifecycle"])
            or reference.get("acceptance") != "historical_rehearsal_excluded"):
        raise BookTShadowError("budget repair original lifecycle/reference mismatch")
    event_path = root / "output/research/book_t_v2_shadow/evidence_events.jsonl"
    events = validate_book_t_lifecycle_events(read_events(event_path)) if event_path.exists() else []
    _validate_source_events(original, events)
    source_events = {event["event_id"] for event in events if event["decision_id"] == reference["original_decision_id"]}
    if not set(reference["deferred_event_sha256"]).issubset(source_events):
        raise BookTShadowError("budget repair deferred event binding mismatch")
    corrected_path = directory / "frozen_input.json"
    if manifest["derived_file_sha256"] != _digest(corrected_path):
        raise BookTShadowError("budget repair derived file hash mismatch")
    corrected = _read(corrected_path)
    # Re-derive from the original frozen facts to reject resealed substitutions.
    expected = _derive(original, reference)
    if canonical_sha256(corrected) != canonical_sha256(expected) or manifest["derived_input_sha256"] != corrected["input_sha256"]:
        raise BookTShadowError("budget repair derived facts mismatch")
    if value.get("budget_repair") and value["input_sha256"] != corrected["input_sha256"]:
        raise BookTShadowError("budget repair supplied derived identity mismatch")
    return corrected


def create_budget_repair(root: Path, path: Path) -> dict[str, Any]:
    """Register one deterministic, append-only correction under an exclusive lock."""
    value = _read(path)
    original_path, original = _original(root, value)
    base = root / REPAIR_ROOT
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".writer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = base / original["input_sha256"]
        if target.exists():
            return resolve_budget_input(root, original)
        event_path = root / "output/research/book_t_v2_shadow/evidence_events.jsonl"
        events = validate_book_t_lifecycle_events(read_events(event_path)) if event_path.exists() else []
        _validate_source_events(original, events)
        decision = original["evidence_lifecycle"]["decision_id"]
        reference = {"version": REPAIR_VERSION,
                     "original_path": str(original_path.relative_to(root)),
                     "original_file_sha256": _digest(original_path),
                     "original_input_sha256": original["input_sha256"],
                     "original_lifecycle_sha256": canonical_sha256(original["evidence_lifecycle"]),
                     "original_decision_id": decision,
                     "deferred_event_sha256": sorted(event["event_id"] for event in events if event["decision_id"] == decision),
                     "acceptance": "historical_rehearsal_excluded"}
        corrected = _derive(original, reference)
        # Rename a complete directory, so readers never see a half registration.
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=base) as temporary:
            staging = Path(temporary) / "version"
            staging.mkdir()
            frozen_path = staging / "frozen_input.json"
            frozen_path.write_text(json.dumps(corrected, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            manifest = {"version": REPAIR_VERSION, "reference": reference,
                        "registered_at": datetime.now(timezone.utc).isoformat(),
                        "derived_file_sha256": _digest(frozen_path),
                        "derived_input_sha256": corrected["input_sha256"],
                        "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0}}
            manifest["manifest_sha256"] = canonical_sha256(manifest)
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            os.rename(staging, target)
        return resolve_budget_input(root, original)


def partition_repair_events(inputs: list[dict[str, Any]], events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Defer only exact original event hashes recorded by verified corrections."""
    events = validate_book_t_lifecycle_events(events)
    deferred = {(value["budget_repair"]["original_decision_id"], digest)
                for value in inputs if value.get("budget_repair")
                for digest in value["budget_repair"]["deferred_event_sha256"]}
    selected = [event for event in events if (event["decision_id"], event["event_id"]) not in deferred]
    retained = [event for event in events if (event["decision_id"], event["event_id"]) in deferred]
    return selected, retained
