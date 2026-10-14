"""Bounded observation of already claimed orders, outside the submit lease."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .trading_execution import ExecutionReceipt, ExecutionState, TradePlan

TERMINAL = {ExecutionState.FILLED, ExecutionState.CANCELLED,
            ExecutionState.REJECTED, ExecutionState.SKIPPED}


def await_orders(plans: list[TradePlan], receipts: list[ExecutionReceipt], *,
                 reconcile: Callable[[TradePlan], ExecutionReceipt], deadline: datetime,
                 now: Callable[[], datetime], sleep: Callable[[float], None],
                 on_progress: Callable[[list[ExecutionReceipt]], None]) -> None:
    """Never submit: reconcile must reject a missing durable submit claim."""
    by_id = {plan.plan_id: plan for plan in plans}
    for receipt in receipts:
        plan = by_id.get(receipt.plan_id)
        if plan is None or receipt.plan_hash != plan.plan_hash or not receipt.submit_claim_id:
            if receipt.state not in TERMINAL:
                raise ValueError("MORNING_AWAIT_ORDER_CLAIM_UNPROVEN")
    while any(row.state not in TERMINAL for row in receipts):
        on_progress(receipts)
        current = now()
        if current >= deadline:
            return
        # Queued pre-auction ACKs do not yet need repeated fill-table reads.
        boundary = datetime.fromisoformat(by_id[receipts[0].plan_id].trade_date + "T09:30:00+08:00")
        if current < boundary and all(row.state in TERMINAL or
                (row.state in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL}
                 and not row.submit_chain_uncertain and not row.cancel_chain_uncertain)
                for row in receipts):
            sleep(min(10.0, (min(boundary, deadline) - current).total_seconds()))
            continue
        for index, previous in enumerate(receipts):
            if previous.state in TERMINAL or now() >= deadline:
                continue
            plan = by_id[previous.plan_id]
            observed = reconcile(plan)
            if (observed.plan_id != plan.plan_id or observed.plan_hash != plan.plan_hash
                    or observed.submit_claim_id != previous.submit_claim_id):
                raise ValueError("MORNING_AWAIT_ORDER_MAPPING_CHANGED")
            receipts[index] = observed
        on_progress(receipts)
        if any(row.state not in TERMINAL for row in receipts) and now() < deadline:
            sleep(min(10.0, (deadline - now()).total_seconds()))
