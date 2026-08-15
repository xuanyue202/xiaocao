"""Book B allocation proof and shared board-lot planning.

The morning paper writer remains the canonical account writer.  This module
only consumes its already-defined ``mode_switch.plan_board_lot_orders``
allocator (or validates its output) before an execution intent can exist.  It
does not choose modes, change weights, or maintain cash/equity state.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable

from xiaocao.strategy.mode_switch import plan_board_lot_orders

from .book_b_pricing import initial_limit_price


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


@dataclass(frozen=True)
class BookBAllocationFacts:
    """Authoritative settled-NAV/cash facts for one frozen batch.

    ``settled_nav`` is the rolling Book B basis: initial capital is only the
    first value; realized gains/losses change it on later batches.  The caller
    must source these facts from the canonical account/broker readback.  This
    type deliberately contains no mutable account state.
    """

    settled_nav: float
    available_cash: float
    current_open_exposure: float = 0.0
    batch_ratio: float = 0.50
    total_exposure_ratio: float = 1.0
    deploy_factor: float = 1.0
    fee_rate: float = 0.0001
    source: str = "explicit"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BookBAllocationFacts":
        try:
            return cls(
                settled_nav=float(payload["settled_nav"]),
                available_cash=float(payload["available_cash"]),
                current_open_exposure=float(payload.get("current_open_exposure", 0.0)),
                batch_ratio=float(payload.get("batch_ratio", 0.50)),
                total_exposure_ratio=float(payload.get("total_exposure_ratio", 1.0)),
                deploy_factor=float(payload.get("deploy_factor", 1.0)),
                fee_rate=float(payload.get("fee_rate", 0.0001)),
                source=str(payload.get("source") or "explicit"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ALLOCATION_FACTS_INVALID") from exc

    def validation_error(self) -> str | None:
        values = (
            self.settled_nav,
            self.available_cash,
            self.current_open_exposure,
            self.batch_ratio,
            self.total_exposure_ratio,
            self.deploy_factor,
            self.fee_rate,
        )
        if any(not math.isfinite(float(value)) for value in values):
            return "ALLOCATION_FACTS_NOT_FINITE"
        if self.settled_nav <= 0:
            return "SETTLED_NAV_INVALID"
        if self.available_cash < 0 or self.current_open_exposure < 0:
            return "ALLOCATION_CASH_OR_EXPOSURE_INVALID"
        if not (0 < self.batch_ratio <= 1):
            return "BATCH_RATIO_INVALID"
        if not (0 < self.total_exposure_ratio <= 1):
            return "TOTAL_EXPOSURE_RATIO_INVALID"
        if not (0 <= self.deploy_factor <= 1):
            return "DEPLOY_FACTOR_INVALID"
        if self.fee_rate < 0:
            return "FEE_RATE_INVALID"
        if not str(self.source or "").strip():
            return "ALLOCATION_SOURCE_MISSING"
        return None

    @property
    def batch_budget(self) -> float:
        return max(0.0, self.settled_nav * self.batch_ratio * self.deploy_factor)

    @property
    def exposure_budget(self) -> float:
        return max(
            0.0,
            self.settled_nav * self.total_exposure_ratio - self.current_open_exposure,
        )

    @property
    def cash_limit(self) -> float:
        return min(self.available_cash, self.batch_budget, self.exposure_budget)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "settled_nav": round(self.settled_nav, 6),
            "available_cash": round(self.available_cash, 6),
            "current_open_exposure": round(self.current_open_exposure, 6),
            "batch_ratio": round(self.batch_ratio, 6),
            "total_exposure_ratio": round(self.total_exposure_ratio, 6),
            "deploy_factor": round(self.deploy_factor, 6),
            "fee_rate": round(self.fee_rate, 8),
            "source": self.source,
        }

    def proof_hash(self, rows: Iterable[dict[str, Any]]) -> str:
        entries = []
        for row in rows:
            entries.append({
                "code": str(row.get("code") or ""),
                "mode": str(row.get("mode") or ""),
                "mode_state": str(row.get("mode_state") or ""),
                "target_weight": round(float(row.get("mode_exec_target_weight") or 0.0), 6),
                "mode_exec_star": row.get("mode_exec_star") is True,
                "mode_trade_eligible": row.get("mode_trade_eligible") is True,
                "shares": int(row.get("mode_exec_planned_shares") or row.get("shares") or 0),
                "planned_cash": round(float(row.get("mode_exec_planned_cash_out") or 0.0), 6),
                "open": round(float(row.get("open") or 0.0), 6),
                "basket_price": round(float(row.get("basket_price") or 0.0), 6),
                "execution_price": round(float(row.get("execution_price") or 0.0), 6),
            })
        entries.sort(key=lambda item: (item["code"], item["mode"]))
        return hashlib.sha256(_canonical({"facts": self.canonical_payload(), "rows": entries})).hexdigest()


def _row_cost(row: dict[str, Any], facts: BookBAllocationFacts) -> float:
    shares = int(row.get("mode_exec_planned_shares") or row.get("shares") or 0)
    price = initial_limit_price(row.get("open"), row.get("basket_price"))
    if shares <= 0 or price is None:
        raise ValueError(f"ALLOCATION_PRICE_OR_SHARES_MISSING:{row.get('code')}")
    conservative_cost = float(shares) * float(price) * (1.0 + facts.fee_rate)
    stated = _number(row.get("mode_exec_planned_cash_out")) or 0.0
    # Never let an under-reported upstream cost evade the batch/exposure caps.
    return max(conservative_cost, stated)


def validate_allocation_rows(
    rows: Iterable[dict[str, Any]],
    facts: BookBAllocationFacts,
    *,
    side: str = "BUY",
) -> tuple[float, str]:
    """Validate existing allocator output and return ``(cost, proof_hash)``."""
    error = facts.validation_error()
    if error:
        raise ValueError(error)
    rows_list = [dict(row) for row in rows]
    if side.upper() != "BUY":
        return 0.0, facts.proof_hash(rows_list)
    if not rows_list:
        raise ValueError("ALLOCATION_EMPTY")
    if len(rows_list) > 3:
        raise ValueError("ALLOCATION_SLOT_LIMIT")
    modes: set[str] = set()
    total = 0.0
    for row in rows_list:
        code = str(row.get("code") or "")
        if row.get("mode_exec_star") is not True or row.get("mode_trade_eligible") is not True:
            raise ValueError(f"ALLOCATION_ROW_NOT_EXECUTABLE:{code}")
        if str(row.get("mode_state") or "") not in {"ACTIVE", "PROVISIONAL"}:
            raise ValueError(f"ALLOCATION_MODE_NOT_ACTIVE:{code}")
        if code.endswith(".BJSE"):
            raise ValueError(f"ALLOCATION_BJSE_BLOCKED:{code}")
        mode = str(row.get("mode") or "")
        if not mode or mode in modes:
            raise ValueError(f"ALLOCATION_MODE_DUPLICATE:{code}")
        modes.add(mode)
        weight = _number(row.get("mode_exec_target_weight"))
        if weight is None or weight <= 0 or weight > 0.50 + 1e-9:
            raise ValueError(f"ALLOCATION_WEIGHT_INVALID:{code}")
        shares = int(row.get("mode_exec_planned_shares") or 0)
        if shares < 100 or shares % 100:
            raise ValueError(f"ALLOCATION_SHARES_INVALID:{code}")
        total += _row_cost(row, facts)
    if total > facts.available_cash + 1e-6:
        raise ValueError("ALLOCATION_CASH_LIMIT")
    if total > facts.batch_budget + 1e-6:
        raise ValueError("ALLOCATION_BATCH_LIMIT")
    if total > facts.exposure_budget + 1e-6:
        raise ValueError("ALLOCATION_TOTAL_EXPOSURE_LIMIT")
    if sum(float(row.get("mode_exec_target_weight") or 0.0) for row in rows_list) > facts.batch_ratio * facts.deploy_factor + 1e-9:
        raise ValueError("ALLOCATION_WEIGHT_SUM_LIMIT")
    proof = facts.proof_hash(rows_list)
    for row in rows_list:
        supplied = row.get("allocation_proof_hash")
        if supplied not in (None, "", proof):
            raise ValueError(f"ALLOCATION_PROOF_MISMATCH:{row.get('code')}")
    return round(total, 6), proof


def allocate_frozen_rows(
    rows: Iterable[dict[str, Any]],
    facts: BookBAllocationFacts,
) -> list[dict[str, Any]]:
    """Use the existing mode-switch allocator to materialize board lots."""
    error = facts.validation_error()
    if error:
        raise ValueError(error)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidate = dict(row)
        if candidate.get("mode_exec_star") is not True or candidate.get("mode_trade_eligible") is not True:
            continue
        price = initial_limit_price(candidate.get("open"), candidate.get("basket_price"))
        if price is None:
            continue
        candidate["execution_price"] = price
        candidates.append(candidate)
    planned = plan_board_lot_orders(
        candidates,
        nav=facts.settled_nav,
        cash_limit=facts.cash_limit,
        fee_rate=facts.fee_rate,
        price_key="execution_price",
        max_candidates=3,
        max_batch_ratio=facts.batch_ratio * facts.deploy_factor,
        target_scale=facts.deploy_factor,
    )
    if not planned:
        raise ValueError("ALLOCATION_EMPTY")
    _, proof = validate_allocation_rows(planned, facts)
    for row in planned:
        row["allocation_proof_hash"] = proof
    return planned


__all__ = [
    "BookBAllocationFacts",
    "allocate_frozen_rows",
    "validate_allocation_rows",
]
