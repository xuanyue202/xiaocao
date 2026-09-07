from __future__ import annotations

import fcntl
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.live.book_b_live_lifecycle import (
    BookBLiveAccountState,
    BookBLiveOwnedLot,
    load_latest_book_b_live_settlement,
    open_execution_plan_ids,
    project_book_b_live_account,
    write_book_b_live_settlement,
)
from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
from xiaocao.live.book_b_live_morning import load_book_b_live_capital_basis
from xiaocao.live.trading_execution import (
    BookBOwnershipEvidence,
    ExecutionReceipt,
    ExecutionStore,
    ExecutionState,
    TradePlan,
)
from xiaocao.live.trading_runner import frozen_rows_digest


NOW = datetime(2026, 9, 1, 6, 56, tzinfo=timezone.utc)
EOD_NOW = NOW + timedelta(minutes=4)


def _canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _snapshot(
    *,
    shares: int = 0,
    sellable: int = 0,
    price: float = 11.0,
    observed_at: datetime = NOW,
    broker_fills: tuple[tuple[str, str, str, int, float], ...] = (),
) -> dict:
    positions = []
    if shares:
        positions.append(
            {
                "证券代码": "000001",
                "证券名称": "测试标的",
                "证券数量": str(shares),
                "可卖数量": str(sellable),
                "参考成本价": "10.0000",
                "当前价": str(price),
                "最新市值": str(round(shares * price, 2)),
            }
        )
    securities_value = round(shares * price, 2)
    total_assets = 100_000.0
    cash_balance = round(total_assets - securities_value, 2)
    order_rows = [
        {
            "证券代码": code.split(".", 1)[0],
            "证券名称": "测试标的",
            "买卖标志": "买入" if side == "BUY" else "卖出",
            "委托价格": str(fill_price),
            "委托数量": str(quantity),
            "委托编号": order_id,
            "成交价格": str(fill_price),
            "成交数量": str(quantity),
            "状态说明": "已成",
        }
        for order_id, code, side, quantity, fill_price in broker_fills
    ]
    trade_rows = [
        {
            "证券代码": code.split(".", 1)[0],
            "证券名称": "测试标的",
            "买卖标志": "买入" if side == "BUY" else "卖出",
            "成交价格": str(fill_price),
            "成交数量": str(quantity),
            "成交类型": "成交",
            "成交编号": f"trade-{order_id}",
            "委托编号": order_id,
        }
        for order_id, code, side, quantity, fill_price in broker_fills
    ]
    rows_by_kind = {
        "positions": positions,
        "today-orders": order_rows,
        "today-trades": trade_rows,
    }
    tables = {
        kind: {
            "kind": kind,
            "rows": rows_by_kind[kind],
            "row_count": len(rows_by_kind[kind]),
            "observed_at": observed_at.isoformat(),
        }
        for kind in ("positions", "today-orders", "today-trades")
    }
    body = {
        "schema_version": 1,
        "status": "account_snapshot_reconciled",
        "trade_date": "2026-09-01",
        "environment": "live",
        "logical_account_id": "primary",
        "account_binding": "proven",
        "fund_account_binding_sha256": "a" * 64,
        "source": "foundersc_native_app",
        "observed_at": observed_at.isoformat(),
        "broker_summary": {
            "total_assets": total_assets,
            "securities_market_value": securities_value,
            "available_cash": cash_balance,
            "cash_balance": cash_balance,
            "withdrawable_cash": cash_balance,
            "asset_equation_cash_field": "cash_balance",
        },
        "funds_summary": {
            "source": "positions_summary",
            "total_assets": total_assets,
            "securities_market_value": securities_value,
            "available_cash": cash_balance,
            "cash_balance": cash_balance,
            "withdrawable_cash": cash_balance,
            "asset_equation_cash_field": "cash_balance",
        },
        "tables": tables,
    }
    body["snapshot_sha256"] = _canonical_sha256(body)
    return body


def _plan(
    *,
    side: str = "BUY",
    lot_id: str | None = None,
    trade_date: str = "2026-09-01",
) -> TradePlan:
    return TradePlan(
        plan_id=(
            f"book-b:{trade_date}:000001.XSHE:BUY"
            if side == "BUY"
            else f"book-b:{trade_date}:000001.XSHE:SELL:lot1"
        ),
        strategy_run_id="test-run",
        snapshot_ref="freeze#1",
        strategy_sha="a" * 40,
        trade_date=trade_date,
        book="B",
        logical_account_id="primary",
        environment="live",
        code="000001.XSHE",
        name="测试标的",
        side=side,
        shares=100,
        limit_price=10.0 if side == "BUY" else 11.0,
        basket_price=10.1 if side == "BUY" else None,
        market_guard_status="ok",
        created_at=NOW - timedelta(hours=5),
        recovery_deadline=NOW + timedelta(minutes=1),
        owned_lot_id=lot_id,
        allocation_proof_hash="proof" if side == "BUY" else None,
        sell_authorized=side == "SELL",
        sell_reason="HARD_STOP" if side == "SELL" else None,
        sell_decision_phase="risk_floor" if side == "SELL" else None,
        sell_decision_at=NOW if side == "SELL" else None,
    )


