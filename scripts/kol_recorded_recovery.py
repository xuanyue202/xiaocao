#!/usr/bin/env python3
"""Observe and bind one authorized recording without creating a capture."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import select
import sys
import time
from uuid import uuid4
from zoneinfo import ZoneInfo
from xiaocao.kol.daily import DailyCoordinator
from xiaocao.kol.human_playback import human_capture_network_owner, enable_capture_listener_pac
from xiaocao.kol.recorded_recovery import collect_recorded_proof, bind_recorded_recovery
from xiaocao.kol.replay_catalog import ReplayCatalogConfig, inspect_original
from xiaocao.kol.xiaocao_wechat import XiaocaoLiveCaptureDriver


def read_reply(stream, timeout=1200):
    deadline=time.monotonic()+timeout
    data=bytearray()
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0 or not select.select([stream],[],[],remaining)[0]:
            raise ValueError('recorded browser input timeout')
        part=os.read(stream.fileno(),4096)
        if not part or len(data)+len(part)>65536:
            raise ValueError('recorded browser input invalid')
        data.extend(part)
        if b'\n' in data:
            return json.loads(data.split(b'\n',1)[0])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity',required=True)
    parser.add_argument('--subscription-dir',type=Path,default=Path('output/live/kol_xiaocao_live/wechat_subscription'))
    parser.add_argument('--proof-path',type=Path,help='Resume only an existing same-original proof; no new Browser observation')
    args=parser.parse_args()
    root=args.subscription_dir.resolve()
    with human_capture_network_owner(root.parent/'native_share_bridge.json'):
        with DailyCoordinator(Path('output/live/kol_daily'))._source_locked('xiaocao_wechat_live'):
            item=json.loads((root/'manifest.json').read_text())['items'][args.identity]
            if item['identity']!=args.identity or item.get('human_playback_deferred'):
                raise ValueError('original not eligible')
            driver=XiaocaoLiveCaptureDriver(root)
            capture_id=item['capture_job_id']
            if args.proof_path:
                print(json.dumps(bind_recorded_recovery(root,args.identity,capture_id,args.proof_path,driver=driver),ensure_ascii=False),flush=True)
                return 0
            driver.require_idle_human_entry(args.identity,capture_id)
            config=ReplayCatalogConfig.from_dict(json.loads((root.parent/'native_share_bridge.json').read_text())['replay_catalog'])
            result=inspect_original(config,item)
            if not result.get('recording'):
                print(json.dumps(result,ensure_ascii=False),flush=True)
                return 0
            driver.prepare_human_playback(args.identity,capture_id)
            enable_capture_listener_pac()
            folder=root/'items'/args.identity
            nonce=uuid4().hex
            claim_path=folder/f'recorded-observation-{nonce}.json'
            claim=dict(identity=args.identity,capture_job_id=capture_id,
                resource_id=result['recording']['resource_id'],
                observed_after=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
            with claim_path.open('x') as f:
                json.dump(claim,f)
                f.write('\n')
            print(json.dumps(dict(event='daily_browser_input_required',
                action='observe_authorized_recorded_course',**claim,
                recording=result['recording'],observation_receipt_path=str(claim_path)),ensure_ascii=False),flush=True)
            reply=read_reply(sys.stdin)
            if reply.get('action')!='observe_authorized_recorded_course' or reply.get('identity')!=args.identity:
                raise ValueError('recorded response identity changed')
            driver.require_idle_human_entry(args.identity,capture_id)
            proof=collect_recorded_proof(root,args.identity,capture_id,reply['candidate_id'],
                player_duration=reply['player_duration_seconds'],player_left=reply['player_left'],
                driver=driver,observation_path=claim_path)
            proof_path=folder/f'recorded-proof-{nonce}.json'
            with proof_path.open('x') as f:
                json.dump(proof,f,ensure_ascii=False,indent=2)
                f.write('\n')
            print(json.dumps(bind_recorded_recovery(root,args.identity,capture_id,proof_path,driver=driver),ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'failed','error_type':type(exc).__name__}),flush=True)
        raise SystemExit(2)
