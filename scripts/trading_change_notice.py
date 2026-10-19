#!/usr/bin/env python3
"""Durably queue and retry APP-simulation trading change notices to WeCom."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from xiaocao.live.incident_delivery import deliver_pending, enqueue_notice, pending_notices

DEFAULT_OUTBOX = Path("output/live/trading_change_notices.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    parser.add_argument("--commit", help="Committed revision containing the APP-simulation change")
    parser.add_argument("--kind", choices=("strategy", "capital", "parameter", "safety"))
    parser.add_argument("--title")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--retry-pending", action="store_true")
    args = parser.parse_args(argv)
    if args.commit or args.kind or args.title or args.body_file:
        if not (args.commit and args.kind and args.title and args.body_file):
            parser.error("--commit, --kind, --title and --body-file are required together")
        body = args.body_file.read_text(encoding="utf-8").strip()
        if not body:
            parser.error("body file is empty")
        identifier = hashlib.sha256(f"{args.kind}\0{args.commit}\0{args.title}".encode()).hexdigest()
        enqueue_notice(args.outbox,
            identifier=identifier, title=args.title,
            body=f"类别={args.kind} 提交={args.commit}\n{body}",
        )
    elif not args.retry_pending:
        parser.error("provide one notice or --retry-pending")
    results = deliver_pending(args.outbox)
    print(json.dumps({"notices": results, "pending_count": len(pending_notices(args.outbox))},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