def _bind_plan_intent(state_dir: Path, plan: TradePlan) -> TradePlan:
    if plan.side == "BUY":
        freeze_path = state_dir / f"book_b_live_freeze_{plan.trade_date}.jsonl"
        rows = [
            {
                "book": "B",
                "code": plan.code,
                "name": plan.name,
                "profile": "v6",
                "mode": "接力",
            }
        ]
        freeze_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        plan = replace(
            plan,
            snapshot_ref=(
                f"{freeze_path}:{plan.trade_date}:"
                f"sha256:{frozen_rows_digest(rows)}:{plan.code}"
            ),
        )
    _write_intent(state_dir, plan)
    return plan


def _record_fill(
    state_dir: Path,
    plan: TradePlan,
    *,
    price: float,
    event_id: str,
) -> TradePlan:
    plan = _bind_plan_intent(state_dir, plan)
    receipt = ExecutionReceipt(
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        state=ExecutionState.FILLED,
        filled_shares=plan.shares,
        remaining_shares=0,
        broker_order_id=f"order-{event_id}",
        fill_price=price,
        event_id=event_id,
    )
    persisted = ExecutionStore(state_dir / "events.jsonl").append(
        plan=plan,
        receipt=receipt,
        kind="broker_receipt",
    )
    BookBOwnershipEvidence(
        state_dir / "book_b_ownership_evidence.jsonl"
    ).record(plan, persisted)
    return plan


def _write_intent(state_dir: Path, plan: TradePlan) -> None:
    payload = {
        "schema_version": 1,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "plan": plan.canonical_payload(),
    }
    path = state_dir / "plan_intents" / f"{hashlib.sha256(plan.plan_id.encode()).hexdigest()[:24]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_project_empty_live_subaccount_keeps_initial_capital(tmp_path: Path) -> None:
    account = project_book_b_live_account(
        tmp_path, _snapshot(), trade_date="2026-09-01", now=NOW
    )

    assert account.cash == 30_000
    assert account.settled_nav == 30_000
    assert account.current_open_exposure == 0
    assert account.lots == ()


def test_project_accepts_hash_bound_same_day_sell_cash_equation(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(
        broker_fills=(("sell-order", "000001.XSHE", "SELL", 100, 10.0),)
    )
    snapshot.pop("snapshot_sha256")
    for summary_key in ("broker_summary", "funds_summary"):
        snapshot[summary_key].update(
            {
                "available_cash": 100_000.0,
                "cash_balance": 90_000.0,
                "withdrawable_cash": 90_000.0,
                "asset_equation_cash_field": "available_cash",
            }
        )
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)

    account = project_book_b_live_account(
        tmp_path, snapshot, trade_date="2026-09-01", now=NOW
    )

    assert account.cash == 30_000
    assert account.settled_nav == 30_000


def test_project_rejects_available_cash_equation_without_same_day_sell(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    snapshot.pop("snapshot_sha256")
    for summary_key in ("broker_summary", "funds_summary"):
        snapshot[summary_key].update(
            {
                "available_cash": 100_000.0,
                "cash_balance": 90_000.0,
                "withdrawable_cash": 90_000.0,
                "asset_equation_cash_field": "available_cash",
            }
        )
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)

    with pytest.raises(ValueError, match="BROKER_FUNDS_EQUATION_FAILED"):
        project_book_b_live_account(
            tmp_path, snapshot, trade_date="2026-09-01", now=NOW
        )


def test_project_accepts_hash_bound_same_day_buy_cash_equation(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(
        shares=100,
        sellable=0,
        broker_fills=(("buy-order", "000001.XSHE", "BUY", 100, 10.0),),
    )
    snapshot.pop("snapshot_sha256")
    for summary_key in ("broker_summary", "funds_summary"):
        snapshot[summary_key].update(
            {
                "available_cash": 98_900.0,
                "cash_balance": 98_905.0,
                "withdrawable_cash": 98_900.0,
                "asset_equation_cash_field": "available_cash",
            }
        )
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)

    account = project_book_b_live_account(
        tmp_path, snapshot, trade_date="2026-09-01", now=NOW
    )

    assert account.cash == 30_000
    assert account.settled_nav == 30_000


