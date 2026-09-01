"""Broker-reconciled Book B live-account lifecycle state.

This module is deliberately outside the paper account namespace.  It projects
only fills already proved by :class:`BookBOwnershipEvidence`, checks those
owned deltas against a fresh broker positions snapshot, and derives the Book B
sub-account cash, lots, exposure and liquidation NAV.  It never submits an
order and never treats the broker's mixed-account cash as Book B cash.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


BOOK_B_LIVE_INITIAL_CAPITAL = 30_000.0
BOOK_B_LIVE_DEFAULT_FEE_RATE = 0.0001
_ACTIVE_EXECUTION_STATES = frozenset(
    {"claimed", "submitted", "acknowledged", "partial", "unknown", "reconciling"}
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


def _nonnegative_int(value: object, *, reason: str) -> int:
    try:
        result = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if result < 0:
        raise ValueError(reason)
    return result


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
    }
    if (
        not isinstance(funds, dict)
        or set(funds) != required_funds
        or funds.get("source") != "positions_summary"
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_FUNDS_SUMMARY_INCOMPLETE")
    total_assets = _finite_float(
        funds.get("total_assets"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    securities = _finite_float(
        funds.get("securities_market_value"),
        reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID",
    )
    available = _finite_float(
        funds.get("available_cash"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    balance = _finite_float(
        funds.get("cash_balance"), reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID"
    )
    withdrawable = _finite_float(
        funds.get("withdrawable_cash"),
        reason="LIVE_BOOK_B_BROKER_FUNDS_INVALID",
    )
    if (
        total_assets <= 0
        or min(securities, available, balance, withdrawable) < 0
        or abs((balance + securities) - total_assets) > 0.10
        or available > balance + 0.10
        or withdrawable > available + 0.10
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_FUNDS_EQUATION_FAILED")
    broker_summary = snapshot.get("broker_summary")
    expected_summary = {
        "total_assets": total_assets,
        "securities_market_value": securities,
        "available_cash": available,
        "cash_balance": balance,
        "withdrawable_cash": withdrawable,
    }
    if not isinstance(broker_summary, dict) or set(broker_summary) != set(
        expected_summary
    ):
        raise ValueError("LIVE_BOOK_B_BROKER_SUMMARY_INCOMPLETE")
    for field, expected in expected_summary.items():
        actual = _finite_float(
            broker_summary.get(field), reason="LIVE_BOOK_B_BROKER_SUMMARY_INVALID"
        )
        if abs(actual - expected) > 0.001:
            raise ValueError("LIVE_BOOK_B_BROKER_SUMMARY_MISMATCH")
    position_value = sum(
        _finite_float(
            row.get("最新市值"), reason="LIVE_BOOK_B_BROKER_POSITION_VALUE_INVALID"
        )
        for row in tables["positions"]["rows"]
    )
    if abs(position_value - securities) > 0.10:
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
    latest: dict[str, str] = {}
    for event in _read_jsonl_strict(Path(state_dir) / "events.jsonl"):
        receipt = event.get("receipt") if isinstance(event.get("receipt"), dict) else {}
        plan_id = str(event.get("plan_id") or receipt.get("plan_id") or "")
        state = str(event.get("state") or receipt.get("state") or "").lower()
        if plan_id:
            latest[plan_id] = state
    return tuple(sorted(plan_id for plan_id, state in latest.items() if state in _ACTIVE_EXECUTION_STATES))


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
    cash = float(initial_capital)
    for event in evidence_rows:
        if event.get("logical_account_id") != "primary":
            raise ValueError("LIVE_BOOK_B_OWNERSHIP_ACCOUNT_MISMATCH")
        side = str(event["side"]).upper()
        shares = int(event["shares"])
        fill_price = float(event["fill_price"])
        intent = intents.get(str(event.get("plan_id") or ""), {})
        fee_rate = _finite_float(
            intent.get("fee_rate", default_fee_rate),
            reason="LIVE_BOOK_B_FEE_RATE_INVALID",
        )
        if fee_rate < 0 or fee_rate >= 1:
            raise ValueError("LIVE_BOOK_B_FEE_RATE_INVALID")
        if side == "BUY":
            lot_id = str(event.get("plan_id") or "")
            current = lot_rows.setdefault(
                lot_id,
                {
                    "owned_lot_id": lot_id,
                    "code": str(event.get("code") or ""),
                    "name": str(event.get("name") or event.get("code") or ""),
                    "entry_date": str(event.get("trade_date") or "")[:10],
                    "cost": 0.0,
                    "shares": 0,
                    "buy_fee_rate": fee_rate,
                    "sell_fee_rate": fee_rate,
                },
            )
            current["cost"] += fill_price * shares
            current["shares"] += shares
            cash -= fill_price * shares * (1.0 + fee_rate)
        else:
            lot_id = str(event.get("owned_lot_id") or intent.get("owned_lot_id") or "")
            if not lot_id or lot_id not in lot_rows:
                raise ValueError("LIVE_BOOK_B_SELL_OWNED_LOT_UNPROVEN")
            if lot_rows[lot_id]["shares"] < shares:
                raise ValueError("LIVE_BOOK_B_SELL_EXCEEDS_OWNED_LOT")
            average_cost = (
                float(lot_rows[lot_id]["cost"])
                / int(lot_rows[lot_id]["shares"])
            )
            lot_rows[lot_id]["cost"] -= average_cost * shares
            lot_rows[lot_id]["shares"] -= shares
            cash += fill_price * shares * (1.0 - fee_rate)

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
        entry_price = float(row["cost"]) / max(1, shares)
        fee_rate = float(row["sell_fee_rate"])
        lots.append(
            BookBLiveOwnedLot(
                owned_lot_id=lot_id,
                code=str(row["code"]),
                name=str(row["name"]),
                entry_date=entry_date,
                entry_price=round(entry_price, 6),
                shares=shares,
                sellable_shares=sellable,
                current_price=round(price, 6),
                market_value=round(price * shares, 2),
                liquidation_value_after_fee=round(price * shares * (1.0 - fee_rate), 2),
                buy_fee_rate=float(row["buy_fee_rate"]),
                sell_fee_rate=fee_rate,
                monitor_context=dict(contexts.get(lot_id) or {}),
            )
        )
    exposure = round(sum(lot.market_value for lot in lots), 2)
    liquidation = round(sum(lot.liquidation_value_after_fee for lot in lots), 2)
    cash = round(cash, 2)
    if cash < -0.10:
        raise ValueError("LIVE_BOOK_B_SUBACCOUNT_CASH_NEGATIVE")
    nav = round(cash + liquidation, 2)
    return BookBLiveAccountState(
        trade_date=str(trade_date)[:10],
        logical_account_id="primary",
        cash=cash,
        current_open_exposure=exposure,
        liquidation_value_after_fee=liquidation,
        settled_nav=nav,
        realized_cash_delta=round(cash - float(initial_capital), 2),
        ownership_head_sha256=ownership_head,
        broker_snapshot_sha256=str(snapshot["snapshot_sha256"]),
        broker_snapshot_observed_at=str(snapshot["observed_at"]),
        lots=tuple(lots),
    )


def settlement_path(state_dir: Path, trade_date: str) -> Path:
    return Path(state_dir) / "settlements" / f"{str(trade_date)[:10]}.json"


def write_book_b_live_settlement(
    state_dir: Path,
    account: BookBLiveAccountState,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write one immutable EOD settlement after all live plans are terminal."""
    open_plans = open_execution_plan_ids(Path(state_dir))
    if open_plans:
        raise ValueError("LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED")
    path = settlement_path(Path(state_dir), account.trade_date)
    if path.exists():
        existing = load_latest_book_b_live_settlement(Path(state_dir))
        if existing is None or existing.get("trade_date") != account.trade_date:
            raise ValueError("LIVE_BOOK_B_SETTLEMENT_INVALID")
        # Crash recovery may read the same account through a newer three-table
        # snapshot.  The already-written settlement remains authoritative as
        # long as no new broker-proved ownership event appeared.
        if existing.get("ownership_head_sha256") != account.ownership_head_sha256:
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
