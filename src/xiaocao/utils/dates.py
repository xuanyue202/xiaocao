from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from xiaocao.api.errors import InvalidDateError


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMPACT_RE = re.compile(r"^\d{8}$")


def today_str() -> str:
    return date.today().isoformat()


def parse_date(value: str) -> date:
    if DATE_RE.match(value):
        return datetime.strptime(value, "%Y-%m-%d").date()
    if COMPACT_RE.match(value):
        return datetime.strptime(value, "%Y%m%d").date()
    raise InvalidDateError(f"Invalid date: {value}. Expected YYYY-MM-DD or YYYYMMDD")


def normal_date(value: str) -> str:
    return parse_date(value).isoformat()


def compact_date(value: str) -> str:
    return parse_date(value).strftime("%Y%m%d")


def date_range(start: str, end: str) -> list[str]:
    current = parse_date(start)
    stop = parse_date(end)
    if current > stop:
        raise InvalidDateError("start date must be before or equal to end date")
    days = []
    while current <= stop:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def lookback_start(end: str, days: int = 45) -> str:
    return (parse_date(end) - timedelta(days=days)).isoformat()
