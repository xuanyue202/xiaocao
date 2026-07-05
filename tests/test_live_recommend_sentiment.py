from __future__ import annotations

import importlib.util
import inspect
import json
from datetime import datetime
from pathlib import Path


def _load_live_recommend():
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "live_recommend.py"
    spec = importlib.util.spec_from_file_location("live_recommend_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_headline_sentiment_summary_and_label():
    mod = _load_live_recommend()
    headlines = [
        {"title": "某公司签约大单并获批新项目"},
        {"title": "主力资金净买入"},
    ]
    score = mod._headline_sentiment_score(headlines)
    assert score > 0
    assert mod._headline_sentiment_label(score) == "偏多"
    summary = mod._headline_sentiment_summary(headlines, score)
    assert "近期公开标题偏多" in summary
    assert "签约大单并获批新项目" in summary


def test_intelligence_evidence_fetch_budget_is_sixty_seconds():
    mod = _load_live_recommend()
    sig = inspect.signature(mod._build_top_stock_sentiment)

    assert mod.INTELLIGENCE_EVIDENCE_TIMEOUT_SEC == 60.0
    assert sig.parameters["max_seconds"].default == 60.0


def test_cache_freshness_expires_same_day_records() -> None:
    mod = _load_live_recommend()

    assert mod._cache_record_fresh(
        {"date": "2026-07-05", "fetched_at": "2026-07-05T09:25:00"},
        "2026-07-05",
        now=datetime.fromisoformat("2026-07-05T09:35:00"),
    ) is True
    assert mod._cache_record_fresh(
        {"date": "2026-07-05", "fetched_at": "2026-07-05T09:25:00"},
        "2026-07-05",
        now=datetime.fromisoformat("2026-07-05T10:05:01"),
    ) is False


def test_build_stock_sentiment_refreshes_stale_same_day_cache(tmp_path: Path, monkeypatch) -> None:
    mod = _load_live_recommend()
    mod.STOCK_SENTIMENT_FILE = tmp_path / "stock_sentiment.json"
    mod.STOCK_SENTIMENT_FILE.write_text(
        json.dumps([{
            "date": "2026-07-05",
            "code": "000001.XSHE",
            "name": "平安银行",
            "fetched_at": "2026-07-05T09:25:00",
            "headlines": [{"title": "旧标题"}],
            "veto_flags": [{"event_type": "debt_default", "severity": "high", "confidence": 0.9}],
        }], ensure_ascii=False),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def fake_fetch(name: str, code: str):
        calls.append((name, code))
        return "https://example.test/rss", [{"title": "新标题", "published_at": "2026-07-05T10:10:00"}]

    monkeypatch.setattr(mod, "_fetch_google_news_headlines", fake_fetch)

    rows = mod._build_top_stock_sentiment(
        [{"code": "000001.XSHE", "name": "平安银行"}],
        "2026-07-05",
        max_workers=1,
        max_seconds=5,
    )

    assert calls == [("平安银行", "000001.XSHE")]
    assert rows[0]["evidence_capture_state"] == "fetched"
    assert rows[0]["headlines"][0]["title"] == "新标题"
    assert rows[0]["prior_veto_flags_carried"] is True
    assert rows[0]["veto_flags"][0]["event_type"] == "debt_default"


def test_open_book_b_positions_are_added_to_intelligence_universe(tmp_path: Path) -> None:
    mod = _load_live_recommend()
    positions = tmp_path / "positions.jsonl"
    positions.write_text(
        "\n".join([
            json.dumps({"book": "B", "status": "open", "code": "000001.XSHE", "name": "平安银行", "entry_date": "2026-07-04"}, ensure_ascii=False),
            json.dumps({"book": "T", "status": "open", "code": "000002.XSHE", "name": "万科A"}, ensure_ascii=False),
            json.dumps({"book": "B", "status": "closed", "code": "000003.XSHE", "name": "国农科技"}, ensure_ascii=False),
        ]) + "\n",
        encoding="utf-8",
    )

    open_positions = mod._load_open_book_b_position_candidates(positions)
    universe = mod._merge_intelligence_universe(
        [{"code": "000004.XSHE", "name": "国华网安"}],
        open_positions,
    )

    assert [row["code"] for row in open_positions] == ["000001.XSHE"]
    assert [row["code"] for row in universe] == ["000004.XSHE", "000001.XSHE"]
    assert universe[1]["target_set"] == "open_position"


def test_merge_sentiment_into_signal_snapshots(tmp_path: Path):
    mod = _load_live_recommend()
    mod.OUT_DIR = tmp_path
    snap = tmp_path / "signal_snapshots.jsonl"
    snap.write_text(
        json.dumps({"date": "2026-06-04", "code": "000001.XSHE", "vb_star": True}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    records = [{
        "date": "2026-06-04",
        "code": "000001.XSHE",
        "score": 0.3,
        "score_source": "agent_review",
        "agent_score": 0.3,
        "agent_short_score": 0.3,
        "agent_trend_score": -0.2,
        "trend_label": "偏空",
        "keyword_score": -0.1,
        "label": "偏多",
        "summary": "近期公开标题偏多，最新聚焦“测试标题”。",
        "source": "google_news_rss",
        "target_set": "vb_star",
        "data_quality": "ok",
        "evidence_state": "available",
        "authority": 0,
        "relevance_counts": {"direct_company_news": 1},
        "usage": {"exit_composite_input": True, "buy_ranking": False},
    }]
    mod._merge_sentiment_into_signal_snapshots(records, "2026-06-04")
    row = json.loads(snap.read_text(encoding="utf-8").strip())
    assert row["stock_sentiment_score"] == 0.3
    assert row["stock_sentiment_label"] == "偏多"
    assert row["stock_sentiment_decision_used"] is False
    assert row["stock_sentiment_target_set"] == "vb_star"
    assert row["stock_sentiment_data_quality"] == "ok"
    assert row["stock_sentiment_authority"] == 0
    assert row["stock_sentiment_exit_composite_input"] is False
    assert row["stock_sentiment_buy_ranking_used"] is False
    assert row["score_source"] == "agent_review"
    assert row["agent_short_score"] == 0.3
    assert row["veto_flags"] == []
    assert row["ai_intelligence_short_star"] is True
    assert row["ai_intelligence_short_rank"] == 1
    assert row["ai_intelligence_short_score"] == 0.3
    assert row["ai_intelligence_short_surface"] == "shadow_ab"
    assert row["intelligence_long_star"] is True
    assert row["intelligence_long_rank"] == 1
    assert row["intelligence_long_score"] == 0.3
    assert row["intelligence_long_surface"] == "shadow_ab"
    assert row["intelligence_factor_short_score"] == 0.3
    assert row["intelligence_factor_trend_score"] == -0.2
    assert row["intelligence_factor_trend_label"] == "偏空"
