"""Post-business observations share the original deadline and cannot write."""
import fcntl
import threading
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_foundersc_native_ax import _helper, _receipt, HelperRunner
from tests.test_foundersc_native_broker import FakeNative, _adapter
from xiaocao.live.bounded_readback import (original_readback, require_read_command,
    remaining, active, mutex, file_lock, ReadbackDeadlineExpired)
from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient

pytestmark = pytest.mark.app_simulation


def deadline(seconds=1):
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def test_nested_scope_never_refunds_budget_and_restores_normal_commands():
    assert not active()
    with original_readback(deadline()):
        first=remaining()
        with original_readback(deadline(60)):
            assert remaining()<=first
            require_read_command('read-query')
        assert remaining()<=first
    assert not active() and remaining() is None
    require_read_command('submit-prepared-order')


@pytest.mark.parametrize('command', ['prepare-order','submit-prepared-order','cancel-order',
    'unlock-keychain','fill-login-keychain','terminate-rejected-session','acknowledge-submit-rejection'])
def test_broker_actions_are_forbidden_during_deferred_readback(command):
    with original_readback(deadline()), pytest.raises(RuntimeError,match='BROKER_WRITE_FORBIDDEN'):
        require_read_command(command)


def test_helper_timeout_is_clamped_to_original_remaining_seconds(tmp_path):
    runner=HelperRunner(_receipt())
    client=FounderscNativeAXClient(helper_path=_helper(tmp_path),runner=runner,timeout_seconds=12)
    with original_readback(deadline(.5)):
        client.probe()
    assert 0<runner.calls[0][1]['timeout']<=.5


def test_secret_boundary_is_rejected_before_keychain_or_helper(tmp_path):
    runner=HelperRunner(_receipt())
    client=FounderscNativeAXClient(helper_path=_helper(tmp_path),runner=runner)
    with original_readback(deadline()), pytest.raises(RuntimeError,match='BROKER_WRITE_FORBIDDEN'):
        client.unlock_from_keychain(explicitly_enabled=True)
    assert runner.calls==[]


def test_queued_file_lock_cannot_outlive_original_readback_budget(tmp_path):
    with (tmp_path/'lease').open('a+b') as holder, (tmp_path/'lease').open('a+b') as queued:
        fcntl.flock(holder.fileno(),fcntl.LOCK_EX)
        with original_readback(deadline(.02)), pytest.raises(ReadbackDeadlineExpired):
            file_lock(queued.fileno())


def test_queued_thread_lock_cannot_outlive_original_readback_budget():
    lock=threading.Lock()
    lock.acquire()
    try:
        with original_readback(deadline(.02)), pytest.raises(ReadbackDeadlineExpired):
            with mutex(lock):
                pytest.fail('contended lock acquired')
    finally:
        lock.release()


def test_already_expired_scope_never_starts_an_observation():
    with pytest.raises(ReadbackDeadlineExpired):
        with original_readback(deadline(-1)):
            pytest.fail('expired scope entered')
    assert not active()


def test_post_business_readiness_cannot_claim_a_password_attempt(tmp_path):
    native=FakeNative(surface_state='authentication_required')
    adapter=_adapter(native)
    with original_readback(deadline()), pytest.raises(RuntimeError,match='AUTHENTICATION_REQUIRED_NO_ATTEMPT'):
        adapter.ensure_native_ready(unlock_once=True)
    assert native.unlock_calls==0 and not adapter.credential_health


def test_current_claim_may_keep_existing_known_rejection_ack_but_nested_old_history_cannot():
    with original_readback(deadline(),allow_known_rejection_ack=True):
        require_read_command('acknowledge-submit-rejection')
        with original_readback(deadline()):
            with pytest.raises(RuntimeError,match='BROKER_WRITE_FORBIDDEN'):
                require_read_command('acknowledge-submit-rejection')
        require_read_command('acknowledge-submit-rejection')
    with original_readback(deadline()):
        with original_readback(deadline(),allow_known_rejection_ack=True):
            with pytest.raises(RuntimeError,match='BROKER_WRITE_FORBIDDEN'):
                require_read_command('acknowledge-submit-rejection')


def test_actual_current_wait_port_bounds_execution_lock_and_retains_ack(tmp_path):
    from tests.test_book_b_preopen_batch import _plan, _ack
    from xiaocao.live.trading_execution import ExecutionStore, ExecutionState
    from xiaocao.live.morning_order_wait import await_claimed_orders
    plan=_plan();rows=[_ack(plan)]
    store=ExecutionStore(tmp_path/'events.jsonl')
    store.append(plan=plan,receipt=rows[0])
    seen=[]
    with store.lock_path.open('a+b') as writer:
        fcntl.flock(writer.fileno(),fcntl.LOCK_EX)
        await_claimed_orders([plan],rows,reconcile=lambda _:store.current(plan.plan_id),
            deadline=deadline(.03),now=lambda:datetime.now(timezone.utc),
            sleep=lambda _:pytest.fail('deadline wait should not sleep'),on_progress=lambda r:seen.append(r[0].state))
    assert rows[0].state==ExecutionState.ACKNOWLEDGED
    assert seen and all(state==ExecutionState.ACKNOWLEDGED for state in seen)