def test_project_rejects_buy_shaped_available_cash_without_same_day_buy(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(shares=100, sellable=0)
    snapshot.pop("snapshot_sha256")
    for summary_key in ("broker_summary", "funds_summary"):
        snapshot[summary_key].update(
            {
                "available_cash": 98_900.0,
                "cash_balance": 98_905.0,
                "withdrawable_cash": 98_900.0,
                "asset_equation_cash_field": "available_cash",
            }
        )
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)

    with pytest.raises(ValueError, match="BROKER_FUNDS_EQUATION_FAILED"):
        project_book_b_live_account(
            tmp_path, snapshot, trade_date="2026-09-01", now=NOW
        )


def test_project_owned_buy_uses_broker_mark_but_not_mixed_account_cash(
    tmp_path: Path,
) -> None:
    buy = _plan()
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=100,
            sellable=100,
            price=11.0,
            broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),),
        ),
        trade_date="2026-09-01",
        now=NOW,
        monitor_context_by_lot={buy.plan_id: {"profile": "v6", "mode": "接力"}},
    )

    assert account.cash == 28_999.9
    assert account.current_open_exposure == 1_100
    assert account.liquidation_value_after_fee == 1_099.89
    assert account.settled_nav == 30_099.79
    assert account.lots[0].owned_lot_id == buy.plan_id
    assert account.lots[0].sellable_shares == 0
    assert account.lots[0].monitor_context == {"profile": "v6", "mode": "接力"}


def test_project_uses_authoritative_fill_notional_not_rounded_fill_price(
    tmp_path: Path,
) -> None:
    _record_fill(tmp_path, _plan(), price=10.0, event_id="buy-fill")
    ownership_path = tmp_path / "book_b_ownership_evidence.jsonl"
    event = json.loads(ownership_path.read_text(encoding="utf-8"))
    event["fill_price"] = 9.99
    unsigned = dict(event)
    unsigned.pop("event_hash")
    event["event_hash"] = _canonical_sha256(unsigned)
    ownership_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=100,
            sellable=100,
            price=10.0,
            broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),),
        ),
        trade_date="2026-09-01",
        now=NOW,
    )

    assert account.cash == 28_999.9
    assert account.lots[0].entry_price == 10.0


def test_project_rejects_fractional_hash_valid_owned_shares(tmp_path: Path) -> None:
    _record_fill(tmp_path, _plan(), price=10.0, event_id="buy-fill")
    ownership_path = tmp_path / "book_b_ownership_evidence.jsonl"
    event = json.loads(ownership_path.read_text(encoding="utf-8"))
    event["shares"] = 99.5
    unsigned = dict(event)
    unsigned.pop("event_hash")
    event["event_hash"] = _canonical_sha256(unsigned)
    ownership_path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="OWNERSHIP_SHARES_INVALID"):
        project_book_b_live_account(
            tmp_path,
            _snapshot(
                shares=100,
                sellable=100,
                price=10.0,
                broker_fills=(
                    ("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),
                ),
            ),
            trade_date="2026-09-01",
            now=NOW,
        )


def test_project_rejects_same_day_owned_fill_missing_from_broker_rows(
    tmp_path: Path,
) -> None:
    _record_fill(tmp_path, _plan(), price=10.0, event_id="buy-fill")

    with pytest.raises(ValueError, match="BROKER_ORDER_FILL_UNPROVEN"):
        project_book_b_live_account(
            tmp_path,
            _snapshot(shares=100, sellable=100, price=10.0),
            trade_date="2026-09-01",
            now=NOW,
        )


def test_project_binds_replacement_fills_to_each_exact_broker_order(
    tmp_path: Path,
) -> None:
    plan = _bind_plan_intent(tmp_path, replace(_plan(), shares=200))
    store = ExecutionStore(tmp_path / "events.jsonl")
    ownership = BookBOwnershipEvidence(
        tmp_path / "book_b_ownership_evidence.jsonl"
    )
    first = store.append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.PARTIAL,
            filled_shares=100,
            remaining_shares=100,
            broker_order_id="order-first",
            fill_price=10.0,
            locator_proof={"plan_cumulative_fill_notional": "1000.00"},
        ),
        kind="first_partial",
    )
    ownership.record(plan, first)
    final = store.append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.FILLED,
            filled_shares=200,
            remaining_shares=0,
            broker_order_id="order-replacement",
            fill_price=10.5,
            locator_proof={"plan_cumulative_fill_notional": "2100.00"},
        ),
        kind="replacement_fill",
    )
    ownership.record(plan, final)

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=200,
            sellable=200,
            price=11.0,
            broker_fills=(
                ("order-first", "000001.XSHE", "BUY", 100, 10.0),
                ("order-replacement", "000001.XSHE", "BUY", 100, 11.0),
            ),
        ),
        trade_date="2026-09-01",
        now=NOW,
    )

    assert account.lots[0].shares == 200
    assert account.lots[0].entry_price == 10.5


