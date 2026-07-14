from __future__ import annotations

import json
from pathlib import Path

from xiaocao.live.intelligence_review_queue import build_review_queue


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

    queue = build_review_queue(live_dir=live, market_date="2026-07-06", limit=8)

    assert queue["status"] == "ready"
    assert [item["code"] for item in queue["items"]] == ["OLD.XSHE", "NEW.XSHE"]
    assert queue["items"][0]["priority_reasons"][0] == "open_book_b_position"
    assert queue["items"][1]["priority_reasons"][0] == "mode_exec_star"
    assert queue["items"][1]["candidate_context"]["mode_state"] == "ACTIVE"
