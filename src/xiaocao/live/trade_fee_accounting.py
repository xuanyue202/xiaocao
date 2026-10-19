"""Actual native order fees and their append-only financial revaluation.

Original ownership and estimated journal postings remain immutable. This module
computes the replacement financial amounts; its caller posts only differences.
It does not query the APP, infer fees from cash, or establish order terminality.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .book_b_capital import digest, number

FEE_COMPONENTS = ("commission", "stamp_duty", "transfer_fee", "other_fee")
FEE_EVIDENCE = "TRADE_FEE_EVIDENCE"
FEE_ADJUSTMENT = "TRADE_FEE_ADJUSTMENT"


def order_key(source: dict) -> tuple[str, str]:
    return source["trade_date"][:10], str(source["broker_order_id"])


def _cents(value) -> int:
    amount = number(value)
    if amount != amount.quantize(Decimal(".01")):
        raise ValueError("BOOK_B_ACTUAL_FEE_CENTS_REQUIRED")
    return int(amount * 100)


def evidence_by_order(entries: list[dict]) -> dict:
    """Validate explicit revision chains; order IDs may recur on other dates."""
    result = {}
    for entry in entries:
        if entry["kind"] != FEE_EVIDENCE:
            continue
        key = order_key(entry["event"])
        previous = result.get(key)
        if entry.get("replaces_fee_entry_sha256") != (previous["entry_hash"] if previous else None):
            raise ValueError("BOOK_B_ACTUAL_FEE_REVISION_UNPROVEN")
        result[key] = entry
    return result


def validate_fee_proof(proof: dict, entries: list[dict], *, binding: str,
                       snapshot: dict) -> dict:
    """An itemized native statement, never an estimated rate or balance delta."""
    statement = proof["statement"]
    if (statement.get("schema_version") != "foundersc-native-trade-fees.v1"
            or statement.get("source") != "foundersc_native_app"
            or statement.get("account_binding") != "proven"
            or statement.get("fund_account_binding_sha256") != binding
            or snapshot["fund_account_binding_sha256"] != binding
            or statement.get("observed_at") != snapshot["observed_at"]
            or statement.get("receipt_sha256") != digest({k: v for k, v in statement.items()
                                                         if k != "receipt_sha256"})):
        raise ValueError("BOOK_B_ACTUAL_FEE_STATEMENT_UNPROVEN")
    rows = statement.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("BOOK_B_ACTUAL_FEE_STATEMENT_UNPROVEN")
    matched = [r for r in rows if r.get("event_id") == proof.get("event_id")]
    if len(matched) != 1:
        raise ValueError("BOOK_B_ACTUAL_FEE_EVENT_NOT_UNIQUE")
    row = matched[0]
    if not isinstance(row.get("event_id"), str) or not row["event_id"].strip():
        raise ValueError("BOOK_B_ACTUAL_FEE_EVENT_INVALID")
    owned = [e for e in entries if e["kind"] in {"BUY", "SELL"}
             and order_key(e["source"]) == order_key(row)]
    if (not owned or row.get("fee_basis") != "broker_final_itemized"
            or row.get("coverage") != "complete_order"
            or any(e["code"] != row.get("code") or e["kind"] != row.get("side") for e in owned)
            or type(row.get("shares")) is not int
            or row["shares"] != sum(e["shares"] for e in owned)
            or row.get("ownership_event_hashes") != [e["source_hash"] for e in owned]
            or _cents(row.get("gross_notional")) != sum(_cents(e["source"]["fill_notional"]) for e in owned)
            or row["trade_date"] != row["trade_date"][:10]
            or row["trade_date"] > snapshot["trade_date"][:10]
            or any(datetime.fromisoformat(e["observed_at"]) > datetime.fromisoformat(statement["observed_at"])
                   for e in owned)):
        raise ValueError("BOOK_B_ACTUAL_FEE_OWNED_COVERAGE_UNPROVEN")
    components = row.get("fees")
    if not isinstance(components, dict) or set(components) != set(FEE_COMPONENTS):
        raise ValueError("BOOK_B_ACTUAL_FEE_COMPONENTS_REQUIRED")
    fee = sum(_cents(components[k]) for k in FEE_COMPONENTS)
    if any(number(v) < 0 for v in components.values()):
        raise ValueError("BOOK_B_ACTUAL_FEE_NEGATIVE")
    gross = _cents(row["gross_notional"])
    cash = (-gross if row["side"] == "BUY" else gross) - fee
    if cash != _cents(row.get("net_cash_change")):
        raise ValueError("BOOK_B_ACTUAL_FEE_CASH_EQUATION_INVALID")
    return row


def projection(entries: list[dict]) -> dict:
    """Revalue all fills using actual fees where proven, preserving cent costs."""
    fees = evidence_by_order(entries)
    fills = [e for e in entries if e["kind"] in {"BUY", "SELL"}]
    grouped = {}
    for entry in fills:
        grouped.setdefault(order_key(entry["source"]), []).append(entry)
    fee_by_fill, pending = {}, []
    for key, group in grouped.items():
        proof = fees.get(key)
        if proof is None:
            pending.append({"trade_date": key[0], "broker_order_id": key[1],
                            "code": group[0]["code"], "side": group[0]["kind"]})
            continue
        event = proof["event"]
        if event["ownership_event_hashes"] != [e["source_hash"] for e in group]:
            raise ValueError("BOOK_B_ACTUAL_FEE_COVERAGE_CHANGED")
        total = sum(_cents(v) for v in event["fees"].values())
        gross = sum(_cents(e["source"]["fill_notional"]) for e in group)
        allocated = cumulative_gross = 0
        for index, entry in enumerate(group):
            cumulative_gross += _cents(entry["source"]["fill_notional"])
            amount = (total - allocated if index == len(group) - 1 else
                int((Decimal(total) * cumulative_gross / gross).quantize(Decimal(1))) - allocated)
            allocated += amount
            fee_by_fill[entry["source_hash"]] = amount
    lots, financial, differences = {}, {}, {"cash": 0, "pnl": 0}
    for entry in fills:
        source_hash, side, lot_id = entry["source_hash"], entry["kind"], entry["lot_id"]
        known = source_hash in fee_by_fill
        fee = fee_by_fill.get(source_hash, entry["fee_cents"])
        gross = _cents(entry["source"]["fill_notional"])
        lot = lots.setdefault(lot_id, {"shares": 0, "cost": 0, "gross_cost": 0, "fees_complete": True})
        qty = entry["shares"]
        if side == "BUY":
            cash, cost, gross_cost = -gross - fee, gross + fee, gross
            lot["shares"] += qty
            lot["fees_complete"] &= known
        else:
            cost = -(lot["cost"] if qty == lot["shares"] else
                     int((Decimal(lot["cost"]) * qty / lot["shares"]).quantize(Decimal(1))))
            gross_cost = -(lot["gross_cost"] if qty == lot["shares"] else
                     int((Decimal(lot["gross_cost"]) * qty / lot["shares"]).quantize(Decimal(1))))
            cash = gross - fee
            lot["shares"] -= qty
        lot["cost"] += cost
        lot["gross_cost"] += gross_cost
        lines = {"cash": cash, "inventory:" + lot_id: cost, "pnl": -cash - cost}
        for account, value in lines.items():
            differences[account] = differences.get(account, 0) + value - entry["lines"].get(account, 0)
        financial[source_hash] = {"fee_cents": fee if known else None,
            "cost_cents": cost, "realized_pnl_cents": cash + cost,
            "gross_pnl_cents": gross + gross_cost if side == "SELL" else 0,
            "gross_sold_cost_cents": -gross_cost if side == "SELL" else 0,
            "final": known and lot["fees_complete"]}
    return {"fills": financial, "lots": lots, "differences": differences,
            "pending_orders": pending, "complete": not pending}


def sync_adjustment(db, entries: list[dict]) -> None:
    from .book_b_accounting import _post
    state = projection(entries)
    if not evidence_by_order(entries):
        return  # Never restate untouched legacy estimated entries.
    previous = {}
    for entry in entries:
        if entry["kind"] == FEE_ADJUSTMENT:
            for key, amount in entry["lines"].items():
                previous[key] = previous.get(key, 0) + amount
    lines = {k: v - previous.get(k, 0) for k, v in state["differences"].items()}
    if not any(lines.values()):
        return
    sources = [e["entry_hash"] for e in entries if e["kind"] in {"BUY", "SELL", FEE_EVIDENCE}]
    observed_at = max((e["observed_at"] for e in entries
        if e["kind"] in {"BUY", "SELL", FEE_EVIDENCE}), key=datetime.fromisoformat)
    head = digest(sources)
    _post(db, {"source_id": "trade-fee-adjustment:" + head, "kind": FEE_ADJUSTMENT,
        "observed_at": observed_at, "source_hash": head, "source_entry_sha256s": sources,
        "fee_basis": "broker_actual_difference", "lines": lines})
