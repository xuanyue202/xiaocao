"""Evidence-based EOD task closure, distinct from broker order terminality."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()


def historical_sell_resolutions(root: Path, snapshot: dict, *, now: datetime) -> list[dict]:
    """Close only the bookkeeping task for independently disposed historical lots.

    UNKNOWN and the same-code BUY fence stay intact. Every fresh snapshot can
    reopen the task; a zero holding alone never supplies this proof.
    """
    from .book_b_accounting import replay_owned
    from .book_b_capital import policy
    from .book_b_live_lifecycle import (validate_broker_account_snapshot,
        open_execution_plan_ids, _load_intent_index, _post_close_timestamp,
        _read_jsonl_strict, _validate_execution_fill_coverage, _validate_same_day_broker_fill_coverage, _broker_side)

    snapshot = validate_broker_account_snapshot(snapshot,
        trade_date=snapshot["trade_date"], now=now)
    _post_close_timestamp(snapshot["observed_at"], trade_date=snapshot["trade_date"],
        reason="EOD_REVIEW_SNAPSHOT_PRE_CLOSE")
    config = policy(root)
    binding = config["fund_account_binding_sha256"] if config else None
    database = root / "accounting.sqlite3"
    if binding is None and database.exists():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
            saved = db.execute("SELECT value FROM metadata WHERE key='fund_account_binding_sha256'").fetchone()
            binding = saved[0] if saved else None
    if binding and binding != snapshot["fund_account_binding_sha256"]:
        raise ValueError("BOOK_B_CAPITAL_ACCOUNT_BINDING_MISMATCH")
    book = replay_owned(root)
    intents = _load_intent_index(root)
    events = _read_jsonl_strict(root / "events.jsonl")
    _validate_execution_fill_coverage(root, book.rows, execution_events=events)
    _validate_same_day_broker_fill_coverage(snapshot, book.rows, trade_date=snapshot["trade_date"])
    latest = {r["plan_id"]: r["receipt"] for r in events}
    result = []
    for plan_id in open_execution_plan_ids(root):
        plan = intents.get(plan_id, {})
        current = latest.get(plan_id)
        lot_id = plan.get("owned_lot_id")
        lot = book.lots.get(lot_id)
        if (plan.get("side") != "SELL" or plan.get("trade_date", "") >= snapshot["trade_date"]
                or current is None or not current.get("broker_order_id") or current.get("filled_shares") != 0
                or current.get("state") not in {"unknown", "acknowledged", "reconciling", "submitted"}
                or current.get("remaining_shares") != plan.get("shares")
                or current.get("plan_hash") != _digest(plan)
                or current.get("account_binding") not in {"proven", "bound"}
                or current.get("cancel_chain_uncertain") or not lot or lot["shares"] != 0):
            continue
        code = plan["code"].split(".")[0]
        if any(str(row.get("证券代码")) == code and float(row["证券数量"]) != 0
               for row in snapshot["tables"]["positions"]["rows"]):
            continue
        buys = [r for r in book.rows if r["side"] == "BUY" and r["plan_id"] == lot_id]
        sells = [r for r in book.rows if r["side"] == "SELL"
                 and (r.get("owned_lot_id") or intents[r["plan_id"]].get("owned_lot_id")) == lot_id]
        if (not buys or not sells or any(r["trade_date"] > plan["trade_date"] for r in buys)
                or sum(r["shares"] for r in buys) != sum(r["shares"] for r in sells)
                or any(r["plan_id"] == plan_id or r["trade_date"] <= plan["trade_date"] for r in sells)):
            continue
        disposal_receipts = [latest.get(r["plan_id"]) for r in sells]
        if any(r is None or r.get("state") not in {"filled", "cancelled"}
               or not r.get("broker_order_id") or r.get("submit_chain_uncertain") or r.get("cancel_chain_uncertain")
               or r.get("account_binding") not in {"proven", "bound"} or r.get("receipt_mapping") is not True
               for r in disposal_receipts):
            continue
        if any(receipt["broker_order_id"] != event["broker_order_id"]
               or receipt["filled_shares"] < event["cumulative_filled_shares"]
               for event, receipt in zip(sells, disposal_receipts)):
            continue
        # Today's exact terminal disposal is supporting evidence. Any other
        # same-code activity can change the interpretation and stays blocking.
        from .foundersc_native_broker import _ORDER_FILLED_STATUSES, _ORDER_CANCELLED_STATUSES
        today_disposals = {r["broker_order_id"] for r in sells if r["trade_date"] == snapshot["trade_date"]}
        if any(str(row.get("证券代码")) == code and (
                str(row.get("委托编号")) not in today_disposals
                or _broker_side(row.get("买卖标志")) != "SELL"
                or (kind == "today-orders" and str(row.get("状态说明") or "").strip()
                    not in _ORDER_FILLED_STATUSES | _ORDER_CANCELLED_STATUSES))
               for kind in ("today-orders", "today-trades")
               for row in snapshot["tables"][kind]["rows"]):
            continue
        result.append({"plan_id": plan_id, "plan_hash": current["plan_hash"],
            "broker_order_id": current["broker_order_id"], "owned_lot_id": lot_id,
            "code": plan["code"], "status": "economically_closed",
            "broker_order_state": current["state"],
            "buy_event_hashes": [r["event_hash"] for r in buys],
            "disposal_event_hashes": [r["event_hash"] for r in sells],
            "disposal_order_ids": sorted({r["broker_order_id"] for r in disposal_receipts}),
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "fund_account_binding_sha256": snapshot["fund_account_binding_sha256"]})
    return result


def assess_eod(root: Path, account: dict, snapshot: dict | None = None,
               *, now: datetime, persist: bool = False) -> dict:
    """Return all execution/cash/fee blockers without stopping at the first one."""
    from .book_b_live_lifecycle import open_execution_plan_ids, _write_json_atomic, _read_jsonl_strict
    resolutions = historical_sell_resolutions(root, snapshot, now=now) if snapshot else []
    closed = {r["plan_id"] for r in resolutions}
    active = sorted(set(open_execution_plan_ids(root)) - closed)
    blockers = []
    if active:
        blockers.append({"code": "LIVE_BOOK_B_EOD_OPEN_EXECUTION_RECONCILE_REQUIRED",
                         "kind": "execution", "plan_ids": active})
    accounting = account.get("accounting")
    if accounting is None and account.get("ownership_head_sha256"):
        blockers.append({"code": "LIVE_BOOK_B_SETTLEMENT_ACTUAL_FEES_REQUIRED", "kind": "fees"})
    elif accounting is not None:
        if accounting.get("status") not in {"reconciled", "cash_discrepancy_tolerated"}:
            blockers.append({"code": "LIVE_BOOK_B_SETTLEMENT_CASH_RECONCILE_REQUIRED",
                "kind": "cash", "status": accounting.get("status"),
                "cash_difference": accounting.get("cash_difference")})
        if accounting.get("fee_status") != "actual_fees_complete":
            blockers.append({"code": "LIVE_BOOK_B_SETTLEMENT_ACTUAL_FEES_REQUIRED",
                "kind": "fees", "pending_fee_orders": accounting.get("pending_fee_orders", [])})
    body = {"schema_version": "book-b-eod-review.v1", "trade_date": account["trade_date"],
        "status": "blocked" if active else "accounting_pending" if blockers else "ready",
        "broker_snapshot_sha256": account.get("broker_snapshot_sha256"),
        "ownership_head_sha256": account.get("ownership_head_sha256"),
        "accounting_observation_sha256": (accounting or {}).get("receipt_sha256"),
        "historical_order_resolutions": resolutions, "active_plan_ids": active,
        "blockers": blockers}
    if persist:
        events = _read_jsonl_strict(Path(root) / "events.jsonl")
        body["execution_evidence"] = {"event_count": len(events), "events_sha256": _digest(events)}
        document = {**body, "broker_snapshot": snapshot}
        digest = _digest(document)
        path = Path(root) / "eod_reviews" / f"{account['trade_date']}-{digest}.json"
        if path.exists() and json.loads(path.read_text()) != document:
            raise ValueError("EOD_REVIEW_IMMUTABILITY_VIOLATION")
        _write_json_atomic(path, document)
        body = {**body, "review_path": str(path), "review_sha256": digest}
    return body


class EodSettlementPending(ValueError):
    def __init__(self, review: dict):
        self.review = review
        super().__init__(review["blockers"][0]["code"])


def settlement_resolved_plan_ids(root: Path, settlement: dict) -> set[str]:
    """Verify a new settlement's exact review; legacy exceptions stay rejected."""
    review = settlement.get("eod_review")
    if not review or not review.get("historical_order_resolutions"):
        return set()
    path = Path(root) / "eod_reviews" / f"{review['trade_date']}-{review['review_sha256']}.json"
    document = json.loads(path.read_text())
    if _digest(document) != review["review_sha256"]:
        raise ValueError("EOD_REVIEW_HASH_MISMATCH")
    snapshot = document["broker_snapshot"]
    if (snapshot["snapshot_sha256"] != settlement["broker_snapshot_sha256"]
            or document["ownership_head_sha256"] != settlement["ownership_head_sha256"]
            or {k: v for k, v in review.items() if k not in {"review_path", "review_sha256"}}
                != {k: v for k, v in document.items() if k != "broker_snapshot"}):
        raise ValueError("EOD_REVIEW_SETTLEMENT_BINDING_MISMATCH")
    # Verify the sealed dated evidence prefix. Later legitimate order states or
    # unrelated fills cannot change a previously valid immutable settlement.
    from .book_b_live_lifecycle import _read_jsonl_strict, validate_broker_account_snapshot
    from .book_b_accounting import replay_owned
    evidence = document["execution_evidence"]
    events = _read_jsonl_strict(Path(root) / "events.jsonl")
    count = evidence["event_count"]
    if type(count) is not int or count <= 0 or len(events) < count or _digest(events[:count]) != evidence["events_sha256"]:
        raise ValueError("EOD_REVIEW_EXECUTION_PREFIX_CHANGED")
    validate_broker_account_snapshot(snapshot, trade_date=settlement["trade_date"],
        now=datetime.fromisoformat(snapshot["observed_at"]))
    if document["ownership_head_sha256"] not in replay_owned(root).cash_by_head:
        raise ValueError("EOD_REVIEW_OWNERSHIP_PREFIX_CHANGED")
    return {r["plan_id"] for r in document["historical_order_resolutions"]}
