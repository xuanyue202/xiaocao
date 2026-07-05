from __future__ import annotations

from pathlib import Path

from xiaocao.live import agent_signals


def test_agent_signal_upsert_expiry_and_scoring(tmp_path: Path) -> None:
    signal = agent_signals.make_signal(
        market_date="2026-07-01",
        source="unit",
        signal_type="news_headline_sentiment",
        scope="stock",
        subject={"kind": "stock", "code": "000001.XSHE"},
        direction="bullish",
        score=0.4,
        label="偏多",
        summary="测试",
        evidence_ref="x",
        expires_at="2026-07-02",
    )
    path = tmp_path / "agent_signals.jsonl"
    agent_signals.upsert_signals(path, [signal])
    agent_signals.upsert_signals(path, [signal])

    rows = agent_signals.read_signals(path, as_of="2026-07-03")
    assert len(rows) == 1
    assert rows[0]["status"] == "expired"

    scored = agent_signals.score_signals_against_training_rows(rows, [
        {"date": "2026-07-01", "code": "000001.XSHE", "net_realized_ret": 1.2},
    ])
    assert scored["n_scored"] == 1
    assert scored["hit_rate"] == 1.0


def test_agent_signal_upsert_replaces_revised_score_for_same_subject(tmp_path: Path) -> None:
    common = {
        "market_date": "2026-07-01",
        "source": "stock_intelligence",
        "signal_type": "ai_intelligence_short_factor",
        "scope": "stock",
        "subject": {"kind": "stock", "code": "000001.XSHE"},
        "summary": "测试",
        "evidence_ref": "x",
    }
    bullish = agent_signals.make_signal(**common, direction="bullish", score=0.4, label="偏多")
    bearish = agent_signals.make_signal(**common, direction="bearish", score=-0.5, label="偏空")
    path = tmp_path / "agent_signals.jsonl"

    agent_signals.upsert_signals(path, [bullish])
    agent_signals.upsert_signals(path, [bearish])

    rows = agent_signals.read_signals(path, as_of="2026-07-01")
    assert len(rows) == 1
    assert rows[0]["direction"] == "bearish"
    assert rows[0]["score"] == -0.5
    assert rows[0]["id"] == rows[0]["stable_key"]


def test_signals_from_intelligence_records() -> None:
    rows = agent_signals.signals_from_intelligence_records([{
        "date": "2026-07-01",
        "code": "000001.XSHE",
        "name": "平安银行",
        "score_source": "agent_review",
        "agent_short_score": -0.3,
        "agent_trend_score": 0.4,
        "score": -0.3,
        "label": "偏空",
        "trend_label": "偏多",
        "summary": "测试",
        "authority": 0,
    }])

    assert rows[0]["direction"] == "bearish"
    assert rows[0]["signal_type"] == "ai_intelligence_short_factor"
    assert rows[0]["authority"] == 0
    assert rows[0]["metadata"]["target_set"] is None
    assert rows[1]["signal_type"] == "ai_intelligence_trend_factor"
    assert rows[1]["direction"] == "bullish"


def test_trend_only_intelligence_record_creates_only_trend_signal() -> None:
    rows = agent_signals.signals_from_intelligence_records([{
        "date": "2026-07-01",
        "code": "000001.XSHE",
        "name": "平安银行",
        "score_source": "pending_agent_review",
        "agent_trend_score": 0.4,
        "trend_score_source": "agent_review",
        "trend_label": "偏多",
        "trend_summary": "趋势证据更强。",
        "authority": 0,
    }])

    assert len(rows) == 1
    assert rows[0]["signal_type"] == "ai_intelligence_trend_factor"
    assert rows[0]["direction"] == "bullish"


def test_pending_intelligence_records_do_not_create_agent_signals() -> None:
    rows = agent_signals.signals_from_intelligence_records([{
        "date": "2026-07-01",
        "code": "000001.XSHE",
        "score_source": "pending_agent_review",
        "score": 0.9,
    }])

    assert rows == []
