#!/usr/bin/env python3
"""Derive a dated EOD review from its original archive; no APP or settlement action."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_accounting import verify_observation
from xiaocao.live.book_b_capital import verify_account
from xiaocao.live.eod_reconciliation import assess_eod
from xiaocao.live.trading_execution import account_writer_lock


def review_original_receipt(path: Path, state_dir: Path, *, root: Path = ROOT) -> dict:
    path, state_dir = path.resolve(), state_dir.resolve()
    raw = path.read_bytes()
    receipt = json.loads(raw)
    identity = receipt.get("automation_identity") or {}
    slot = root / "output/live/eod_task_slots/xiaocao-daily-eod" / f"{receipt['trade_date']}-app.json"
    if (receipt.get("phase") != "eod" or receipt.get("route") != "native-app"
            or receipt.get("execute_sells_requested") is not False
            or path.parent != state_dir / "runs/intraday/archive"
            or path.name != f"{receipt['run_id']}.json"
            or Path(receipt["run_receipt_path"]).resolve() != path
            or identity.get("automation_id") != "xiaocao-daily-eod"
            or identity.get("branch") != "app" or identity.get("trade_date") != receipt["trade_date"]
            or Path(str(identity.get("claim_path") or "")).resolve() != slot.resolve()
            or os.environ.get("CODEX_AUTOMATION_ID") != identity["automation_id"]
            or not os.environ.get("CODEX_THREAD_ID")
            or os.environ["CODEX_THREAD_ID"] != identity.get("thread_id")
            or json.loads(slot.read_text()) != identity):
        raise ValueError("EOD_REVIEW_ORIGINAL_OWNER_REQUIRED")
    account, snapshot = receipt["account"], receipt["broker_snapshot"]
    if (account["broker_snapshot_sha256"] != snapshot["snapshot_sha256"]
            or account["trade_date"] != receipt["trade_date"]):
        raise ValueError("EOD_REVIEW_ACCOUNT_SNAPSHOT_MISMATCH")
    with account_writer_lock(state_dir / "account_writer_locks", "primary"):
        verify_account(state_dir, account)
        verify_observation(state_dir, account["accounting"], current=True)
        review = assess_eod(state_dir, account, snapshot,
            now=datetime.fromisoformat(snapshot["observed_at"]), persist=True)
    return {"source_receipt_path": str(path),
        "source_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_status": "dated_original_observation", "eod_review": review,
        "app_queries": 0, "orders_created": 0, "settlement_written": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, default=ROOT / "output/live/book_b_live_execution")
    args = parser.parse_args()
    print(json.dumps(review_original_receipt(args.receipt, args.state_dir), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
