"""Direct unit tests for the extracted staged exit policy
(src/xiaocao/live/exit_policy.py). These lock the OPERATING_CONTRACT §4
invariant — intraday only executes the hard floor; ordinary exits defer to
14:55 — at the module boundary, independent of live_monitor wiring.
"""
from __future__ import annotations

from datetime import datetime

from xiaocao.live.exit_policy import decide_sell_action

# Times are naive; exit_policy localizes them to the A-share session tz.
T_MORNING = datetime(2026, 6, 19, 10, 0)   # 10:00 — intraday checkpoint
T_1456 = datetime(2026, 6, 19, 14, 56)     # past the 14:55 discipline gate
POS = {"mode": "首红断低吸", "profile": "v5"}
DETAIL = {"pctChangeRate": -3.0, "upPrice": 0.0, "high": 0.0}  # nothing special


def _call(**over):
    base = dict(
        position=POS, detail=DETAIL, latest_price=10.0, peak=10.0,
        dd_pct=0.0, dd_threshold=2.0, t1_blocked=False, hold_days=1,
        signal_score=0.0, hard_dd_threshold=8.0, now=T_MORNING,
    )
    base.update(over)
    return decide_sell_action(**base)


def test_t1_blocked_never_acts():
    d = _call(t1_blocked=True, dd_pct=50.0)  # even a huge drawdown
    assert d["triggered"] is False and d["decision_phase"] == "t1_blocked"


def test_same_day_holds():
    d = _call(hold_days=0, dd_pct=5.0)
    assert d["triggered"] is False and d["decision_phase"] == "same_day"


def test_hard_floor_executes_intraday():
    d = _call(dd_pct=8.0, now=T_MORNING)
    assert d["triggered"] is True and d["sell_reason"] == "HARD_STOP"
    assert d["decision_phase"] == "risk_floor"


def test_ordinary_trailing_is_deferred_intraday_not_executed():
    # dd above the v5 2% threshold but below the 8% hard floor, mid-session:
    # MUST be diagnosed (deferred), never executed before 14:55.
    d = _call(dd_pct=3.0, now=T_MORNING)
    assert d["triggered"] is False
    assert d.get("deferred_sell_reason") == "TRAILING_STOP"


def test_composite_deterioration_deferred_intraday():
    d = _call(signal_score=-0.5, dd_pct=0.0, now=T_MORNING)
    assert d["triggered"] is False
    assert d.get("deferred_sell_reason") == "COMPOSITE_MORNING_EXIT"


def test_1455_executes_trailing_when_dd_breached():
    d = _call(dd_pct=3.0, now=T_1456)
    assert d["triggered"] is True and d["sell_reason"] == "TRAILING_STOP"
    assert d["decision_phase"] == "eod_discipline"


def test_1455_executes_discipline_when_dd_not_breached():
    d = _call(dd_pct=0.5, now=T_1456)
    assert d["triggered"] is True and d["sell_reason"] == "EOD_DISCIPLINE_1455"


def test_hard_floor_suppressed_by_near_limit_up_strong_hold():
    # A near-limit-up name with an 8% drawdown must NOT fire the hard floor (the
    # soft hold suppresses it); intraday it neither executes nor defers a sell.
    detail = {"upPrice": 11.0, "pctChangeRate": 9.9, "high": 11.0}
    d = _call(detail=detail, latest_price=10.98, dd_pct=8.0, now=T_MORNING)
    assert d["triggered"] is False and d["sell_reason"] is None
    assert d.get("deferred_sell_reason") is None


def test_1455_strong_hold_suppresses_discipline_exit():
    detail = {"upPrice": 11.0, "pctChangeRate": 9.9, "high": 11.0}
    d = _call(detail=detail, latest_price=10.98, dd_pct=3.0, now=T_1456)
    assert d["triggered"] is False and d["hold_reason"] == "NEAR_LIMIT_UP"
