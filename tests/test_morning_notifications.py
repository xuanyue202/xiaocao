import json
import pytest
from xiaocao.live.morning_notifications import MorningNotifications, message


@pytest.mark.parametrize("original", [b'{broken', b'[]', b'null'])
def test_corrupt_prior_claim_preserves_business_result_and_never_sends(tmp_path, original):
    path = tmp_path / 'old.json'
    path.write_bytes(original)
    sent, observed = [], []
    def build():
        return MorningNotifications('2026-10-01', root=tmp_path,
            sender=lambda *a: sent.append(a) or {'status': 'ok'},
            recipients=lambda: ('user',), on_delivery=observed.append)
    first = build()
    assert first.publish('result', {'status': 'completed', 'run_id': 'first'}) is None
    assert first.terminal.is_set()
    assert first.close()[0]['status'] == 'pending_reconcile'
    later = build()
    later.retry_pending()
    assert later.publish('result', {'status': 'completed', 'run_id': 'recovery'}) is None
    assert all(r['status'] == 'pending_reconcile' for r in later.close())
    assert observed and not sent
    assert path.read_bytes() == original
    assert list(tmp_path.glob('*.json')) == [path]


def test_routine_milestones_stay_local_and_result_delivers_once(tmp_path):
    sent = []
    def sender(title, body, recipient):
        sent.append((title, body, recipient))
        return {"status": "ok", "retry_safety": "not_needed"}
    notices = MorningNotifications("2026-09-28", root=tmp_path, sender=sender,
                                   recipients=lambda: ("configured-user",))
    for _ in range(2):
        notices.publish("preflight-start")
        notices.publish("ready")
        notices.publish("result", {"run_id": "original", "status": "completed", "orders": [
            {"plan_id": "owned-plan", "state": "filled", "filled_shares": 100,
             "fill_quantity_proven": True, "broker_order_id": "123"}]})
    results = notices.close()
    assert len(sent) == 1
    assert all(r["status"] == "delivered" and r["delivered_at"] for r in results)
    assert "100 股" in sent[0][1]
    assert sum(json.loads(p.read_text()).get("delivery_policy") == "local_only"
               for p in tmp_path.glob("*.json")) == 2


def test_preflight_problem_keeps_golden_window_and_ready_notices_live(tmp_path):
    sent = []
    notices = MorningNotifications("2026-09-28", root=tmp_path,
        sender=lambda title, body, recipient: sent.append(body) or {"status": "ok"},
        recipients=lambda: ("user",))
    notices.publish("preflight-problem", {"reason": "DEPENDENCY_DOWN", "request_path": "/original/request"})
    assert not notices.terminal.is_set()
    notices.publish("ready")
    notices.publish("result", {"status": "completed"})
    assert len(notices.close()) == 1
    assert len(sent) == 1


def test_delivery_proof_is_emitted_before_runner_close(tmp_path):
    from threading import Event
    observed, results = Event(), []
    def callback(result):
        results.append(result)
        observed.set()
    notices = MorningNotifications("2026-09-28", root=tmp_path,
        sender=lambda *args: {"status": "ok"}, recipients=lambda: ("user",), on_delivery=callback)
    notices.publish("result", {"status": "completed"})
    assert observed.wait(2)
    assert results[0]["status"] == "delivered" and results[0]["delivered_at"]
    assert notices.terminal.is_set()
    notices.close()


def test_retry_never_resends_delivered_or_uncertain_recipient(tmp_path):
    sent = []
    def sender(title, body, recipient):
        sent.append(recipient)
        if recipient == "safe" and sent.count(recipient) == 1:
            return {"status": "failed", "retry_safety": "safe", "failure_phase": "connect"}
        if recipient == "uncertain":
            return {"status": "uncertain", "retry_safety": "uncertain"}
        return {"status": "ok"}
    def build():
        return MorningNotifications("2026-09-28", root=tmp_path, sender=sender,
                                    recipients=lambda: ("delivered", "safe", "uncertain"))
    first = build()
    first.publish("result", {"status": "blocked", "failed_stage": "preflight", "reason": "UNLOCK_UNPROVEN"})
    assert first.close()[0]["status"] == "pending"
    later = build()
    later.retry_pending()
    assert later.close()[0]["status"] == "pending"
    assert sent.count("delivered") == sent.count("uncertain") == 1
    assert sent.count("safe") == 2
    title, body = message("result", "2026-09-28", {"status": "blocked", "failed_stage": "preflight", "reason": "UNLOCK_UNPROVEN"})
    assert "受阻" in title and "未进入" in body
    assert "UNLOCK_UNPROVEN" not in body


