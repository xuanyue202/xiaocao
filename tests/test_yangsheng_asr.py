import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from xiaocao.yangsheng import asr, capture
from xiaocao.yangsheng.native import CaptureError, digest


@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / 'course.mp4'; path.write_bytes(b'accepted original video')
    sha = capture.sha_file(path)
    proof = {'task_id': 'same-download', 'replay_id': '123', 'publisher_sha256': digest('teacher@finder'),
        'path': str(path), 'size': path.stat().st_size, 'sha256': sha, 'expected_duration_seconds': 3,
        'full_artifact_verified': True, 'full_packet_read_verified': True}
    return {'publisher': 'teacher@finder', 'replay': '123', 'path': str(path), 'size': path.stat().st_size,
        'sha256': sha, 'proof': json.dumps(proof), 'created': 200, 'duration': 3}


def engine_runner(mutator=None):
    def run(command, **kwargs):
        state = Path(command[command.index('--state') + 1])
        media = Path(command[command.index('--media') + 1])
        directory = state / 'replays' / ('e' * 64); directory.mkdir(parents=True)
        transcript = directory / 'transcript.md'; transcript.write_text('0–3 秒：课程原文')
        result = {'status': 'complete', 'identity': 'e' * 64, 'video_id': 'sha256:' + capture.sha_file(media),
            'media_sha256': capture.sha_file(media), 'media_bytes': media.stat().st_size, 'video_written': False,
            'sample_count': 48000, 'duration_seconds': 3, 'transcript': str(transcript),
            'transcript_sha256': capture.sha_file(transcript), 'producer_sha256': 'c' * 64,
            'source_live_id_verified': False, 'upstream_capture_verified': False}
        if mutator is not None: mutator(result)
        (directory / 'receipt.json').write_text(json.dumps(result))
        return SimpleNamespace(returncode=0, stdout=json.dumps(result))
    return Mock(side_effect=run)


def test_actual_source_and_engine_receipts_bound_once(tmp_path, artifact):
    runner = engine_runner()
    result = asr.transcribe_one(tmp_path, artifact, runner=runner)
    assert result['upstream_capture_verified'] is True
    assert result['source_live_id_verified'] is False
    assert result['replay_id'] == '123' and result['upstream_task_id'] == 'same-download'
    assert result['sample_count'] == 48000 and result['duration_seconds'] == 3
    assert result['media_sha256'] == artifact['sha256']
    assert 'asr/engine' in runner.call_args.args[0][-3]
    repeat = asr.transcribe_one(tmp_path, artifact, runner=runner)
    assert repeat['idempotent_replay'] is True and runner.call_count == 1


@pytest.mark.parametrize('field,value', [('replay_id', '999'), ('publisher_sha256', 'a' * 64),
    ('full_packet_read_verified', False), ('expected_duration_seconds', 4)])
def test_invalid_upstream_binding_never_starts_asr(tmp_path, artifact, field, value):
    proof = json.loads(artifact['proof']); proof[field] = value; artifact['proof'] = json.dumps(proof)
    runner = Mock()
    with pytest.raises(CaptureError, match='upstream_proof_mismatch'): asr.transcribe_one(tmp_path, artifact, runner=runner)
    runner.assert_not_called()


def test_modified_source_never_starts_asr(tmp_path, artifact):
    Path(artifact['path']).write_bytes(b'changed video')
    runner = Mock()
    with pytest.raises(CaptureError, match='artifact_changed'): asr.transcribe_one(tmp_path, artifact, runner=runner)
    runner.assert_not_called()


@pytest.mark.parametrize('field,value,code', [('media_sha256', 'a' * 64, 'binding_mismatch'),
    ('status', 'in_progress', 'binding_mismatch'), ('sample_count', 16000, 'coverage_mismatch'),
    ('duration_seconds', 6, 'coverage_mismatch'), ('transcript_sha256', 'a' * 64, 'transcript_changed')])
