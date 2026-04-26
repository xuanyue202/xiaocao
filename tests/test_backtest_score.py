"""Tests for backtest score_trades — both 1d (BC) and multi-day (Plan B)."""
from __future__ import annotations

import pytest

from xiaocao.backtest import score_trades


def _kbd(daily: list[tuple[str, float, float, float, float]]) -> dict[str, dict]:
    """Build {date: {open, high, low, close}} from list of tuples."""
    return {d: {"open": o, "high": h, "low": low, "close": c} for d, o, h, low, c in daily}


SIGNAL_BASE = {"code": "X.XSHE", "name": "X", "mode": "test_mode"}


def test_1d_bc_buy_open_sell_next_close() -> None:
    """Default behavior unchanged: buy day-1 open, sell day-2 close."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),  # buy here at 10.0
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),  # sell here at 10.8
        ("2026-04-22", 10.9, 11.5, 10.7, 11.2),
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21", "2026-04-22"]
    trades, incomplete = score_trades(signals, trade_days, klines)
    assert incomplete == []
    assert len(trades) == 1
    # (10.8 / 10.0 - 1) * 100 = +8%
    assert trades[0]["returnPct"] == pytest.approx(8.0)
    assert trades[0]["sellDate"] == "2026-04-21"


def test_hold_to_n_3d() -> None:
    """hold_days=3 + exit_rule=hold_to_n: sell at trade_days[idx+3] close."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),
        ("2026-04-22", 10.9, 11.5, 10.7, 11.2),
        ("2026-04-23", 11.3, 12.0, 11.0, 11.6),  # sell here at 11.6
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23"]
    trades, _ = score_trades(signals, trade_days, klines, hold_days=3, exit_rule="hold_to_n")
    assert len(trades) == 1
    # (11.6 / 10.0 - 1) * 100 = +16%
    assert trades[0]["returnPct"] == pytest.approx(16.0)
    assert trades[0]["sellDate"] == "2026-04-23"
    assert trades[0]["holdDays"] == 3
    assert trades[0]["exitKind"] == "hold_to_n"


def test_max_dd_triggers_stop() -> None:
    """max_dd_pct=5%: peak rises to 11.0, low drops to 10.0 → drawdown > 5% → stop."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),     # buy here at 10.0
        ("2026-04-21", 10.3, 11.0, 10.0, 10.5),     # peak=11.0; low=10.0 → DD=9.1% > 5% → STOP
        ("2026-04-22", 10.4, 10.6, 10.0, 10.5),
        ("2026-04-23", 10.5, 10.7, 10.3, 10.5),
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23"]
    trades, _ = score_trades(signals, trade_days, klines, hold_days=3,
                             exit_rule="max_dd", max_dd_pct=5.0)
    assert len(trades) == 1
    # peak = 11.0; stop_price = 11.0 * 0.95 = 10.45
    # ret = (10.45 / 10.0 - 1) * 100 = +4.5%
    assert trades[0]["returnPct"] == pytest.approx(4.5)
    assert trades[0]["exitKind"] == "max_dd_stop"


def test_max_dd_falls_through_to_hold_to_n() -> None:
    """When DD never exceeds max_dd_pct, fall back to hold_to_n."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.2, 9.95, 10.1),
        ("2026-04-21", 10.1, 10.3, 10.05, 10.2),    # tight range, no DD
        ("2026-04-22", 10.2, 10.4, 10.15, 10.3),
        ("2026-04-23", 10.3, 10.5, 10.25, 10.4),    # sell here
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23"]
    trades, _ = score_trades(signals, trade_days, klines, hold_days=3,
                             exit_rule="max_dd", max_dd_pct=5.0)
    assert len(trades) == 1
    # ret = (10.4 / 10.0 - 1) * 100 = +4%
    assert trades[0]["returnPct"] == pytest.approx(4.0)
    assert trades[0]["exitKind"] == "hold_to_n"


def test_max_favorable_picks_best_high() -> None:
    """exit_rule=max_favorable: sell at the HIGH of the day with the max HIGH in window."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.5, 10.2, 10.8),     # max high here = 11.5
        ("2026-04-22", 10.9, 11.2, 10.7, 11.0),
        ("2026-04-23", 11.0, 11.3, 10.9, 11.2),
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23"]
    trades, _ = score_trades(signals, trade_days, klines, hold_days=3,
                             exit_rule="max_favorable")
    assert len(trades) == 1
    # ret = (11.5 / 10.0 - 1) * 100 = +15%
    assert trades[0]["returnPct"] == pytest.approx(15.0)
    assert trades[0]["sellDate"] == "2026-04-21"
    assert trades[0]["exitKind"] == "max_favorable"


def test_window_clipped_at_end_of_trade_days() -> None:
    """If hold_days extends past last trade_day, clip to available days."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),  # only 1 day after buy
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20", "2026-04-21"]
    trades, incomplete = score_trades(signals, trade_days, klines,
                                       hold_days=5, exit_rule="hold_to_n")
    assert len(trades) == 1
    # Window = [04-21]; sell at 04-21 close = 10.8
    assert trades[0]["sellDate"] == "2026-04-21"
    assert trades[0]["returnPct"] == pytest.approx(8.0)
    assert trades[0]["holdDays"] == 1


