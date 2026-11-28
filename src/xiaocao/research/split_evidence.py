"""Immutable per-lot inputs for a weekly verification of the APP execution comparison."""

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from xiaocao.live.book_b_capital import digest
from xiaocao.live.trade_fee_accounting import order_key, projection, FEE_EVIDENCE


def collect(state, assignment):
    from xiaocao.live import entry_clock_pilot as pilot
    from xiaocao.live.book_b_live_morning import _plan_intent_path
    from xiaocao.live.book_b_live_lifecycle import _read_jsonl_strict
    from xiaocao.live.trading_execution import ExecutionStore
    from xiaocao.live.book_b_accounting import DATABASE, _entries

    pid = assignment["child_id"]
    folder = pilot.root(state)

    def optional(path):
        return json.loads(path.read_bytes()) if path.exists() else None

    selected = {
        r["event_hash"] for r in pilot.owned_rows(state) if r["owned_lot_id"] == pid
    }
    owned = [
        r
        for r in _read_jsonl_strict(state / "book_b_ownership_evidence.jsonl")
        if r["event_hash"] in selected
    ]
    keys = {order_key(r) for r in owned}
    plans = {assignment["early"]["plan_id"], pid} | {r["plan_id"] for r in owned}
    store = ExecutionStore(state / "events.jsonl")
    journal = []
    if owned:
        db_path = (state / DATABASE).resolve()
        if db_path.exists():
            with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
                entries = _entries(db)
                predecessors = dict(
                    db.execute("SELECT entry_hash,previous_hash FROM entries")
                )
            for e in entries:
                if (
                    e.get("lot_id") == pid
                    and e["kind"] in ("BUY", "SELL")
                    or e["kind"] == FEE_EVIDENCE
                    and order_key(e["event"]) in keys
                ):
                    journal.append(
                        {"entry": e, "previous_hash": predecessors[e["entry_hash"]]}
                    )
    return dict(
        assignment=assignment,
        disposition=optional(folder / "dispositions" / (assignment["day"] + ".json")),
        intents={k: optional(_plan_intent_path(state, k)) for k in sorted(plans)},
        executions={k: store.events(k) for k in sorted(plans)},
        ownership=owned,
        journal=journal,
    )


def verify(packet, actual, day):
    from xiaocao.live.book_b_live_morning import read_durable_live_plan_intent
    from xiaocao.live import entry_clock_pilot as pilot

    doc = packet["assignment"]
    parent = read_durable_live_plan_intent(doc["early"])
    whole = read_durable_live_plan_intent(doc["original"])
    pid = doc["child_id"]
    if (
        doc["day"] != day
        or doc["scope"] != pilot.AUTH
        or doc["sha256"] != digest({k: v for k, v in doc.items() if k != "sha256"})
        or doc["sha256"] != actual["assignment"]
        or pid != actual["child_id"]
        or pid != parent.plan_id + pilot.TAG
        or parent.plan_hash != replace(whole, shares=whole.shares - 100).plan_hash
        or not 0 < whole.limit_price * 100 * 1.0001 <= doc["paired_cash_yuan"] <= 3000
    ):
        raise ValueError("split_allocation_evidence")
    plans = {
        k: read_durable_live_plan_intent(v) for k, v in packet["intents"].items() if v
    }
    if parent.plan_id in plans and plans[parent.plan_id].plan_hash != parent.plan_hash:
        raise ValueError("split_parent_evidence")
    events = {}
    latest = {}
    for k, rows in packet["executions"].items():
        prev = None
        for seq, e in enumerate(rows, 1):
            if (
                e["event_hash"]
                != digest({k: v for k, v in e.items() if k != "event_hash"})
                or e["sequence"] != seq
                or e["previous_hash"] != prev
                or e["plan_id"] != k
                or k not in plans
                or e["plan_hash"] != plans[k].plan_hash
                or e["receipt"]["plan_hash"] != e["plan_hash"]
            ):
                raise ValueError("split_execution_evidence")
            events[e["event_id"]] = e
            prev = e["event_hash"]
            latest[k] = e["receipt"]
    disposition = packet.get("disposition") or {}
    if (
        disposition
        and (
            disposition["assignment"] != doc["sha256"] or disposition["child_id"] != pid
        )
        or disposition.get("kind") != actual.get("disposition")
    ):
        raise ValueError("split_disposition_evidence")
    receipt = latest.get(pid)
    if not receipt:
        if (
            actual["status"]
            != ("no_submit" if disposition.get("kind") == "no_submit" else "pending")
            or packet["ownership"]
        ):
            raise ValueError("split_absence_evidence")
        return
    child = plans[pid]
    early = latest.get(parent.plan_id) or {}
    if (
        child.code != parent.code
        or child.shares != 100
        or child.limit_price != parent.limit_price
        or receipt["state"] != actual["state"]
        or receipt.get("broker_order_id") != actual["order_id"]
        or receipt.get("broker_order_id")
        and receipt["broker_order_id"] == early.get("broker_order_id")
    ):
        raise ValueError("split_child_evidence")
    legs = {"BUY": [], "SELL": []}
    for r in packet["ownership"]:
        event = events[r["source_execution_event_id"]]
        k = r["plan_id"]
        if (
            r["event_hash"] != digest({k: v for k, v in r.items() if k != "event_hash"})
            or k != event["plan_id"]
            or plans[k].plan_hash != r["plan_hash"]
            or r["code"] != child.code
            or (k if r["side"] == "BUY" else plans[k].owned_lot_id) != pid
        ):
            raise ValueError("split_fill_evidence")
        legs[r["side"]].append(r)
    journal = []
    for item in packet["journal"]:
        entry = item["entry"]
        if entry["entry_hash"] != digest(
            {
                "body": {k: v for k, v in entry.items() if k != "entry_hash"},
                "previous_hash": item["previous_hash"],
            }
        ):
            raise ValueError("split_fee_posting_evidence")
        journal.append(entry)
    financial = projection(journal)["fills"]

    def leg(side):
        rows = legs[side]
        count = sum(r["shares"] for r in rows)
        gross = sum((Decimal(str(r["fill_notional"])) for r in rows), Decimal(0))
        fees = [financial.get(r["event_hash"], {}).get("fee_cents") for r in rows]
        return count, gross, None if None in fees else Decimal(sum(fees)) / 100

    bought, buy, buyfee = leg("BUY")
    sold, sell, sellfee = leg("SELL")
    complete = (
        receipt["state"] in {s.value for s in pilot.TERMINAL}
        and not receipt.get("submit_chain_uncertain")
        and not receipt.get("cancel_chain_uncertain")
        and bought == sold
    )
    net = (
        float(sell - buy - buyfee - sellfee)
        if complete and None not in (buyfee, sellfee)
        else None
    )
    if (
        actual["status"] != ("closed" if complete else "open_or_reconciling")
        or actual["bought"] != bought
        or actual["sold"] != sold
        or bought != receipt["filled_shares"]
        or actual["buy_gross"] != float(buy)
        or actual["sell_gross"] != float(sell)
        or actual["buy_actual_fee"] != (float(buyfee) if buyfee is not None else None)
        or actual["sell_actual_fee"]
        != (float(sellfee) if sellfee is not None else None)
        or actual["actual_realized_net"] != net
    ):
        raise ValueError("split_net_evidence")
