"""Conservative Paper-B cost, independent of APP order/fill authority.

User decision, 2026-10-26 (Operating Contract §5): test profitability with
the verified first-minute HIGH. This deliberately charges an adverse cost;
it is not an error/slippage to optimise away. The 2026-06-20 VWAP change
confused a conservative benchmark with an unproved average execution model.
Changing this purpose requires a new explicit user decision, not better PnL.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo


CONSERVATIVE_COST_BASIS = "verified_first_minute_high_cost_v1"
CHINA_TZ = ZoneInfo("Asia/Shanghai")


def _positive(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def verified_first_minute_high(
    window: dict | None,
    *,
    code: str,
    trade_date: str,
    start_hhmm: str,
    end_hhmm: str,
    observed_at: datetime,
) -> tuple[float | None, dict]:
    """Retain candidate evidence, but never certify an unproved source interval.

    A 09:31 label and plausible OHLC cannot establish whether a provider labels
    the start or end of a minute. The current minute_line source is a point
    series; its first-minute HIGH contract has NOT been established. Even a
    structurally valid response therefore remains unproven. See
    docs/reviews/2026-10-26-paper-first-minute-source.md for the provider probes
    needed before implementing an accepting source adapter. No runtime flag or
    payload assertion may bypass that missing contract.
    """
    evidence = {
        "schema_version": "paper-first-minute-high.v1",
        "source": "xiaocao_api/stock/minute_line",
        "request": {"code": code, "tradeDate": trade_date, "freq": "1min", "adj": "bfq"},
        "observed_at": observed_at.isoformat(),
        "status": "unproven",
        "source_interval_status": "unproven",
    }

    def reject(reason: str) -> tuple[None, dict]:
        return None, {**evidence, "reason": reason}

    if (start_hhmm, end_hhmm) != ("0930", "0931"):
        return reject("FIRST_MINUTE_WINDOW_REQUIRED")
    end = datetime.fromisoformat(trade_date).replace(hour=9, minute=32, second=5, tzinfo=CHINA_TZ)
    if observed_at.tzinfo is None or observed_at < end:
        return reject("FIRST_MINUTE_NOT_FINAL")
    if not window or window.get("source") != "xiaocao_api":
        return reject("FIRST_MINUTE_SOURCE_UNPROVEN")
    raw = window.get("raw_minute_rows")
    if not isinstance(raw, list):
        return reject("FIRST_MINUTE_RAW_BAR_MISSING")
    bars = [r for r in raw if isinstance(r, dict) and str(r.get("tradeTime")) == "0931"]
    if len(bars) != 1:
        return reject("FIRST_MINUTE_BAR_NOT_UNIQUE")
    bar = bars[0]
    try:
        encoded = json.dumps(bar, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        return reject("FIRST_MINUTE_BAR_INVALID_JSON")
    evidence.update({"raw_bar": bar, "raw_bar_sha256": hashlib.sha256(encoded.encode()).hexdigest()})
    if bar.get("code") != code or str(bar.get("tradeDate")) != trade_date.replace("-", ""):
        return reject("FIRST_MINUTE_IDENTITY_MISMATCH")
    if bar.get("freq") != "1min" or type(bar.get("tradeMinutes")) is not int or bar["tradeMinutes"] != 1:
        return reject("FIRST_MINUTE_INTERVAL_UNPROVEN")
    op, hi, lo, close, volume = [_positive(bar.get(k)) for k in ("open", "high", "low", "close", "vol")]
    if any(v is None for v in (op, hi, lo, close, volume)):
        return reject("FIRST_MINUTE_OHLCV_MISSING")
    if not lo <= min(op, close) <= max(op, close) <= hi:
        return reject("FIRST_MINUTE_OHLC_INCONSISTENT")
    if bar.get("trade") is not None:
        last = _positive(bar["trade"])
        if last is None or not lo <= last <= hi:
            return reject("FIRST_MINUTE_TRADE_INCONSISTENT")
    # Do not turn synthetic test OHLC or future non-null fields into authority.
    # The provider's actual full interval/finality semantics need proof first.
    return reject("FIRST_MINUTE_SOURCE_INTERVAL_UNPROVEN")
