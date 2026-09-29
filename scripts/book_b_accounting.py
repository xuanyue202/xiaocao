"""Import, query and back up Book-B accounting; no APP access or order action."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import book_b_accounting as accounting
from xiaocao.live.book_b_capital import current_flow_state, verify_account, allocate_cash
from xiaocao.live.book_b_live_lifecycle import validate_broker_account_snapshot, _write_json_atomic
from xiaocao.live.trading_execution import account_writer_lock


def export_statement(root: Path, directory: Path, *, receipt: dict | None = None) -> dict:
    """Use an exact immutable observation; never silently obtain a new mark."""
    with account_writer_lock(root / "account_writer_locks", "primary"):
        state = accounting.sync_journal(root)
        if receipt is None:
            report = accounting.latest_observation(root)
        else:
            account, snapshot = receipt["account"], receipt["snapshot"]
            if account.get("accounting") is not None:
                report = accounting.verify_observation(root, account["accounting"])
            else:
                observed = datetime.fromisoformat(snapshot["observed_at"])
                validate_broker_account_snapshot(snapshot, trade_date=snapshot["trade_date"], now=observed)
                verify_account(root, account)
                if (account["ownership_head_sha256"] != accounting.replay_owned(root).head
                        or account.get("capital_flow_head_sha256") != current_flow_state(root)["capital_flow_head_sha256"]
                        or account["broker_snapshot_sha256"] != snapshot["snapshot_sha256"]
                        or account["broker_snapshot_observed_at"] != snapshot["observed_at"]):
                    raise ValueError("BOOK_B_ACCOUNTING_RECEIPT_NOT_CURRENT_SOURCE_HEAD")
                report = accounting.observe_account(root, cash=account["cash"],
                    market_value=account["current_open_exposure"],
                    liquidation_value=account["liquidation_value_after_fee"],
                    snapshot=snapshot, capital_state=current_flow_state(root))
        detail = accounting.details(root)
        current_mark = bool(report and report["journal_head_sha256"] == state["journal_head_sha256"])
        identifier = accounting.digest({"journal_head_sha256": state["journal_head_sha256"],
            "observation_sha256": report["receipt_sha256"] if report else None})
        directory.mkdir(parents=True, exist_ok=True)
        report_path = directory / (identifier + ".json")
        body = {"journal": state, "valuation": report,
            "valuation_status": "dated_observation" if current_mark else "stale_or_missing_mark"}
        if report_path.exists() and json.loads(report_path.read_text()) != body:
            raise ValueError("BOOK_B_ACCOUNTING_EXPORT_IMMUTABILITY_VIOLATION")
        _write_json_atomic(report_path, body)
        detail_path = directory / (state["journal_head_sha256"] + ".csv")
        with detail_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(detail[0]))
            writer.writeheader()
            writer.writerows(detail)
        return {**state, "status": report["status"] if current_mark else "stale_or_missing_mark",
            "observed_at": report["observed_at"] if report else None,
            "marked_nav": report["marked_nav"] if current_mark else None,
            "cumulative_pnl": report["cumulative_pnl"] if current_mark else None,
            "report_path": str(report_path), "details_path": str(detail_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("sync", "statement", "record-cash", "allocate", "backup"))
    parser.add_argument("--state-dir", type=Path, default=ROOT / "output/live/book_b_live_execution")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--approval-reference")
    args = parser.parse_args(argv)
    root = args.state_dir
    try:
        receipt = json.loads(args.receipt.read_text()) if args.receipt else None
        if args.action == "sync":
            result = accounting.sync_journal(root)
        elif args.action == "statement":
            result = export_statement(root, args.output_dir or root / "accounting_reports", receipt=receipt)
        elif args.action == "record-cash":
            if receipt is None:
                parser.error("record-cash requires --receipt with a proved native cash statement")
            result = accounting.record_cash_event(root, receipt)
        elif args.action == "allocate":
            if receipt is None or not args.approval_reference:
                parser.error("allocate requires --receipt and --approval-reference")
            snapshot = receipt.get("snapshot", receipt)
            now = datetime.now(timezone.utc)
            validate_broker_account_snapshot(snapshot, trade_date=snapshot["trade_date"], now=now)
            with account_writer_lock(root / "account_writer_locks", "primary"):
                book = accounting.replay_owned(root)
                prior = accounting.latest_observation(root)
                if prior is None or prior["broker_snapshot_sha256"] != snapshot["snapshot_sha256"]:
                    raise ValueError("BOOK_B_ACCOUNTING_ALLOCATION_CURRENT_OBSERVATION_REQUIRED")
                accounting.verify_observation(root, prior, current=True)
                available = snapshot["funds_summary"]["available_cash"]
                if accounting.number(available) != accounting.number(prior["cash"]):
                    raise ValueError("BOOK_B_ACCOUNTING_ALLOCATION_OPEN_BUY_RECONCILE_REQUIRED")
                liquidation = accounting.number(prior["liquidation_nav"]) - accounting.number(prior["cash"])
                _, funding = allocate_cash(root, base_cash=book.cash,
                    liquidation=liquidation,
                    ownership_head=book.head, snapshot=snapshot, allocation_reference=args.approval_reference)
                accounting.observe_account(root, cash=available, market_value=prior["owned_market_value"],
                    liquidation_value=liquidation, snapshot=snapshot, capital_state=funding)
                result = accounting.sync_journal(root)
        else:
            if args.output_dir is None:
                parser.error("backup requires --output-dir naming a new backup file")
            result = accounting.backup(root, args.output_dir)
    except (KeyError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
