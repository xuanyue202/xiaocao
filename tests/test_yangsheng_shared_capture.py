"""Shared capture tests exercise task uncertainty, lifecycle and media acceptance."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from xiaocao.yangsheng import artifacts, capture, native, network, runtime
from xiaocao.yangsheng.native import CaptureError


def replay(replay_id='123', created=200, username='teacher@finder'):
    return {'id': replay_id, 'username': username, 'createtime': created,
            'objectDesc': {'description': '课程', 'media': [{'videoPlayLen': 600, 'url': 'https://a.video.qq.com/media?ticket=a%2Bb%20c',
                'urlToken': '&opaque=keep+bytes', 'decodeKey': '123', 'spec': [{'fileFormat': 'xWT111', 'bitRate': 100}]}]}}


def seed(db):
    with db:
        db.execute("INSERT INTO meta VALUES('baseline','100')")
        db.execute("INSERT INTO publishers VALUES('teacher@finder','[]',NULL)")


def test_closing_barrier_excludes_new_scan_and_new_scan_excludes_closing(tmp_path):
    with capture.lifecycle_lease(tmp_path, closing=True):
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with capture.lifecycle_lease(tmp_path): pass
    with capture.lifecycle_lease(tmp_path):
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with capture.lifecycle_lease(tmp_path, closing=True): pass
    with capture.lifecycle_lease(tmp_path, closing=True): pass


def test_history_not_backlog_and_verified_state_retained(tmp_path):
    with capture.database(tmp_path) as db:
        seed(db)
        capture.record_replays(db, 'teacher@finder', {'1': replay('1', 50), '2': replay('2', 200)}, 1)
        assert [tuple(row) for row in db.execute('SELECT id,state FROM replays ORDER BY created DESC')] == [('2', 'pending'), ('1', 'historical_discovered')]
        db.execute("UPDATE replays SET state='verified' WHERE id='2'")
        capture.record_replays(db, 'teacher@finder', {'2': replay('2', 200)}, 2)
        assert db.execute("SELECT state FROM replays WHERE id='2'").fetchone()[0] == 'verified'
        with pytest.raises(CaptureError, match='binding_changed'):
            capture.record_replays(db, 'teacher@finder', {'2': replay('2', 201)}, 3)


def test_unknown_create_retains_intent_and_never_reposts(tmp_path, monkeypatch):
    post = Mock(side_effect=CaptureError('transport_unknown_result'))
    monkeypatch.setattr(capture, 'request', post)
    monkeypatch.setattr(capture, 'find_task', lambda *a: None)
    with capture.database(tmp_path) as db:
        seed(db)
        with pytest.raises(CaptureError, match='transport_unknown_result'):
            capture.create_task(db, 'local', 'teacher@finder', replay())
        assert db.execute('SELECT state FROM jobs').fetchone()[0] == 'pending_create'
    with capture.database(tmp_path) as db:
        with pytest.raises(CaptureError, match='pending_shared_task_unresolved'):
            capture.create_task(db, 'local', 'teacher@finder', replay())
    assert post.call_count == 1
    body = post.call_args.args[2]
    assert body['url'] == replay()['objectDesc']['media'][0]['url'] + '&opaque=keep+bytes&X-snsvideoflag=xWT111'
    assert body['id'] == capture.task_identity('teacher@finder', '123')


def test_retained_unknown_create_reconciles_exact_existing_task(tmp_path, monkeypatch):
    existing = {'id': 'original-task', 'status': 'running'}
    monkeypatch.setattr(capture, 'find_task', lambda *a: existing)
    post = Mock(); monkeypatch.setattr(capture, 'request', post)
    with capture.database(tmp_path) as db:
        seed(db)
        db.execute("INSERT INTO jobs VALUES('teacher@finder','123','xWT111',NULL,'pending_create',1)")
        assert capture.create_task(db, 'local', 'teacher@finder', replay()) == existing
        assert db.execute('SELECT task_id FROM jobs').fetchone()[0] == 'original-task'
    post.assert_not_called()


@pytest.mark.parametrize('value', ['https://evil.example/media', 'https://video.qq.com.evil.example/media'])
def test_native_media_host_not_guessed(tmp_path, monkeypatch, value):
    monkeypatch.setattr(capture, 'find_task', lambda *a: None)
    obj = replay(); obj['objectDesc']['media'][0]['url'] = value
    with capture.database(tmp_path) as db:
        seed(db)
        with pytest.raises(CaptureError, match='unexpected_native_media_host'):
            capture.create_task(db, 'local', 'teacher@finder', obj)
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0


def test_partial_scan_preserves_history_and_reports_degraded(tmp_path, monkeypatch):
    with capture.database(tmp_path) as db:
        seed(db)
        db.execute("INSERT INTO publishers VALUES('z@finder','[]',NULL)"); db.commit()
    monkeypatch.setattr(capture, 'request', lambda *a: {'enabled': True, 'engine': 'gopeed', 'channels_available': True})
    def objects(api, username, *args):
        if username == 'z@finder': raise CaptureError('access_protection')
        return {'123': replay()}
    monkeypatch.setattr(capture, 'publisher_objects', objects)
    value = capture.cycle(tmp_path, create=False)
    assert value['status'] == 'degraded' and value['covered'] == 1
    assert value['errors'][0]['code'] == 'access_protection'
    with capture.database(tmp_path) as db:
        assert db.execute('SELECT count(*) FROM replays').fetchone()[0] == 1


@pytest.mark.parametrize('proof,code', [
    ({'accepted': [], 'waiting': [], 'failures': [{'code': 'probe_failed'}]}, 'verification_failed'),
    ({'accepted': [], 'waiting': [{'status': 'pause'}], 'failures': []}, 'owned_task_paused'),
    ({'accepted': [], 'waiting': [{'code': 'pending_shared_task_unresolved'}], 'failures': []}, 'still_active'),
])
def test_idle_tasks_cannot_override_unaccepted_artifact(tmp_path, monkeypatch, proof, code):
    monkeypatch.setattr(artifacts, 'reconcile_artifacts', lambda *a: proof)
    monkeypatch.setattr(artifacts, 'tasks', lambda *a: [])
    monkeypatch.setattr(artifacts, 'request', lambda *a: {'post_processing_active': []})
    with pytest.raises(CaptureError, match=code): artifacts.drain_before_shutdown(tmp_path, timeout=0)


def test_post_processing_blocks_close_even_if_task_is_done(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, 'reconcile_artifacts', lambda *a: {'accepted': [], 'waiting': [], 'failures': []})
    monkeypatch.setattr(artifacts, 'tasks', lambda *a: [{'status': 'done'}])
    monkeypatch.setattr(artifacts, 'request', lambda *a: {'post_processing_active': ['original-task']})
    with pytest.raises(CaptureError, match='still_active'): artifacts.drain_before_shutdown(tmp_path, timeout=0)


def test_shutdown_retains_barrier_after_drain(tmp_path, monkeypatch):
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    monkeypatch.setattr(artifacts, 'drain_before_shutdown', lambda *a: {'accepted': []})
    with runtime.shared_shutdown_lease('local', tmp_path):
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with capture.lifecycle_lease(tmp_path): pass


def test_health_failure_does_not_claim_already_closed(tmp_path, monkeypatch):
    from xiaocao.kol import xiaocao_live
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    monkeypatch.setattr(runtime, 'request', Mock(side_effect=CaptureError('request_timeout')))
    service = Mock(); service.cleanup_snapshot.return_value = {'process_gone': False}
    monkeypatch.setattr(xiaocao_live, 'XiaocaoLiveService', lambda: service)
    with pytest.raises(Exception): runtime.finish(tmp_path)
    service._disable_owned_capture_pac.assert_not_called()


def test_foreign_proxy_configuration_is_preserved(monkeypatch):
    before = {'pac': 'URL: original\nEnabled: No'}
    command = Mock(return_value='URL: foreign\nEnabled: Yes')
    monkeypatch.setattr(network, 'command', command)
    monkeypatch.setattr(network, 'snapshot', lambda: {'pac': 'URL: foreign\nEnabled: Yes'})
    assert network.restore(before, 'owned')['foreign_configuration_preserved']
    assert command.call_count == 1


def test_publisher_mismatch_and_native_protection_stop_read(monkeypatch):
    monkeypatch.setattr(native, 'request', lambda *a: {'errCode': 0, 'data': {'contact': {'username': 'other@finder'}}})
    with pytest.raises(CaptureError, match='contact_mismatch'): native.replay_page('local', 'teacher@finder', '')
    monkeypatch.setattr(native, 'request', lambda *a: {'errCode': 1, 'errMsg': 'login required'})
    with pytest.raises(CaptureError, match='access_protection'): native.replay_page('local', 'teacher@finder', '')


def test_other_page_user_blocks_proxy_detachment_and_shutdown(tmp_path, monkeypatch):
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    detach = Mock()
    with capture.lifecycle_lease(tmp_path):
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with runtime.shared_shutdown_lease('local', tmp_path): detach()
    detach.assert_not_called()


@pytest.mark.parametrize('method,event', [
    ('cancel_capture_wait', 'capture_wait_cancelled'),
    ('cleanup_sniffer', 'capture_cleanup_completed'),
])
def test_shared_repeated_cleanup_uses_strict_gone_receipt_without_api(tmp_path, monkeypatch, method, event):
    from types import SimpleNamespace
    from xiaocao.kol.capture import CaptureJobStore
    from xiaocao.kol.xiaocao_live import XiaocaoLiveService
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    store = CaptureJobStore(tmp_path / 'capture.jsonl'); armed = store.arm([])
    service = XiaocaoLiveService(tmp_path / 'live', capture_ledger=store.path,
        sniffer_client=SimpleNamespace(candidates=lambda: []))
    service._append(event, capture_job_id=armed['job_id'], status='old_cleanup')
    monkeypatch.setattr(service, 'cleanup_snapshot', lambda: {
        'process_gone': True, 'api_status_unavailable': True,
        'listeners': {'2022': False, '2023': False},
        'proxy_flags': {'HTTPEnable': 0, 'HTTPSEnable': 0, 'ProxyAutoConfigEnable': 0, 'SOCKSEnable': 0},
        'capture_proxy_detached': True, 'observed_at': '2026-10-22T12:00:00+08:00'})
    monkeypatch.setattr(runtime, 'request', lambda *a: pytest.fail('do not query a closed API'))
    monkeypatch.setattr(service, '_disable_owned_capture_pac', lambda: pytest.fail('already closed'))
    assert getattr(service, method)(capture_job_id=armed['job_id'])['idempotent_replay']


def test_invalid_shared_cancel_preserves_proxy_before_refusal(tmp_path, monkeypatch):
    from xiaocao.kol.capture import CaptureJobStore
    from xiaocao.kol.enrichment_types import EnrichmentError
    from xiaocao.kol.xiaocao_live import XiaocaoLiveService
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    store = CaptureJobStore(tmp_path / 'capture.jsonl'); armed = store.arm([])
    store.transition(armed, 'download_claimed', status='download_claimed')
    service = XiaocaoLiveService(tmp_path / 'live', capture_ledger=store.path)
    monkeypatch.setattr(service, '_disable_owned_capture_pac', lambda: pytest.fail('preserve active owner proxy'))
    with pytest.raises(EnrichmentError, match='idle capture wait'):
        service.cancel_capture_wait(armed['job_id'])
