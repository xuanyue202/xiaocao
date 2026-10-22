#!/usr/bin/env python3
"""Exact Wu SNS snapshot, isolated decryption cache; emits no tokens or URLs."""
import argparse
import hashlib
import json
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE = 'wxid_02jgv2ozgk3r12'


def read_snapshot(parent):
    from wechat_cli.core.config import load_config
    from wechat_cli.core.db_cache import DBCache
    from wechat_cli.core.key_utils import strip_key_metadata
    cfg = load_config()
    keys = strip_key_metadata(json.loads(Path(cfg['keys_file']).read_text()))
    raw = Path(cfg['db_dir']) / 'sns/sns.db'; wal = Path(str(raw) + '-wal')
    def stamps(): return [(p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else None for p in (raw, wal)]
    with tempfile.TemporaryDirectory(prefix='sns-', dir=parent) as directory:
        class Cache(DBCache):
            CACHE_DIR = directory
            MTIME_FILE = str(Path(directory) / '_mtimes.json')
        before = stamps(); db = Cache(keys, cfg['db_dir']).get('sns/sns.db')
        if not db or before != stamps(): raise ValueError('sns_snapshot_unstable')
        with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as connection:
            rows = connection.execute("SELECT tid,content FROM SnsTimeLine WHERE user_name=? OR ((user_name IS NULL OR user_name='') AND instr(CAST(content AS TEXT),?)>0)", (SOURCE, SOURCE)).fetchall()
        posts = []; publishers = {}
        for identity, body in rows:
            node = ET.fromstring(body)
            if (node.findtext('./username') or node.findtext('.//username') or '').strip() != SOURCE: continue
            cards = []
            for kind in ('finderLive', 'finderFeed'):
                for card in node.findall('.//' + kind):
                    username = card.findtext('finderUsername') or card.findtext('username') or ''
                    if not username.endswith('@finder'): continue
                    entry = publishers.setdefault(username, {'finder_username': username, 'observed_names': []})
                    name = card.findtext('nickname') or ''
                    if name and name not in entry['observed_names']: entry['observed_names'].append(name)
                    cards.append({'publisher_sha256': hashlib.sha256(username.encode()).hexdigest(), 'kind': kind,
                        'live_id': card.findtext('finderLiveID') or '', 'object_id': card.findtext('finderObjectID') or card.findtext('objectId') or ''})
            posts.append({'moment_id': str(identity), 'source_sha256': hashlib.sha256(body if isinstance(body, bytes) else body.encode()).hexdigest(), 'timestamp': int(node.findtext('.//createTime') or 0), 'cards': cards})
        return {'source_snapshot_stable': True, 'publishers': list(publishers.values()), 'posts': posts, 'server_coverage_proven': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--state-dir', required=True); args = parser.parse_args()
    try: print(json.dumps(read_snapshot(args.state_dir), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'code': type(error).__name__})); raise SystemExit(1)
