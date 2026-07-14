from __future__ import annotations

import json
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
    assert [e["status"] for e in events] == ["info", "degraded", "succeeded"]
    snapshot = run_flow.build_snapshot(
        automation="morning",
        market_date="2026-07-01",
        events=events,
        exit_code=0,
    )
    assert snapshot["status"] == "degraded"
    assert snapshot["deterministic_status"] == "succeeded"
    assert snapshot["counts"]["degraded"] == 1


def test_optional_health_degrades_success_without_faking_main_chain_failure() -> None:
    events = [run_flow.event(
        automation="morning", market_date="2026-07-14", step="done", status="succeeded"
    )]

    snapshot = run_flow.build_snapshot(
        automation="morning",
        market_date="2026-07-14",
        events=events,
        exit_code=0,
        supporting_health={
            "status": "degraded",
            "issues": [{"surface": "posture", "detail": "expired"}],
        },
    )

    assert snapshot["deterministic_status"] == "succeeded"
    assert snapshot["status"] == "degraded"
    assert snapshot["supporting_health"]["issues"][0]["surface"] == "posture"


def test_partial_agent_review_is_supporting_degradation(tmp_path: Path) -> None:
    (tmp_path / "intelligence_review_queue_2026-07-14.json").write_text(json.dumps({
        "market_date": "2026-07-14",
        "items": [{"code": "A.XSHE"}, {"code": "B.XSHE"}],
    }), encoding="utf-8")
    (tmp_path / "stock_sentiment_history.jsonl").write_text(json.dumps({
        "date": "2026-07-14", "code": "A.XSHE", "score_source": "agent_review",
    }) + "\n", encoding="utf-8")
    posture = tmp_path / "posture.json"
    posture.write_text(json.dumps({"valid_until": "2026-07-14"}), encoding="utf-8")

    health = run_flow.supporting_health_from_live(
        live_dir=tmp_path, market_date="2026-07-14", posture_path=posture,
    )

    assert health["status"] == "degraded"
    assert health["agent_review"] == {"selected": 2, "reviewed": 1, "pending": 1}
    assert any(issue["surface"] == "agent_review" for issue in health["issues"])
