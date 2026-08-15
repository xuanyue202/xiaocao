"""Safe orchestration helpers for frozen Book B execution plans.

This module intentionally does not select candidates or change strategy
weights.  It validates or materializes board-lot sizing through the canonical
mode-switch allocator, then advances immutable plans through
:class:`TradingExecution`.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .book_b_allocation import (
    BookBAllocationFacts,
    allocate_frozen_rows,
    validate_allocation_rows,
)
from .foundersc_opencli import FounderscQuantOpenCLIAdapter
from .trading_execution import (
    BookBOwnershipEvidence,
    ExecutionReceipt,
    ExecutionStore,
    TradePlan,
    TradingExecution,
    TradingIncidentOutbox,
    trade_plan_from_frozen_row,
)


def read_frozen_rows(path: Path | str, *, date: str | None = None) -> list[dict[str, Any]]:
    """Read a JSONL freeze without silently dropping malformed rows."""
    source = Path(path)
    rows: list[dict[str, Any]] = []
    if not source.exists():
        raise FileNotFoundError(source)
    with source.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {source}:{number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"freeze row must be an object at {source}:{number}")
            if date is not None and str(row.get("date") or row.get("trade_date") or "")[:10] != date:
                continue
            rows.append(dict(row))
    return rows


def plans_from_frozen_rows(
    rows: Iterable[dict[str, Any]],
    *,
    environment: str,
    logical_account_id: str,
    strategy_sha: str = "unknown",
    now: datetime | None = None,
    side: str = "BUY",
    allocation: BookBAllocationFacts | None = None,
) -> list[TradePlan]:
    """Materialize all plans before executing any of them.

    The all-before-any validation prevents a malformed later row from leaving
    a partially started batch.  Selection, rank, and sizing remain upstream.
    """
    rows_list = [dict(row) for row in rows]
    normalized_side = str(side or "BUY").upper()
    if normalized_side == "BUY":
        if allocation is None:
            raise ValueError("ALLOCATION_PROOF_MISSING")
        if any(row.get("mode_exec_planned_shares") in (None, "") for row in rows_list):
            rows_list = allocate_frozen_rows(rows_list, allocation)
    for row in rows_list:
        if environment == "live" and row.get("book") in (None, ""):
            raise ValueError(f"live execution freeze must prove Book B: {row.get('code')}")
        row_book = str(row.get("book") or "B").strip().upper()
        if row_book != "B":
            raise ValueError(f"execution freeze is not Book B: {row.get('code')}")
        if normalized_side == "BUY":
            if row.get("mode_exec_star") is not True:
                raise ValueError(f"execution freeze row is not ★E: {row.get('code')}")
            if row.get("mode_trade_eligible") is not True:
                raise ValueError(f"execution freeze row is not executable: {row.get('code')}")
            if "executable_fillable" in row and row.get("executable_fillable") is not True:
                raise ValueError(f"execution freeze row is not fillable: {row.get('code')}")
            if environment == "live" and row.get("is_live") is not True:
                raise ValueError(f"live execution requires a live freeze row: {row.get('code')}")
        else:
            # A SELL intent is not a generic opposite-side order.  It must be
            # an explicit Book-B monitor decision bound to one owned lot and
            # still sellable under the current T+1/liquidity facts.
            if row.get("sell_authorized") is not True:
                if row.get("alert") == "SELL_TRIGGERED" and row.get("triggered") is True:
                    row["sell_authorized"] = True
                else:
                    raise ValueError(f"SELL_MONITOR_AUTHORIZATION_MISSING:{row.get('code')}")
            if not row.get("owned_lot_id"):
                raise ValueError(f"SELL_OWNED_LOT_MISSING:{row.get('code')}")
            if row.get("t1_blocked") is True:
                raise ValueError(f"SELL_T1_BLOCKED:{row.get('code')}")
            if any(row.get(key) for key in ("sell_block_reason", "sell_blocked_reason", "liquidity_block_reason")):
                raise ValueError(f"SELL_LIQUIDITY_BLOCKED:{row.get('code')}")
            if environment == "live" and row.get("is_live") is not True:
                raise ValueError(f"live execution requires a live freeze row: {row.get('code')}")
    if normalized_side == "BUY":
        _total, proof = validate_allocation_rows(rows_list, allocation)
        for row in rows_list:
            supplied = row.get("allocation_proof_hash")
            if supplied not in (None, "", proof):
                raise ValueError(f"ALLOCATION_PROOF_MISMATCH:{row.get('code')}")
            row["allocation_proof_hash"] = proof
    plans = [
        trade_plan_from_frozen_row(
            row,
            environment=environment,
            logical_account_id=logical_account_id,
            strategy_sha=strategy_sha,
            now=now,
            side=normalized_side,
        )
        for row in rows_list
    ]
    seen: set[str] = set()
    for plan in plans:
        if plan.plan_id in seen:
            raise ValueError(f"duplicate immutable plan id: {plan.plan_id}")
        seen.add(plan.plan_id)
    return plans


def execute_plans(
    plans: Iterable[TradePlan],
    *,
    execution: TradingExecution,
    broker: Any | None = None,
) -> list[ExecutionReceipt]:
    """Advance plans in deterministic input order through one execution port."""
    return [execution.execute(plan, broker) for plan in plans]


def build_foundersc_execution(
    state_dir: Path | str,
    *,
    profile: str | None = None,
    route: str = "manual-limit",
    now=None,
    notifier=None,
) -> tuple[TradingExecution, FounderscQuantOpenCLIAdapter]:
    """Build the durable Xiaocao engine and the read-only Founder adapter."""
    root = Path(state_dir)
    store = ExecutionStore(root / "events.jsonl")
    outbox = TradingIncidentOutbox(root / "incidents.jsonl")
    adapter = FounderscQuantOpenCLIAdapter(profile=profile, route=route)
    execution = TradingExecution(
        store=store,
        broker=adapter,
        ledger=BookBOwnershipEvidence(root / "book_b_ownership_evidence.jsonl"),
        outbox=outbox,
        now=now,
        notifier=notifier,
    )
    return execution, adapter


__all__ = [
    "build_foundersc_execution",
    "execute_plans",
    "plans_from_frozen_rows",
    "read_frozen_rows",
]
