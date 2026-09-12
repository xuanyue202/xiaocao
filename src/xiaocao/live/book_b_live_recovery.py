"""Resume, reconcile or close one durable Book-B plan without a new producer."""
from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .book_b_live_morning import (
    BookBLiveMorningConfig, BookBLiveMorningReceipt, _event_chain_proven,
    _plan_intent_path, read_durable_live_plan_intent, run_book_b_live_morning,
    write_book_b_live_morning_receipt,
)
from .trading_execution import (
    ExecutionReceipt, ExecutionState, ExecutionStore, TradePlan, account_writer_lock,
)
from .book_b_live_lifecycle import open_execution_plan_ids

UNCLAIMED = {ExecutionState.PLANNED, ExecutionState.VALIDATED, ExecutionState.PREPARED}
TERMINAL = {ExecutionState.FILLED, ExecutionState.CANCELLED, ExecutionState.REJECTED,
            ExecutionState.SKIPPED}


def _history(state_dir: Path, plan: TradePlan) -> list[dict]:
    path = state_dir / "events.jsonl"
    # ExecutionStore's compatibility reader skips malformed lines. A recovery
    # must not interpret a corrupt submit claim as an absent submit claim.
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("LIVE_RECOVERY_EVENT_INVALID")
    events = [row for row in rows if row.get("plan_id") == plan.plan_id]
    if not _event_chain_proven(plan.plan_id, events) or any(
        row.get("plan_hash") != plan.plan_hash for row in events
    ):
        raise ValueError("LIVE_RECOVERY_EVENT_CHAIN_INVALID")
    return events


def _has_possible_write(events: list[dict]) -> bool:
    for event in events:
        receipt = ExecutionReceipt.from_dict(event["receipt"])
        if (receipt.state not in UNCLAIMED or receipt.submit_claim_id
                or receipt.cancel_claim_id or receipt.broker_order_id
                or receipt.submit_chain_uncertain or receipt.cancel_chain_uncertain
                or receipt.filled_shares or receipt.attempt):
            return True
    return False


def check_monitor_pending_plans(state_dir: Path) -> tuple[str, ...]:
    """Prove which open intents are only local BUY reservations.

    These remain open for their original owner. They cannot by themselves
    block monitoring of owned lots; SELL intents and uncertain effects can.
    """
    deferred = []
    with account_writer_lock(state_dir / "account_writer_locks", "primary"):
        for plan_id in open_execution_plan_ids(state_dir):
            path = _plan_intent_path(state_dir, plan_id)
            if not path.is_file():
                raise ValueError("LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED")
            plan = read_durable_live_plan_intent(json.loads(path.read_text()))
            if plan.plan_id != plan_id or plan.logical_account_id != "primary":
                raise ValueError("LIVE_RECOVERY_PLAN_BINDING_MISMATCH")
            if plan.side == "BUY" and not _has_possible_write(_history(state_dir, plan)):
                deferred.append(plan_id)
            else:
                raise ValueError("LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED")
    return tuple(deferred)


def close_unsubmitted_plan(state_dir: Path, plan: TradePlan, *, reason: str) -> ExecutionReceipt:
    """Close only the local unclaimed intent; never imply a service cancellation."""
    with account_writer_lock(state_dir / "account_writer_locks", plan.logical_account_id):
        events = _history(state_dir, plan)
        store = ExecutionStore(state_dir / "events.jsonl")
        current = store.current(plan.plan_id)
        if current is not None and current.state in TERMINAL:
            return current
        if _has_possible_write(events):
            raise ValueError("LIVE_RECOVERY_RECONCILE_ONLY")
        return store.append(
            plan=plan,
            receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.SKIPPED,
                                     reason=reason, remaining_shares=plan.shares,
                                     active=False, next_action="stop"),
            kind="unsubmitted_intent_closed",
            details={"closure_scope": "local_unclaimed_intent", "broker_write_count": 0},
        )


def run_book_b_live_recovery(
    config: BookBLiveMorningConfig, *, plan_id: str, action: str = "resume",
    now=lambda: datetime.now(timezone.utc), **callbacks,
) -> BookBLiveMorningReceipt:
    """Reuse the normal runner only for a proven unclaimed, unchanged BUY.

    Possible writes go directly to TradingExecution's reconcile path. Closed
    plans return their prior result. Neither branch opens a new review window.
    """
    if action not in {"resume", "reconcile", "close"}:
        raise ValueError("LIVE_RECOVERY_ACTION_INVALID")
    config = replace(config, resume_plan_id=plan_id)
    started = now()
    payload = json.loads(_plan_intent_path(config.state_dir, plan_id).read_text())
    plan = read_durable_live_plan_intent(payload)
    if plan.plan_id != plan_id or plan.logical_account_id != config.logical_account_id:
        raise ValueError("LIVE_RECOVERY_PLAN_BINDING_MISMATCH")
    events = _history(config.state_dir, plan)
    current = ExecutionStore(config.state_dir / "events.jsonl").current(plan_id)
    possible_write = _has_possible_write(events)
    deadline = plan.recovery_deadline
    failure = None
    if current is not None and current.state in TERMINAL:
        result = current
    elif action == "close" or (not possible_write and started >= deadline):
        result = close_unsubmitted_plan(
            config.state_dir, plan,
            reason="UNSUBMITTED_INTENT_EXPIRED" if started >= deadline
            else "OWNER_ABANDONED_UNSUBMITTED_INTENT",
        )
    elif possible_write:
        # CLAIMED/UNKNOWN are already durable. The execution port owns query
        # and mapping; prepare and review callbacks are deliberately unused.
        result = current
        try:
            result = callbacks["execute"](plan)
            for _ in range(3):
                if result.state in TERMINAL:
                    break
                if callbacks.get("wait_for_reconcile"):
                    callbacks["wait_for_reconcile"]()
                result = callbacks["execute"](plan)
        except (OSError, ValueError, RuntimeError) as exc:
            failure = f"LIVE_RECOVERY_RECONCILE_FAILED:{exc}"
            result = ExecutionStore(config.state_dir / "events.jsonl").current(plan_id) or result
    else:
        if action == "reconcile":
            raise ValueError("LIVE_RECOVERY_UNSUBMITTED_USE_RESUME_OR_CLOSE")
        if plan.trade_date != config.trade_date or plan.side != "BUY":
            raise ValueError("LIVE_RECOVERY_BUY_DATE_MISMATCH")
        return run_book_b_live_morning(config, now=now, **callbacks)
    receipt = BookBLiveMorningReceipt(
        trade_date=config.trade_date,
        status="blocked" if failure else "completed" if result.state == ExecutionState.FILLED else
               "skipped" if result.state in TERMINAL else "blocked",
        reason=failure or result.reason or result.state.value,
        plan_count=1, execution_receipts=(result.as_dict(),), preparation_receipts=(),
        freeze_path=str(config.freeze_path), allocation_facts_path=str(config.allocation_facts_path),
        state_path=str(config.state_dir), run_id=f"{config.trade_date}-{uuid.uuid4().hex[:12]}",
        recovery_of=plan_id, persisted_plan_ids=(plan_id,),
        failed_stage="reconcile" if failure else None,
        stage_times={"started": started.isoformat(), "finished": now().isoformat()},
    )
    write_book_b_live_morning_receipt(config, receipt)
    return receipt
