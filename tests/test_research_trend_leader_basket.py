from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import research_trend_leader_basket as trend_basket  # noqa: E402


def test_minute_bar_uses_trade_price_axis() -> None:
    rows = [
        {"tradeMinutes": 2, "trade": 12.0, "close": None},
        {"tradeMinutes": 0, "trade": 10.0, "close": None},
        {"tradeMinutes": 1, "trade": 11.0, "close": None},
    ]
    assert trend_basket.minute_bar(rows) == {
        "open": 10.0,
        "close": 12.0,
        "high": 12.0,
        "low": 10.0,
        "bars": 3,
    }


def test_parse_basket_accepts_name_and_theme() -> None:
    parsed = trend_basket.parse_basket("600487.XSHG:亨通光电/CPO,002463.XSHE:沪电股份/PCB")
    assert parsed == [
        {"code": "600487.XSHG", "name": "亨通光电", "theme": "CPO"},
        {"code": "002463.XSHE", "name": "沪电股份", "theme": "PCB"},
    ]
