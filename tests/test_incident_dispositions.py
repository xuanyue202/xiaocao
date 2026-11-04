"""EOD planning views are actually consumed, never financial authority."""
import json
import fcntl
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_inherited_execution_isolation import old_buy, marked, snapshot, NOW
from xiaocao.live.incident_dispositions import refresh, consume
from xiaocao.live.eod_reconciliation import assess_eod
from xiaocao.live.trading_execution import ExecutionReceipt, ExecutionStore, ExecutionState

pytestmark=pytest.mark.app_simulation


def document(ref):
    return json.loads(Path(ref['path']).read_text())


def test_eod_maintains_distinct_permission_repair_order_impact_and_next_window(tmp_path):
    plan,original=old_buy(tmp_path)
    account=marked(tmp_path,snapshot()).as_dict()
    report=assess_eod(tmp_path,account,now=NOW,persist=True)
    assert report['status']=='blocked' and report['active_plan_ids']==[plan.plan_id]
    ref=report['incident_dispositions'];row=document(ref)['records'][0]
    assert row['business_limit']['status']=='expected_exclusion'
    assert row['technical_repair']['status']=='loaded_guard_present'
    assert row['technical_repair']['natural_acceptance']=='not_inferred'
    assert row['service_order']['state']=='unknown' and not row['service_order']['terminal']
    assert row['current_economic_impact']['status']=='bounded_at_snapshot'
    assert not row['next_window']['accepted_handoff']
    assert ref['admission_authority']=='none'
    assert ExecutionStore(tmp_path/'events.jsonl').current(plan.plan_id)==original


def test_next_original_consumer_records_actual_input_without_promoting_it(tmp_path):
    old_buy(tmp_path)
    first=refresh(tmp_path,trade_date='2026-10-29',stage='eod',now=NOW-timedelta(hours=18))
    result=consume(tmp_path,trade_date='2026-10-30',run_id='original-current-owner',now=NOW)
    receipt=document(result)
    assert receipt['run_id']=='original-current-owner'
    assert receipt['prior_ref']==first and receipt['current_ref']==first
    assert receipt['admission_authority']=='none' and not receipt['accepted_handoff']


def test_stable_incident_id_survives_new_readback_and_preserves_formal_unknown(tmp_path):
    plan,original=old_buy(tmp_path)
    first=refresh(tmp_path,trade_date='2026-10-29',stage='eod',now=NOW-timedelta(hours=18))
    ExecutionStore(tmp_path/'events.jsonl').append(plan=plan,receipt=replace(original,reason='NATIVE_HISTORY_QUERY_CAPTURE_INCOMPLETE'))
    consumed=consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    receipt=document(consumed);new=document(receipt['current_ref'])
    assert receipt['source_advanced']
    assert new['records'][0]['incident_id']==document(first)['records'][0]['incident_id']
    assert new['records'][0]['service_order']['state']=='unknown'
    assert Path(first['path']).is_file()


def test_corrupt_derived_pointer_is_preserved_and_rebuilt_without_touching_orders(tmp_path):
    old_buy(tmp_path)
    refresh(tmp_path,trade_date='2026-10-29',stage='eod',now=NOW-timedelta(hours=18))
    before=(tmp_path/'events.jsonl').read_bytes()
    pointer=tmp_path/'incident_dispositions/latest.json';pointer.write_text('broken pointer')
    result=consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    assert result['derived_recovery']
    assert len(list((tmp_path/'incident_dispositions/quarantine').glob('*.json')))==1
    assert (tmp_path/'events.jsonl').read_bytes()==before
    assert document(result)['current_ref']['admission_authority']=='none'


def test_dated_empty_incident_view_never_claims_account_or_trading_readiness(tmp_path):
    result=consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    current=document(document(result)['current_ref'])
    assert current['records']==[] and current['admission_authority']=='none'
    assert current['fund_account_binding_sha256'] is None


def test_an_older_writer_cannot_roll_back_latest_or_erase_new_order_evidence(tmp_path):
    plan,original=old_buy(tmp_path)
    ExecutionStore(tmp_path/'events.jsonl').append(plan=plan,receipt=replace(original,reason='new exact readback'))
    current=refresh(tmp_path,trade_date='2026-10-30',stage='post_business',now=NOW)
    older=refresh(tmp_path,trade_date='2026-10-29',stage='eod',now=NOW-timedelta(hours=18))
    pointer=json.loads((tmp_path/'incident_dispositions/latest.json').read_text())
    assert pointer==current and not older['latest_pointer_updated']
    assert document(current)['execution_source']['event_count']==2
    assert Path(older['path']).is_file()


@pytest.mark.parametrize('broken', [[],{'path':None}, {'path':7}])
def test_malformed_derived_pointer_rebuilds_without_blocking_current_owner(tmp_path, broken):
    old_buy(tmp_path)
    folder=tmp_path/'incident_dispositions';folder.mkdir()
    (folder/'latest.json').write_text(json.dumps(broken))
    result=consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    assert result['derived_recovery']
    assert document(document(result)['current_ref'])['records'][0]['service_order']['state']=='unknown'


def test_future_derived_pointer_is_quarantined_and_replaced_for_current_consumption(tmp_path):
    old_buy(tmp_path)
    refresh(tmp_path,trade_date='2026-10-31',stage='eod',now=NOW+timedelta(days=1))
    result=consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    pointer=json.loads((tmp_path/'incident_dispositions/latest.json').read_text())
    assert result['derived_recovery']
    assert pointer==document(result)['current_ref'] and pointer['trade_date']=='2026-10-30'


