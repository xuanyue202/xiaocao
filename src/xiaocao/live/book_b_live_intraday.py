"""Book B live intraday decisions and handoff to the execution port.

The module owns decision/lifecycle state, not broker clicks.  It reconciles
existing durable plans first, consumes fresh broker positions/orders/trades
plus the funds summary embedded in the positions capture,
projects Xiaocao-owned lots, records deterministic decisions, and hands newly
authorized SELL intents to the existing ``TradingExecution`` port exactly
once.  Real submission remains entirely behind that port's two-key gate.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from .book_b_live_lifecycle import (
    BookBLiveAccountState,
    BookBLiveOwnedLot,
    open_execution_plan_ids,
    project_book_b_live_account,
    write_book_b_live_settlement,
)
from .book_b_live_morning import (
    bind_durable_live_plan_intents,
    read_durable_live_plan_intent,
    reconcile_open_book_b_plans,
)
from .trading_execution import ExecutionReceipt, TradePlan


_AUTHORIZED_REASONS = frozenset(
    {"AI_EVENT_RISK_EXIT", "HARD_STOP", "TRAILING_STOP", "EOD_DISCIPLINE_1455"}
)
_AUTHORIZED_PHASES = {
    "AI_EVENT_RISK_EXIT": "event_risk",
    "HARD_STOP": "risk_floor",
    "TRAILING_STOP": "eod_discipline",
    "EOD_DISCIPLINE_1455": "eod_discipline",
}
_INTRADAY_IMMEDIATE_REASONS = frozenset({"AI_EVENT_RISK_EXIT", "HARD_STOP"})
_LIVE_PHASES = frozenset({"opening", "sparse", "precheck", "closing", "eod"})


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@contextmanager
def _checkpoint_lock(state_dir: Path):
    path = Path(state_dir) / "book_b_live_checkpoint.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _intent_path(state_dir: Path, plan_id: str) -> Path:
    digest = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()[:24]
    return Path(state_dir) / "plan_intents" / f"{digest}.json"


def _china_trade_deadline(trade_date: str) -> datetime:
    return datetime.fromisoformat(str(trade_date)[:10]).replace(
        hour=14,
        minute=57,
        second=0,
        microsecond=0,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    ).astimezone(timezone.utc)


def _continuous_auction(current: datetime, trade_date: str) -> bool:
    local = current.astimezone(ZoneInfo("Asia/Shanghai"))
    if local.date().isoformat() != str(trade_date)[:10]:
        return False
    clock = (local.hour, local.minute, local.second)
    return (9, 30, 0) <= clock < (11, 30, 0) or (13, 0, 0) <= clock < (14, 57, 0)


def _closing_discipline_window(current: datetime, trade_date: str) -> bool:
    local = current.astimezone(ZoneInfo("Asia/Shanghai"))
    if local.date().isoformat() != str(trade_date)[:10]:
        return False
    clock = (local.hour, local.minute, local.second)
    return (14, 55, 0) <= clock < (14, 57, 0)


def _eod_settlement_window(current: datetime, trade_date: str) -> bool:
    local = current.astimezone(ZoneInfo("Asia/Shanghai"))
    return bool(
        local.date().isoformat() == str(trade_date)[:10]
        and (local.hour, local.minute, local.second) >= (15, 0, 0)
    )


def _snapshot_observed_at(snapshot: dict[str, Any]) -> datetime:
    try:
        observed = datetime.fromisoformat(
            str(snapshot.get("observed_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_TIME_UNPROVEN") from exc
    if observed.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_TIME_UNPROVEN")
    return observed


def _sell_limit_price(latest_price: object) -> float:
    try:
        price = float(latest_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("LIVE_SELL_PRICE_UNPROVEN") from exc
    if not math.isfinite(price) or price <= 0:
        raise ValueError("LIVE_SELL_PRICE_UNPROVEN")
    # A current-price SELL is conservative and deterministic: no implicit
    # market order and no widening to the daily limit-down price.
    return math.floor((price + 1e-9) * 100.0) / 100.0


def load_monitor_contexts(
    freeze_dir: Path,
    lots: Iterable[BookBLiveOwnedLot],
) -> dict[str, dict[str, Any]]:
    """Recover immutable monitor priors from each filled BUY's dated freeze."""
    allowed = {
        "profile",
        "mode",
        "flags",
        "xcjw",
        "jsjl",
        "fee_rate",
        "instrument_type",
        "settlement_cycle",
        "lot_size",
        "buy_fee_rate",
        "sell_fee_rate",
    }
    contexts: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[BookBLiveOwnedLot]] = {}
    for lot in lots:
        grouped.setdefault(lot.entry_date, []).append(lot)
    for entry_date, dated_lots in grouped.items():
        path = Path(freeze_dir) / f"book_b_live_freeze_{entry_date}.jsonl"
        if not path.is_file():
            raise ValueError(f"LIVE_BOOK_B_MONITOR_FREEZE_MISSING:{entry_date}")
        rows: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError
                    rows.append(row)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"LIVE_BOOK_B_MONITOR_FREEZE_INVALID:{entry_date}") from exc
        for lot in dated_lots:
            matches = [
                row
                for row in rows
                if str(row.get("code") or "") == lot.code
                and str(row.get("book") or "B").upper() == "B"
            ]
            if len(matches) != 1:
                raise ValueError(f"LIVE_BOOK_B_MONITOR_CONTEXT_UNPROVEN:{lot.code}")
            contexts[lot.owned_lot_id] = {
                key: matches[0][key]
                for key in allowed
                if key in matches[0] and matches[0][key] not in (None, "")
            }
    return contexts


