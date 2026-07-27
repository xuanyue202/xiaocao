from __future__ import annotations

import json

from scripts.wait_for_morning_freeze import wait_for_morning_freeze


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
