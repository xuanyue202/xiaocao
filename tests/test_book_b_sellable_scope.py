from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from xiaocao.live.book_b_capital import POLICY, digest
from xiaocao.live.book_b_live_lifecycle import project_book_b_sellable
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from xiaocao.live.foundersc_native_ax import FounderscNativeAXError
from xiaocao.live.morning_order_wait import await_orders
from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionState
from tests.test_foundersc_native_broker import FakeNative, _plan
from tests.test_book_b_live_lifecycle import _record_fill, _plan as owned_plan, NOW

pytestmark = pytest.mark.app_simulation


class ScopedNative(FakeNative):
    def __init__(self, now):
        super().__init__()
        self.clock = now
        self.payload["helper_version"] = 11
        self.position_summary = {}  # Full account must fail; quantity proof survives.
        self.positions[1]["当前价"] = "unreadable"
        self.orders[0]["成交数量"] = "unreadable"

    def read_query(self, **kwargs):
        result = super().read_query(**kwargs)
        raw = result.payload["query_readback"]
        raw.update(structural_parsing_proven=True, critical_confidence_floor=.9,
                   critical_cell_confidences=[{k: .99 for k in row} for row in raw["rows"]],
                   observed_at=self.clock.isoformat())
        return result


def test_sell_scope_proves_quantity_and_duplicate_guard_without_funds(monkeypatch):
    now = datetime.now(timezone.utc)
    native = ScopedNative(now)
    adapter = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint="123******890", scoped_sell_preflight=True,
        snapshot_read_delays=(0,))
    plan = replace(_plan(), side="SELL", trade_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat())
    capability = adapter.probe(plan)
    assert capability.ready and capability.supports_submit
    assert capability.sellable_shares == 100
    assert capability.capabilities["native_position_funds_summary"] is False
    proof = adapter.capital_action_proof(plan, now=now)
    assert proof["available_cash"] is None and proof["sellable_shares"] == 100
    assert proof["proof_sha256"] == digest({k:v for k,v in proof.items() if k != "proof_sha256"})
    # Same-code locked shares must not suppress a proved sellable prior-day lot.
    native.positions[1]["证券数量"] = "200"
    assert adapter.probe(plan).t1_blocked is False
    assert adapter.probe(replace(plan, shares=200)).t1_blocked is True
    native.orders.append({"证券代码":"000001", "委托编号":"9999999", "买卖标志":"卖出", "委托价格":"10", "委托数量":"100"})
    rejected = adapter.prepare(plan)
    assert rejected.reason == "NATIVE_PREEXISTING_EXACT_ORDER_BLOCKS_SUBMIT"
    assert native.prepare_calls == native.submit_calls == 0


@pytest.mark.parametrize("fault", ["identity", "date", "sellable", "cells"])
def test_sell_scope_never_relaxes_identity_date_or_quantities(fault):
    now = datetime.now(timezone.utc)
    native = ScopedNative(now)
    adapter = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint="123******890", scoped_sell_preflight=True,
        snapshot_read_delays=(0,))
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if fault == "identity":
        original = native.read_query
        def wrong_account(**kwargs):
            result = original(**kwargs)
            result.payload["trade_account_fingerprint"] = "999******999"
            return result
        native.read_query = wrong_account
    elif fault == "date":
        day = "2000-01-01"
    elif fault == "sellable":
        native.positions[1]["可卖数量"] = "101"
    else:
        original = native.read_query
        def bad(**kwargs):
            result = original(**kwargs)
            result.payload["query_readback"]["critical_cell_confidences"][1]["可卖数量"] = .1
            return result
        native.read_query = bad
    with pytest.raises(FounderscNativeAXError):
        adapter.read_sellable_snapshot(trade_date=day, owned_codes={"000001.XSHE"})


