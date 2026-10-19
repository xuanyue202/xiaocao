"""Freshness of capture inputs; independent of exchange quote timestamp rules."""
from datetime import datetime, timezone
from typing import Mapping


class CaptureInputsExpired(ValueError):
    pass


def observation_current(record: Mapping, *, now: datetime | None = None) -> bool:
    try:
        observed = datetime.fromisoformat(record["observed_at"])
        current = now or datetime.now(timezone.utc)
        return (observed.tzinfo is not None and current.tzinfo is not None
                and 0 <= (current - observed).total_seconds() <= 60)
    except (KeyError, TypeError, ValueError):
        return False


def require_capture_inputs(readiness: dict, *, now: datetime | None = None, required_codes=None) -> None:
    sources = readiness.get("sources") or []
    if not sources or any(r.get("status") not in {"populated", "empty_confirmed"}
                          or not observation_current(r, now=now) for r in sources):
        raise CaptureInputsExpired("MORNING_CAPTURE_SOURCES_EXPIRED_OR_UNPROVED")
    prices = readiness.get("price_enrichment") or {}
    if (prices.get("status") != "complete" or prices.get("unpriced_codes")
            or not observation_current(prices, now=now)):
        raise CaptureInputsExpired("MORNING_CAPTURE_PRICES_EXPIRED_OR_UNPROVED")
    # Individual prices can precede the final price probe by many slow reads.
    observations = prices.get("observations", [])
    if required_codes and set(required_codes) - {str(r.get("code") or "") for r in observations}:
        raise CaptureInputsExpired("MORNING_CAPTURE_PRICE_COVERAGE_UNPROVED")
    for record in observations:
        if not observation_current(record, now=now):
            raise CaptureInputsExpired("MORNING_CAPTURE_PRICE_EXPIRED_OR_UNPROVED")
