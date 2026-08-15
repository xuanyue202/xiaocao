"""Shared deterministic Book B entry-price rules."""
from __future__ import annotations


def initial_limit_price(
    open_price: float | int | None,
    basket_price: float | int | None,
    *,
    premium_pct: float = 0.5,
) -> float | None:
    """Return the one Book B initial limit rule, or ``None`` if unpriced."""
    try:
        opening = float(open_price) if open_price not in (None, "") else None
        basket = float(basket_price) if basket_price not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if opening is None or opening <= 0:
        return None
    limit = opening * (1.0 + float(premium_pct) / 100.0)
    if basket is not None and basket > 0:
        limit = min(limit, basket)
    return round(limit, 6)


__all__ = ["initial_limit_price"]
