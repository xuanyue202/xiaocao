from __future__ import annotations

from datetime import datetime

from scripts.live_monitor import _decide_sell_action, _decide_trend_sell_action, _sell_block_reason
from xiaocao.utils.trading_session import A_SHARE_TZ


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 2, hour, minute, tzinfo=A_SHARE_TZ)


def test_stale_position_defers_composite_exit_to_eod_discipline() -> None:
    # staged execution: composite deterioration is diagnosed intraday but
    # executed at the 14:55 pass, not sold into the morning weakness
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": 1.2, "high": 10.1, "upPrice": 11.0},
        latest_price=9.95,
        peak=10.15,
        dd_pct=1.97,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=-0.2,
        now=_dt(10, 0),
    )

    assert decision["triggered"] is False
    assert decision["deferred_sell_reason"] == "COMPOSITE_MORNING_EXIT"


def test_stale_position_waits_when_composite_not_bad_enough() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": 2.4, "high": 10.1, "upPrice": 11.0},
        latest_price=10.0,
        peak=10.1,
        dd_pct=0.99,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.05,
        now=_dt(10, 0),
    )

    assert decision["triggered"] is False
    assert decision["decision_phase"] == "morning_assessment"


def test_stale_position_holds_when_turning_leader_near_high_and_score_supports_it() -> None:
    decision = _decide_sell_action(
        {"mode": "接力低弱转1", "flags": "★KP1", "xcjw": 380, "jsjl": 12},
        detail={"pctChangeRate": 8.6, "high": 10.08, "upPrice": 11.0},
        latest_price=10.05,
        peak=10.05,
        dd_pct=0.0,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.42,
        now=_dt(10, 5),
    )

    assert decision["triggered"] is False
    assert decision["hold_reason"] == "TURNED_LEADER_NEAR_HIGH"


def test_eod_discipline_sells_soft_hold_that_is_not_strong_enough() -> None:
    decision = _decide_sell_action(
        {"mode": "接力低弱转1", "flags": "★KP1", "xcjw": 320, "jsjl": 8},
        detail={"pctChangeRate": 6.4, "high": 10.0, "upPrice": 11.0},
        latest_price=9.98,
        peak=10.0,
        dd_pct=0.2,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.12,
        now=_dt(14, 56),
    )

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "EOD_DISCIPLINE_1455"


def test_eod_discipline_keeps_limit_up_style_exception() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 150, "jsjl": 0},
        detail={"pctChangeRate": 9.8, "high": 10.9, "upPrice": 11.0},
        latest_price=10.97,
        peak=10.98,
        dd_pct=0.09,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.35,
        now=_dt(14, 56),
    )

    assert decision["triggered"] is False
    assert decision["hold_reason"] in {"NEAR_LIMIT_UP", "LIMIT_UP_DAY"}


def test_soft_trailing_stop_is_deferred_intraday() -> None:
    # dd above the soft threshold but below the hard floor: diagnose, don't
    # sell the morning low
    decision = _decide_sell_action(
        {"mode": "绿断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": -2.5, "high": 10.0, "upPrice": 11.0},
        latest_price=9.6,
        peak=10.0,
        dd_pct=4.0,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.8,
        now=_dt(9, 41),
    )

    assert decision["triggered"] is False
    assert decision["deferred_sell_reason"] == "TRAILING_STOP"


def test_hard_floor_executes_immediately_intraday() -> None:
    decision = _decide_sell_action(
        {"mode": "绿断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": -8.5, "high": 10.0, "upPrice": 11.0},
        latest_price=9.1,
        peak=10.0,
        dd_pct=9.0,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.8,
        now=_dt(9, 31),
    )

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "HARD_STOP"
    assert decision["decision_phase"] == "risk_floor"


def test_eod_pass_executes_trailing_stop_with_attribution() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": -3.0, "high": 10.0, "upPrice": 11.0},
        latest_price=9.7,
        peak=10.0,
        dd_pct=3.0,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.0,
        now=_dt(14, 56),
    )

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "TRAILING_STOP"
    assert decision["decision_phase"] == "eod_discipline"


