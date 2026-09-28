#!/usr/bin/env python3
"""Deliver exact morning result evidence or retry safely pending notices."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.live.morning_notifications import MorningNotifications
from xiaocao.live.morning_observability import terminal_notice


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--retry-pending", action="store_true")
    args = parser.parse_args(argv)
    if not args.receipt and not args.retry_pending:
        parser.error("--receipt or --retry-pending is required")
    if args.receipt:
        payload = json.loads(args.receipt.read_text())
        if not payload.get("trade_date") or not payload.get("run_id"):
            raise ValueError("MORNING_RECEIPT_IDENTITY_REQUIRED")
        notices = MorningNotifications(payload["trade_date"])
        notices.publish("result", terminal_notice(payload, args.receipt))
    else:
        notices = MorningNotifications("retry")
    if args.retry_pending:
        notices.retry_pending()
    results = notices.close()
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    return 0 if all(r["status"] == "delivered" for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
