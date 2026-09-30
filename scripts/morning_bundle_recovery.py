#!/usr/bin/env python3
"""Recover only the original bytes cited by one morning dependency request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.live.morning_bundle import recover_request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--live-dir", type=Path, default=Path("output/live"))
    args = parser.parse_args()
    result = recover_request(args.request, args.live_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.get("status") == "ready" else 1)


if __name__ == "__main__":
    main()