def test_snapshot_rejects_sub_cent_funds_equation_drift(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot.pop("snapshot_sha256")
    snapshot["funds_summary"]["total_assets"] = 100_000.01
    snapshot["broker_summary"]["total_assets"] = 100_000.01
    snapshot["snapshot_sha256"] = _canonical_sha256(snapshot)

    with pytest.raises(ValueError, match="BROKER_FUNDS_EQUATION_FAILED"):
        project_book_b_live_account(
            tmp_path, snapshot, trade_date="2026-09-01", now=NOW
        )


def test_manual_older_same_code_shares_do_not_make_entry_day_lot_sellable(
    tmp_path: Path,
) -> None:
    buy = _plan()
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=200,
            sellable=100,
            price=11.0,
            broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),),
        ),
        trade_date="2026-09-01",
        now=NOW,
    )

    assert account.lots[0].shares == 100
    assert account.lots[0].sellable_shares == 0


def test_project_rejects_book_b_owned_shares_missing_at_broker(tmp_path: Path) -> None:
    _record_fill(tmp_path, _plan(), price=10.0, event_id="buy-fill")

    with pytest.raises(ValueError, match="BROKER_OWNERSHIP_MISMATCH"):
        project_book_b_live_account(
            tmp_path,
            _snapshot(
                broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),)
            ),
            trade_date="2026-09-01",
            now=NOW,
        )


def test_project_blocks_broker_fill_when_ownership_write_is_missing(
    tmp_path: Path,
) -> None:
    plan = _plan()
    ExecutionStore(tmp_path / "events.jsonl").append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.FILLED,
            filled_shares=100,
            remaining_shares=0,
            broker_order_id="order-unowned",
            fill_price=10.0,
        ),
        kind="ledger_write_failed",
    )

    with pytest.raises(ValueError, match="EXECUTION_FILL_NOT_OWNED"):
        project_book_b_live_account(
            tmp_path,
            _snapshot(shares=100, sellable=100, price=10.0),
            trade_date="2026-09-01",
            now=NOW,
        )


def test_project_accepts_repaired_ownership_after_historical_write_failure(
    tmp_path: Path,
) -> None:
    plan = _bind_plan_intent(tmp_path, _plan())
    persisted = ExecutionStore(tmp_path / "events.jsonl").append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.FILLED,
            filled_shares=100,
            remaining_shares=0,
            broker_order_id="order-repaired",
            fill_price=10.0,
        ),
        kind="ledger_write_failed",
    )
    BookBOwnershipEvidence(
        tmp_path / "book_b_ownership_evidence.jsonl"
    ).record(plan, persisted)

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=100,
            sellable=100,
            price=10.0,
            broker_fills=(("order-repaired", "000001.XSHE", "BUY", 100, 10.0),),
        ),
        trade_date="2026-09-01",
        now=NOW,
    )

    assert account.lots[0].shares == 100
    assert account.ownership_head_sha256 is not None


def test_project_rejects_hash_valid_ownership_with_bad_cumulative_delta(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _record_fill(tmp_path, plan, price=10.0, event_id="buy-fill")
    path = tmp_path / "book_b_ownership_evidence.jsonl"
    row = json.loads(path.read_text(encoding="utf-8"))
    row["cumulative_filled_shares"] = 99
    unsigned = dict(row)
    unsigned.pop("event_hash")
    row["event_hash"] = _canonical_sha256(unsigned)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="OWNERSHIP_CUMULATIVE_MISMATCH"):
        project_book_b_live_account(
            tmp_path,
            _snapshot(shares=100, sellable=100, price=10.0),
            trade_date="2026-09-01",
            now=NOW,
        )


def test_project_sell_consumes_exact_owned_lot_and_realized_cash(tmp_path: Path) -> None:
    buy = _plan()
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")
    sell = _plan(side="SELL", lot_id=buy.plan_id)
    _write_intent(tmp_path, sell)
    _record_fill(tmp_path, sell, price=11.0, event_id="sell-fill")

    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            broker_fills=(
                ("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),
                ("order-sell-fill", "000001.XSHE", "SELL", 100, 11.0),
            )
        ),
        trade_date="2026-09-01",
        now=NOW,
    )

    assert account.lots == ()
    assert account.cash == 30_099.79
    assert account.settled_nav == 30_099.79


