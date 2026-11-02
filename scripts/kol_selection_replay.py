#!/usr/bin/env python3
"""Benchmark local frozen-data to recommendation; never run a trading entry."""
import argparse
import json
from pathlib import Path
from xiaocao.kol.selection_replay import replay


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--analysis',type=Path)
    parser.add_argument('--raw-strategy',action='store_true')
    parser.add_argument('--date')
    parser.add_argument('--repeats',type=int,default=30)
    parser.add_argument('--p95-budget-ms',type=float,default=100.)
    args=parser.parse_args()
    report=replay(args.bundle_root,args.output_dir,repeats=args.repeats,p95_budget_ms=args.p95_budget_ms,
        analysis=json.loads(args.analysis.read_bytes()) if args.analysis else None,
        replay_raw_strategy=args.raw_strategy,trade_date=args.date)
    print(json.dumps({key:value for key,value in report.items() if key!='cases'},ensure_ascii=False))
    return 0 if report['performance_passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
