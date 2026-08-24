"""Shared deterministic Book B entry-price rules."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def initial_limit_price(
    open_price: float | int | None,
    basket_price: float | int | None,
    *,
    premium_pct: float = 0.5,
    tick_size: float | None = None,
) -> float | None:
    """Return the shared Book B limit, optionally floored to a price tick."""
    try:
        opening = Decimal(str(open_price)) if open_price not in (None, "") else None
        basket = Decimal(str(basket_price)) if basket_price not in (None, "") else None
        premium = Decimal(str(premium_pct))
        tick = Decimal(str(tick_size)) if tick_size is not None else None
    except (InvalidOperation, TypeError, ValueError):
        return None
    if opening is None or opening <= 0 or (tick is not None and tick <= 0):
        return None
    limit = opening * (Decimal("1") + premium / Decimal("100"))
    if basket is not None and basket > 0:
        limit = min(limit, basket)
    if tick is not None:
        limit = (limit / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    if limit <= 0:
        return None
    return round(float(limit), 6)


__all__ = ["initial_limit_price"]
