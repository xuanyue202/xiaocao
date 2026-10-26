"""Finalize EOD observations and optionally send the completed daily digest."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.eod_closeout import closeout
from xiaocao.live.status import build_digest
from xiaocao.research import eod_feedback
from status import push_digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--review", type=Path, help="reviewed structured daily handoff JSON")
    group.add_argument("--context", action="store_true", help="read prior daily items and weekly responses only")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--push-wecom", action="store_true", help="send after original-terminal validation")
    args = parser.parse_args()
    if args.context:
        if args.push_wecom:
            parser.error("--context cannot send")
        contents = {}
        for path in sorted(ROOT.glob(eod_feedback.DAILY_PATTERN)):
            data = path.read_bytes()
            contents[path.relative_to(ROOT).as_posix()] = data
            try:
                references = eod_feedback.referenced_paths(data)
            except (KeyError, ValueError, TypeError, AttributeError):
                continue  # Observer reports malformed records as evidence gaps.
            for reference in references:
                candidate = ROOT / reference
                if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
                    contents[reference] = candidate.read_bytes()
        ledger = ROOT / eod_feedback.WEEKLY_LEDGER
        if ledger.is_file():
            contents[eod_feedback.WEEKLY_LEDGER] = ledger.read_bytes()
        result = eod_feedback.observe_feedback(contents, as_of=dt.date.fromisoformat(args.date))
    else:
        result = closeout(ROOT, json.loads(args.review.read_bytes()), env=os.environ,
                          build_digest=build_digest, push_digest=push_digest if args.push_wecom else None)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