def test_multi_day_invalid_hold_days_raises() -> None:
    with pytest.raises(ValueError):
        score_trades({}, [], {}, hold_days=0)


def test_multi_day_invalid_exit_rule_raises() -> None:
    with pytest.raises(ValueError):
        score_trades({"d": [SIGNAL_BASE]}, ["d", "e"], {}, hold_days=2, exit_rule="bogus")


def test_signals_on_last_day_marked_incomplete() -> None:
    """A signal on the last trade day has no next day to sell into → incomplete."""
    klines = {"X.XSHE": _kbd([("2026-04-20", 10.0, 10.5, 9.8, 10.2)])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trade_days = ["2026-04-20"]
    trades, incomplete = score_trades(signals, trade_days, klines)
    assert trades == []
    assert "2026-04-20" in incomplete


# === Plan D — entry_rule="confirmation_935" tests ===

def _minute_recs(time_trade_pairs: list[tuple[str, float, float]]) -> list[dict]:
    """Build minute records (tradeTime, trade, pctChangeRate)."""
    return [
        {"tradeTime": t, "trade": price, "pctChangeRate": pct}
        for t, price, pct in time_trade_pairs
    ]


def test_entry_rule_confirmation_935_buys_at_935_when_still_strong() -> None:
    """When stock holds near 9:30-9:35 peak (drawdown ≤ threshold) = STILL STRONG
    → buy at 9:35 close (the empirical winning subset)."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),  # next-day close 10.8
    ])}
    # 9:30-9:35 monotonic up to 10.5 (no retrace) → drawdown = 0 → still strong
    minute_recs = _minute_recs([
        ("0930", 10.0, 0.0),
        ("0931", 10.1, 1.0),
        ("0932", 10.2, 2.0),
        ("0933", 10.3, 3.0),
        ("0934", 10.4, 4.0),
        ("0935", 10.5, 5.0),  # still at peak / strong
    ])
    intraday = {("20260420", "X.XSHE"): minute_recs}

    signals = {"2026-04-20": [SIGNAL_BASE]}
    trades, _ = score_trades(
        signals, ["2026-04-20", "2026-04-21"], klines,
        entry_rule="confirmation_935",
        intraday_minute_data=intraday,
        intraday_dd_threshold=1.5,
    )
    assert len(trades) == 1
    # Entry at 9:35 close = 10.5; sell at next-day close = 10.8 → +2.86%
    assert trades[0]["returnPct"] == pytest.approx((10.8 / 10.5 - 1) * 100, abs=0.01)
    assert trades[0]["intradayEntry"] == pytest.approx(10.5)


def test_entry_rule_confirmation_935_skips_when_retraced() -> None:
    """When stock retraces ≥ threshold from 9:30-9:35 peak → weak signal, SKIP."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),
    ])}
    # 9:30→9:32 surge to 10.5, then retrace to 10.2 → drawdown = 2.86% > 1.5%
    minute_recs = _minute_recs([
        ("0930", 10.0, 0.0),
        ("0931", 10.3, 3.0),
        ("0932", 10.5, 5.0),  # peak
        ("0933", 10.4, 4.0),
        ("0934", 10.3, 3.0),
        ("0935", 10.2, 2.0),  # retraced from peak
    ])
    intraday = {("20260420", "X.XSHE"): minute_recs}

    signals = {"2026-04-20": [SIGNAL_BASE]}
    trades, _ = score_trades(
        signals, ["2026-04-20", "2026-04-21"], klines,
        entry_rule="confirmation_935",
        intraday_minute_data=intraday,
        intraday_dd_threshold=1.5,
    )
    assert trades == []  # retraced (weak) → skip


def test_entry_rule_confirmation_935_no_minute_data_fails_safe() -> None:
    """Missing minute data + entry_rule=confirmation_935 → SKIP (don't fall back to open)."""
    klines = {"X.XSHE": _kbd([
        ("2026-04-20", 10.0, 10.5, 9.8, 10.2),
        ("2026-04-21", 10.3, 11.0, 10.0, 10.8),
    ])}
    signals = {"2026-04-20": [SIGNAL_BASE]}
    trades, _ = score_trades(
        signals, ["2026-04-20", "2026-04-21"], klines,
        entry_rule="confirmation_935",
        intraday_minute_data={},  # empty
    )
    assert trades == []


def test_entry_rule_unknown_raises() -> None:
    with pytest.raises(ValueError):
        score_trades({}, [], {}, entry_rule="bogus")
