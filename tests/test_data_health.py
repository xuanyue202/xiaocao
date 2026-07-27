"""Tests for the data-health doctor (src/xiaocao/live/data_health.py)."""
from __future__ import annotations

import json

from xiaocao.live import data_health


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_duplicate_snapshots_detected(tmp_path):
    # The 06-01 bug: same (date,code,is_live,book) captured more than once.
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t1"},
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t2"},
        {"date": "2026-06-01", "code": "B", "is_live": True, "captured_at": "t1"},
    ])
    findings = data_health.duplicate_snapshots(tmp_path)
    assert findings and findings[0]["severity"] == "critical"


def test_clean_snapshots_no_finding(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t1"},
        {"date": "2026-06-02", "code": "A", "is_live": True, "captured_at": "t1"},
    ])
    assert data_health.duplicate_snapshots(tmp_path) == []


def test_duplicate_snapshots_are_book_scoped(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-06-01", "book": "B", "code": "A", "is_live": True, "captured_at": "t1"},
        {"date": "2026-06-01", "book": "T", "code": "A", "is_live": True, "captured_at": "t1"},
    ])
    assert data_health.duplicate_snapshots(tmp_path) == []


def test_incomplete_ledger_transaction_is_critical(tmp_path):
    pending = tmp_path / ".ledger_txn" / "pending.json"
    pending.parent.mkdir(parents=True)
    pending.write_text("{}", encoding="utf-8")

    findings = data_health.incomplete_ledger_transaction(tmp_path)

    assert findings and findings[0]["severity"] == "critical"


def test_account_drift_detected(tmp_path):
    (tmp_path / "paper_account.json").write_text(json.dumps({"realized_pnl": -4191.0}), encoding="utf-8")
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "realized_pnl": -100.0},
        {"book": "B", "status": "closed", "realized_pnl": -50.0},  # sum -150 vs account -4191
    ])
    findings = data_health.account_reconciles(tmp_path)
    assert findings and "drift" in findings[0]["detail"]


def test_account_reconciles_within_tolerance(tmp_path):
    (tmp_path / "paper_account.json").write_text(json.dumps({"realized_pnl": -150.0}), encoding="utf-8")
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "realized_pnl": -100.0},
        {"book": "B", "status": "closed", "realized_pnl": -50.0},
    ])
    assert data_health.account_reconciles(tmp_path) == []


def test_book_t_account_drift_detected(tmp_path):
    (tmp_path / "paper_account_T.json").write_text(json.dumps({"realized_pnl": 100.0}), encoding="utf-8")
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "T", "status": "closed", "realized_pnl": 10.0},
    ])
    findings = data_health.account_reconciles_book_t(tmp_path)
    assert findings and findings[0]["check"] == "account_reconciles_book_t"


def test_book_t_blocked_sell_cannot_be_recorded_as_closed(tmp_path):
    _write_jsonl(tmp_path / "alerts.jsonl", [{
        "ts": "2026-07-13T15:14:10",
        "alert": "SELL_BLOCKED",
        "book": "T",
        "reason": "LIMIT_DOWN_NO_BID",
        "code": "000725.XSHE",
        "entry_date": "2026-07-07",
    }])
    _write_jsonl(tmp_path / "positions.jsonl", [{
        "book": "T",
        "status": "closed",
        "code": "000725.XSHE",
        "entry_date": "2026-07-07",
        "exit_date": "2026-07-13",
        "exit_price": 6.83,
    }])

    findings = data_health.blocked_sell_executions(tmp_path)

    assert findings and findings[0]["severity"] == "critical"
    assert "000725.XSHE" in findings[0]["detail"]


def test_book_t_blocked_sell_remaining_open_is_healthy(tmp_path):
    _write_jsonl(tmp_path / "alerts.jsonl", [{
        "ts": "2026-07-13T15:14:10",
        "alert": "SELL_BLOCKED",
        "book": "T",
        "reason": "LIMIT_DOWN_NO_BID",
        "code": "000725.XSHE",
        "entry_date": "2026-07-07",
    }])
    _write_jsonl(tmp_path / "positions.jsonl", [{
        "book": "T",
        "status": "open",
        "code": "000725.XSHE",
        "entry_date": "2026-07-07",
    }])

    assert data_health.blocked_sell_executions(tmp_path) == []


