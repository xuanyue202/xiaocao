"""Real Python execution/store/adapter chain with a controllable native service."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_foundersc_native_broker import FakeNative, _adapter, _plan
from xiaocao.live.safety import ENV_LIVE_ENABLED, ENV_SIGNING_KEY, make_authorization
from xiaocao.live.trading_execution import (
    BookBOwnershipEvidence, ExecutionState, ExecutionStore, TradingExecution,
)


@pytest.fixture
def chain(tmp_path):
    china_day = datetime.now(timezone(timedelta(hours=8))).date()
    now = datetime(china_day.year, china_day.month, china_day.day, 1, 35, tzinfo=timezone.utc)
    plan = replace(_plan(), created_at=now, trade_date=now.astimezone(timezone(timedelta(hours=8))).date().isoformat(),
                   recovery_deadline=now + timedelta(minutes=5), price_rule="explicit-test-limit",
                   code="512010.XSHG")
    signing = "local-test-key"
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(make_authorization(
        scope="test", max_notional=2000, signing_key=signing,
        expires_at=(now + timedelta(hours=1)).isoformat(), issued_at=now.isoformat(),
    )))
    def engine(native):
        return TradingExecution(
            store=ExecutionStore(tmp_path / "events.jsonl"), broker=_adapter(native),
            ledger=BookBOwnershipEvidence(tmp_path / "ownership.jsonl"),
            safety_env={ENV_LIVE_ENABLED: "true", ENV_SIGNING_KEY: signing},
            auth_path=auth, audit_path=tmp_path / "audit.jsonl", now=lambda: now,
            notifier=lambda *_args: None,
        )
    return plan, engine


@pytest.mark.parametrize("lost", [None, "submit", "cancel"])
def test_restart_after_native_response_loss_never_repeats_effect(chain, lost):
    class Native(FakeNative):
        def submit_prepared_order(self, **kwargs):
            result = super().submit_prepared_order(**kwargs)
            if lost == "submit":
                raise TimeoutError("response lost after service accepted")
            return result

        def cancel_order(self, **kwargs):
            result = super().cancel_order(**kwargs)
            if lost == "cancel":
                self.lose_cancel_reads = True
                raise TimeoutError("response lost after service cancelled")
            return result

        def read_query(self, **kwargs):
            if getattr(self, "lose_cancel_reads", False):
                raise TimeoutError("queries also unavailable until reconnect")
            return super().read_query(**kwargs)

    plan, engine = chain
    native = Native()
    first = engine(native).execute(plan)
    assert first.state == (ExecutionState.UNKNOWN if lost == "submit" else ExecutionState.ACKNOWLEDGED), first.reason
    resumed = engine(native).execute(plan)
    assert resumed.state == ExecutionState.ACKNOWLEDGED
    assert native.submit_calls == 1 and native.prepare_calls == 1
    cancelled = engine(native).cancel(plan)
    if lost == "cancel":
        assert cancelled.state == ExecutionState.UNKNOWN
        native.lose_cancel_reads = False
        cancelled = engine(native).cancel(plan)
    assert cancelled.state == ExecutionState.CANCELLED
    before = (native.submit_calls, native.cancel_calls, len(native.query_calls))
    for _ in range(3):
        assert engine(native).execute(plan).state == ExecutionState.CANCELLED
        assert engine(native).cancel(plan).state == ExecutionState.CANCELLED
    assert before == (native.submit_calls, native.cancel_calls, len(native.query_calls))
    assert native.submit_calls == native.cancel_calls == 1


@pytest.mark.parametrize("field,value", [
    ("trade_account_fingerprint", "999******000"), ("screen_locked", True),
    ("accessibility_trusted", False), ("app_running", False),
])
def test_broken_native_readiness_never_reaches_order_fields(chain, field, value):
    plan, engine = chain
    native = FakeNative(**{field: value})
    receipt = engine(native).execute(plan)
    assert receipt.state in {ExecutionState.REJECTED, ExecutionState.VALIDATED}
    assert receipt.submit_claim_id is None and receipt.broker_order_id is None
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0


@pytest.mark.parametrize("filled", [40, 100])
def test_partial_cancel_and_fill_are_recorded_once_across_restarts(chain, filled):
    plan, engine = chain
    native = FakeNative()
    accepted = engine(native).execute(plan)
    order = next(row for row in native.orders if row["委托编号"] == accepted.broker_order_id)
    order.update({"状态说明": "已撤" if filled < 100 else "已成", "成交数量": str(filled)})
    native.trades = [{
        "证券代码": "512010", "买卖标志": "买入", "成交时间": "100001",
        "成交价格": "9.98", "成交数量": str(filled), "成交金额": str(filled * 9.98),
        "成交编号": "700001", "委托编号": accepted.broker_order_id,
    }]
    final = engine(native).execute(plan)
    assert final.state == (ExecutionState.CANCELLED if filled < 100 else ExecutionState.FILLED), final.reason
    for _ in range(3):
        assert engine(native).execute(plan).filled_shares == filled
    ledger = engine(native).ledger
    assert ledger.owned_shares(logical_account_id="primary", code=plan.code) == filled
    rows = [json.loads(line) for line in ledger.path.read_text().splitlines()]
    assert len(rows) == 1
    assert native.submit_calls == 1 and native.cancel_calls == 0


@pytest.mark.parametrize("tail", ['{"submit_claim_id":', '[]\n', 'null\n'])
def test_damaged_execution_history_cannot_be_interpreted_as_no_order(chain, tail):
    plan, engine = chain
    native = FakeNative()
    execution = engine(native)
    execution.store.path.write_text(tail)
    with pytest.raises(ValueError, match="EXECUTION_HISTORY_CORRUPT"):
        execution.execute(plan)
    assert native.prepare_calls == native.submit_calls == native.cancel_calls == 0
    assert execution.store.path.read_text() == tail


@pytest.mark.parametrize("sellable", [0, 100])
def test_owned_sell_uses_native_side_and_t1_then_reconciles_once(chain, sellable):
    plan, engine = chain
    native = FakeNative()
    bought = engine(native).execute(plan)
    order = next(row for row in native.orders if row["委托编号"] == bought.broker_order_id)
    order.update({"状态说明": "已成", "成交数量": "100"})
    native.trades = [{"证券代码": "512010", "买卖标志": "买入", "成交价格": "10.0",
                      "成交数量": "100", "成交编号": "700001", "委托编号": bought.broker_order_id}]
    assert engine(native).execute(plan).state == ExecutionState.FILLED
    native.positions.append({"证券代码": "512010", "证券数量": "100",
        "可卖数量": str(sellable), "当前价": "10", "最新市值": "1000"})
    sell = replace(plan, plan_id=plan.plan_id + ":sell", side="SELL", basket_price=None,
        owned_lot_id=plan.plan_id, sell_authorized=True, sell_reason="HARD_STOP",
        sell_decision_phase="risk_floor", sell_decision_at=plan.created_at,
        market_guard_required=True, market_guard_observed_at=plan.created_at,
        market_guard_latest_price=10.0, market_guard_down_price=9.0)
    receipt = engine(native).execute(sell)
    if not sellable:
        assert receipt.state in {ExecutionState.SKIPPED, ExecutionState.REJECTED}, receipt.reason
        assert native.submit_calls == 1
    else:
        assert receipt.state == ExecutionState.ACKNOWLEDGED, receipt.reason
        assert native.orders[-1]["买卖标志"] == "卖出"
        assert engine(native).cancel(sell).state == ExecutionState.CANCELLED
        assert engine(native).cancel(sell).state == ExecutionState.CANCELLED
        assert native.submit_calls == 2 and native.cancel_calls == 1
    assert engine(native).ledger.owned_shares(logical_account_id="primary", code=plan.code) == 100


@pytest.mark.parametrize("workers", [2, 5, 20])
def test_concurrent_same_plan_submits_and_cancels_exactly_once(chain, workers):
    plan, engine = chain
    native = FakeNative()
    def simultaneously(action):
        start = Barrier(workers)
        def invoke(_):
            execution = engine(native)  # independent stores/adapters, shared account lock
            start.wait(timeout=5)
            return getattr(execution, action)(plan)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(invoke, range(workers)))
    submitted = simultaneously("execute")
    assert {r.state for r in submitted} == {ExecutionState.ACKNOWLEDGED}
    assert len({r.broker_order_id for r in submitted}) == 1
    assert native.prepare_calls == native.submit_calls == 1
    cancelled = simultaneously("cancel")
    assert {r.state for r in cancelled} == {ExecutionState.CANCELLED}
    assert native.cancel_calls == 1


@pytest.mark.parametrize("workers", [2, 5, 20])
@pytest.mark.parametrize("same_symbol", [False, True])
def test_concurrent_distinct_orders_preserve_each_tuple_and_exact_cancel(chain, workers, same_symbol):
    plan, engine = chain
    native = FakeNative()
    plans = [replace(plan, plan_id=f"{plan.plan_id}:batch:{index}",
                     code=f"{512010 if same_symbol else 512010 + index:06d}.XSHG", limit_price=9.0 + index / 100)
             for index in range(workers)]
    start = Barrier(workers)
    def submit(item):
        start.wait(timeout=5)
        return engine(native).execute(item)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        receipts = list(pool.map(submit, plans))
    assert all(r.state == ExecutionState.ACKNOWLEDGED for r in receipts)
    assert len({r.broker_order_id for r in receipts}) == workers
    orders = {row["委托编号"]: row for row in native.orders}
    for item, receipt in zip(plans, receipts):
        row = orders[receipt.broker_order_id]
        assert row["证券代码"] == item.code.split(".")[0]
        assert float(row["委托价格"]) == item.limit_price
        assert int(row["委托数量"]) == item.shares
    # A different cancellation order must still target the original order IDs.
    for item in reversed(plans):
        assert engine(native).cancel(item).state == ExecutionState.CANCELLED
    assert native.submit_calls == native.cancel_calls == workers
    assert native.orders[0]["状态说明"] == "未报"  # unrelated pre-existing order


@pytest.mark.parametrize("different_state_dir", [False, True])
def test_account_reader_cannot_navigate_between_prepare_and_submit(chain, tmp_path, different_state_dir):
    from threading import Event
    prepared, reader_attempting, reader_entered = Event(), Event(), Event()
    class Native(FakeNative):
        def prepare_order(self, **kwargs):
            result = super().prepare_order(**kwargs)
            prepared.set()
            assert reader_attempting.wait(3)
            assert not reader_entered.wait(.1)
            return result
        def submit_prepared_order(self, **kwargs):
            assert not reader_entered.is_set(), "reader replaced the prepared form"
            return super().submit_prepared_order(**kwargs)
    plan, engine = chain
    native = Native()
    writer = engine(native)
    reader = engine(native)
    if different_state_dir:
        reader.account_lock_dir = tmp_path / "other-checkout/state/locks"
    original = native.read_query
    def read_query(**kwargs):
        if prepared.is_set() and reader_attempting.is_set() and native.submit_calls == 0:
            reader_entered.set()
        receipt = original(**kwargs)
        receipt.payload["query_readback"]["observed_at"] = writer.now().isoformat()
        return receipt
    native.read_query = read_query
    def query():
        assert prepared.wait(3)
        reader_attempting.set()
        # This public adapter read does not acquire the account-state lock.
        return reader.broker.read_live_account_snapshot(
            trade_date=plan.trade_date, expected_fund_account_fingerprint="123******890",
            now=writer.now())
    with ThreadPoolExecutor(2) as pool:
        reading = pool.submit(query)
        receipt = pool.submit(writer.execute, plan).result(timeout=5)
        reading.result(timeout=5)
    assert receipt.state == ExecutionState.ACKNOWLEDGED, receipt.reason
    assert native.submit_calls == 1
    assert engine(native).cancel(plan).state == ExecutionState.CANCELLED
