"""Construct explicit native fee evidence for isolated accounting fixtures only."""
from datetime import datetime
from decimal import Decimal
from xiaocao.live import book_b_accounting as ledger
from xiaocao.live.book_b_capital import digest


def fee_proof(root, snapshot, order, fee, *, identifier=None, replaces=None):
    rows = [e for e in ledger.replay_owned(root).entries if e["source"]["broker_order_id"] == order]
    gross = sum(Decimal(str(e["source"]["fill_notional"])) for e in rows)
    row = {"event_id": identifier or "fee-" + order, "trade_date": rows[0]["source"]["trade_date"],
        "broker_order_id": order, "code": rows[0]["code"], "side": rows[0]["kind"],
        "shares": sum(e["shares"] for e in rows), "gross_notional": str(gross),
        "ownership_event_hashes": [e["source_hash"] for e in rows],
        "coverage": "complete_order", "fee_basis": "broker_final_itemized",
        "fees": {"commission": str(fee), "stamp_duty": "0", "transfer_fee": "0", "other_fee": "0"},
        "net_cash_change": str((-gross if rows[0]["kind"] == "BUY" else gross) - Decimal(str(fee)))}
    statement = {"schema_version": "foundersc-native-trade-fees.v1",
        "source": "foundersc_native_app", "account_binding": "proven",
        "fund_account_binding_sha256": snapshot["fund_account_binding_sha256"],
        "observed_at": snapshot["observed_at"], "rows": [row]}
    statement["receipt_sha256"] = digest(statement)
    return {"statement": statement, "event_id": row["event_id"], "broker_snapshot": snapshot,
            "replaces_fee_entry_sha256": replaces}



def prove_fixture_fees(root, snapshot):
    entries = ledger.replay_owned(root).entries
    grouped = {}
    for event in entries:
        grouped.setdefault(event['source']['broker_order_id'], []).append(event)
    for order, group in grouped.items():
        fee = Decimal(sum(e['fee_cents'] for e in group)) / 100
        proof = fee_proof(root, snapshot, order, fee)
        ledger.record_trade_fees(root, proof, now=datetime.fromisoformat(snapshot['observed_at']))


def proved_fee_account(root, snapshot):
    from xiaocao.live.book_b_live_lifecycle import project_book_b_live_account
    now = datetime.fromisoformat(snapshot["observed_at"])
    project_book_b_live_account(root, snapshot, trade_date=snapshot["trade_date"], now=now)
    prove_fixture_fees(root, snapshot)
    return project_book_b_live_account(root, snapshot, trade_date=snapshot["trade_date"], now=now)