def test_book_t_block_does_not_contradict_same_identity_book_b_close(tmp_path):
    _write_jsonl(tmp_path / "alerts.jsonl", [{
        "ts": "2026-07-13T15:14:10", "alert": "SELL_BLOCKED", "book": "T",
        "reason": "LIMIT_DOWN_NO_BID", "code": "SAME", "entry_date": "2026-07-07",
    }])
    _write_jsonl(tmp_path / "positions.jsonl", [{
        "book": "B", "status": "closed", "code": "SAME",
        "entry_date": "2026-07-07", "exit_date": "2026-07-13",
    }])

    assert data_health.blocked_sell_executions(tmp_path) == []


def test_morning_sell_block_can_clear_before_later_execution(tmp_path):
    _write_jsonl(tmp_path / "alerts.jsonl", [{
        "ts": "2026-06-11T09:36:26",
        "alert": "SELL_BLOCKED",
        "book": "B",
        "reason": "LIMIT_DOWN_NO_BID",
        "code": "603859.XSHG",
        "entry_date": "2026-06-10",
    }])
    _write_jsonl(tmp_path / "positions.jsonl", [{
        "book": "B", "status": "closed", "code": "603859.XSHG",
        "entry_date": "2026-06-10", "exit_date": "2026-06-11",
    }])

    assert data_health.blocked_sell_executions(tmp_path) == []


def test_unlabeled_ledger_rows_are_surfaced(tmp_path):
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "code": "A", "realized_pnl": -10.0},
        {"status": "closed", "code": "LEGACY", "realized_pnl": -5.0},  # no book label
    ])
    _write_jsonl(tmp_path / "paper_trades.jsonl", [
        {"book": "B", "side": "BUY", "code": "A"},
        {"side": "SELL", "code": "LEGACY_TRADE"},
    ])
    findings = data_health.unlabeled_closed_positions(tmp_path)
    assert findings and findings[0]["severity"] == "critical"
    assert "LEGACY" in findings[0]["detail"]
    assert "1 position" in findings[0]["detail"] and "1 trade" in findings[0]["detail"]


def test_invalid_book_value_is_critical(tmp_path):
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "X", "status": "closed", "code": "INVALID"},
    ])
    _write_jsonl(tmp_path / "paper_trades.jsonl", [
        {"book": "B", "side": "BUY", "code": "OK"},
    ])

    findings = data_health.unlabeled_closed_positions(tmp_path)

    assert findings and findings[0]["severity"] == "critical"
    assert "INVALID:'X'" in findings[0]["detail"]


def test_labeled_positions_produce_no_unlabeled_finding(tmp_path):
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "code": "A", "realized_pnl": -10.0},
        {"book": "A", "status": "closed", "code": "B", "realized_pnl": 5.0},
    ])
    _write_jsonl(tmp_path / "paper_trades.jsonl", [
        {"book": "B", "side": "BUY", "code": "A"},
        {"book": "A", "side": "SELL", "code": "B"},
    ])
    assert data_health.unlabeled_closed_positions(tmp_path) == []


def test_stale_open_positions_flagged(tmp_path):
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "open", "code": "A", "entry_date": "2026-06-01"},
        {"book": "B", "status": "open", "code": "B", "entry_date": "2026-06-18"},
    ])
    findings = data_health.stale_open_positions(tmp_path, today="2026-06-20", max_days=10)
    assert findings and "A(2026-06-01)" in findings[0]["detail"]
    assert "B(2026-06-18)" not in findings[0]["detail"]  # only 2 days old


def _write_mode_history(cache_path, latest_trade_date):
    import sqlite3
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cache_path)
    con.execute("CREATE TABLE IF NOT EXISTS mode_history (mode TEXT, trade_date TEXT, code TEXT, return_pct REAL)")
    con.execute("INSERT INTO mode_history VALUES (?,?,?,?)", ("首红断低吸", latest_trade_date, "X", -2.0))
    con.commit()
    con.close()


