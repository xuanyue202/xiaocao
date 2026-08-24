from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.wait_for_morning_freeze import wait_for_morning_freeze
from xiaocao.live.intelligence_review_queue import (
    build_review_queue,
    write_review_queue,
)


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_review_queue_prioritizes_open_positions_over_new_candidates(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    _jsonl(live / "positions.jsonl", [
        {"code": "OLD.XSHE", "name": "Old", "book": "B", "status": "open", "entry_date": "2026-07-01"},
    ])
    _jsonl(live / "stock_sentiment_history.jsonl", [
        {"date": "2026-07-06", "code": "OLD.XSHE", "score_source": "pending_agent_review"},
        {"date": "2026-07-06", "code": "NEW.XSHE", "score_source": "pending_agent_review"},
        {"date": "2026-07-06", "code": "DONE.XSHE", "score_source": "agent_review", "agent_short_score": 0.5},
    ])
    _jsonl(live / "intelligence_evidence_2026-07-06.jsonl", [
        {
            "date": "2026-07-06",
            "code": "NEW.XSHE",
            "name": "New",
            "data_quality": "ok",
            "evidence_count": 5,
            "candidate_context": {
                "mode_exec_star": True,
                "mode_exec_rank": 1,
                "mode_state": "ACTIVE",
                "vb_star": True,
                "vb_rank": 1,
            },
            "evidence": [{"title": "new title"}],
        },
        {
            "date": "2026-07-06",
            "code": "OLD.XSHE",
            "name": "Old",
            "data_quality": "ok",
            "evidence_count": 2,
            "candidate_context": {"vb_star": False},
            "evidence": [{"title": "old title"}],
        },
        {
            "date": "2026-07-06",
            "code": "DONE.XSHE",
            "name": "Done",
            "data_quality": "ok",
            "evidence_count": 5,
            "candidate_context": {"vb_star": True, "vb_rank": 2},
            "evidence": [{"title": "done title"}],
        },
    ])
    _jsonl(live / "signal_snapshots.jsonl", [
        {"date": "2026-07-06", "code": "NEW.XSHE", "book": "B"},
    ])
    (live / "recommend_2026-07-06.md").write_text("# frozen\n", encoding="utf-8")

    queue = build_review_queue(
        live_dir=live,
        market_date="2026-07-06",
        limit=8,
        strategy_sha="d" * 40,
    )

    assert queue["status"] == "ready"
    assert [item["code"] for item in queue["items"]] == ["OLD.XSHE", "NEW.XSHE"]
    assert queue["items"][0]["priority_reasons"][0] == "open_book_b_position"
    assert queue["items"][1]["priority_reasons"][0] == "mode_exec_star"
    assert queue["items"][1]["candidate_context"]["mode_state"] == "ACTIVE"
    assert queue["freeze_binding"]["snapshot_row_count"] == 1
    assert len(queue["freeze_binding"]["snapshot_sha256"]) == 64
    assert len(queue["freeze_binding"]["report_sha256"]) == 64
    assert queue["freeze_binding"]["strategy_run_id"].startswith("morning-freeze:")
    assert queue["freeze_binding"]["strategy_sha"] == "d" * 40


def test_agent_review_rewrite_does_not_invalidate_immutable_live_freeze(
    tmp_path: Path,
) -> None:
    live = tmp_path / "live"
    live.mkdir()
    market_date = "2026-07-06"
    snapshot_row = {
        "date": market_date,
        "code": "NEW.XSHE",
        "book": "B",
        "is_live": True,
        "mode_exec_star": True,
        "mode_trade_eligible": True,
        "executable_fillable": True,
    }
    _jsonl(live / "signal_snapshots.jsonl", [snapshot_row])
    _jsonl(
        live / f"intelligence_evidence_{market_date}.jsonl",
        [
            {
                "date": market_date,
                "code": "NEW.XSHE",
                "data_quality": "ok",
                "evidence_count": 1,
                "candidate_context": {"mode_exec_star": True},
            }
        ],
    )
    report = live / f"recommend_{market_date}.md"
    report.write_text("# frozen\n", encoding="utf-8")
    queue = build_review_queue(
        live_dir=live,
        market_date=market_date,
        limit=8,
        strategy_sha="d" * 40,
    )
    freeze = Path(queue["freeze_binding"]["snapshot_path"])
    write_review_queue(
        live / f"intelligence_review_queue_{market_date}.json",
        queue,
    )

    _jsonl(
        live / "signal_snapshots.jsonl",
        [
            {
                **snapshot_row,
                "score_source": "agent_review",
                "agent_short_score": 0.75,
                "stock_sentiment_summary": "reviewed after deterministic freeze",
            }
        ],
    )

    result = wait_for_morning_freeze(
        date=market_date,
        live_dir=live,
        snapshot_path=freeze,
        timeout_sec=0,
        poll_sec=0.01,
    )

    assert result["status"] == "ready"
    assert result["snapshot_path"] == str(freeze)
    assert queue["freeze_binding"]["snapshot_artifact"] == (
        "immutable_book_b_live_freeze_v1"
    )


def test_review_queue_refuses_to_overwrite_a_different_live_freeze(
    tmp_path: Path,
) -> None:
    live = tmp_path / "live"
    live.mkdir()
    market_date = "2026-07-06"
    original = {"date": market_date, "code": "A.XSHE", "book": "B"}
    _jsonl(live / "signal_snapshots.jsonl", [original])
    (live / f"recommend_{market_date}.md").write_text("# frozen\n", encoding="utf-8")
    build_review_queue(live_dir=live, market_date=market_date, limit=8)

    _jsonl(
        live / "signal_snapshots.jsonl",
        [{**original, "score_source": "later_agent_review"}],
    )

    with pytest.raises(RuntimeError, match="BOOK_B_LIVE_FREEZE_IMMUTABILITY_VIOLATION"):
        build_review_queue(live_dir=live, market_date=market_date, limit=8)
