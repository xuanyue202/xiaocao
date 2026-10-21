#!/usr/bin/env python3
"""Local metadata companion for Liuguan; owns no native or downloader actions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('discover',))
    args = parser.parse_args()
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