def test_eod_settlement_is_hash_bound_idempotent_and_reusable(tmp_path: Path) -> None:
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(observed_at=EOD_NOW),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )

    first = write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    same = write_book_b_live_settlement(
        tmp_path, account, now=EOD_NOW + timedelta(seconds=30)
    )
    loaded = load_latest_book_b_live_settlement(tmp_path)

    assert same == first
    assert loaded == first
    assert first["capital_basis_source"] == "broker_reconciled_book_b_nav"
    assert first["settled_nav"] == 30_000
    basis = load_book_b_live_capital_basis(tmp_path)
    assert basis.settled_nav == 30_000
    assert basis.current_open_exposure == 0
    assert basis.source == "broker_reconciled_book_b_nav"
    assert basis.receipt_sha256 == first["settlement_sha256"]
    account_digest = hashlib.sha256(b"primary").hexdigest()[:24]
    assert (
        tmp_path / "account_writer_locks" / f"account-{account_digest}.lock"
    ).exists()


def test_eod_settlement_blocks_while_any_execution_is_open(tmp_path: Path) -> None:
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(observed_at=EOD_NOW),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "plan_id": "book-b:open",
                "state": "unknown",
                "receipt": {"state": "unknown"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="OPEN_EXECUTION_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


@pytest.mark.parametrize(
    "state",
    [ExecutionState.PLANNED, ExecutionState.VALIDATED, ExecutionState.PREPARED],
)
def test_eod_settlement_blocks_every_pre_submit_nonterminal_state(
    tmp_path: Path,
    state: ExecutionState,
) -> None:
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(observed_at=EOD_NOW),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )
    plan = _bind_plan_intent(tmp_path, _plan())
    ExecutionStore(tmp_path / "events.jsonl").append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=state,
            remaining_shares=plan.shares,
        ),
        kind="pre_submit_state",
    )

    with pytest.raises(ValueError, match="OPEN_EXECUTION_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


def test_eod_settlement_blocks_intent_persisted_before_first_event(
    tmp_path: Path,
) -> None:
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(observed_at=EOD_NOW),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )
    plan = _bind_plan_intent(tmp_path, _plan())

    assert open_execution_plan_ids(tmp_path) == (plan.plan_id,)
    with pytest.raises(ValueError, match="OPEN_EXECUTION_RECONCILE_REQUIRED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


def test_open_plan_scan_rejects_event_with_conflicting_intent_hash(
    tmp_path: Path,
) -> None:
    persisted = _bind_plan_intent(tmp_path, _plan())
    conflicting = replace(persisted, limit_price=9.99)
    ExecutionStore(tmp_path / "events.jsonl").append(
        plan=conflicting,
        receipt=ExecutionReceipt(
            plan_id=conflicting.plan_id,
            plan_hash=conflicting.plan_hash,
            state=ExecutionState.CANCELLED,
        ),
        kind="conflicting_terminal",
    )

    with pytest.raises(ValueError, match="PLAN_INTENT_EVENT_HASH_MISMATCH"):
        open_execution_plan_ids(tmp_path)


def test_eod_settlement_rechecks_locked_ownership_head_before_write(
    tmp_path: Path,
) -> None:
    first = _plan()
    _record_fill(tmp_path, first, price=10.0, event_id="buy-fill")
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(
            shares=100,
            sellable=100,
            price=10.0,
            observed_at=EOD_NOW,
            broker_fills=(("order-buy-fill", "000001.XSHE", "BUY", 100, 10.0),),
        ),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )
    second = replace(
        _plan(),
        plan_id="book-b:2026-09-01:000001.XSHE:BUY:second",
    )
    _record_fill(tmp_path, second, price=10.0, event_id="second-buy-fill")

    with pytest.raises(ValueError, match="SETTLEMENT_OWNERSHIP_CHANGED"):
        write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)


def test_next_day_basis_blocks_a_post_settlement_fill_missing_ownership(
    tmp_path: Path,
) -> None:
    account = project_book_b_live_account(
        tmp_path,
        _snapshot(observed_at=EOD_NOW),
        trade_date="2026-09-01",
        now=EOD_NOW,
    )
    write_book_b_live_settlement(tmp_path, account, now=EOD_NOW)
    plan = _plan()
    ExecutionStore(tmp_path / "events.jsonl").append(
        plan=plan,
        receipt=ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.FILLED,
            filled_shares=100,
            remaining_shares=0,
            fill_price=10.0,
        ),
        kind="broker_receipt",
    )

    with pytest.raises(ValueError, match="EXECUTION_FILL_NOT_OWNED"):
        load_book_b_live_capital_basis(tmp_path)


