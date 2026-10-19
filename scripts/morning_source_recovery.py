#!/usr/bin/env python3
"""Signal the exact live, uncommitted original morning producer once."""
import argparse
import json
from pathlib import Path
from xiaocao.live.morning_source_recovery import signal_recheck

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(signal_recheck(args.request), sort_keys=True))
