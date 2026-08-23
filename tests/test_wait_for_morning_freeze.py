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
