#!/usr/bin/env python3
"""Inspect an original's recorded-course identity without entry or download."""
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.replay_catalog import (
    ReplayCatalogConfig, ReplayCatalogError, inspect_original, verify_original,
)
from xiaocao.kol.enrichment_types import EnrichmentError
from xiaocao.kol.xiaocao_wechat import WechatCliHistoryReader, parse_xiaocao_live_messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--subscription-dir', type=Path,
        default=Path('output/live/kol_xiaocao_live/wechat_subscription'))
    parser.add_argument('--inspect-access', action='store_true')
    args = parser.parse_args()
    try:
        bridge = json.loads((args.subscription_dir.parent/'native_share_bridge.json').read_text())
        config = ReplayCatalogConfig.from_dict(bridge.get('replay_catalog'))
        items = json.loads((args.subscription_dir/'manifest.json').read_text())['items']
        item = items[args.identity]
        if item.get('identity') != args.identity:
            raise ReplayCatalogError('original_identity_changed')
        if item.get('human_playback_deferred') or item.get('status') in {'completed', 'handoff_ready'}:
            raise ReplayCatalogError('original_not_eligible_for_catalog_recovery')
        try:
            originals = parse_xiaocao_live_messages(WechatCliHistoryReader()())
            verify_original(item, args.identity, originals)
        except EnrichmentError:
            raise ReplayCatalogError('original_history_unavailable') from None
        result = inspect_original(config, item, originals=originals,
                                  inspect_access=args.inspect_access)
        result['observed_at'] = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ReplayCatalogError, OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc) if isinstance(exc, ReplayCatalogError) else 'catalog_local_evidence_invalid'
        print(json.dumps({
            'status':'action_required','code':code,'identity':args.identity,
            'owner':'agent','stage':'recorded_catalog',
            'next_action':'diagnose_repair_then_exact_resume',
            'download_attempted':False,
        }))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
