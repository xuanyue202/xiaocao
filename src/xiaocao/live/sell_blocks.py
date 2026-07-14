"""Shared audit facts for sell attempts rejected by market liquidity.

An alert with ``SELL_BLOCKED`` is an execution fact, not a recommendation.  Any
paper-book writer must preserve the position for that exact trading day.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SellBlockKey = tuple[str, str, str, str]


def normal_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if len(text) >= 10:
        return text[:10]
    return None


def load_blocked_sell_keys(
    path: Path,
    *,
    book: str | None = None,
    not_before_time: str | None = None,
) -> dict[SellBlockKey, str]:
    """Return exact ``(book, date, code, entry_date) -> reason`` blocked facts."""
    blocked: dict[SellBlockKey, str] = {}
    if not path.exists():
        return blocked
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if row.get("alert") != "SELL_BLOCKED":
                continue
            row_book = str(row.get("book") or "B")
            if book is not None and row_book != book:
                continue
            ts = str(row.get("ts") or "")
            if not_before_time is not None:
                event_time = ts[11:19] if len(ts) >= 19 else ""
                if not event_time or event_time < not_before_time:
                    continue
            alert_date = normal_date(row.get("ts") or row.get("date"))
            entry_date = normal_date(row.get("entry_date"))
            code = str(row.get("code") or "").strip()
            if not alert_date or not entry_date or not code:
                continue
            blocked[(row_book, alert_date, code, entry_date)] = str(
                row.get("reason") or "SELL_BLOCKED"
            )
    return blocked