def test_stale_market_cache_flagged(tmp_path):
    # date_kline/mode_history feed frozen weeks behind (the June-2026 hidden lag).
    cache = tmp_path / ".cache" / "xiaocao.db"
    _write_mode_history(cache, "2026-05-27")
    findings = data_health.stale_market_cache(cache, today="2026-06-22", max_days=10)
    assert findings and findings[0]["severity"] == "warn"
    assert "2026-05-27" in findings[0]["detail"]


def test_fresh_market_cache_no_finding(tmp_path):
    cache = tmp_path / ".cache" / "xiaocao.db"
    _write_mode_history(cache, "2026-06-19")
    assert data_health.stale_market_cache(cache, today="2026-06-22", max_days=10) == []


def test_fresh_reconstructed_daily_bridges_lagging_vendor_cache(tmp_path):
    cache = tmp_path / ".cache" / "xiaocao.db"
    _write_mode_history(cache, "2026-05-27")
    reconstructed = tmp_path / "live" / "daily_reconstructed.jsonl"
    _write_jsonl(reconstructed, [{
        "code": "000001.XSHG", "date": "20260619", "close": 3000,
        "source": "minute_reconstructed",
    }])

    assert data_health.stale_market_cache(
        cache,
        reconstructed_path=reconstructed,
        today="2026-06-22",
        max_days=10,
    ) == []


def test_missing_market_cache_no_finding(tmp_path):
    # A missing cache is not a dirty-data finding.
    assert data_health.stale_market_cache(tmp_path / ".cache" / "xiaocao.db", today="2026-06-22") == []


def test_forward_label_bar_coverage_waits_until_eod_reconstruction(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-07-17", "code": "A.XSHE", "is_live": True, "book": "B"},
    ])

    assert data_health.forward_label_bar_coverage(tmp_path, today="2026-07-20") == []


def test_forward_label_bar_coverage_flags_missing_previous_live_batch(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-07-17", "code": "A.XSHE", "is_live": True, "book": "B"},
        {"date": "2026-07-17", "code": "B.XSHE", "is_live": True, "book": "B"},
        {"date": "2026-07-17", "code": "PAPER.XSHE", "is_live": False, "book": "B"},
        {"date": "2026-07-20", "code": "TODAY.XSHE", "is_live": True, "book": "B"},
    ])
    _write_jsonl(tmp_path / "daily_reconstructed.jsonl", [
        {"date": "20260720", "code": "000001.XSHG", "close": 3000},
        {"date": "20260720", "code": "A.XSHE", "close": 10},
    ])

    findings = data_health.forward_label_bar_coverage(tmp_path, today="2026-07-20")

    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"
    assert "B.XSHE" in findings[0]["detail"]
    assert "PAPER.XSHE" not in findings[0]["detail"]


def test_forward_label_bar_coverage_accepts_complete_previous_live_batch(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-07-17", "code": "A.XSHE", "is_live": True, "book": "B"},
        {"date": "2026-07-17", "code": "B.XSHE", "is_live": True, "book": "B"},
    ])
    _write_jsonl(tmp_path / "daily_reconstructed.jsonl", [
        {"date": "2026-07-20", "code": "000001.XSHG", "close": 3000},
        {"date": "2026-07-20", "code": "A.XSHE", "close": 10},
        {"date": "2026-07-20", "code": "B.XSHE", "close": 20},
    ])

    assert data_health.forward_label_bar_coverage(tmp_path, today="2026-07-20") == []


def test_check_surfaces_stale_cache(tmp_path):
    # check() auto-resolves the cache as a sibling of live_dir and includes it.
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    _write_mode_history(tmp_path / ".cache" / "xiaocao.db", "2026-05-27")
    report = data_health.check(live_dir, today="2026-06-22")
    assert any(f["check"] == "stale_market_cache" for f in report["findings"])


def test_check_aggregates(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t1"},
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t2"},
    ])
    report = data_health.check(tmp_path)
    assert report["ok"] is False and report["critical"] == 1