def test_incomplete_or_wrong_engine_cannot_complete(tmp_path, artifact, field, value, code):
    runner = engine_runner(lambda result: result.update({field: value}))
    with pytest.raises(CaptureError, match=code): asr.transcribe_one(tmp_path, artifact, runner=runner)
    receipt = tmp_path / 'asr/courses' / digest(artifact['publisher']) / '123/receipt.json'
    assert json.loads(receipt.read_text())['status'] != 'complete'


@pytest.mark.parametrize('target', ['transcript', 'engine_receipt'])
def test_modified_completed_output_blocks_replay(tmp_path, artifact, target):
    runner = engine_runner(); result = asr.transcribe_one(tmp_path, artifact, runner=runner)
    Path(result[target]).write_text('changed')
    with pytest.raises(CaptureError, match='changed'): asr.transcribe_one(tmp_path, artifact, runner=runner)
    assert runner.call_count == 1


def test_asr_engine_failure_is_persisted_without_completion(tmp_path, artifact):
    runner = Mock(return_value=SimpleNamespace(returncode=1, stdout=''))
    with pytest.raises(CaptureError, match='local_asr_engine_failed'): asr.transcribe_one(tmp_path, artifact, runner=runner)
    receipt = tmp_path / 'asr/courses' / digest(artifact['publisher']) / '123/receipt.json'
    assert json.loads(receipt.read_text())['status'] == 'incomplete'


def test_asr_single_worker_avoids_duplicate_engine(tmp_path, monkeypatch):
    import fcntl
    with (tmp_path / 'asr-worker.lock').open('a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: pytest.fail('existing worker owns queue'))
        assert asr.run_pending(tmp_path)['status'] == 'busy'


def test_missing_replay_cannot_select_unrelated_course(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: [])
    with pytest.raises(CaptureError, match='verified_replay_missing'): asr.run_pending(tmp_path, replay='999')


def test_worker_can_read_accepted_snapshot_while_scan_owns_writer_lock(tmp_path, artifact):
    with capture.database(tmp_path) as db:
        with db:
            db.execute('INSERT INTO replays VALUES(?,?,?,?,?,?,?,?)',
                (artifact['publisher'], artifact['replay'], 200, 3, '{}', 'verified', 1, 1))
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',
                tuple(artifact[k] for k in ('publisher', 'replay', 'path', 'size', 'sha256', 'proof')))
        # The scan's EX flock stays held, but committed SQLite rows are readable.
        assert asr.accepted_artifacts(tmp_path)[0]['replay'] == '123'


def test_missing_catalog_does_not_become_empty_success(tmp_path):
    with pytest.raises(CaptureError, match='catalog_not_initialized'):
        asr.accepted_artifacts(tmp_path)


def test_bad_course_does_not_starve_other_verified_recordings(tmp_path, monkeypatch):
    rows = [{'publisher': 'teacher@finder', 'replay': '1'}, {'publisher': 'teacher@finder', 'replay': '2'}]
    monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: rows)
    def transcribe(root, row):
        if row['replay'] == '1': raise CaptureError('asr_source_artifact_changed')
        return {'status': 'complete', 'replay_id': '2'}
    monkeypatch.setattr(asr, 'transcribe_one', transcribe)
    result = asr.run_pending(tmp_path)
    assert result['status'] == 'degraded' and result['count'] == 1
    assert result['courses'][0]['replay_id'] == '2'
    assert result['failures'][0]['replay_id'] == '1'
    assert json.loads((tmp_path / 'asr-last-run.json').read_text()) == result


