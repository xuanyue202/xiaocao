"""Broker-neutral Book B execution seam.

The deterministic Book B selector remains outside this module.  It hands this
module an immutable :class:`TradePlan`; the module owns the durable claim,
broker receipt lifecycle, real-capital gate, retry/reconcile policy, and
incident handoff.  A broker adapter is deliberately small so a Web/OpenCLI
implementation can change without leaking DOM details into Xiaocao.

The module is broker-neutral.  A live adapter may submit only after it proves
an exact route, account binding and reconciliation capability.  A first-order
probe may leave receipt mapping pending; the one claimed submit must then prove
its broker order and strategy identifiers or become reconcile-only UNKNOWN.
Paper/simulation adapters are used by the contract tests.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from . import notify as notify_module
from .book_b_pricing import initial_limit_price
from .buy_guards import evaluate_buy_market_guard
from .safety import DEFAULT_AUTH_PATH, DEFAULT_AUDIT_PATH, require_capital_action
from .capital_keychain import CapitalRuntimeUnavailable


class ExecutionState(str, Enum):
    PLANNED = "planned"
    VALIDATED = "validated"
    PREPARED = "prepared"
    CLAIMED = "claimed"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"
    SKIPPED = "skipped"


class BrokerStatus(str, Enum):
    PREPARED = "prepared"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


TERMINAL_STATES = frozenset(
    {
        ExecutionState.FILLED,
        ExecutionState.CANCELLED,
        ExecutionState.REJECTED,
        ExecutionState.SKIPPED,
    }
)

_TRADING_GUARD_STATUSES = frozenset({
    "ok", "t", "trading", "open", "normal", "交易中", "正常",
})
_LIMIT_DOWN_GUARD_STATUSES = frozenset({"limit_down", "limitdown", "跌停"})
_UNAVAILABLE_GUARD_STATUSES = frozenset({
    "", "unknown", "stale", "unavailable", "s", "suspended", "halt",
    "stopped", "停牌", "暂停交易",
})
_SELL_AUTHORIZED_REASONS = frozenset({
    "AI_EVENT_RISK_EXIT",
    "HARD_STOP",
    "TRAILING_STOP",
    "EOD_DISCIPLINE_1455",
})
_SELL_AUTHORIZED_PHASES = frozenset({"event_risk", "risk_floor", "eod_discipline"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_tz_aware_datetime(value: object) -> datetime | None:
    """Parse a decision timestamp without inventing a timezone."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


_SENSITIVE_EVIDENCE_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "credential",
    "authorization",
    "otp",
)


def _safe_evidence(value: object, *, depth: int = 0) -> object:
    """Keep small locator proofs useful while excluding credential material."""
    if depth > 3:
        return "<depth-limit>"
    if isinstance(value, dict):
        safe: dict[str, object] = {}
        for raw_key, raw_value in list(value.items())[:64]:
            key = str(raw_key)
            lowered = key.lower()
            if any(marker in lowered for marker in _SENSITIVE_EVIDENCE_MARKERS):
                continue
            safe[key[:128]] = _safe_evidence(raw_value, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple)):
        return [_safe_evidence(item, depth=depth + 1) for item in list(value)[:64]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:512]
    return str(value)[:512]


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_guard_status(value: object) -> str:
    raw = str(value or "").strip().lower()
    # Xiaocao's current SSE detail feed emits values such as ``T100`` while
    # the bundled upstream UI documents the leading ``T`` as continuous
    # auction.  Preserve fail-closed handling for every other unknown prefix.
    if raw in _TRADING_GUARD_STATUSES or (
        raw.startswith("t") and raw[1:].isdigit()
    ):
        return "ok"
    if raw in _LIMIT_DOWN_GUARD_STATUSES:
        return "limit_down"
    return "unavailable"


def _parse_market_guard_observed_at(value: object, trade_date: str) -> datetime | None:
    """Bind the proprietary feed clock to its immutable China trade date."""
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed
    text = str(value or "").strip()
    for clock_format in ("%H:%M:%S:%f", "%H:%M:%S", "%H%M%S"):
        try:
            clock = datetime.strptime(text, clock_format).time()
        except ValueError:
            continue
        try:
            day = datetime.fromisoformat(trade_date).date()
        except ValueError:
            return None
        return datetime.combine(day, clock, tzinfo=ZoneInfo("Asia/Shanghai"))
    return None


@dataclass(frozen=True)
class TradePlan:
    """Immutable economic intent passed from the deterministic Book B spine."""

    plan_id: str
    strategy_run_id: str
    snapshot_ref: str
    strategy_sha: str
    trade_date: str
    book: str
    logical_account_id: str
    environment: str
    code: str
    name: str
    side: str
    shares: int
    limit_price: float
    basket_price: float | None
    market_guard_status: str
    created_at: datetime
    recovery_deadline: datetime
    owned_lot_id: str | None = None
    submit_not_before: datetime | None = None
    price_rule: str = ""
    market_guard_required: bool = False
    market_guard_observed_at: datetime | None = None
    market_guard_latest_price: float | None = None
    market_guard_down_price: float | None = None
    allocation_proof_hash: str | None = None
    sell_authorized: bool = False
    sell_reason: str | None = None
    sell_decision_phase: str | None = None
    sell_decision_at: datetime | None = None
    sell_block_reason: str | None = None

    @property
    def notional(self) -> float:
        return round(float(self.limit_price) * int(self.shares), 2)

    @property
    def plan_hash(self) -> str:
        return hashlib.sha256(_canonical(self.canonical_payload())).hexdigest()

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "strategy_run_id": self.strategy_run_id,
            "snapshot_ref": self.snapshot_ref,
            "strategy_sha": self.strategy_sha,
            "trade_date": self.trade_date,
            "book": self.book,
            "logical_account_id": self.logical_account_id,
            "environment": self.environment,
            "code": self.code,
            "name": self.name,
            "side": self.side,
            "shares": int(self.shares),
            "limit_price": round(float(self.limit_price), 6),
            "basket_price": None if self.basket_price is None else round(float(self.basket_price), 6),
            "market_guard_status": self.market_guard_status,
            "created_at": _iso(self.created_at),
            "recovery_deadline": _iso(self.recovery_deadline),
            "owned_lot_id": self.owned_lot_id,
            "submit_not_before": _iso(self.submit_not_before),
            "price_rule": self.price_rule,
            "market_guard_required": self.market_guard_required,
            "market_guard_observed_at": _iso(self.market_guard_observed_at),
            "market_guard_latest_price": self.market_guard_latest_price,
            "market_guard_down_price": self.market_guard_down_price,
            "allocation_proof_hash": self.allocation_proof_hash,
            "sell_authorized": self.sell_authorized,
            "sell_reason": self.sell_reason,
            "sell_decision_phase": self.sell_decision_phase,
            "sell_decision_at": _iso(self.sell_decision_at),
            "sell_block_reason": self.sell_block_reason,
        }

    def validation_error(self) -> str | None:
        if not self.plan_id.strip():
            return "PLAN_ID_MISSING"
        if self.book != "B":
            return "BOOK_NOT_B"
        if not self.logical_account_id.strip():
            return "LOGICAL_ACCOUNT_MISSING"
        if self.environment not in {"mock", "live"}:
            return "ENVIRONMENT_INVALID"
        if not self.code.strip() or not self.name.strip():
            return "SECURITY_IDENTITY_MISSING"
        if self.side.upper() not in {"BUY", "SELL"}:
            return "SIDE_INVALID"
        if int(self.shares) <= 0 or int(self.shares) % 100:
            return "SHARES_NOT_BOARD_LOT"
        if float(self.limit_price) <= 0:
            return "LIMIT_PRICE_INVALID"
        if self.side.upper() == "BUY":
            if self.basket_price is None or float(self.basket_price) <= 0:
                return "BASKET_PRICE_MISSING"
            if float(self.limit_price) > float(self.basket_price) + 1e-6:
                return "LIMIT_ABOVE_BASKET"
            if self.environment == "live" and not self.allocation_proof_hash:
                return "ALLOCATION_PROOF_MISSING"
            if str(self.market_guard_status or "").strip().lower() not in (
                _TRADING_GUARD_STATUSES
                | _LIMIT_DOWN_GUARD_STATUSES
                | _UNAVAILABLE_GUARD_STATUSES
            ):
                return "MARKET_GUARD_INVALID"
        else:
            if not self.owned_lot_id:
                return "OWNED_LOT_ID_MISSING"
            if not self.sell_authorized:
                return "SELL_AUTHORIZATION_MISSING"
            if self.sell_reason not in _SELL_AUTHORIZED_REASONS:
                return "SELL_REASON_NOT_AUTHORIZED"
            if self.sell_decision_phase not in _SELL_AUTHORIZED_PHASES:
                return "SELL_PHASE_NOT_AUTHORIZED"
            if self.sell_block_reason:
                return f"SELL_BLOCKED:{self.sell_block_reason}"
            if self.sell_decision_at is None or self.sell_decision_at.tzinfo is None:
                return "SELL_DECISION_AT_NOT_TZ_AWARE"
        if self.recovery_deadline.tzinfo is None:
            return "RECOVERY_DEADLINE_NOT_TZ_AWARE"
        if self.submit_not_before is not None and self.submit_not_before.tzinfo is None:
            return "SUBMIT_NOT_BEFORE_NOT_TZ_AWARE"
        return None

    def guard_reason(self, *, now: datetime | None = None) -> str | None:
        if self.side.upper() != "BUY":
            return None
        status = str(self.market_guard_status or "unavailable").strip().lower()
        if status in {"limit_down", "limitdown", "跌停"}:
            return "LIMIT_DOWN_BUY_BLOCKED"
        if status in _UNAVAILABLE_GUARD_STATUSES:
            return "LIMIT_DOWN_CHECK_UNAVAILABLE"
        if self.market_guard_required and (
            self.market_guard_observed_at is None
            or self.market_guard_latest_price is None
            or self.market_guard_down_price is None
        ):
            return "LIMIT_DOWN_CHECK_UNAVAILABLE"
        if self.market_guard_required:
            allowed, reason, _evidence = evaluate_buy_market_guard(
                {
                    "market_guard_required": True,
                    "market_guard_status": self.market_guard_status,
                    "market_price": self.market_guard_latest_price,
                    "down_price": self.market_guard_down_price,
                    "market_observed_at": _iso(self.market_guard_observed_at),
                    "trade_date": self.trade_date,
                },
                require_authoritative=True,
                now=now,
            )
            if not allowed:
                return reason or "LIMIT_DOWN_CHECK_UNAVAILABLE"
        return None

    def describe(self, *, requested_shares: int | None = None) -> str:
        shares = int(self.shares if requested_shares is None else requested_shares)
        return (
            f"book={self.book} env={self.environment} account={self.logical_account_id} "
            f"{self.side.upper()} {self.code} {self.name} price={self.limit_price:.4f} "
            f"basket={self.basket_price if self.basket_price is not None else '-'} shares={shares} "
            f"trade_date={self.trade_date} deadline={_iso(self.recovery_deadline)} plan_id={self.plan_id} "
            f"lot={self.owned_lot_id or '-'} sell_reason={self.sell_reason or '-'}"
        )


