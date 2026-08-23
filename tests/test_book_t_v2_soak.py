from __future__ import annotations

import pytest

from scripts.book_t_v2_soak import evaluate_engineering_burn_in


def test_twenty_day_burn_in_stays_pending_without_real_inputs() -> None:
    result = evaluate_engineering_burn_in([])

    assert result["status"] == "pending"
    assert result["required_real_trading_days"] == 20
    assert result["real_trading_days"] == 0
    assert result["rehearsal_days_excluded"] == 0
    assert result["strategy_promotion_authorized"] is False


def test_engineering_burn_in_floor_cannot_be_lowered_below_twenty_days() -> None:
    with pytest.raises(ValueError, match="below twenty"):
        evaluate_engineering_burn_in([], required_days=19)
