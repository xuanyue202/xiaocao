"""Shared capture tests exercise task uncertainty, lifecycle and media acceptance."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from xiaocao.yangsheng import artifacts, capture, native, network, runtime
from xiaocao.yangsheng.native import CaptureError


@pytest.fixture(autouse=True)
def isolated_native_hold(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', tmp_path / 'unused-bridge.json')


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


@pytest.mark.parametrize('legacy_duration', [None, 0])
def test_zero_duration_from_typed_sdk_matches_missing_unverified_history(tmp_path, legacy_duration):
    obj = replay('124', 50)
    obj['objectDesc']['media'][0].pop('videoPlayLen')
    with capture.database(tmp_path) as db:
        seed(db)
        capture.record_replays(db, 'teacher@finder', {'124': obj}, 1)
        db.execute("UPDATE replays SET duration=? WHERE id='124'", (legacy_duration,))
        obj['objectDesc']['media'][0]['videoPlayLen'] = 0
        capture.record_replays(db, 'teacher@finder', {'124': obj}, 2)
        row = db.execute("SELECT duration,state FROM replays WHERE id='124'").fetchone()
        assert row['duration'] == legacy_duration and row['state'] == 'historical_discovered'
        with pytest.raises(CaptureError, match='replay_media_not_ready'):
            capture.create_task(db, 'unused', 'teacher@finder', obj)
        obj['objectDesc']['media'][0]['videoPlayLen'] = 600
        with pytest.raises(CaptureError, match='binding_changed'):
            capture.record_replays(db, 'teacher@finder', {'124': obj}, 3)


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


@pytest.mark.parametrize('selector,ok', [('xWT111', True), ('different', False)])
def test_retained_media_preserves_existing_signed_selector(tmp_path, monkeypatch, selector, ok):
    monkeypatch.setattr(capture, 'find_task', lambda *a: None)
    post = Mock(side_effect=CaptureError('transport_unknown_result'))
    monkeypatch.setattr(capture, 'request', post)
    obj = replay(); media = obj['objectDesc']['media'][0]
    media['url'] += '&X-snsvideoflag=' + selector
    with capture.database(tmp_path) as db:
        seed(db)
        with pytest.raises(CaptureError, match='transport_unknown_result' if ok else 'media_format_conflict'):
            capture.create_task(db, 'local', 'teacher@finder', obj)
    if ok:
        url = post.call_args.args[2]['url']
        assert url.count('X-snsvideoflag=') == 1
        assert 'ticket=a%2Bb%20c' in url and 'opaque=keep+bytes' in url
    else: post.assert_not_called()


@pytest.mark.parametrize('message', ['请求超时', 'request timed out', 'timeout'])
def test_backend_timeout_remains_retryable(message):
    with pytest.raises(CaptureError, match='^request_timeout$'):
        native.check_error(400, message, 'candidate_api_error')


def test_unavailable_publisher_does_not_starve_following_publishers(tmp_path, monkeypatch):
    with capture.database(tmp_path) as db:
        seed(db)
        db.execute("INSERT INTO publishers VALUES('a@finder','[]',NULL)")
        db.commit()
    monkeypatch.setattr(capture, 'request', lambda *a: {'enabled': True, 'engine': 'gopeed', 'channels_available': True})
    calls = []
    def objects(api, username, *args):
        calls.append(username)
        if username == 'a@finder':
            raise CaptureError('publisher_unavailable')
        return {'123': replay()}
    monkeypatch.setattr(capture, 'publisher_objects', objects)
    value = capture.cycle(tmp_path, create=False)
    assert calls == ['a@finder', 'teacher@finder']
    assert value['covered'] == 1 and value['publisher_count'] == 2
    assert value['status'] == 'degraded'
    assert value['errors'] == [{'publisher_sha256': native.digest('a@finder'), 'code': 'publisher_unavailable'}]
    with capture.database(tmp_path) as db:
        assert db.execute('SELECT count(*) FROM replays').fetchone()[0] == 1
        assert db.execute("SELECT verified_at FROM publishers WHERE username='a@finder'").fetchone()[0] is None


@pytest.mark.parametrize('message,expected', [
    ({'String': ''}, 'publisher_unavailable'),
    ({'String': '请重新登录'}, 'access_protection'),
    ({'String': 'unknown failure'}, 'native_base_error'),
])
def test_native_publisher_failure_preserves_protection_boundary(monkeypatch, message, expected):
    monkeypatch.setattr(native, 'request', lambda *a: {'errCode': 0, 'data': {'BaseResponse': {'Ret': -1, 'ErrMsg': message}}})
    with pytest.raises(CaptureError, match='^' + expected + '$'):
        native.replay_page('local', 'teacher@finder', '')


def test_bootstrap_reuses_live_socket_without_native_input_or_proxy_change(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'request', lambda *a: {'enabled': True, 'channels_available': True})
    monkeypatch.setattr(network, 'snapshot', lambda: pytest.fail('no proxy reads or changes needed'))
    refresh = Mock()
    result = runtime.bootstrap(None, None, root=tmp_path, refresh=refresh)
    assert result['reused'] and result['proxy_changed'] is False
    refresh.assert_not_called()


@pytest.mark.parametrize('refresh_fails', [False, True])
def test_visible_refresh_holds_leases_and_restores_pac_on_failure(tmp_path, monkeypatch, refresh_fails):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import io
    held = []
    @contextmanager
    def native_lease():
        held.append(True)
        try: yield
        finally: held.pop()
    monkeypatch.setattr(runtime, 'native_lease', native_lease)
    monkeypatch.setattr(runtime, 'request', Mock(side_effect=[{'enabled': True}, {'enabled': True, 'channels_available': True}]))
    monkeypatch.setattr(network, 'snapshot', lambda: {'pac': 'Enabled: No'})
    monkeypatch.setattr(network, 'command', lambda *a: 'URL: http://127.0.0.1:2022/liuguan/proxy.pac\nEnabled: Yes')
    restored = Mock(return_value={'restored': True}); monkeypatch.setattr(network, 'restore', restored)
    guard = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('armed\n'), wait=Mock())
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *a, **kw: guard)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **kw: pytest.fail('visible route must not focus/click separately'))
    def refresh():
        assert held == [True]
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with capture.lifecycle_lease(tmp_path, closing=True): pass
        if refresh_fails: raise CaptureError('native_refresh_not_confirmed')
    if refresh_fails:
        with pytest.raises(CaptureError, match='native_refresh_not_confirmed'):
            runtime.bootstrap(None, None, root=tmp_path, refresh=refresh)
        assert not (tmp_path / 'native-entry.json').exists()
    else:
        assert runtime.bootstrap(None, None, root=tmp_path, refresh=refresh)['status'] == 'connected'
    restored.assert_called_once()
    assert held == [] and guard.stdin.closed


def test_exact_provider_deactivation_is_distinct_from_unavailable(monkeypatch):
    unavailable = {'errCode': 0, 'data': {'BaseResponse': {'Ret': -1, 'ErrMsg': {'String': ''}}}}
    deactivated = {'errCode': 0, 'data': {'BaseResponse': {'Ret': -5900, 'ErrMsg': {'String': ''}},
        'contact': {'username': 'teacher@finder', 'nickname': '账号已注销'}}}
    calls = Mock(side_effect=[unavailable, deactivated])
    monkeypatch.setattr(native, 'request', calls)
    with pytest.raises(CaptureError, match='publisher_deactivated'):
        native.replay_page('local', 'teacher@finder', '')
    assert calls.call_count == 2
    deactivated['data']['contact']['username'] = 'someone-else@finder'
    calls.side_effect = [unavailable, deactivated]
    with pytest.raises(CaptureError, match='publisher_contact_mismatch'):
        native.replay_page('local', 'teacher@finder', '')


def test_sdk_decode_failure_retries_same_page_once_and_does_not_retry_protection(monkeypatch):
    page = {'object': [replay()], 'contact': {'username': 'teacher@finder'}}
    calls = Mock(side_effect=[CaptureError('sdk_decode_failed'), page])
    monkeypatch.setattr(native, 'replay_page', calls)
    waits = []
    monkeypatch.setattr(native, 'sleep', waits.append)
    progress = {'pages': 0}
    assert native.publisher_objects('local', 'teacher@finder', 50, 2, progress) == {'123': replay()}
    assert calls.call_count == 2 and calls.call_args_list[0] == calls.call_args_list[1]
    assert progress['retries'] == 1 and waits == [3]
    calls.reset_mock(); calls.side_effect = CaptureError('access_protection')
    with pytest.raises(CaptureError, match='access_protection'):
        native.publisher_objects('local', 'teacher@finder', 50, 2, {'pages': 0})
    assert calls.call_count == 1


def test_cycle_accounts_for_deactivated_publishers_without_calling_them_empty(tmp_path, monkeypatch):
    with capture.database(tmp_path) as db:
        seed(db)
        db.execute("INSERT INTO publishers VALUES('z@finder','[]',NULL)"); db.commit()
    monkeypatch.setattr(capture, 'request', lambda *a: {'enabled': True, 'engine': 'gopeed', 'channels_available': True})
    waits = []
    monkeypatch.setattr(capture, 'sleep', waits.append)
    def objects(api, username, *args):
        if username == 'z@finder': raise CaptureError('publisher_deactivated')
        return {'123': replay()}
    monkeypatch.setattr(capture, 'publisher_objects', objects)
    result = capture.cycle(tmp_path, create=False)
    assert result['status'] == 'scanned' and result['covered'] == 1
    assert waits == [2]
    assert result['assessed'] == 2 and len(result['deactivated']) == 1 and result['errors'] == []
    with capture.database(tmp_path) as db:
        assert db.execute("SELECT state FROM publisher_checks WHERE publisher='z@finder'").fetchone()[0] == 'deactivated'
        assert db.execute('SELECT count(*) FROM publishers').fetchone()[0] == 2


def test_preserved_backend_still_waits_for_owned_artifacts_and_dispatches_asr(tmp_path, monkeypatch):
    from xiaocao.yangsheng import asr
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    calls = []
    def wait(root, api, **kwargs):
        calls.append(('wait', kwargs))
        with pytest.raises(CaptureError, match='lifecycle_busy'):
            with capture.lifecycle_lease(root, closing=True): pass
        return {'accepted': [{'replay_id': '123'}], 'waiting': [], 'failures': []}
    monkeypatch.setattr(artifacts, 'wait_for_artifacts', wait)
    monkeypatch.setattr(asr, 'start_worker', lambda root: calls.append(('asr', {})) or {'status': 'dispatched'})
    monkeypatch.setattr(runtime, 'native_lease', lambda: pytest.fail('no native lease or input'))
    monkeypatch.setattr(runtime, 'request', lambda *a: pytest.fail('no backend shutdown probe'))
    result = runtime.finish(tmp_path, preserve_backend=True)
    assert result['code'] == 'xiaocao_continuation_preserved'
    assert result['artifacts']['accepted'] == [{'replay_id': '123'}]
    assert [v[0] for v in calls] == ['wait', 'asr']


def test_owned_drain_does_not_wait_for_foreign_download(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, 'reconcile_artifacts', lambda *a: {'accepted': [], 'waiting': [], 'failures': []})
    monkeypatch.setattr(artifacts, 'tasks', lambda *a: pytest.fail('foreign work is preserved'))
    monkeypatch.setattr(artifacts, 'request', lambda *a: pytest.fail('reconciler owns post-processing proof'))
    assert artifacts.wait_for_artifacts(tmp_path, timeout=0)['waiting'] == []


def test_owned_drain_failure_still_wakes_already_accepted_asr(tmp_path, monkeypatch):
    from xiaocao.yangsheng import asr
    enabled = tmp_path / 'enabled'; enabled.touch()
    monkeypatch.setattr(runtime, 'ENABLED', enabled)
    monkeypatch.setattr(artifacts, 'wait_for_artifacts', Mock(side_effect=CaptureError('shared_owned_task_paused')))
    worker = Mock(return_value={'status': 'dispatched'}); monkeypatch.setattr(asr, 'start_worker', worker)
    with pytest.raises(CaptureError, match='owned_task_paused'):
        runtime.finish(tmp_path, preserve_backend=True)
    worker.assert_called_once_with(tmp_path)


@pytest.mark.parametrize('processing', [None, {}, 'unknown'])
def test_missing_postprocessing_proof_cannot_accept_owned_media(tmp_path, monkeypatch, processing):
    monkeypatch.setattr(artifacts, 'request', lambda *a: {'enabled': True, 'post_processing_active': processing})
    with pytest.raises(CaptureError, match='post_processing_status_unverified'):
        artifacts.reconcile_artifacts(tmp_path)


def test_foreign_postprocessing_does_not_block_owned_artifact_acceptance(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, 'request', lambda *a: {'enabled': True, 'post_processing_active': ['foreign'], 'download_dir': str(tmp_path)})
    monkeypatch.setattr(artifacts, 'find_task', lambda *a: {'id': 'owned', 'status': 'done'})
    monkeypatch.setattr(artifacts, 'verify_task', lambda *a: {'path': str(tmp_path / 'media'), 'size': 10, 'sha256': 'a'*64})
    with capture.database(tmp_path) as db:
        with db:
            db.execute("INSERT INTO jobs VALUES('teacher@finder','123','spec','owned','running',1)")
            db.execute("INSERT INTO replays VALUES('teacher@finder','123',1,2,'{}','pending',1,1)")
    result = artifacts.reconcile_artifacts(tmp_path)
    assert result['accepted'][0]['task_id'] == 'owned'
    assert result['waiting'] == []


def test_retained_page_gets_reconnect_grace_before_native_input(monkeypatch):
    initial = {'pid': 100, 'enabled': True, 'engine': 'gopeed', 'channels_available': False}
    clock = [0.0]; waits = []
    monkeypatch.setattr(runtime, 'monotonic', lambda: clock[0])
    def wait(seconds):
        waits.append(seconds); clock[0] += seconds
    monkeypatch.setattr(runtime, 'sleep', wait)
    read = Mock(side_effect=[initial, {**initial, 'channels_available': True}]); monkeypatch.setattr(runtime, 'request', read)
    assert runtime.wait_for_native_connection('local', initial)['channels_available']
    assert waits == [1, 1]
    assert all(c.args[1] == '/api/shared-capture/status' and c.kwargs['timeout'] <= 1 for c in read.call_args_list)
    read.reset_mock(); waits.clear()
    assert runtime.wait_for_native_connection('local', {**initial, 'channels_available': True})['channels_available']
    read.assert_not_called(); assert waits == []


def test_reconnect_grace_preserves_missing_page_as_missing(monkeypatch):
    initial = {'pid': 100, 'enabled': True, 'engine': 'gopeed', 'channels_available': False}
    clock = [0.0]
    monkeypatch.setattr(runtime, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(runtime, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(runtime, 'request', lambda *a, **k: initial)
    assert runtime.wait_for_native_connection('local', initial, timeout=3)['channels_available'] is False
    assert clock[0] == 3


def test_held_missing_connection_never_requests_native_input(tmp_path, monkeypatch):
    from scripts import kol_daily
    config = tmp_path / 'native_share_bridge.json'
    config.write_text(json.dumps({'activation_hold': {'active': True}}))
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', config, raising=False)
    deployed = tmp_path / 'enabled.json'; deployed.write_text('{}')
    monkeypatch.setattr(runtime, 'ENABLED', deployed)
    value = {'status': 'waiting', 'code': 'liuguan_native_connection_required',
             'artifacts': {'accepted': [{'task_id': 'retained'}]}}
    run = Mock(return_value=value); monkeypatch.setattr(runtime, 'run_local', run)
    prompt = Mock(side_effect=AssertionError('must not request native input'))
    monkeypatch.setattr(kol_daily, '_read_agent_json', prompt)
    result = kol_daily._run_liuguan_local_companion()
    assert result['code'] == 'liuguan_connection_unavailable_native_entry_held'
    assert result['artifacts'] == value['artifacts']
    run.assert_called_once(); prompt.assert_not_called()


def test_malformed_hold_preserves_companion_artifacts_without_native_prompt(tmp_path, monkeypatch):
    from scripts import kol_daily
    config = tmp_path / 'bridge.json'; config.write_text('{"activation_hold":null}')
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', config)
    deployed = tmp_path / 'enabled.json'; deployed.write_text('{}')
    monkeypatch.setattr(runtime, 'ENABLED', deployed)
    value = {'status': 'waiting', 'code': 'liuguan_native_connection_required', 'artifacts': {'accepted': ['retained']}}
    monkeypatch.setattr(runtime, 'run_local', Mock(return_value=value))
    monkeypatch.setattr(kol_daily, '_read_agent_json', lambda *a: pytest.fail('no native prompt'))
    result = kol_daily._run_liuguan_local_companion()
    assert result['code'] == 'native_entry_configuration_unreadable'
    assert result['artifacts'] == value['artifacts']


def test_held_bootstrap_stops_before_lease_proxy_or_input(tmp_path, monkeypatch):
    config = tmp_path / 'bridge.json'
    config.write_text(json.dumps({'activation_hold': {'active': True}}))
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', config, raising=False)
    monkeypatch.setattr(runtime, 'request', lambda *a: {'enabled': True, 'channels_available': False})
    monkeypatch.setattr(runtime, 'native_lease', lambda: pytest.fail('must not acquire native lease'))
    monkeypatch.setattr(network, 'snapshot', lambda: pytest.fail('must not read/mutate proxy'))
    refresh = Mock()
    with pytest.raises(CaptureError, match='^native_entry_suspended$'):
        runtime.bootstrap(None, None, root=tmp_path, refresh=refresh)
    refresh.assert_not_called()


def test_held_healthy_companion_keeps_api_work_without_native_request(tmp_path, monkeypatch):
    from scripts import kol_daily
    config = tmp_path / 'bridge.json'
    config.write_text(json.dumps({'activation_hold': {'active': True}}))
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', config)
    deployed = tmp_path / 'enabled.json'; deployed.write_text('{}')
    monkeypatch.setattr(runtime, 'ENABLED', deployed)
    value = {'status': 'scanned', 'available': 29, 'deactivated': 4}
    monkeypatch.setattr(runtime, 'run_local', Mock(return_value=value))
    monkeypatch.setattr(kol_daily, '_read_agent_json', lambda *a: pytest.fail('no native request'))
    assert kol_daily._run_liuguan_local_companion() == value


@pytest.mark.parametrize('connected', [False, True])
def test_connection_diagnostic_only_reads_existing_backend(tmp_path, monkeypatch, connected):
    binary = tmp_path / 'backend'; binary.write_bytes(b'fixture')
    descriptor = tmp_path / 'enabled.json'
    descriptor.write_text(json.dumps({'binary': str(binary), 'sha256': capture.sha_file(binary)}))
    config = tmp_path / 'bridge.json'
    config.write_text(json.dumps({'activation_hold': {'active': True}}))
    monkeypatch.setattr(runtime, 'NATIVE_ENTRY_CONFIG', config)
    monkeypatch.setattr(runtime, 'BACKEND', binary)
    monkeypatch.setattr(runtime, 'ENABLED', descriptor)
    monkeypatch.setattr(runtime, 'executable', lambda pid: binary)
    read = Mock(return_value={'pid': 123, 'enabled': True, 'engine': 'gopeed', 'channels_available': connected})
    monkeypatch.setattr(runtime, 'request', read)
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *a, **k: pytest.fail('no service/app start'))
    monkeypatch.setattr(runtime, 'native_lease', lambda: pytest.fail('no native lease'))
    monkeypatch.setattr(network, 'snapshot', lambda: pytest.fail('no proxy reads/mutations'))
    result = runtime.connection_status()
    assert result['channels_api_reusable'] is connected
    assert result['native_entry_held'] is True
    assert result['native_operations'] == result['proxy_changes'] == 0
    read.assert_called_once_with('http://127.0.0.1:2022', '/api/shared-capture/status', timeout=1)
    assert not (tmp_path / 'catalog.sqlite').exists()


def test_connection_diagnostic_never_starts_missing_backend(tmp_path, monkeypatch):
    binary = tmp_path / 'backend'; binary.write_bytes(b'fixture')
    descriptor = tmp_path / 'enabled.json'
    descriptor.write_text(json.dumps({'binary': str(binary), 'sha256': capture.sha_file(binary)}))
    monkeypatch.setattr(runtime, 'BACKEND', binary)
    monkeypatch.setattr(runtime, 'ENABLED', descriptor)
    monkeypatch.setattr(runtime, 'request', Mock(side_effect=CaptureError('transport_error')))
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *a, **k: pytest.fail('no backend fallback'))
    assert runtime.connection_status()['backend_started'] is False
