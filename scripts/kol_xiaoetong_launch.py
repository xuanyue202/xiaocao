#!/usr/bin/env python3
"""Read-only official launch resolver; emits a command but never opens WeChat."""

import argparse
import json

from xiaocao.kol.xiaoetong_launch import UnsupportedLaunchApplication, resolve_launch_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--expected-identity")
    parser.add_argument("--subscription-id", help="Emit an exact runner response without retyping IDs")
    args = parser.parse_args()
    try:
        result = resolve_launch_plan(args.source_url, expected_identity=args.expected_identity)
    except UnsupportedLaunchApplication:
        result = {"status": "unsupported_application", "error_type": "UnsupportedLaunchApplication", "launch_allowed": False}
        if args.subscription_id:
            result["browser_response"] = {
                "action": "resolve_xiaoetong_page", "subscription_id": args.subscription_id,
                "page_state": "unsupported_application", "launch_allowed": False,
            }
        print(json.dumps(result))
        return 1
    except Exception as exc:
        # Provider exceptions can contain URLs: report only type, never credentials.
        print(json.dumps({"status": "visible_ui_fallback", "error_type": type(exc).__name__}))
        return 1
    if args.subscription_id:
        result["browser_response"] = {
            "action": "resolve_xiaoetong_page", "subscription_id": args.subscription_id,
            "page_url": result["page_url"], "source_identity": result["source_identity"],
            "live_id": result["live_id"], "page_state": "unknown",
        }
    print(json.dumps({"status": "launch_plan_ready", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
