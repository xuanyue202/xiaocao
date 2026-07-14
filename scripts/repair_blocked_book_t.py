#!/usr/bin/env python3
"""Repair one Book-T sell that contradicted a recorded liquidity block.

The repair reverses both the impossible sell and the later automatic re-buy it
caused.  Every amount is derived from the frozen ledger rows; nothing is
hand-entered.  The command is dry-run by default and appends the complete
before/after record when ``--apply`` is supplied.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.sell_blocks import load_blocked_sell_keys  # noqa: E402
from xiaocao.live import accounts  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _one(rows: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly one {label}, found {len(rows)}")
    return rows[0]


def repair_blocked_roundtrip(
    *,
    positions_path: Path,
    trades_path: Path,
    account_path: Path,
    alerts_path: Path,
    audit_path: Path,
    code: str,
    entry_date: str,
    blocked_date: str,
    replacement_entry_date: str,
    apply: bool,
) -> dict[str, Any]:
    blocked = load_blocked_sell_keys(alerts_path, book="T")
    block_reason = blocked.get(("T", blocked_date, code, entry_date))
    if not block_reason:
        raise RuntimeError("no exact Book-T SELL_BLOCKED fact; refusing ledger repair")

    positions = _read_jsonl(positions_path)
    trades = _read_jsonl(trades_path)
    account = json.loads(account_path.read_text(encoding="utf-8"))
    original = _one([
        p for p in positions
        if p.get("book") == "T" and p.get("code") == code
        and p.get("entry_date") == entry_date and p.get("exit_date") == blocked_date
        and p.get("status") == "closed"
    ], label="blocked closed position")
    replacement = _one([
        p for p in positions
        if p.get("book") == "T" and p.get("code") == code
        and p.get("entry_date") == replacement_entry_date and p.get("status", "open") == "open"
    ], label="causal replacement position")
    invalid_sell = _one([
        t for t in trades
        if t.get("book") == "T" and t.get("side") == "SELL" and t.get("code") == code
        and t.get("date") == blocked_date
    ], label="blocked SELL trade")
    invalid_buy = _one([
        t for t in trades
        if t.get("book") == "T" and t.get("side") == "BUY" and t.get("code") == code
        and t.get("date") == replacement_entry_date
    ], label="causal replacement BUY trade")
    if int(original.get("shares") or 0) != int(replacement.get("shares") or 0):
        raise RuntimeError("replacement share count differs; refusing ambiguous repair")
    if int(invalid_sell.get("shares") or 0) != int(invalid_buy.get("shares") or 0):
        raise RuntimeError("SELL/BUY share count differs; refusing ambiguous repair")

    repaired_positions = [copy.deepcopy(p) for p in positions if p is not replacement]
    restored = next(p for p in repaired_positions if p is not None and p == original)
    restored["status"] = "open"
    for key in (
        "exit_date", "exit_price", "exit_fee", "exit_cash_in", "realized_pnl", "exit_reason",
        "trend_exit_peak", "trend_exit_dd_pct", "trend_hold_days",
    ):
        restored.pop(key, None)
    repair_id = f"book_t_blocked_{blocked_date}_{code}_{entry_date}"
    restored["trend_exit_blocked_date"] = blocked_date
    restored["trend_exit_blocked_reason"] = block_reason
    restored["ledger_repair_id"] = repair_id

    repaired_trades = [
        t for t in trades if t is not invalid_sell and t is not invalid_buy
    ]
    repaired_account = copy.deepcopy(account)
    repaired_account["cash"] = round(
        float(account.get("cash") or 0.0)
        - float(original.get("exit_cash_in") or 0.0)
        + float(replacement.get("entry_cash_out") or 0.0),
        2,
    )
    repaired_account["realized_pnl"] = round(
        float(account.get("realized_pnl") or 0.0) - float(original.get("realized_pnl") or 0.0), 2
    )
    repaired_account["total_fees"] = round(
        float(account.get("total_fees") or 0.0)
        - float(original.get("exit_fee") or 0.0)
        - float(replacement.get("entry_fee") or 0.0),
        2,
    )
    buy_dates = [str(t.get("date")) for t in repaired_trades if t.get("book") == "T" and t.get("side") == "BUY"]
    sell_dates = [str(t.get("date")) for t in repaired_trades if t.get("book") == "T" and t.get("side") == "SELL"]
    repaired_account["last_buy_date"] = max(buy_dates) if buy_dates else None
    repaired_account["last_sell_date"] = max(sell_dates) if sell_dates else None
    repaired_account["updated_at"] = datetime.now().isoformat(timespec="seconds")
    repaired_account["ledger_repair_id"] = repair_id

    audit = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "repair_id": repair_id,
        "reason": "reverse SELL recorded after exact SELL_BLOCKED and its causal next-entry BUY",
        "block_reason": block_reason,
        "applied": apply,
        "position_before": original,
        "position_after": restored,
        "removed_replacement_position": replacement,
        "removed_trades": [invalid_sell, invalid_buy],
        "account_before": account,
        "account_after": repaired_account,
    }
    if apply:
        accounts.commit_file_transaction(
            live_dir=positions_path.parent,
            payloads=[
                ("positions", positions_path, accounts.encode_jsonl(repaired_positions)),
                ("trades", trades_path, accounts.encode_jsonl(repaired_trades)),
                ("account", account_path, accounts.encode_json(repaired_account)),
                ("repair_audit", audit_path, accounts.append_jsonl_bytes(audit_path, [audit])),
            ],
        )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", required=True)
    parser.add_argument("--entry-date", required=True)
    parser.add_argument("--blocked-date", required=True)
    parser.add_argument("--replacement-entry-date", required=True)
    parser.add_argument("--live-dir", default="output/live")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    live = Path(args.live_dir)
    with accounts.ledger_lock(accounts.ledger_lock_path(live)):
        accounts.recover_ledger_transaction(live)
        result = repair_blocked_roundtrip(
            positions_path=live / "positions.jsonl",
            trades_path=live / "paper_trades.jsonl",
            account_path=live / "paper_account_T.json",
            alerts_path=live / "alerts.jsonl",
            audit_path=live / "ledger_repairs.jsonl",
            code=args.code,
            entry_date=args.entry_date,
            blocked_date=args.blocked_date,
            replacement_entry_date=args.replacement_entry_date,
            apply=args.apply,
        )
    print(json.dumps({
        "repair_id": result["repair_id"],
        "applied": result["applied"],
        "account_before": result["account_before"],
        "account_after": result["account_after"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
