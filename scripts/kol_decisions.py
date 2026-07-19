#!/usr/bin/env python3
"""Process evidence-linked KOL judgments into household and paper outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.decisions import DecisionPipeline, load_bundle, render_household_message
from xiaocao.kol.household import LiangHuiMcpClient
from xiaocao.live.notify import notify


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", help="source-neutral decision bundle JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("output/live/kol_intelligence"))
    parser.add_argument("--preflight", action="store_true", help="validate without side effects")
    parser.add_argument(
        "--send-wechat",
        action="store_true",
        help="deliver pending household advisories through Xiaocao's configured WeCom relay",
    )
    parser.add_argument("--mark-delivered", metavar="IDEMPOTENCY_KEY")
    parser.add_argument("--receipt", help="external WeChat receipt/reference")
    args = parser.parse_args()

    household_loader = None
    if args.bundle is not None:
        bundle = load_bundle(args.bundle)
        if (bundle.get("household_context_provider") or {}).get("type") == "lianghui_mcp":
            household_loader = LiangHuiMcpClient.from_config().load_context
    pipeline = DecisionPipeline(args.output_dir, household_context_loader=household_loader)
    if args.mark_delivered:
        if not args.receipt:
            parser.error("--mark-delivered requires --receipt")
        print(
            json.dumps(
                pipeline.record_delivery(args.mark_delivered, args.receipt), ensure_ascii=False
            )
        )
        return 0
    if args.bundle is None:
        parser.error("bundle is required unless --mark-delivered is used")
    if args.preflight:
        result = pipeline.preflight(bundle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"ready", "waiting_for_household_context"} else 2
    result = pipeline.process(bundle)
    if result.get("status") == "completed" and args.send_wechat:
        result["wechat_delivery"] = pipeline.deliver_wechat(
            result,
            sender=lambda title, body: notify(title, body, macos=False),
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "latest_result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if result.get("status") == "completed":
        message_path = args.output_dir / "latest_household_message.md"
        message_path.write_text(render_household_message(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "result": str(result_path)}, ensure_ascii=False))
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
