#!/usr/bin/env python3
"""Bound original-request recovery; credentials never enter argv or output."""
import argparse
import json
from pathlib import Path

from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient
from xiaocao.live.foundersc_session_recovery import recover_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--phase", choices=["restart", "fill", "claim-login", "finish"], required=True)
    args = parser.parse_args()
    native = FounderscNativeAXClient()
    native.refresh_helper()
    print(json.dumps(recover_session(args.request, native=native, phase=args.phase), ensure_ascii=False))


if __name__ == "__main__":
    main()
