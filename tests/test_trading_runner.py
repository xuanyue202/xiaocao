from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from xiaocao.live.trading_runner import (
    plans_from_frozen_rows,
    read_frozen_rows,
)
from xiaocao.live.book_b_allocation import BookBAllocationFacts


def _row(code: str = "000001.XSHE") -> dict:
    return {
        "date": "2026-08-15",
        "book": "B",
        "is_live": True,
        "mode_exec_star": True,
        "mode_trade_eligible": True,
        "mode_state": "ACTIVE",
        "mode": "mode-a",
        "mode_exec_target_weight": 0.5,
        "code": code,
        "name": "测试标的",
        "open": 10.0,
        "basket_price": 10.10,
        "mode_exec_planned_shares": 200,
        "market_guard_status": "ok",
    }


def test_read_frozen_rows_is_date_scoped_and_does_not_drop_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "freeze.jsonl"
    path.write_text(
        json.dumps(_row(), ensure_ascii=False)
        + "\n"
        + json.dumps({**_row("000002.XSHE"), "date": "2026-08-14"})
        + "\n",
        encoding="utf-8",
    )
    assert [row["code"] for row in read_frozen_rows(path, date="2026-08-15")] == ["000001.XSHE"]
    path.write_text("{}\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        read_frozen_rows(path)


def test_plans_are_materialized_before_execution_and_duplicate_ids_fail() -> None:
    plans = plans_from_frozen_rows(
        [_row()],
        environment="mock",
        logical_account_id="primary",
        now=datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc),
        allocation=BookBAllocationFacts(settled_nav=30000, available_cash=30000),
    )
    assert len(plans) == 1
    assert plans[0].limit_price == 10.05
    with pytest.raises(ValueError, match="ALLOCATION_MODE_DUPLICATE"):
        plans_from_frozen_rows(
            [_row(), _row()],
            environment="mock",
            logical_account_id="primary",
            allocation=BookBAllocationFacts(settled_nav=30000, available_cash=30000),
        )


def test_runner_rejects_non_book_b_or_non_star_rows() -> None:
    with pytest.raises(ValueError, match="not Book B"):
        plans_from_frozen_rows(
            [dict(_row(), book="A")],
            environment="mock",
            logical_account_id="primary",
            allocation=BookBAllocationFacts(settled_nav=30000, available_cash=30000),
        )
    with pytest.raises(ValueError, match="not ★E"):
        plans_from_frozen_rows(
            [dict(_row(), mode_exec_star=False)],
            environment="mock",
            logical_account_id="primary",
            allocation=BookBAllocationFacts(settled_nav=30000, available_cash=30000),
        )


def test_runner_requires_allocation_proof_and_caps_arbitrary_shares() -> None:
    with pytest.raises(ValueError, match="ALLOCATION_PROOF_MISSING"):
        plans_from_frozen_rows(
            [_row()],
            environment="mock",
            logical_account_id="primary",
        )
    with pytest.raises(ValueError, match="ALLOCATION_BATCH_LIMIT"):
        plans_from_frozen_rows(
            [dict(_row(), mode_exec_planned_shares=2_000)],
            environment="mock",
            logical_account_id="primary",
            allocation=BookBAllocationFacts(settled_nav=30_000, available_cash=30_000),
        )


def test_runner_sell_requires_authorized_owned_lot_and_tz_timestamp() -> None:
    sell = {
        "date": "2026-08-15",
        "book": "B",
        "code": "000001.XSHE",
        "name": "测试标的",
        "shares": 100,
        "limit_price": 10.0,
        "owned_lot_id": "book-b:000001:2026-08-14",
        "sell_authorized": True,
        "sell_reason": "HARD_STOP",
        "decision_phase": "risk_floor",
        "decision_at": "2026-08-15T01:01:00+00:00",
    }
    plans = plans_from_frozen_rows(
        [sell], environment="mock", logical_account_id="primary", side="SELL"
    )
    assert plans[0].sell_reason == "HARD_STOP"
    with pytest.raises(ValueError, match="SELL_T1_BLOCKED"):
        plans_from_frozen_rows(
            [dict(sell, t1_blocked=True)],
            environment="mock", logical_account_id="primary", side="SELL"
        )
