#!/usr/bin/env python3
"""Verify native WeChat Xiaocao capture acceptance from live receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.xiaocao_capture_acceptance import inspect_acceptance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", action="append", required=True)
    parser.add_argument("--required-count", type=int, default=1)
    parser.add_argument("--not-before")
    parser.add_argument(
        "--subscription-dir",
        type=Path,
        default=Path("output/live/kol_xiaocao_live/wechat_subscription"),
    )
    parser.add_argument("--sniffer-url", default="http://127.0.0.1:2022")
    args = parser.parse_args()
    result = inspect_acceptance(
        args.subscription_dir,
        args.identity,
        required_count=args.required_count,
        sniffer_url=args.sniffer_url,
        not_before=args.not_before,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
