from datetime import datetime, timezone

import pytest

from xiaocao.live.buy_guards import evaluate_buy_market_guard


@pytest.mark.parametrize("status,allowed", [("T", True), ("T000", True), ("T12", True),
                                             ("Tbad", False), ("X000", False)])
def test_proprietary_trading_family_matches_live(status, allowed):
    now = datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc)
    result = evaluate_buy_market_guard({
        "market_guard_required": True, "market_guard_status": status,
        "market_observed_at": now.isoformat(), "date": "2026-09-07",
        "latest_price": 10, "down_price": 9,
    }, now=now)
    assert result[0] is allowed
