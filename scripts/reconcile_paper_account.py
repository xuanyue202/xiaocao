#!/usr/bin/env python3
"""Rebuild the Book B paper account from positions.jsonl.

Use this after a deterministic re-derivation of fills/position PnL. The account
file is a state cache; positions are the position-level source of truth once
their entry_cash_out / realized_pnl fields have been corrected.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import accounts  # noqa: E402

LIVE = ROOT / "output" / "live"
POSITIONS = LIVE / "positions.jsonl"
ACCOUNT = LIVE / "paper_account.json"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def rebuild_account(
    positions: list[dict[str, Any]],
    account: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    initial = _f(account.get("initial_capital"), 100000.0)
    fee_rate = _f(account.get("fee_rate"), 0.0001)
    book_b = [p for p in positions if p.get("book", "B") == "B"]
    closed = [p for p in book_b if p.get("status") == "closed"]
    open_pos = [p for p in book_b if p.get("status", "open") == "open"]

    realized = round(sum(_f(p.get("realized_pnl")) for p in closed), 2)
    open_cash_out = round(sum(_f(p.get("entry_cash_out")) for p in open_pos), 2)
    total_fees = round(
        sum(_f(p.get("entry_fee")) + _f(p.get("exit_fee")) for p in closed)
        + sum(_f(p.get("entry_fee")) for p in open_pos),
        2,
    )
    cash = round(initial + realized - open_cash_out, 2)

    rebuilt = dict(account)
    rebuilt.update({
        "cash": cash,
        "fee_rate": fee_rate,
        "initial_capital": initial,
        "realized_pnl": realized,
        "total_fees": total_fees,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "reconcile_source": "positions.jsonl",
        "reconcile_note": (
            "rebuilt from Book B positions: cash = initial_capital + "
            "closed_realized_pnl - open_entry_cash_out"
        ),
    })
    summary = {
        "closed_book_b": len(closed),
        "open_book_b": len(open_pos),
        "initial_capital": initial,
        "closed_realized_pnl": realized,
        "open_entry_cash_out": open_cash_out,
        "cash": cash,
        "total_fees": total_fees,
        "old_cash": account.get("cash"),
        "old_realized_pnl": account.get("realized_pnl"),
        "cash_delta": round(cash - _f(account.get("cash")), 2),
        "realized_delta": round(realized - _f(account.get("realized_pnl")), 2),
    }
    return rebuilt, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--positions", default=str(POSITIONS))
    ap.add_argument("--account", default=str(ACCOUNT))
    ap.add_argument("--write", action="store_true", help="write rebuilt account JSON")
    args = ap.parse_args()

    positions_path = Path(args.positions)
    account_path = Path(args.account)
    live_dir = account_path.parent
    with accounts.ledger_lock(accounts.ledger_lock_path(live_dir)):
        accounts.recover_ledger_transaction(live_dir)
        positions = _load_jsonl(positions_path)
        account = _load_json(account_path)
        if not positions:
            print(f"no positions found: {positions_path}", file=sys.stderr)
            return 2
        rebuilt, summary = rebuild_account(positions, account)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        if args.write:
            accounts.commit_file_transaction(
                live_dir=live_dir,
                payloads=[("account", account_path, accounts.encode_json(rebuilt))],
            )
            print(f"wrote rebuilt account -> {account_path}")
        else:
            print("dry-run only; pass --write to update the account file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
