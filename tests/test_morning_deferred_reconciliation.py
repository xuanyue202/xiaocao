"""Deferred history is consumed after business with the exact original owner."""
import json
import fcntl
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_inherited_execution_isolation import old_buy
from xiaocao.automation_run import runner_identity
from xiaocao.live.bounded_readback import active, require_read_command
from xiaocao.live.morning_deferred_reconciliation import reconcile_deferred
from xiaocao.live.trading_execution import ExecutionStore

pytestmark=pytest.mark.app_simulation


def original(root,monkeypatch,*,seconds=30,status='completed'):
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-book-b-live-morning')
    monkeypatch.setenv('CODEX_THREAD_ID','original-thread')
    plan,saved=old_buy(root)
    body={'run_id':'2026-10-30-original','trade_date':'2026-10-30','state_path':str(root),
        'runner_identity':runner_identity('xiaocao-book-b-live-morning','scripts/book_b_live_morning.py'),
        'status':status,'preparation_deadline':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(),
        'deferred_prior_day_buy_plan_ids':[plan.plan_id], 'deferred_prior_day_sell_plan_ids':[]}
    path=root/'runs/history/2026-10-30-original.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(body))
    return plan,saved,path


def document(ref):
    return json.loads(Path(ref['path']).read_text())


def test_original_owner_reads_exact_old_claim_once_without_rewriting_opening_result(tmp_path,monkeypatch):
    plan,saved,path=original(tmp_path,monkeypatch)
    raw=path.read_bytes();calls=[]
    def read(old):
        assert active() and old.plan_hash==plan.plan_hash
        calls.append(old.plan_id)
        return ExecutionStore(tmp_path/'events.jsonl').append(plan=old,
            receipt=replace(saved,reason='NATIVE_HISTORY_QUERY_CAPTURE_INCOMPLETE'))
    ref=reconcile_deferred(tmp_path,path,reconcile=read)
    body=document(ref)
    assert calls==[plan.plan_id] and path.read_bytes()==raw
    assert body['results'][0]['receipt']['state']=='unknown'
    assert not body['budget_extended'] and body['unobserved_plan_ids']==[]
    assert body['incident_dispositions']['admission_authority']=='none'


@pytest.mark.parametrize('change', ['thread','pid'])
def test_another_owner_or_unresolved_current_batch_cannot_run_history(tmp_path,monkeypatch,change):
    _,_,path=original(tmp_path,monkeypatch)
    if change=='thread':monkeypatch.setenv('CODEX_THREAD_ID','other-thread')
    if change=='pid':
        body=json.loads(path.read_text());body['runner_identity']['runner_pid']=os.getpid()+1
        path.write_text(json.dumps(body))
    def forbidden(plan):pytest.fail('wrong owner entered history')
    with pytest.raises(ValueError,match='ORIGINAL_OWNER_UNPROVEN'):
        reconcile_deferred(tmp_path,path,reconcile=forbidden)


def test_deadline_records_exact_unobserved_ids_without_a_query_or_new_budget(tmp_path,monkeypatch):
    plan,_,path=original(tmp_path,monkeypatch,seconds=-1)
    def forbidden(plan):pytest.fail('expired original budget queried APP')
    body=document(reconcile_deferred(tmp_path,path,reconcile=forbidden))
    assert body['results']==[] and body['unobserved_plan_ids']==[plan.plan_id]
    assert not body['budget_extended']


def test_a_callback_cannot_cross_the_read_only_native_boundary(tmp_path,monkeypatch):
    plan,saved,path=original(tmp_path,monkeypatch)
    def broken(old):
        require_read_command('cancel-order')
        pytest.fail('write passed the read-only scope')
    body=document(reconcile_deferred(tmp_path,path,reconcile=broken))
    assert body['results'][0]['reason']=='ORIGINAL_READBACK_BROKER_WRITE_FORBIDDEN'
    assert ExecutionStore(tmp_path/'events.jsonl').current(plan.plan_id)==saved


def test_contended_execution_history_respects_deadline_before_any_app_query(tmp_path,monkeypatch):
    plan,_,path=original(tmp_path,monkeypatch,seconds=.03)
    def forbidden(plan):pytest.fail('contended history reached APP')
    with (tmp_path/'events.jsonl.lock').open('a+b') as writer:
        fcntl.flock(writer.fileno(),fcntl.LOCK_EX)
        body=document(reconcile_deferred(tmp_path,path,reconcile=forbidden))
    assert body['results'][0]['reason']=='ORIGINAL_READBACK_DEADLINE_EXHAUSTED'
    assert body['results'][0]['plan_id']==plan.plan_id
    assert not body['budget_extended']


@pytest.mark.parametrize('status', ['blocked','failed','unresolved'])
def test_recoverable_failure_returns_promptly_without_old_history_or_losing_ids(tmp_path,monkeypatch,status):
    plan,_,path=original(tmp_path,monkeypatch,status=status)
    def forbidden(plan):pytest.fail('current failed business waited on old history')
    body=document(reconcile_deferred(tmp_path,path,reconcile=forbidden))
    assert body['deferred_reason']=='CURRENT_BUSINESS_NOT_TERMINAL'
    assert body['results']==[] and body['unobserved_plan_ids']==[plan.plan_id]


def test_current_ack_blocks_old_history_even_if_rollup_claims_completed(tmp_path,monkeypatch):
    from xiaocao.live.trading_execution import ExecutionState
    plan,_,path=original(tmp_path,monkeypatch)
    current,saved=old_buy(tmp_path,code='000001.XSHE',day='2026-10-30',state=ExecutionState.ACKNOWLEDGED)
    body=json.loads(path.read_text())
    body['execution_receipts']=[saved.as_dict()];body['persisted_plan_ids']=[current.plan_id]
    path.write_text(json.dumps(body))
    def forbidden(plan):pytest.fail('current ACK was abandoned for old history')
    result=document(reconcile_deferred(tmp_path,path,reconcile=forbidden))
    assert result['deferred_reason']=='CURRENT_ORDER_TERMINAL_UNPROVEN'
    assert result['unobserved_plan_ids']==[plan.plan_id]
