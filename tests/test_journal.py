"""Tests for the structured decision journal (src/xiaocao/live/journal.py)."""
from __future__ import annotations

from xiaocao.live import journal


def test_append_and_read_roundtrip(tmp_path):
    path = tmp_path / "decision_journal.jsonl"
    rec = journal.append_decision(
        automation="live_monitor", market_date="2026-06-19",
        deterministic={"open_positions": 2, "positions": [{"code": "000001.XSHG"}]},
        posture={"regime": "neutral"}, path=path,
    )
    assert rec["automation"] == "live_monitor" and rec["state_hash"]
    rows = journal.read_all(path)
    assert len(rows) == 1 and rows[0]["market_date"] == "2026-06-19"
    assert rows[0]["deterministic"]["open_positions"] == 2


def test_read_recent_and_for_date(tmp_path):
    path = tmp_path / "j.jsonl"
    for i, d in enumerate(["2026-06-18", "2026-06-18", "2026-06-19"]):
        journal.append_decision(automation="m", market_date=d, run_id=f"r{i}", path=path)
    assert len(journal.read_recent(2, path=path)) == 2
    assert len(journal.read_for_date("2026-06-18", path=path)) == 2


def test_latest_filters_by_automation_and_date(tmp_path):
    path = tmp_path / "j.jsonl"
    journal.append_decision(automation="morning", market_date="2026-06-19", run_id="a", path=path)
    journal.append_decision(automation="live_monitor", market_date="2026-06-19", run_id="b", path=path)
    journal.append_decision(automation="live_monitor", market_date="2026-06-19", run_id="c", path=path)
    # A fresh-context agent at the close asks: what did today's morning run conclude?
    assert journal.latest(automation="morning", market_date="2026-06-19", path=path)["run_id"] == "a"
    # ...and the most recent monitor run.
    assert journal.latest(automation="live_monitor", path=path)["run_id"] == "c"
    assert journal.latest(automation="eod", path=path) is None


def test_state_hash_is_stable_and_order_independent():
    a = journal.state_hash({"x": 1, "y": [2, 3]})
    b = journal.state_hash({"y": [2, 3], "x": 1})
    assert a == b and len(a) == 16


def test_append_never_raises_on_unwritable_path(tmp_path):
    # A file where a directory is expected -> mkdir/open fail, but auditing must
    # never crash the loop; append returns the record regardless.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    rec = journal.append_decision(
        automation="m", market_date="2026-06-19", path=blocker / "nested.jsonl",
    )
    assert rec["automation"] == "m"
    assert journal.read_all(blocker / "nested.jsonl") == []
