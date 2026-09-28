#!/usr/bin/env python3
"""Signal the waiting original morning process after its local repair."""
import argparse
import json
from pathlib import Path
from xiaocao.runner_recovery import signal_recheck


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(signal_recheck(args.request), sort_keys=True))


if __name__ == "__main__":
    main()
