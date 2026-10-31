"""Beijing clock-hour slots with a two-minute scheduler early-start allowance."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")


def automation_hour_start(now: datetime) -> datetime:
    """Assign HH:58 through HH:59:59 to the upcoming hour, without changing now."""
    if now.tzinfo is None:
        raise ValueError("automation clock needs a timezone")
    local = now.astimezone(BEIJING)
    return (local + timedelta(minutes=2)).replace(minute=0, second=0, microsecond=0)