def test_intraday_hard_stop_materializes_one_owned_lot_sell_handoff(
    tmp_path: Path,
) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")
    seen: list[TradePlan] = []

    def execute(plan: TradePlan) -> ExecutionReceipt:
        seen.append(plan)
        return ExecutionReceipt(
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            state=ExecutionState.REJECTED,
            reason="TEST_NO_BROKER_WRITE",
            remaining_shares=plan.shares,
        )

    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="precheck",
        account_snapshot_provider=lambda: _snapshot(
            shares=100, sellable=100, price=9.2
        ),
        status_provider=lambda lots: [
            {
                "owned_lot_id": lots[0].owned_lot_id,
                "triggered": True,
                "sell_reason": "HARD_STOP",
                "decision_phase": "risk_floor",
                "latest_price": 9.2,
                "dd_pct": 8.0,
                "net_ret_pct": -8.1,
                "market_guard_status": "ok",
                "market_guard_observed_at": NOW,
                "market_guard_down_price": 9.0,
            }
        ],
        execute=execute,
        now=lambda: NOW,
        strategy_sha="a" * 40,
    )

    assert receipt.status == "executed"
    assert len(seen) == 1
    assert seen[0].side == "SELL"
    assert seen[0].owned_lot_id == buy.plan_id
    assert seen[0].sell_reason == "HARD_STOP"
    assert seen[0].limit_price == 9.2
    assert len(list((tmp_path / "plan_intents").glob("*.json"))) == 2


def test_intraday_rejects_tampered_buy_freeze_binding(tmp_path: Path) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")
    freeze = tmp_path / "book_b_live_freeze_2026-08-31.jsonl"
    row = json.loads(freeze.read_text(encoding="utf-8"))
    row["profile"] = "tampered"
    freeze.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="MONITOR_FREEZE_BINDING_MISMATCH"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="precheck",
            account_snapshot_provider=lambda: _snapshot(
                shares=100, sellable=100, price=9.2
            ),
            status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: NOW,
        )


def test_intraday_unknown_sell_stops_before_materializing_second_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lots = tuple(
        BookBLiveOwnedLot(
            owned_lot_id=f"buy-lot-{index}",
            code=f"00000{index}.XSHE",
            name=f"标的{index}",
            entry_date="2026-08-31",
            entry_price=10.0,
            shares=100,
            sellable_shares=100,
            current_price=9.0,
            market_value=900.0,
            liquidation_value_after_fee=899.91,
            buy_fee_rate=0.0001,
            sell_fee_rate=0.0001,
            snapshot_ref="test-only",
            monitor_context={},
        )
        for index in (1, 2)
    )
    account = BookBLiveAccountState(
        trade_date="2026-09-01",
        logical_account_id="primary",
        cash=28_000.0,
        current_open_exposure=1_800.0,
        liquidation_value_after_fee=1_799.82,
        settled_nav=29_799.82,
        realized_cash_delta=-2_000.0,
        ownership_head_sha256="a" * 64,
        broker_snapshot_sha256="b" * 64,
        broker_snapshot_observed_at=NOW.isoformat(),
        lots=lots,
    )
    monkeypatch.setattr(
        "xiaocao.live.book_b_live_intraday.project_book_b_live_account",
        lambda *args, **kwargs: account,
    )
    monkeypatch.setattr(
        "xiaocao.live.book_b_live_intraday.load_monitor_contexts",
        lambda *args, **kwargs: {},
    )
    calls: list[TradePlan] = []

    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="precheck",
        account_snapshot_provider=lambda: _snapshot(),
        status_provider=lambda owned: [
            {
                "owned_lot_id": lot.owned_lot_id,
                "triggered": True,
                "sell_reason": "HARD_STOP",
                "decision_phase": "risk_floor",
                "latest_price": 9.0,
                "market_guard_status": "ok",
                "market_guard_observed_at": NOW,
                "market_guard_down_price": 8.0,
            }
            for lot in owned
        ],
        execute=lambda plan: (
            calls.append(plan)
            or ExecutionReceipt(
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                state=ExecutionState.UNKNOWN,
                reason="TEST_UNKNOWN",
                remaining_shares=plan.shares,
            )
        ),
        now=lambda: NOW,
    )

    assert receipt.status == "executed"
    assert len(calls) == 1
    assert len(receipt.execution_receipts) == 1
    assert len(list((tmp_path / "plan_intents").glob("*.json"))) == 1


