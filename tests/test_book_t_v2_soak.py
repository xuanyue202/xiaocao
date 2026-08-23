from __future__ import annotations

from scripts.book_t_v2_soak import evaluate_five_day_soak


def test_five_day_soak_stays_pending_without_real_inputs() -> None:
    result = evaluate_five_day_soak([])

    assert result["status"] == "pending"
    assert result["real_trading_days"] == 0
    assert result["rehearsal_days_excluded"] == 0
    assert result["strategy_promotion_authorized"] is False
