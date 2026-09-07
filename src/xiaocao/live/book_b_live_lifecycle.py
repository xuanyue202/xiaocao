"""Broker-reconciled Book B live-account lifecycle state.

This module is deliberately outside the paper account namespace.  It projects
only fills already proved by :class:`BookBOwnershipEvidence`, checks those
owned deltas against a fresh broker positions snapshot, and derives the Book B
sub-account cash, lots, exposure and liquidation NAV.  It never submits an
order and never treats the broker's mixed-account cash as Book B cash.
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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .trading_execution import account_writer_lock


BOOK_B_LIVE_INITIAL_CAPITAL = 30_000.0
BOOK_B_LIVE_DEFAULT_FEE_RATE = 0.0001
_TERMINAL_EXECUTION_STATES = frozenset(
    {"filled", "cancelled", "rejected", "skipped"}
)


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


def _finite_float(value: object, *, reason: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if not math.isfinite(result):
        raise ValueError(reason)
    return result


def _finite_decimal(value: object, *, reason: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(reason)
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if not result.is_finite():
        raise ValueError(reason)
    return result


def _nonnegative_int(value: object, *, reason: str) -> int:
    number = _finite_decimal(value, reason=reason)
    if number < 0 or number != number.to_integral_value():
        raise ValueError(reason)
    return int(number)


def _post_close_timestamp(
    value: object,
    *,
    trade_date: str,
    reason: str,
) -> datetime:
    try:
        observed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(reason) from exc
    if observed.tzinfo is None:
        raise ValueError(reason)
    local = observed.astimezone(ZoneInfo("Asia/Shanghai"))
    if (
        local.date().isoformat() != str(trade_date)[:10]
        or (local.hour, local.minute, local.second) < (15, 0, 0)
    ):
        raise ValueError(reason)
    return observed


def _normalize_code(value: object) -> str:
    text = str(value or "").strip().upper()
    digits = text.split(".", 1)[0]
    if len(digits) != 6 or not digits.isdigit():
        raise ValueError("LIVE_BOOK_B_BROKER_CODE_INVALID")
    return digits


def _read_jsonl_strict(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError
                rows.append(row)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"LIVE_BOOK_B_JSONL_INVALID:{path.name}") from exc
    return rows


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_broker_account_snapshot(
    snapshot: dict[str, Any],
    *,
    trade_date: str,
    logical_account_id: str = "primary",
    now: datetime | None = None,
    max_age_seconds: float = 300.0,
) -> dict[str, Any]:
    """Validate three row tables plus the positions-embedded funds summary."""
    payload = dict(snapshot)
    claimed_hash = str(payload.pop("snapshot_sha256", ""))
    if len(claimed_hash) != 64 or _sha256(payload) != claimed_hash:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_HASH_MISMATCH")
    if (
        snapshot.get("status") != "account_snapshot_reconciled"
        or snapshot.get("source") != "foundersc_native_app"
        or
        snapshot.get("environment") != "live"
        or snapshot.get("logical_account_id") != logical_account_id
        or snapshot.get("account_binding") not in {"proven", "bound"}
        or str(snapshot.get("trade_date") or "")[:10] != str(trade_date)[:10]
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_BINDING_MISMATCH")
    fingerprint_hash = str(snapshot.get("fund_account_binding_sha256") or "")
    if len(fingerprint_hash) != 64:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_ACCOUNT_UNPROVEN")
    tables = snapshot.get("tables")
    if not isinstance(tables, dict) or set(tables) != {
        "positions", "today-orders", "today-trades"
    }:
        raise ValueError("LIVE_BOOK_B_BROKER_THREE_TABLES_INCOMPLETE")
    for kind, table in tables.items():
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise ValueError(f"LIVE_BOOK_B_BROKER_TABLE_INVALID:{kind}")
        if int(table.get("row_count") or 0) != len(table["rows"]):
            raise ValueError(f"LIVE_BOOK_B_BROKER_TABLE_COUNT_MISMATCH:{kind}")
    funds = snapshot.get("funds_summary")
    required_funds = {
        "source",
        "total_assets",
        "securities_market_value",
        "available_cash",
        "cash_balance",
        "withdrawable_cash",
        "asset_equation_cash_field",
    }
    if (
        not isinstance(funds, dict)
        or set(funds) != required_funds
        or funds.get("source") != "positions_summary"
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_FUNDS_SUMMARY_INCOMPLETE")
    total_assets_decimal = _finite_decimal(
        funds.get("total_assets"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    securities_decimal = _finite_decimal(
        funds.get("securities_market_value"),
        reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID",
    )
    available_decimal = _finite_decimal(
        funds.get("available_cash"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    balance_decimal = _finite_decimal(
        funds.get("cash_balance"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    withdrawable_decimal = _finite_decimal(
        funds.get("withdrawable_cash"),
        reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID",
    )
    asset_equation_cash_field = str(
        funds.get("asset_equation_cash_field") or ""
    )
    common_invalid = total_assets_decimal <= 0 or min(
        securities_decimal,
        available_decimal,
        balance_decimal,
        withdrawable_decimal,
    ) < 0
    if asset_equation_cash_field == "cash_balance":
        equation_invalid = (
            balance_decimal + securities_decimal != total_assets_decimal
            or available_decimal > balance_decimal
            or withdrawable_decimal > available_decimal
        )
    elif asset_equation_cash_field == "available_cash":
        equation_invalid = available_decimal + securities_decimal != total_assets_decimal
        expected_side = "SELL" if available_decimal > balance_decimal else "BUY"
        if available_decimal > balance_decimal:
            equation_invalid = equation_invalid or withdrawable_decimal > balance_decimal
        elif balance_decimal > available_decimal:
            equation_invalid = equation_invalid or withdrawable_decimal > available_decimal
        else:
            equation_invalid = True
        if not equation_invalid:
            equation_invalid = not any(
                _broker_side(row.get("买卖标志")) == expected_side
                and _nonnegative_int(
                    row.get("成交数量"),
                    reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
                )
                > 0
                and _finite_decimal(
                    row.get("成交价格"),
                    reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
                )
                > 0
                and "撤" not in str(row.get("成交类型") or "")
                for row in tables["today-trades"]["rows"]
            )
    else:
        equation_invalid = True
    if common_invalid or equation_invalid:
        raise ValueError("LIVE_BOOK_B_BROKER_FUNDS_EQUATION_FAILED")
    total_assets = float(total_assets_decimal)
    securities = float(securities_decimal)
    available = float(available_decimal)
    balance = float(balance_decimal)
    withdrawable = float(withdrawable_decimal)
    broker_summary = snapshot.get("broker_summary")
    expected_summary = {
        "total_assets": total_assets,
        "securities_market_value": securities,
        "available_cash": available,
        "cash_balance": balance,
        "withdrawable_cash": withdrawable,
        "asset_equation_cash_field": asset_equation_cash_field,
    }
    if not isinstance(broker_summary, dict) or set(broker_summary) != set(
        expected_summary
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_SUMMARY_INCOMPLETE")
    if broker_summary.get("asset_equation_cash_field") != (
        asset_equation_cash_field
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_SUMMARY_MISMATCH")
    for field, expected in expected_summary.items():
        if field == "asset_equation_cash_field":
            continue
        actual = _finite_decimal(
            broker_summary.get(field), reason="LIVE_BOOK_B_BROKER_SUMMARY_INVALID"
        )
        if actual != Decimal(str(expected)):
            raise ValueError("LIVE_BOOK_B_BROKER_SUMMARY_MISMATCH")
    position_value = sum(
        (
            _finite_decimal(
                row.get("最新市值"),
                reason="LIVE_BOOK_B_BROKER_POSITION_VALUE_INVALID",
            )
            for row in tables["positions"]["rows"]
        ),
        Decimal("0"),
    )
    if position_value != securities_decimal:
        raise ValueError("LIVE_BOOK_B_BROKER_POSITION_SUM_MISMATCH")
    observed_raw = str(snapshot.get("observed_at") or "")
    try:
        observed = datetime.fromisoformat(observed_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_TIME_UNPROVEN") from exc
    if observed.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_TIME_UNPROVEN")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
    china = ZoneInfo("Asia/Shanghai")
    if observed.astimezone(china).date().isoformat() != str(trade_date)[:10]:
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_DATE_MISMATCH")
    age = (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    if age < -30 or age > float(max_age_seconds):
        raise ValueError("LIVE_BOOK_B_BROKER_SNAPSHOT_STALE")
    return dict(snapshot)


def _validate_ownership_chain(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    validated: list[dict[str, Any]] = []
    previous_hash: str | None = None
    cumulative_by_plan: dict[tuple[str, str], int] = {}
    cumulative_notional_by_plan: dict[tuple[str, str], Decimal] = {}
    source_execution_event_ids: set[str] = set()
    for row in rows:
        event = dict(row)
        claimed_hash = str(event.pop("event_hash", ""))
        if event.get("previous_hash") != previous_hash:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_CHAIN_BROKEN")
        if len(claimed_hash) != 64 or _sha256(event) != claimed_hash:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_EVENT_HASH_MISMATCH")
        if (
            event.get("evidence_kind") != "book_b_ownership"
            or event.get("kind") != "fill_observed"
            or event.get("book") != "B"
            or event.get("environment") != "live"
        ):
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_EVENT_INVALID")
        side = str(event.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_SIDE_INVALID")
        shares = _nonnegative_int(
            event.get("shares"), reason="LIVE_BOOK_B_OWNERSHIP_SHARES_INVALID"
        )
        price = _finite_float(
            event.get("fill_price"), reason="LIVE_BOOK_B_OWNERSHIP_FILL_PRICE_INVALID"
        )
        if shares <= 0 or price <= 0:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_FILL_INVALID")
        plan_id = str(event.get("plan_id") or "")
        plan_hash = str(event.get("plan_hash") or "")
        if not plan_id or len(plan_hash) != 64:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_PLAN_BINDING_INVALID")
        key = (plan_id, plan_hash)
        cumulative = _nonnegative_int(
            event.get("cumulative_filled_shares"),
            reason="LIVE_BOOK_B_OWNERSHIP_CUMULATIVE_INVALID",
        )
        if cumulative != cumulative_by_plan.get(key, 0) + shares:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_CUMULATIVE_MISMATCH")
        cumulative_by_plan[key] = cumulative
        fill_notional = _finite_decimal(
            event.get("fill_notional"),
            reason="LIVE_BOOK_B_OWNERSHIP_FILL_NOTIONAL_INVALID",
        )
        cumulative_notional = _finite_decimal(
            event.get("cumulative_fill_notional"),
            reason="LIVE_BOOK_B_OWNERSHIP_CUMULATIVE_NOTIONAL_INVALID",
        )
        if (
            fill_notional <= 0
            or cumulative_notional <= 0
            or cumulative_notional
            != cumulative_notional_by_plan.get(key, Decimal("0")) + fill_notional
        ):
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_NOTIONAL_MISMATCH")
        cumulative_notional_by_plan[key] = cumulative_notional
        source_event_id = str(event.get("source_execution_event_id") or "")
        if (
            not source_event_id
            or source_event_id in source_execution_event_ids
        ):
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_EXECUTION_BINDING_INVALID")
        source_execution_event_ids.add(source_event_id)
        validated.append({**event, "event_hash": claimed_hash})
        previous_hash = claimed_hash
    return validated, previous_hash


def _broker_side(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"B", "BUY", "买", "买入"}:
        return "BUY"
    if text in {"S", "SELL", "卖", "卖出"}:
        return "SELL"
    raise ValueError("LIVE_BOOK_B_BROKER_SIDE_INVALID")


def _validate_same_day_broker_fill_coverage(
    snapshot: dict[str, Any],
    ownership_rows: list[dict[str, Any]],
    *,
    trade_date: str,
) -> None:
    """Bind every same-day owned fill delta to its exact broker order."""
    fills_by_order: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in ownership_rows:
        if str(row.get("trade_date") or "")[:10] != str(trade_date)[:10]:
            continue
        order_id = str(row.get("broker_order_id") or "").strip()
        code = _normalize_code(row.get("code"))
        side = str(row.get("side") or "").upper()
        key = (
            str(row.get("plan_id") or ""),
            str(row.get("plan_hash") or ""),
            order_id,
            code,
            side,
        )
        aggregate = fills_by_order.setdefault(
            key,
            {"shares": 0, "notional": Decimal("0")},
        )
        aggregate["shares"] += _nonnegative_int(
            row.get("shares"),
            reason="LIVE_BOOK_B_BROKER_FILL_COVERAGE_INVALID",
        )
        aggregate["notional"] += _finite_decimal(
            row.get("fill_notional"),
            reason="LIVE_BOOK_B_BROKER_FILL_COVERAGE_INVALID",
        )
    if not fills_by_order:
        return
    tables = snapshot["tables"]
    order_rows = tables["today-orders"]["rows"]
    trade_rows = tables["today-trades"]["rows"]
    for key, aggregate in fills_by_order.items():
        _plan_id, _plan_hash, order_id, code, side = key
        filled_shares = aggregate["shares"]
        fill_notional = aggregate["notional"]
        if not order_id or filled_shares <= 0 or fill_notional <= 0:
            raise ValueError("LIVE_BOOK_B_BROKER_FILL_COVERAGE_INVALID")
        matching_orders = [
            row
            for row in order_rows
            if str(row.get("委托编号") or "").strip() == order_id
            and _normalize_code(row.get("证券代码")) == code
            and _broker_side(row.get("买卖标志")) == side
        ]
        if len(matching_orders) != 1:
            raise ValueError("LIVE_BOOK_B_BROKER_ORDER_FILL_UNPROVEN")
        order_filled = _nonnegative_int(
            matching_orders[0].get("成交数量") or 0,
            reason="LIVE_BOOK_B_BROKER_ORDER_FILL_UNPROVEN",
        )
        if order_filled != filled_shares:
            raise ValueError("LIVE_BOOK_B_BROKER_ORDER_FILL_MISMATCH")
        matching_trades: list[dict[str, Any]] = []
        for row in trade_rows:
            if (
                str(row.get("委托编号") or "").strip() != order_id
                or _normalize_code(row.get("证券代码")) != code
                or _broker_side(row.get("买卖标志")) != side
            ):
                continue
            price = _finite_decimal(
                row.get("成交价格"),
                reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
            )
            if "撤" in str(row.get("成交类型") or "") or price == 0:
                continue
            if price < 0:
                raise ValueError("LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN")
            matching_trades.append(row)
        trade_shares = sum(
            _nonnegative_int(
                row.get("成交数量"),
                reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
            )
            for row in matching_trades
        )
        trade_notional = sum(
            (
                _finite_decimal(
                    row.get("成交价格"),
                    reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
                )
                * _nonnegative_int(
                    row.get("成交数量"),
                    reason="LIVE_BOOK_B_BROKER_TRADE_FILL_UNPROVEN",
                )
                for row in matching_trades
            ),
            Decimal("0"),
        )
        if trade_shares != filled_shares or trade_notional != fill_notional:
            raise ValueError("LIVE_BOOK_B_BROKER_TRADE_FILL_MISMATCH")


def _load_intent_index(state_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    intent_dir = state_dir / "plan_intents"
    if not intent_dir.is_dir():
        return index
    for path in sorted(intent_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("LIVE_BOOK_B_PLAN_INTENT_INVALID") from exc
        plan = payload.get("plan") if isinstance(payload, dict) else None
        if not isinstance(plan, dict):
            raise ValueError("LIVE_BOOK_B_PLAN_INTENT_INVALID")
        plan_id = str(plan.get("plan_id") or "")
        if not plan_id or payload.get("plan_hash") != _sha256(plan):
            raise ValueError("LIVE_BOOK_B_PLAN_INTENT_HASH_MISMATCH")
        if plan_id in index:
            raise ValueError("LIVE_BOOK_B_PLAN_INTENT_DUPLICATE")
        index[plan_id] = dict(plan)
    return index


def _validate_execution_fill_coverage(
    state_dir: Path,
    ownership_rows: list[dict[str, Any]],
) -> None:
    """Prove every broker fill in execution state reached ownership evidence."""
    events = _read_jsonl_strict(Path(state_dir) / "events.jsonl")
    ownership_cumulative: dict[tuple[str, str], int] = {}
    ownership_source_ids: set[str] = set()
    for row in ownership_rows:
        key = (str(row.get("plan_id") or ""), str(row.get("plan_hash") or ""))
        ownership_cumulative[key] = max(
            ownership_cumulative.get(key, 0),
            _nonnegative_int(
                row.get("cumulative_filled_shares"),
                reason="LIVE_BOOK_B_OWNERSHIP_CUMULATIVE_INVALID",
            ),
        )
        source_id = str(row.get("source_execution_event_id") or "")
        if not source_id:
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_EXECUTION_BINDING_MISSING")
        ownership_source_ids.add(source_id)

    previous_by_plan: dict[str, str | None] = {}
    sequence_by_plan: dict[str, int] = {}
    execution_event_ids: set[str] = set()
    required_cumulative: dict[tuple[str, str], int] = {}
    for row in events:
        event = dict(row)
        claimed_hash = str(event.pop("event_hash", ""))
        plan_id = str(event.get("plan_id") or "")
        plan_hash = str(event.get("plan_hash") or "")
        receipt = event.get("receipt")
        if not plan_id or not plan_hash or not isinstance(receipt, dict):
            raise ValueError("LIVE_BOOK_B_EXECUTION_EVENT_INVALID")
        expected_sequence = sequence_by_plan.get(plan_id, 0) + 1
        if (
            event.get("sequence") != expected_sequence
            or event.get("previous_hash") != previous_by_plan.get(plan_id)
            or len(claimed_hash) != 64
            or _sha256(event) != claimed_hash
            or str(receipt.get("plan_id") or "") != plan_id
            or str(receipt.get("plan_hash") or "") != plan_hash
        ):
            raise ValueError("LIVE_BOOK_B_EXECUTION_CHAIN_BROKEN")
        sequence_by_plan[plan_id] = expected_sequence
        previous_by_plan[plan_id] = claimed_hash
        event_id = str(event.get("event_id") or "")
        if not event_id or str(receipt.get("event_id") or "") != event_id:
            raise ValueError("LIVE_BOOK_B_EXECUTION_EVENT_INVALID")
        execution_event_ids.add(event_id)
        filled = _nonnegative_int(
            receipt.get("filled_shares"),
            reason="LIVE_BOOK_B_EXECUTION_FILL_INVALID",
        )
        key = (plan_id, plan_hash)
        required_cumulative[key] = max(required_cumulative.get(key, 0), filled)
    if not ownership_source_ids.issubset(execution_event_ids):
        raise ValueError("LIVE_BOOK_B_OWNERSHIP_EXECUTION_BINDING_MISMATCH")
    for key, filled in required_cumulative.items():
        if filled > ownership_cumulative.get(key, 0):
            raise ValueError("LIVE_BOOK_B_EXECUTION_FILL_NOT_OWNED")


def open_execution_plan_ids(state_dir: Path) -> tuple[str, ...]:
    intents = _load_intent_index(Path(state_dir))
    intent_hashes = {plan_id: _sha256(plan) for plan_id, plan in intents.items()}
    latest = {plan_id: "" for plan_id in intents}
    for event in _read_jsonl_strict(Path(state_dir) / "events.jsonl"):
        receipt = event.get("receipt") if isinstance(event.get("receipt"), dict) else {}
        plan_id = str(event.get("plan_id") or receipt.get("plan_id") or "")
        state = str(event.get("state") or receipt.get("state") or "").lower()
        if plan_id:
            if (
                plan_id in intent_hashes
                and str(event.get("plan_hash") or receipt.get("plan_hash") or "")
                != intent_hashes[plan_id]
            ):
                raise ValueError("LIVE_BOOK_B_PLAN_INTENT_EVENT_HASH_MISMATCH")
            latest[plan_id] = state
    return tuple(
        sorted(
            plan_id
            for plan_id, state in latest.items()
            if state not in _TERMINAL_EXECUTION_STATES
        )
    )


def ownership_head_sha256(state_dir: Path) -> str | None:
    """Return the ownership head after execution-fill coverage is proven."""
    rows, head = _validate_ownership_chain(
        _read_jsonl_strict(Path(state_dir) / "book_b_ownership_evidence.jsonl")
    )
    _validate_execution_fill_coverage(Path(state_dir), rows)
    return head


@dataclass(frozen=True)
class BookBLiveOwnedLot:
    owned_lot_id: str
    code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    sellable_shares: int
    current_price: float
    market_value: float
    liquidation_value_after_fee: float
    buy_fee_rate: float
    sell_fee_rate: float
    snapshot_ref: str
    monitor_context: dict[str, Any]


@dataclass(frozen=True)
class BookBLiveAccountState:
    trade_date: str
    logical_account_id: str
    cash: float
    current_open_exposure: float
    liquidation_value_after_fee: float
    settled_nav: float
    realized_cash_delta: float
    ownership_head_sha256: str | None
    broker_snapshot_sha256: str
    broker_snapshot_observed_at: str
    lots: tuple[BookBLiveOwnedLot, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lots"] = [asdict(lot) for lot in self.lots]
        return payload


def project_book_b_live_account(
    state_dir: Path,
    broker_snapshot: dict[str, Any],
    *,
    trade_date: str,
    now: datetime | None = None,
    monitor_context_by_lot: dict[str, dict[str, Any]] | None = None,
    initial_capital: float = BOOK_B_LIVE_INITIAL_CAPITAL,
    default_fee_rate: float = BOOK_B_LIVE_DEFAULT_FEE_RATE,
) -> BookBLiveAccountState:
    """Project owned lots and Book B NAV from proved fills plus broker marks."""
    snapshot = validate_broker_account_snapshot(
        broker_snapshot, trade_date=trade_date, now=now
    )
    state_root = Path(state_dir)
    evidence_rows, ownership_head = _validate_ownership_chain(
        _read_jsonl_strict(state_root / "book_b_ownership_evidence.jsonl")
    )
    _validate_execution_fill_coverage(state_root, evidence_rows)
    _validate_same_day_broker_fill_coverage(
        snapshot,
        evidence_rows,
        trade_date=trade_date,
    )
    intents = _load_intent_index(state_root)
    contexts = monitor_context_by_lot or {}

    broker_positions: dict[str, dict[str, Any]] = {}
    for row in snapshot["tables"]["positions"]["rows"]:
        code6 = _normalize_code(row.get("证券代码"))
        if code6 in broker_positions:
            raise ValueError(f"LIVE_BOOK_B_BROKER_POSITION_DUPLICATE:{code6}")
        broker_positions[code6] = {
            "shares": _nonnegative_int(
                row.get("证券数量"), reason="LIVE_BOOK_B_BROKER_SHARES_INVALID"
            ),
            "sellable": _nonnegative_int(
                row.get("可卖数量"), reason="LIVE_BOOK_B_BROKER_SELLABLE_INVALID"
            ),
            "price": _finite_float(
                row.get("当前价"), reason="LIVE_BOOK_B_BROKER_PRICE_INVALID"
            ),
        }

    lot_rows: dict[str, dict[str, Any]] = {}
    cash = _finite_decimal(
        initial_capital, reason="LIVE_BOOK_B_INITIAL_CAPITAL_INVALID"
    )
    for event in evidence_rows:
        if event.get("logical_account_id") != "primary":
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_ACCOUNT_MISMATCH")
        side = str(event["side"]).upper()
        shares = _nonnegative_int(
            event.get("shares"), reason="LIVE_BOOK_B_OWNERSHIP_SHARES_INVALID"
        )
        fill_notional = _finite_decimal(
            event.get("fill_notional"),
            reason="LIVE_BOOK_B_OWNERSHIP_FILL_NOTIONAL_INVALID",
        )
        plan_id = str(event.get("plan_id") or "")
        intent = intents.get(plan_id)
        if intent is None or _sha256(intent) != str(event.get("plan_hash") or ""):
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_PLAN_INTENT_UNPROVEN")
        fee_rate = _finite_decimal(
            intent.get("fee_rate", default_fee_rate),
            reason="LIVE_BOOK_B_FEE_RATE_INVALID",
        )
        if fee_rate < 0 or fee_rate >= 1:
            raise ValueError("LIVE_BOOK_B_FEE_RATE_INVALID")
        if side == "BUY":
            lot_id = plan_id
            snapshot_ref = str(intent.get("snapshot_ref") or "")
            if not snapshot_ref:
                raise ValueError("LIVE_BOOK_B_BUY_SNAPSHOT_REF_UNPROVEN")
            current = lot_rows.setdefault(
                lot_id,
                {
                    "owned_lot_id": lot_id,
                    "code": str(event.get("code") or ""),
                    "name": str(event.get("name") or event.get("code") or ""),
                    "entry_date": str(event.get("trade_date") or "")[:10],
                    "cost": Decimal("0"),
                    "shares": 0,
                    "buy_fee_rate": fee_rate,
                    "sell_fee_rate": fee_rate,
                    "snapshot_ref": snapshot_ref,
                },
            )
            if current["snapshot_ref"] != snapshot_ref:
                raise ValueError("LIVE_BOOK_B_BUY_SNAPSHOT_REF_MISMATCH")
            current["cost"] += fill_notional
            current["shares"] += shares
            cash -= fill_notional * (Decimal("1") + fee_rate)
        else:
            lot_id = str(event.get("owned_lot_id") or intent.get("owned_lot_id") or "")
            if not lot_id or lot_id not in lot_rows:
                raise ValueError("LIVE_BOOK_B_SELL_OWNED_LOT_UNPROVEN")
            if lot_rows[lot_id]["shares"] < shares:
                raise ValueError("LIVE_BOOK_B_SELL_EXCEEDS_OWNED_LOT")
            average_cost = lot_rows[lot_id]["cost"] / int(
                lot_rows[lot_id]["shares"]
            )
            lot_rows[lot_id]["cost"] -= average_cost * shares
            lot_rows[lot_id]["shares"] -= shares
            cash += fill_notional * (Decimal("1") - fee_rate)

    owned_by_code: dict[str, int] = {}
    for lot in lot_rows.values():
        if lot["shares"] <= 0:
            continue
        code6 = _normalize_code(lot["code"])
        owned_by_code[code6] = owned_by_code.get(code6, 0) + int(lot["shares"])
    for code6, owned in owned_by_code.items():
        broker = broker_positions.get(code6)
        if broker is None or broker["shares"] < owned:
            raise ValueError(f"LIVE_BOOK_B_BROKER_OWNERSHIP_MISMATCH:{code6}")

    remaining_sellable = {
        code6: min(int(position["sellable"]), owned_by_code.get(code6, 0))
        for code6, position in broker_positions.items()
    }
    lots: list[BookBLiveOwnedLot] = []
    for lot_id, row in sorted(
        lot_rows.items(), key=lambda item: (item[1]["entry_date"], item[0])
    ):
        shares = int(row["shares"])
        if shares <= 0:
            continue
        code6 = _normalize_code(row["code"])
        broker = broker_positions[code6]
        entry_date = str(row["entry_date"])
        if entry_date >= str(trade_date)[:10]:
            # Broker sellable is account-level.  A manual older holding of the
            # same code must never make today's Book-B-owned lot appear T+1
            # eligible, so same-day lots consume none of that quantity.
            sellable = 0
        else:
            sellable = min(shares, remaining_sellable.get(code6, 0))
            remaining_sellable[code6] = max(
                0, remaining_sellable.get(code6, 0) - sellable
            )
        price = float(broker["price"])
        if price <= 0:
            raise ValueError(f"LIVE_BOOK_B_BROKER_MARK_INVALID:{code6}")
        entry_price = row["cost"] / shares
        fee_rate = row["sell_fee_rate"]
        lots.append(
            BookBLiveOwnedLot(
                owned_lot_id=lot_id,
                code=str(row["code"]),
                name=str(row["name"]),
                entry_date=entry_date,
                entry_price=round(float(entry_price), 6),
                shares=shares,
                sellable_shares=sellable,
                current_price=round(price, 6),
                market_value=round(price * shares, 2),
                liquidation_value_after_fee=round(
                    price * shares * (1.0 - float(fee_rate)), 2
                ),
                buy_fee_rate=float(row["buy_fee_rate"]),
                sell_fee_rate=float(fee_rate),
                snapshot_ref=str(row["snapshot_ref"]),
                monitor_context=dict(contexts.get(lot_id) or {}),
            )
        )
    exposure = round(sum(lot.market_value for lot in lots), 2)
    liquidation = round(sum(lot.liquidation_value_after_fee for lot in lots), 2)
    cash = cash.quantize(Decimal("0.01"))
    if cash < Decimal("-0.10"):
        raise ValueError("LIVE_BOOK_B_SUBACCOUNT_CASH_NEGATIVE")
    nav = cash + Decimal(str(liquidation))
    return BookBLiveAccountState(
        trade_date=str(trade_date)[:10],
        logical_account_id="primary",
        cash=float(cash),
        current_open_exposure=exposure,
        liquidation_value_after_fee=liquidation,
        settled_nav=float(nav),
        realized_cash_delta=float(
            (
                cash
                - _finite_decimal(
                    initial_capital,
                    reason="LIVE_BOOK_B_INITIAL_CAPITAL_INVALID",
                )
            ).quantize(Decimal("0.01"))
        ),
        ownership_head_sha256=ownership_head,
        broker_snapshot_sha256=str(snapshot["snapshot_sha256"]),
        broker_snapshot_observed_at=str(snapshot["observed_at"]),
        lots=tuple(lots),
    )


def settlement_path(state_dir: Path, trade_date: str) -> Path:
    return Path(state_dir) / "settlements" / f"{str(trade_date)[:10]}.json"


@contextmanager
def _account_execution_ownership_snapshot_lock(state_dir: Path):
    """Match the execution lock order while settlement is committed."""
    root = Path(state_dir)
    handles = []
    with account_writer_lock(root / "account_writer_locks", "primary"):
        try:
            for path in (
                root / "plan_intents" / ".lock",
                root / "events.jsonl.lock",
                root / "book_b_ownership_evidence.jsonl.lock",
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open("a+", encoding="utf-8")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                handles.append(handle)
            yield
        finally:
            for handle in reversed(handles):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()


def write_book_b_live_settlement(
    state_dir: Path,
    account: BookBLiveAccountState,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write one immutable EOD settlement after all live plans are terminal."""
    root = Path(state_dir)
    with _account_execution_ownership_snapshot_lock(root):
        open_plans = open_execution_plan_ids(root)
        if open_plans:
            raise ValueError("LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED")
        current_ownership_head = ownership_head_sha256(root)
        if current_ownership_head != account.ownership_head_sha256:
            raise ValueError("LIVE_BOOK_B_SETTLEMENT_OWNERSHIP_CHANGED")
        path = settlement_path(root, account.trade_date)
        if path.exists():
            existing = load_latest_book_b_live_settlement(root)
            if existing is None or existing.get("trade_date") != account.trade_date:
                raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID")
            # Crash recovery may read the same account through a newer
            # three-table snapshot. The already-written settlement remains
            # authoritative only while the locked ownership head is unchanged.
            if existing.get("ownership_head_sha256") != current_ownership_head:
                raise ValueError("LIVE_BOOK_B_SETTLEMENT_IMMUTABILITY_VIOLATION")
            return existing
        observed = now or datetime.now(timezone.utc)
        if observed.tzinfo is None:
            raise ValueError("LIVE_BOOK_B_NOW_NOT_TZ_AWARE")
        _post_close_timestamp(
            observed.isoformat(),
            trade_date=account.trade_date,
            reason="LIVE_BOOK_B_SETTLEMENT_WINDOW_NOT_OPEN",
        )
        _post_close_timestamp(
            account.broker_snapshot_observed_at,
            trade_date=account.trade_date,
            reason="LIVE_BOOK_B_SETTLEMENT_SNAPSHOT_PRE_CLOSE",
        )
        body = {
            "schema_version": 1,
            "status": "settled",
            "capital_basis_source": "broker_reconciled_book_b_nav",
            "trade_date": account.trade_date,
            "environment": "live",
            "logical_account_id": account.logical_account_id,
            "account_binding": "proven",
            "settled_at": observed.isoformat(),
            **account.as_dict(),
        }
        body["settlement_sha256"] = _sha256(body)
        _write_json_atomic(path, body)
        return body