def test_intraday_can_handoff_entire_sellable_odd_lot_after_partial_buy(
    tmp_path: Path,
) -> None:
    buy = _bind_plan_intent(tmp_path, _plan(trade_date="2026-08-31"))
    partial = ExecutionStore(tmp_path / "events.jsonl").append(
        plan=buy,
        receipt=ExecutionReceipt(
            plan_id=buy.plan_id,
            plan_hash=buy.plan_hash,
            state=ExecutionState.PARTIAL,
            filled_shares=50,
            remaining_shares=50,
            broker_order_id="partial-buy",
            fill_price=10.0,
        ),
        kind="broker_receipt",
    )
    BookBOwnershipEvidence(
        tmp_path / "book_b_ownership_evidence.jsonl"
    ).record(buy, partial)
    ExecutionStore(tmp_path / "events.jsonl").append(
        plan=buy,
        receipt=ExecutionReceipt(
            plan_id=buy.plan_id,
            plan_hash=buy.plan_hash,
            state=ExecutionState.CANCELLED,
            filled_shares=50,
            remaining_shares=50,
            broker_order_id="partial-buy",
            fill_price=10.0,
        ),
        kind="cancel_receipt",
    )
    seen: list[TradePlan] = []

    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="precheck",
        account_snapshot_provider=lambda: _snapshot(
            shares=50, sellable=50, price=9.2
        ),
        status_provider=lambda lots: [
            {
                "owned_lot_id": lots[0].owned_lot_id,
                "triggered": True,
                "sell_reason": "HARD_STOP",
                "decision_phase": "risk_floor",
                "latest_price": 9.2,
                "market_guard_status": "ok",
                "market_guard_observed_at": NOW,
                "market_guard_down_price": 9.0,
            }
        ],
        execute=lambda plan: (
            seen.append(plan)
            or ExecutionReceipt(
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                state=ExecutionState.REJECTED,
                reason="TEST_NO_BROKER_WRITE",
                remaining_shares=plan.shares,
            )
        ),
        now=lambda: NOW,
    )

    assert receipt.status == "executed"
    assert seen[0].side == "SELL"
    assert seen[0].shares == 50


def test_sparse_soft_exit_is_recorded_but_never_handed_off(tmp_path: Path) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")

    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="sparse",
        account_snapshot_provider=lambda: _snapshot(
            shares=100, sellable=100, price=9.8
        ),
        status_provider=lambda lots: [
            {
                "owned_lot_id": lots[0].owned_lot_id,
                "triggered": False,
                "sell_reason": None,
                "decision_phase": "midday_reassessment",
                "latest_price": 9.8,
                "dd_pct": 2.0,
                "net_ret_pct": -2.1,
                "deferred_sell_reason": "TRAILING_STOP",
            }
        ],
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        now=lambda: NOW,
    )

    assert receipt.status == "observed"
    assert receipt.execution_receipts == ()
    assert receipt.decisions[0]["deferred_sell_reason"] == "TRAILING_STOP"
    assert len(list((tmp_path / "plan_intents").glob("*.json"))) == 1


def test_intraday_liquidity_block_records_decision_without_sell_intent(
    tmp_path: Path,
) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")

    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="closing",
        account_snapshot_provider=lambda: _snapshot(
            shares=100, sellable=100, price=9.0
        ),
        status_provider=lambda lots: [
            {
                "owned_lot_id": lots[0].owned_lot_id,
                "triggered": True,
                "sell_reason": "EOD_DISCIPLINE_1455",
                "decision_phase": "eod_discipline",
                "latest_price": 9.0,
                "sell_block_reason": "LIMIT_DOWN_NO_BID",
            }
        ],
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        now=lambda: NOW,
    )

    assert receipt.status == "observed"
    assert receipt.decisions[0]["sell_authorized"] is False
    assert receipt.decisions[0]["sell_block_reason"] == "LIMIT_DOWN_NO_BID"


def test_intraday_trigger_fails_closed_on_unproved_market_status(tmp_path: Path) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")

    with pytest.raises(ValueError, match="LIVE_SELL_MARKET_GUARD_UNPROVEN"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="precheck",
            account_snapshot_provider=lambda: _snapshot(
                shares=100, sellable=100, price=9.2
            ),
            status_provider=lambda lots: [
                {
                    "owned_lot_id": lots[0].owned_lot_id,
                    "triggered": True,
                    "sell_reason": "HARD_STOP",
                    "decision_phase": "risk_floor",
                    "latest_price": 9.2,
                    "market_guard_status": "S",
                    "market_guard_observed_at": NOW,
                    "market_guard_down_price": 9.0,
                }
            ],
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: NOW,
        )
    assert len(list((tmp_path / "plan_intents").glob("*.json"))) == 1


def test_intraday_eod_only_reconciles_projects_and_settles(tmp_path: Path) -> None:
    receipt = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="eod",
        account_snapshot_provider=lambda: _snapshot(observed_at=EOD_NOW),
        status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        now=lambda: EOD_NOW,
    )

    assert receipt.status == "settled"
    assert receipt.settlement is not None
    assert receipt.settlement["settled_nav"] == 30_000


def test_intraday_rejects_eod_settlement_before_market_close(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="EOD_SETTLEMENT_WINDOW_NOT_OPEN"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="eod",
            account_snapshot_provider=lambda: _snapshot(),
            status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: NOW,
        )


def test_intraday_rejects_preclose_snapshot_after_eod_window_opens(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="EOD_BROKER_SNAPSHOT_PRE_CLOSE"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="eod",
            account_snapshot_provider=lambda: _snapshot(),
            status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: EOD_NOW,
        )


