from __future__ import annotations

from kronos_screen.scripts.paper_record import (
    _attach_fill_prices,
    _fill_price,
    _fill_price_from_window,
    _fill_window_high,
    _validate_fill_window,
)


class FakeClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def minute_line(self, code: str, freq: str, adj: str, *, trade_date: str, count: int):
        return self.rows


def test_fill_uses_opening_window_high_when_basket_not_reached() -> None:
    price, basis, basket_rule, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window_high=10.28,
        window_time="0931",
    )

    assert price == 10.28
    assert basis == "opening_window_capped_by_basket"
    assert basket_rule == "entry+2.1%"
    assert meta["fill_window_high"] == 10.28


def test_fill_caps_at_basket_when_opening_window_trades_through_limit() -> None:
    price, basis, basket_rule, meta = _fill_price_from_window(
        {"basket_price": 10.391, "basket_rule": "entry+2.1%", "open": 10.18},
        window_high=10.5,
        window_time="0931",
    )

    assert price == 10.391
    assert basis == "opening_window_capped_by_basket"
    assert basket_rule == "entry+2.1%"
    assert meta["fill_window_high"] == 10.5


def test_fill_window_high_uses_only_configured_opening_minutes() -> None:
    client = FakeClient([
        {"tradeTime": "0929", "high": 11.0, "trade": 11.0},
        {"tradeTime": "0930", "high": 10.2, "trade": 10.1},
        {"tradeTime": "0931", "trade": 10.28},
        {"tradeTime": "0932", "high": 10.9, "trade": 10.9},
    ])

    high, trade_time = _fill_window_high(
        client,
        "000670.XSHE",
        "2026-06-10",
        start_hhmm="0930",
        end_hhmm="0931",
    )

    assert high == 10.28
    assert trade_time == "0931"


def test_attach_fill_prices_makes_fill_price_use_precomputed_window() -> None:
    client = FakeClient([
        {"tradeTime": "0930", "high": 5.08, "trade": 5.08},
        {"tradeTime": "0931", "high": 5.11, "trade": 5.09},
    ])

    [record] = _attach_fill_prices(
        client,
        [{"code": "002613.XSHE", "basket_price": 5.212, "basket_rule": "entry+2.0%", "open": 5.11}],
        "2026-06-10",
        start_hhmm="0930",
        end_hhmm="0931",
    )

    price, basis, basket_rule = _fill_price(record)
    assert price == 5.11
    assert basis == "opening_window_capped_by_basket"
    assert basket_rule == "entry+2.0%"


def test_validate_fill_window_rejects_reversed_window() -> None:
    try:
        _validate_fill_window("0931", "0930")
    except ValueError as exc:
        assert "fill-window-end" in str(exc)
    else:
        raise AssertionError("expected reversed fill window to fail")
