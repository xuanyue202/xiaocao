"""Beijing clock-hour slots with a ten-minute scheduler early-start allowance."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")


def automation_hour_start(now: datetime) -> datetime:
    """Assign HH:50 through HH:59:59 to the upcoming hour, without changing now."""
    if now.tzinfo is None:
        raise ValueError("automation clock needs a timezone")
    local = now.astimezone(BEIJING)
    return (local + timedelta(minutes=10)).replace(minute=0, second=0, microsecond=0)


def validate_automation_slot(slot: datetime, acquired_at: datetime | None, now: datetime) -> datetime:
    """Validate the gate binding without altering the observed acquisition time."""
    if (slot.tzinfo is None or slot.minute or slot.second or slot.microsecond
            or now.tzinfo is None):
        raise ValueError("automation slot must be a timezone-aware hour")
    local_slot = slot.astimezone(BEIJING)
    if local_slot.minute or local_slot.second or local_slot.microsecond:
        raise ValueError("automation slot must be a Beijing hour")
    if acquired_at is not None and (
        acquired_at.tzinfo is None or acquired_at > now
        or automation_hour_start(acquired_at) != local_slot
    ):
        raise ValueError("automation acquisition time is invalid")
    return local_slot
