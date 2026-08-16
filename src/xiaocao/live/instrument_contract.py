"""Verified instrument and market-data contracts for paper execution.

Book T v2 treats an ETF as an expression of a theme, not as a stock-shaped
row.  This module is the narrow execution seam for that distinction: callers
provide explicit instrument metadata and proprietary market facts, and the
module either returns a verified contract or a fail-closed reason.

The module intentionally does not fetch data or write a ledger.  API clients
and paper writers are adapters around this interface; keeping the validation
here makes lot sizing, fees, and sellability consistent for every caller.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


INSTRUMENT_CONTRACT_SCHEMA_VERSION = 1
VALID_INSTRUMENT_TYPES = frozenset({"equity", "etf"})
VALID_SETTLEMENT_CYCLES = frozenset({"T+0", "T+1"})
VERIFIED_MARKET_CONTRACT_STATES = frozenset({"verified", "valid", "ok", "available"})
PROPRIETARY_SOURCES = frozenset({"xiaocao_api", "xiaocao", "proprietary_api"})


class InstrumentContractError(ValueError):
    """The instrument cannot safely enter a paper execution path."""


class UnknownInstrumentContract(InstrumentContractError):
    """Required instrument metadata is missing or not understood."""


@dataclass(frozen=True)
class InstrumentContract:
    """Explicit execution metadata for one tradeable instrument."""

    code: str
    instrument_type: str
    lot_size: int
    settlement_cycle: str
    buy_fee_rate: float
    sell_fee_rate: float
    name: str = ""
    catalog_trade_date: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    market_data_contract: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "InstrumentContract":
        """Build a strict contract from a row or an ``instrument_contract`` map.

        No defaults are supplied for lot size, settlement cycle, or fees.  A
        missing value is an execution blocker rather than an invitation to
        reuse the 100-share stock convention.
        """
        if not isinstance(raw, Mapping):
            raise UnknownInstrumentContract("instrument contract must be an object")

        nested = raw.get("instrument_contract")
        if isinstance(nested, Mapping):
            # Keep row-level identity/provenance as fallbacks when a writer
            # stores only execution metadata in the nested contract.
            raw = {**raw, **nested}

        code = _required_text(raw.get("code") or raw.get("stockId"), "code")
        instrument_type = _normalize_instrument_type(raw.get("instrument_type"))
        lot_size = _normalize_lot_size(raw.get("lot_size"))
        settlement_cycle = _normalize_settlement_cycle(raw.get("settlement_cycle"))

        shared_fee = raw.get("fee_rate")
        buy_fee_rate = _normalize_fee(
            raw.get("buy_fee_rate", shared_fee), "buy_fee_rate"
        )
        sell_fee_rate = _normalize_fee(
            raw.get("sell_fee_rate", shared_fee), "sell_fee_rate"
        )

        provenance = raw.get("provenance") or raw.get("source_metadata") or {}
        if not isinstance(provenance, Mapping):
            raise UnknownInstrumentContract("provenance must be an object")
        provenance_copy = {str(key): value for key, value in provenance.items()}
        catalog_trade_date = _normalize_date(
            provenance_copy.get("trade_date")
            or raw.get("catalog_trade_date")
            or raw.get("tradeDate")
        )

        market_data_contract = (
            raw.get("market_data_contract")
            or raw.get("quote_contract")
            or {}
        )
        if not isinstance(market_data_contract, Mapping):
            raise UnknownInstrumentContract("market_data_contract must be an object")

        return cls(
            code=code,
            instrument_type=instrument_type,
            lot_size=lot_size,
            settlement_cycle=settlement_cycle,
            buy_fee_rate=buy_fee_rate,
            sell_fee_rate=sell_fee_rate,
            name=str(raw.get("name") or raw.get("stockName") or ""),
            catalog_trade_date=catalog_trade_date,
            provenance=provenance_copy,
            market_data_contract={str(key): value for key, value in market_data_contract.items()},
        )

    @property
    def fee_rate(self) -> float:
        """Compatibility view for callers that use one rate for both sides."""
        return self.buy_fee_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INSTRUMENT_CONTRACT_SCHEMA_VERSION,
            "code": self.code,
            "name": self.name,
            "instrument_type": self.instrument_type,
            "lot_size": self.lot_size,
            "settlement_cycle": self.settlement_cycle,
            "buy_fee_rate": self.buy_fee_rate,
            "sell_fee_rate": self.sell_fee_rate,
            "provenance": dict(self.provenance),
            "catalog_trade_date": self.catalog_trade_date,
            "market_data_contract": dict(self.market_data_contract),
        }


@dataclass(frozen=True)
class MarketDataValidation:
    """Result of checking the facts required for a paper fill or valuation."""

    status: str
    reason: str
    source: str
    price: float | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ready"


def contract_from_record(
    record: Mapping[str, Any], *, strict: bool = False
) -> InstrumentContract | None:
    """Read an explicit contract from a candidate/position row.

    Legacy equity rows may omit metadata while the old Book B/T path is being
    migrated, so non-strict reads return ``None`` for those rows.  An explicit
    ETF row is never inferred: strict callers must provide all fields.
    """
    if not isinstance(record, Mapping):
        if strict:
            raise UnknownInstrumentContract("instrument row must be an object")
        return None
    raw = record.get("instrument_contract")
    if raw is None:
        raw = record if record.get("instrument_type") is not None else None
    if raw is None:
        if strict:
            raise UnknownInstrumentContract("instrument_type is required")
        return None
    try:
        return InstrumentContract.from_mapping(raw)
    except InstrumentContractError:
        if strict:
            raise
        return None


def market_contract_verified(
    contract: InstrumentContract,
    *,
    required: Sequence[str] = ("realtime", "minute", "daily"),
) -> bool:
    """Whether the named proprietary quote contracts were explicitly verified."""
    return all(
        str(contract.market_data_contract.get(name) or "").strip().lower()
        in VERIFIED_MARKET_CONTRACT_STATES
        for name in required
    )


def minute_trade_price(row: Mapping[str, Any], *, instrument_type: str) -> float | None:
    """Return the authoritative minute price.

    ETF minute payloads use ``trade``.  ``close`` is deliberately ignored for
    ETFs because the endpoint can return null or a non-price placeholder in
    that field.  Equities retain the close fallback for legacy fixtures.
    """
    trade = _positive_float(row.get("trade"))
    if trade is not None:
        return trade
    if instrument_type == "etf":
        return None
    return _positive_float(row.get("close"))


def validate_market_data(
    record: Mapping[str, Any],
    *,
    realtime: Mapping[str, Any] | None,
    minute_rows: Sequence[Mapping[str, Any]] | None,
    daily_rows: Sequence[Mapping[str, Any]] | None,
    liquidity: Mapping[str, Any] | None,
    as_of: str | None = None,
    source: str = "xiaocao_api",
    max_catalog_age_days: int = 1,
) -> MarketDataValidation:
    """Validate the complete proprietary market contract for one instrument.

    The order is deliberate: source and instrument identity are checked before
    freshness, then realtime/minute/daily facts and liquidity.  The first
    failure is returned as a stable reason for audit and fail-closed callers.
    """
    normalized_source = str(source or "").strip().lower()
    if normalized_source not in PROPRIETARY_SOURCES:
        return _failure("PUBLIC_SOURCE_FORBIDDEN", normalized_source or "unknown")

    try:
        contract = contract_from_record(record, strict=True)
    except InstrumentContractError as exc:
        return _failure("INSTRUMENT_CONTRACT_UNVERIFIED", normalized_source, error=str(exc))
    assert contract is not None

    provenance_source = str(contract.provenance.get("source") or normalized_source).strip().lower()
    if provenance_source not in PROPRIETARY_SOURCES:
        return _failure("PUBLIC_SOURCE_FORBIDDEN", provenance_source or "unknown")

    normalized_as_of = _normalize_date(as_of)
    if normalized_as_of:
        if not contract.catalog_trade_date:
            return _failure("CATALOG_DATE_MISSING", normalized_source)
        try:
            age = (date.fromisoformat(normalized_as_of) - date.fromisoformat(contract.catalog_trade_date)).days
        except ValueError:
            return _failure("CATALOG_DATE_INVALID", normalized_source)
        if age < 0 or age > max(0, int(max_catalog_age_days)):
            return _failure("CATALOG_STALE", normalized_source, age_days=age)

    for field_name in ("realtime", "minute", "daily"):
        state = str(contract.market_data_contract.get(field_name) or "").strip().lower()
        if state not in VERIFIED_MARKET_CONTRACT_STATES:
            return _failure("MARKET_CONTRACT_UNVERIFIED", normalized_source, field=field_name)

    if not isinstance(realtime, Mapping):
        return _failure("REALTIME_MISSING", normalized_source)
    realtime_status = _trading_status(realtime)
    if realtime_status == "halted":
        return _failure("HALTED", normalized_source)
    if realtime_status != "active":
        return _failure("REALTIME_STATUS_UNKNOWN", normalized_source)
    realtime_price = _positive_float(realtime.get("trade"))
    if realtime_price is None:
        return _failure("REALTIME_TRADE_MISSING", normalized_source)
    realtime_date = _row_date(realtime)
    if normalized_as_of and realtime_date and realtime_date != normalized_as_of:
        return _failure("REALTIME_STALE", normalized_source, trade_date=realtime_date)

    if not isinstance(minute_rows, Sequence) or isinstance(minute_rows, (str, bytes)) or not minute_rows:
        return _failure("MINUTE_MISSING", normalized_source)
    matching_minutes = [
        row for row in minute_rows
        if isinstance(row, Mapping)
        and (not normalized_as_of or not _row_date(row) or _row_date(row) == normalized_as_of)
    ]
    if not matching_minutes:
        return _failure("MINUTE_STALE", normalized_source)
    for row in matching_minutes:
        if minute_trade_price(row, instrument_type=contract.instrument_type) is None:
            return _failure(
                "MINUTE_TRADE_MISSING" if contract.instrument_type == "etf" else "MINUTE_PRICE_MISSING",
                normalized_source,
            )

    if not isinstance(daily_rows, Sequence) or isinstance(daily_rows, (str, bytes)) or not daily_rows:
        return _failure("DAILY_MISSING", normalized_source)
    matching_daily = [
        row for row in daily_rows
        if isinstance(row, Mapping)
        and (not normalized_as_of or not _row_date(row) or _row_date(row) == normalized_as_of)
    ]
    if not matching_daily:
        return _failure("DAILY_STALE", normalized_source)
    for row in matching_daily:
        if any(_positive_float(row.get(field)) is None for field in ("open", "high", "low", "close")):
            return _failure("DAILY_OHLC_MISSING", normalized_source)

    if not isinstance(liquidity, Mapping):
        return _failure("LIQUIDITY_UNKNOWN", normalized_source)
    liquidity_status = str(liquidity.get("status") or "").strip().lower()
    if liquidity_status in {"halted", "suspended"}:
        return _failure("HALTED", normalized_source)
    if liquidity_status in {"illiquid", "insufficient", "blocked"}:
        return _failure("ILLIQUID", normalized_source)
    if liquidity_status not in {"liquid", "ok", "sufficient", "verified"}:
        amount = _positive_float(
            liquidity.get("average_daily_amount")
            or liquidity.get("avg_daily_amount")
            or liquidity.get("amount")
        )
        if amount is None or amount <= 0:
            return _failure("LIQUIDITY_UNKNOWN", normalized_source)

    return MarketDataValidation(
        status="ready",
        reason="READY",
        source=normalized_source,
        price=realtime_price,
        details={"code": contract.code, "instrument_type": contract.instrument_type},
    )


def shares_for_budget(
    record: Mapping[str, Any] | InstrumentContract,
    *,
    price: float,
    budget: float,
) -> int:
    """Return the largest whole-lot BUY that fits budget including entry fee."""
    contract = _as_contract(record)
    price_value = _positive_float(price)
    budget_value = _positive_float(budget)
    if price_value is None or budget_value is None:
        return 0
    lot_cost = price_value * contract.lot_size * (1.0 + contract.buy_fee_rate)
    if lot_cost <= 0:
        return 0
    lots = math.floor((budget_value + 1e-9) / lot_cost)
    return max(0, lots) * contract.lot_size


def entry_fee_for(record: Mapping[str, Any] | InstrumentContract, gross_notional: float) -> float:
    contract = _as_contract(record)
    return round(max(0.0, float(gross_notional)) * contract.buy_fee_rate, 2)


def exit_fee_for(record: Mapping[str, Any] | InstrumentContract, gross_notional: float) -> float:
    contract = _as_contract(record)
    return round(max(0.0, float(gross_notional)) * contract.sell_fee_rate, 2)


def is_sellable(
    record: Mapping[str, Any] | InstrumentContract,
    *,
    entry_date: str,
    as_of: str,
) -> bool:
    """Apply explicit T+0/T+1 metadata; unknown metadata blocks the sell."""
    try:
        contract = _as_contract(record)
        entry = _normalize_date(entry_date)
        current = _normalize_date(as_of)
        if not entry or not current or current < entry:
            return False
        return contract.settlement_cycle == "T+0" or current > entry
    except InstrumentContractError:
        return False


def _as_contract(record: Mapping[str, Any] | InstrumentContract) -> InstrumentContract:
    if isinstance(record, InstrumentContract):
        return record
    contract = contract_from_record(record, strict=True)
    assert contract is not None
    return contract


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise UnknownInstrumentContract(f"{field_name} is required")
    return text


def _normalize_instrument_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {"stock": "equity", "a_share": "equity", "ashare": "equity"}
    normalized = aliases.get(text, text)
    if normalized not in VALID_INSTRUMENT_TYPES:
        raise UnknownInstrumentContract("instrument_type must be equity or etf")
    return normalized


def _normalize_lot_size(value: Any) -> int:
    if isinstance(value, bool):
        raise UnknownInstrumentContract("lot_size must be a positive integer")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UnknownInstrumentContract("lot_size must be a positive integer") from None
    if not math.isfinite(number) or number <= 0 or number != int(number):
        raise UnknownInstrumentContract("lot_size must be a positive integer")
    return int(number)


def _normalize_settlement_cycle(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    if text in {"t+0", "t0", "0", "sameday"}:
        return "T+0"
    if text in {"t+1", "t1", "1", "nextday"}:
        return "T+1"
    raise UnknownInstrumentContract("settlement_cycle must be T+0 or T+1")


def _normalize_fee(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UnknownInstrumentContract(f"{field_name} is required") from None
    if not math.isfinite(number) or number < 0:
        raise UnknownInstrumentContract(f"{field_name} must be a finite non-negative rate")
    return number


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _normalize_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        text = text[:10]
    elif len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _row_date(row: Mapping[str, Any]) -> str | None:
    return _normalize_date(row.get("tradeDate") or row.get("trade_date") or row.get("date"))


def _trading_status(row: Mapping[str, Any]) -> str:
    if row.get("isSuspended") is True or row.get("suspended") is True:
        return "halted"
    raw = row.get("status") or row.get("tradeStatus") or row.get("tradingStatus") or row.get("state")
    if isinstance(raw, bool):
        return "active" if raw else "halted"
    text = str(raw or "").strip().lower()
    if text in {"halted", "suspended", "stop", "停牌", "0", "false"}:
        return "halted"
    if text in {"active", "tradable", "trading", "normal", "1", "true", "t"}:
        return "active"
    return "unknown"


def _failure(reason: str, source: str, **details: Any) -> MarketDataValidation:
    return MarketDataValidation(
        status="blocked",
        reason=reason,
        source=source,
        details=details,
    )
