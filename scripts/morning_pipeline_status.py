#!/usr/bin/env python3
"""Observe exact dated morning owners, remaining budgets and consumer receipts."""
import argparse
import json
from pathlib import Path
from xiaocao.live.morning_pipeline import save_pipeline_status

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--live-dir", type=Path, default=Path("output/live"))
    args = parser.parse_args()
    print(json.dumps(save_pipeline_status(args.live_dir, args.date)))
