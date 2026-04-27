from __future__ import annotations

from datetime import datetime

from xiaocao.utils.trading_session import (
    A_SHARE_TZ,
    classify_a_share_session,
    latest_completed_trade_date,
)


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 4, 27, hour, minute, tzinfo=A_SHARE_TZ)


def test_classify_a_share_session_core_phases() -> None:
    assert classify_a_share_session(_dt(8, 59)).phase == "premarket"
    assert classify_a_share_session(_dt(9, 20)).phase == "auction"
    assert classify_a_share_session(_dt(9, 27)).phase == "preopen"
    assert classify_a_share_session(_dt(10, 0)).phase == "morning"
    assert classify_a_share_session(_dt(12, 0)).phase == "lunch"
    assert classify_a_share_session(_dt(14, 0)).phase == "afternoon"
    assert classify_a_share_session(_dt(15, 30)).phase == "postclose_pending"
    assert classify_a_share_session(_dt(16, 0)).phase == "afterclose"


def test_latest_completed_trade_date_uses_previous_before_afterclose_ready() -> None:
    dates = ["2026-04-23", "2026-04-24", "2026-04-27"]
    assert latest_completed_trade_date(dates, _dt(9, 0)) == "2026-04-24"
    assert latest_completed_trade_date(dates, _dt(14, 30)) == "2026-04-24"
    assert latest_completed_trade_date(dates, _dt(15, 30)) == "2026-04-24"
    assert latest_completed_trade_date(dates, _dt(16, 0)) == "2026-04-27"


def test_latest_completed_trade_date_keeps_past_latest_date() -> None:
    dates = ["2026-04-23", "2026-04-24"]
    assert latest_completed_trade_date(dates, _dt(9, 0)) == "2026-04-24"
