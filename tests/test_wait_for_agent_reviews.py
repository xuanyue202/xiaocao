from __future__ import annotations

import json

from scripts.wait_for_agent_reviews import review_progress


def _write(path, value):
    if isinstance(value, list):
        path.write_text("\n".join(json.dumps(row) for row in value) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def test_review_progress_counts_only_selected_same_day_agent_reviews(tmp_path) -> None:
    queue = tmp_path / "queue.json"
    history = tmp_path / "history.jsonl"
    _write(queue, {
        "market_date": "2026-07-14",
        "items": [{"code": "A.XSHE"}, {"code": "B.XSHE"}],
    })
    _write(history, [
        {"date": "2026-07-14", "code": "A.XSHE", "score_source": "agent_review"},
        {"date": "2026-07-14", "code": "B.XSHE", "score_source": "pending_agent_review"},
        {"date": "2026-07-13", "code": "B.XSHE", "score_source": "agent_review"},
        {"date": "2026-07-14", "code": "OTHER", "score_source": "agent_review"},
    ])

    progress = review_progress(queue, history)

    assert progress == {"selected": 2, "reviewed": 1, "pending": 1, "reviewed_codes": ["A.XSHE"]}
