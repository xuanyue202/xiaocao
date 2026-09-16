"""Counter acceptance is independent of the later exchange fill."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from xiaocao.live.book_b_live_morning import advance_submission_batch
from xiaocao.live.trading_execution import (
    ExecutionReceipt, ExecutionState, _outside_live_initial_submit_window,
    trade_plan_from_frozen_row,
)
from tests.test_book_b_live_morning import _frozen_row

pytestmark = pytest.mark.app_simulation


def _plan(index=1):
    return trade_plan_from_frozen_row(
        {**_frozen_row(), "code": f"{index:06d}.XSHE", "mode_exec_planned_shares": 100},
        environment="live", logical_account_id="primary",
        now=datetime(2026, 8, 24, 1, 24, tzinfo=timezone.utc),
    )


def _ack(plan, **changes):
    receipt = ExecutionReceipt(
        plan.plan_id, plan.plan_hash, ExecutionState.ACKNOWLEDGED,
        broker_order_id=f"60000{plan.code[:6]}", broker_strategy_id=plan.code,
        receipt_mapping=True, submit_claim_id=plan.code, account_binding="proven",
        active=True, remaining_shares=plan.shares, next_action="reconcile",
    )
    return replace(receipt, **changes)


@pytest.mark.parametrize("minute,second,allowed", [(24, 59, False), (25, 0, True),
                                                   (27, 59, True), (29, 59, True), (30, 0, True)])
def test_buy_counter_window_opens_at_0925(minute, second, allowed):
    plan = _plan()
    assert plan.submit_not_before == datetime(2026, 8, 24, 1, 25, tzinfo=timezone.utc)
    clock = datetime(2026, 8, 24, 1, minute, second, tzinfo=timezone.utc)
    assert _outside_live_initial_submit_window(plan, clock) is not allowed
    if minute < 30:
        assert _outside_live_initial_submit_window(replace(plan, side="SELL"), clock)


@pytest.mark.parametrize("count", [2, 3, 5])
@pytest.mark.parametrize("partial", [False, True])
def test_all_counter_acceptances_precede_fill_polling(count, partial):
    plans = [_plan(index) for index in range(1, count + 1)]
    calls = []
    receipts = []

    def execute(plan):
        calls.append(plan.plan_id)
        return _ack(plan, state=ExecutionState.PARTIAL, filled_shares=50,
                    remaining_shares=50) if partial else _ack(plan)

    def wait():
        assert calls[:count] == [plan.plan_id for plan in plans]

    advance_submission_batch(plans, execute=execute, allow=lambda _: True,
                              receipts=receipts, wait=wait)
    assert calls == [plan.plan_id for plan in plans] * 4
    assert len(receipts) == count
    assert len({receipt.broker_order_id for receipt in receipts}) == count


@pytest.mark.parametrize("changes", [
    {"state": ExecutionState.UNKNOWN}, {"receipt_mapping": False},
    {"submit_chain_uncertain": True}, {"cancel_chain_uncertain": True},
    {"submit_claim_id": None}, {"broker_order_id": None},
    {"account_binding": "unproven"}, {"active": None},
    {"remaining_shares": 1}, {"next_action": "reconcile_only"},
    {"plan_hash": "wrong"},
])
def test_unproven_first_order_never_allows_second_write(changes):
    plans = [_plan(1), _plan(2)]
    calls, receipts = [], []

    def execute(plan):
        calls.append(plan.plan_id)
        return _ack(plan, **changes)

    advance_submission_batch(plans, execute=execute, allow=lambda _: True, receipts=receipts)
    assert calls == [plans[0].plan_id] * 4
    assert len(receipts) == 1


def test_read_failure_retains_all_initial_acks():
    plans = [_plan(1), _plan(2)]
    calls, receipts = [], []

    def execute(plan):
        calls.append(plan.plan_id)
        if len(calls) > 2:
            raise RuntimeError("read failed")
        return _ack(plan)

    with pytest.raises(RuntimeError, match="read failed"):
        advance_submission_batch(plans, execute=execute, allow=lambda _: True, receipts=receipts)
    assert [r.broker_order_id for r in receipts] == [_ack(p).broker_order_id for p in plans]


def test_duplicate_counter_id_blocks_the_remainder_of_batch():
    plans = [_plan(1), _plan(2), _plan(3)]
    receipts, calls = [], []

    def execute(plan):
        calls.append(plan.plan_id)
        return _ack(plan, broker_order_id="600001")

    with pytest.raises(ValueError, match="LIVE_BATCH_ORDER_ID_REUSED"):
        advance_submission_batch(plans, execute=execute, allow=lambda _: True, receipts=receipts)
    assert calls == [plan.plan_id for plan in plans[:2]]


def test_prepared_without_claim_is_not_reexecuted_as_reconciliation():
    calls, receipts = [], []
    plan = _plan()

    def execute(plan):
        calls.append(plan.plan_id)
        return ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PREPARED,
                                next_action="prepare")

    advance_submission_batch([plan, _plan(2)], execute=execute, allow=lambda _: True, receipts=receipts)
    assert calls == [plan.plan_id]


def test_final_review_receives_account_before_starting_its_budget(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, _execute_capture
    from tests.test_book_b_live_morning import _live_allocation_payload
    from xiaocao.live.book_b_live_morning import run_book_b_live_morning

    config = _morning(tmp_path)
    clock = [datetime(2026, 8, 24, 1, 25, 52, tzinfo=timezone.utc)]
    reads, requests = [], []

    def read_account():
        reads.append(clock[0])
        clock[0] += timedelta(seconds=45)
        return _live_allocation_payload()

    def review(request):
        requests.append(request)
        assert request["account_facts"]["settled_nav"] == 30000
        assert request["allocation_capsule_sha256"] == _live_allocation_payload()["allocation_capsule_sha256"]
        assert request["account_risk"]["status"] == "NORMAL"
        assert datetime.fromisoformat(request["requested_at"]) == clock[0]
        assert request["max_wait_seconds"] == 23
        return {"status": "timed_out", "fallback": "neutral"}

    receipt = run_book_b_live_morning(config, execute=_execute_capture([]),
                                    read_allocation_facts=read_account, risk_provider=_risk,
                                    review_rendezvous=review, now=lambda: clock[0])
    assert receipt.status == "completed", receipt.reason
    assert len(reads) == len(requests) == 1


def test_nested_account_fence_keeps_other_process_out(tmp_path):
    import subprocess
    import sys
    from xiaocao.live.trading_execution import account_writer_lock

    script = """
import fcntl, sys
with open(sys.argv[1], 'a+') as stream:
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(7)
"""
    with account_writer_lock(tmp_path, "primary"):
        with account_writer_lock(tmp_path, "primary"):
            path = next(tmp_path.glob("account-*.lock"))
        assert subprocess.run([sys.executable, "-c", script, str(path)], timeout=5).returncode == 7
    assert subprocess.run([sys.executable, "-c", script, str(path)], timeout=5).returncode == 0


def test_nested_account_fence_does_not_admit_another_thread(tmp_path):
    import threading
    from xiaocao.live.trading_execution import account_writer_lock

    started, entered = threading.Event(), threading.Event()

    def writer():
        started.set()
        with account_writer_lock(tmp_path, "primary"):
            entered.set()

    with account_writer_lock(tmp_path, "primary"):
        with account_writer_lock(tmp_path, "primary"):
            worker = threading.Thread(target=writer)
            worker.start()
            assert started.wait(1)
            assert not entered.wait(0.05)
        assert not entered.is_set()
    worker.join(timeout=2)
    assert entered.is_set() and not worker.is_alive()
