#!/usr/bin/env python3
"""Read the checklist or acknowledge an original-owner input-loading worker."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from xiaocao.live.morning_checklist import MorningChecklist
from xiaocao.live.morning_kol_inputs import acknowledge_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--loaded", type=Path, help="Worker JSON: worker_id and loaded_viewpoint_ids")
    parser.add_argument("--item", choices=["market_auth", "transport", "delivery", "accounting_history"])
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--status", choices=["passed", "recovered", "degraded", "blocked"], default="passed")
    args = parser.parse_args()
    if args.loaded or args.item:
        checklist = MorningChecklist.owned(args.checklist, post_business=args.item in {"delivery", "accounting_history"})
        if args.loaded:
            if args.input is None or args.item:
                parser.error("--loaded requires --input and excludes --item")
            receipt = json.loads(args.loaded.read_text())
            acknowledge_inputs(checklist, args.input.resolve(), worker_id=receipt["worker_id"],
                               loaded_ids=receipt["loaded_viewpoint_ids"],
                               loaded_receipt_path=args.loaded.resolve())
        else:
            if args.evidence is None or not args.evidence.is_file():
                parser.error("--item requires a saved evidence file")
            # This is an operator attestation, not a validator or execution gate.
            checklist.record(args.item, args.status, evidence={"path": str(args.evidence.resolve()),
                             "attested_by": "original_owner"})
    else:
        payload = json.loads(args.checklist.read_text())
        checklist = MorningChecklist(args.checklist, payload["binding"])
    print(json.dumps(checklist.read(now=datetime.now(timezone.utc)), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
