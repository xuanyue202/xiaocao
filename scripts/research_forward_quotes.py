"""Shared local-clock windows and source-bound quotes for forward research."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from live_monitor import _detail_observed_at, _detail_trade_date

CHINA = ZoneInfo("Asia/Shanghai")


def now():
    return datetime.now(CHINA)


def save(path, state):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as stream:
        json.dump(
            state, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def at(day, hhmm):
    return datetime.fromisoformat(f"{day}T{hhmm[:2]}:{hhmm[2:]}:00").replace(
        tzinfo=CHINA
    )


def wait_until(target, clock, sleep):
    while (seconds := (target - clock()).total_seconds()) > 0:
        sleep(min(15, seconds))


def bar(client, code, day, minute):
    raw = client.minute_line(code, trade_date=day.replace("-", ""), count=241)
    hits = [
        r
        for r in raw
        if r.get("code") == code
        and str(r.get("tradeDate")) == day.replace("-", "")
        and str(r.get("tradeTime")).zfill(4) == minute
    ]
    if len(hits) != 1:
        return None
    row = hits[0]
    price, volume = float(row["trade"]), float(row["vol"])
    if math.isfinite(price) and price > 0 and math.isfinite(volume) and volume >= 0:
        return {"trade": price, "vol": volume}
    return None


def collect(client, codes, day, minute, deadline, clock, sleep):
    pending = list(dict.fromkeys(codes))
    points, errors = {}, {}
    while pending and clock() < deadline:
        for code in list(pending):
            if clock() >= deadline:
                break
            try:
                q = bar(client, code, day, minute)
            except Exception as exc:
                q = None
                errors[code] = type(exc).__name__
            observed = clock()
            if q and observed < deadline:
                points[code] = {**q, "observed_at": observed.isoformat()}
                pending.remove(code)
        if pending and clock() < deadline:
            sleep(min(2, (deadline - clock()).total_seconds()))
    return points, {
        code: errors.get(code, "exact_point_missing_or_late") for code in pending
    }


def close_guard(client, code, day):
    payload = client.second_line_detail_info(code)
    if isinstance(payload, dict) and code in payload:
        payload = {**payload[code], "code": payload[code].get("code", code)}
    rows = payload if isinstance(payload, list) else [payload]
    for r in rows:
        if not isinstance(r, dict) or r.get("code") != code:
            continue
        if _detail_trade_date(r) != day:
            continue
        timestamp = _detail_observed_at(r, day)
        if not timestamp or timestamp.astimezone(CHINA).date().isoformat() != day:
            continue
        minute = timestamp.astimezone(CHINA).strftime("%H%M")
        if not "1500" <= minute <= "1510":
            continue
        if not re.fullmatch(
            r"T[0-9]*|NORMAL|TRADING", str(r.get("tradeStatus") or "").upper()
        ):
            continue
        down, bid = float(r["downPrice"]), float(r["buyVol1"])
        if math.isfinite(down) and down > 0 and math.isfinite(bid) and bid >= 0:
            return {
                "down": down,
                "bid_shares": bid if minute == "1500" else None,
                "quote_at": timestamp.isoformat(),
            }
    return None
