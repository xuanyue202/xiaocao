"""Inherited audit uncertainty bounds current admission; no broker effects."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal

import pytest

from tests.test_book_b_available_capital import activate
from tests.test_foundersc_native_broker import _plan
from xiaocao.live.book_b_capital import digest
from xiaocao.live.book_b_live_morning import (bind_durable_live_plan_intents,
    load_book_b_live_capital_basis, _load_allocation, BookBLiveMorningConfig,
    run_book_b_live_morning)
from xiaocao.live.buy_preflight import pretrade_account, allocation_from_buy_preflight
from xiaocao.live.inherited_execution import verify
from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionState, ExecutionStore

pytestmark = pytest.mark.app_simulation
NOW = datetime(2026, 10, 30, 1, 25, tzinfo=timezone.utc)
BINDING = 'a' * 64


def snapshot(now=NOW, *, available=30000, balance=None, rows=(), codes=('688028',)):
    positions = {'scope': 'new_buy_preflight', 'observed_at': now.isoformat(),
        'rows': list(rows), 'row_count': len(rows), 'scoped_codes': list(codes),
        'summary_values': {'可用': str(available)}}
    if balance is not None:
        positions['summary_values']['余额'] = str(balance)
    body = {'schema_version': 'book-b-buy-preflight.v1', 'trade_date': now.date().isoformat(),
        'logical_account_id': 'primary', 'account_binding': 'proven',
        'fund_account_binding_sha256': BINDING, 'observed_at': now.isoformat(),
        'available_cash': float(available), 'positions': positions}
    return {**body, 'snapshot_sha256': digest(body)}


def old_buy(root, *, code='688028.XSHG', day='2026-10-29', shares=100, price=10, state=ExecutionState.UNKNOWN):
    stamp = datetime.fromisoformat(day + 'T01:25:00+00:00')
    plan = replace(_plan(), code=code, plan_id=f'book-b:{day}:{code}:BUY', trade_date=day,
        created_at=stamp, recovery_deadline=stamp+timedelta(minutes=10), shares=shares,
        limit_price=price, basket_price=price+.1)
    bind_durable_live_plan_intents(root, [plan])
    store = ExecutionStore(root / 'events.jsonl')
    receipt = store.append(plan=plan, receipt=ExecutionReceipt(plan.plan_id, plan.plan_hash,
        state, submit_claim_id='original-claim', submit_chain_uncertain=True,
        remaining_shares=shares, account_binding='proven',
        locator_proof={'fund_account_binding_sha256': BINDING}))
    return plan, receipt


def marked(root, snap):
    activate(root, BINDING)
    return pretrade_account(root, snap, trade_date=snap['trade_date'], now=datetime.fromisoformat(snap['observed_at']))


def test_bounded_prior_buy_does_not_prevent_current_scoped_account(tmp_path):
    old, saved = old_buy(tmp_path)
    before = (tmp_path/'events.jsonl').read_bytes()
    account = marked(tmp_path, snapshot())
    assert account.cash == account.settled_nav == 30000
    proof = account.accounting['inherited_buy_isolation']
    assert float(proof['new_buy_cash_limit']) == 28999.9
    assert float(proof['potential_exposure_upper_bound']) == 1000
    assert account.accounting['cumulative_pnl'] is None
    assert (tmp_path/'events.jsonl').read_bytes() == before
    assert ExecutionStore(tmp_path/'events.jsonl').current(old.plan_id) == saved


@pytest.mark.parametrize('available,balance,expected_cash,expected_risk', [
    (30000, 30000, 28999.9, 30000),
    (28999.9, 30000, 28999.9, 30000),
    (20000, 20000, 18999.9, 20000),
])
def test_reserve_does_not_double_charge_reflected_cash_or_mint_loss(tmp_path, available, balance, expected_cash, expected_risk):
    old_buy(tmp_path)
    account = marked(tmp_path, snapshot(available=available, balance=balance))
    proof = account.accounting['inherited_buy_isolation']
    assert float(proof['new_buy_cash_limit']) == expected_cash
    assert account.cash == account.settled_nav == 30000
    assert float(account.accounting['conservative_risk_nav']) == expected_risk
    assert account.accounting['cash_difference'] is None
    assert not (tmp_path/'capital_flows.jsonl').exists()


def test_possible_exposure_is_reserved_without_absorbing_manual_positions(tmp_path):
    old_buy(tmp_path)
    row = {'证券代码': '688028', '证券数量': '5000', '可卖数量': '5000', '当前价': '30'}
    account = marked(tmp_path, snapshot(rows=[row]))
    assert account.lots == () and account.current_open_exposure == 0
    assert float(account.accounting['inherited_buy_isolation']['potential_exposure_upper_bound']) == 3000


@pytest.mark.parametrize('fault,error', [('scope', 'POSITION_SCOPE'), ('mark', 'MARK_UNPROVEN')])
def test_unbounded_current_fact_is_an_explicit_dependency(tmp_path, fault, error):
    old_buy(tmp_path)
    snap = snapshot(rows=[{'证券代码':'688028', '证券数量':'100', '可卖数量':'100', '当前价':'bad'}])
    if fault == 'scope':
        snap['positions']['scoped_codes'] = []
    elif fault == 'balance':
        snap['positions']['rows'] = []
        snap['positions']['summary_values']['余额'] = '1'
    snap.pop('snapshot_sha256');snap['snapshot_sha256']=digest(snap)
    with pytest.raises(ValueError, match=error):
        marked(tmp_path, snap)


def test_same_day_unknown_and_cross_account_identity_stay_blocked(tmp_path):
    old_buy(tmp_path, day=NOW.date().isoformat())
    with pytest.raises(ValueError, match='OWNED_ORDER_RECONCILE_REQUIRED'):
        marked(tmp_path, snapshot())
    snap = snapshot();snap['fund_account_binding_sha256']='b'*64
    snap.pop('snapshot_sha256');snap['snapshot_sha256']=digest(snap)
    with pytest.raises(ValueError):
        pretrade_account(tmp_path, snap, trade_date=snap['trade_date'], now=NOW)


def test_freshness_and_immutable_evidence_are_checked(tmp_path):
    old_buy(tmp_path)
    account = marked(tmp_path, snapshot())
    proof = account.accounting['inherited_buy_isolation']
    assert verify(tmp_path, proof, now=NOW) == proof
    with pytest.raises(ValueError, match='BUY_PREFLIGHT_PROOF_INVALID'):
        verify(tmp_path, proof, now=NOW+timedelta(seconds=61))
    path=Path(proof['snapshot_path']);path.write_text('{}')
    with pytest.raises(ValueError, match='SNAPSHOT_HASH'):
        verify(tmp_path, proof)


def test_allocation_consumes_both_cash_and_exposure_bounds(tmp_path):
    old_buy(tmp_path, shares=2000)
    snap=snapshot()
    account=marked(tmp_path,snap)
    basis=load_book_b_live_capital_basis(tmp_path,trade_date=snap['trade_date'],current_account=account)
    payload=allocation_from_buy_preflight(snap,basis,now=NOW)
    config=BookBLiveMorningConfig(snap['trade_date'],tmp_path/'freeze',tmp_path/'allocation',tmp_path)
    facts=_load_allocation(config,payload)
    assert facts.available_cash==9998 and facts.current_open_exposure==20000
    assert facts.cash_limit==9998
    assert payload['available_cash']==30000 and payload['current_open_exposure']==0


def test_original_morning_reaches_independent_order_before_old_history(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    config=_morning(tmp_path)
    config.state_dir.mkdir()
    old, saved=old_buy(config.state_dir, day='2026-08-21')
    activate(config.state_dir,BINDING)
    snap=snapshot(MORNING)
    account=pretrade_account(config.state_dir,snap,trade_date=config.trade_date,now=MORNING)
    basis=load_book_b_live_capital_basis(config.state_dir,trade_date=config.trade_date,current_account=account)
    payload=allocation_from_buy_preflight(snap,basis,now=MORNING)
    calls=[]
    def execute(plan):
        assert plan.plan_id!=old.plan_id, 'old history consumed the current batch'
        calls.append(plan)
        return ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.CANCELLED,remaining_shares=plan.shares)
    receipt=run_book_b_live_morning(config,execute=execute,now=lambda:MORNING,
        risk_provider=_risk,read_allocation_facts=lambda:payload)
    assert receipt.status=='completed',receipt.reason
    assert len(calls)==1 and calls[0].code=='000001.XSHE'
    assert receipt.deferred_prior_day_buy_plan_ids==(old.plan_id,)
    assert ExecutionStore(config.state_dir/'events.jsonl').current(old.plan_id)==saved


@pytest.mark.parametrize('code',['688028.XSHG','000001.XSHE'])
def test_old_canary_sell_deferral_keeps_independent_buy_and_same_code_fence_together(tmp_path,code):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    config=_morning(tmp_path);config.state_dir.mkdir()
    stamp=MORNING-timedelta(days=3)
    old=replace(_plan(),side='SELL',code=code,owned_lot_id='original-owned-lot',
        plan_id=f'book-b-canary:{stamp.date()}:{code}:SELL',trade_date=str(stamp.date()),
        created_at=stamp,recovery_deadline=stamp+timedelta(minutes=10))
    folder=config.state_dir/'canary_intents';folder.mkdir()
    (folder/'original-sell.json').write_text(json.dumps({'schema_version':1,
        'plan_hash':old.plan_hash,'plan':old.canonical_payload()}))
    store=ExecutionStore(config.state_dir/'events.jsonl')
    saved=store.append(plan=old,receipt=ExecutionReceipt(old.plan_id,old.plan_hash,
        ExecutionState.UNKNOWN,submit_claim_id='old-sell-claim',remaining_shares=old.shares,
        account_binding='proven',next_action='reconcile_only'))
    activate(config.state_dir,BINDING);snap=snapshot(MORNING)
    account=pretrade_account(config.state_dir,snap,trade_date=config.trade_date,now=MORNING)
    basis=load_book_b_live_capital_basis(config.state_dir,trade_date=config.trade_date,current_account=account)
    payload=allocation_from_buy_preflight(snap,basis,now=MORNING)
    calls=[]
    def execute(plan):
        assert plan.plan_id!=old.plan_id,'old SELL consumed the current opening'
        calls.append(plan)
        return ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.CANCELLED,remaining_shares=plan.shares)
    receipt=run_book_b_live_morning(config,execute=execute,now=lambda:MORNING,
        risk_provider=_risk,read_allocation_facts=lambda:payload)
    assert receipt.deferred_prior_day_sell_plan_ids==(old.plan_id,)
    if code=='000001.XSHE':
        assert receipt.status=='no_action'
        assert any(row['reason']=='PRIOR_OPEN_SELL_SAME_CODE' and not row['allowed']
            for row in receipt.policy_consumptions)
        assert not calls and receipt.plan_count==0
        assert not list((config.state_dir/'plan_intents').glob('*.json'))
    else:
        assert receipt.status=='completed' and len(calls)==1 and calls[0].code=='000001.XSHE'
    assert store.current(old.plan_id)==saved
    from xiaocao.live.book_b_live_morning import reconcile_open_book_b_plans
    observed=[]
    assert reconcile_open_book_b_plans(config.state_dir,trade_date=config.trade_date,
        now=MORNING,execute=lambda plan:observed.append(plan) or saved,
        reconcile_proven_prior_day_sells=True)==(saved.as_dict(),)
    assert [row.plan_id for row in observed]==[old.plan_id]


def test_canary_old_sell_strict_zero_fill_and_economic_closure_use_original_family(tmp_path):
    from tests.test_book_b_live_lifecycle import _prior_zero_fill_sell_after_independent_exit
    from xiaocao.live.book_b_live_lifecycle import proven_prior_day_zero_fill_sell_ids,unresolved_prior_sell_codes
    from xiaocao.live.eod_reconciliation import historical_sell_resolutions
    old,now,store,saved,snap=_prior_zero_fill_sell_after_independent_exit(tmp_path,canary=True)
    before=(tmp_path/'events.jsonl').read_bytes()
    assert proven_prior_day_zero_fill_sell_ids(tmp_path,trade_date=snap['trade_date'],asof=now)==(old.plan_id,)
    proof=historical_sell_resolutions(tmp_path,snap,now=now)
    assert [row['plan_id'] for row in proof]==[old.plan_id]
    assert proof[0]['status']=='economically_closed' and store.current(old.plan_id)==saved
    assert old.code in unresolved_prior_sell_codes(tmp_path,trade_date=snap['trade_date'])
    assert (tmp_path/'events.jsonl').read_bytes()==before


@pytest.mark.parametrize('balance', ['bad', '1', None])
def test_optional_bad_balance_uses_available_lower_bound(tmp_path, balance):
    old_buy(tmp_path)
    account=marked(tmp_path,snapshot(balance=balance))
    assert float(account.accounting['inherited_buy_isolation']['new_buy_cash_limit'])==28999.9


@pytest.mark.parametrize('contradiction', ['price','quantity','negative_quantity','fractional_quantity',
    'code','mapping','receipt_price','remaining'])
def test_explicit_native_tuple_contradictions_never_get_intent_bound(tmp_path, contradiction):
    plan, saved=old_buy(tmp_path)
    native={'code':'688028','side':'buy','price':'10','quantity':100,'field_mapping_proven':True}
    extra={}
    if contradiction=='price':native['price']='100'
    if contradiction=='quantity':native['quantity']=10000
    if contradiction=='negative_quantity':native['quantity']=-1
    if contradiction=='fractional_quantity':native['quantity']='99.5'
    if contradiction=='code':native['code']='600001'
    if contradiction=='mapping':native['field_mapping_proven']=False
    if contradiction=='receipt_price':extra['order_price']=100
    if contradiction=='remaining':extra['remaining_shares']=10000
    store=ExecutionStore(tmp_path/'events.jsonl')
    store.append(plan=plan,receipt=replace(saved,locator_proof={**saved.locator_proof,'native_order_readback':native},**extra))
    # A later generic query cannot erase an earlier explicit contradiction.
    store.append(plan=plan,receipt=replace(saved,locator_proof={}))
    with pytest.raises(ValueError,match='EFFECT_BOUND_CONTRADICTED'):
        marked(tmp_path,snapshot())


def test_archived_isolation_survives_later_owned_fills_but_current_mark_requires_refresh(tmp_path):
    from tests.test_book_b_live_lifecycle import _record_fill, _plan as owned_plan
    old_buy(tmp_path)
    proof=marked(tmp_path,snapshot()).accounting['inherited_buy_isolation']
    _record_fill(tmp_path,owned_plan(),price=10,event_id='later-independent-fill')
    assert verify(tmp_path,proof,current=False)==proof
    with pytest.raises(ValueError,match='SOURCE_CHANGED'):
        verify(tmp_path,proof)


def test_real_unit_risk_accepts_bounded_history_without_latching_an_unclassified_loss(tmp_path):
    from tests.test_book_b_live_policy import _history, NOW as current
    from xiaocao.live.live_decision_support import evaluate_live_risk
    days=_history(tmp_path)
    old_buy(tmp_path,day='2026-08-31')
    row={'证券代码':'000001','证券数量':'2000','可卖数量':'2000','当前价':'10'}
    account=marked(tmp_path,snapshot(current,available=9998,balance=9998,rows=[row],codes=['000001','688028']))
    risk=evaluate_live_risk(tmp_path,now=current,account=account,trading_dates_provider=lambda _:days)
    assert risk.deploy_factor>0,risk.reasons
    assert not risk.pause_latched and account.accounting['cumulative_pnl'] is None


def test_review_wait_refreshes_bounds_before_binding_new_intent(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    config=_morning(tmp_path);config.state_dir.mkdir()
    old_buy(config.state_dir,day='2026-08-21',shares=2000)
    activate(config.state_dir,BINDING)
    clock=[MORNING];cash=[30000]
    def allocation():
        snap=snapshot(clock[0],available=cash[0],balance=cash[0])
        account=pretrade_account(config.state_dir,snap,trade_date=config.trade_date,now=clock[0])
        basis=load_book_b_live_capital_basis(config.state_dir,trade_date=config.trade_date,current_account=account)
        return allocation_from_buy_preflight(snap,basis,now=clock[0])
    def review(request):
        clock[0]+=timedelta(seconds=121);cash[0]=29000
        return {'status':'deferred','reason':'TEST_FINAL_REVIEW_TIMEOUT'}
    seen=[]
    def execute(plan):
        seen.append(plan)
        return ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.CANCELLED,remaining_shares=plan.shares)
    result=run_book_b_live_morning(config,execute=execute,now=lambda:clock[0],risk_provider=_risk,
        read_allocation_facts=allocation,review_rendezvous=review)
    assert result.status=='completed',result.reason
    assert len(seen)==1 and seen[0].notional*1.0001<=8998


def test_native_batch_drop_is_checked_before_prepare_or_submit_without_resizing_intents(tmp_path):
    from contextlib import contextmanager
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    config=_morning(tmp_path);config.state_dir.mkdir()
    old_buy(config.state_dir,day='2026-08-21',shares=2000)
    activate(config.state_dir,BINDING)
    cash=[30000]
    def allocation():
        snap=snapshot(MORNING,available=cash[0],balance=cash[0])
        account=pretrade_account(config.state_dir,snap,trade_date=config.trade_date,now=MORNING)
        basis=load_book_b_live_capital_basis(config.state_dir,trade_date=config.trade_date,current_account=account)
        return allocation_from_buy_preflight(snap,basis,now=MORNING)
    @contextmanager
    def batch(plans):
        cash[0]=29000
        yield
    seen=[]
    result=run_book_b_live_morning(config,execute=lambda p:seen.append(p),now=lambda:MORNING,
        risk_provider=_risk,read_allocation_facts=allocation,submission_scope=batch)
    assert result.status=='blocked' and result.reason=='LIVE_INHERITED_BUY_ACTION_BUDGET_CHANGED'
    assert seen==[]
    current=[json.loads(p.read_text()) for p in (config.state_dir/'plan_intents').glob('*.json')
             if json.loads(p.read_text())['plan']['trade_date']==config.trade_date]
    assert len(current)==1 and current[0]['plan']['shares']==900


def test_same_code_old_buy_stays_fenced_before_a_new_intent(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    config=_morning(tmp_path);config.state_dir.mkdir()
    old,saved=old_buy(config.state_dir,code='000001.XSHE',day='2026-08-21')
    snap=snapshot(MORNING,codes=['000001'])
    account=marked(config.state_dir,snap)
    basis=load_book_b_live_capital_basis(config.state_dir,trade_date=config.trade_date,current_account=account)
    payload=allocation_from_buy_preflight(snap,basis,now=MORNING)
    def forbidden(plan):
        pytest.fail('same code reached execution')
    result=run_book_b_live_morning(config,execute=forbidden,now=lambda:MORNING,
        risk_provider=_risk,read_allocation_facts=lambda:payload)
    assert result.plan_count==0
    assert not any(json.loads(p.read_text())['plan']['trade_date']==config.trade_date
        for p in (config.state_dir/'plan_intents').glob('*.json'))
    assert ExecutionStore(config.state_dir/'events.jsonl').current(old.plan_id)==saved


def test_old_canary_uses_its_own_canonical_intent_without_a_global_history_wait(tmp_path):
    stamp=NOW-timedelta(days=1)
    plan=replace(_plan(),plan_id='book-b-canary:2026-10-29:688028.XSHG:BUY',code='688028.XSHG',
        trade_date='2026-10-29',created_at=stamp,recovery_deadline=stamp+timedelta(minutes=10))
    folder=tmp_path/'canary_intents';folder.mkdir()
    (folder/'original.json').write_text(json.dumps({'schema_version':1,'plan_hash':plan.plan_hash,
        'plan':plan.canonical_payload()}))
    ExecutionStore(tmp_path/'events.jsonl').append(plan=plan,receipt=ExecutionReceipt(plan.plan_id,
        plan.plan_hash,ExecutionState.UNKNOWN,submit_claim_id='original-canary',submit_chain_uncertain=True,
        remaining_shares=plan.shares,account_binding='proven'))
    account=marked(tmp_path,snapshot())
    assert account.accounting['inherited_buy_isolation']['plan_bounds'][0]['plan_id']==plan.plan_id
    assert not (tmp_path/'plan_intents').exists()


@pytest.mark.parametrize('bound,latched,previous_cap,expected', [
    (30000,False,1,1),(27000,False,1,.5),(24000,False,1,0),
    (33000,False,.5,.5),(33000,True,1,0),(0,False,1,0)])
def test_under_lease_risk_cap_only_tightens_the_existing_peak_and_pause(bound,latched,previous_cap,expected):
    from tests.test_book_b_live_policy import _risk
    from xiaocao.live.account_risk import tighten_conservative_new_risk_cap
    risk=replace(_risk(),pause_latched=latched,deploy_factor=previous_cap)
    before=risk.as_dict()
    assert tighten_conservative_new_risk_cap(risk,Decimal(bound))==expected
    assert risk.as_dict()==before


def test_native_locale_numbers_use_original_adapter_semantics_without_rewriting_evidence(tmp_path):
    plan,saved=old_buy(tmp_path,shares=1000,price=17.39)
    native={'code':'688028','side':'B','price':'17,3900','quantity':'1,000','field_mapping_proven':True}
    ExecutionStore(tmp_path/'events.jsonl').append(plan=plan,
        receipt=replace(saved,locator_proof={**saved.locator_proof,'native_order_readback':native}))
    before=(tmp_path/'events.jsonl').read_bytes()
    account=marked(tmp_path,snapshot())
    proof=account.accounting['inherited_buy_isolation']
    assert float(proof['new_buy_cash_limit'])==12608.26
    assert (tmp_path/'events.jsonl').read_bytes()==before


def test_batch_failure_still_observes_current_claims_before_old_business(tmp_path):
    from contextlib import contextmanager
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    from tests.test_book_b_preopen_batch import _ack
    config=_morning(tmp_path)
    held=[False];calls=[]
    @contextmanager
    def batch(plans):
        held[0]=True
        try:yield
        finally:held[0]=False
    def failed_observer(rows):
        raise RuntimeError('CURRENT_PROGRESS_FAILED')
    def observe(plans,rows):
        assert not held[0]
        calls.append('current_claim_readback')
        rows[0]=replace(rows[0],state=ExecutionState.CANCELLED,active=False)
    result=run_book_b_live_morning(config,execute=_ack,now=lambda:MORNING,risk_provider=_risk,
        submission_scope=batch,on_order_progress=failed_observer,await_order_results=observe)
    assert result.status=='blocked' and result.reason=='CURRENT_PROGRESS_FAILED'
    assert calls==['current_claim_readback']
    assert result.execution_receipts[0]['state']=='cancelled'
    assert result.post_failure_readback['status']=='terminal'


def test_a_failed_current_wait_is_preserved_without_a_second_callback_or_old_history(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    from tests.test_book_b_preopen_batch import _ack
    config=_morning(tmp_path);calls=[]
    def failed_wait(plans,rows):
        calls.append('readback_failure')
        raise RuntimeError('CURRENT_READBACK_UNPROVEN')
    result=run_book_b_live_morning(config,execute=_ack,now=lambda:MORNING,risk_provider=_risk,
        await_order_results=failed_wait)
    assert result.status=='blocked' and calls==['readback_failure']
    assert result.execution_receipts[0]['state']=='acknowledged'
    assert result.post_failure_readback['status']=='unproven'


@pytest.mark.parametrize('fault', ['second_claim','changed_counter'])
def test_one_intent_cannot_bound_two_unresolved_effects(tmp_path,fault):
    plan,saved=old_buy(tmp_path)
    store=ExecutionStore(tmp_path/'events.jsonl')
    if fault=='second_claim':
        store.append(plan=plan,receipt=replace(saved,submit_claim_id='another-unresolved-claim'))
    else:
        store.append(plan=plan,receipt=replace(saved,broker_order_id='1234567'))
        store.append(plan=plan,receipt=replace(saved,broker_order_id='1234568'))
    with pytest.raises(ValueError,match='MULTIPLE_UNRESOLVED_CLAIMS|ORDER_IDENTITY_CHANGED'):
        marked(tmp_path,snapshot())


@pytest.mark.parametrize('filled', [50,100])
def test_proved_canary_fill_replays_owned_lots_and_leaves_independent_buy_capacity(tmp_path,monkeypatch,filled):
    from types import SimpleNamespace
    from tests.test_book_b_live_policy import _history
    from xiaocao.live.trading_execution import (TradingExecution, BookBOwnershipEvidence,
        BrokerReceipt, BrokerStatus)
    from xiaocao.live.buy_preflight import current_buy_query_codes
    _history(tmp_path)
    stamp=NOW-timedelta(days=1)
    plan=replace(_plan(),plan_id='book-b-canary:2026-10-29:688028.XSHG:BUY',
        code='688028.XSHG',trade_date='2026-10-29',created_at=stamp,
        recovery_deadline=stamp+timedelta(minutes=10))
    folder=tmp_path/'canary_intents';folder.mkdir()
    source=folder/'original.json'
    source.write_text(json.dumps({'schema_version':1,'plan_hash':plan.plan_hash,'plan':plan.canonical_payload()}))
    original_bytes=source.read_bytes()
    store=ExecutionStore(tmp_path/'events.jsonl')
    store.append(plan=plan,receipt=ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.UNKNOWN,
        submit_claim_id='original-canary',submit_chain_uncertain=True,remaining_shares=100,account_binding='proven'))
    broker_receipt=BrokerReceipt(status=BrokerStatus.PARTIAL if filled<100 else BrokerStatus.FILLED,
        order_id='1234567',strategy_id='original-claim-derived',receipt_mapping=True,
        requested_shares=100,filled_shares=filled,remaining_shares=100-filled,
        fill_price=10,order_price=10,account_binding='proven',conclusive=True,active=filled<100,
        observed_at=NOW-timedelta(seconds=1))
    execution=TradingExecution(store=store,ledger=BookBOwnershipEvidence(tmp_path/'book_b_ownership_evidence.jsonl'),
        notifier=lambda *_:{'wecom':'test'},now=lambda:NOW-timedelta(seconds=1))
    with monkeypatch.context() as scoped:
        scoped.setattr('xiaocao.live.trading_execution._utcnow',lambda:NOW-timedelta(seconds=1))
        observed=execution.reconcile_existing(plan,SimpleNamespace(recover=lambda *_:broker_receipt))
    assert observed.filled_shares==filled
    if filled<100:
        store.append(plan=plan,receipt=replace(observed,state=ExecutionState.UNKNOWN,next_action='reconcile_only'))
    cash=round(9998-filled*10*1.0001,2)
    positions=[{'证券代码':'000001','证券数量':'2000','可卖数量':'2000','当前价':'10'},
        {'证券代码':'688028','证券数量':'1000','可卖数量':'1000','当前价':'10'}]
    snap=snapshot(available=cash,balance=cash,rows=positions,codes=['000001','688028'])
    account=marked(tmp_path,snap)
    assert {lot.owned_lot_id:lot.shares for lot in account.lots}[plan.plan_id]==filled
    assert account.current_open_exposure==20000+filled*10
    assert current_buy_query_codes(tmp_path,trade_date=snap['trade_date'])=={'000001.XSHE','688028.XSHG'}
    basis=load_book_b_live_capital_basis(tmp_path,trade_date=snap['trade_date'],current_account=account)
    payload=allocation_from_buy_preflight(snap,basis,now=NOW)
    facts=_load_allocation(BookBLiveMorningConfig(snap['trade_date'],tmp_path/'freeze',tmp_path/'allocation',tmp_path),
        payload,asof=NOW)
    assert facts.cash_limit>1000.1 and facts.current_open_exposure==21000
    assert account.accounting['cumulative_pnl'] is None
    assert source.read_bytes()==original_bytes
    assert not any(json.loads(p.read_text())['plan']['plan_id']==plan.plan_id
        for p in (tmp_path/'plan_intents').glob('*.json'))


def test_unclaimed_unusable_canary_file_is_not_a_current_financial_dependency(tmp_path):
    folder=tmp_path/'canary_intents';folder.mkdir()
    path=folder/'unused-test.json';path.write_text('unusable original test draft')
    account=marked(tmp_path,snapshot())
    assert account.cash==30000 and account.lots==()
    assert path.read_text()=='unusable original test draft'


def test_an_effectful_canary_without_its_original_source_stays_explicitly_unbounded(tmp_path):
    plan=replace(_plan(),plan_id='book-b-canary:2026-10-29:688028.XSHG:BUY',
        code='688028.XSHG',trade_date='2026-10-29')
    store=ExecutionStore(tmp_path/'events.jsonl')
    saved=store.append(plan=plan,receipt=ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.UNKNOWN,
        submit_claim_id='original-canary',submit_chain_uncertain=True,remaining_shares=100,account_binding='proven'))
    with pytest.raises(ValueError,match='INHERITED_BUY_INTENT_MISSING'):
        marked(tmp_path,snapshot())
    assert store.current(plan.plan_id)==saved


def test_expired_unclaimed_canary_is_closed_locally_without_an_old_app_query(tmp_path):
    from xiaocao.live.book_b_live_morning import reconcile_open_book_b_plans
    stamp=NOW-timedelta(days=1)
    plan=replace(_plan(),plan_id='book-b-canary:2026-10-29:688028.XSHG:BUY',
        code='688028.XSHG',trade_date='2026-10-29',created_at=stamp,
        recovery_deadline=stamp+timedelta(minutes=10))
    folder=tmp_path/'canary_intents';folder.mkdir()
    (folder/'original.json').write_text(json.dumps({'schema_version':1,'plan_hash':plan.plan_hash,
        'plan':plan.canonical_payload()}))
    store=ExecutionStore(tmp_path/'events.jsonl')
    store.append(plan=plan,receipt=ExecutionReceipt(plan.plan_id,plan.plan_hash,ExecutionState.PLANNED,
        remaining_shares=100,active=False))
    def forbidden(plan):pytest.fail('a no-effect local expiry queried APP')
    rows=reconcile_open_book_b_plans(tmp_path,trade_date='2026-10-30',now=NOW,
        execute=forbidden,defer_prior_day_buys=True,defer_prior_day_sells=True)
    assert rows[0]['state']=='skipped' and rows[0]['reason']=='UNSUBMITTED_INTENT_EXPIRED'
    assert store.current(plan.plan_id).submit_claim_id is None


def test_unexpected_exception_after_first_durable_claim_uses_only_original_readback(tmp_path):
    from tests.test_book_b_live_policy import _morning, _risk, MORNING
    from tests.test_book_b_preopen_batch import _ack
    from xiaocao.live.morning_order_wait import await_claimed_orders
    config=_morning(tmp_path);calls=[]
    store=ExecutionStore(config.state_dir/'events.jsonl')
    def interrupted(plan):
        calls.append('one_submit_boundary')
        store.append(plan=plan,receipt=replace(_ack(plan),state=ExecutionState.UNKNOWN,
            submit_chain_uncertain=True))
        raise TypeError('receipt shape changed after durable claim')
    def wait(plans,rows):
        def read(plan):
            calls.append('original_claim_readback')
            return store.append(plan=plan,receipt=replace(store.current(plan.plan_id),
                state=ExecutionState.CANCELLED,active=False))
        return await_claimed_orders(plans,rows,reconcile=read,
            deadline=datetime.now(timezone.utc)+timedelta(seconds=1),
            now=lambda:datetime.now(timezone.utc),sleep=lambda _:pytest.fail('terminal must not wait'),
            on_progress=lambda _:None,read_existing=lambda plan:store.current(plan.plan_id))
    result=run_book_b_live_morning(config,execute=interrupted,now=lambda:MORNING,risk_provider=_risk,
        await_order_results=wait)
    assert result.status=='blocked' and result.reason=='UNEXPECTED_EXECUTION_FAILURE:TypeError'
    assert calls==['one_submit_boundary','original_claim_readback']
    assert result.order_wait['discovery_complete'] and result.execution_receipts[0]['state']=='cancelled'
    assert result.execution_receipts[0]['submit_claim_id']
