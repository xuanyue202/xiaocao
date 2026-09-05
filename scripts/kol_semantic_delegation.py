#!/usr/bin/env python3
"""Prepare, record or verify one local KOL semantic delegation; no dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.semantic_bundle import SemanticBundleError
from xiaocao.kol.semantic_delegation import prepare, record_dispatch, verify_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparing = commands.add_parser("prepare")
    preparing.add_argument("--analysis-request", required=True, type=Path)
    preparing.add_argument("--market-evidence", type=Path)
    preparing.add_argument("--household-context", type=Path)
    recording = commands.add_parser("record-dispatch")
    verifying = commands.add_parser("verify-result")
    for command in (recording, verifying):
        command.add_argument("--analysis-request", required=True, type=Path)
        command.add_argument("--packet", required=True, type=Path)
        command.add_argument("--agent-id", required=True, help="Actual UUID returned to parent")
    recording.add_argument("--invocation-args", required=True, type=Path,
                           help="Actual spawn args; continuation also accepts only the retained explicit model/effort/fork triple")
    recording.add_argument("--context-delivery", type=Path,
                           help="Actual send_input invocation_args {target,message,interrupt?} and result {submission_id} JSON")
    verifying.add_argument("--bundle", required=True, type=Path)
    verifying.add_argument("--semantic-draft", required=True, type=Path)
    verifying.add_argument("--receipt", type=Path)
    verifying.add_argument("--semantic-review", type=Path,
                           help="Separate parent-authored full-evidence review; never inferred from structural checks")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.analysis_request, market_evidence=args.market_evidence,
                             household_context=args.household_context)
        elif args.command == "record-dispatch":
            result = record_dispatch(args.analysis_request, packet_path=args.packet,
                                     agent_id=args.agent_id, invocation_args=args.invocation_args,
                                     context_delivery=args.context_delivery)
        else:
            result = verify_result(args.analysis_request, packet_path=args.packet,
                                   agent_id=args.agent_id, bundle_path=args.bundle,
                                   semantic_draft=args.semantic_draft, receipt_path=args.receipt,
                                   semantic_review=args.semantic_review)
    except (ValueError, OSError, SemanticBundleError) as exc:
        error = exc.to_dict() if isinstance(exc, SemanticBundleError) else str(exc)
        print(json.dumps({"status": "blocked", "error": error}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result.get("semantic_acceptance", {}).get("status") == "changes_required":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
