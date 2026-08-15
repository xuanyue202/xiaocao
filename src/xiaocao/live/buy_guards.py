"""Deterministic market facts required before a Book B BUY."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


LIMIT_DOWN_BUY_BLOCKED = "LIMIT_DOWN_BUY_BLOCKED"
LIMIT_DOWN_CHECK_UNAVAILABLE = "LIMIT_DOWN_CHECK_UNAVAILABLE"

_TRADING_STATUSES = frozenset({"ok", "t", "trading", "open", "normal", "交易中", "正常"})
_HALTED_STATUSES = frozenset({"s", "suspended", "halt", "stopped", "停牌", "暂停交易"})
_LIMIT_DOWN_STATUSES = frozenset({"limit_down", "limitdown", "跌停"})
_MARKET_TZ = ZoneInfo("Asia/Shanghai")


def _number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _observation_date(value: object) -> str | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    compact = re.match(r"^(\d{4})(\d{2})(\d{2})", text)
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}-{compact.group(3)}"
    return None


def _observation_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=_MARKET_TZ)
        except ValueError:
            return None
    if not text or len(text) < 16 or "-" not in text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_MARKET_TZ)
    return parsed


def evaluate_buy_market_guard(
    row: dict[str, Any],
    *,
    require_authoritative: bool | None = None,
    now: datetime | None = None,
    max_age_seconds: int = 900,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Return ``(allowed, reason, evidence)`` for one BUY row.

    The function never infers a price limit from a percentage.  For a live
    snapshot the caller must set ``market_guard_required`` (or pass the
    keyword) and provide a current price, authoritative ``downPrice`` and a
    tradable status.  Missing/ambiguous facts fail closed.  Historical paper
    rows may omit the guard because they are not used to authorize a current
    order.
    """
    required = bool(row.get("market_guard_required")) if require_authoritative is None else bool(require_authoritative)
    status_raw = str(row.get("market_guard_status") or row.get("trade_status") or row.get("tradeStatus") or "").strip()
    status = status_raw.lower()
    down_price = _number(row, "down_price", "downPrice", "limit_down_price")
    latest_price = _number(row, "latest_price", "market_price", "trade", "last")
    observed_at = row.get("market_observed_at") or row.get("trade_timestamp") or row.get("tradeTimestamp")
    evidence = {
        "market_guard_required": required,
        "market_guard_status": status_raw or None,
        "down_price": down_price,
        "latest_price": latest_price,
        "observed_at": observed_at,
    }

    if status in _LIMIT_DOWN_STATUSES:
        return False, LIMIT_DOWN_BUY_BLOCKED, evidence
    if down_price is not None and latest_price is not None and latest_price <= down_price + 1e-6:
        return False, LIMIT_DOWN_BUY_BLOCKED, evidence
    if status in _HALTED_STATUSES:
        return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
    if required and not observed_at:
        return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
    if required:
        expected_date = str(row.get("date") or row.get("trade_date") or "")[:10]
        observed_date = _observation_date(observed_at)
        if expected_date and observed_date != expected_date:
            return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
        observed_dt = _observation_datetime(observed_at)
        if observed_dt is None:
            # A few legacy paper fixtures carry only a clock value.  Without
            # an expected trade date there is no date mismatch to prove; keep
            # that compatibility path.  Live plans always carry trade_date,
            # so malformed/date-less observations still fail closed there.
            if expected_date:
                return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
        else:
            clock = now or datetime.now(timezone.utc)
            if clock.tzinfo is None:
                clock = clock.replace(tzinfo=timezone.utc)
            age_seconds = (clock - observed_dt).total_seconds()
            if age_seconds > max(0, int(max_age_seconds)) or age_seconds < -60:
                return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
    if status in _TRADING_STATUSES and down_price is not None and latest_price is not None:
        return True, None, evidence
    if not required:
        return True, None, evidence
    return False, LIMIT_DOWN_CHECK_UNAVAILABLE, evidence
