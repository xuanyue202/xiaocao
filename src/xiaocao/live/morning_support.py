"""Versioned support bounds; execution windows and immutable requests are independent."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CONDITIONAL_FIRST = 'conditional_first_v1'


def conditional_first(request: dict) -> bool:
    return request.get('judgment_mode') == CONDITIONAL_FIRST


def opening_cutoff(trade_date: str, *, mode: str | None = None) -> datetime:
    second = 30 if mode == CONDITIONAL_FIRST else 0
    return datetime.fromisoformat(f'{trade_date}T09:27:{second:02d}+08:00')


def support_deadline(request: dict) -> datetime:
    requested = datetime.fromisoformat(request['requested_at'].replace('Z', '+00:00'))
    deadline = min(datetime.fromisoformat(request['entry_deadline'].replace('Z', '+00:00')),
                   requested + timedelta(seconds=min(120, float(request['max_wait_seconds']))))
    if request.get('review_wait_until'):
        deadline = min(deadline, datetime.fromisoformat(request['review_wait_until'].replace('Z', '+00:00')))
    local = requested.astimezone(ZoneInfo('Asia/Shanghai'))
    if conditional_first(request) or (local.hour, local.minute) < (9, 30):
        deadline = min(deadline, opening_cutoff(local.date().isoformat(), mode=request.get('judgment_mode')))
    return deadline