@dataclass(frozen=True)
class BrokerCapability:
    """Read-only proof that an adapter is bound to the requested account/mode."""

    ready: bool
    environment: str
    logical_account_id: str
    supports_submit: bool = False
    supports_reconcile: bool = False
    route: str = ""
    account_binding: str = ""
    locator_proof: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    manual_position_shares: int | None = None
    owned_position_shares: int | None = None
    sellable_shares: int | None = None
    t1_blocked: bool | None = None
    position_source: str = ""
    template_name: str | None = None
    template_version: str | None = None

    @classmethod
    def from_template(cls, payload: dict[str, Any]) -> "BrokerCapability":
        caps = payload.get("capabilities")
        caps = dict(caps) if isinstance(caps, dict) else {}
        locator_proof = _safe_evidence(payload.get("locator_proof") or {})
        return cls(
            ready=str(payload.get("status") or "").lower() in {"ok", "ready", "prepared"},
            environment=str(payload.get("environment") or ""),
            logical_account_id=str(payload.get("logical_account_id") or ""),
            supports_submit=bool(payload.get("submit_capability") or caps.get("submit")),
            supports_reconcile=bool(
                payload.get("reconcile_capability")
                if "reconcile_capability" in payload
                else caps.get("reconcile", False)
            ),
            route=str(payload.get("route") or ""),
            account_binding=str(payload.get("account_binding") or ""),
            locator_proof=locator_proof if isinstance(locator_proof, dict) else {},
            capabilities=caps,
            reason=str(payload.get("reason") or ""),
            manual_position_shares=_optional_int(payload.get("manual_position_shares")),
            owned_position_shares=_optional_int(payload.get("owned_position_shares")),
            sellable_shares=_optional_int(payload.get("sellable_shares")),
            t1_blocked=payload.get("t1_blocked") if isinstance(payload.get("t1_blocked"), bool) else None,
            position_source=str(payload.get("position_source") or ""),
            template_name=str(payload.get("template_name") or "") or None,
            template_version=str(payload.get("template_version") or "") or None,
        )


@dataclass(frozen=True)
class BrokerReceipt:
    """Normalized adapter output; raw DOM/API data never crosses this seam.

    ``filled_shares`` is cumulative for the broker order identified by
    ``order_id``.  The execution engine carries the plan-level total across
    replacement orders; adapters that cannot prove a fill leave it at zero
    (or return ``UNKNOWN``) rather than guessing.
    """

    status: str | BrokerStatus
    order_id: str | None = None
    strategy_id: str | None = None
    receipt_mapping: bool | None = None
    requested_shares: int | None = None
    filled_shares: int = 0
    remaining_shares: int | None = None
    order_price: float | None = None
    fill_price: float | None = None
    latest_price: float | None = None
    active: bool | None = None
    retry_allowed: bool | None = None
    market_guard_status: str | None = None
    market_guard_observed_at: datetime | None = None
    market_guard_down_price: float | None = None
    template_name: str | None = None
    template_version: str | None = None
    account_binding: str | None = None
    locator_proof: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    error_code: str | None = None
    observed_at: datetime | None = None
    submitted_at: datetime | None = None
    cancelled_at: datetime | None = None
    conclusive: bool = True
    echoed: dict[str, Any] = field(default_factory=dict)
    field_readback: dict[str, Any] = field(default_factory=dict)

    def normalized_status(self) -> BrokerStatus:
        raw = self.status.value if isinstance(self.status, BrokerStatus) else str(self.status or "").strip().lower()
        aliases = {
            "ack": BrokerStatus.ACCEPTED,
            "accepted": BrokerStatus.ACCEPTED,
            "submitted": BrokerStatus.ACCEPTED,
            "working": BrokerStatus.ACCEPTED,
            "partial_fill": BrokerStatus.PARTIAL,
            "partially_filled": BrokerStatus.PARTIAL,
            "cancelled": BrokerStatus.CANCELLED,
            "canceled": BrokerStatus.CANCELLED,
            "rejected": BrokerStatus.REJECTED,
            "error": BrokerStatus.REJECTED,
            "unknown": BrokerStatus.UNKNOWN,
            "timeout": BrokerStatus.UNKNOWN,
        }
        return aliases.get(raw, BrokerStatus(raw) if raw in {item.value for item in BrokerStatus} else BrokerStatus.UNKNOWN)


class BrokerAdapter(Protocol):
    def probe(self, plan: TradePlan) -> BrokerCapability: ...

    def prepare(self, plan: TradePlan, *, requested_shares: int | None = None) -> BrokerReceipt: ...

    def submit(self, plan: TradePlan, claim_id: str, *, requested_shares: int | None = None) -> BrokerReceipt: ...

    def reconcile(self, plan: TradePlan, previous: dict[str, Any]) -> BrokerReceipt: ...

    def recover(self, plan: TradePlan, error: str) -> BrokerReceipt: ...