@pytest.mark.parametrize("entry_date,expected_sellable", [("2026-08-31",50),("2026-09-01",0)])
def test_sellable_projection_preserves_owned_lot_t1_and_unknown_valuation(tmp_path, entry_date, expected_sellable):
    buy = owned_plan(trade_date=entry_date)
    _record_fill(tmp_path, buy, price=10, event_id="buy")
    cfg = {"policy_id": POLICY, "logical_account_id": "primary", "fund_account_binding_sha256": "a"*64}
    cfg["policy_sha256"] = digest(cfg)
    (tmp_path/"capital_policy.json").write_text(json.dumps(cfg))
    snapshot = {"schema_version":"book-b-sellable-only.v1", "source":"foundersc_native_app",
        "environment":"live", "logical_account_id":"primary", "account_binding":"proven",
        "trade_date":"2026-09-01", "fund_account_binding_sha256":"a"*64, "observed_at":NOW.isoformat(),
        "positions":{"scope":"sellable_only", "capture_proven":True, "row_count":1,
            "scoped_codes":["000001"], "observed_at":NOW.isoformat(),
            "rows":[{"证券代码":"000001", "证券数量":"100", "可卖数量":"50"}]}}
    snapshot["snapshot_sha256"] = digest(snapshot)
    result = project_book_b_sellable(tmp_path, snapshot, trade_date="2026-09-01", now=NOW)
    assert result.lots[0].sellable_shares == expected_sellable
    assert result.lots[0].owned_lot_id == buy.plan_id
    assert result.lots[0].current_price is None
    assert result.as_dict()["cash"] is result.as_dict()["settled_nav"] is None
    # A mark/quantity is not a complete account and cannot settle it.
    from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account
    with pytest.raises(ValueError):
        project_book_b_live_account(tmp_path, snapshot, trade_date="2026-09-01", now=NOW)


def test_original_sell_wait_tracks_partial_fill_without_submit_or_budget_reset():
    now = [datetime(2026,10,22,6,45,tzinfo=timezone.utc)]
    plan = replace(_plan(), side="SELL", trade_date="2026-10-22")
    first = ExecutionReceipt(plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        state=ExecutionState.ACKNOWLEDGED, submit_claim_id="one", broker_order_id="12345", remaining_shares=100)
    rows, seen = [first], []
    def reconcile(exact):
        assert exact is plan
        seen.append(exact.plan_id)
        return replace(first, state=ExecutionState.PARTIAL if len(seen)==1 else ExecutionState.FILLED,
                       filled_shares=50 if len(seen)==1 else 100, remaining_shares=50 if len(seen)==1 else 0)
    await_orders([plan], rows, reconcile=reconcile, deadline=now[0]+timedelta(seconds=20),
                 now=lambda:now[0], sleep=lambda seconds: now.__setitem__(0, now[0]+timedelta(seconds=seconds)),
                 on_progress=lambda rows:None)
    assert rows[0].state == ExecutionState.FILLED and len(seen)==2


@pytest.mark.parametrize("fail_after_claim", [False, True])
def test_intraday_public_entry_keeps_original_claim_and_invokes_wait(tmp_path, fail_after_claim):
    from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
    from xiaocao.live.trading_execution import ExecutionStore
    from tests.test_book_b_live_lifecycle import _snapshot
    buy = _record_fill(tmp_path, owned_plan(trade_date="2026-08-31"), price=10, event_id="buy")
    calls = []
    def execute(plan):
        calls.append(plan)
        receipt = ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.ACKNOWLEDGED,
            submit_claim_id="original-claim", broker_order_id="12345", remaining_shares=plan.shares)
        ExecutionStore(tmp_path / "events.jsonl").append(plan=plan, receipt=receipt)
        if fail_after_claim:
            raise OSError("response interrupted after durable claim")
        return receipt
    def await_result(plans, receipts):
        assert plans == calls and len(receipts) == 1
        assert receipts[0].submit_claim_id == "original-claim"
        receipts[0] = replace(receipts[0], state=ExecutionState.CANCELLED)
        return {"status": "terminal"}
    result = run_book_b_live_intraday(state_dir=tmp_path, freeze_dir=tmp_path,
        trade_date="2026-09-01", phase="precheck", now=lambda: NOW,
        account_snapshot_provider=lambda: _snapshot(shares=100, sellable=100, price=9.2),
        status_provider=lambda _: [{"owned_lot_id":buy.plan_id,"triggered":True,
            "sell_reason":"HARD_STOP","latest_price":9.2,"market_guard_status":"ok",
            "market_guard_observed_at":NOW,"market_guard_down_price":9.}],
        execute=execute, await_sell_results=await_result)
    assert len(calls) == 1 and result.order_wait == {"status":"terminal"}
    assert result.execution_receipts[0]["state"] == "cancelled"
    assert result.status == ("blocked" if fail_after_claim else "executed")
    assert result.batch_failure == ("OSError" if fail_after_claim else None)
