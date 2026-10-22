"""Verify finished Gopeed media and drain shared tasks before shutdown."""
import json
import math
import subprocess
import time
from pathlib import Path
from .capture import DEFAULT_ROOT, database, find_task, labels, sha_file, task_identity, tasks
from .native import CaptureError, request, finite_duration


def verify_task(task, publisher, record, spec, download_root):
    if labels(task).get('id') != task_identity(publisher, record['replay_id']) or labels(task).get('spec', '') != spec:
        raise CaptureError('artifact_shared_task_binding_changed')
    meta = task.get('meta') or {}; resource = meta.get('res') or {}; opts = meta.get('opts') or {}
    size = resource.get('size'); downloaded = (task.get('progress') or {}).get('downloaded')
    if task.get('status') != 'done' or type(size) is not int or size <= 0 or downloaded != size:
        raise CaptureError('shared_artifact_not_complete')
    path = (Path(opts['path']) / opts['name']).resolve(strict=True)
    allowed = (Path(download_root) / 'liuguan').resolve()
    if not path.is_relative_to(allowed) or path.stat().st_size != size:
        raise CaptureError('shared_artifact_path_or_size_mismatch')
    before = path.stat()
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries',
        'format=duration,size:stream=codec_type,codec_name,duration,width,height', '-of', 'json', str(path)], capture_output=True, timeout=120)
    if result.returncode: raise CaptureError('shared_artifact_probe_failed')
    probe = json.loads(result.stdout)
    streams = [s for s in probe.get('streams', []) if s.get('codec_type') in ('audio', 'video')]
    if {s['codec_type'] for s in streams} != {'audio', 'video'}: raise CaptureError('shared_artifact_missing_track')
    for stream in [probe['format'], *streams]:
        duration = float(stream.get('duration', 'nan'))
        if not finite_duration(duration) or not finite_duration(record['duration_seconds']) or abs(duration - record['duration_seconds']) > 2:
            raise CaptureError('shared_artifact_duration_mismatch')
    packet = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-i', str(path),
        '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-f', 'null', '-'], capture_output=True, timeout=300)
    if packet.returncode or packet.stderr: raise CaptureError('shared_artifact_packet_read_failed')
    sha = sha_file(path); after = path.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
        raise CaptureError('shared_artifact_changed_during_verification')
    return {'path': str(path), 'size': size, 'sha256': sha, 'task_id': task['id'], 'replay_id': record['replay_id'],
        'publisher_sha256': record['publisher_sha256'], 'expected_duration_seconds': record['duration_seconds'],
        'probe': probe, 'full_packet_read_verified': True, 'source_live_id_verified': False, 'full_artifact_verified': True}


def reconcile_artifacts(root=DEFAULT_ROOT, api='http://127.0.0.1:2022'):
    health = request(api, '/api/shared-capture/status')
    if health.get('enabled') is not True: raise CaptureError('shared_backend_not_enabled')
    accepted = []; waiting = []; failures = []
    with database(Path(root)) as db:
        for job in db.execute('SELECT * FROM jobs').fetchall():
            if db.execute('SELECT 1 FROM artifacts WHERE publisher=? AND replay=?', (job['publisher'], job['replay'])).fetchone(): continue
            task = find_task(api, job['publisher'], job['replay'], job['spec'], job['task_id'])
            if task is None:
                waiting.append({'replay_id': job['replay'], 'code': 'pending_shared_task_unresolved'}); continue
            with db: db.execute('UPDATE jobs SET task_id=?,state=?,updated=? WHERE publisher=? AND replay=?', (task['id'], task['status'], time.time(), job['publisher'], job['replay']))
            if task['status'] != 'done':
                (failures if task['status'] == 'error' else waiting).append({'replay_id': job['replay'], 'task_id': task['id'], 'status': task['status']}); continue
            if task['id'] in health.get('post_processing_active', []):
                waiting.append({'replay_id': job['replay'], 'code': 'shared_post_processing_active'}); continue
            record = json.loads(db.execute('SELECT metadata FROM replays WHERE publisher=? AND id=?', (job['publisher'], job['replay'])).fetchone()[0])
            try: proof = verify_task(task, job['publisher'], record, job['spec'], health['download_dir'])
            except CaptureError as error:
                failures.append({'replay_id': job['replay'], 'code': str(error)}); continue
            with db:
                db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)', (job['publisher'], job['replay'], proof['path'], proof['size'], proof['sha256'], json.dumps(proof)))
                db.execute("UPDATE replays SET state='verified' WHERE publisher=? AND id=?", (job['publisher'], job['replay']))
            accepted.append({'replay_id': job['replay'], 'task_id': task['id'], 'sha256': proof['sha256']})
    return {'accepted': accepted, 'waiting': waiting, 'failures': failures}


def drain_before_shutdown(root=DEFAULT_ROOT, api='http://127.0.0.1:2022', timeout=1200):
    deadline = time.monotonic() + timeout
    while True:
        proof = reconcile_artifacts(root, api)
        active = [t for t in tasks(api) if t.get('status') in ('running', 'ready', 'wait')]
        health = request(api, '/api/shared-capture/status')
        processing = health.get('post_processing_active')
        if not isinstance(processing, list): raise CaptureError('shared_post_processing_status_unverified')
        if proof['failures']: raise CaptureError('shared_artifact_verification_failed')
        paused = any(r.get('status') == 'pause' for r in proof['waiting'])
        if paused: raise CaptureError('shared_owned_task_paused')
        if not active and not processing and not proof['waiting']: return proof
        if time.monotonic() >= deadline: raise CaptureError('shared_downloads_still_active')
        time.sleep(min(10, max(0, deadline-time.monotonic())))
