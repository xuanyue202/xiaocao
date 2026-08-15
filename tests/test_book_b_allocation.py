from __future__ import annotations

import pytest

from xiaocao.live.book_b_allocation import (
    BookBAllocationFacts,
    allocate_frozen_rows,
    validate_allocation_rows,
)


def _candidate(code: str, mode: str, price: float = 10.0) -> dict:
    return {
        "code": code,
        "name": code,
        "mode": mode,
        "mode_state": "ACTIVE",
        "mode_exec_star": True,
        "mode_trade_eligible": True,
        "mode_exec_target_weight": 0.5,
        "open": price,
        "basket_price": price * 1.01,
    }


def test_allocator_materializes_board_lots_and_proof() -> None:
    facts = BookBAllocationFacts(settled_nav=30_000, available_cash=30_000)
    planned = allocate_frozen_rows(
        [_candidate("000001.XSHE", "m1"), _candidate("000002.XSHE", "m2", 20.0)],
        facts,
    )
    assert 1 <= len(planned) <= 2
    assert all(int(row["mode_exec_planned_shares"]) % 100 == 0 for row in planned)
    assert all(row["allocation_proof_hash"] == facts.proof_hash(planned) for row in planned)
    total, proof = validate_allocation_rows(planned, facts)
    assert total > 0
    assert proof == planned[0]["allocation_proof_hash"]


def test_allocation_rejects_batch_exposure_and_tampered_proof() -> None:
    facts = BookBAllocationFacts(settled_nav=30_000, available_cash=30_000)
    oversized = _candidate("000001.XSHE", "m1")
    oversized["mode_exec_planned_shares"] = 2_000
    with pytest.raises(ValueError, match="ALLOCATION_BATCH_LIMIT"):
        validate_allocation_rows([oversized], facts)

    valid = _candidate("000001.XSHE", "m1")
    valid["mode_exec_planned_shares"] = 100
    valid["allocation_proof_hash"] = "forged"
    with pytest.raises(ValueError, match="ALLOCATION_PROOF_MISMATCH"):
        validate_allocation_rows([valid], facts)


def test_rolling_nav_and_cash_are_not_replaced_by_initial_default() -> None:
    facts = BookBAllocationFacts(
        settled_nav=20_000,
        available_cash=8_000,
        current_open_exposure=19_000,
    )
    row = _candidate("000001.XSHE", "m1")
    row["mode_exec_planned_shares"] = 100
    with pytest.raises(ValueError, match="ALLOCATION_TOTAL_EXPOSURE_LIMIT"):
        validate_allocation_rows([row], facts)
