#!/usr/bin/env python3
"""Publish/read a reviewed source-only pack. No model, network or trading calls."""
import argparse
import json
from pathlib import Path

from xiaocao.kol.trading_preparation import preparation_status, publish_preparation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("publish", "status"))
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.command == "publish" and not (args.notes and args.review):
        parser.error("publish requires --notes and --review")
    try:
        context = json.loads(args.context.read_text())
        result = preparation_status(args.root, context) if args.command == "status" else publish_preparation(
            args.root, context, json.loads(args.notes.read_text()), json.loads(args.review.read_text()))
    except (ValueError, OSError, KeyError) as exc:
        result = {"status": "blocked", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
