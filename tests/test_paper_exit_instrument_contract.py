from __future__ import annotations

import json

from xiaocao.live.paper_exit import execute_simulated_sells


def _contract(*, settlement_cycle: str = "T+0") -> dict:
    return {
        "code": "510300.XSHG",
        "instrument_type": "etf",
        "lot_size": 200,
        "settlement_cycle": settlement_cycle,
        "buy_fee_rate": 0.001,
        "sell_fee_rate": 0.002,
        "provenance": {
            "source": "xiaocao_api",
            "endpoint": "/stock/etf_info",
            "trade_date": "2026-08-14",
        },
        "market_data_contract": {
            "realtime": "verified",
            "minute": "verified",
            "daily": "verified",
            "fill": "verified",
        },
    }


def _run(
    tmp_path,
    *,
    settlement_cycle: str = "T+0",
    shares: int = 200,
    detail: dict | None = None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    positions = tmp_path / "positions.jsonl"
    account = tmp_path / "paper_account_T.json"
    trades = tmp_path / "paper_trades.jsonl"
    alerts = tmp_path / "alerts.jsonl"
    row = {
        "book": "T",
        "status": "open",
        "code": "510300.XSHG",
        "name": "沪深300ETF",
        "entry_date": "2026-08-14",
        "entry_price": 3.0,
        "shares": shares,
        "entry_cash_out": 600.60,
        "instrument_type": "etf",
        "instrument_contract": _contract(settlement_cycle=settlement_cycle),
    }
    positions.write_text(json.dumps(row) + "\n", encoding="utf-8")
    account.write_text(json.dumps({
        "initial_capital": 30000.0,
        "cash": 29399.40,
        "realized_pnl": 0.0,
        "total_fees": 0.60,
        "fee_rate": 0.0001,
    }), encoding="utf-8")
    alert = {
        "book": "T",
        "code": "510300.XSHG",
        "entry_date": "2026-08-14",
        "latest_price": 3.2,
        "sell_reason": "TREND_TRAIL_STOP",
    }
    current_detail = detail if detail is not None else {
        "code": "510300.XSHG",
        "_source": "xiaocao_api",
        "trade": 3.1,
        "tradeDate": "20260814",
        "status": "active",
        "liquidity_status": "liquid",
    }
    return execute_simulated_sells(
        [alert],
        book="T",
        live_dir=tmp_path,
        positions_path=positions,
        account_path=account,
        trades_path=trades,
        alerts_path=alerts,
        initial_capital=30000.0,
        default_fee_rate=0.0001,
        trade_date="2026-08-14",
        detail_provider=lambda _code: current_detail,
        timestamp_provider=lambda _alert: "2026-08-14T10:00:00",
    ), positions, account, trades, alerts


def test_etf_sell_uses_metadata_fee_and_lot(tmp_path) -> None:
    result, positions, account, trades, _alerts = _run(tmp_path)

    assert result == (1, 0)
    closed = json.loads(positions.read_text(encoding="utf-8"))
    assert closed["status"] == "closed"
    assert closed["exit_fee"] == 1.24
    assert closed["lot_size"] == 200
    account_row = json.loads(account.read_text(encoding="utf-8"))
    assert account_row["cash"] == 30018.16
    trade = json.loads(trades.read_text(encoding="utf-8"))
    assert trade["fee"] == 1.24


def test_etf_t1_sell_is_blocked_on_entry_day(tmp_path) -> None:
    result, positions, _account, _trades, alerts = _run(tmp_path, settlement_cycle="T+1")

    assert result == (0, 1)
    assert json.loads(positions.read_text(encoding="utf-8"))["status"] == "open"
    alert_row = json.loads(alerts.read_text(encoding="utf-8"))
    assert alert_row["reason"] == "T1_BLOCKED"


def test_etf_partial_lot_is_blocked(tmp_path) -> None:
    result, positions, _account, _trades, alerts = _run(tmp_path, shares=100)

    assert result == (0, 1)
    assert json.loads(positions.read_text(encoding="utf-8"))["status"] == "open"
    assert json.loads(alerts.read_text(encoding="utf-8"))["reason"] == "LOT_SIZE_INVALID"


def test_etf_sell_requires_current_status_liquidity_and_source(tmp_path) -> None:
    result, positions, _account, _trades, alerts = _run(
        tmp_path,
        detail={
            "code": "510300.XSHG",
            "_source": "xiaocao_api",
            "trade": 3.1,
            "tradeDate": "20260814",
            "status": "active",
        },
    )

    assert result == (0, 1)
    assert json.loads(positions.read_text(encoding="utf-8"))["status"] == "open"
    assert json.loads(alerts.read_text(encoding="utf-8"))["reason"] == "LIQUIDITY_UNKNOWN"
