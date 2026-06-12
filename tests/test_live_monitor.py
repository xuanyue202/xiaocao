from __future__ import annotations

from datetime import datetime

from scripts.live_monitor import _decide_sell_action, _sell_block_reason
from xiaocao.utils.trading_session import A_SHARE_TZ


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 2, hour, minute, tzinfo=A_SHARE_TZ)


def test_stale_position_sells_after_935_when_composite_turns_negative() -> None:
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

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "COMPOSITE_MORNING_EXIT"


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


def test_hard_stop_sells_before_morning_rotation_window() -> None:
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
        now=_dt(9, 31),
    )

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "TRAILING_STOP"


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

    assert decision["triggered"] is True
    assert decision["sell_reason"] == "COMPOSITE_MIDDAY_EXIT"


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
