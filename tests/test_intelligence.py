from __future__ import annotations

from xiaocao.live import intelligence


def test_stock_intelligence_record_shapes_evidence_and_usage() -> None:
    record = intelligence.build_stock_intelligence_record(
        date="2026-07-01",
        code="000001.XSHE",
        name="平安银行",
        source="unit",
        source_url="https://example.com/rss",
        headlines=[
            {"title": "平安银行获批新项目并签约大单", "link": "https://example.com/a"},
            {"title": "A股市场题材分化"},
        ],
    )

    assert record["schema_version"] == 2
    assert record["authority"] == 0
    assert record["decision_used"] is False
    assert record["usage"]["buy_ranking"] is False
    assert record["usage"]["exit_composite_input"] is False
    assert record["data_quality"] == "ok"
    assert record["relevance_counts"]["direct_company_news"] == 1
    assert record["relevance_counts"]["macro_market_news"] == 1
    assert record["score"] == 0.0
    assert record["score_source"] == "pending_agent_review"
    assert record["keyword_score"] > 0


def test_normalize_legacy_stock_intelligence_record() -> None:
    legacy = {
        "date": "2026-07-01",
        "code": "000001.XSHE",
        "sentiment_score": 0.3,
        "headlines": [{"title": "平安银行增长"}],
    }
    record = intelligence.normalize_stock_intelligence_record(
        legacy,
        date="2026-07-01",
        code="000001.XSHE",
        name="平安银行",
    )

    assert record["schema_version"] == 2
    assert record["score"] == 0.0
    assert record["keyword_score"] == 0.3
    assert record["data_quality"] == "ok"
    assert record["usage"]["training_shadow"] is True


def test_apply_agent_review_short_only_does_not_write_trend() -> None:
    base = intelligence.build_stock_intelligence_record(
        date="2026-07-01",
        code="000001.XSHE",
        name="平安银行",
        source="unit",
        source_url="",
        headlines=[{"title": "平安银行增长"}],
    )

    reviewed = intelligence.apply_agent_review(base, {
        "short_score": 0.4,
        "summary": "短线催化清楚，趋势兑现压力偏大。",
    })

    assert reviewed["score_source"] == "agent_review"
    assert reviewed["agent_short_score"] == 0.4
    assert reviewed["agent_trend_score"] is None
    assert reviewed["score"] == 0.4


def test_apply_agent_review_trend_only_preserves_short() -> None:
    base = intelligence.build_stock_intelligence_record(
        date="2026-07-01",
        code="000001.XSHE",
        name="平安银行",
        source="unit",
        source_url="",
        headlines=[{"title": "平安银行增长"}],
    )
    short = intelligence.apply_agent_review(base, {"short_score": -0.1, "summary": "短线一般。"})

    reviewed = intelligence.apply_agent_review(short, {
        "trend_score": 0.5,
        "trend_summary": "趋势逻辑更强。",
    })

    assert reviewed["agent_short_score"] == -0.1
    assert reviewed["score"] == -0.1
    assert reviewed["agent_trend_score"] == 0.5
    assert reviewed["trend_score_source"] == "agent_review"
    assert reviewed["trend_summary"] == "趋势逻辑更强。"


def test_short_shadow_rank_map_requires_agent_review_bullish_quality() -> None:
    ranked = intelligence.short_shadow_rank_map([
        {"code": "A.XSHE", "score": 0.9, "data_quality": "ok", "score_source": "pending_agent_review"},
        {"code": "B.XSHE", "agent_short_score": 0.4, "score": 0.4, "data_quality": "ok", "score_source": "agent_review", "target_rank": 2},
        {"code": "C.XSHE", "agent_short_score": 0.5, "score": 0.5, "data_quality": "fetch_failed", "score_source": "agent_review"},
        {"code": "D.XSHE", "agent_short_score": 0.3, "score": 0.3, "data_quality": "ok", "score_source": "agent_review", "target_rank": 1},
    ])

    assert list(ranked) == ["B.XSHE", "D.XSHE"]
    assert ranked["B.XSHE"]["ai_intelligence_short_rank"] == 1
    assert ranked["D.XSHE"]["ai_intelligence_short_star"] is True
    assert ranked["D.XSHE"]["intelligence_long_star"] is True
