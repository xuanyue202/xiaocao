from __future__ import annotations

import json

from scripts import repair_blocked_book_t as repair


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_repair_reverses_blocked_sell_and_causal_rebuy(tmp_path) -> None:
    positions = tmp_path / "positions.jsonl"
    trades = tmp_path / "paper_trades.jsonl"
    account = tmp_path / "paper_account_T.json"
    alerts = tmp_path / "alerts.jsonl"
    audit = tmp_path / "ledger_repairs.jsonl"
    _write_jsonl(positions, [
        {
            "book": "T", "code": "000725.XSHE", "entry_date": "2026-07-07",
            "shares": 1200, "entry_cash_out": 9158.25, "status": "closed",
            "exit_date": "2026-07-13", "exit_fee": 0.82, "exit_cash_in": 8195.18,
            "realized_pnl": -963.07, "exit_reason": "TREND_DAILY_TRAIL_STOP",
            "trend_exit_peak": 8.28, "trend_exit_dd_pct": 17.5, "trend_hold_days": 4,
        },
        {
            "book": "T", "code": "000725.XSHE", "entry_date": "2026-07-14",
            "shares": 1200, "entry_cash_out": 8266.84, "entry_fee": 0.83,
            "status": "open", "source": "auto:trend_book",
        },
        {"book": "T", "code": "OTHER", "entry_date": "2026-07-02", "status": "open"},
    ])
    _write_jsonl(trades, [
        {"book": "T", "side": "BUY", "code": "000725.XSHE", "date": "2026-07-07"},
        {
            "book": "T", "side": "SELL", "code": "000725.XSHE", "date": "2026-07-13",
            "shares": 1200, "fee": 0.82, "realized_pnl": -963.07,
        },
        {
            "book": "T", "side": "BUY", "code": "000725.XSHE", "date": "2026-07-14",
            "shares": 1200, "fee": 0.83,
        },
    ])
    account.write_text(json.dumps({
        "cash": 546.16, "realized_pnl": -1760.86, "total_fees": 8.34,
        "last_buy_date": "2026-07-14", "last_sell_date": "2026-07-13",
    }), encoding="utf-8")
    _write_jsonl(alerts, [{
        "ts": "2026-07-13T15:14:10", "alert": "SELL_BLOCKED", "book": "T",
        "reason": "LIMIT_DOWN_NO_BID", "code": "000725.XSHE", "entry_date": "2026-07-07",
    }])

    result = repair.repair_blocked_roundtrip(
        positions_path=positions,
        trades_path=trades,
        account_path=account,
        alerts_path=alerts,
        audit_path=audit,
        code="000725.XSHE",
        entry_date="2026-07-07",
        blocked_date="2026-07-13",
        replacement_entry_date="2026-07-14",
        apply=True,
    )

    repaired_positions = _read_jsonl(positions)
    restored = next(p for p in repaired_positions if p.get("code") == "000725.XSHE")
    assert restored["entry_date"] == "2026-07-07" and restored["status"] == "open"
    assert "exit_date" not in restored and restored["trend_exit_blocked_reason"] == "LIMIT_DOWN_NO_BID"
    assert not any(p.get("entry_date") == "2026-07-14" for p in repaired_positions)
    assert [(t["side"], t["date"]) for t in _read_jsonl(trades)] == [("BUY", "2026-07-07")]
    repaired_account = json.loads(account.read_text(encoding="utf-8"))
    assert repaired_account["cash"] == 617.82
    assert repaired_account["realized_pnl"] == -797.79
    assert repaired_account["total_fees"] == 6.69
    assert repaired_account["last_buy_date"] == "2026-07-07"
    assert repaired_account["last_sell_date"] is None
    assert result["applied"] is True and audit.exists()