def test_a_contended_derived_writer_never_waits_ahead_of_current_business(tmp_path):
    old_buy(tmp_path)
    first=refresh(tmp_path,trade_date='2026-10-29',stage='eod',now=NOW-timedelta(hours=18))
    folder=tmp_path/'incident_dispositions'
    before=(tmp_path/'events.jsonl').read_bytes()
    with (folder/'.writer.lock').open('a+b') as other_writer:
        fcntl.flock(other_writer.fileno(),fcntl.LOCK_EX)
        with pytest.raises(ValueError,match='WRITER_BUSY'):
            consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW)
    assert json.loads((folder/'latest.json').read_text())==first
    assert (tmp_path/'events.jsonl').read_bytes()==before


@pytest.mark.parametrize('order_id,mapping', [(None,None),('1234567',False)])
def test_derived_view_preserves_formal_rejection_without_reinterpreting_broker_mapping(tmp_path,order_id,mapping):
    plan,saved=old_buy(tmp_path)
    ExecutionStore(tmp_path/'events.jsonl').append(plan=plan,receipt=replace(saved,
        state=ExecutionState.REJECTED,broker_status='rejected',active=False,
        broker_order_id=order_id,receipt_mapping=mapping),kind='reconcile_receipt')
    ref=refresh(tmp_path,trade_date='2026-10-30',stage='post_business',now=NOW)
    row=document(ref)['records'][0]
    assert row['service_order']['terminal'] and row['service_order']['terminal_basis']=='formal_execution_state'
    assert row['current_economic_impact']['status']=='execution_terminal'
    assert ref['admission_authority']=='none'


def test_environment_identity_alone_is_not_an_accepted_next_owner(tmp_path,monkeypatch):
    from xiaocao.automation_run import automation_run
    monkeypatch.setenv('CODEX_AUTOMATION_ID','xiaocao-book-b-live-morning')
    monkeypatch.setenv('CODEX_THREAD_ID','original-owner')
    # This is a pure derived-view/lock test, no APP port is invoked.
    monkeypatch.setattr('xiaocao.live.app_test_window.app_test_context_active',lambda:False)
    assert not document(consume(tmp_path,trade_date='2026-10-30',run_id='repair',now=NOW))['accepted_handoff']
    with automation_run('xiaocao-book-b-live-morning','2026-10-30',root=tmp_path/'runner_locks'):
        body=document(consume(tmp_path,trade_date='2026-10-30',run_id='original',now=NOW))
        assert body['accepted_handoff'] and body['dated_lock_owner']['thread_id']=='original-owner'
        wrong=document(consume(tmp_path,trade_date='2026-10-31',run_id='different-date',now=NOW))
        assert not wrong['accepted_handoff']


def legacy_skip_without_intent(root, **changes):
    from tests.test_foundersc_native_broker import _plan
    plan = _plan()
    store = ExecutionStore(root / 'events.jsonl')
    first = ExecutionReceipt(plan.plan_id, plan.plan_hash, ExecutionState.PLANNED)
    store.append(plan=plan, receipt=replace(first, **changes), kind='plan_created')
    store.append(plan=plan, receipt=replace(first, state=ExecutionState.SKIPPED,
        reason='LIMIT_DOWN_CHECK_UNAVAILABLE'), kind='transition')
    return plan


def test_legacy_guard_skip_without_intent_remains_explicit_without_blocking_incident_view(tmp_path):
    plan = legacy_skip_without_intent(tmp_path)
    before = (tmp_path / 'events.jsonl').read_bytes()
    ref = refresh(tmp_path, trade_date='2026-10-30', stage='post_business', now=NOW)
    view = document(ref)
    assert view['records'] == [] and view['admission_authority'] == 'none'
    skipped = view['execution_source']['legacy_pre_submit_skips_without_intent']
    assert len(skipped) == 1 and skipped[0]['plan_id'] == plan.plan_id
    assert skipped[0]['plan_hash'] == plan.plan_hash and skipped[0]['event_hash']
    assert (tmp_path / 'events.jsonl').read_bytes() == before


@pytest.mark.parametrize('changes', [
    {'submit_claim_id': 'claimed'}, {'cancel_claim_id': 'claimed'},
    {'broker_order_id': '1234567'}, {'filled_shares': 1},
    {'submit_chain_uncertain': True}, {'cancel_chain_uncertain': True},
    {'active': True}, {'attempt': 1}, {'locator_proof': {'submitted': True}},
])
def test_missing_intent_with_any_possible_order_effect_stays_unproved(tmp_path, changes):
    legacy_skip_without_intent(tmp_path, **changes)
    with pytest.raises(ValueError, match='EXECUTION_SOURCE_UNPROVEN'):
        refresh(tmp_path, trade_date='2026-10-30', stage='post_business', now=NOW)


def test_legacy_skip_does_not_excuse_a_changed_event_chain(tmp_path):
    legacy_skip_without_intent(tmp_path)
    path = tmp_path / 'events.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['receipt']['reason'] = 'changed after hashing'
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    with pytest.raises(ValueError, match='EXECUTION_SOURCE_UNPROVEN'):
        refresh(tmp_path, trade_date='2026-10-30', stage='post_business', now=NOW)