@pytest.mark.parametrize('kind', ['missing_field', 'invalid_type'])
def test_malformed_completed_receipt_does_not_stop_other_course(tmp_path, artifact, monkeypatch, kind):
    first = artifact
    second = {**artifact, 'replay': '124'}
    original = asr.transcribe_one
    path = tmp_path / 'asr/courses' / digest(first['publisher']) / '123/receipt.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': 'complete', 'media_sha256': first['sha256'],
        'replay_id': first['replay'], 'publisher_sha256': digest(first['publisher']),
        'upstream_task_id': 'same-download',
        'source_proof_sha256': hashlib.sha256(first['proof'].encode()).hexdigest()}) if kind == 'missing_field' else '[]')
    monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: [first, second])
    def transcribe(root, row):
        if row['replay'] == '124': return {'status': 'complete', 'replay_id': '124'}
        return original(root, row)
    monkeypatch.setattr(asr, 'transcribe_one', transcribe)
    result = asr.run_pending(tmp_path)
    assert result['status'] == 'degraded' and result['courses'][0]['replay_id'] == '124'
    assert result['failures'][0]['replay_id'] == '123'


@pytest.mark.parametrize('contents', ['{broken json', '[]'])
def test_summary_isolated_from_corrupt_receipt(tmp_path, artifact, monkeypatch, contents):
    monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: [artifact])
    receipt = tmp_path / 'asr/courses' / digest(artifact['publisher']) / '123/receipt.json'
    receipt.parent.mkdir(parents=True); receipt.write_text(contents)
    assert asr.summary(tmp_path)['invalid_receipts'] == 1


def test_shared_source_failures_use_existing_coordinator_retry_boundary():
    from xiaocao.kol.enrichment_types import EnrichmentError
    assert isinstance(CaptureError('shared_backend_lifecycle_busy'), EnrichmentError)


def test_native_scan_failure_still_dispatches_accepted_downloads(tmp_path, monkeypatch):
    from xiaocao.yangsheng import runtime, artifacts
    monkeypatch.setattr(runtime, 'initialize', lambda db: None)
    monkeypatch.setattr(runtime, 'ensure_backend', lambda *a: {'enabled': True})
    monkeypatch.setattr(artifacts, 'reconcile_artifacts', lambda *a: {'accepted': 1})
    monkeypatch.setattr(runtime, 'moments_snapshot', lambda *a: {})
    def unavailable(*args, **kwargs):
        with capture.database(tmp_path):
            raise CaptureError('native_socket_not_connected')
    monkeypatch.setattr(runtime, 'cycle', unavailable)
    calls = []
    def dispatch(root):
        # Reacquiring the writer lock proves dispatch follows scan unwinding.
        with capture.database(root): calls.append(root)
        return {'status': 'dispatched'}
    monkeypatch.setattr(asr, 'start_worker', dispatch)
    with pytest.raises(CaptureError, match='native_socket_not_connected'):
        runtime._run_local(tmp_path, 'http://127.0.0.1:23222')
    assert calls == [tmp_path]


def test_wake_during_old_worker_consumes_newly_accepted_course(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered = Event(); release = Event()
    rows = [{'publisher': 'teacher@finder', 'replay': 'A'}]
    completed = []
    monkeypatch.setattr(asr, 'accepted_artifacts', lambda *a: list(rows))
    def transcribe(root, row):
        if row['replay'] == 'A' and not entered.is_set():
            entered.set()
            assert release.wait(5)
        completed.append(row['replay'])
        return {'replay_id': row['replay'], 'status': 'complete'}
    monkeypatch.setattr(asr, 'transcribe_one', transcribe)
    with ThreadPoolExecutor(max_workers=2) as executor:
        old = executor.submit(asr.run_pending, tmp_path)
        assert entered.wait(5)
        rows.append({'publisher': 'teacher@finder', 'replay': 'B'})
        wake = executor.submit(asr.run_pending, tmp_path, wait_seconds=5)
        try:
            assert asr.run_pending(tmp_path)['status'] == 'busy'
        finally:
            release.set()
        assert old.result(timeout=5)['count'] == 1
        assert wake.result(timeout=5)['count'] == 2
    assert 'B' in completed
