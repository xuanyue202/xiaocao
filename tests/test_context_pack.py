from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from xiaocao.live.context_pack import build_context_pack


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_build_context_pack_from_existing_artifacts(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    _jsonl(live / "signal_snapshots.jsonl", [
        {
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "book": "B",
            "stock_sentiment_score": 0.3,
            "intelligence_factor_score_source": "pending_agent_review",
        }
    ])
    _jsonl(live / "stock_sentiment_history.jsonl", [
        {
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "score_source": "pending_agent_review",
            "data_quality": "ok",
            "evidence_state": "available",
            "authority": 0,
        }
    ])
    _jsonl(live / "intelligence_evidence_2026-07-01.jsonl", [
        {
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "name": "Test",
            "universe": "candidates+open_positions",
            "data_quality": "ok",
            "evidence_count": 1,
            "candidate_context": {"vb_star": True, "vb_rank": 1},
            "evidence": [{"title": "headline"}],
        }
    ])
    _jsonl(live / "positions.jsonl", [
        {"date": "2026-07-01", "code": "000001.XSHE", "book": "B", "status": "open", "entry_date": "2026-07-01"}
    ])
    (live / "paper_account.json").write_text(json.dumps({"cash": 100000, "realized_pnl": 0}), encoding="utf-8")
    (live / "paper_holdings.json").write_text(json.dumps({"date": "2026-07-01", "open_positions": 1}), encoding="utf-8")
    _jsonl(live / "agent_signals.jsonl", [
        {
            "id": "s1",
            "market_date": "2026-07-01",
            "signal_type": "news_headline_sentiment",
            "status": "active",
            "authority": 0,
        }
    ])

    pack = build_context_pack(
        live_dir=live,
        market_date="2026-07-01",
        phase="morning",
        now=datetime(2026, 7, 1, 9, 30),
    )

    assert pack["read_only"] is True
    assert pack["signals"]["rows_for_date"] == 1
    assert pack["signals"]["sentiment_attached"] == 1
    assert pack["stock_intelligence"]["data_quality"]["ok"] == 1
    assert pack["agent_signals"]["rows_for_date"] == 1
    assert pack["intelligence_evidence"]["rows_for_date"] == 1
    assert pack["intelligence_status"]["status"] == "pending_agent_review"
    assert pack["intelligence_status"]["fallback_to_base_pick"] is True
    assert pack["intelligence_status"]["agent_review_rows"] == 0
    assert pack["intelligence_review_queue"]["counts"]["selected_items"] == 1


def test_context_pack_status_uses_fresh_review_queue_not_stale_file(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    _jsonl(live / "positions.jsonl", [
        {"date": "2026-07-01", "code": "000001.XSHE", "book": "B", "status": "open", "entry_date": "2026-07-01"}
    ])
    _jsonl(live / "stock_sentiment_history.jsonl", [
        {"date": "2026-07-01", "code": "000001.XSHE", "score_source": "pending_agent_review", "data_quality": "ok"}
    ])
    _jsonl(live / "intelligence_evidence_2026-07-01.jsonl", [
        {
            "date": "2026-07-01",
            "code": "000001.XSHE",
            "name": "Test",
            "data_quality": "ok",
            "evidence_count": 1,
            "candidate_context": {"vb_star": True, "vb_rank": 1},
            "evidence": [{"title": "headline"}],
        }
    ])
    (live / "intelligence_review_queue_2026-07-01.json").write_text(
        json.dumps({
            "status": "ready",
            "counts": {"selected_items": 99, "pending_items": 99},
            "items": [],
        }),
        encoding="utf-8",
    )

    pack = build_context_pack(
        live_dir=live,
        market_date="2026-07-01",
        phase="morning",
        now=datetime(2026, 7, 1, 9, 30),
    )

    fresh_counts = pack["intelligence_review_queue"]["counts"]
    status_queue = pack["intelligence_status"]["review_queue"]
    assert fresh_counts["selected_items"] == 1
    assert status_queue["selected_items"] == fresh_counts["selected_items"]
    assert status_queue["pending_items"] == fresh_counts["pending_items"]