def test_actual_current_wait_port_observes_only_claims_without_an_order_action():
    from dataclasses import replace
    from tests.test_book_b_preopen_batch import _plan, _ack
    from xiaocao.live.trading_execution import ExecutionState
    from xiaocao.live.morning_order_wait import await_claimed_orders
    plan=_plan();rows=[_ack(plan)];calls=[]
    def read(old):
        assert active() and old.plan_hash==plan.plan_hash
        with pytest.raises(RuntimeError,match='BROKER_WRITE_FORBIDDEN'):
            require_read_command('submit-prepared-order')
        calls.append(old.plan_id)
        return replace(rows[0],state=ExecutionState.CANCELLED,active=False)
    await_claimed_orders([plan],rows,reconcile=read,deadline=deadline(),
        now=lambda:datetime.now(timezone.utc),sleep=lambda _:pytest.fail('terminal should not wait'),on_progress=lambda _:None)
    assert calls==[plan.plan_id] and rows[0].state==ExecutionState.CANCELLED


def test_actual_progress_notice_never_reenters_contended_store_after_deadline(tmp_path):
    from tests.test_book_b_preopen_batch import _plan, _ack
    from xiaocao.live.trading_execution import ExecutionStore
    from xiaocao.live.morning_order_wait import await_claimed_orders
    from xiaocao.live.morning_observability import terminal_notice
    plan=_plan();rows=[_ack(plan)];seen=[]
    store=ExecutionStore(tmp_path/'events.jsonl');store.append(plan=plan,receipt=rows[0])
    def progress(current):
        assert active(), 'expired scope retried a durable evidence lookup'
        seen.append('bounded_progress')
        terminal_notice({'execution_receipts':[r.as_dict() for r in current]},tmp_path/'runs/history/original.json')
    with store.lock_path.open('a+b') as holder:
        fcntl.flock(holder.fileno(),fcntl.LOCK_EX)
        result=await_claimed_orders([plan],rows,reconcile=lambda _:pytest.fail('progress should exhaust budget'),
            deadline=deadline(.03),now=lambda:datetime.now(timezone.utc),
            sleep=lambda _:pytest.fail('deadline must not sleep'),on_progress=progress)
    assert result['status']=='pending_original_deadline' and seen==['bounded_progress']


def test_terminal_notice_after_deadline_uses_only_memory_and_preserves_current_uncertainty(tmp_path):
    from tests.test_book_b_preopen_batch import _plan, _ack
    from xiaocao.live.trading_execution import ExecutionStore
    from xiaocao.live.morning_observability import bounded_terminal_notice
    from xiaocao.live.morning_notifications import current_result_fingerprint
    plan=_plan();receipt=_ack(plan)
    store=ExecutionStore(tmp_path/'events.jsonl');store.append(plan=plan,receipt=receipt)
    payload={'execution_receipts':[receipt.as_dict()],'order_wait':{'discovery_complete':False}}
    with store.lock_path.open('a+b') as holder:
        fcntl.flock(holder.fileno(),fcntl.LOCK_EX)
        notice=bounded_terminal_notice(payload,tmp_path/'runs/history/original.json',deadline=deadline(-1))
    assert notice['current_order_evidence_unproven'] and notice['pending_evidence_unproven']
    known={**notice,'current_order_evidence_unproven':False}
    assert current_result_fingerprint(notice)==current_result_fingerprint(known)
    assert current_result_fingerprint(known)==current_result_fingerprint({k:v for k,v in known.items()
        if k!='current_order_evidence_unproven'})


def test_current_claim_discovery_finds_interrupted_submit_without_executing_again(tmp_path):
    from dataclasses import replace
    from tests.test_book_b_preopen_batch import _plan, _ack
    from xiaocao.live.trading_execution import ExecutionStore, ExecutionState
    from xiaocao.live.morning_order_wait import await_claimed_orders
    plan=_plan();store=ExecutionStore(tmp_path/'events.jsonl');rows=[]
    claimed=store.append(plan=plan,receipt=replace(_ack(plan),state=ExecutionState.UNKNOWN,
        submit_chain_uncertain=True))
    calls=[]
    def reconcile(old):
        calls.append(old.plan_id)
        return store.append(plan=old,receipt=replace(claimed,state=ExecutionState.CANCELLED,active=False))
    result=await_claimed_orders([plan],rows,reconcile=reconcile,deadline=deadline(),
        now=lambda:datetime.now(timezone.utc),sleep=lambda _:pytest.fail('terminal must not wait'),
        on_progress=lambda _:None,read_existing=lambda p:store.current(p.plan_id))
    assert result['discovery_complete'] and rows[0].state==ExecutionState.CANCELLED
    assert calls==[plan.plan_id] and rows[0].submit_claim_id==claimed.submit_claim_id


def test_checklist_audit_lock_also_uses_the_active_original_deadline(tmp_path):
    from xiaocao.live.morning_checklist import MorningChecklist
    checklist=MorningChecklist.create(tmp_path,{'owner_thread_id':'original','trade_date':'2026-10-30'})
    with checklist.path.with_suffix('.lock').open('a+b') as holder:
        fcntl.flock(holder.fileno(),fcntl.LOCK_EX)
        with original_readback(deadline(.03)),pytest.raises(ReadbackDeadlineExpired):
            checklist.record('orders','pending',evidence={'status':'known_current_ack'})


def test_runner_audit_lock_degrades_immediately_with_original_budget_still_available(tmp_path):
    from xiaocao.live.morning_checklist import MorningChecklist
    checklist=MorningChecklist.create(tmp_path,{'owner_thread_id':'original','trade_date':'2026-10-30'})
    with checklist.path.with_suffix('.lock').open('a+b') as holder:
        fcntl.flock(holder.fileno(),fcntl.LOCK_EX)
        with original_readback(deadline(10)),pytest.raises(BlockingIOError):
            checklist.record('orders','pending',evidence={'status':'known_current_ack'},nonblocking=True)
