"""Safe orchestration helpers for frozen Book B execution plans.

This module intentionally does not select candidates or allocate cash.  The
caller supplies rows already emitted by the deterministic morning freeze (or
explicit intent JSON); this layer only materializes immutable plans and
advances them through :class:`TradingExecution`.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .foundersc_opencli import FounderscQuantOpenCLIAdapter
from .trading_execution import (
    ExecutionReceipt,
    ExecutionStore,
    TradePlan,
    TradingAccountLedger,
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
) -> list[TradePlan]:
    """Materialize all plans before executing any of them.

    The all-before-any validation prevents a malformed later row from leaving
    a partially started batch.  Selection, rank, and sizing remain upstream.
    """
    rows_list = [dict(row) for row in rows]
    for row in rows_list:
        if environment == "live" and row.get("book") in (None, ""):
            raise ValueError(f"live execution freeze must prove Book B: {row.get('code')}")
        row_book = str(row.get("book") or "B").strip().upper()
        if row_book != "B":
            raise ValueError(f"execution freeze is not Book B: {row.get('code')}")
        if side.upper() == "BUY":
            if row.get("mode_exec_star") is not True:
                raise ValueError(f"execution freeze row is not ★E: {row.get('code')}")
            if row.get("mode_trade_eligible") is not True:
                raise ValueError(f"execution freeze row is not executable: {row.get('code')}")
            if "executable_fillable" in row and row.get("executable_fillable") is not True:
                raise ValueError(f"execution freeze row is not fillable: {row.get('code')}")
            if environment == "live" and row.get("is_live") is not True:
                raise ValueError(f"live execution requires a live freeze row: {row.get('code')}")
    plans = [
        trade_plan_from_frozen_row(
            row,
            environment=environment,
            logical_account_id=logical_account_id,
            strategy_sha=strategy_sha,
            now=now,
            side=side,
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
        ledger=TradingAccountLedger(root / "book_b_ledger.jsonl"),
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
