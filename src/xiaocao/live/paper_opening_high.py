"""Prove the opening minute's HIGH with native cumulative quote bounds.

This is not the maximum of sampled last prices. Equal cumulative HIGHs before
and after the boundary bound every intervening trade; an in-minute witness
excludes an auction-only maximum. No account, order or ledger writes live here.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from xiaocao.api.errors import ApiAuthError

CHINA = ZoneInfo("Asia/Shanghai")
QUOTE_SOURCE = "xiaocao_api/stock/second_line_detail_info"


def _read_error(exc: Exception) -> str:
    return "API_AUTHENTICATION_FAILED_990502" if isinstance(exc, ApiAuthError) else type(exc).__name__


def _number(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("FIRST_MINUTE_QUOTE_NUMBER_INVALID")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("FIRST_MINUTE_QUOTE_NUMBER_INVALID") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError("FIRST_MINUTE_QUOTE_NUMBER_INVALID")
    return number


def _clock(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("FIRST_MINUTE_QUOTE_CLOCK_INVALID")
    return parsed.astimezone(CHINA)


def _source_clock(row: dict, trade_date: str) -> datetime:
    raw = row.get("tradeTimestamp")
    try:
        clock = datetime.strptime(str(raw), "%H:%M:%S:%f").time()
    except ValueError as exc:
        raise ValueError("FIRST_MINUTE_QUOTE_CLOCK_INVALID") from exc
    return datetime.combine(datetime.fromisoformat(trade_date).date(), clock, CHINA)


def prove_cumulative_high(proof: dict, *, code: str, trade_date: str,
                          now: datetime, bar: dict) -> tuple[float, str]:
    """Return an exact interval HIGH and hash, or raise a precise evidence gap."""
    try:
        encoded = json.dumps(proof, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        raise ValueError("FIRST_MINUTE_QUOTE_INVALID_JSON") from exc
    if not re.fullmatch(r"\d{6}\.(XSHG|XSHE|BJSE)", code):
        raise ValueError("FIRST_MINUTE_INSTRUMENT_UNPROVEN")
    if proof.get("source") != QUOTE_SOURCE or code not in str(
        (proof.get("request") or {}).get("codes", "")
    ).split(","):
        raise ValueError("FIRST_MINUTE_QUOTE_SOURCE_MISMATCH")
    if "API_AUTHENTICATION_FAILED_990502" in proof.get("errors", []):
        raise ValueError("FIRST_MINUTE_API_AUTHENTICATION_FAILED_990502")
    start = datetime.fromisoformat(trade_date).replace(hour=9, minute=30, tzinfo=CHINA)
    boundary = start + timedelta(minutes=1)
    observations = proof.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("FIRST_MINUTE_QUOTE_BRACKET_MISSING")
    before, after = [], []
    previous = None
    for observation in observations:
        if not isinstance(observation, dict) or not isinstance(observation.get("raw_quote"), dict):
            raise ValueError("FIRST_MINUTE_QUOTE_PROOF_INVALID")
        row = observation["raw_quote"]
        if row.get("code") != code or str(row.get("tradeDate")) != trade_date.replace("-", ""):
            raise ValueError("FIRST_MINUTE_QUOTE_IDENTITY_MISMATCH")
        received = _clock(observation["observed_at"])
        source_time = _source_clock(row, trade_date)
        if received.date() != start.date() or received > now or not 0 <= (received - source_time).total_seconds() <= 10:
            raise ValueError("FIRST_MINUTE_QUOTE_STALE_OR_FUTURE")
        op, high, low, last, volume, amount = (
            _number(row.get(key)) for key in ("open", "high", "low", "trade", "vol", "amt"))
        if not low <= min(op, last) <= max(op, last) <= high or op != _number(bar["open"]):
            raise ValueError("FIRST_MINUTE_QUOTE_PRICE_CONFLICT")
        if previous and (source_time < previous[0] or high < previous[1]
                         or volume < previous[2] or amount < previous[3]):
            raise ValueError("FIRST_MINUTE_QUOTE_SESSION_CONFLICT")
        previous = source_time, high, volume, amount
        if start <= source_time <= received < boundary:
            before.append((high, op))
        elif received >= boundary and source_time >= boundary:
            after.append((high, op))
        else:
            raise ValueError("FIRST_MINUTE_QUOTE_OUTSIDE_BRACKET")
    if not before or len(after) != 1:
        raise ValueError("FIRST_MINUTE_QUOTE_BRACKET_MISSING")
    high, op = after[0]
    if before[-1][0] != high:
        raise ValueError("FIRST_MINUTE_HIGH_CHANGED_ACROSS_BOUNDARY")
    if high != _number(bar["high"]):
        raise ValueError("FIRST_MINUTE_HIGH_SOURCE_CONFLICT")
    if high == op:
        # Quote.trade can still be a cached auction last. A positive-volume
        # aggregate ending inside the continuous minute proves a real print.
        request = proof.get("trade_witness_request") or {}
        if request != {"code": code, "codeType": 0, "isLess": 0, "count": 5000}:
            raise ValueError("FIRST_MINUTE_TRADE_WITNESS_SOURCE_UNPROVEN")
        witness_received = _clock(proof["trade_witness_observed_at"])
        if not boundary <= witness_received <= now:
            raise ValueError("FIRST_MINUTE_TRADE_WITNESS_CLOCK_INVALID")
        witnessed = False
        for row in proof.get("trade_witness_rows", []):
            if row.get("code") != code or str(row.get("tradeDate")) != trade_date.replace("-", ""):
                continue
            clock = str(row.get("tradeTime", ""))
            if not re.fullmatch(r"\d{6}", clock) or not "093000" <= clock < "093100":
                continue
            stamp = datetime.fromtimestamp(_number(row.get("timestamp")) / 1000, CHINA)
            if stamp.date() != start.date() or stamp.strftime("%H%M%S") != clock:
                continue
            if _number(row.get("oneVol")) > 0 and _number(row.get("oneAmt")) > 0 and _number(row.get("trade")) == high:
                witnessed = True
        if not witnessed:
            raise ValueError("FIRST_MINUTE_AUCTION_ONLY_HIGH_UNPROVEN")
    return high, hashlib.sha256(encoded).hexdigest()


def capture_opening_high(client: object, codes: list[str], trade_date: str, *,
                         now: Callable[[], datetime] | None = None,
                         sleep: Callable[[float], None] = time.sleep) -> dict[str, dict]:
    """Original-process, bounded reads while no paper ledger lock is held.

    Late starts cannot recover a missed pre-boundary observation. The caller
    preserves the resulting explicit gap, rather than reconstructing history.
    """
    now = now or (lambda: datetime.now(CHINA))
    codes = sorted(set(codes))
    if not codes or now().date().isoformat() != trade_date:
        return {}
    start = datetime.fromisoformat(trade_date).replace(hour=9, minute=30, second=50, tzinfo=CHINA)
    boundary = start.replace(minute=31, second=0)
    post_deadline = boundary + timedelta(seconds=10)
    request = {"codes": ",".join(codes)}
    proofs = {code: {"source": QUOTE_SOURCE, "request": request,
                     "observations": [], "errors": []} for code in codes}
    if now() >= boundary:
        for proof in proofs.values():
            proof["errors"].append("FIRST_MINUTE_PRE_CAPTURE_MISSED")
        return proofs

    def wait_until(target: datetime) -> None:
        while now() < target:
            sleep(min(2, (target - now()).total_seconds()))

    def read_quotes(active_codes: list[str]) -> None:
        try:
            payload = client.second_line_detail_info(request["codes"])
            received = now().isoformat()
            for code in active_codes:
                row = payload.get(code) if isinstance(payload, dict) else None
                if not isinstance(row, dict):
                    proofs[code]["errors"].append("FIRST_MINUTE_QUOTE_MISSING")
                else:
                    proofs[code]["observations"].append({"observed_at": received, "raw_quote": row})
        except Exception as exc:
            for code in active_codes:
                proofs[code]["errors"].append(_read_error(exc))

    wait_until(start)
    while now() < boundary:
        read_quotes(codes)
        remaining = (boundary - now()).total_seconds()
        if remaining > 0:
            sleep(min(1, remaining))
    pending = set(codes)
    while pending and now() < post_deadline:
        read_quotes(sorted(pending))
        for code in list(pending):
            observations = proofs[code]["observations"]
            if observations:
                try:
                    source_time = _source_clock(observations[-1]["raw_quote"], trade_date)
                    if boundary <= source_time <= _clock(observations[-1]["observed_at"]):
                        pending.remove(code)
                except ValueError:
                    pass
        if pending and now() < post_deadline:
            sleep(min(1, (post_deadline - now()).total_seconds()))
    for code in codes:
        observations = proofs[code]["observations"]
        # Preserve only genuinely received in-minute observations and the final
        # read. A request crossing 09:31 is audit evidence, never a pre witness.
        pre = [q for q in observations if _clock(q["observed_at"]) < boundary]
        post = []
        for observation in observations[len(pre):]:
            try:
                if _source_clock(observation["raw_quote"], trade_date) >= boundary:
                    post.append(observation)
            except ValueError:
                pass
        proofs[code]["observations"] = pre + post[:1]
        proofs[code]["discarded_boundary_reads"] = [q for q in observations if
            q not in proofs[code]["observations"]]
        if observations and observations[-1]["raw_quote"].get("high") == observations[-1]["raw_quote"].get("open"):
            try:
                proofs[code]["trade_witness_rows"] = client.post(
                    "/stock/each_trade", {"code": code, "codeType": 0, "isLess": 0, "count": 5000})
                proofs[code]["trade_witness_request"] = {"code": code, "codeType": 0, "isLess": 0, "count": 5000}
                proofs[code]["trade_witness_observed_at"] = now().isoformat()
            except Exception as exc:
                proofs[code]["errors"].append(_read_error(exc))
    return proofs