def test_delivery_exception_remains_uncertain_after_restart(tmp_path):
    calls = []
    def sender(*args):
        calls.append(args)
        raise TimeoutError()
    first = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    first.publish("result", {"status": "completed"})
    first.close()
    later = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    later.retry_pending()
    later.close()
    assert len(calls) == 1
    assert list(json.loads(next(tmp_path.glob("*.json")).read_text())["recipients"].values())[0]["status"] == "uncertain"


def test_queued_ack_is_reported_as_problem_not_fill():
    title, body = message("result", "2026-09-28", {"status": "unresolved", "orders": [
        {"state": "acknowledged", "filled_shares": 0, "broker_order_id": "123"}]})
    assert "受阻" in title and "等待成交" in body and "成交数量待核对" in body
    assert "确认成交 0" not in body


def test_notification_storage_failure_does_not_block_runner(monkeypatch, tmp_path):
    from xiaocao.live import morning_notifications as module
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(module, "_write", fail)
    notices = MorningNotifications("2026-09-28", root=tmp_path)
    assert notices.publish("ready") is None
    assert notices.close()[0]["status"] == "pending"


def test_golden_window_reports_unproved_outcome_without_stopping_recovery(tmp_path):
    from datetime import datetime
    timers, sent = [], []
    class Timer:
        def __init__(self, delay, callback):
            self.delay, self.callback = delay, callback
            timers.append(self)
        def start(self):
            pass
        def cancel(self):
            pass
        def join(self):
            pass
    def sender(t, b, r):
        sent.append((t, b))
        return {"status": "ok"}
    notices = MorningNotifications("2026-09-28", root=tmp_path, sender=sender, recipients=lambda: ("user",))
    notices.arm_golden_window(now=datetime.fromisoformat("2026-09-28T09:00:00+08:00"), timer_factory=Timer)
    assert timers[0].delay == 1800
    timers[0].callback()
    notices.publish("result", {"status": "completed", "run_id": "original"})
    assert len(notices.close()) == 2
    assert "暂未证明" in sent[0][1] and "委托 0" not in sent[0][1]
    assert "结果" in sent[1][0]


def test_unchanged_recovery_result_does_not_send_again(tmp_path):
    sent = []
    notices = MorningNotifications("2026-10-01", root=tmp_path,
        sender=lambda *args: sent.append(args) or {"status": "ok"}, recipients=lambda: ("user",))
    facts = {"status": "blocked", "failed_stage": "preflight", "reason": "DEPENDENCY_DOWN"}
    notices.publish("result", {**facts, "run_id": "first", "receipt_path": "/first"})
    notices.publish("result", {**facts, "run_id": "recovery", "receipt_path": "/second"})
    assert all(row["status"] == "delivered" for row in notices.close())
    assert len(sent) == 1


def test_explicit_user_action_notifies_but_routine_problem_stays_local(tmp_path):
    sent = []
    notices = MorningNotifications("2026-10-01", root=tmp_path,
        sender=lambda *args: sent.append(args) or {"status": "ok"}, recipients=lambda: ("user",))
    notices.publish("preflight-problem", {"run_id": "repair", "reason": "DEPENDENCY_DOWN"})
    notices.publish("preflight-problem", {"run_id": "human", "reason": "LOGIN_SMS_REQUIRED", "user_action_required": True})
    assert len(notices.close()) == len(sent) == 1
    assert "需要你处理" in sent[0][1]


