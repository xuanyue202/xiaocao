"""Tests for the data-health doctor (src/xiaocao/live/data_health.py)."""
from __future__ import annotations

import json

from xiaocao.live import data_health


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_duplicate_snapshots_detected(tmp_path):
    # The 06-01 bug: same (date,code,is_live) captured more than once.
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


def test_unlabeled_closed_positions_are_surfaced(tmp_path):
    # A closed row with NO `book` field is counted as book B by default; surface
    # it so a future book-A close can't be silently absorbed into book B's recon.
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "code": "A", "realized_pnl": -10.0},
        {"status": "closed", "code": "LEGACY", "realized_pnl": -5.0},  # no book label
    ])
    findings = data_health.unlabeled_closed_positions(tmp_path)
    assert findings and findings[0]["severity"] == "warn"
    assert "LEGACY" in findings[0]["detail"] and "1 closed" in findings[0]["detail"]


def test_labeled_positions_produce_no_unlabeled_finding(tmp_path):
    _write_jsonl(tmp_path / "positions.jsonl", [
        {"book": "B", "status": "closed", "code": "A", "realized_pnl": -10.0},
        {"book": "A", "status": "closed", "code": "B", "realized_pnl": 5.0},
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


def test_missing_market_cache_no_finding(tmp_path):
    # A missing cache is not a dirty-data finding.
    assert data_health.stale_market_cache(tmp_path / ".cache" / "xiaocao.db", today="2026-06-22") == []


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
