"""Historical BUYs do not precede a lawful current owned-lot protective SELL."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_book_b_live_lifecycle import _record_fill, _plan as owned_plan, _snapshot
from tests.test_inherited_execution_isolation import old_buy, BINDING
from tests.test_book_b_available_capital import activate
from tests.test_foundersc_native_broker import _plan
from xiaocao.live.book_b_capital import digest
from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday
from xiaocao.live.book_b_live_recovery import check_monitor_pending_plans
from xiaocao.live.trading_execution import (ExecutionStore, ExecutionReceipt, ExecutionState,
    BookBOwnershipEvidence)
from xiaocao.live.trading_runner import frozen_rows_digest

pytestmark=pytest.mark.app_simulation
NOW=datetime(2026,9,1,2,25,tzinfo=timezone.utc)


def setup(root,monkeypatch,kind='normal',*,day='2026-08-30',same_code=False):
    root.mkdir(parents=True,exist_ok=True)
    owned=_record_fill(root,owned_plan(trade_date='2026-08-31'),price=10,event_id='owned')
    activate(root,BINDING)
    if kind=='normal':
        old,saved=old_buy(root,day=day,code='000001.XSHE' if same_code else '688028.XSHG')
    else:
        stamp=datetime.fromisoformat(day+'T01:25:00+00:00')
        code='688028.XSHG'
        rows=[{'book':'B','code':code,'profile':'v6','mode':'接力'}]
        freeze=root/f'book_b_live_freeze_{day}.jsonl'
        freeze.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        old=replace(_plan(),plan_id=f'book-b-canary:{day}:{code}:BUY',trade_date=day,code=code,
            created_at=stamp,recovery_deadline=stamp+timedelta(minutes=10),
            snapshot_ref=f'{freeze}:{day}:sha256:{frozen_rows_digest(rows)}:{code}')
        folder=root/'canary_intents';folder.mkdir()
        (folder/'original.json').write_text(json.dumps({'schema_version':1,'plan_hash':old.plan_hash,
            'plan':old.canonical_payload()}))
        store=ExecutionStore(root/'events.jsonl')
        filled=50 if kind=='partial_canary' else 0
        saved=store.append(plan=old,receipt=ExecutionReceipt(old.plan_id,old.plan_hash,
            ExecutionState.PARTIAL if filled else ExecutionState.UNKNOWN,
            submit_claim_id='old-claim',submit_chain_uncertain=True,
            remaining_shares=100-filled,filled_shares=filled,fill_price=10 if filled else None,
            broker_order_id='1234567' if filled else None,receipt_mapping=True if filled else None,
            account_binding='proven'))
        if filled:
            with monkeypatch.context() as scoped:
                scoped.setattr('xiaocao.live.trading_execution._utcnow',lambda:NOW-timedelta(seconds=1))
                BookBOwnershipEvidence(root/'book_b_ownership_evidence.jsonl').record(old,saved)
            saved=store.append(plan=old,receipt=replace(saved,state=ExecutionState.UNKNOWN,next_action='reconcile_only'))
    return owned,old,saved


def account_snapshot(kind,*,scope='full',fault=None):
    snap=_snapshot(shares=100,sellable=100,price=9.2,observed_at=NOW)
    rows=snap['tables']['positions']['rows']
    if kind=='partial_canary':
        rows.append({'证券代码':'688028','证券数量':'500','可卖数量':'500','当前价':'10',
            '最新市值':'5000','参考成本价':'10'})
        snap['tables']['positions']['row_count']=2
        for summary in ('broker_summary','funds_summary'):
            snap[summary].update(securities_market_value=5920,available_cash=94080,
                cash_balance=94080,withdrawable_cash=94080)
    if scope=='sellable':
        snap={'schema_version':'book-b-sellable-only.v1','source':'foundersc_native_app',
            'environment':'live','logical_account_id':'primary','account_binding':'proven',
            'trade_date':'2026-09-01','fund_account_binding_sha256':BINDING,'observed_at':NOW.isoformat(),
            'positions':{'scope':'sellable_only','capture_proven':True,'row_count':len(rows),
                'scoped_codes':[row['证券代码'] for row in rows], 'observed_at':NOW.isoformat(),'rows':rows}}
    if fault=='account':snap['fund_account_binding_sha256']='b'*64
    if fault=='quantity':rows[0]['证券数量']='99'
    if fault=='date':snap['trade_date']='2026-09-02'
    snap.pop('snapshot_sha256',None);snap['snapshot_sha256']=digest(snap)
    return snap


def statuses(lots):
    return [{'owned_lot_id':lot.owned_lot_id,'triggered':lot.code=='000001.XSHE',
        'sell_reason':'HARD_STOP','latest_price':9.2,'market_guard_status':'ok',
        'market_guard_observed_at':NOW,'market_guard_down_price':9.} for lot in lots]


def run(root,snapshot,calls):
    def execute(plan):
        assert plan.side=='SELL' and plan.code=='000001.XSHE','old BUY history preceded current exit'
        calls.append(plan)
        return ExecutionStore(root/'events.jsonl').append(plan=plan,receipt=ExecutionReceipt(plan.plan_id,
            plan.plan_hash,ExecutionState.CANCELLED,submit_claim_id='current-sell-claim',
            remaining_shares=plan.shares,broker_order_id='1234568',account_binding='proven',receipt_mapping=True))
    return run_book_b_live_intraday(state_dir=root,freeze_dir=root,trade_date='2026-09-01',phase='sparse',
        now=lambda:NOW,account_snapshot_provider=lambda:snapshot,status_provider=statuses,execute=execute)


@pytest.mark.parametrize('kind',['normal','canary','partial_canary'])
@pytest.mark.parametrize('scope',['full','sellable'])
def test_old_buy_history_never_precedes_current_independent_owned_exit(tmp_path,monkeypatch,kind,scope):
    owned,old,saved=setup(tmp_path,monkeypatch,kind)
    calls=[]
    result=run(tmp_path,account_snapshot(kind,scope=scope),calls)
    assert result.status=='executed' and len(calls)==1
    assert calls[0].owned_lot_id==owned.plan_id and calls[0].shares==100
    assert old.plan_id in result.deferred_buy_plan_ids
    assert ExecutionStore(tmp_path/'events.jsonl').current(old.plan_id)==saved


def test_same_code_old_buy_does_not_forbid_selling_independently_proved_prior_lot(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,same_code=True)
    calls=[]
    assert run(tmp_path,account_snapshot('normal'),calls).status=='executed'
    assert len(calls)==1


@pytest.mark.parametrize('scope',['full','sellable'])
@pytest.mark.parametrize('fault',['account','date','quantity'])
def test_deferral_never_relaxes_current_account_date_or_owned_quantity(tmp_path,monkeypatch,scope,fault):
    setup(tmp_path,monkeypatch)
    calls=[]
    with pytest.raises(ValueError):run(tmp_path,account_snapshot('normal',scope=scope,fault=fault),calls)
    assert calls==[]


def test_same_day_unknown_and_default_caller_remain_strict(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,day='2026-09-01')
    with pytest.raises(ValueError,match='OPEN_EXECUTION_RECONCILE_REQUIRED'):
        check_monitor_pending_plans(tmp_path,trade_date='2026-09-01',allow_open_sells=True,
            defer_prior_day_buys_for_owned_exit=True)
    other=tmp_path/'old';setup(other,monkeypatch)
    with pytest.raises(ValueError,match='OPEN_EXECUTION_RECONCILE_REQUIRED'):
        check_monitor_pending_plans(other,trade_date='2026-09-01',allow_open_sells=True)


def test_corrupt_old_event_chain_stays_a_real_dependency(tmp_path,monkeypatch):
    _,old,_=setup(tmp_path,monkeypatch)
    path=tmp_path/'events.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    next(row for row in rows if row['plan_id']==old.plan_id)['event_hash']='0'*64
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    calls=[]
    with pytest.raises(ValueError):run(tmp_path,account_snapshot('normal'),calls)
    assert calls==[]


@pytest.mark.parametrize('kind',['normal','canary','partial_canary'])
def test_actual_sparse_poll_claim_reaches_original_app_protection_seam(tmp_path,monkeypatch,kind):
    from tests.test_kol_trading_tick import tick
    root=tmp_path/'output/live/book_b_live_execution'
    _,old,saved=setup(root,monkeypatch,kind)
    result=tick.poll(tmp_path,now=NOW,owner_thread_id='original-sparse-owner')
    assert result['status']=='run' and old.plan_id in result['deferred_reconcile_plan_ids']
    calls=[]
    receipt=run(root,account_snapshot(kind),calls)
    assert receipt.status=='executed' and len(calls)==1
    assert ExecutionStore(root/'events.jsonl').current(old.plan_id)==saved
    assert tick.poll(tmp_path,now=NOW)['reason']=='RUNNING_CLAIM'


def test_eod_keeps_full_old_order_readback_and_strict_settlement(tmp_path,monkeypatch):
    _,old,saved=setup(tmp_path,monkeypatch)
    current=NOW.replace(hour=7,minute=1)
    snap=account_snapshot('normal')
    snap['observed_at']=current.isoformat()
    for table in snap['tables'].values():table['observed_at']=current.isoformat()
    snap.pop('snapshot_sha256');snap['snapshot_sha256']=digest(snap)
    calls=[]
    def read(plan):
        assert plan.plan_id==old.plan_id
        calls.append(plan.plan_id)
        return saved
    receipt=run_book_b_live_intraday(state_dir=tmp_path,trade_date='2026-09-01',phase='eod',
        now=lambda:current,account_snapshot_provider=lambda:snap,
        status_provider=lambda _:pytest.fail('EOD acquired a new exit decision'),execute=read)
    assert receipt.status=='blocked' and calls==[old.plan_id]
    assert receipt.deferred_buy_plan_ids==()
    assert old.plan_id in receipt.eod_review['active_plan_ids']


def test_one_old_lots_missing_strategy_source_does_not_suppress_independent_protective_exit(tmp_path,monkeypatch):
    _,old,saved=setup(tmp_path,monkeypatch,'partial_canary')
    (tmp_path/'book_b_live_freeze_2026-08-30.jsonl').unlink()
    calls=[]
    receipt=run(tmp_path,account_snapshot('partial_canary'),calls)
    assert receipt.status=='executed' and len(calls)==1
    assert receipt.deferred_monitor_lots[0]['owned_lot_id']==old.plan_id
    assert receipt.deferred_monitor_lots[0]['scope']=='strategy_source_unproven'
    assert ExecutionStore(tmp_path/'events.jsonl').current(old.plan_id)==saved


def claimed_canary_sell(root,owned,*,suffix='original'):
    plan=replace(_plan(),plan_id=f'book-b-canary:2026-09-01:000001.XSHE:SELL:{suffix}',
        trade_date='2026-09-01',created_at=NOW,recovery_deadline=NOW+timedelta(minutes=10),
        side='SELL',owned_lot_id=owned.plan_id,sell_authorized=True,sell_reason='HARD_STOP',
        sell_decision_phase='risk_floor',sell_decision_at=NOW,market_guard_required=True,
        market_guard_observed_at=NOW,market_guard_latest_price=9.2,market_guard_down_price=9.)
    folder=root/'canary_intents';folder.mkdir(exist_ok=True)
    (folder/f'{suffix}.json').write_text(json.dumps({'schema_version':1,
        'plan_hash':plan.plan_hash,'plan':plan.canonical_payload()}))
    saved=ExecutionStore(root/'events.jsonl').append(plan=plan,receipt=ExecutionReceipt(
        plan.plan_id,plan.plan_hash,ExecutionState.UNKNOWN,submit_claim_id=f'claim-{suffix}',
        submit_chain_uncertain=True,remaining_shares=plan.shares,account_binding='proven',
        next_action='reconcile_only'))
    return plan,saved


def test_same_day_canary_sell_keeps_original_claim_without_a_second_intent(tmp_path,monkeypatch):
    owned,_,_=setup(tmp_path,monkeypatch)
    plan,saved=claimed_canary_sell(tmp_path,owned)
    calls=[]
    def read_existing(seen):
        calls.append(seen)
        assert seen.plan_id==plan.plan_id and seen.plan_hash==plan.plan_hash
        return saved
    receipt=run_book_b_live_intraday(state_dir=tmp_path,freeze_dir=tmp_path,trade_date='2026-09-01',
        phase='sparse',now=lambda:NOW,account_snapshot_provider=lambda:account_snapshot('normal'),
        status_provider=statuses,execute=read_existing)
    assert receipt.status=='pending' and calls
    assert all(row.plan_id==plan.plan_id for row in calls)
    ordinary=[json.loads(p.read_text())['plan'] for p in (tmp_path/'plan_intents').glob('*.json')]
    assert not [raw for raw in ordinary if raw['side']=='SELL']
    assert ExecutionStore(tmp_path/'events.jsonl').current(plan.plan_id)==saved


def test_conflicting_same_day_same_lot_intents_never_choose_one_to_submit(tmp_path,monkeypatch):
    from xiaocao.live.book_b_live_intraday import _existing_sell_plan_for_lot
    owned,_,_=setup(tmp_path,monkeypatch)
    claimed_canary_sell(tmp_path,owned,suffix='one')
    claimed_canary_sell(tmp_path,owned,suffix='two')
    with pytest.raises(ValueError,match='LIVE_BOOK_B_SAME_LOT_SELL_INTENT_CONFLICT'):
        _existing_sell_plan_for_lot(tmp_path,trade_date='2026-09-01',owned_lot_id=owned.plan_id)