def test_midday_review_tightens_threshold_vs_morning() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": 0.8, "high": 10.1, "upPrice": 11.0},
        latest_price=9.98,
        peak=10.1,
        dd_pct=1.19,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=-0.03,
        now=_dt(11, 0),
    )

    # midday cut (-0.02) catches a score the morning cut (-0.15) would pass,
    # but execution is deferred to the 14:55 pass
    assert decision["triggered"] is False
    assert decision["deferred_sell_reason"] == "COMPOSITE_MIDDAY_EXIT"


def test_same_day_position_remains_t1_blocked() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": 0.5, "high": 10.0, "upPrice": 11.0},
        latest_price=9.95,
        peak=10.0,
        dd_pct=0.5,
        dd_threshold=2.0,
        t1_blocked=True,
        hold_days=0,
        now=_dt(10, 0),
    )

    assert decision["triggered"] is False
    assert decision["decision_phase"] == "t1_blocked"


def test_ai_event_risk_exit_triggers_after_t1() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": 1.0, "high": 10.2, "upPrice": 11.0},
        latest_price=10.1,
        peak=10.2,
        dd_pct=0.98,
        dd_threshold=2.0,
        t1_blocked=False,
        hold_days=1,
        signal_score=0.5,
        event_risk={"triggered": True, "event_types": ["financial_fraud"]},
        now=_dt(10, 0),
    )

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "AI_EVENT_RISK_EXIT"
    assert decision["decision_phase"] == "event_risk"


def test_ai_event_risk_exit_respects_t1_block() -> None:
    decision = _decide_sell_action(
        {"mode": "首红断低吸", "flags": "", "xcjw": 120, "jsjl": 0},
        detail={"pctChangeRate": -8.0, "high": 10.0, "upPrice": 11.0},
        latest_price=9.2,
        peak=10.0,
        dd_pct=8.0,
        dd_threshold=2.0,
        t1_blocked=True,
        hold_days=0,
        event_risk={"triggered": True, "event_types": ["financial_fraud"]},
        now=_dt(10, 0),
    )

    assert decision["triggered"] is False
    assert decision["decision_phase"] == "t1_blocked"


def test_book_t_uses_wide_trend_stop_not_shortline_composite() -> None:
    decision = _decide_trend_sell_action(
        {"trend_rebalance_days": 60},
        dd_pct=11.5,
        dd_threshold=12.0,
        t1_blocked=False,
        hold_days=10,
        now=_dt(10, 0),
    )
    assert decision["triggered"] is False
    assert decision["hold_reason"] == "TREND_HOLD"

    decision = _decide_trend_sell_action(
        {"trend_rebalance_days": 60},
        dd_pct=12.1,
        dd_threshold=12.0,
        t1_blocked=False,
        hold_days=10,
        now=_dt(10, 0),
    )
    assert decision["triggered"] is True
    assert decision["sell_reason"] == "TREND_TRAIL_STOP"


def test_book_t_rebalance_due_waits_for_paired_morning_switch() -> None:
    intraday = _decide_trend_sell_action(
        {"trend_rebalance_days": 20},
        dd_pct=0.0,
        t1_blocked=False,
        hold_days=21,
        now=_dt(10, 0),
    )
    eod = _decide_trend_sell_action(
        {"trend_rebalance_days": 20},
        dd_pct=0.0,
        t1_blocked=False,
        hold_days=21,
        now=_dt(14, 56),
    )
    assert intraday["triggered"] is False
    assert eod["triggered"] is False
    assert eod["sell_reason"] is None
    assert eod["decision_phase"] == "trend_rebalance_due_wait_paired_switch"


def test_simulated_sell_blocks_limit_down_with_no_bid() -> None:
    assert _sell_block_reason({
        "trade": 9.001,
        "downPrice": 9.0,
        "buyVol1": 0,
    }) == "LIMIT_DOWN_NO_BID"


def test_simulated_sell_allows_limit_down_when_bid_exists() -> None:
    assert _sell_block_reason({
        "trade": 9.0,
        "downPrice": 9.0,
        "buyVol1": 100,
    }) is None
