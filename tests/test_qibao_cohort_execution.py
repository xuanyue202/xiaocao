from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from research_qibao_cohort_execution import _minute_fill_return  # noqa: E402


def _bars(day: str, prices: list[tuple[str, float]]) -> list[dict]:
    return [
        {
            "tradeDate": day.replace("-", ""),
            "tradeTime": t,
            "trade": px,
            "amt": px * 100,
            "vol": 100,
        }
        for t, px in prices
    ]


def test_minute_fill_return_uses_limit_touch_window_vwap() -> None:
    ret, meta = _minute_fill_return(
        "300001.XSHE",
        "2026-06-01",
        "2026-06-02",
        {
            "300001.XSHE": {
                "2026-06-01": _bars("2026-06-01", [("0930", 10.0), ("0931", 10.2)]),
                "2026-06-02": _bars("2026-06-02", [("1459", 11.0), ("1500", 11.1)]),
            }
        },
        open_reference=10.0,
        open_reference_basis="test_open",
        start_hhmm="0930",
        end_hhmm="0931",
        limit_premium_pct=0.5,
    )

    assert ret is not None
    assert abs(ret - 10.447761194) < 1e-6
    assert abs(meta["entry_price"] - 10.05) < 1e-9
    assert meta["exit_price"] == 11.1
    assert meta["reason"] == "filled"


def test_minute_fill_return_skips_when_limit_not_touched() -> None:
    ret, meta = _minute_fill_return(
        "300001.XSHE",
        "2026-06-01",
        "2026-06-02",
        {
            "300001.XSHE": {
                "2026-06-01": _bars("2026-06-01", [("0930", 10.2), ("0931", 10.3)]),
                "2026-06-02": _bars("2026-06-02", [("1500", 11.1)]),
            }
        },
        open_reference=10.0,
        open_reference_basis="test_open",
        start_hhmm="0930",
        end_hhmm="0931",
        limit_premium_pct=0.5,
    )

    assert ret is None
    assert meta["reason"] == "limit_not_touched"
    assert abs(meta["fill_limit_price"] - 10.05) < 1e-9


def test_minute_fill_return_requires_sell_minute() -> None:
    ret, meta = _minute_fill_return(
        "300001.XSHE",
        "2026-06-01",
        "2026-06-02",
        {"300001.XSHE": {"2026-06-01": _bars("2026-06-01", [("0930", 10.0), ("0931", 10.0)])}},
        open_reference=10.0,
        open_reference_basis="test_open",
        start_hhmm="0930",
        end_hhmm="0931",
        limit_premium_pct=0.5,
    )

    assert ret is None
    assert meta["reason"] == "missing_sell_minute"
    assert meta["entry_price"] == 10.0
