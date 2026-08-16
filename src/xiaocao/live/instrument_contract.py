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
PROPRIETARY_SOURCES = frozenset(
    {"xiaocao_api", "xiaocao", "proprietary_api", "p-xcapi", "p-xcapi.kjap1.cn"}
)


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

        fees = raw.get("fees") or raw.get("fee_contract") or raw.get("transaction_cost") or {}
        if not isinstance(fees, Mapping):
            raise UnknownInstrumentContract("fees must be an object")
        shared_fee = raw.get("fee_rate")
        if shared_fee in (None, ""):
            shared_fee = _first_present(fees, ("fee_rate", "rate", "commission"))
        buy_fee = raw.get("buy_fee_rate")
        if buy_fee in (None, ""):
            buy_fee = _first_present(fees, ("buy_fee_rate", "buy"), default=shared_fee)
        sell_fee = raw.get("sell_fee_rate")
        if sell_fee in (None, ""):
            sell_fee = _first_present(fees, ("sell_fee_rate", "sell"), default=shared_fee)
        buy_fee_rate = _normalize_fee(
            _fee_rate_value(buy_fee), "buy_fee_rate"
        )
        sell_fee_rate = _normalize_fee(
            _fee_rate_value(sell_fee), "sell_fee_rate"
        )

        market_data_contract = (
            raw.get("market_data_contract")
            or raw.get("quote_contract")
            or {}
        )
        if not isinstance(market_data_contract, Mapping):
            raise UnknownInstrumentContract("market_data_contract must be an object")
        provenance_copy = _normalize_provenance(
            raw.get("provenance") or raw.get("source_metadata"),
            market_data_contract,
        )
        catalog_trade_date = _normalize_date(
            provenance_copy.get("trade_date")
            or raw.get("catalog_trade_date")
            or raw.get("tradeDate")
        )

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


