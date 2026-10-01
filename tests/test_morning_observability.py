from pathlib import Path
import json
from xiaocao.live.morning_observability import review_notice, review_brief, terminal_notice
from xiaocao.live.morning_observability import dependency_user_action


def test_full_evidence_is_referenced_not_injected_into_operator_messages():
    request = {'request_id': 'a'*64, 'request_sha256': 'a'*64,
        'requested_at': '2026-09-17T09:25:00+08:00',
        'entry_deadline': '2026-09-17T11:30:00+08:00', 'max_wait_seconds': 120,
        'candidates': [{'code': str(i), 'mode': 'N字低吸', 'mode_exec_star': i == 0,
            'mode_state': 'ACTIVE', 'market_price': 10, 'basket_price': 11,
            'unrelated_payload': 'x'*50000} for i in range(10)]}
    notice = review_notice(request, Path('full.json'), Path('receipt.json'), Path('brief.json'))
    assert len(json.dumps(notice)) < 2048
    assert 'candidates' not in notice and 'request' not in notice
    brief = review_brief(request)
    assert len(brief['candidates']) == 10
    assert brief['candidates'][0]['market_price'] == 10
    assert brief['review_deadline'] == '2026-09-17T09:27:00+08:00'
    assert request['candidates'][0]['unrelated_payload']  # immutable source untouched
    terminal = terminal_notice({'execution_receipts': [{'state': 'filled',
        'broker_order_id': '123', 'filled_shares': 100, 'locator_proof': 'x'*50000}]}, Path('run.json'))
    assert terminal['orders'][0]['broker_order_id'] == '123'
    assert len(json.dumps(terminal)) < 2048


def test_blocked_morning_exposes_old_order_and_existing_alert_delivery(tmp_path):
    root = tmp_path / 'book'
    receipt_path = root / 'runs' / 'history' / 'run.json'
    receipt_path.parent.mkdir(parents=True)
    (root / 'incidents.jsonl').write_text('\n'.join(json.dumps(r) for r in [
        {'incident_id': 'alert', 'status': 'pending',
         'body': 'state=unknown order_id=6007019\n'},
        {'incident_id': 'alert', 'status': 'delivered',
         'created_at': '2026-09-22T01:01:06+00:00', 'result': {'wecom': 'ok'}},
    ]))
    notice = terminal_notice({'status': 'blocked', 'execution_receipts': (),
        'open_plan_reconciliations': [{'plan_id': 'old-sell', 'state': 'unknown',
            'broker_order_id': '6007019', 'reason': 'NATIVE_HISTORICAL_STATUS_UNPROVEN'}]}, receipt_path)
    assert notice['pending_orders'][0]['broker_order_id'] == '6007019'
    assert notice['incident_notifications'][0]['wecom'] == 'ok'
    assert notice['incident_notifications'][0]['delivered_at'] == '2026-09-22T01:01:06+00:00'
    assert notice['orders'] == []


def test_user_only_failures_propagate_without_unknown_counter_escalation():
    assert dependency_user_action('NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:screen_locked')['required']
    assert dependency_user_action('NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:screen_lock_state_unavailable')['required']
    assert dependency_user_action('NATIVE_AX_KEYCHAIN_READ_DENIED')['required']
    assert dependency_user_action('OTHER', {'state': 'unproven_no_retry'})['required']
    assert not dependency_user_action('OTHER', {'state': 'verified', 'remaining_attempts': None})['required']
    assert not dependency_user_action('NATIVE_AX_PRESECRET_DIALOG_BLOCKED')['required']
    action = dependency_user_action('NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:screen_locked')
    request = {'status': 'exhausted', 'failures': [{'evidence': {'user_action': action}}]}
    payload = {'reason': 'DEPENDENCY_RECOVERY_BUDGET_EXHAUSTED',
               'dependency_recovery': {'requests': [request]}}
    notice = terminal_notice(payload, Path('receipt.json'))
    assert notice['user_action_required'] and '解锁 macOS' in notice['user_action']['request']
    request['status'] = 'recovered'
    assert not terminal_notice(payload, Path('receipt.json'))['user_action_required']


def test_prior_and_durable_pending_are_reported_without_inventing_fills(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from xiaocao.live import book_b_live_lifecycle, trading_execution
    root = tmp_path / 'book_b_live_execution'
    receipt = root / 'runs/history/run.json'
    receipt.parent.mkdir(parents=True)
    (root / 'events.jsonl').write_text('durable fixture supplied by store')
    durable = {'plan_id': 'historical', 'state': 'unknown', 'broker_order_id': 'old', 'filled_shares': 0}
    monkeypatch.setattr(book_b_live_lifecycle, 'open_execution_plan_ids', lambda _: ['historical'])
    monkeypatch.setattr(trading_execution, 'ExecutionStore', lambda _: SimpleNamespace(
        current=lambda _: SimpleNamespace(as_dict=lambda: durable)))
    notice = terminal_notice({'prior_reconciliations': [{'plan_id': 'previous', 'state': 'acknowledged',
        'broker_order_id': 'prior', 'filled_shares': 0}]}, receipt)
    assert {r['broker_order_id'] for r in notice['pending_orders']} == {'old', 'prior'}
    assert all(r['fill_quantity_proven'] is False for r in notice['pending_orders'])
    assert durable == {'plan_id': 'historical', 'state': 'unknown', 'broker_order_id': 'old', 'filled_shares': 0}


def test_only_proved_fill_readback_can_confirm_quantity():
    row = {'plan_id': 'owned', 'state': 'filled', 'filled_shares': 100, 'receipt_mapping': True}
    assert not terminal_notice({'execution_receipts': [row]}, Path('receipt'))['orders'][0]['fill_quantity_proven']
    row['locator_proof'] = {'fill_observation_pending': False}
    assert terminal_notice({'execution_receipts': [row]}, Path('receipt'))['orders'][0]['fill_quantity_proven']
    row['submit_chain_uncertain'] = True
    assert not terminal_notice({'execution_receipts': [row]}, Path('receipt'))['orders'][0]['fill_quantity_proven']
