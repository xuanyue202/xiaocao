"""Serial, resumable ASR of accepted Liuguan artifacts with source binding.

The existing local-file ASR engine remains unchanged. This adapter verifies the
upstream artifact separately and binds its replay identity to the engine receipt.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import time
from .capture import DEFAULT_ROOT, sha_file
from .native import CaptureError, digest, save

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(os.environ.get('YANGSHENG_VAULT_ROOT', str(Path.home() / 'Documents/xuanyue notebook'))) / '_system/yangsheng-capture/capture.py'


def accepted_artifacts(root):
    # A single read-only SELECT is a consistent SQLite snapshot. Do not take the
    # writer's long native-scan/file-verification lock just to consume accepted
    # artifacts: that would race asynchronous worker startup.
    path = Path(root) / 'catalog.sqlite'
    if not path.is_file(): raise CaptureError('asr_catalog_not_initialized')
    try:
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("""SELECT a.*,r.created,r.duration FROM artifacts a
                JOIN replays r ON a.publisher=r.publisher AND a.replay=r.id ORDER BY r.created DESC,a.replay""")]
    except sqlite3.OperationalError:
        raise CaptureError('asr_catalog_read_unavailable') from None


def verify_source(row):
    proof = json.loads(row['proof'])
    if (proof.get('full_artifact_verified') is not True or proof.get('full_packet_read_verified') is not True
            or proof.get('replay_id') != row['replay'] or proof.get('publisher_sha256') != digest(row['publisher'])
            or proof.get('sha256') != row['sha256'] or proof.get('size') != row['size']
            or proof.get('expected_duration_seconds') != row['duration']):
        raise CaptureError('asr_upstream_proof_mismatch')
    path = Path(row['path']).resolve(strict=True)
    if path != Path(proof['path']).resolve() or path.stat().st_size != row['size'] or sha_file(path) != row['sha256']:
        raise CaptureError('asr_source_artifact_changed')
    return proof


def verify_receipt(result, row, state):
    if (result.get('status') != 'complete' or result.get('media_sha256') != row['sha256']
            or result.get('media_bytes') != row['size'] or result.get('video_id') != 'sha256:' + row['sha256']
            or result.get('video_written') is not False):
        raise CaptureError('asr_engine_binding_mismatch')
    count = result.get('sample_count'); duration = result.get('duration_seconds')
    if (type(count) is not int or count <= 0 or not isinstance(duration, (int, float))
            or duration != count / 16000 or abs(duration - row['duration']) > 2):
        raise CaptureError('asr_audio_coverage_mismatch')
    transcript = Path(result['transcript']).resolve(strict=True)
    expected_dir = (Path(state) / 'replays' / str(result['identity'])).resolve()
    if transcript.parent != expected_dir or transcript.name != 'transcript.md' or not transcript.is_relative_to(Path(state).resolve()):
        raise CaptureError('asr_transcript_path_mismatch')
    if sha_file(transcript) != result.get('transcript_sha256'):
        raise CaptureError('asr_transcript_changed')
    engine_receipt = expected_dir / 'receipt.json'
    if json.loads(engine_receipt.read_text()) != result:
        raise CaptureError('asr_engine_receipt_readback_mismatch')
    return transcript, engine_receipt


def transcribe_one(root, row, *, runner=subprocess.run):
    proof = verify_source(row)
    state = Path(root) / 'asr/engine'; state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # A changed output/hash must be investigated; never silently overwrite an
    # accepted transcript. The engine checks its own completed receipts as well.
    directory = Path(root) / 'asr/courses' / digest(row['publisher']) / row['replay']
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / 'receipt.json'
    if destination.exists():
        prior = json.loads(destination.read_text())
        if prior.get('status') == 'complete':
            if (prior.get('replay_id') != row['replay'] or prior.get('publisher_sha256') != digest(row['publisher'])
                    or prior.get('upstream_task_id') != proof['task_id']
                    or prior.get('source_proof_sha256') != hashlib.sha256(row['proof'].encode()).hexdigest()
                    or prior.get('media_sha256') != row['sha256'] or sha_file(prior['transcript']) != prior['transcript_sha256']):
                raise CaptureError('asr_completed_output_changed')
            if sha_file(prior['engine_receipt']) != prior['engine_receipt_sha256']:
                raise CaptureError('asr_completed_receipt_changed')
            verify_receipt(json.loads(Path(prior['engine_receipt']).read_text()), row, state)
            return {**prior, 'idempotent_replay': True}
    save(destination, {'status': 'in_progress', 'replay_id': row['replay'], 'media_sha256': row['sha256']})
    completed = runner([sys.executable, '-B', str(ENGINE), 'transcribe-local', '--state', str(state), '--media', row['path']],
        capture_output=True, text=True, timeout=14400)
    if completed.returncode:
        save(destination, {'status': 'incomplete', 'replay_id': row['replay'], 'media_sha256': row['sha256'], 'code': 'local_asr_engine_failed'})
        raise CaptureError('local_asr_engine_failed')
    result = json.loads(completed.stdout)
    transcript, engine_receipt = verify_receipt(result, row, state)
    verify_source(row)
    bound = {'status': 'complete', 'publisher_sha256': digest(row['publisher']), 'replay_id': row['replay'],
        'platform': 'wechat_channels', 'replay_published_at': row['created'], 'source_live_id_verified': False,
        'upstream_capture_verified': True, 'upstream_task_id': proof['task_id'],
        'source_proof_sha256': hashlib.sha256(row['proof'].encode()).hexdigest(),
        'media_sha256': row['sha256'], 'media_bytes': row['size'], 'media_path': row['path'],
        'sample_count': result['sample_count'], 'duration_seconds': result['duration_seconds'],
        'transcript': str(transcript), 'transcript_sha256': result['transcript_sha256'],
        'engine_receipt': str(engine_receipt), 'engine_receipt_sha256': sha_file(engine_receipt),
        'engine_producer_sha256': result['producer_sha256'], 'completed_at': time.time()}
    save(destination, bound)
    return bound


def run_pending(root=DEFAULT_ROOT, *, replay=None, limit=None):
    root = Path(root); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'asr-worker.lock').open('a') as lease:
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return {'status': 'busy', 'code': 'asr_worker_retained'}
        accepted = accepted_artifacts(root)
        if replay is not None:
            accepted = [row for row in accepted if row['replay'] == replay]
            if not accepted: raise CaptureError('asr_verified_replay_missing')
        rows = accepted if limit is None else accepted[:limit]
        results = []; failures = []
        for row in rows:
            try: results.append(transcribe_one(root, row))
            except (CaptureError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
                failures.append({'replay_id': row['replay'], 'publisher_sha256': digest(row['publisher']),
                    'code': str(error) if isinstance(error, CaptureError) else type(error).__name__})
        report = {'status': 'degraded' if failures else 'complete', 'courses': results,
            'count': len(results), 'failures': failures}
        save(root / 'asr-last-run.json', report)
        return report


def summary(root=DEFAULT_ROOT):
    counts = {'accepted_courses': 0, 'complete_receipts': 0, 'incomplete': 0, 'pending': 0, 'invalid_receipts': 0}
    for row in accepted_artifacts(root):
        counts['accepted_courses'] += 1
        receipt = Path(root) / 'asr/courses' / digest(row['publisher']) / row['replay'] / 'receipt.json'
        try:
            value = json.loads(receipt.read_text()) if receipt.exists() else {}
            if not isinstance(value, dict): raise ValueError('invalid receipt')
        except (OSError, ValueError, TypeError):
            counts['invalid_receipts'] += 1
            continue
        if (value.get('status') == 'complete' and value.get('media_sha256') == row['sha256']
                and value.get('source_proof_sha256') == hashlib.sha256(row['proof'].encode()).hexdigest()):
            counts['complete_receipts'] += 1
        elif value: counts['incomplete'] += 1
        else: counts['pending'] += 1
    return counts


def start_worker(root=DEFAULT_ROOT):
    """No independent schedule: each Local Capture may wake this one serial worker."""
    root = Path(root); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'asr-worker.log').open('a') as output:
        os.chmod(output.name, 0o600)
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        process = subprocess.Popen([sys.executable, '-m', 'xiaocao.yangsheng.asr', '--root', str(root)],
            stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True, env=env)
    return {'status': 'dispatched', 'pid': process.pid}


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--replay'); parser.add_argument('--limit', type=int); args = parser.parse_args()
    try:
        result = run_pending(args.root, replay=args.replay, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False))
        if result['status'] == 'degraded': raise SystemExit(1)
    except Exception as error:
        print(json.dumps({'status': 'incomplete', 'code': str(error) if isinstance(error, CaptureError) else type(error).__name__})); raise SystemExit(1)