def contract_record_fields(
    contract: InstrumentContract,
    *,
    include_market_data: bool = False,
    include_provenance: bool = False,
) -> dict[str, Any]:
    """Return the durable row fields shared by paper writers and receipts."""
    fields: dict[str, Any] = {
        "instrument_type": contract.instrument_type,
        "lot_size": contract.lot_size,
        "settlement_cycle": contract.settlement_cycle,
        "buy_fee_rate": contract.buy_fee_rate,
        "sell_fee_rate": contract.sell_fee_rate,
        "instrument_contract": contract.to_dict(),
    }
    if include_market_data:
        fields["market_data_contract"] = dict(contract.market_data_contract)
    if include_provenance:
        fields["instrument_provenance"] = dict(contract.provenance)
    return fields


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
    required: Sequence[str] = ("realtime", "minute", "daily", "fill"),
) -> bool:
    """Whether the named proprietary quote contracts were explicitly verified."""
    return all(
        _market_component_verified(contract.market_data_contract, name)
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

    provenance_source = str(contract.provenance.get("source") or "").strip().lower()
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

    for field_name in ("realtime", "minute", "daily", "fill"):
        if not _market_component_verified(contract.market_data_contract, field_name):
            return _failure("MARKET_CONTRACT_UNVERIFIED", normalized_source, field=field_name)

    if not isinstance(realtime, Mapping):
        return _failure("REALTIME_MISSING", normalized_source)
    realtime_code = _row_code(realtime)
    if realtime_code and not _same_instrument(realtime_code, contract.code):
        return _failure("MARKET_DATA_CODE_MISMATCH", normalized_source, code=realtime_code)
    realtime_status = _trading_status(realtime)
    if realtime_status == "halted":
        return _failure("HALTED", normalized_source)
    if realtime_status != "active":
        return _failure("REALTIME_STATUS_UNKNOWN", normalized_source)
    realtime_price = _positive_float(realtime.get("trade"))
    if realtime_price is None:
        return _failure("REALTIME_TRADE_MISSING", normalized_source)
    realtime_date = _row_date(realtime)
    if normalized_as_of:
        if not realtime_date:
            return _failure("REALTIME_DATE_MISSING", normalized_source)
        if realtime_date != normalized_as_of:
            return _failure("REALTIME_STALE", normalized_source, trade_date=realtime_date)

    if not isinstance(minute_rows, Sequence) or isinstance(minute_rows, (str, bytes)) or not minute_rows:
        return _failure("MINUTE_MISSING", normalized_source)
    matching_minutes: list[Mapping[str, Any]] = []
    for row in minute_rows:
        if not isinstance(row, Mapping):
            continue
        row_date = _row_date(row)
        if normalized_as_of and not row_date:
            return _failure("MINUTE_DATE_MISSING", normalized_source)
        if normalized_as_of and row_date != normalized_as_of:
            continue
        matching_minutes.append(row)
    if not matching_minutes:
        return _failure("MINUTE_STALE", normalized_source)
    for row in matching_minutes:
        row_code = _row_code(row)
        if row_code and not _same_instrument(row_code, contract.code):
            return _failure("MARKET_DATA_CODE_MISMATCH", normalized_source, code=row_code)
        if minute_trade_price(row, instrument_type=contract.instrument_type) is None:
            return _failure(
                "MINUTE_TRADE_MISSING" if contract.instrument_type == "etf" else "MINUTE_PRICE_MISSING",
                normalized_source,
            )

    if not isinstance(daily_rows, Sequence) or isinstance(daily_rows, (str, bytes)) or not daily_rows:
        return _failure("DAILY_MISSING", normalized_source)
    matching_daily: list[Mapping[str, Any]] = []
    for row in daily_rows:
        if not isinstance(row, Mapping):
            continue
        row_date = _row_date(row)
        if normalized_as_of and not row_date:
            return _failure("DAILY_DATE_MISSING", normalized_source)
        if normalized_as_of and row_date != normalized_as_of:
            continue
        matching_daily.append(row)
    if not matching_daily:
        return _failure("DAILY_STALE", normalized_source)
    for row in matching_daily:
        row_code = _row_code(row)
        if row_code and not _same_instrument(row_code, contract.code):
            return _failure("MARKET_DATA_CODE_MISMATCH", normalized_source, code=row_code)
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
        return _failure("LIQUIDITY_UNKNOWN", normalized_source)

    return MarketDataValidation(
        status="ready",
        reason="READY",
        source=normalized_source,
        price=realtime_price,
        details={"code": contract.code, "instrument_type": contract.instrument_type},
    )


def validate_sell_market_data(
    record: Mapping[str, Any],
    detail: Mapping[str, Any] | None,
    *,
    as_of: str,
    source: str | None = None,
) -> MarketDataValidation:
    """Validate the current proprietary facts used by an explicit SELL.

    The full fill/settlement validator requires historical minute and daily
    rows.  A live SELL already has a current quote detail, so this seam checks
    the facts that must be fresh at the point of the side effect: proprietary
    source, current date, active trading state, a trade price, and explicit
    liquidity state.  Missing state is deliberately not inferred from order
    book amounts.
    """
    if not isinstance(detail, Mapping):
        return _failure("REALTIME_MISSING", str(source or "unknown"))
    source_value = str(
        source
        or detail.get("_source")
        or detail.get("source")
        or _nested_source(detail.get("provenance"))
        or _nested_source(detail.get("market_data_facts"))
        or ""
    ).strip().lower()
    if source_value not in PROPRIETARY_SOURCES:
        return _failure("PUBLIC_SOURCE_FORBIDDEN", source_value or "unknown")
    try:
        contract = contract_from_record(record, strict=True)
    except InstrumentContractError as exc:
        return _failure("INSTRUMENT_CONTRACT_UNVERIFIED", source_value, error=str(exc))
    assert contract is not None
    if not market_contract_verified(contract):
        return _failure("MARKET_CONTRACT_UNVERIFIED", source_value)

    normalized_as_of = _normalize_date(as_of)
    detail_date = _row_date(detail)
    if normalized_as_of:
        if not detail_date:
            return _failure("REALTIME_DATE_MISSING", source_value)
        if detail_date != normalized_as_of:
            return _failure("REALTIME_STALE", source_value, trade_date=detail_date)
    status = _trading_status(detail)
    if status == "halted":
        return _failure("HALTED", source_value)
    if status != "active":
        return _failure("REALTIME_STATUS_UNKNOWN", source_value)
    price = _positive_float(detail.get("trade"))
    if price is None:
        return _failure("REALTIME_TRADE_MISSING", source_value)
    liquidity_status = _liquidity_status(detail)
    if liquidity_status in {"halted", "suspended"}:
        return _failure("HALTED", source_value)
    if liquidity_status in {"illiquid", "insufficient", "blocked"}:
        return _failure("ILLIQUID", source_value)
    if liquidity_status not in {"liquid", "ok", "sufficient", "verified"}:
        return _failure("LIQUIDITY_UNKNOWN", source_value)
    return MarketDataValidation(
        status="ready",
        reason="READY",
        source=source_value,
        price=price,
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


def _fee_rate_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("fee_rate", "rate", "commission"):
            nested = value.get(key)
            if nested not in (None, ""):
                return nested
        return None
    return value


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str], *, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return default


def _normalize_provenance(
    raw: Any,
    market_data_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize catalog/mapping provenance without losing resolver edges."""
    if isinstance(raw, Mapping):
        normalized: dict[str, Any] = {str(key): value for key, value in raw.items()}
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        normalized = {"mapping_evidence": [dict(item) if isinstance(item, Mapping) else item for item in raw]}
    elif raw not in (None, ""):
        normalized = {"source": str(raw).strip()}
    else:
        normalized = {}

    market_source = str(market_data_contract.get("source") or "").strip()
    current_source = str(normalized.get("source") or "").strip()
    if market_source and current_source.lower() not in PROPRIETARY_SOURCES:
        if current_source:
            normalized["catalog_source"] = current_source
        normalized["source"] = market_source
        market_version = market_data_contract.get("version") or market_data_contract.get("source_version")
        if market_version and not normalized.get("source_version"):
            normalized["source_version"] = market_version
    return normalized


def _market_component_verified(
    market_data_contract: Mapping[str, Any],
    name: str,
) -> bool:
    value = market_data_contract.get(name)
    if value is None and name == "daily":
        value = market_data_contract.get("settlement_data") or market_data_contract.get("settlement")
    if value is None and name == "fill":
        value = market_data_contract.get("fill_semantics")
    if isinstance(value, Mapping):
        state = str(value.get("status") or "").strip().lower()
        verified = value.get("verified") is True
        if state not in VERIFIED_MARKET_CONTRACT_STATES and not verified:
            return False
        if name == "minute":
            price_field = str(value.get("price_field") or value.get("trade_field") or "").strip().lower()
            if price_field and price_field != "trade":
                return False
        return True
    return str(value or "").strip().lower() in VERIFIED_MARKET_CONTRACT_STATES


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


def _row_code(row: Mapping[str, Any]) -> str:
    return str(
        row.get("code")
        or row.get("stockId")
        or row.get("stockCode")
        or row.get("fundCode")
        or ""
    ).strip().upper()


def _same_instrument(actual: str, expected: str) -> bool:
    actual_base = actual.split(".", 1)[0]
    expected_base = expected.upper().split(".", 1)[0]
    return actual == expected.upper() or actual_base == expected_base


def _nested_source(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("source") or value.get("_source") or "")
    return ""


def _liquidity_status(row: Mapping[str, Any]) -> str:
    raw = row.get("liquidity_status") or row.get("liquidityStatus") or row.get("liquidity")
    if isinstance(raw, Mapping):
        raw = raw.get("status")
    return str(raw or "").strip().lower()


def _trading_status(row: Mapping[str, Any]) -> str:
    if row.get("isSuspended") is True or row.get("suspended") is True:
        return "halted"
    raw = (
        row.get("status")
        or row.get("tradeStatus")
        or row.get("tradingStatus")
        or row.get("state")
        or row.get("statusType")
    )
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
