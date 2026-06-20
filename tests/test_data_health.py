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


def test_check_aggregates(tmp_path):
    _write_jsonl(tmp_path / "signal_snapshots.jsonl", [
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t1"},
        {"date": "2026-06-01", "code": "A", "is_live": True, "captured_at": "t2"},
    ])
    report = data_health.check(tmp_path)
    assert report["ok"] is False and report["critical"] == 1
