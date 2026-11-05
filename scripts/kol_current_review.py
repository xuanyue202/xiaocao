#!/usr/bin/env python3
"""Register/wait for an owner-bound, preloaded current-applicability analyst."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from xiaocao.live import current_review
from xiaocao.kol import opening_preparation as prep


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['register', 'wait', 'paper-prepare'])
    p.add_argument('--warmup', type=Path)
    p.add_argument('--dispatch', type=Path)
    p.add_argument('--loaded', type=Path)
    p.add_argument('--worker-id')
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    now = datetime.now(prep.TZ)
    try:
        if a.command == 'paper-prepare':
            import os
            from xiaocao.live.paper_morning_kol import owner_binding
            from xiaocao.kol.rolling_preparation import registered
            from xiaocao.kol.trading_context import build_trading_context, write_trading_projection
            from xiaocao.live.runtime_snapshot import operational_root
            run = Path(os.environ['XIAOCAO_DAILY_RUN_DIR'])
            binding = owner_binding(run, now.date().isoformat())
            if now >= now.replace(hour=9, minute=20, second=0, microsecond=0):
                print(json.dumps({'event':'paper_kol_current_warmup', 'warmup_path':None,
                                  'authority':0, 'status':'registration_window_closed'}))
                return 0
            state_root = operational_root(a.root)
            source = registered(state_root, now=now)
            input_path = None
            if source:
                summary = write_trading_projection(build_trading_context(repo_root=state_root,
                    as_of=now, read_report_ids=[], include_report_bodies=False), repo_root=state_root)
                inputs = prep.input_payload(summary, binding=binding, repo_root=state_root)
                input_path = prep.write_artifact(run, inputs, '.early-kol-inputs.json')
            path = current_review.prepare(run, binding, source[0], now=now, root=a.root,
                current_input_path=input_path) if source else None
            value = {'event':'paper_kol_current_warmup', 'warmup_path':str(path) if path else None,
                     'authority':0, 'status':'ready' if path else 'unavailable'}
        elif a.command == 'register':
            value = current_review.register(a.warmup, prep.read_json(a.dispatch), prep.read_json(a.loaded), now=now)
        else:
            current_review.record_loaded(a.warmup, worker_id=a.worker_id, now=now)
            print(json.dumps({'event':'current_worker_preloaded', 'loaded_path':str(a.warmup.with_suffix('.loaded.json'))}), flush=True)
            value = current_review.wait(a.warmup, worker_id=a.worker_id)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({'status':'deferred', 'reason': str(e) if str(e).startswith('CURRENT_REVIEW_') else type(e).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
