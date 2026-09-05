#!/usr/bin/env python3
"""Read-only official launch resolver; emits a command but never opens WeChat."""

import argparse
import json

from xiaocao.kol.xiaoetong_launch import resolve_launch_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--expected-identity")
    args = parser.parse_args()
    try:
        result = resolve_launch_plan(args.source_url, expected_identity=args.expected_identity)
    except Exception as exc:
        # Provider exceptions can contain URLs: report only type, never credentials.
        print(json.dumps({"status": "visible_ui_fallback", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"status": "launch_plan_ready", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
