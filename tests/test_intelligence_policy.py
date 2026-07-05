from __future__ import annotations

from xiaocao.live import intelligence_policy


def test_hard_veto_requires_taxonomy_confidence_and_severity() -> None:
    row = {
        "veto_flags": [
            {
                "event_type": "dishonesty_enforcement",
                "severity": "critical",
                "confidence": 0.91,
                "reason": "listed as dishonest enforcement subject",
                "event_date": "2026-07-01",
            },
            {
                "event_type": "keyword_bad_news",
                "severity": "critical",
                "confidence": 0.99,
                "reason": "not in explicit taxonomy",
            },
            {
                "event_type": "financial_fraud",
                "severity": "low",
                "confidence": 0.95,
                "reason": "severity too low",
            },
        ],
    }

    flags = intelligence_policy.valid_hard_veto_flags(
        row,
        asof="2026-07-02T09:30:00+08:00",
    )

    assert [flag["event_type"] for flag in flags] == ["dishonesty_enforcement"]
    state = intelligence_policy.hard_veto_state(row, asof="2026-07-02T09:30:00+08:00")
    assert state["hard_veto"] is True
    assert state["event_types"] == ["dishonesty_enforcement"]


def test_stale_hard_veto_expires_unless_ongoing() -> None:
    cfg = intelligence_policy.IntelligenceTradeConfig(veto_max_age_days=30)
    stale = {
        "veto_flags": [{
            "event_type": "debt_default",
            "severity": "high",
            "confidence": 0.9,
            "event_date": "2026-05-01",
        }]
    }
    ongoing = {
        "veto_flags": [{**stale["veto_flags"][0], "ongoing": True}]
    }

    assert intelligence_policy.hard_veto_state(stale, config=cfg, asof="2026-07-05T09:30:00+08:00")["hard_veto"] is False
    assert intelligence_policy.hard_veto_state(ongoing, config=cfg, asof="2026-07-05T09:30:00+08:00")["hard_veto"] is True


def test_select_buy_candidates_replaces_low_ranked_base_pick_with_ai_candidate() -> None:
    rows = [
        {
            "code": "A.XSHE",
            "vb_star": True,
            "vb_rank": 1,
            "rank_score": 100,
            "score_source": "agent_review",
            "agent_short_score": 0.1,
            "data_quality": "ok",
        },
        {
            "code": "B.XSHE",
            "vb_star": True,
            "vb_rank": 2,
            "rank_score": 98,
            "score_source": "agent_review",
            "agent_short_score": 0.4,
            "data_quality": "ok",
            "veto_flags": [{
                "event_type": "dishonesty_enforcement",
                "severity": "critical",
                "confidence": 0.95,
            }],
        },
        {
            "code": "C.XSHE",
            "vb_star": False,
            "rank_score": 90,
            "score_source": "agent_review",
            "agent_short_score": 0.9,
            "data_quality": "ok",
        },
    ]

    result = intelligence_policy.select_buy_candidates(
        rows,
        pick_col="vb_star",
        config=intelligence_policy.IntelligenceTradeConfig(mode="on", score_bonus=20),
    )

    assert result.slot_count == 2
    assert [row["code"] for row in result.selected] == ["C.XSHE", "A.XSHE"]
    assert result.selected[0]["ai_intelligence_replaced_base_pick"] is True
    assert [row["code"] for row in result.vetoed] == ["B.XSHE"]


def test_select_buy_candidates_accepts_signal_snapshot_schema() -> None:
    rows = [
        {
            "code": "A.XSHE",
            "vb_star": True,
            "vb_rank": 1,
            "rank_score": 100,
            "intelligence_factor_score_source": "agent_review",
            "intelligence_factor_short_score": 0.0,
            "stock_sentiment_data_quality": "ok",
        },
        {
            "code": "C.XSHE",
            "vb_star": False,
            "rank_score": 90,
            "agent_short_score": None,
            "intelligence_factor_score_source": "agent_review",
            "intelligence_factor_short_score": 0.9,
            "stock_sentiment_data_quality": "ok",
        },
    ]

    result = intelligence_policy.select_buy_candidates(
        rows,
        pick_col="vb_star",
        config=intelligence_policy.IntelligenceTradeConfig(mode="on", score_bonus=20),
    )

    assert [row["code"] for row in result.selected] == ["C.XSHE"]
    assert result.selected[0]["ai_intelligence_short_score"] == 0.9
    assert result.selected[0]["ai_intelligence_replaced_base_pick"] is True


def test_select_buy_candidates_without_agent_review_matches_base_picks() -> None:
    rows = [
        {"code": "B.XSHE", "vb_star": True, "vb_rank": 2, "rank_score": 99},
        {"code": "A.XSHE", "vb_star": True, "vb_rank": 1, "rank_score": 10},
        {"code": "C.XSHE", "vb_star": False, "rank_score": 99},
    ]

    result = intelligence_policy.select_buy_candidates(rows, pick_col="vb_star")

    assert [row["code"] for row in result.selected] == ["B.XSHE", "A.XSHE"]
    assert all(row["ai_intelligence_buy_ranking_used"] is False for row in result.selected)
    assert result.vetoed == []


def test_low_score_non_base_review_does_not_disturb_base_picks() -> None:
    rows = [
        {"code": "B.XSHE", "vb_star": True, "vb_rank": 2, "rank_score": 99},
        {"code": "A.XSHE", "vb_star": True, "vb_rank": 1, "rank_score": 10},
        {
            "code": "C.XSHE",
            "vb_star": False,
            "rank_score": 999,
            "score_source": "agent_review",
            "agent_short_score": -0.2,
            "data_quality": "ok",
        },
    ]

    result = intelligence_policy.select_buy_candidates(rows, pick_col="vb_star")

    assert [row["code"] for row in result.selected] == ["B.XSHE", "A.XSHE"]
    assert all(row["ai_intelligence_buy_ranking_used"] is False for row in result.selected)


def test_event_risk_exit_uses_hard_veto_state() -> None:
    risk = intelligence_policy.event_risk_exit({
        "veto_flags": [{
            "event_type": "financial_fraud",
            "severity": "high",
            "confidence": 0.8,
            "reason": "confirmed financial fraud",
        }]
    })

    assert risk["triggered"] is True
    assert risk["sell_reason"] == "AI_EVENT_RISK_EXIT"
