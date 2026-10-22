"""Read-only APP lot/order/accounting joins; never repair or infer broker facts."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from xiaocao.live.book_b_accounting import details, latest_observation, replay_owned, verify_observation
from xiaocao.live.book_b_live_lifecycle import _load_intent_index, _read_jsonl_strict
from xiaocao.live.book_b_capital import digest
from xiaocao.live.trading_execution import account_writer_lock
from xiaocao.live.book_b_workflow import compare_final_plans


def _morning_final_plans(root: Path) -> tuple[list[dict], list[dict]]:
    plans, failures = [], []
    for path in sorted((root / "runs/history").glob("*.json")):
        try:
            if path.is_symlink():
                raise ValueError("APP_FINAL_PLAN_SYMLINK")
            raw = path.read_bytes()
            receipt = json.loads(raw)
            final = receipt.get("final_plan")
            if final is None:
                continue  # Old receipts stay missing; never reconstruct a decision.
            if (receipt.get("run_id") != path.stem or
                    receipt.get("runner_identity", {}).get("automation_id") != "xiaocao-book-b-live-morning" or
                    final.get("freeze", {}).get("market_date") != receipt.get("trade_date")):
                raise ValueError("APP_FINAL_PLAN_OWNER_OR_DATE_UNPROVEN")
            compare_final_plans(final, final)
            plans.append({"trade_date":receipt["trade_date"],"run_id":receipt["run_id"],
                "source_path":str(path),"source_sha256":hashlib.sha256(raw).hexdigest(),"final_plan":final})
        except (ValueError, OSError, TypeError, KeyError) as exc:
            failures.append({"source_path":str(path),"reason":type(exc).__name__})
    return plans, failures


def _seconds(start, end):
    if not start or not end:
        return None
    a,b = datetime.fromisoformat(start),datetime.fromisoformat(end)
    return (b-a).total_seconds() if a.tzinfo and b.tzinfo and b>=a else None


def build_lifecycle_report(root: Path) -> dict:
    root = Path(root)
    final_plans, final_plan_failures = _morning_final_plans(root)
    with account_writer_lock(root/"account_writer_locks","primary"):
        book = replay_owned(root)
        intents = _load_intent_index(root)
        rows = _read_jsonl_strict(root/"events.jsonl")
        financial = details(root) if (root/"accounting.sqlite3").exists() else []
        observation = latest_observation(root)
        current_observation = False
        if observation:
            try:
                verify_observation(root,observation,current=True)
                current_observation = True
            except ValueError:
                pass
    events = {}
    for row in rows:
        events.setdefault(row["plan_id"],[]).append(row)
    finances = {row["source_sha256"]:row for row in financial if row["kind"] in {"BUY","SELL"}}
    orders=[]
    for plan_id,plan in sorted(intents.items()):
        history=events.get(plan_id,[])
        previous=None
        for index,event in enumerate(history,1):
            if (event.get("plan_hash") != digest(plan) or event.get("previous_hash") != previous
                    or event.get("sequence") != index
                    or event.get("event_hash") != digest({k:v for k,v in event.items() if k!="event_hash"})):
                raise ValueError("APP_LIFECYCLE_EXECUTION_CHAIN_INVALID")
            previous=event["event_hash"]
        receipt=history[-1]["receipt"] if history else {}
        claim=next((row["ts"] for row in history if row["receipt"].get("submit_claim_id")),None)
        ack=next((row["ts"] for row in history if row["state"] in {"acknowledged","partial","filled"}),None)
        terminal=next((row["ts"] for row in history if row["state"] in {"filled","cancelled","rejected","skipped"}),None)
        order={"plan_id":plan_id,"plan_hash":digest(plan),"side":plan["side"],"code":plan["code"],
            "trade_date":plan["trade_date"],"snapshot_ref":plan.get("snapshot_ref"),"strategy_sha":plan.get("strategy_sha"),
            "lot_id":plan.get("owned_lot_id") or plan_id,"shares":plan["shares"],"limit_price":plan["limit_price"],
            "quote":{k:plan.get(k) for k in ("market_guard_latest_price","market_guard_observed_at","price_rule")},
            "state":receipt.get("state","unsubmitted"),"broker_order_id":receipt.get("broker_order_id"),
            "filled_shares":receipt.get("filled_shares",0),"remaining_shares":receipt.get("remaining_shares"),
            "submit_claim_id":receipt.get("submit_claim_id"),"created_at":plan.get("created_at"),
            "claimed_at":claim,"ack_observed_at":ack,"terminal_observed_at":terminal,
            "trigger_to_claim_seconds":_seconds(plan.get("sell_decision_at") or plan.get("created_at"),claim),
            "claim_to_ack_observation_seconds":_seconds(claim,ack),
            "claim_to_terminal_observation_seconds":_seconds(claim,terminal),
            "clock_basis":"local_observation_not_inferred_exchange_fill_time",
            "execution_head_sha256":previous}
        orders.append(order)
    lots=[]
    for lot_id,lot in sorted(book.lots.items()):
        fills=[r for r in book.rows if (r["plan_id"] if r["side"]=="BUY" else
               r.get("owned_lot_id") or intents[r["plan_id"]].get("owned_lot_id"))==lot_id]
        sell_finances=[finances.get(r["event_hash"]) for r in fills if r["side"]=="SELL"]
        final=bool(sell_finances) and all(r and r.get("final_realized_pnl") is not None for r in sell_finances)
        linked=[order for order in orders if order["lot_id"]==lot_id]
        assisted="user-assisted" in lot_id
        attribution=("explicit_user_assistance" if assisted else "recorded_automation_chain" if
                     linked and all(o["submit_claim_id"] for o in linked if o["filled_shares"]>0) else "unclassified")
        lots.append({"lot_id":lot_id,"code":lot["code"],"entry_date":lot["entry_date"],
            "remaining_shares":lot["shares"],"entry_snapshot_ref":lot["snapshot_ref"],
            "ownership_event_hashes":[r["event_hash"] for r in fills],
            "order_plan_ids":[o["plan_id"] for o in linked],"assistance_basis":attribution,
            "estimated_realized_pnl":round(sum(e["realized_pnl_cents"] for e in book.entries if e["lot_id"]==lot_id)/100,2),
            "confirmed_realized_pnl":round(sum(float(r["final_realized_pnl"]) for r in sell_finances),2) if final else None,
            "fee_status":"actual_fees_complete_for_sold_quantity" if final else "actual_fees_unproved",
            "fills":[{k:r.get(k) for k in ("event_hash","plan_id","side","shares","fill_price",
                "fill_notional","broker_order_id","trade_time","native_trade_id","ts")} for r in fills]})
    result={"schema_version":"app-b-lifecycle-report.v1","authority":0,"environment":"app_server_simulation",
        "final_plans":final_plans,"final_plan_failures":final_plan_failures,
        "ownership_head_sha256":book.head,"orders":orders,"lots":lots,
        "accounting_observation":observation,"accounting_heads_current":current_observation,
        "headline_nav":observation.get("marked_nav") if observation and current_observation else None,
        "headline_confirmed_profit":observation.get("cumulative_pnl") if observation and current_observation else None,
        "limitations":["No broker actions or new financial postings", "recorded automation chain does not exclude unrecorded manual help",
                        "missing fee/cash proof keeps confirmed profit unknown", "observation duration is not exchange latency"]}
    result["receipt_sha256"]=digest(result)
    return result
