#!/usr/bin/env python3
"""Read source evidence, publish bounded KOL judgments, and request/audit reviews."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol import trading_decision as decisions


def main(argv: list[str] | None = None, *, client=None, clock=decisions.utc_now) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("publish", "status", "request", "audit", "feedback"))
    parser.add_argument("--root", type=Path, default=decisions.ROOT)
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--book", choices=("B", "T", "KOL-US"), default="B")
    parser.add_argument("--runtime", choices=("live", "paper"), default="paper")
    parser.add_argument("--phase")
    parser.add_argument("--decision-context", type=Path)
    parser.add_argument("--frozen-evidence", type=Path, action="append", default=[])
    parser.add_argument("--live-root", type=Path, help="Live execution state directory containing runs/ and decision JSONL")
    parser.add_argument("--paper-root", type=Path, help="Paper decision support directory containing consumption/*.json")
    args = parser.parse_args(argv)

    def path(value: Path) -> Path:
        return value if value.is_absolute() else args.root / value

    try:
        if args.command == "publish":
            if not all((args.decision, args.review, args.context)):
                raise decisions.TradingDecisionError("publish_files_required")
            result = decisions.publish_trading_decision(args.root,
                decisions.read_json(path(args.decision)), decisions.read_json(path(args.review)),
                decisions.read_json(path(args.context)), client=client, clock=clock)
        elif args.command == "request":
            if not all((args.context, args.decision_context, args.phase)):
                raise decisions.TradingDecisionError("request_files_and_phase_required")
            result = decisions.request_decision(args.root, book=args.book, runtime=args.runtime,
                phase=args.phase, context_path=args.context, decision_context_path=args.decision_context,
                frozen_evidence=args.frozen_evidence, clock=clock)
        elif args.command == "status":
            result = decisions.decision_status(args.root, book=args.book, runtime=args.runtime, clock=clock)
        else:
            result = decisions.audit_feedback(args.root,
                live_root=path(args.live_root) if args.live_root else None,
                paper_root=path(args.paper_root) if args.paper_root else None, clock=clock)
    except decisions.TradingDecisionError as exc:
        print(json.dumps({"status": "blocked", "code": str(exc)}, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "trading_decision_command_failed"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