class BookBLiveDecisionLedger:
    """Append-only, hash-chained decision ledger with decision-id idempotency."""

    def __init__(self, path: Path):
        self.path = Path(path)
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
        try:
            with self.path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError
                    rows.append(row)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("LIVE_BOOK_B_DECISION_LEDGER_INVALID") from exc
        previous: str | None = None
        for row in rows:
            event = dict(row)
            claimed = str(event.pop("event_hash", ""))
            if event.get("previous_hash") != previous or _sha256(event) != claimed:
                raise ValueError("LIVE_BOOK_B_DECISION_CHAIN_BROKEN")
            previous = claimed
        return rows

    def append(self, decision: dict[str, Any]) -> dict[str, Any]:
        handle = self._locked()
        try:
            rows = self._rows()
            matches = [row for row in rows if row.get("decision_id") == decision.get("decision_id")]
            if matches:
                comparable = dict(matches[-1])
                comparable.pop("event_hash", None)
                comparable.pop("previous_hash", None)
                comparable.pop("recorded_at", None)
                if comparable != decision:
                    raise ValueError("LIVE_BOOK_B_DECISION_IMMUTABILITY_VIOLATION")
                return matches[-1]
            event = {
                **decision,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "previous_hash": rows[-1].get("event_hash") if rows else None,
            }
            event["event_hash"] = _sha256(event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


@dataclass(frozen=True)
class BookBLiveIntradayReceipt:
    trade_date: str
    phase: str
    status: str
    reason: str
    account: dict[str, Any] | None
    decisions: tuple[dict[str, Any], ...]
    execution_receipts: tuple[dict[str, Any], ...]
    reconciliation_receipts: tuple[dict[str, Any], ...]
    settlement: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _existing_sell_plan_for_lot(
    state_dir: Path,
    *,
    trade_date: str,
    owned_lot_id: str,
) -> TradePlan | None:
    intent_dir = Path(state_dir) / "plan_intents"
    if not intent_dir.is_dir():
        return None
    for path in sorted(intent_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("LIVE_PLAN_INTENT_INVALID") from exc
        plan = read_durable_live_plan_intent(payload)
        if (
            plan.trade_date == trade_date
            and plan.side.upper() == "SELL"
            and plan.owned_lot_id == owned_lot_id
        ):
            return plan
    return None


def _sell_plan(
    lot: BookBLiveOwnedLot,
    status: dict[str, Any],
    *,
    trade_date: str,
    phase: str,
    logical_account_id: str,
    strategy_sha: str,
    current: datetime,
    decision_id: str,
) -> TradePlan:
    reason = str(status.get("sell_reason") or "")
    decision_phase = _AUTHORIZED_PHASES.get(reason)
    if reason not in _AUTHORIZED_REASONS or decision_phase is None:
        raise ValueError("LIVE_SELL_REASON_NOT_AUTHORIZED")
    shares = min(int(lot.shares), int(lot.sellable_shares))
    if shares <= 0:
        raise ValueError("LIVE_SELL_T1_OR_BROKER_SELLABLE_BLOCKED")
    observed_raw = status.get("market_guard_observed_at")
    if isinstance(observed_raw, datetime):
        observed = observed_raw
    else:
        try:
            observed = datetime.fromisoformat(
                str(observed_raw or "").replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("LIVE_SELL_MARKET_GUARD_TIME_UNPROVEN") from exc
    if observed.tzinfo is None:
        raise ValueError("LIVE_SELL_MARKET_GUARD_TIME_UNPROVEN")
    local_observed = observed.astimezone(ZoneInfo("Asia/Shanghai"))
    guard_status = str(status.get("market_guard_status") or "").strip().lower()
    guard_trading = guard_status in {
        "ok", "t", "trading", "open", "normal", "交易中", "正常"
    } or (guard_status.startswith("t") and guard_status[1:].isdigit())
    age = (
        current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)
    ).total_seconds()
    if (
        local_observed.date().isoformat() != trade_date
        or age < -30
        or age > 300
        or status.get("market_guard_down_price") in (None, "")
        or not guard_trading
    ):
        raise ValueError("LIVE_SELL_MARKET_GUARD_UNPROVEN")
    lot_digest = hashlib.sha256(lot.owned_lot_id.encode("utf-8")).hexdigest()[:12]
    return TradePlan(
        plan_id=f"book-b:{trade_date}:{lot.code}:SELL:{lot_digest}",
        strategy_run_id=f"book-b-live-monitor:{trade_date}:{phase}",
        snapshot_ref=f"book_b_live_decisions.jsonl:{decision_id}",
        strategy_sha=strategy_sha,
        trade_date=trade_date,
        book="B",
        logical_account_id=logical_account_id,
        environment="live",
        code=lot.code,
        name=lot.name,
        side="SELL",
        shares=shares,
        limit_price=_sell_limit_price(status.get("latest_price")),
        basket_price=None,
        market_guard_status=str(status.get("market_guard_status") or "ok"),
        created_at=current,
        recovery_deadline=_china_trade_deadline(trade_date),
        owned_lot_id=lot.owned_lot_id,
        submit_not_before=current,
        price_rule="current_proprietary_trade_floor_tick",
        market_guard_required=True,
        market_guard_observed_at=observed,
        market_guard_latest_price=float(status.get("latest_price")),
        market_guard_down_price=(
            float(status["market_guard_down_price"])
            if status.get("market_guard_down_price") not in (None, "")
            else None
        ),
        sell_authorized=True,
        sell_reason=reason,
        sell_decision_phase=decision_phase,
        sell_decision_at=current,
        sell_block_reason=str(status.get("sell_block_reason") or "") or None,
    )


def _run_book_b_live_intraday_locked(
    *,
    state_dir: Path,
    trade_date: str,
    phase: str,
    account_snapshot_provider: Callable[[], dict[str, Any]],
    status_provider: Callable[[tuple[BookBLiveOwnedLot, ...]], list[dict[str, Any]]],
    execute: Callable[[TradePlan], ExecutionReceipt],
    now: Callable[[], datetime],
    strategy_sha: str = "unknown",
    freeze_dir: Path | None = None,
    execute_sells: bool = True,
) -> BookBLiveIntradayReceipt:
    """Run one exact-once live lifecycle checkpoint without broker UI logic."""
    normalized_phase = str(phase or "").lower()
    if normalized_phase not in _LIVE_PHASES:
        raise ValueError("LIVE_BOOK_B_INTRADAY_PHASE_INVALID")
    current = now()
    if current.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
    state_root = Path(state_dir)
    reconciled = reconcile_open_book_b_plans(
        state_root,
        trade_date=trade_date,
        execute=execute,
    )
    if open_execution_plan_ids(state_root):
        raise ValueError("LIVE_BOOK_B_OPEN_EXECUTION_RECONCILE_REQUIRED")
    phase_now = now()
    if phase_now.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
    if normalized_phase == "closing" and not _closing_discipline_window(
        phase_now, trade_date
    ):
        raise ValueError("LIVE_BOOK_B_CLOSING_DISCIPLINE_WINDOW_NOT_OPEN")
    if normalized_phase == "eod" and not _eod_settlement_window(
        phase_now, trade_date
    ):
        raise ValueError("LIVE_BOOK_B_EOD_SETTLEMENT_WINDOW_NOT_OPEN")
    snapshot = account_snapshot_provider()
    current = now()
    if current.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
    provisional = project_book_b_live_account(
        state_root,
        snapshot,
        trade_date=trade_date,
        now=current,
    )
    contexts = (
        load_monitor_contexts(Path(freeze_dir), provisional.lots)
        if freeze_dir is not None and provisional.lots
        else {}
    )
    account = project_book_b_live_account(
        state_root,
        snapshot,
        trade_date=trade_date,
        now=current,
        monitor_context_by_lot=contexts,
    )
    if normalized_phase == "eod":
        current = now()
        if current.tzinfo is None:
            raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
        if not _eod_settlement_window(current, trade_date):
            raise ValueError("LIVE_BOOK_B_EOD_SETTLEMENT_WINDOW_NOT_OPEN")
        if not _eod_settlement_window(
            _snapshot_observed_at(snapshot), trade_date
        ):
            raise ValueError("LIVE_BOOK_B_EOD_BROKER_SNAPSHOT_PRE_CLOSE")
        settlement = write_book_b_live_settlement(state_root, account, now=current)
        return BookBLiveIntradayReceipt(
            trade_date=trade_date,
            phase=normalized_phase,
            status="settled",
            reason="BROKER_RECONCILED_EOD_SETTLED",
            account=account.as_dict(),
            decisions=(),
            execution_receipts=(),
            reconciliation_receipts=tuple(reconciled),
            settlement=settlement,
        )
    if not account.lots:
        return BookBLiveIntradayReceipt(
            trade_date=trade_date,
            phase=normalized_phase,
            status="no_action",
            reason="NO_OWNED_BOOK_B_LIVE_LOTS",
            account=account.as_dict(),
            decisions=(),
            execution_receipts=(),
            reconciliation_receipts=tuple(reconciled),
        )
    statuses = status_provider(account.lots)
    by_lot = {str(status.get("owned_lot_id") or ""): status for status in statuses}
    if set(by_lot) != {lot.owned_lot_id for lot in account.lots}:
        raise ValueError("LIVE_BOOK_B_STATUS_COVERAGE_MISMATCH")
    ledger = BookBLiveDecisionLedger(state_root / "book_b_live_decisions.jsonl")
    decisions: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for lot in account.lots:
        decision_now = now()
        if decision_now.tzinfo is None:
            raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
        if normalized_phase == "closing" and not _closing_discipline_window(
            decision_now, trade_date
        ):
            raise ValueError("LIVE_BOOK_B_CLOSING_DISCIPLINE_WINDOW_NOT_OPEN")
        status = dict(by_lot[lot.owned_lot_id])
        reason = str(status.get("sell_reason") or "") or None
        triggered = status.get("triggered") is True
        authorized_now = bool(
            triggered
            and reason in _AUTHORIZED_REASONS
            and not status.get("sell_block_reason")
            and lot.sellable_shares > 0
            and (
                normalized_phase == "closing"
                or reason in _INTRADAY_IMMEDIATE_REASONS
            )
        )
        decision_id = _sha256(
            {
                "trade_date": trade_date,
                "phase": normalized_phase,
                "owned_lot_id": lot.owned_lot_id,
                "broker_snapshot_sha256": account.broker_snapshot_sha256,
                "triggered": triggered,
                "sell_reason": reason,
                "decision_phase": status.get("decision_phase"),
            }
        )
        decision = {
            "schema_version": 1,
            "decision_id": decision_id,
            "trade_date": trade_date,
            "phase": normalized_phase,
            "book": "B",
            "environment": "live",
            "logical_account_id": "primary",
            "owned_lot_id": lot.owned_lot_id,
            "code": lot.code,
            "name": lot.name,
            "shares": lot.shares,
            "sellable_shares": lot.sellable_shares,
            "broker_snapshot_sha256": account.broker_snapshot_sha256,
            "triggered": triggered,
            "sell_authorized": authorized_now,
            "sell_reason": reason,
            "decision_phase": status.get("decision_phase"),
            "latest_price": status.get("latest_price"),
            "market_guard_status": status.get("market_guard_status"),
            "market_guard_observed_at": (
                status["market_guard_observed_at"].isoformat()
                if isinstance(status.get("market_guard_observed_at"), datetime)
                else status.get("market_guard_observed_at")
            ),
            "market_guard_down_price": status.get("market_guard_down_price"),
            "dd_pct": status.get("dd_pct"),
            "net_ret_pct": status.get("net_ret_pct"),
            "strong_hold_reason": status.get("strong_hold_reason"),
            "deferred_sell_reason": status.get("deferred_sell_reason"),
            "sell_block_reason": status.get("sell_block_reason"),
        }
        decisions.append(ledger.append(decision))
        if not authorized_now or not execute_sells:
            continue
        if not _continuous_auction(decision_now, trade_date):
            continue
        existing = _existing_sell_plan_for_lot(
            state_root, trade_date=trade_date, owned_lot_id=lot.owned_lot_id
        )
        if existing is None:
            plan = _sell_plan(
                lot,
                status,
                trade_date=trade_date,
                phase=normalized_phase,
                logical_account_id="primary",
                strategy_sha=strategy_sha,
                current=decision_now,
                decision_id=decision_id,
            )
            plan = bind_durable_live_plan_intents(
                state_root,
                [plan],
            )[0]
        else:
            plan = existing
        receipt = execute(plan)
        receipts.append(receipt.as_dict())
    status_name = "executed" if receipts else "observed"
    reason_name = "SELL_INTENTS_HANDED_OFF" if receipts else "NO_NEW_LIVE_SELL_HANDOFF"
    return BookBLiveIntradayReceipt(
        trade_date=trade_date,
        phase=normalized_phase,
        status=status_name,
        reason=reason_name,
        account=account.as_dict(),
        decisions=tuple(decisions),
        execution_receipts=tuple(receipts),
        reconciliation_receipts=tuple(reconciled),
    )


def run_book_b_live_intraday(
    *,
    state_dir: Path,
    trade_date: str,
    phase: str,
    account_snapshot_provider: Callable[[], dict[str, Any]],
    status_provider: Callable[[tuple[BookBLiveOwnedLot, ...]], list[dict[str, Any]]],
    execute: Callable[[TradePlan], ExecutionReceipt],
    now: Callable[[], datetime],
    strategy_sha: str = "unknown",
    freeze_dir: Path | None = None,
    execute_sells: bool = True,
) -> BookBLiveIntradayReceipt:
    """Run one checkpoint under a process-wide lifecycle writer fence."""
    with _checkpoint_lock(Path(state_dir)):
        return _run_book_b_live_intraday_locked(
            state_dir=state_dir,
            trade_date=trade_date,
            phase=phase,
            account_snapshot_provider=account_snapshot_provider,
            status_provider=status_provider,
            execute=execute,
            now=now,
            strategy_sha=strategy_sha,
            freeze_dir=freeze_dir,
            execute_sells=execute_sells,
        )


__all__ = [
    "BookBLiveDecisionLedger",
    "BookBLiveIntradayReceipt",
    "load_monitor_contexts",
    "run_book_b_live_intraday",
]