@dataclass(frozen=True)
class ExecutionReceipt:
    plan_id: str
    plan_hash: str
    state: ExecutionState
    reason: str = ""
    filled_shares: int = 0
    remaining_shares: int = 0
    broker_order_id: str | None = None
    broker_strategy_id: str | None = None
    broker_status: str | None = None
    receipt_mapping: bool | None = None
    submit_chain_uncertain: bool = False
    order_price: float | None = None
    fill_price: float | None = None
    latest_price: float | None = None
    active: bool | None = None
    market_guard_status: str | None = None
    market_guard_observed_at: datetime | None = None
    market_guard_down_price: float | None = None
    template_name: str | None = None
    template_version: str | None = None
    account_binding: str | None = None
    locator_proof: dict[str, Any] = field(default_factory=dict)
    attempt: int = 0
    next_action: str = ""
    event_id: str | None = None
    observed_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "state": self.state.value,
            "reason": self.reason,
            "filled_shares": self.filled_shares,
            "remaining_shares": self.remaining_shares,
            "broker_order_id": self.broker_order_id,
            "broker_strategy_id": self.broker_strategy_id,
            "broker_status": self.broker_status,
            "receipt_mapping": self.receipt_mapping,
            "submit_chain_uncertain": self.submit_chain_uncertain,
            "order_price": self.order_price,
            "fill_price": self.fill_price,
            "latest_price": self.latest_price,
            "active": self.active,
            "market_guard_status": self.market_guard_status,
            "market_guard_observed_at": _iso(self.market_guard_observed_at),
            "market_guard_down_price": self.market_guard_down_price,
            "template_name": self.template_name,
            "template_version": self.template_version,
            "account_binding": self.account_binding,
            "locator_proof": _safe_evidence(self.locator_proof),
            "attempt": self.attempt,
            "next_action": self.next_action,
            "event_id": self.event_id,
            "observed_at": _iso(self.observed_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionReceipt":
        locator_proof = _safe_evidence(payload.get("locator_proof") or {})
        return cls(
            plan_id=str(payload.get("plan_id") or ""),
            plan_hash=str(payload.get("plan_hash") or ""),
            state=ExecutionState(str(payload.get("state") or ExecutionState.PLANNED.value)),
            reason=str(payload.get("reason") or ""),
            filled_shares=int(payload.get("filled_shares") or 0),
            remaining_shares=int(payload.get("remaining_shares") or 0),
            broker_order_id=payload.get("broker_order_id"),
            broker_strategy_id=payload.get("broker_strategy_id"),
            broker_status=payload.get("broker_status"),
            receipt_mapping=(
                payload.get("receipt_mapping")
                if isinstance(payload.get("receipt_mapping"), bool)
                else None
            ),
            submit_chain_uncertain=(
                payload.get("submit_chain_uncertain") is True
                or payload.get("submit_uncertain") is True
            ),
            order_price=_optional_float(payload.get("order_price")),
            fill_price=_optional_float(payload.get("fill_price")),
            latest_price=_optional_float(payload.get("latest_price")),
            active=payload.get("active") if isinstance(payload.get("active"), bool) else None,
            market_guard_status=payload.get("market_guard_status"),
            market_guard_observed_at=_parse_datetime(payload.get("market_guard_observed_at")),
            market_guard_down_price=_optional_float(payload.get("market_guard_down_price")),
            template_name=payload.get("template_name"),
            template_version=payload.get("template_version"),
            account_binding=payload.get("account_binding"),
            locator_proof=locator_proof if isinstance(locator_proof, dict) else {},
            attempt=_optional_int(payload.get("attempt")) or 0,
            next_action=str(payload.get("next_action") or ""),
            event_id=payload.get("event_id"),
            observed_at=_parse_datetime(payload.get("observed_at")),
        )


class ExecutionStore:
    """Append-only hash-chained execution events with a per-store lock."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def events(self, plan_id: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        handle = self._locked()
        try:
            rows = []
            with self.path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if row.get("plan_id") == plan_id:
                        rows.append(row)
            return rows
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def current(self, plan_id: str) -> ExecutionReceipt | None:
        rows = self.events(plan_id)
        if not rows:
            return None
        latest = rows[-1].get("receipt") or {}
        return ExecutionReceipt.from_dict(latest)

    def append(
        self,
        *,
        plan: TradePlan,
        receipt: ExecutionReceipt,
        kind: str = "transition",
        details: dict[str, Any] | None = None,
    ) -> ExecutionReceipt:
        handle = self._locked()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            previous_hash: str | None = None
            sequence = 0
            if self.path.exists():
                with self.path.open(encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            row = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        if row.get("plan_id") == plan.plan_id:
                            previous_hash = row.get("event_hash")
                            sequence = max(sequence, int(row.get("sequence") or 0))
            event = {
                "schema_version": 1,
                "event_id": uuid.uuid4().hex,
                "sequence": sequence + 1,
                "ts": _iso(_utcnow()),
                "kind": kind,
                "plan_id": plan.plan_id,
                "plan_hash": plan.plan_hash,
                "state": receipt.state.value,
                "previous_hash": previous_hash,
                "receipt": {**receipt.as_dict(), "event_id": None},
                "details": details or {},
            }
            event["receipt"]["event_id"] = event["event_id"]
            event["event_hash"] = hashlib.sha256(_canonical(event)).hexdigest()
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return ExecutionReceipt(
                **{**asdict(receipt), "event_id": event["event_id"]},
            )
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


# The test name is intentionally kept as a compatibility alias: the store is
# still file-backed, but tests can point it at an isolated temporary path.
InMemoryExecutionStore = ExecutionStore


class BookBOwnershipEvidence:
    """Append-only broker-ownership evidence, never the account ledger.

    The broker remains the cash/position authority.  This ledger records only
    fills that the broker adapter has already proved, so mixed-account SELL
    guards can distinguish Xiaocao-owned deltas from manual holdings.  Each
    plan is idempotent by its plan-level cumulative filled quantity.  It must
    never be pointed at ``positions.jsonl`` or ``paper_trades.jsonl``: those
    files and ``paper_ledger.lock`` remain the canonical paper account writer.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.name in {"positions.jsonl", "paper_trades.jsonl", "paper_ledger.lock"}:
            raise ValueError("ownership evidence cannot replace canonical account files")
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def owned_shares(self, *, logical_account_id: str, code: str) -> int:
        """Return the net Book B fill delta for diagnostics and SELL binding."""
        handle = self._locked()
        try:
            total = 0
            for row in self._rows():
                if (
                    row.get("book") == "B"
                    and row.get("logical_account_id") == logical_account_id
                    and row.get("code") == code
                ):
                    sign = 1 if str(row.get("side") or "").upper() == "BUY" else -1
                    total += sign * int(row.get("shares") or 0)
            return max(0, total)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def record(self, plan: TradePlan, receipt: ExecutionReceipt) -> dict[str, Any] | None:
        """Record only a newly observed cumulative fill delta."""
        if receipt.state not in {ExecutionState.PARTIAL, ExecutionState.FILLED}:
            return None
        cumulative = max(0, min(int(plan.shares), int(receipt.filled_shares)))
        if cumulative <= 0:
            return None
        handle = self._locked()
        try:
            rows = self._rows()
            previous = max(
                [
                    int(row.get("cumulative_filled_shares") or 0)
                    for row in rows
                    if row.get("plan_id") == plan.plan_id
                    and row.get("plan_hash") == plan.plan_hash
                ]
                or [0]
            )
            if cumulative <= previous:
                return None
            delta = cumulative - previous
            previous_hash = rows[-1].get("event_hash") if rows else None
            event = {
                "schema_version": 1,
                "evidence_kind": "book_b_ownership",
                "event_id": uuid.uuid4().hex,
                "ts": _iso(_utcnow()),
                "kind": "fill_observed",
                "plan_id": plan.plan_id,
                "plan_hash": plan.plan_hash,
                "book": plan.book,
                "logical_account_id": plan.logical_account_id,
                "environment": plan.environment,
                "trade_date": plan.trade_date,
                "code": plan.code,
                "name": plan.name,
                "side": plan.side.upper(),
                "shares": delta,
                "cumulative_filled_shares": cumulative,
                "fill_price": receipt.fill_price,
                "order_price": receipt.order_price,
                "broker_order_id": receipt.broker_order_id,
                "source_execution_event_id": receipt.event_id,
                "previous_hash": previous_hash,
            }
            event["event_hash"] = hashlib.sha256(_canonical(event)).hexdigest()
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


# Compatibility name for callers written during the phase-one seam.  New code
# should use the explicit non-canonical name above.
TradingAccountLedger = BookBOwnershipEvidence


class TradingIncidentOutbox:
    """Durable, idempotent incident handoff independent of the order ledger."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    rows.append(json.loads(line))
                except (TypeError, ValueError):
                    continue
        return rows

    def enqueue(self, *, incident_id: str, title: str, body: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            rows = self._rows()
            matching = [row for row in rows if row.get("incident_id") == incident_id]
            # A delivered incident is terminal and must remain exactly-once.
            # A pending incident is an outstanding delivery claim: let the
            # caller retry the same body without appending duplicate claims.
            if any(row.get("status") == "delivered" for row in matching):
                return False
            if any(row.get("status") == "pending" for row in matching):
                return True
            row = {
                "schema_version": 1,
                "incident_id": incident_id,
                "created_at": _iso(_utcnow()),
                "title": title,
                "body": body,
                "status": "pending",
            }
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def mark_delivered(self, incident_id: str, result: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            row = {
                "schema_version": 1,
                "incident_id": incident_id,
                "created_at": _iso(_utcnow()),
                "status": "delivered",
                "result": result,
            }
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def delivered(self, incident_id: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return any(
                row.get("incident_id") == incident_id and row.get("status") == "delivered"
                for row in self._rows()
            )
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


class TradingTakeoverStore:
    """Durable, credential-free capsule for a human/agent takeover.

    A capsule is deliberately separate from the execution event stream: it is
    the compact handoff surface a recovery agent can consume after a crash or
    an UNKNOWN broker response.  It contains only the immutable plan, the
    normalized receipt, and locator/account proof summaries already emitted by
    the broker adapter; raw DOM, credentials, and arbitrary page text never
    enter this file.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def write(
        self,
        plan: TradePlan,
        receipt: ExecutionReceipt,
        *,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        stable_incident_id = incident_id or hashlib.sha256(
            _canonical({
                "plan_hash": plan.plan_hash,
                "state": receipt.state.value,
                "reason": receipt.reason,
                "order_id": receipt.broker_order_id,
                "filled": receipt.filled_shares,
                "remaining": receipt.remaining_shares,
            })
        ).hexdigest()
        payload = {
            "schema_version": 1,
            "incident_id": stable_incident_id,
            "plan": plan.canonical_payload(),
            "receipt": receipt.as_dict(),
            "template_name": receipt.template_name,
            "template_version": receipt.template_version,
            "account_binding": receipt.account_binding,
            "locator_proof": _safe_evidence(receipt.locator_proof),
            "safe_next_action": (
                "reconcile_only"
                if receipt.state == ExecutionState.UNKNOWN
                else receipt.next_action
            ),
            "forbidden_actions": ["submit", "blind_retry", "create_new_plan"],
            "reconcile_required": receipt.state == ExecutionState.UNKNOWN
            or receipt.next_action in {"reconcile", "reconcile_only"},
        }
        capsule_id = hashlib.sha256(_canonical({"incident_id": stable_incident_id})).hexdigest()
        capsule = {
            **payload,
            "capsule_id": capsule_id,
            "created_at": _iso(_utcnow()),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if any(row.get("capsule_id") == capsule_id for row in self._rows()):
                return capsule
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(capsule, ensure_ascii=False, sort_keys=True, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return capsule
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


Notifier = Callable[[str, str], object]


class TradingExecution:
    """Deep Book B execution module behind one idempotent public method."""

    def __init__(
        self,
        *,
        store: ExecutionStore,
        broker: BrokerAdapter | None = None,
        ledger: BookBOwnershipEvidence | None = None,
        outbox: TradingIncidentOutbox | None = None,
        takeovers: TradingTakeoverStore | None = None,
        notifier: Notifier | None = None,
        now: Callable[[], datetime] | None = None,
        safety_env: dict[str, str] | None = None,
        safety_env_provider: Callable[[], dict[str, str]] | None = None,
        auth_path: Path = DEFAULT_AUTH_PATH,
        audit_path: Path | None = DEFAULT_AUDIT_PATH,
        account_lock_dir: Path | None = None,
    ):
        self.store = store
        self.broker = broker
        self.ledger = ledger
        self.outbox = outbox or TradingIncidentOutbox(store.path.with_name("trading_incidents.jsonl"))
        self.takeovers = takeovers or TradingTakeoverStore(store.path.with_name("trading_takeovers.jsonl"))
        self.notifier = notifier if notifier is not None else self._default_notifier
        self.now = now or _utcnow
        if safety_env is not None and safety_env_provider is not None:
            raise ValueError("configure safety_env or safety_env_provider, not both")
        self.safety_env = safety_env
        self.safety_env_provider = safety_env_provider
        self.auth_path = auth_path
        self.audit_path = audit_path
        self.account_lock_dir = Path(account_lock_dir or store.path.parent / "account_writer_locks")

    @staticmethod
    def _default_notifier(title: str, body: str) -> object:
        return notify_module.notify(title, body, audience="trading")

    @staticmethod
    def _with_capability_evidence(
        receipt: ExecutionReceipt,
        capability: BrokerCapability,
    ) -> ExecutionReceipt:
        return replace(
            receipt,
            template_name=receipt.template_name or capability.template_name,
            template_version=receipt.template_version or capability.template_version,
            account_binding=receipt.account_binding or capability.account_binding,
            locator_proof=_safe_evidence(
                receipt.locator_proof or capability.locator_proof
            ),
        )

    @contextmanager
    def _account_writer_lock(self, logical_account_id: str):
        """Fence every transition for one logical account, not just one file."""
        account = str(logical_account_id or "").strip()
        if not account:
            raise ValueError("logical account id is required for writer fencing")
        digest = hashlib.sha256(account.encode("utf-8")).hexdigest()[:24]
        self.account_lock_dir.mkdir(parents=True, exist_ok=True)
        path = self.account_lock_dir / f"account-{digest}.lock"
        handle = path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def execute(self, plan: TradePlan, broker: BrokerAdapter | None = None) -> ExecutionReceipt:
        """Advance one immutable plan, never replaying an uncertain submit."""
        broker = broker or self.broker
        if broker is None:
            raise ValueError("a broker adapter must be configured before execute")
        with self._account_writer_lock(plan.logical_account_id):
            return self._execute_locked(plan, broker)

    def _execute_locked(self, plan: TradePlan, broker: BrokerAdapter) -> ExecutionReceipt:
        existing = self.store.current(plan.plan_id)
        if existing is not None and existing.plan_hash != plan.plan_hash:
            return self._record(
                plan,
                ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.REJECTED, "PLAN_HASH_MISMATCH"),
                kind="plan_conflict",
            )
        if existing is None:
            return self._start(plan, broker)
        if existing.state in TERMINAL_STATES:
            return existing
        if existing.state in {ExecutionState.UNKNOWN, ExecutionState.SUBMITTED, ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL, ExecutionState.RECONCILING}:
            return self._reconcile(plan, broker, existing)
        if existing.state in {ExecutionState.PLANNED, ExecutionState.VALIDATED, ExecutionState.PREPARED}:
            return self._continue(plan, broker, existing)
        return existing

    def _start(self, plan: TradePlan, broker: BrokerAdapter) -> ExecutionReceipt:
        receipt = self._record(
            plan,
            ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PLANNED, remaining_shares=plan.shares),
            kind="plan_created",
        )
        error = plan.validation_error()
        if error:
            return self._record(
                plan,
                replace(receipt, state=ExecutionState.REJECTED, reason=error, next_action="human_review"),
            )
        guard_reason = plan.guard_reason(now=self.now())
        if guard_reason:
            return self._record(
                plan,
                replace(receipt, state=ExecutionState.SKIPPED, reason=guard_reason, next_action="stop"),
            )
        if plan.submit_not_before is not None and self.now() < plan.submit_not_before:
            return self._record(
                plan,
                replace(receipt, state=ExecutionState.VALIDATED, reason="SUBMIT_NOT_BEFORE", next_action="wait_until_submit_window"),
            )
        if plan.side.upper() == "BUY" and self.now() >= plan.recovery_deadline:
            return self._record(
                plan,
                replace(receipt, state=ExecutionState.SKIPPED, reason="RECOVERY_DEADLINE_REACHED", next_action="stop"),
            )
        return self._continue(plan, broker, replace(receipt, state=ExecutionState.VALIDATED))

    def _capital_denial(
        self,
        plan: TradePlan,
        previous: ExecutionReceipt,
    ) -> ExecutionReceipt | None:
        """Recheck both capital keys before every live submit-capable phase."""
        if plan.environment != "live":
            return None
        try:
            env = (
                self.safety_env_provider()
                if self.safety_env_provider is not None
                else self.safety_env
            )
            require_capital_action(
                kind="real_capital",
                side=plan.side,
                code=plan.code,
                notional=plan.notional,
                auth_path=self.auth_path,
                audit_path=self.audit_path,
                env=env,
                now=self.now(),
            )
        except CapitalRuntimeUnavailable as exc:
            denied = self._record(
                plan,
                replace(
                    previous,
                    state=ExecutionState.REJECTED,
                    reason=f"SAFETY_DENIED:CAPITAL_RUNTIME_UNAVAILABLE:{exc}",
                    next_action="human_review",
                ),
            )
            self._incident(plan, denied)
            return denied
        except Exception as exc:  # Gate errors are capital denials, never fallbacks.
            denied = self._record(
                plan,
                replace(
                    previous,
                    state=ExecutionState.REJECTED,
                    reason=f"SAFETY_DENIED:{exc}",
                    next_action="human_review",
                ),
            )
            self._incident(plan, denied)
            return denied
        return None

    def _continue(self, plan: TradePlan, broker: BrokerAdapter, previous: ExecutionReceipt) -> ExecutionReceipt:
        if plan.submit_not_before is not None and self.now() < plan.submit_not_before:
            return self._record(
                plan,
                replace(previous, reason="SUBMIT_NOT_BEFORE", next_action="wait_until_submit_window"),
            )
        if plan.side.upper() == "BUY" and self.now() >= plan.recovery_deadline:
            return self._record(
                plan,
                replace(previous, state=ExecutionState.SKIPPED, reason="RECOVERY_DEADLINE_REACHED", next_action="stop"),
            )
        denied = self._capital_denial(plan, previous)
        if denied is not None:
            return denied
        try:
            capability = broker.probe(plan)
        except Exception as exc:  # Probe has no external side effect; keep the plan retryable.
            failed = self._record(
                plan,
                replace(previous, reason=f"BROKER_PROBE_FAILED:{type(exc).__name__}", next_action="probe"),
                kind="probe_failed",
            )
            if plan.environment == "live":
                self._incident(plan, failed)
            return failed
        if not capability.ready or capability.environment != plan.environment or capability.logical_account_id != plan.logical_account_id:
            failed = self._record(
                plan,
                self._with_capability_evidence(
                    replace(previous, reason="BROKER_BINDING_MISMATCH", next_action="probe"),
                    capability,
                ),
                kind="binding_mismatch",
                details={"capability": asdict(capability)},
            )
            if plan.environment == "live":
                self._incident(plan, failed)
            return failed
        ownership_reason = self._ownership_reason(plan, capability)
        if ownership_reason is None and plan.side.upper() == "SELL" and self.ledger is not None:
            owned_by_book_b = self.ledger.owned_shares(
                logical_account_id=plan.logical_account_id,
                code=plan.code,
            )
            if int(plan.shares) > owned_by_book_b:
                ownership_reason = "OWNED_LEDGER_BOUND"
        if ownership_reason:
            state = ExecutionState.SKIPPED if ownership_reason in {
                "MANUAL_HOLDING_CONFLICT",
                "MANUAL_HOLDING_CHECK_UNAVAILABLE",
                "T1_BLOCKED",
                "OWNED_LEDGER_BOUND",
            } else ExecutionState.REJECTED
            blocked = self._record(
                plan,
                self._with_capability_evidence(
                    replace(previous, state=state, reason=ownership_reason, next_action="human_review" if state == ExecutionState.REJECTED else "stop"),
                    capability,
                ),
                kind="ownership_guard",
                details={"capability": asdict(capability)},
            )
            if plan.environment == "live":
                self._incident(plan, blocked)
            return blocked
        if not capability.supports_submit:
            denied = self._record(
                plan,
                self._with_capability_evidence(
                    replace(previous, state=ExecutionState.REJECTED, reason="NO_ROUTE_PROVEN", next_action="human_review"),
                    capability,
                ),
                kind="submit_capability_missing",
                details={"capability": asdict(capability)},
            )
            if plan.environment == "live":
                self._incident(plan, denied)
            return denied
        if plan.environment == "live" and not capability.supports_reconcile:
            blocked = self._record(
                plan,
                self._with_capability_evidence(
                    replace(
                        previous,
                        state=ExecutionState.REJECTED,
                        reason="BROKER_RECONCILE_UNPROVEN",
                        next_action="human_review",
                    ),
                    capability,
                ),
                kind="reconcile_capability_unproven",
                details={"capability": asdict(capability)},
            )
            self._incident(plan, blocked)
            return blocked
        if plan.environment == "live" and str(capability.account_binding or "").strip().lower() not in {
            "proven",
            "bound",
        }:
            blocked = self._record(
                plan,
                self._with_capability_evidence(
                    replace(previous, state=ExecutionState.REJECTED, reason="ACCOUNT_BINDING_UNPROVEN", next_action="human_review"),
                    capability,
                ),
                kind="account_binding_unproven",
                details={"account_binding": capability.account_binding},
            )
            self._incident(plan, blocked)
            return blocked
        try:
            prepared = broker.prepare(plan)
            prepared = replace(
                prepared,
                template_name=prepared.template_name or capability.template_name,
                template_version=prepared.template_version or capability.template_version,
                account_binding=prepared.account_binding or capability.account_binding,
                locator_proof=prepared.locator_proof or capability.locator_proof,
            )
        except Exception as exc:
            failed = self._record(
                plan,
                replace(previous, reason=f"BROKER_PREPARE_FAILED:{type(exc).__name__}", next_action="prepare"),
                kind="prepare_failed",
            )
            if plan.environment == "live":
                self._incident(plan, failed)
            return failed
        prepared_status = prepared.normalized_status()
        if prepared_status == BrokerStatus.UNKNOWN or not prepared.conclusive:
            prepared_unknown = self._receipt_from_broker(
                plan, previous, prepared, ExecutionState.UNKNOWN, plan.shares
            )
            unknown = self._record(
                plan,
                replace(
                    prepared_unknown,
                    state=ExecutionState.UNKNOWN,
                    reason=prepared.reason or "PREPARE_RESPONSE_UNKNOWN",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="prepare_unknown",
            )
            if plan.environment == "live":
                self._incident(plan, unknown)
            return unknown
        if prepared_status != BrokerStatus.PREPARED or not self._echo_matches(plan, prepared.echoed, plan.shares):
            failed = self._record(
                plan,
                replace(previous, state=ExecutionState.REJECTED, reason="PREPARE_MISMATCH", next_action="human_review"),
                kind="prepare_mismatch",
                details={
                    "field_readback": prepared.field_readback,
                    "echoed": prepared.echoed,
                    "template_name": prepared.template_name,
                    "template_version": prepared.template_version,
                    "account_binding": prepared.account_binding,
                    "locator_proof": prepared.locator_proof,
                },
            )
            if plan.environment == "live":
                self._incident(plan, failed)
            return failed
        prepared_receipt = self._receipt_from_broker(plan, previous, prepared, ExecutionState.PREPARED, plan.shares)
        prepared_receipt = self._record(plan, prepared_receipt)
        denied = self._capital_denial(plan, prepared_receipt)
        if denied is not None:
            return denied
        return self._submit_claimed(plan, broker, prepared_receipt, requested_shares=plan.shares)

    @staticmethod
    def _ownership_reason(plan: TradePlan, capability: BrokerCapability) -> str | None:
        """Enforce the mixed-account boundary from broker facts only."""
        if plan.environment != "live":
            if plan.side.upper() == "BUY" and capability.manual_position_shares and capability.manual_position_shares > 0:
                return "MANUAL_HOLDING_CONFLICT"
            if plan.side.upper() == "SELL" and capability.owned_position_shares is not None:
                sellable = capability.sellable_shares if capability.sellable_shares is not None else capability.owned_position_shares
                if int(plan.shares) > int(sellable or 0):
                    return "OWNED_POSITION_BOUND"
            if plan.side.upper() == "SELL" and capability.t1_blocked is True:
                return "T1_BLOCKED"
            return None
        if plan.side.upper() == "BUY":
            if capability.manual_position_shares is None:
                return "MANUAL_HOLDING_CHECK_UNAVAILABLE"
            if capability.manual_position_shares > 0:
                return "MANUAL_HOLDING_CONFLICT"
        if plan.side.upper() == "SELL":
            if capability.owned_position_shares is None or capability.sellable_shares is None:
                return "OWNED_POSITION_CHECK_UNAVAILABLE"
            if capability.t1_blocked is True:
                return "T1_BLOCKED"
            if int(plan.shares) > min(capability.owned_position_shares, capability.sellable_shares):
                return "OWNED_POSITION_BOUND"
        return None

    def _submit_claimed(
        self,
        plan: TradePlan,
        broker: BrokerAdapter,
        previous: ExecutionReceipt,
        *,
        requested_shares: int,
        already_filled: int = 0,
    ) -> ExecutionReceipt:
        if previous.attempt >= 2:
            blocked = self._record(
                plan,
                replace(
                    previous,
                    state=ExecutionState.REJECTED,
                    reason="RETRY_LIMIT_REACHED",
                    next_action="stop",
                ),
                kind="submit_attempt_limit_reached",
            )
            if plan.environment == "live":
                self._incident(plan, blocked)
            return blocked
        claim_id = f"{plan.plan_id}:{previous.attempt + 1}:{uuid.uuid4().hex}"
        claimed = self._record(
            plan,
            replace(
                previous,
                state=ExecutionState.CLAIMED,
                attempt=previous.attempt + 1,
                remaining_shares=requested_shares,
                next_action="submit_once",
            ),
            kind="durable_claim",
            details={"claim_id": claim_id, "requested_shares": requested_shares},
        )
        try:
            broker_receipt = broker.submit(plan, claim_id, requested_shares=requested_shares)
        except Exception as exc:
            unknown = self._record(
                plan,
                replace(
                    claimed,
                    state=ExecutionState.UNKNOWN,
                    reason=f"SUBMIT_RESPONSE_UNKNOWN:{type(exc).__name__}",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="submit_unknown",
                details={"claim_id": claim_id},
            )
            self._incident(plan, unknown)
            return unknown
        if broker_receipt.normalized_status() == BrokerStatus.UNKNOWN or not broker_receipt.conclusive:
            unknown_base = self._receipt_from_broker(
                plan,
                claimed,
                broker_receipt,
                ExecutionState.UNKNOWN,
                requested_shares,
                already_filled=already_filled,
            )
            unknown = self._record(
                plan,
                replace(
                    unknown_base,
                    state=ExecutionState.UNKNOWN,
                    reason=broker_receipt.reason or "SUBMIT_RESPONSE_UNKNOWN",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="submit_unknown",
                details={"claim_id": claim_id, "error_code": broker_receipt.error_code},
            )
            self._incident(plan, unknown)
            return unknown
        if plan.environment == "live" and not self._live_submit_receipt_proven(
            broker_receipt
        ):
            unknown_base = self._receipt_from_broker(
                plan,
                claimed,
                broker_receipt,
                ExecutionState.UNKNOWN,
                requested_shares,
                already_filled=already_filled,
            )
            unknown = self._record(
                plan,
                replace(
                    unknown_base,
                    state=ExecutionState.UNKNOWN,
                    reason="LIVE_SUBMIT_RECEIPT_UNPROVEN",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="submit_receipt_unproven",
                details={"claim_id": claim_id},
            )
            self._incident(plan, unknown)
            return unknown
        state = self._state_for_broker(broker_receipt)
        return self._record(
            plan,
            self._receipt_from_broker(plan, claimed, broker_receipt, state, requested_shares, already_filled=already_filled),
            kind="submit_receipt",
            details={"claim_id": claim_id},
        )

    def _reconcile(self, plan: TradePlan, broker: BrokerAdapter, previous: ExecutionReceipt) -> ExecutionReceipt:
        reconciling = self._record(
            plan,
            replace(previous, state=ExecutionState.RECONCILING, next_action="reconcile"),
            kind="reconcile_started",
        )
        try:
            broker_receipt = broker.reconcile(plan, reconciling.as_dict())
        except Exception as exc:
            unknown = self._record(
                plan,
                replace(
                    reconciling,
                    state=ExecutionState.UNKNOWN,
                    reason=f"RECONCILE_FAILED:{type(exc).__name__}",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="reconcile_unknown",
            )
            self._incident(plan, unknown)
            return unknown
        if broker_receipt.normalized_status() == BrokerStatus.UNKNOWN or not broker_receipt.conclusive:
            unknown_base = self._receipt_from_broker(
                plan, reconciling, broker_receipt, ExecutionState.UNKNOWN, plan.shares
            )
            unknown = self._record(
                plan,
                replace(
                    unknown_base,
                    state=ExecutionState.UNKNOWN,
                    reason=broker_receipt.reason or "RECONCILE_UNKNOWN",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="reconcile_unknown",
            )
            self._incident(plan, unknown)
            return unknown
        if plan.environment == "live" and not self._live_reconcile_receipt_proven(
            previous,
            broker_receipt,
        ):
            unknown_base = self._receipt_from_broker(
                plan,
                reconciling,
                broker_receipt,
                ExecutionState.UNKNOWN,
                plan.shares,
            )
            unknown = self._record(
                plan,
                replace(
                    unknown_base,
                    state=ExecutionState.UNKNOWN,
                    reason="LIVE_RECONCILE_RECEIPT_UNPROVEN",
                    next_action="reconcile_only",
                ),
                kind="reconcile_receipt_unproven",
            )
            self._incident(plan, unknown)
            return unknown
        state = self._state_for_broker(broker_receipt)
        reconciled = self._record(
            plan,
            self._receipt_from_broker(plan, reconciling, broker_receipt, state, plan.shares),
            kind="reconcile_receipt",
        )
        if state != ExecutionState.PARTIAL or reconciled.remaining_shares <= 0:
            return reconciled
        if reconciled.submit_chain_uncertain:
            return self._record(
                plan,
                replace(
                    reconciled,
                    reason="UNCERTAIN_SUBMIT_NO_RETRY",
                    next_action="stop",
                ),
                kind="uncertain_submit_retry_blocked",
            )
        if reconciled.attempt >= 2:
            return self._record(
                plan,
                replace(
                    reconciled,
                    reason="RETRY_LIMIT_REACHED",
                    next_action="stop",
                ),
                kind="retry_limit_reached",
            )
        if not self._retry_allowed(plan, broker_receipt):
            reason = self._retry_block_reason(plan, broker_receipt)
            return self._record(plan, replace(reconciled, reason=reason, next_action="wait_for_basket" if reason == "REALTIME_ABOVE_BASKET" else "stop"))
        denied = self._capital_denial(plan, reconciled)
        if denied is not None:
            return denied
        try:
            capability = broker.probe(plan)
            if not capability.ready or not capability.supports_submit:
                failed = self._record(
                    plan,
                    self._with_capability_evidence(
                        replace(reconciled, reason="RETRY_ROUTE_UNAVAILABLE", next_action="stop"),
                        capability,
                    ),
                    kind="retry_route_unavailable",
                    details={"capability": asdict(capability)},
                )
                if plan.environment == "live":
                    self._incident(plan, failed)
                return failed
            requested = reconciled.remaining_shares
            prepared = broker.prepare(plan, requested_shares=requested)
            prepared = replace(
                prepared,
                template_name=prepared.template_name or capability.template_name,
                template_version=prepared.template_version or capability.template_version,
                account_binding=prepared.account_binding or capability.account_binding,
                locator_proof=prepared.locator_proof or capability.locator_proof,
            )
            prepared_status = prepared.normalized_status()
            if prepared_status == BrokerStatus.UNKNOWN or not prepared.conclusive:
                retry_unknown_base = self._receipt_from_broker(
                    plan,
                    reconciled,
                    prepared,
                    ExecutionState.UNKNOWN,
                    requested,
                    already_filled=reconciled.filled_shares,
                )
                unknown = self._record(
                    plan,
                    replace(
                        retry_unknown_base,
                        state=ExecutionState.UNKNOWN,
                        reason=prepared.reason or "RETRY_PREPARE_RESPONSE_UNKNOWN",
                        next_action="reconcile_only",
                        submit_chain_uncertain=True,
                    ),
                    kind="retry_prepare_unknown",
                )
                if plan.environment == "live":
                    self._incident(plan, unknown)
                return unknown
            if prepared_status != BrokerStatus.PREPARED or not self._echo_matches(plan, prepared.echoed, requested):
                failed = self._record(
                    plan,
                    replace(reconciled, state=ExecutionState.REJECTED, reason="RETRY_PREPARE_MISMATCH", next_action="human_review"),
                    kind="retry_prepare_mismatch",
                    details={
                        "field_readback": prepared.field_readback,
                        "echoed": prepared.echoed,
                        "template_name": prepared.template_name,
                        "template_version": prepared.template_version,
                        "account_binding": prepared.account_binding,
                        "locator_proof": prepared.locator_proof,
                    },
                )
                if plan.environment == "live":
                    self._incident(plan, failed)
                return failed
            prepared_retry = self._record(
                plan,
                self._receipt_from_broker(plan, reconciled, prepared, ExecutionState.PREPARED, requested, already_filled=reconciled.filled_shares),
                kind="retry_prepared",
            )
            denied = self._capital_denial(plan, prepared_retry)
            if denied is not None:
                return denied
            return self._submit_claimed(
                plan,
                broker,
                prepared_retry,
                requested_shares=requested,
                already_filled=reconciled.filled_shares,
            )
        except Exception as exc:
            failed = self._record(
                plan,
                replace(
                    reconciled,
                    state=ExecutionState.UNKNOWN,
                    reason=f"RETRY_PREPARE_UNKNOWN:{type(exc).__name__}",
                    next_action="reconcile_only",
                    submit_chain_uncertain=True,
                ),
                kind="retry_unknown",
            )
            if plan.environment == "live":
                self._incident(plan, failed)
            return failed

    @staticmethod
    def _echo_matches(plan: TradePlan, echoed: dict[str, Any], requested_shares: int) -> bool:
        if not echoed:
            return False
        echoed_code = str(echoed.get("code") or "").strip()
        expected_code = str(plan.code or "").strip()
        if echoed_code != expected_code and echoed_code.split(".", 1)[0] != expected_code.split(".", 1)[0]:
            return False
        echoed_side = str(echoed.get("side") or "").strip().upper()
        if echoed_side in {"买入", "BUY"}:
            echoed_side = "BUY"
        elif echoed_side in {"卖出", "SELL"}:
            echoed_side = "SELL"
        if echoed_side != plan.side.upper():
            return False
        try:
            shares = echoed.get("shares", echoed.get("quantity", echoed.get("requested_shares")))
            price = echoed.get("limit_price", echoed.get("order_price", echoed.get("price")))
            if int(shares) != int(requested_shares):
                return False
            return abs(float(price) - float(plan.limit_price)) <= 1e-6
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _state_for_broker(receipt: BrokerReceipt) -> ExecutionState:
        return {
            BrokerStatus.PREPARED: ExecutionState.PREPARED,
            BrokerStatus.ACCEPTED: ExecutionState.ACKNOWLEDGED,
            BrokerStatus.PARTIAL: ExecutionState.PARTIAL,
            BrokerStatus.FILLED: ExecutionState.FILLED,
            BrokerStatus.CANCELLED: ExecutionState.CANCELLED,
            BrokerStatus.REJECTED: ExecutionState.REJECTED,
            BrokerStatus.UNKNOWN: ExecutionState.UNKNOWN,
        }[receipt.normalized_status()]

    @staticmethod
    def _account_binding_proven(receipt: BrokerReceipt) -> bool:
        return str(receipt.account_binding or "").strip().lower() in {
            "proven",
            "bound",
        }

    @classmethod
    def _live_submit_receipt_proven(cls, receipt: BrokerReceipt) -> bool:
        status = receipt.normalized_status()
        if status == BrokerStatus.REJECTED:
            return (
                cls._account_binding_proven(receipt)
                and receipt.conclusive
                and all(
                    receipt.field_readback.get(key) is False
                    for key in ("submitted", "saved", "started")
                )
            )
        return (
            status
            in {
                BrokerStatus.ACCEPTED,
                BrokerStatus.PARTIAL,
                BrokerStatus.FILLED,
                BrokerStatus.CANCELLED,
            }
            and cls._account_binding_proven(receipt)
            and receipt.receipt_mapping is True
            and bool(receipt.order_id)
            and bool(receipt.strategy_id)
        )

    @classmethod
    def _live_reconcile_receipt_proven(
        cls,
        previous: ExecutionReceipt,
        receipt: BrokerReceipt,
    ) -> bool:
        return (
            cls._account_binding_proven(receipt)
            and receipt.receipt_mapping is True
            and bool(previous.broker_order_id)
            and receipt.order_id == previous.broker_order_id
            and bool(previous.broker_strategy_id)
        )

    def _receipt_from_broker(
        self,
        plan: TradePlan,
        previous: ExecutionReceipt,
        broker: BrokerReceipt,
        state: ExecutionState,
        requested_shares: int,
        *,
        already_filled: int = 0,
    ) -> ExecutionReceipt:
        broker_filled = max(0, int(broker.filled_shares or 0))
        base_filled = max(int(already_filled), int(previous.filled_shares))
        same_order = bool(
            broker.order_id
            and previous.broker_order_id
            and broker.order_id == previous.broker_order_id
        )
        # Broker fills are cumulative within one order.  A replacement order
        # starts a new counter and is added to the plan total; a reconcile of
        # the same order takes the monotonic maximum to avoid double counting.
        filled = min(
            int(plan.shares),
            max(base_filled, broker_filled)
            if same_order
            else base_filled + broker_filled,
        )
        if state == ExecutionState.FILLED:
            filled = int(plan.shares)
        remaining = max(0, int(plan.shares) - filled)
        if state in {ExecutionState.CANCELLED, ExecutionState.REJECTED}:
            remaining = max(0, int(plan.shares) - filled)
        return replace(
            previous,
            state=state,
            reason=broker.reason,
            filled_shares=filled,
            remaining_shares=remaining,
            broker_order_id=broker.order_id or previous.broker_order_id,
            broker_strategy_id=broker.strategy_id or previous.broker_strategy_id,
            broker_status=broker.normalized_status().value,
            receipt_mapping=(
                broker.receipt_mapping
                if isinstance(broker.receipt_mapping, bool)
                else previous.receipt_mapping
            ),
            order_price=broker.order_price,
            fill_price=broker.fill_price,
            latest_price=broker.latest_price,
            active=broker.active,
            market_guard_status=broker.market_guard_status,
            market_guard_observed_at=broker.market_guard_observed_at or broker.observed_at,
            market_guard_down_price=broker.market_guard_down_price,
            template_name=broker.template_name or previous.template_name,
            template_version=broker.template_version or previous.template_version,
            account_binding=broker.account_binding or previous.account_binding,
            locator_proof=_safe_evidence(broker.locator_proof or previous.locator_proof),
            next_action=(
                "reconcile" if state in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL} else
                "reconcile_only" if state == ExecutionState.UNKNOWN else
                "human_review" if state == ExecutionState.REJECTED else "stop"
            ),
            observed_at=broker.observed_at or self.now(),
        )

    def _retry_allowed(self, plan: TradePlan, broker: BrokerReceipt) -> bool:
        if plan.side.upper() != "BUY" or self.now() >= plan.recovery_deadline:
            return False
        if broker.active is not False:
            return False
        if not broker.order_id or not broker.conclusive:
            return False
        if broker.retry_allowed is False:
            return False
        if broker.normalized_status() == BrokerStatus.PARTIAL:
            terminal = broker.field_readback.get("order_terminal")
            reason = str(broker.reason or "").lower()
            if terminal is not True and not any(
                marker in reason for marker in ("cancel", "reject", "expire", "closed", "terminal")
            ):
                return False
        guard_ok, _guard_reason, _evidence = self._retry_market_guard(plan, broker)
        if not guard_ok:
            return False
        observed_at = broker.observed_at
        if observed_at is None:
            return False
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age_seconds = (self.now() - observed_at).total_seconds()
        if age_seconds > 300 or age_seconds < -60:
            return False
        price = broker.latest_price
        return price is not None and float(price) > 0 and plan.basket_price is not None and float(price) <= float(plan.basket_price) + 1e-6

    def _retry_market_guard(self, plan: TradePlan, broker: BrokerReceipt) -> tuple[bool, str | None, dict[str, Any]]:
        required = bool(plan.market_guard_required or plan.environment == "live")
        observed_at = broker.market_guard_observed_at or broker.observed_at
        return evaluate_buy_market_guard(
            {
                "market_guard_required": required,
                "market_guard_status": broker.market_guard_status or plan.market_guard_status,
                "latest_price": broker.latest_price,
                "down_price": (
                    broker.market_guard_down_price
                    if broker.market_guard_down_price is not None
                    else plan.market_guard_down_price
                ),
                "market_observed_at": _iso(observed_at),
                "trade_date": plan.trade_date,
            },
            require_authoritative=required,
            now=self.now(),
        )

    def _retry_block_reason(self, plan: TradePlan, broker: BrokerReceipt) -> str:
        if self.now() >= plan.recovery_deadline:
            return "RECOVERY_DEADLINE_REACHED"
        if broker.active is not False:
            return "ORDER_STILL_ACTIVE"
        if not broker.order_id or not broker.conclusive:
            return "ORDER_TERMINALITY_UNPROVEN"
        if broker.normalized_status() == BrokerStatus.PARTIAL:
            terminal = broker.field_readback.get("order_terminal")
            reason = str(broker.reason or "").lower()
            if terminal is not True and not any(
                marker in reason for marker in ("cancel", "reject", "expire", "closed", "terminal")
            ):
                return "ORDER_TERMINALITY_UNPROVEN"
        _guard_ok, guard_reason, _evidence = self._retry_market_guard(plan, broker)
        if not _guard_ok:
            return guard_reason or "LIMIT_DOWN_CHECK_UNAVAILABLE"
        observed_at = broker.observed_at
        if observed_at is None:
            return "LIMIT_DOWN_CHECK_UNAVAILABLE"
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age_seconds = (self.now() - observed_at).total_seconds()
        if age_seconds > 300 or age_seconds < -60:
            return "LIMIT_DOWN_CHECK_UNAVAILABLE"
        if broker.latest_price is None or plan.basket_price is None:
            return "LIMIT_DOWN_CHECK_UNAVAILABLE"
        if float(broker.latest_price) > float(plan.basket_price) + 1e-6:
            return "REALTIME_ABOVE_BASKET"
        if broker.retry_allowed is False:
            return "BROKER_RETRY_NOT_ALLOWED"
        return "RETRY_NOT_PROVEN"

    def _record(
        self,
        plan: TradePlan,
        receipt: ExecutionReceipt,
        *,
        kind: str = "transition",
        details: dict[str, Any] | None = None,
    ) -> ExecutionReceipt:
        recorded = self.store.append(plan=plan, receipt=receipt, kind=kind, details=details)
        if self.ledger is not None:
            try:
                self.ledger.record(plan, recorded)
            except Exception as exc:
                # A broker fill cannot be undone because our local ledger had
                # a write failure.  Preserve the execution receipt, surface a
                # durable incident, and let the next recovery pass repair the
                # supporting ledger without submitting again.
                ledger_failure = self.store.append(
                    plan=plan,
                    receipt=replace(
                        recorded,
                        reason=f"LEDGER_WRITE_FAILED:{type(exc).__name__}",
                        next_action="ledger_reconcile",
                    ),
                    kind="ledger_write_failed",
                    details={"ledger_path": str(self.ledger.path)},
                )
                self._incident(plan, ledger_failure)
                return ledger_failure
        return recorded

    def _incident(self, plan: TradePlan, receipt: ExecutionReceipt) -> None:
        incident_id = hashlib.sha256(
            _canonical({
                "plan_hash": plan.plan_hash,
                "state": receipt.state.value,
                "reason": receipt.reason,
                "order_id": receipt.broker_order_id,
                "filled": receipt.filled_shares,
                "remaining": receipt.remaining_shares,
            })
        ).hexdigest()
        body = (
            "交易异常，需要确认\n"
            f"操作：{plan.describe()}\n"
            f"state={receipt.state.value} reason={receipt.reason} order_id={receipt.broker_order_id or '-'}\n"
            f"filled={receipt.filled_shares} remaining={receipt.remaining_shares} next={receipt.next_action}\n"
            f"template={receipt.template_name or '-'}@{receipt.template_version or '-'} "
            f"account_binding={receipt.account_binding or '-'} locator_proof={json.dumps(_safe_evidence(receipt.locator_proof), ensure_ascii=False, sort_keys=True)}\n"
            "已完成安全检查：Book B 身份、计划哈希、账户/环境绑定、价格/数量回读、"
            f"real-capital Keychain两条件资金门={'已通过' if plan.environment == 'live' else '不适用（mock）'}\n"
            f"是否需要用户介入：{'是' if receipt.next_action == 'human_review' or receipt.state == ExecutionState.UNKNOWN else '否（继续安全对账）'}\n"
            "未知状态只允许继续对账，不会盲目重发。"
        )
        self.takeovers.write(plan, receipt, incident_id=incident_id)
        fresh = self.outbox.enqueue(incident_id=incident_id, title="Book B 交易异常", body=body)
        if not fresh or self.outbox.delivered(incident_id):
            return
        try:
            result = self.notifier("Book B 交易异常", body)
            ok = result == "ok" or (isinstance(result, dict) and (result.get("wecom") == "ok" or result.get("status") == "ok"))
            if ok:
                self.outbox.mark_delivered(incident_id, result)
        except Exception:
            # The outbox row remains pending; the next safe recovery pass may retry.
            return


# Name used by the design document and future callers.  Keep the implementation
# name explicit for now while the broker-neutral module is being integrated.
BookBLiveExecution = TradingExecution


def trade_plan_from_frozen_row(
    row: dict[str, Any],
    *,
    environment: str,
    logical_account_id: str,
    strategy_run_id: str | None = None,
    strategy_sha: str = "unknown",
    now: datetime | None = None,
    recovery_deadline: datetime | None = None,
    side: str = "BUY",
) -> TradePlan:
    """Translate one already-selected frozen row into an immutable intent.

    This function does not select candidates, allocate cash, or infer a fill.
    Book B's existing selector/board-lot allocator must supply the row and the
    planned shares.  For BUY it only materializes the existing initial-limit
    rule ``min(open * 1.005, basket)``.
    """
    trade_date = str(row.get("date") or row.get("trade_date") or "")[:10]
    code = str(row.get("code") or "")
    name = str(row.get("name") or code)
    normalized_side = str(side or "BUY").upper()
    if not trade_date or not code:
        raise ValueError("frozen row requires date and code")
    raw_book = row.get("book")
    if environment == "live" and raw_book in (None, ""):
        raise ValueError(f"live frozen row must prove Book B: {trade_date} {code}")
    row_book = str(raw_book or "B").strip().upper()
    if row_book != "B":
        raise ValueError(f"frozen row is not Book B: {trade_date} {code} book={row_book}")
    if environment == "live" and normalized_side == "BUY":
        if row.get("mode_exec_star") is not True:
            raise ValueError(f"live frozen BUY row is not ★E: {trade_date} {code}")
        if row.get("mode_trade_eligible") is not True:
            raise ValueError(f"live frozen BUY row is not executable: {trade_date} {code}")
        if "executable_fillable" in row and row.get("executable_fillable") is not True:
            raise ValueError(f"live frozen BUY row is not fillable: {trade_date} {code}")
        if row.get("is_live") is not True:
            raise ValueError(f"live frozen BUY row must be live: {trade_date} {code}")
    shares_value = row.get("mode_exec_planned_shares") if normalized_side == "BUY" else row.get("shares")
    if shares_value in (None, ""):
        shares_value = row.get("planned_shares")
    if shares_value in (None, ""):
        raise ValueError(f"frozen row requires planned shares: {trade_date} {code}")
    shares = int(shares_value)
    basket_raw = row.get("basket_price")
    basket = None if basket_raw in (None, "") else float(basket_raw)
    if normalized_side == "BUY":
        open_raw = row.get("open")
        if open_raw in (None, "") or basket is None or basket <= 0:
            raise ValueError(f"frozen BUY row requires open and basket_price: {trade_date} {code}")
        # A broker order price must be one valid stock tick.  Keep the shared
        # paper/allocation formula unchanged and apply the floor only at this
        # live-capable execution boundary.
        limit_price = initial_limit_price(open_raw, basket, tick_size=0.01)
        if limit_price is None:
            raise ValueError(f"frozen BUY row has invalid open/basket: {trade_date} {code}")
    else:
        price_raw = row.get("limit_price") or row.get("execution_price") or row.get("open")
        if price_raw in (None, ""):
            raise ValueError(f"frozen SELL row requires limit_price or execution_price: {trade_date} {code}")
        limit_price = float(price_raw)
        basket = None
    created = now or _utcnow()
    local_date = datetime.fromisoformat(trade_date).replace(
        tzinfo=ZoneInfo("Asia/Shanghai")
    )
    if recovery_deadline is None:
        recovery_deadline = local_date.replace(hour=9, minute=45, second=0, microsecond=0).astimezone(timezone.utc)
    submit_not_before = _parse_datetime(row.get("submit_not_before")) or created
    if environment == "live" and normalized_side == "BUY":
        opening_submit = local_date.replace(
            hour=9,
            minute=30,
            second=0,
            microsecond=0,
        ).astimezone(timezone.utc)
        submit_not_before = max(submit_not_before, opening_submit)
    plan_id = f"book-b:{trade_date}:{code}:{normalized_side}"
    raw_guard = row.get("market_guard_status") or row.get("trade_status") or row.get("tradeStatus")
    if raw_guard in (None, "") and environment == "mock" and not bool(row.get("market_guard_required")):
        normalized_guard = "ok"
    else:
        normalized_guard = _normalize_guard_status(raw_guard)
    observed_at = _parse_market_guard_observed_at(
        row.get("market_observed_at")
        or row.get("trade_timestamp")
        or row.get("tradeTimestamp"),
        trade_date,
    )
    latest_price = _optional_float(
        row.get("market_price") or row.get("latest_price") or row.get("trade")
    )
    down_price = _optional_float(
        row.get("down_price") or row.get("downPrice") or row.get("limit_down_price")
    )
    plan = TradePlan(
        plan_id=plan_id,
        strategy_run_id=str(strategy_run_id or row.get("strategy_run_id") or f"morning-{trade_date}"),
        snapshot_ref=str(row.get("snapshot_ref") or f"signal_snapshots.jsonl:{trade_date}:{code}"),
        strategy_sha=str(strategy_sha or row.get("strategy_sha") or "unknown"),
        trade_date=trade_date,
        book="B",
        logical_account_id=logical_account_id,
        environment=environment,
        code=code,
        name=name,
        side=normalized_side,
        shares=shares,
        limit_price=round(limit_price, 6),
        basket_price=basket,
        market_guard_status=normalized_guard,
        created_at=created,
        recovery_deadline=recovery_deadline,
        owned_lot_id=row.get("owned_lot_id"),
        submit_not_before=submit_not_before,
        price_rule=(
            "min(frozen_open*1.005,basket_price)"
            if normalized_side == "BUY" else "frozen_sell_limit"
        ),
        market_guard_required=bool(row.get("market_guard_required")) or environment == "live",
        market_guard_observed_at=observed_at,
        market_guard_latest_price=latest_price,
        market_guard_down_price=down_price,
        allocation_proof_hash=str(row.get("allocation_proof_hash") or "") or None,
        sell_authorized=bool(row.get("sell_authorized") is True),
        sell_reason=str(row.get("sell_reason") or "") or None,
        sell_decision_phase=str(row.get("decision_phase") or row.get("sell_decision_phase") or "") or None,
        sell_decision_at=_parse_tz_aware_datetime(
            row.get("sell_decision_at") or row.get("decision_at")
        ),
        sell_block_reason=(
            str(
                row.get("sell_block_reason")
                or row.get("sell_blocked_reason")
                or row.get("liquidity_block_reason")
                or ("T1_BLOCKED" if row.get("t1_blocked") is True else "")
            )
            or None
        ),
    )
    if normalized_side == "SELL":
        error = plan.validation_error()
        if error:
            raise ValueError(error)
    return plan
