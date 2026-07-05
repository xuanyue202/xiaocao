from __future__ import annotations

from pathlib import Path

from xiaocao.live import run_flow


def test_events_from_log_and_snapshot(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text(
        "\n".join([
            "[2026-07-01 09:25:00] morning: live_recommend",
            "[2026-07-01 09:26:00] data health CRITICAL — SKIPPING forward_eval",
            "[2026-07-01 09:27:00] morning done -> output/live/recommend_2026-07-01.md",
        ]) + "\n",
        encoding="utf-8",
    )

    events = run_flow.events_from_log(automation="morning", market_date="2026-07-01", log_path=log)
    assert [e["status"] for e in events] == ["info", "failed", "succeeded"]
    snapshot = run_flow.build_snapshot(
        automation="morning",
        market_date="2026-07-01",
        events=events,
        exit_code=0,
    )
    assert snapshot["status"] == "failed"
    assert snapshot["counts"]["failed"] == 1
