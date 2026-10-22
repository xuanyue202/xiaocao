"""Durable replay inventory and exact-once jobs in the shared Gopeed singleton."""
from __future__ import annotations
import fcntl
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
from zoneinfo import ZoneInfo
from time import sleep
from .native import CaptureError, digest, evidence, finite_duration, publisher_objects, request

DEFAULT_ROOT = Path.home() / '.codex/yangsheng-capture/production'
VALIDATION = Path.home() / '.codex/yangsheng-capture/upstream-validation-20261022'
SEEDS = Path.home() / '.codex/yangsheng-capture/native-validation/matrix/cached-publishers.json'


@contextmanager
def lifecycle_lease(root=DEFAULT_ROOT, *, closing=False):
    """Prevent creates racing final drain and termination; always before DB locks."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'backend-lifecycle.lock').open('a') as lease:
        try:
            fcntl.flock(lease, (fcntl.LOCK_EX if closing else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CaptureError('shared_backend_lifecycle_busy') from None
        yield


@contextmanager
def database(root: Path):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'capture.lock').open('a') as lease:
        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise CaptureError('liuguan_capture_busy') from None
        db = sqlite3.connect(root / 'catalog.sqlite', timeout=2)
        db.row_factory = sqlite3.Row
        db.executescript('''
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS publishers(username TEXT PRIMARY KEY,aliases TEXT NOT NULL,verified_at REAL);
          CREATE TABLE IF NOT EXISTS replays(publisher TEXT NOT NULL,id TEXT NOT NULL,created INTEGER NOT NULL,
            duration REAL,metadata TEXT NOT NULL,state TEXT NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL,
            PRIMARY KEY(publisher,id));
          CREATE TABLE IF NOT EXISTS jobs(publisher TEXT NOT NULL,replay TEXT NOT NULL,spec TEXT NOT NULL,
            task_id TEXT,state TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(publisher,replay));
          CREATE TABLE IF NOT EXISTS artifacts(publisher TEXT NOT NULL,replay TEXT NOT NULL,path TEXT NOT NULL,
            size INTEGER NOT NULL,sha256 TEXT NOT NULL,proof TEXT NOT NULL,PRIMARY KEY(publisher,replay));
          CREATE TABLE IF NOT EXISTS publisher_checks(publisher TEXT PRIMARY KEY,state TEXT NOT NULL,observed_at REAL NOT NULL,evidence TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS moments(id TEXT PRIMARY KEY,content_hash TEXT NOT NULL,metadata TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS cycles(id INTEGER PRIMARY KEY,started REAL NOT NULL,finished REAL,
            covered INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL,errors TEXT NOT NULL DEFAULT '[]');
        ''')
        try: yield db
        finally: db.close()


def sha_file(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''): sha.update(chunk)
    return sha.hexdigest()


def initialize(db, seeds=SEEDS, validation=VALIDATION):
    if db.execute("SELECT 1 FROM meta WHERE key='baseline'").fetchone(): return
    registry = json.loads(Path(seeds).read_text())
    catalog = json.loads((Path(validation) / 'matrix-capture.json').read_text())
    proof = json.loads((Path(validation) / 'three-replay-acceptance.json').read_text())
    if not catalog.get('all_publishers_complete') or len(catalog['publishers']) != 33 or not proof.get('capture_completed'):
        raise CaptureError('verified_initial_baseline_required')
    if hashlib.sha256(Path(seeds).read_bytes()).hexdigest() != catalog['seed_snapshot_sha256']:
        raise CaptureError('baseline_registry_binding_changed')
    names = {digest(p['finder_username']): p['finder_username'] for p in registry['publishers']}
    if len(names) != 33: raise CaptureError('baseline_registry_invalid')
    for item in proof['accepted']:
        path = Path(item['path'])
        if not path.is_file() or path.stat().st_size != item['size'] or sha_file(path) != item['sha256']:
            raise CaptureError('baseline_artifact_changed')
    now = time.time()
    with db:
        for p in registry['publishers']:
            db.execute('INSERT INTO publishers VALUES(?,?,?)', (p['finder_username'], json.dumps(p['observed_names'], ensure_ascii=False), catalog['snapshot_saved_at']))
        for record in catalog['replays']:
            db.execute('INSERT INTO replays VALUES(?,?,?,?,?,?,?,?)', (names[record['publisher_sha256']], record['replay_id'], record['created_at'], record['duration_seconds'], json.dumps(record, ensure_ascii=False), 'baseline', now, now))
        for item in proof['accepted']:
            publisher = names[item['publisher_sha256']]
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)', (publisher, item['replay_id'], item['path'], item['size'], item['sha256'], json.dumps(item)))
            db.execute("UPDATE replays SET state='verified' WHERE publisher=? AND id=?", (publisher, item['replay_id']))
        db.execute('INSERT INTO meta VALUES(?,?)', ('baseline', str(catalog['snapshot_saved_at'])))


def task_identity(publisher, replay):
    return 'liuguan:' + digest(publisher) + ':' + replay


def tasks(api):
    result = []
    for page in range(1, 101):
        data = request(api, f'/api/task/list?page={page}&page_size=500')
        result.extend(data.get('list') or [])
        if page * 500 >= data.get('total', len(result)): return result
    raise CaptureError('shared_task_lookup_limit')


def labels(task):
    return ((task.get('meta') or {}).get('req') or {}).get('labels') or {}


def find_task(api, publisher, replay, spec, expected=None):
    rows = [t for t in tasks(api) if labels(t).get('id') == task_identity(publisher, replay) and labels(t).get('spec', '') == spec]
    if expected is not None: rows = [t for t in rows if t.get('id') == expected]
    if len(rows) > 1: raise CaptureError('ambiguous_shared_task')
    if expected is not None and not rows: raise CaptureError('retained_shared_task_missing')
    return rows[0] if rows else None


def record_replays(db, publisher, objects, now):
    baseline = float(db.execute("SELECT value FROM meta WHERE key='baseline'").fetchone()[0])
    for obj in objects.values():
        record = evidence(obj)
        existing = db.execute('SELECT * FROM replays WHERE publisher=? AND id=?', (publisher, record['replay_id'])).fetchone()
        if existing:
            if existing['created'] != record['created_at'] or (existing['duration'] or None) != record['duration_seconds']:
                raise CaptureError('retained_replay_binding_changed')
            db.execute('UPDATE replays SET metadata=?,last_seen=? WHERE publisher=? AND id=?', (json.dumps(record, ensure_ascii=False), now, publisher, record['replay_id']))
        else:
            state = 'pending' if record['created_at'] > baseline else 'historical_discovered'
            db.execute('INSERT INTO replays VALUES(?,?,?,?,?,?,?,?)', (publisher, record['replay_id'], record['created_at'], record['duration_seconds'], json.dumps(record, ensure_ascii=False), state, now, now))


def create_task(db, api, publisher, obj):
    record = evidence(obj); replay = record['replay_id']
    old = db.execute('SELECT * FROM jobs WHERE publisher=? AND replay=?', (publisher, replay)).fetchone()
    if old:
        found = find_task(api, publisher, replay, old['spec'], old['task_id'])
        if found is None: raise CaptureError('pending_shared_task_unresolved')
        with db: db.execute('UPDATE jobs SET task_id=?,state=?,updated=? WHERE publisher=? AND replay=?', (found['id'], found['status'], time.time(), publisher, replay))
        return found
    if not finite_duration(record['duration_seconds']) or not record['media_url_observed']:
        raise CaptureError('replay_media_not_ready')
    media = obj['objectDesc']['media'][0]
    choices = [s for s in media.get('spec') or [] if s.get('fileFormat') and finite_duration(s.get('bitRate'))]
    spec = min(choices, key=lambda s: s['bitRate'])['fileFormat'] if choices else ''
    found = find_task(api, publisher, replay, spec)
    if found is not None:
        with db: db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', (publisher, replay, spec, found['id'], found['status'], time.time()))
        return found
    media_url = str(media['url']) + str(media.get('urlToken') or '')
    parsed = urlsplit(media_url)
    if parsed.scheme != 'https' or not parsed.hostname or not any(parsed.hostname == h or parsed.hostname.endswith('.' + h) for h in ('video.qq.com', 'tc.qq.com')) or parsed.username:
        raise CaptureError('unexpected_native_media_host')
    # Keep signed ticket bytes unchanged. Only append the verified format selector.
    if parsed.fragment or (spec and re.fullmatch(r'[A-Za-z0-9_-]+', spec) is None):
        raise CaptureError('invalid_native_media_format')
    selectors = [value for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key == 'X-snsvideoflag']
    if selectors and selectors != [spec]:
        raise CaptureError('native_media_format_conflict')
    if spec and not selectors:
        media_url += ('&' if parsed.query else '?') + 'X-snsvideoflag=' + spec
    try: key = int(media.get('decodeKey') or 0)
    except (ValueError, TypeError): raise CaptureError('invalid_native_decode_key') from None
    if not 0 <= key < 2**63: raise CaptureError('native_decode_key_out_of_range')
    date = datetime.fromtimestamp(record['created_at'], ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
    payload = {'id': task_identity(publisher, replay), 'nonce_id': obj.get('objectNonceId', ''), 'url': media_url,
               'title': record['title'], 'key': key, 'spec': spec, 'suffix': '.mp4',
               'filename': 'liuguan/' + date + '-' + replay + ('_' + spec if spec else '_original')}
    with db: db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', (publisher, replay, spec, None, 'pending_create', time.time()))
    try: result = request(api, '/api/task/create', payload)
    except CaptureError:
        found = find_task(api, publisher, replay, spec)
        if found is None: raise
    else:
        task_id = result.get('id')
        if not isinstance(task_id, str) or not task_id: raise CaptureError('created_shared_task_id_missing')
        found = find_task(api, publisher, replay, spec, task_id)
    with db: db.execute('UPDATE jobs SET task_id=?,state=?,updated=? WHERE publisher=? AND replay=?', (found['id'], found['status'], time.time(), publisher, replay))
    return found


def ingest_moments(db, snapshot):
    if not snapshot.get('source_snapshot_stable'): raise CaptureError('moments_snapshot_unstable')
    for publisher in snapshot['publishers']:
        username = publisher['finder_username']
        if not username.endswith('@finder'): raise CaptureError('moments_publisher_invalid')
        db.execute('INSERT INTO publishers(username,aliases) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET aliases=excluded.aliases', (username, json.dumps(publisher.get('observed_names') or [], ensure_ascii=False)))
    changed = 0
    for post in snapshot['posts']:
        existing = db.execute('SELECT content_hash FROM moments WHERE id=?', (post['moment_id'],)).fetchone()
        if existing is None or existing[0] != post['source_sha256']: changed += 1
        db.execute('INSERT INTO moments VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,metadata=excluded.metadata', (post['moment_id'], post['source_sha256'], json.dumps(post, ensure_ascii=False)))
    return changed


def cycle(root=DEFAULT_ROOT, api='http://127.0.0.1:2022', *, moments_snapshot=None, create=True):
    with lifecycle_lease(root), database(Path(root)) as db:
        initialize(db)
        moments_changed = None
        if moments_snapshot is not None:
            with db: moments_changed = ingest_moments(db, moments_snapshot)
        publishers = [r[0] for r in db.execute('SELECT username FROM publishers ORDER BY username')]
        try: health = request(api, '/api/shared-capture/status')
        except CaptureError as error:
            return {'status': 'waiting', 'code': 'shared_backend_unavailable', 'detail': str(error)}
        if health.get('enabled') is not True or health.get('engine') != 'gopeed':
            return {'status': 'waiting', 'code': 'shared_backend_upgrade_required'}
        if health.get('channels_available') is not True:
            return {'status': 'waiting', 'code': 'liuguan_native_connection_required', 'publisher_count': len(publishers)}
        started = time.time()
        with db:
            cursor = db.execute('INSERT INTO cycles(started,total) VALUES(?,?)', (started, len(publishers)))
            cycle_id = cursor.lastrowid
        covered = 0; errors = []; created = []; deactivated = []; retries = 0
        for index, username in enumerate(publishers):
            if index: sleep(2)
            progress = {'pages': 0}
            try:
                objects = publisher_objects(api, username, 50, 2, progress)
                with db:
                    record_replays(db, username, objects, time.time())
                    db.execute('UPDATE publishers SET verified_at=? WHERE username=?', (time.time(), username))
                    db.execute('INSERT OR REPLACE INTO publisher_checks VALUES(?,?,?,?)', (username, 'available', time.time(), '{}'))
                covered += 1
                if create:
                    for obj in sorted(objects.values(), key=lambda x: x['createtime']):
                        row = db.execute('SELECT state FROM replays WHERE publisher=? AND id=?', (username, str(obj['id']))).fetchone()
                        if row['state'] == 'pending':
                            task = create_task(db, api, username, obj)
                            created.append({'replay_id': str(obj['id']), 'task_id': task['id'], 'status': task['status']})
            except CaptureError as error:
                if str(error) == 'publisher_deactivated':
                    proof = {'publisher_sha256': digest(username), 'provider_nickname': '账号已注销', 'provider_code': -5900, 'identity_verified': True}
                    deactivated.append(proof)
                    with db:
                        db.execute('INSERT OR REPLACE INTO publisher_checks VALUES(?,?,?,?)', (username, 'deactivated', time.time(), json.dumps(proof, ensure_ascii=False)))
                    continue
                errors.append({'publisher_sha256': digest(username), 'code': str(error)})
                if str(error) not in ('request_timeout', 'sdk_decode_failed', 'sdk_request_busy', 'replay_media_not_ready', 'publisher_unavailable'): break
            finally:
                retries += progress.get('retries', 0)
        with db: db.execute('UPDATE cycles SET finished=?,covered=?,errors=? WHERE id=?', (time.time(), covered, json.dumps(errors), cycle_id))
        return {'status': 'scanned' if covered + len(deactivated) == len(publishers) and not errors else 'degraded', 'cycle_id': cycle_id,
                'publisher_count': len(publishers), 'covered': covered, 'assessed': covered + len(deactivated),
                'deactivated': deactivated, 'retries': retries, 'catalog_count': db.execute('SELECT count(*) FROM replays').fetchone()[0],
                'moments_changed': moments_changed, 'tasks': created, 'errors': errors}