def test_intraday_rejects_closing_authority_before_1455(
    tmp_path: Path,
) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")
    early = NOW - timedelta(minutes=2)

    with pytest.raises(ValueError, match="CLOSING_DISCIPLINE_WINDOW_NOT_OPEN"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="closing",
            account_snapshot_provider=lambda: _snapshot(
                shares=100,
                sellable=100,
                price=11.0,
                observed_at=early,
            ),
            status_provider=lambda lots: [
                {
                    "owned_lot_id": lots[0].owned_lot_id,
                    "triggered": True,
                    "sell_reason": "EOD_DISCIPLINE_1455",
                    "decision_phase": "eod_discipline",
                    "latest_price": 11.0,
                    "market_guard_status": "ok",
                    "market_guard_observed_at": early,
                    "market_guard_down_price": 9.0,
                }
            ],
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: early,
        )


def test_intraday_blocks_new_decisions_while_any_live_plan_is_unresolved(
    tmp_path: Path,
) -> None:
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "plan_id": "book-b:unknown",
                "state": "unknown",
                "receipt": {"state": "unknown"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="OPEN_EXECUTION_RECONCILE_REQUIRED"):
        run_book_b_live_intraday(
            state_dir=tmp_path,
            freeze_dir=tmp_path,
            trade_date="2026-09-01",
            phase="sparse",
            account_snapshot_provider=lambda: (_ for _ in ()).throw(
                AssertionError("snapshot must wait for durable reconcile")
            ),
            status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
            execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
            now=lambda: NOW,
        )


def test_intraday_rejects_overlapping_checkpoint_before_broker_read(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "book_b_live_checkpoint.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="CHECKPOINT_ALREADY_RUNNING"):
            run_book_b_live_intraday(
                state_dir=tmp_path,
                freeze_dir=tmp_path,
                trade_date="2026-09-01",
                phase="sparse",
                account_snapshot_provider=lambda: (_ for _ in ()).throw(
                    AssertionError("overlap must not read broker")
                ),
                status_provider=lambda lots: (_ for _ in ()).throw(
                    AssertionError(lots)
                ),
                execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
                now=lambda: NOW,
            )


def test_full_live_lifecycle_buy_decision_sell_fill_eod_and_next_basis(
    tmp_path: Path,
) -> None:
    buy = _plan(trade_date="2026-08-31")
    _record_fill(tmp_path, buy, price=10.0, event_id="buy-fill")
    handed_off: list[TradePlan] = []

    intraday = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="closing",
        account_snapshot_provider=lambda: _snapshot(
            shares=100, sellable=100, price=11.0
        ),
        status_provider=lambda lots: [
            {
                "owned_lot_id": lots[0].owned_lot_id,
                "triggered": True,
                "sell_reason": "EOD_DISCIPLINE_1455",
                "decision_phase": "eod_discipline",
                "latest_price": 11.0,
                "dd_pct": 0.0,
                "net_ret_pct": 9.98,
                "market_guard_status": "ok",
                "market_guard_observed_at": NOW,
                "market_guard_down_price": 9.0,
            }
        ],
        execute=lambda plan: (
            handed_off.append(plan)
            or ExecutionReceipt(
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                state=ExecutionState.ACKNOWLEDGED,
                reason="TEST_HANDOFF_ONLY",
                remaining_shares=plan.shares,
            )
        ),
        now=lambda: NOW,
        strategy_sha="a" * 40,
    )
    assert intraday.status == "executed"
    assert len(handed_off) == 1

    # The transaction implementation owns this transition in production.  The
    # lifecycle consumes only its broker-proved fill receipt.
    _record_fill(tmp_path, handed_off[0], price=11.0, event_id="sell-fill")
    eod = run_book_b_live_intraday(
        state_dir=tmp_path,
        freeze_dir=tmp_path,
        trade_date="2026-09-01",
        phase="eod",
        account_snapshot_provider=lambda: _snapshot(
            observed_at=EOD_NOW,
            broker_fills=(
                ("order-sell-fill", "000001.XSHE", "SELL", 100, 11.0),
            ),
        ),
        status_provider=lambda lots: (_ for _ in ()).throw(AssertionError(lots)),
        execute=lambda plan: (_ for _ in ()).throw(AssertionError(plan)),
        now=lambda: EOD_NOW,
    )

    assert eod.status == "settled"
    assert eod.settlement is not None
    assert eod.settlement["settled_nav"] == 30_099.79
    basis = load_book_b_live_capital_basis(tmp_path)
    assert basis.settled_nav == 30_099.79
    assert basis.current_open_exposure == 0
    assert basis.source == "broker_reconciled_book_b_nav"