def load_latest_book_b_live_settlement(state_dir: Path) -> dict[str, Any] | None:
    paths = sorted((Path(state_dir) / "settlements").glob("*.json"))
    if not paths:
        return None
    path = paths[-1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID")
    claimed = str(payload.pop("settlement_sha256", ""))
    if len(claimed) != 64 or _sha256(payload) != claimed:
        raise ValueError("LIVE_BOOK_B_SETTLEMENT_HASH_MISMATCH")
    payload["settlement_sha256"] = claimed
    if (
        payload.get("status") != "settled"
        or payload.get("capital_basis_source") != "broker_reconciled_book_b_nav"
        or payload.get("environment") != "live"
        or payload.get("logical_account_id") != "primary"
        or payload.get("account_binding") != "proven"
    ):
        raise ValueError("LIVE_BOOK_B_SETTLEMENT_BINDING_MISMATCH")
    trade_date = str(payload.get("trade_date") or "")[:10]
    _post_close_timestamp(
        payload.get("settled_at"),
        trade_date=trade_date,
        reason="LIVE_BOOK_B_SETTLEMENT_TIME_INVALID",
    )
    _post_close_timestamp(
        payload.get("broker_snapshot_observed_at"),
        trade_date=trade_date,
        reason="LIVE_BOOK_B_SETTLEMENT_SNAPSHOT_INVALID",
    )
    return payload


__all__ = [
    "BOOK_B_LIVE_DEFAULT_FEE_RATE",
    "BOOK_B_LIVE_INITIAL_CAPITAL",
    "BookBLiveAccountState",
    "BookBLiveOwnedLot",
    "load_latest_book_b_live_settlement",
    "open_execution_plan_ids",
    "ownership_head_sha256",
    "project_book_b_live_account",
    "settlement_path",
    "validate_broker_account_snapshot",
    "write_book_b_live_settlement",
]
