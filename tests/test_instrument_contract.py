from __future__ import annotations

from datetime import date

import pytest

from xiaocao.live.instrument_contract import (
    InstrumentContract,
    InstrumentContractError,
    entry_fee_for,
    exit_fee_for,
    is_sellable,
    market_contract_verified,
    shares_for_budget,
    validate_market_data,
)


def _etf_record(**overrides):
    record = {
        "code": "510300.XSHG",
        "name": "沪深300ETF",
        "instrument_type": "etf",
        "lot_size": 100,
        "settlement_cycle": "T+1",
        "buy_fee_rate": 0.0001,
        "sell_fee_rate": 0.0001,
        "market_data_contract": {
            "realtime": "verified",
            "minute": "verified",
            "daily": "verified",
            "fill": "verified",
        },
        "provenance": {
            "source": "xiaocao_api",
            "endpoint": "/stock/etf_info",
            "trade_date": "2026-08-14",
        },
    }
    record.update(overrides)
    return record


_MISSING = object()


def _market_inputs(*, realtime=_MISSING, minute_rows=_MISSING, daily_rows=_MISSING, liquidity=_MISSING):
    return {
        "realtime": realtime
        if realtime is not _MISSING
        else {"trade": 3.10, "tradeDate": "20260814", "status": "active"},
        "minute_rows": minute_rows
        if minute_rows is not _MISSING
        else [{"trade": 3.10, "close": 99.0, "tradeDate": "20260814"}],
        "daily_rows": daily_rows
        if daily_rows is not _MISSING
        else [{
            "tradeDate": "20260814",
            "open": 3.00,
            "high": 3.20,
            "low": 2.95,
            "close": 3.10,
        }],
        "liquidity": liquidity if liquidity is not _MISSING else {"status": "liquid"},
    }


def test_etf_contract_requires_explicit_execution_metadata() -> None:
    contract = InstrumentContract.from_mapping(_etf_record())

    assert contract.code == "510300.XSHG"
    assert contract.instrument_type == "etf"
    assert contract.lot_size == 100
    assert contract.settlement_cycle == "T+1"
    assert contract.buy_fee_rate == 0.0001
    assert contract.sell_fee_rate == 0.0001


def test_resolver_shape_accepts_nested_quote_contract_and_edge_provenance() -> None:
    row = {
        "code": "159001.XSHE",
        "instrument_type": "etf",
        "lot_size": 100,
        "settlement_cycle": "T+1",
        "fees": {"buy": {"rate": 0.0002}, "sell": {"rate": 0.0003}},
        "catalog_trade_date": "2026-08-14",
        "provenance": [{
            "edge_type": "theme_to_etf",
            "source": "theme_registry",
            "source_version": "theme-v1",
            "source_id": "theme:ai",
            "evidence_id": "edge-1",
        }],
        "market_data_contract": {
            "status": "verified",
            "source": "p-xcapi",
            "version": "quote-v1",
            "realtime": {"status": "verified"},
            "minute": {"status": "verified", "price_field": "trade"},
            "daily": {"status": "verified"},
            "fill": {"status": "verified"},
        },
    }

    contract = InstrumentContract.from_mapping(row)

    assert contract.buy_fee_rate == 0.0002
    assert contract.sell_fee_rate == 0.0003
    assert contract.provenance["source"] == "p-xcapi"
    assert contract.provenance["mapping_evidence"][0]["edge_type"] == "theme_to_etf"
    assert market_contract_verified(contract) is True


@pytest.mark.parametrize(
    "field, value",
    [
        ("lot_size", None),
        ("settlement_cycle", "unknown"),
        ("buy_fee_rate", None),
    ],
)
def test_unknown_etf_contract_values_fail_closed(field: str, value) -> None:
    row = _etf_record(**{field: value})

    with pytest.raises(InstrumentContractError, match=field):
        InstrumentContract.from_mapping(row)


def test_market_contract_uses_trade_for_etf_minutes_and_rejects_close_only() -> None:
    result = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        **_market_inputs(),
    )

    assert result.ok is True
    assert result.price == 3.10
    assert result.source == "xiaocao_api"

    missing_trade = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        **_market_inputs(minute_rows=[{
            "tradeDate": "20260814",
            "close": 3.10,
        }]),
    )

    assert missing_trade.ok is False
    assert missing_trade.reason == "MINUTE_TRADE_MISSING"


@pytest.mark.parametrize(
    "inputs, reason",
    [
        ({"realtime": None}, "REALTIME_MISSING"),
        ({"realtime": {"trade": 3.1, "tradeDate": "20260814", "status": "halted"}}, "HALTED"),
        ({"liquidity": {"status": "illiquid"}}, "ILLIQUID"),
        ({"minute_rows": []}, "MINUTE_MISSING"),
    ],
)
def test_market_contract_fail_closed_for_unavailable_execution_facts(inputs, reason: str) -> None:
    result = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        **_market_inputs(**inputs),
    )

    assert result.ok is False
    assert result.reason == reason


def test_market_contract_rejects_stale_catalog_and_public_source() -> None:
    stale = validate_market_data(
        _etf_record(
            provenance={
                "source": "xiaocao_api",
                "endpoint": "/stock/etf_info",
                "trade_date": "2026-08-10",
            }
        ),
        as_of="2026-08-14",
        max_catalog_age_days=1,
        **_market_inputs(),
    )
    assert stale.ok is False
    assert stale.reason == "CATALOG_STALE"

    public = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        source="public",
        **_market_inputs(),
    )
    assert public.ok is False
    assert public.reason == "PUBLIC_SOURCE_FORBIDDEN"


def test_market_contract_requires_explicit_liquidity_and_dated_rows() -> None:
    unknown_liquidity = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        **_market_inputs(liquidity={"average_daily_amount": 10_000_000}),
    )
    assert unknown_liquidity.reason == "LIQUIDITY_UNKNOWN"

    undated_minutes = validate_market_data(
        _etf_record(),
        as_of="2026-08-14",
        **_market_inputs(minute_rows=[{"trade": 3.1}]),
    )
    assert undated_minutes.reason == "MINUTE_DATE_MISSING"


def test_lot_fee_and_sellability_use_contract_metadata() -> None:
    row = _etf_record(lot_size=200, settlement_cycle="T+0", buy_fee_rate=0.001, sell_fee_rate=0.002)

    assert shares_for_budget(row, price=3.0, budget=1250.0) == 400
    assert entry_fee_for(row, 1200.0) == 1.2
    assert exit_fee_for(row, 1200.0) == 2.4
    assert is_sellable(row, entry_date="2026-08-14", as_of="2026-08-14") is True

    t1 = _etf_record(settlement_cycle="T+1")
    assert is_sellable(t1, entry_date="2026-08-14", as_of="2026-08-14") is False
    assert is_sellable(t1, entry_date="2026-08-14", as_of="2026-08-15") is True
    assert is_sellable({"instrument_type": "etf"}, entry_date="2026-08-14", as_of="2026-08-14") is False


def test_catalog_dates_accept_iso_and_compact_forms() -> None:
    contract = InstrumentContract.from_mapping(
        _etf_record(
            provenance={
                "source": "xiaocao_api",
                "endpoint": "/stock/etf_info",
                "trade_date": "20260814",
            }
        )
    )

    assert contract.catalog_trade_date == date(2026, 8, 14).isoformat()
