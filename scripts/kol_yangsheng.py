#!/usr/bin/env python3
"""Liuguan metadata discovery and opt-in shared local capture."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import select
from time import monotonic
import subprocess
import sys


def _visible_refresh(timeout=30):
    from xiaocao.yangsheng.native import CaptureError
    # Leave the 60-second PAC guardian enough time for the socket readback.
    print(json.dumps({'event': 'liuguan_visible_refresh_required', 'action': 'refresh_existing_verified_native_replay_once', 'deadline_seconds': timeout}), flush=True)
    deadline = monotonic() + timeout
    chunks = b''
    descriptor = sys.stdin.fileno()
    while b'\n' not in chunks:
        remaining = deadline - monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise CaptureError('native_refresh_timeout')
        chunk = os.read(descriptor, 64)
        if not chunk or len(chunks) + len(chunk) > 64:
            raise CaptureError('native_refresh_not_confirmed')
        chunks += chunk
    if chunks.split(b'\n', 1)[0].strip() != b'refreshed':
        raise CaptureError('native_refresh_not_confirmed')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('discover', 'capture', 'finish', 'bootstrap', 'status', 'connections', 'asr'))
    parser.add_argument('--window-id', type=int); parser.add_argument('--pid', type=int)
    parser.add_argument('--visible-refresh', action='store_true', help='Retained PTY handshake for one freshly verified native File/Refresh action')
    parser.add_argument('--replay', help='One previously accepted replay for ASR')
    parser.add_argument('--api', default='http://127.0.0.1:2022')
    parser.add_argument('--reconnect-wait', type=float, default=0, help='Passive socket wait for connections only, 0..35 seconds')
    args = parser.parse_args()
    if args.command != 'discover':
        from xiaocao.yangsheng.capture import CaptureError, DEFAULT_ROOT, database, initialize
        from xiaocao.yangsheng.runtime import run_local, finish, bootstrap, connection_status
        try:
            if args.command == 'connections':
                value = connection_status(args.api, reconnect_wait=args.reconnect_wait)
            elif args.command == 'asr':
                from xiaocao.yangsheng.asr import run_pending
                value = run_pending(replay=args.replay)
            elif args.command == 'capture': value = run_local(api=args.api)
            elif args.command == 'finish': value = finish(api=args.api)
            elif args.command == 'bootstrap':
                if not args.visible_refresh and (not args.window_id or not args.pid): parser.error('fresh verified window ID and PID required')
                value = bootstrap(args.window_id, args.pid, api=args.api, refresh=_visible_refresh if args.visible_refresh else None)
            else:
                with database(DEFAULT_ROOT) as db:
                    initialize(db)
                    value = {'status': 'inventory', 'publisher_count': db.execute('SELECT count(*) FROM publishers').fetchone()[0],
                        'replay_count': db.execute('SELECT count(*) FROM replays').fetchone()[0],
                        'verified_count': db.execute('SELECT count(*) FROM artifacts').fetchone()[0],
                        'states': dict(db.execute('SELECT state,count(*) FROM replays GROUP BY state').fetchall())}
                from xiaocao.yangsheng.asr import summary
                value['asr'] = summary(DEFAULT_ROOT)
        except CaptureError as error: value = {'status': 'degraded', 'code': str(error)}
        print(json.dumps(value, ensure_ascii=False)); return 0 if value['status'] not in ('degraded',) else 1
    vault = Path(os.environ.get('YANGSHENG_VAULT_ROOT', str(Path.home() / 'Documents/xuanyue notebook')))
    entry = vault / '_system/yangsheng-capture/capture.py'
    if not entry.is_file():
        print(json.dumps({'status': 'source_unavailable', 'code': 'local_yangsheng_adapter_missing'}))
        return 1
    try:
        result = subprocess.run([sys.executable, '-B', str(entry), args.command],
                                capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print(json.dumps({'status': 'source_failed', 'code': 'yangsheng_adapter_timeout'}))
        return 1
    except OSError:
        print(json.dumps({'status': 'source_unavailable', 'code': 'yangsheng_adapter_start_failed'}))
        return 1
    # The adapter exports only credential-free metadata and fixed error codes.
    try:
        value = json.loads(result.stdout if result.returncode == 0 else result.stderr)
    except (ValueError, TypeError):
        value = {'status': 'source_failed', 'code': 'yangsheng_adapter_invalid_response'}
    if not isinstance(value, dict):
        value = {'status': 'source_failed', 'code': 'yangsheng_adapter_invalid_response'}
    if result.returncode:
        reason = value.get('reason', '')
        value = {'status': 'source_failed', 'code': 'yangsheng_adapter_failed',
                 'adapter_reason': reason if isinstance(reason, str) and re.fullmatch(r'[a-zA-Z_]{1,64}', reason) else 'unknown'}
    elif (value.get('status') != 'discovered'
          or any(type(value.get(key)) is not int or value[key] < 0
                 for key in ('notifications', 'moment_count', 'live_candidate_count'))
          or value.get('coverage') != 'local_wechat_cache_only'
          or value.get('capture_status') != 'awaiting_replay_metadata'):
        value = {'status': 'source_failed', 'code': 'yangsheng_adapter_invalid_response'}
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value.get('status') == 'discovered' else 1


if __name__ == '__main__':
    raise SystemExit(main())
