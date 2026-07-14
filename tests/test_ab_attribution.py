from __future__ import annotations

import pytest

from xiaocao.live.ab_attribution import paired_exit_attribution


def _position(book, *, code="X", day="2026-07-10", shares=100, entry=10.0, pnl=0.0, status="closed"):
    return {
        "book": book, "code": code, "entry_date": day, "shares": shares,
        "entry_price": entry, "entry_cash_out": entry * shares,
        "status": status, "realized_pnl": pnl,
    }


def test_paired_exit_edge_uses_same_cohort_normalized_returns() -> None:
    result = paired_exit_attribution([
        _position("A", pnl=100.0),
        _position("B", pnl=50.0),
    ])

    assert result["eligible_pairs"] == 1
    assert result["mean_a_return_pct"] == pytest.approx(10.0)
    assert result["mean_b_return_pct"] == pytest.approx(5.0)
    assert result["mean_b_minus_a_pp"] == pytest.approx(-5.0)
    assert result["b_better_pairs"] == 0


def test_pairing_excludes_share_price_and_open_cohort_drift() -> None:
    result = paired_exit_attribution([
        _position("A", code="SHARES", shares=100),
        _position("B", code="SHARES", shares=200),
        _position("A", code="PRICE", entry=10.0),
        _position("B", code="PRICE", entry=10.1),
        _position("A", code="OPEN", status="open"),
        _position("B", code="OPEN", status="closed"),
        _position("B", code="ONLY_B"),
    ])

    assert result["eligible_pairs"] == 0
    assert result["mean_b_minus_a_pp"] is None
    assert result["excluded"] == {
        "entry_price_mismatch": 1,
        "missing_book_a": 1,
        "not_both_closed": 1,
        "shares_mismatch": 1,
    }
