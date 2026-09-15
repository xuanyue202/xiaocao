from __future__ import annotations

import hashlib
import json

from scripts.wait_for_morning_freeze import wait_for_morning_freeze
from xiaocao.live.trading_runner import frozen_rows_digest


def test_wait_for_morning_freeze_accepts_matching_report_and_queue(tmp_path) -> None:
    date = "2026-07-20"
    (tmp_path / f"recommend_{date}.md").write_text("# recommendation\n", encoding="utf-8")
    (tmp_path / f"intelligence_review_queue_{date}.json").write_text(
        json.dumps({
            "market_date": date,
            "status": "ready",
            "counts": {"selected_items": 7},
        }),
        encoding="utf-8",
    )

    result = wait_for_morning_freeze(
        date=date,
        live_dir=tmp_path,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "ready"
    assert result["queue_status"] == "ready"
    assert result["selected_items"] == 7


def test_wait_for_morning_freeze_rejects_stale_queue(tmp_path) -> None:
    date = "2026-07-20"
    (tmp_path / f"recommend_{date}.md").write_text("# recommendation\n", encoding="utf-8")
    (tmp_path / f"intelligence_review_queue_{date}.json").write_text(
        json.dumps({"market_date": "2026-07-17", "status": "ready"}),
        encoding="utf-8",
    )

    result = wait_for_morning_freeze(
        date=date,
        live_dir=tmp_path,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "timeout"
    assert result["reason"] == "queue_market_date_mismatch"


def test_wait_for_morning_freeze_binds_the_completed_snapshot(tmp_path) -> None:
    date = "2026-07-20"
    snapshot = tmp_path / "signal_snapshots.jsonl"
    snapshot_row = {"date": date, "code": "000001.XSHE", "book": "B"}
    snapshot.write_text(json.dumps(snapshot_row) + "\n", encoding="utf-8")
    report = tmp_path / f"recommend_{date}.md"
    report.write_text("# recommendation\n", encoding="utf-8")
    snapshot_sha = frozen_rows_digest([snapshot_row])
    report_sha = hashlib.sha256(report.read_bytes()).hexdigest()
    (tmp_path / f"intelligence_review_queue_{date}.json").write_text(
        json.dumps({
            "market_date": date,
            "status": "ready",
            "counts": {"selected_items": 1},
            "freeze_binding": {
                "strategy_run_id": f"morning-freeze:{date}:{snapshot_sha[:16]}",
                "strategy_sha": "d" * 40,
                "snapshot_row_count": 1,
                "snapshot_sha256": snapshot_sha,
                "report_sha256": report_sha,
            },
        }),
        encoding="utf-8",
    )

    result = wait_for_morning_freeze(
        date=date,
        live_dir=tmp_path,
        snapshot_path=snapshot,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "ready"
    assert result["snapshot_row_count"] == 1
    assert len(result["snapshot_sha256"]) == 64
    assert result["snapshot_path"] == str(snapshot)
    assert result["strategy_sha"] == "d" * 40


def test_wait_for_morning_freeze_rejects_snapshot_appended_after_queue_freeze(tmp_path) -> None:
    date = "2026-07-20"
    original = {"date": date, "code": "000001.XSHE", "book": "B"}
    appended = {"date": date, "code": "000002.XSHE", "book": "B"}
    snapshot = tmp_path / "signal_snapshots.jsonl"
    snapshot.write_text(
        "\n".join(json.dumps(row) for row in (original, appended)) + "\n",
        encoding="utf-8",
    )
    report = tmp_path / f"recommend_{date}.md"
    report.write_text("# recommendation\n", encoding="utf-8")
    (tmp_path / f"intelligence_review_queue_{date}.json").write_text(
        json.dumps({
            "market_date": date,
            "status": "ready",
            "counts": {"selected_items": 1},
            "freeze_binding": {
                "strategy_run_id": "morning-freeze:stale",
                "strategy_sha": "d" * 40,
                "snapshot_row_count": 1,
                "snapshot_sha256": frozen_rows_digest([original]),
                "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            },
        }),
        encoding="utf-8",
    )

    result = wait_for_morning_freeze(
        date=date,
        live_dir=tmp_path,
        snapshot_path=snapshot,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "timeout"
    assert result["reason"] == "queue_snapshot_binding_mismatch"


def test_wait_for_morning_freeze_rejects_missing_producer_strategy_sha(tmp_path) -> None:
    date = "2026-07-20"
    snapshot = tmp_path / "signal_snapshots.jsonl"
    row = {"date": date, "code": "000001.XSHE", "book": "B"}
    snapshot.write_text(json.dumps(row) + "\n", encoding="utf-8")
    report = tmp_path / f"recommend_{date}.md"
    report.write_text("# recommendation\n", encoding="utf-8")
    (tmp_path / f"intelligence_review_queue_{date}.json").write_text(
        json.dumps(
            {
                "market_date": date,
                "status": "ready",
                "counts": {"selected_items": 1},
                "freeze_binding": {
                    "strategy_run_id": "morning-freeze:missing-sha",
                    "snapshot_row_count": 1,
                    "snapshot_sha256": frozen_rows_digest([row]),
                    "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                },
            }
        ),
        encoding="utf-8",
    )

    result = wait_for_morning_freeze(
        date=date,
        live_dir=tmp_path,
        snapshot_path=snapshot,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "timeout"
    assert result["reason"] == "queue_snapshot_binding_mismatch"


def test_freeze_wait_keeps_session_warm_with_bounded_heartbeats(tmp_path, monkeypatch):
    import scripts.wait_for_morning_freeze as waiter
    elapsed = [0.0]
    beats = []
    monkeypatch.setattr(waiter.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(waiter.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    monkeypatch.setattr(waiter, "_freeze_status", lambda **kwargs: {"status": "ready" if elapsed[0] >= 61 else "missing"})
    result = waiter.wait_for_morning_freeze(date="2026-09-11", live_dir=tmp_path,
        timeout_sec=90, poll_sec=1, heartbeat=lambda: beats.append(elapsed[0]))
    assert result["status"] == "ready" and beats == [0, 30, 60]


def _morning_clock(monkeypatch, start):
    from datetime import datetime, timedelta
    import scripts.wait_for_morning_freeze as waiter
    elapsed, sleeps = [0.0], []
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (start + timedelta(seconds=elapsed[0])).astimezone(tz)
    def sleep(seconds):
        sleeps.append(seconds)
        elapsed[0] += seconds
    # raising=False keeps the original fixed-interval implementation reproducible.
    monkeypatch.setattr(waiter, 'datetime', Clock, raising=False)
    monkeypatch.setattr(waiter.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(waiter.time, 'sleep', sleep)
    return waiter, elapsed, sleeps


def test_early_native_wait_sleeps_until_0924_before_touching_app(tmp_path, monkeypatch):
    from datetime import datetime
    waiter, elapsed, sleeps = _morning_clock(monkeypatch, datetime.fromisoformat('2026-09-15T09:00:00+08:00'))
    beats, reads = [], []
    def status(**kwargs):
        reads.append(elapsed[0])
        return {'status': 'ready' if elapsed[0] >= 1533 else 'waiting'}
    monkeypatch.setattr(waiter, '_freeze_status', status)
    result = waiter.wait_for_morning_freeze(date='2026-09-15', live_dir=tmp_path,
        timeout_sec=2100, poll_sec=1, heartbeat=lambda: beats.append(elapsed[0]))
    assert result['status'] == 'ready'
    assert beats == [1440, 1470, 1500, 1530]
    assert not any(0 < t < 1440 for t in reads)
    assert max(sleeps) <= 60


def test_early_wait_timeout_never_touches_app(tmp_path, monkeypatch):
    from datetime import datetime
    waiter, elapsed, sleeps = _morning_clock(monkeypatch, datetime.fromisoformat('2026-09-15T09:23:50+08:00'))
    monkeypatch.setattr(waiter, '_freeze_status', lambda **kw: {'status': 'waiting'})
    def unexpected_heartbeat():
        raise AssertionError('native heartbeat before 09:24')
    result = waiter.wait_for_morning_freeze(date='2026-09-15', live_dir=tmp_path,
        timeout_sec=5, poll_sec=1, heartbeat=unexpected_heartbeat)
    assert result['status'] == 'timeout'
    assert elapsed[0] == 5 and sleeps == [5]


def test_0924_wakeup_recovers_before_consuming_freeze(tmp_path, monkeypatch):
    from datetime import datetime
    waiter, elapsed, _ = _morning_clock(monkeypatch, datetime.fromisoformat('2026-09-15T09:23:50+08:00'))
    events = []
    def status(**kw):
        events.append(('freeze', elapsed[0]))
        return {'status': 'ready' if elapsed[0] >= 10 else 'waiting'}
    monkeypatch.setattr(waiter, '_freeze_status', status)
    result = waiter.wait_for_morning_freeze(date='2026-09-15', live_dir=tmp_path,
        timeout_sec=30, poll_sec=1, heartbeat=lambda: events.append(('native', elapsed[0])))
    assert result['status'] == 'ready'
    assert events == [('freeze', 0), ('native', 10), ('freeze', 11)]


def test_late_start_and_native_recovery_failure_do_not_wait_or_continue(tmp_path, monkeypatch):
    from datetime import datetime
    import pytest
    waiter, elapsed, sleeps = _morning_clock(monkeypatch, datetime.fromisoformat('2026-09-15T09:24:40+08:00'))
    monkeypatch.setattr(waiter, '_freeze_status', lambda **kw: {'status': 'waiting'})
    def failed_recovery():
        raise RuntimeError('session_recovery_failed')
    with pytest.raises(RuntimeError, match='session_recovery_failed'):
        waiter.wait_for_morning_freeze(date='2026-09-15', live_dir=tmp_path,
            timeout_sec=90, poll_sec=1, heartbeat=failed_recovery)
    assert elapsed[0] == 0 and sleeps == []


def test_paper_freeze_wait_has_no_native_idle_schedule(tmp_path, monkeypatch):
    from datetime import datetime
    waiter, elapsed, _ = _morning_clock(monkeypatch, datetime.fromisoformat('2026-09-15T09:00:00+08:00'))
    monkeypatch.setattr(waiter, '_freeze_status', lambda **kw: {'status': 'ready' if elapsed[0] >= 1 else 'waiting'})
    result = waiter.wait_for_morning_freeze(date='2026-09-15', live_dir=tmp_path,
        timeout_sec=5, poll_sec=1)
    assert result['status'] == 'ready' and elapsed[0] == 1
