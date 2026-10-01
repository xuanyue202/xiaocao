#!/usr/bin/env python3
"""Rebuild the Book B paper account from positions.jsonl.

Use this after a deterministic re-derivation of fills/position PnL. The account
file is a state cache; positions are the position-level source of truth once
their entry_cash_out / realized_pnl fields have been corrected.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import sys
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live import accounts  # noqa: E402
from xiaocao.live.paper_research import day, fingerprint, money, number, read_json, read_jsonl  # noqa: E402

LIVE = ROOT / "output" / "live"
POSITIONS = LIVE / "positions.jsonl"
ACCOUNT = LIVE / "paper_account.json"


def rebuild_account(
    positions: list[dict[str, Any]],
    account: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if account.get("book", "B") != "B":
        raise ValueError("account does not belong to Book B")
    initial = money(account.get("initial_capital"), "initial_capital", nonnegative=True)
    if initial <= 0:
        raise ValueError("initial_capital must be positive")
    old_cash = money(account.get("cash"), "cash", nonnegative=True)
    old_realized = money(account.get("realized_pnl"), "realized_pnl")
    if "fee_rate" in account:
        fee_rate = number(account["fee_rate"], "fee_rate")
        if not 0 <= fee_rate < 1:
            raise ValueError("invalid fee_rate")
    if "total_fees" in account:
        money(account["total_fees"], "total_fees", nonnegative=True)
    # This reconstruction is for the fixed-capital paper ledger, not APP flows.
    for key in ("net_capital_flows", "net_external_flows", "capital_flows"):
        if key in account and account[key] not in (0, [], None):
            raise ValueError("capital flows require separate verified reconstruction")
    realized = open_cash_out = total_fees = money(0, "zero")
    closed_count = open_count = 0
    seen = set()
    for position in positions:
        if not isinstance(position, dict):
            raise ValueError("position must be an object")
        book = accounts.require_explicit_book(position, kind="position")
        if book != "B":
            continue
        code = position.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("position requires code")
        entry_date = day(position.get("entry_date"))
        identity = (book, code, entry_date)
        if identity in seen:
            raise ValueError(f"duplicate lot: {identity}")
        seen.add(identity)
        # Canonical paper writers retain original filled shares through a
        # whole-lot exit. APP order remainders/partial-cost projections have
        # different semantics and cannot prove this paper reconstruction.
        if any(key in position for key in ("original_shares", "remaining_shares", "sold_shares",
                                            "cumulative_sold_shares", "partial_exits", "exit_fills", "sell_fills")):
            raise ValueError("partial-lot accounting requires its dedicated cumulative fill evidence")
        shares = number(position.get("shares"), "shares")
        if shares <= 0 or shares != shares.to_integral_value():
            raise ValueError("shares must be a positive integer")
        cost = money(position.get("entry_cash_out"), "entry_cash_out", nonnegative=True)
        fee = money(position.get("entry_fee"), "entry_fee", nonnegative=True)
        if cost <= 0 or fee >= cost:
            raise ValueError("invalid entry cost/fee")
        gross = money(position.get("gross_notional"), "gross_notional", nonnegative=True)
        if gross <= 0 or gross + fee != cost:
            raise ValueError("entry cash does not match gross plus fee")
        entry_price = number(position.get("entry_price"), "entry_price")
        if entry_price <= 0:
            raise ValueError("invalid entry_price")
        # paper_record saves entry_price to 3 dp after calculating gross from
        # the raw modeled price; cash remains exact cents. Respect only that
        # published rounding interval, never an arbitrary relative tolerance.
        if abs(gross - entry_price * shares) > shares * Decimal("0.0005") + Decimal("0.005"):
            raise ValueError("entry notional contradicts price and filled shares")
        for price_key in ("entry_price", "exit_price"):
            if price_key in position and position[price_key] is not None:
                if number(position[price_key], price_key) <= 0:
                    raise ValueError(f"invalid {price_key}")
        total_fees += fee
        status = position.get("status")
        if status == "open":
            open_count += 1
            open_cash_out += cost
            if "realized_pnl" in position and money(position["realized_pnl"], "open realized_pnl") != 0:
                raise ValueError("open lot has unproved partial realized accounting")
            if "exit_fee" in position and money(position["exit_fee"], "open exit_fee") != 0:
                raise ValueError("open lot has unproved partial exit fees")
            if position.get("exit_date") or position.get("exit_cash_in") is not None or position.get("exit_price") is not None:
                raise ValueError("open lot contains exit accounting")
        elif status == "closed":
            exit_date = day(position.get("exit_date"))
            if exit_date < entry_date:
                raise ValueError("exit precedes entry")
            pnl = money(position.get("realized_pnl"), "position realized_pnl")
            cash_in = money(position.get("exit_cash_in"), "exit_cash_in", nonnegative=True)
            exit_fee = money(position.get("exit_fee"), "exit_fee", nonnegative=True)
            exit_price = number(position.get("exit_price"), "exit_price")
            if exit_price <= 0:
                raise ValueError("invalid exit_price")
            exit_gross = cash_in + exit_fee
            if "exit_gross_notional" in position and money(position["exit_gross_notional"], "exit gross") != exit_gross:
                raise ValueError("exit gross does not match exit cash plus fee")
            # paper_exit saves the modeled exit price to 4 dp after using the
            # raw price for gross. Closed shares still mean all original shares.
            if abs(exit_gross - exit_price * shares) > shares * Decimal("0.00005") + Decimal("0.005"):
                raise ValueError("exit cash/fee contradict price and original filled shares")
            if cash_in - cost != pnl:
                raise ValueError("closed PnL does not match exit cash minus entry cost")
            realized += pnl
            total_fees += exit_fee
            closed_count += 1
        else:
            raise ValueError(f"unsupported position status: {status!r}")
    if not seen:
        raise ValueError("no verified Book B positions")
    cash = initial + realized - open_cash_out
    if cash < 0:
        raise ValueError("reconstruction produces negative cash")
    rebuilt = dict(account)
    rebuilt.update(cash=float(cash), initial_capital=float(initial),
                   realized_pnl=float(realized), total_fees=float(total_fees))
    summary = {
        "closed_book_b": closed_count, "open_book_b": open_count,
        "initial_capital": float(initial), "closed_realized_pnl": float(realized),
        "open_entry_cash_out": float(open_cash_out), "cash": float(cash),
        "total_fees": float(total_fees), "old_cash": float(old_cash),
        "old_realized_pnl": float(old_realized), "cash_delta": float(cash - old_cash),
        "realized_delta": float(realized - old_realized),
        "price_evidence_basis": "paper producer rounding intervals: entry 3dp, exit 4dp; exact cash cents",
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
    try:
        if args.write and positions_path.resolve().parent != account_path.resolve().parent:
            raise ValueError("write requires positions and account under the same shared ledger lock")
        if args.write and account_path.name in ("paper_account_A.json", "paper_account_T.json"):
            raise ValueError("Book B reconciliation cannot write another book account")
        # A dry-run must not create a lock file or finish someone else's write.
        # --write reloads and verifies all inputs while holding the shared lock.
        context = accounts.ledger_lock(accounts.ledger_lock_path(live_dir)) if args.write else nullcontext()
        with context:
            pending = live_dir / ".ledger_txn" / "pending.json"
            if pending.exists():
                raise ValueError(f"unresolved ledger transaction: {pending}; recover separately")
            positions_bytes = positions_path.read_bytes()
            account_bytes = account_path.read_bytes()
            positions = read_jsonl(positions_path)
            account = read_json(account_path)
            rebuilt, summary = rebuild_account(positions, account)
            if pending.exists() or positions_path.read_bytes() != positions_bytes or account_path.read_bytes() != account_bytes:
                raise ValueError("source changed during verification")
            evidence = {
                "positions_path": str(positions_path.resolve()),
                "positions_sha256": hashlib.sha256(positions_bytes).hexdigest(),
                "account_path": str(account_path.resolve()),
                "account_before_sha256": hashlib.sha256(account_bytes).hexdigest(),
                "price_evidence_basis": summary["price_evidence_basis"],
                "verified_accounting_sha256": fingerprint({k: rebuilt[k] for k in
                    ("initial_capital", "cash", "realized_pnl", "total_fees")}),
            }
            summary["source_evidence"] = evidence
            changed = any(account.get(k) != rebuilt[k] for k in
                          ("initial_capital", "cash", "realized_pnl", "total_fees"))
            summary["changed"] = changed
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
            if args.write and changed:
                rebuilt.update({
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "reconcile_source": str(positions_path.resolve()),
                    "reconcile_evidence": evidence,
                    "reconcile_note": "verified fixed-capital Book B lot accounting",
                })
                accounts.commit_file_transaction(
                    live_dir=live_dir,
                    payloads=[("account", account_path, accounts.encode_json(rebuilt))],
                )
                print(f"wrote rebuilt account -> {account_path}")
            elif args.write:
                print("account already reconciled; no write")
            else:
                print("dry-run only; pass --write to update the account file")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"reconciliation refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