def test_local_events_are_not_sent_by_retry_or_direct_send(tmp_path):
    sent = []
    notices = MorningNotifications("2026-10-01", root=tmp_path,
        sender=lambda *args: sent.append(args) or {"status": "ok"}, recipients=lambda: ("user",))
    notices.publish("ready")
    path = next(tmp_path.glob("*.json"))
    assert notices.send(path)["status"] == "recorded_only"
    notices.retry_pending()
    notices.close()
    assert not sent


def test_legacy_routine_problem_cannot_be_sent_after_upgrade(tmp_path):
    path = tmp_path / 'old.json'
    record = {'notification_id': 'old', 'automation_id': 'xiaocao-book-b-live-morning',
        'trade_date': '2026-10-01', 'kind': 'preflight-problem', 'status': 'pending',
        'recipients': {}, 'title': 'old', 'body': 'recoverable problem'}
    path.write_text(json.dumps(record))
    sent = []
    notices = MorningNotifications('2026-10-01', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    notices.retry_pending()
    assert notices.send(path)['status'] == 'recorded_only'
    assert notices.close() == [] and sent == []
    assert json.loads(path.read_text()) == record


def test_legacy_result_preserves_claim_across_different_recovery_run(tmp_path):
    import hashlib
    from xiaocao.live.morning_observability import terminal_notice
    root = tmp_path / 'book_b_morning_notifications'
    root.mkdir()
    receipt = tmp_path / 'book_b_live_execution/runs/history/first.json'
    receipt.parent.mkdir(parents=True)
    payload = {'run_id': 'first', 'trade_date': '2026-10-01', 'status': 'blocked',
               'failed_stage': 'preflight', 'reason': 'DEPENDENCY_DOWN'}
    receipt.write_text(json.dumps(payload))
    key = hashlib.sha256(b'xiaocao-book-b-live-morning|2026-10-01|result|first').hexdigest()
    recipient = hashlib.sha256(b'user').hexdigest()
    sent = []
    for state in ('delivered', 'uncertain', 'sending'):
        record = {'notification_id': key, 'automation_id': 'xiaocao-book-b-live-morning',
            'trade_date': '2026-10-01', 'kind': 'result', 'status': 'pending', 'title': 'old',
            'body': f'回执：{receipt}', 'recipients': {recipient: {'status': state, 'attempted_at': 'original'}}}
        path = root / f'{key}.json'
        path.write_text(json.dumps(record))
        notices = MorningNotifications('2026-10-01', root=root,
            sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
        facts = terminal_notice({**payload, 'run_id': 'recovery'}, receipt)
        assert notices.publish('result', facts) == key
        notices.close()
        persisted = json.loads(path.read_text())
        assert persisted['recipients'] == record['recipients']
        assert persisted['body'] == record['body']
    assert not sent
    # A proved business outcome change is a new result, not a resend.
    notices = MorningNotifications('2026-10-01', root=root,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    facts = terminal_notice({**payload, 'run_id': 'recovery', 'status': 'completed', 'reason': None}, receipt)
    assert notices.publish('result', facts) != key
    notices.close()
    assert len(sent) == 1


def test_unbound_legacy_result_requires_reconciliation_before_new_send(tmp_path):
    root = tmp_path / 'book_b_morning_notifications'
    root.mkdir()
    record = {'notification_id': 'old', 'automation_id': 'xiaocao-book-b-live-morning',
        'trade_date': '2026-10-01', 'kind': 'result', 'status': 'delivered',
        'title': 'old', 'body': 'missing receipt', 'recipients': {'user': {'status': 'delivered'}}}
    path = root / 'old.json'
    path.write_text(json.dumps(record))
    sent = []
    notices = MorningNotifications('2026-10-01', root=root,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    notices.publish('result', {'run_id': 'recovery', 'status': 'blocked'})
    assert notices.close()[0]['status'] == 'pending_reconcile'
    later = MorningNotifications('2026-10-01', root=root,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    later.retry_pending()
    later.close()
    assert sent == [] and json.loads(path.read_text()) == record


def test_same_dependency_request_notifies_when_it_becomes_human_only(tmp_path):
    from xiaocao.live.morning_observability import dependency_user_action
    sent = []
    notices = MorningNotifications('2026-10-01', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    facts = {'run_id': 'same-request:NATIVE_AX_ACCOUNT_SURFACE_NOT_READY',
             'reason': 'NATIVE_AX_ACCOUNT_SURFACE_NOT_READY'}
    local = notices.publish('preflight-problem', {**facts, 'user_action_required': False})
    human = {**facts, 'user_action_required': True,
             'user_action': dependency_user_action('NATIVE_AX_ACCOUNT_SURFACE_NOT_READY:screen_locked')}
    required = notices.publish('preflight-problem', human)
    assert required != local
    notices.publish('preflight-problem', human)
    notices.close()
    assert len(sent) == 1 and '解锁 macOS' in sent[0][1]
    assert json.loads((tmp_path / f'{local}.json').read_text())['delivery_policy'] == 'local_only'


@pytest.mark.app_simulation
@pytest.mark.parametrize('status', ['completed', 'no_action', 'blocked'])
def test_historical_pending_does_not_relabel_current_terminal_result(status):
    title, body = message('result', '2026-10-08', {
        'status': status, 'reason': 'NO_EXECUTABLE_STAR_E',
        'pending_orders': [{'code': '000572.XSHE', 'side': 'SELL',
                            'broker_order_id': '6007019', 'state': 'unknown'}],
    })
    assert ('执行受阻' in title) == (status == 'blocked')
    assert '6007019' not in body and '000572.XSHE' not in body


@pytest.mark.app_simulation
@pytest.mark.parametrize('history', [
    {'pending_orders': [{'code': '000572.XSHE', 'side': 'SELL',
                         'broker_order_id': '6007019', 'state': 'unknown'}]},
    {'pending_evidence_unproven': True},
])
def test_completed_buy_keeps_success_reason_with_unresolved_history(history):
    from xiaocao.live.morning_notifications import _cause

    facts = {'status': 'completed', 'reason': 'BROKER_TERMINAL', 'orders': [
        {'code': '000573.XSHE', 'side': 'BUY', 'state': 'filled',
         'broker_order_id': '6000065', 'filled_shares': 8200,
         'fill_quantity_proven': True}]}
    title, body = message('result', '2026-10-20', {**facts, **history})
    assert '执行结果' in title and '6000065' in body and '8200 股' in body
    assert _cause('BROKER_TERMINAL') not in body
    assert body == message('result', '2026-10-20', facts)[1]


@pytest.mark.app_simulation
@pytest.mark.parametrize('kind', ['result', 'golden-window'])
@pytest.mark.parametrize('user_action_required', [False, True])
def test_internal_history_stays_out_of_notice_without_hiding_current_order_or_user_action(kind, user_action_required):
    facts = {'status': 'unresolved', 'orders': [
        {'plan_id': 'book-b:2026-10-21:301052.XSHE:BUY', 'state': 'acknowledged',
         'broker_order_id': '6000066', 'filled_shares': 0,
         'submit_chain_uncertain': False, 'cancel_chain_uncertain': False}],
        'pending_orders': [{'code': '000572.XSHE', 'side': 'SELL',
                            'broker_order_id': '6007019', 'state': 'unknown'}],
        'pending_evidence_unproven': True,
        'user_action_required': user_action_required,
        'user_action': {'request': '请解锁 macOS 后继续本次交易核验。'}}
    original = json.loads(json.dumps(facts))
    _, body = message(kind, '2026-10-21', facts)
    assert '6000066' in body and '6007019' not in body
    assert ('请解锁 macOS' in body) is user_action_required
    assert facts == original


@pytest.mark.app_simulation
@pytest.mark.parametrize('prior_state', ['delivered', 'uncertain', 'sending'])
def test_history_only_refresh_reuses_upgraded_recipient_claim(tmp_path, prior_state):
    import hashlib
    from xiaocao.live.morning_notifications import result_fingerprint

    facts = {'status': 'completed', 'reason': 'BROKER_TERMINAL', 'orders': [
        {'plan_id': 'book-b:2026-10-21:301052.XSHE:BUY', 'state': 'filled',
         'broker_order_id': '6000066', 'filled_shares': 500, 'fill_price': 32.98}],
        'pending_orders': [{'plan_id': 'old', 'state': 'unknown', 'broker_order_id': '6007019'}]}
    fingerprint = result_fingerprint(facts)
    key = hashlib.sha256(f'xiaocao-book-b-live-morning|2026-10-21|result|{fingerprint}'.encode()).hexdigest()
    recipient = hashlib.sha256(b'user').hexdigest()
    original = {'notification_id': key, 'automation_id': 'xiaocao-book-b-live-morning',
        'trade_date': '2026-10-21', 'kind': 'result', 'result_fingerprint': fingerprint,
        'title': 'original title', 'body': 'original body', 'status': 'pending',
        'recipients': {recipient: {'status': prior_state, 'attempted_at': 'original'}}}
    path = tmp_path / f'{key}.json'
    path.write_text(json.dumps(original))
    sent = []
    notices = MorningNotifications('2026-10-21', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    assert notices.publish('result', facts) == key
    refreshed = {**facts, 'pending_orders': [], 'pending_evidence_unproven': True}
    assert notices.publish('result', refreshed) == key
    notices.close()
    persisted = json.loads(path.read_text())
    assert not sent and persisted['body'] == original['body']
    assert persisted['recipients'] == original['recipients']
    assert list(tmp_path.glob('*.json')) == [path]


@pytest.mark.app_simulation
def test_current_order_change_still_notifies_after_history_only_refresh(tmp_path):
    sent = []
    notices = MorningNotifications('2026-10-21', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    facts = {'status': 'unresolved', 'orders': [
        {'plan_id': 'current', 'state': 'acknowledged', 'broker_order_id': '6000066'}]}
    first = notices.publish('result', facts)
    assert notices.publish('result', {**facts, 'pending_evidence_unproven': True}) == first
    final = {**facts, 'status': 'completed', 'orders': [
        {**facts['orders'][0], 'state': 'filled', 'filled_shares': 500, 'fill_price': 32.98}]}
    assert notices.publish('result', final) != first
    notices.close()
    assert len(sent) == 2


@pytest.mark.app_simulation
def test_unbound_legacy_history_change_does_not_create_another_send(tmp_path):
    from xiaocao.live.morning_notifications import result_fingerprint

    path = tmp_path / 'original.json'
    record = {'notification_id': 'original', 'automation_id': 'xiaocao-book-b-live-morning',
        'trade_date': '2026-10-21', 'kind': 'result', 'status': 'pending',
        'title': 'old', 'body': 'old', 'recipients': {'user': {'status': 'uncertain'}},
        'result_fingerprint': result_fingerprint({'status': 'completed',
            'pending_orders': [{'plan_id': 'old', 'state': 'unknown'}]})}
    path.write_text(json.dumps(record))
    sent = []
    notices = MorningNotifications('2026-10-21', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'}, recipients=lambda: ('user',))
    notices.publish('result', {'status': 'completed', 'pending_orders': []})
    assert notices.close()[0]['status'] == 'pending_reconcile'
    assert not sent and json.loads(path.read_text()) == record


@pytest.mark.app_simulation
def test_concurrent_history_only_publishers_share_one_atomic_delivery_claim(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier, sent = Barrier(2), []
    original = MorningNotifications._legacy_result_alias
    def rendezvous(self, *args):
        result = original(self, *args)
        barrier.wait(timeout=2)
        return result
    monkeypatch.setattr(MorningNotifications, '_legacy_result_alias', rendezvous)
    publishers = [MorningNotifications('2026-10-21', root=tmp_path,
        sender=lambda *args: sent.append(args) or {'status': 'ok'},
        recipients=lambda: ('user',)) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(p.publish, 'result', {'status': 'completed',
            'pending_evidence_unproven': bool(i)}) for i, p in enumerate(publishers)]
        keys = [call.result() for call in calls]
    for publisher in publishers:
        publisher.close()
    assert keys[0] == keys[1] and keys[0] is not None
    assert len(sent) == 1 and len(list(tmp_path.glob('*.json'))) == 1
