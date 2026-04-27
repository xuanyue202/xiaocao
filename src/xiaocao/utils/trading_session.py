from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


A_SHARE_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class TradingSession:
    phase: str
    uses_live_intraday_data: bool
    aggregate_data_ready: bool


def now_shanghai() -> datetime:
    return datetime.now(A_SHARE_TZ)


def classify_a_share_session(now: datetime | None = None) -> TradingSession:
    """Classify the current A-share trading-day phase by wall clock.

    This deliberately separates "the calendar says today is a trading day"
    from "after-close aggregate endpoints are ready". Many Xiaocao endpoints
    populate only after close and can still be empty during premarket/intraday.
    """
    current = _to_shanghai(now).time()
    if current < time(9, 15):
        return TradingSession("premarket", uses_live_intraday_data=False, aggregate_data_ready=False)
    if current < time(9, 25):
        return TradingSession("auction", uses_live_intraday_data=True, aggregate_data_ready=False)
    if current < time(9, 30):
        return TradingSession("preopen", uses_live_intraday_data=True, aggregate_data_ready=False)
    if current < time(11, 30):
        return TradingSession("morning", uses_live_intraday_data=True, aggregate_data_ready=False)
    if current < time(13, 0):
        return TradingSession("lunch", uses_live_intraday_data=True, aggregate_data_ready=False)
    if current < time(15, 0):
        return TradingSession("afternoon", uses_live_intraday_data=True, aggregate_data_ready=False)
    if current < time(16, 0):
        return TradingSession("postclose_pending", uses_live_intraday_data=True, aggregate_data_ready=False)
    return TradingSession("afterclose", uses_live_intraday_data=False, aggregate_data_ready=True)


def latest_completed_trade_date(
    trade_dates: list[str],
    now: datetime | None = None,
) -> str:
    """Return the latest trade date whose after-close aggregate data should exist."""
    if not trade_dates:
        raise ValueError("trade_dates must not be empty")
    dates = sorted(trade_dates)
    today_iso = _to_shanghai(now).date().isoformat()
    latest = dates[-1]
    if latest < today_iso:
        return latest
    if latest > today_iso:
        return latest
    if classify_a_share_session(now).aggregate_data_ready:
        return latest
    previous = [d for d in dates if d < today_iso]
    return previous[-1] if previous else latest


def _to_shanghai(now: datetime | None) -> datetime:
    if now is None:
        return now_shanghai()
    if now.tzinfo is None:
        return now.replace(tzinfo=A_SHARE_TZ)
    return now.astimezone(A_SHARE_TZ)
