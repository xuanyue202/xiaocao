from __future__ import annotations

import json

from kronos_screen.scripts import settle_book_t as sbt


def test_book_t_existing_bank_position_waits_for_paired_morning_switch() -> None:
    row = {
        "book": "T",
        "code": "601288.XSHG",
        "name": "农业银行",
        "category_name": "业绩股权类",
        "fee_rate": 0.0001,
    }

    alignment = sbt._trend_alignment_for_position(row)
    sbt._mark_trend_switch_context(row, fee_rate=0.0001, alignment=alignment)

    assert row["trend_alignment"] == "external"
    assert "银行" in row["trend_alignment_reason"]
    assert row["trend_switch_policy"] == "hold_exposure; paired_morning_switch_when_replacement_ready"
    assert row["trend_switch_est_roundtrip_fee_bps"] == 2.0

    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=0,
        rebalance_days=60,
        alignment=alignment,
    ) is None
    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) is None


def test_book_t_aligned_position_keeps_exposure_until_paired_rebalance_or_trail() -> None:
    alignment = {
        "trend_alignment": "aligned",
        "trend_alignment_reason": "matched posture keyword: 半导体",
    }

    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) is None
    assert sbt._trend_exit_reason(
        dd_pct=1.0,
        trail_dd=12.0,
        hold_days=60,
        rebalance_days=60,
        alignment=alignment,
    ) is None
    assert sbt._trend_exit_reason(
        dd_pct=12.0,
        trail_dd=12.0,
        hold_days=1,
        rebalance_days=60,
        alignment=alignment,
    ) == "TREND_DAILY_TRAIL_STOP"


def test_blocked_sell_key_prevents_same_day_book_t_settlement(tmp_path) -> None:
    alerts = tmp_path / "alerts.jsonl"
    alerts.write_text(
        json.dumps({
            "ts": "2026-07-13T15:14:10",
            "alert": "SELL_BLOCKED",
            "book": "T",
            "reason": "LIMIT_DOWN_NO_BID",
            "code": "000725.XSHE",
            "entry_date": "2026-07-07",
        }) + "\n",
        encoding="utf-8",
    )

    blocked = sbt._load_blocked_sell_keys(alerts)

    assert ("T", "2026-07-13", "000725.XSHE", "2026-07-07") in blocked
    assert sbt._settlement_block_reason(
        blocked,
        book="T",
        exit_date="2026-07-13",
        code="000725.XSHE",
        entry_date="2026-07-07",
    ) == "LIMIT_DOWN_NO_BID"
    assert sbt._settlement_block_reason(
        blocked,
        book="T",
        exit_date="2026-07-14",
        code="000725.XSHE",
        entry_date="2026-07-07",
    ) is None


def test_sell_block_key_is_book_scoped(tmp_path) -> None:
    alerts = tmp_path / "alerts.jsonl"
    alerts.write_text(json.dumps({
        "ts": "2026-07-13T15:14:10", "alert": "SELL_BLOCKED", "book": "T",
        "reason": "LIMIT_DOWN_NO_BID", "code": "SAME", "entry_date": "2026-07-07",
    }) + "\n", encoding="utf-8")
    blocked = sbt._load_blocked_sell_keys(alerts)

    assert sbt._settlement_block_reason(
        blocked, book="B", exit_date="2026-07-13", code="SAME", entry_date="2026-07-07",
    ) is None


def test_book_t_close_uses_explicit_instrument_fee_and_lot() -> None:
    position = {
        "book": "T",
        "code": "510300.XSHG",
        "entry_date": "2026-08-14",
        "entry_price": 3.0,
        "shares": 200,
        "entry_cash_out": 600.60,
        "instrument_contract": {
            "code": "510300.XSHG",
            "instrument_type": "etf",
            "lot_size": 200,
            "settlement_cycle": "T+0",
            "buy_fee_rate": 0.001,
            "sell_fee_rate": 0.002,
        },
    }
    account = {"cash": 0.0, "realized_pnl": 0.0, "total_fees": 0.0}

    trade = sbt._close_position(
        position,
        exit_date="2026-08-14",
        exit_price=3.1,
        exit_reason="TREND_DAILY_TRAIL_STOP",
        peak_price=3.2,
        dd_pct=3.125,
        hold_days=0,
        account=account,
    )

    assert trade is not None
    assert trade["fee"] == 1.24
    assert trade["lot_size"] == 200
    assert account["cash"] == 618.76
