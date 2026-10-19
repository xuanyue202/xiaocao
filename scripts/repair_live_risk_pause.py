#!/usr/bin/env python3
"""Review or append an evidence-bound correction; no broker actions."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.live.risk_history_repair import repair_false_pause


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--risk-ledger", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = repair_false_pause(args.state_dir, args.risk_ledger,
        expected_head=args.expected_head, now=datetime.now(timezone.utc), apply=args.apply)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
