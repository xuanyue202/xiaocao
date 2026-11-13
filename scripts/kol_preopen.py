#!/usr/bin/env python3
"""Record actual original-source preparation dispatch/review or inspect its proof."""
import argparse
import json
from pathlib import Path
from xiaocao.kol import preopen_program as program


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['dispatch','review-open','worker-terminal','status'])
    parser.add_argument('--input',type=Path)
    parser.add_argument('--dispatch',type=Path)
    parser.add_argument('--context',type=Path)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--program',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='dispatch':
            if not args.input or not args.dispatch:parser.error('dispatch requires --input and --dispatch')
            result=program.record_dispatch(args.input,args.dispatch,now=program.clock())
        elif args.command=='worker-terminal':
            if not args.input or not args.receipt:parser.error('worker-terminal requires --input and --receipt')
            result=program.record_worker_terminal(args.input,args.receipt,now=program.clock())
        elif args.command=='review-open':
            if not args.input or not args.context:parser.error('review-open requires --input and --context')
            result=program.record_review(args.input,args.context,now=program.clock())
        else:
            if not args.program:parser.error('status requires --program')
            plan=program.read(args.program)
            status_path=args.program.with_name('status.json')
            result={'plan':plan,'status':json.loads(status_path.read_bytes()) if status_path.exists() else {'status':'not_observed'}}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'blocked','reason':str(exc) if str(exc).startswith('KOL_PREOPEN_') else type(exc).__name__}))
        return 2


if __name__=='__main__':raise SystemExit(main())
