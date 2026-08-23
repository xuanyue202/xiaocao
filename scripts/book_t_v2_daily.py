#!/usr/bin/env python3
"""Prepare and advance one Book T v2 shadow evidence day.

The command is deliberately paper/research-only.  ``--prepare`` creates the
dated morning input; ``--daily-mark`` appends only a close mark.  Exit and
matured outcome events require a later explicit evidence adapter and are never
invented by this command.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research.book_t_v2_producer import (  # noqa: E402
    BookTV2ProducerError,
    prepare_book_t_v2_shadow_day,
    record_book_t_v2_daily_mark,
)
from xiaocao.research.book_t_v2_lifecycle import (  # noqa: E402
    append_events,
    build_exit_event,
    build_matured_outcome_event,
    lifecycle_summary,
    read_events,
    validate_lifecycle,
)


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--daily-mark", action="store_true")
    mode.add_argument("--exit", action="store_true")
    mode.add_argument("--matured", action="store_true")
    parser.add_argument("--date", required=True, help="ISO trading date")
    parser.add_argument("--root", default=os.environ.get("XIAOCAO_ROOT", str(ROOT)))
    parser.add_argument("--run-mode", choices=["real", "rehearsal"], default="real")
    parser.add_argument("--capsule", help="isolated injected adapter capsule JSON")
    parser.add_argument("--marks", help="isolated close-mark JSON list")
    parser.add_argument(
        "--facts",
        help="JSON object {observed_at, rows} for a later exit or matured outcome",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        capsule = None
        if args.capsule:
            value = json.loads(_path(args.capsule).read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise BookTV2ProducerError("adapter capsule must be an object")
            capsule = value
        if args.prepare:
            result = prepare_book_t_v2_shadow_day(
                root,
                args.date,
                run_mode=args.run_mode,
                capsule=capsule,
            )
        elif args.daily_mark:
            marks = None
            if args.marks:
                value = json.loads(_path(args.marks).read_text(encoding="utf-8"))
                if not isinstance(value, list):
                    raise BookTV2ProducerError("--marks must contain a JSON list")
                marks = value
            result = record_book_t_v2_daily_mark(root, args.date, marks=marks)
        else:
            if not args.facts:
                raise BookTV2ProducerError("--facts is required for --exit/--matured")
            facts = json.loads(_path(args.facts).read_text(encoding="utf-8"))
            if not isinstance(facts, dict) or not isinstance(facts.get("rows"), list):
                raise BookTV2ProducerError("--facts must be an object with observed_at and rows")
            observed_at = str(facts.get("observed_at") or "").strip()
            if not observed_at:
                raise BookTV2ProducerError("--facts.observed_at is required")
            input_path = root / f"output/live/book_t_v2_shadow_input_{args.date}.json"
            frozen = json.loads(input_path.read_text(encoding="utf-8"))
            lifecycle = validate_lifecycle(frozen.get("evidence_lifecycle") or {})
            event_path = root / "output/research/book_t_v2_shadow/evidence_events.jsonl"
            previous = read_events(event_path)
            decision_id = lifecycle["decision_id"]
            stages = {
                str(row.get("stage"))
                for row in previous
                if str(row.get("decision_id")) == decision_id
            }
            if args.exit:
                if "daily_mark" not in stages:
                    raise BookTV2ProducerError("exit evidence requires a prior daily_mark")
                event = build_exit_event(
                    lifecycle,
                    observed_at=observed_at,
                    exits=facts["rows"],
                )
            else:
                if "exit" not in stages:
                    raise BookTV2ProducerError("matured outcome requires a prior exit")
                event = build_matured_outcome_event(
                    lifecycle,
                    observed_at=observed_at,
                    outcomes=facts["rows"],
                )
            events = append_events(event_path, [event])
            decision_events = [
                row for row in events
                if str(row.get("decision_id") or "") == str(decision_id)
            ]
            result = lifecycle_summary([lifecycle], events=decision_events)
            result["decision_id"] = decision_id
            result["event_path"] = str(event_path)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0
    except (BookTV2ProducerError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Book T v2 daily blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
