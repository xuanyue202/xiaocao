"""Predeclared, funded APP-rule controls; no broker or canonical paper writer.

All four portfolios commit together under one research lock. Plans precede
model price windows; unknown fills retain reservations. The window model is
explicitly different from an APP receipt and never grants trading authority.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import fcntl
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.live.account_risk import AccountRiskReceipt, NAV_BASIS, NavObservation, evaluate_account_risk
from xiaocao.live.book_b_allocation import BookBAllocationFacts, allocate_policy_rows
from xiaocao.live.book_b_capital import digest
from xiaocao.live.book_b_pricing import initial_limit_price
from xiaocao.live.book_b_workflow import RULE_PROFILE, adjudicate_book_b, eligible_buy_rows, final_plan_receipt, compare_final_plans
from xiaocao.live.trading_runner import frozen_rows_digest
from xiaocao.utils.atomic_files import atomic_write

CHINA = ZoneInfo("Asia/Shanghai")
VARIANTS = ("app_b_control", "mode_m", "open_limit", "no_kol")
PROTOCOL = {
    "schema_version": "app-b-forward-protocol.v1", "authority": 0, "rule_profile": RULE_PROFILE,
    "initial_capital_cents": 10_000_000, "fee_rate": .0001, "variants": list(VARIANTS),
    "entry": "shared_app_allocator_and_policy_caps", "exit": "production_B_staged_exit",
    "window_minutes": 5, "max_volume_fraction": .01,
    "fill_model": "limit_price_at_observed_cross_with_one_percent_volume_cap",
    "remaining_model_quantity": "expire_after_complete_window_or_remain_unknown",
    "planning_time": "after_business_next_future_window_never_backdated",
    "promotion": "PROPOSAL_ONLY_requires_research_run_and_human_gate",
}


def _stamp(value) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("FORWARD_AWARE_TIME_REQUIRED")
    return parsed.astimezone(CHINA)


def _cents(value) -> int:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("FORWARD_FINITE_MONEY_REQUIRED")
    return int((number*100).quantize(Decimal("1")))


def _read_state(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("FORWARD_STATE_SYMLINK")
    if not path.exists():
        return {"schema_version":"app-b-forward-state.v1", "protocol_sha256":digest(PROTOCOL),
                "accounts":{v:{"cash_cents":PROTOCOL["initial_capital_cents"], "lots":[], "orders":[],
                               "risk":None, "marks":{}, "valuations":[]} for v in VARIANTS},
                "events":[], "morning_dates":[]}
    value = json.loads(path.read_bytes())
    if (value.get("state_sha256") != digest({k:v for k,v in value.items() if k != "state_sha256"})
            or value.get("protocol_sha256") != digest(PROTOCOL)):
        raise ValueError("FORWARD_STATE_OR_PROTOCOL_CHANGED")
    return value


def _marked(account: dict, marks: dict, now: datetime) -> tuple[int, int] | None:
    if any(o["status"] in {"pending", "unknown"} for o in account["orders"]):
        return None
    exposure = 0
    for lot in account["lots"]:
        if lot["shares"] <= 0:
            continue
        mark = marks.get(lot["code"], {})
        try:
            stamp = _stamp(mark["observed_at"])
            price = Decimal(str(mark["price"]))
            if (price <= 0 or not price.is_finite() or mark.get("status") != "ok"
                    or stamp.date() != now.date() or stamp > now
                    or not ((now-stamp).total_seconds() <= 300 or (now.hour >= 15 and stamp.hour >= 15))):
                return None
        except (KeyError, ValueError, TypeError):
            return None
        exposure += _cents(price*lot["shares"])
    return account["cash_cents"] + _cents(Decimal(exposure)/100*(1-Decimal(str(PROTOCOL["fee_rate"])))), exposure


def _risk(account: dict, marks: dict, now: datetime) -> AccountRiskReceipt:
    marked = _marked(account, marks, now)
    previous = AccountRiskReceipt(**account["risk"]) if account["risk"] else None
    observation = None if marked is None else NavObservation(now.date().isoformat(), marked[0]/100,
        "paper:B", 100000., 0., NAV_BASIS, "reconciled", now.isoformat(), digest(marks))
    result = evaluate_account_risk([], current_nav=observation, asof=now, account_id="paper:B",
        initial_capital=100000., require_settled_history=False, previous_receipt=previous)
    account["risk"] = result.as_dict()
    return result


def _reserved(account: dict) -> int:
    return sum(order["reserved_cents"] for order in account["orders"]
               if order["side"] == "BUY" and order["status"] in {"pending", "unknown"})


def _window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(second=0, microsecond=0)+timedelta(minutes=1)
    if (9,25) <= (now.hour,now.minute) < (9,30):
        start = now.replace(hour=9,minute=30,second=0,microsecond=0)
    end = start+timedelta(minutes=PROTOCOL["window_minutes"]-1)
    # No window crosses lunch or the continuous-auction close.
    if not ((9,30) <= (start.hour,start.minute) <= (end.hour,end.minute) <= (11,30)
            or (13,0) <= (start.hour,start.minute) <= (end.hour,end.minute) <= (14,57)):
        raise ValueError("FORWARD_MODEL_WINDOW_CLOSED")
    return start, end


def _order(account: dict, *, code: str, shares: int, limit: float, side: str,
           now: datetime, source: str, lot_id: str | None = None, context: dict | None = None) -> dict:
    start, end = _window(now)
    if shares <= 0 or limit <= 0 or (side == "BUY" and shares % 100):
        raise ValueError("FORWARD_ORDER_ECONOMICS_INVALID")
    result = {"code":code, "side":side, "shares":shares, "limit_price":limit,
        "created_at":now.isoformat(), "window_start":start.isoformat(), "window_end":end.isoformat(),
        "source_sha256":source, "lot_id":lot_id, "context":context or {},
        "reserved_cents":_cents(Decimal(str(limit))*shares*(1+Decimal(str(PROTOCOL["fee_rate"])))) if side=="BUY" else 0}
    result["order_id"] = digest(result)
    result.update(status="pending", filled_shares=0, fee_cents=0, model_evidence=None)
    if result["reserved_cents"] > account["cash_cents"]-_reserved(account):
        raise ValueError("FORWARD_CASH_RESERVATION_EXCEEDED")
    account["orders"].append(result)
    return result


def adjudicate_variant(rows: list[dict], freeze: dict, policy: dict, variant: str) -> tuple:
    """Use the same derived candidates for quote acquisition and planning."""
    if variant not in VARIANTS:
        raise ValueError("FORWARD_VARIANT_INVALID")
    if variant == "no_kol":
        policy = {"status":"neutral", "book":"B", "runtime":"live", "reason":"REGISTERED_NO_KOL_CONTROL"}
    adjudication = adjudicate_book_b(rows, policy, freeze=freeze, runtime="live")
    derived, explanation = adjudication.rows, deepcopy(adjudication.receipt)
    if variant == "mode_m":
        flags = {(r["code"],r.get("mode")):r.get("mode_star") is True for r in rows}
        derived = [{**r,"mode_exec_star":flags.get((r["code"],r.get("mode")), False)} for r in derived]
        ids = {(r["code"],r.get("mode")) for r in eligible_buy_rows(derived)}
        for row in explanation["rows"]:
            row["star_selected"] = (row["code"],row["mode"]) in ids
            if row["star_selected"]:
                row["selection_reason"] = "REGISTERED_MODE_M_CHALLENGE"
        explanation["strategy_codes"] = [r["code"] for r in eligible_buy_rows(derived)]
        explanation["strategy_semantics_sha256"] = digest({"source":explanation["strategy_semantics_sha256"], "variant":variant,"rows":explanation["rows"]})
        explanation["receipt_sha256"] = digest({k:v for k,v in explanation.items() if k!="receipt_sha256"})
    return derived, explanation, policy


def morning_quote_codes(rows: list[dict], freeze: dict, policy: dict) -> set[str]:
    return {r["code"] for variant in VARIANTS
            for r in eligible_buy_rows(adjudicate_variant(rows, freeze, policy, variant)[0])
            if r.get("mode_state") in {"ACTIVE", "PROVISIONAL"} and not r["code"].endswith(".BJSE")}


def plan_morning(state: dict, inputs: dict, now: datetime) -> dict:
    today = now.date().isoformat()
    if today in state["morning_dates"]:
        return {"status":"already_consumed", "trade_date":today}
    rows, freeze = inputs["rows"], inputs["freeze"]
    if (freeze.get("market_date") != today or len(rows) != freeze.get("snapshot_row_count")
            or frozen_rows_digest(rows) != freeze.get("snapshot_sha256")
            or not freeze.get("checkpoint_sha256")):
        raise ValueError("FORWARD_ORIGINAL_BUNDLE_REQUIRED")
    resolve_orders(state, inputs.get("windows", {}), now)
    state["morning_dates"].append(today)
    results = {}
    # Late invocations record the denominator, without reconstructing a morning order.
    late = not (9,25) <= (now.hour,now.minute) < (10,0)
    for variant, account in state["accounts"].items():
        derived, explanation, policy = adjudicate_variant(rows, freeze, inputs["policy"], variant)
        risk = _risk(account, inputs["marks"], now)
        marked = _marked(account, inputs["marks"], now)
        held = {lot["code"] for lot in account["lots"] if lot["shares"] > 0}
        held.update(o["code"] for o in account["orders"] if o["status"] in {"pending","unknown"})
        candidates = [r for r in eligible_buy_rows(derived) if r["mode_state"] in {"ACTIVE","PROVISIONAL"}
                      and r["code"] not in held and not r["code"].endswith(".BJSE")]
        facts = None
        evidence = None
        orders = []
        reason = "LATE_INPUT_NO_BACKDATE" if late else "PLANNED_OR_EMPTY"
        if not late and marked is not None:
            facts = BookBAllocationFacts(settled_nav=marked[0]/100,
                available_cash=(account["cash_cents"]-_reserved(account))/100,
                current_open_exposure=marked[1]/100, deploy_factor=inputs["performance_factor"],
                source="independent_forward_account_fresh_marks")
            effective, evidence = allocate_policy_rows(candidates, facts, policy, risk)
            for row in evidence["rows_by_code"].values():
                code = row["code"]
                market = inputs["market_guards"].get(code, {})
                try:
                    observed = _stamp(market["observed_at"])
                    fresh = observed.date()==now.date() and 0 <= (now-observed).total_seconds() <= 60
                except (KeyError, ValueError):
                    fresh = False
                if market.get("allowed") is not True or not fresh:
                    continue
                limit = initial_limit_price(row.get("open"),row.get("basket_price"),
                    premium_pct=0 if variant=="open_limit" else .5, tick_size=.01)
                if limit is None:
                    continue
                orders.append(_order(account, code=code, shares=int(row["mode_exec_planned_shares"]),
                    limit=limit, side="BUY", now=now, source=digest(inputs), context=row))
        elif marked is None:
            reason = "CURRENT_MARKS_UNPROVEN"
        results[variant] = {"status":reason, "risk":risk.as_dict(),
            "held_or_reserved_codes":sorted(held), "market_guards":inputs["market_guards"],
            "final_plan":final_plan_receipt(explanation, facts.canonical_payload() if facts else None,
                orders, policy_evidence=evidence, execution_model=PROTOCOL["fill_model"])}
    return {"trade_date":today,"status":"recorded", "variants":results}


def resolve_orders(state: dict, windows: dict, now: datetime) -> list[dict]:
    """Consume only exact future windows, never a current-price fallback."""
    results = []
    rate = Decimal(str(PROTOCOL["fee_rate"]))
    for variant, account in state["accounts"].items():
        for order in account["orders"]:
            if order["status"] not in {"pending","unknown"} or now <= _stamp(order["window_end"])+timedelta(minutes=1):
                continue
            evidence = windows.get(order["order_id"])
            if not evidence or evidence.get("complete") is not True:
                order["status"] = "unknown"
                results.append({"variant":variant,"order_id":order["order_id"],"status":"unknown"})
                continue
            if (evidence.get("code") != order["code"] or evidence.get("window_start") != order["window_start"]
                    or evidence.get("window_end") != order["window_end"] or _stamp(evidence["observed_at"]) > now
                    or _stamp(evidence["observed_at"]) <= _stamp(order["window_end"])):
                raise ValueError("FORWARD_WINDOW_BINDING_INVALID")
            bars = evidence["bars"]
            required = {_stamp(order["window_start"])+timedelta(minutes=i) for i in range(PROTOCOL["window_minutes"])}
            if {_stamp(b["at"]) for b in bars} != required or len(bars) != len(required):
                raise ValueError("FORWARD_WINDOW_COVERAGE_INVALID")
            limit = Decimal(str(order["limit_price"]))
            crossed_volume = Decimal(0)
            for bar in bars:
                price, volume = Decimal(str(bar["price"])), Decimal(str(bar["volume_shares"]))
                if not price.is_finite() or not volume.is_finite() or price <= 0 or volume < 0:
                    raise ValueError("FORWARD_WINDOW_VALUES_INVALID")
                if (price <= limit if order["side"]=="BUY" else price >= limit):
                    crossed_volume += volume
            lot_size = 100 if order["side"]=="BUY" else 1
            capacity = int(crossed_volume*Decimal(str(PROTOCOL["max_volume_fraction"])) // lot_size)*lot_size
            quantity = min(order["shares"],capacity)
            notional = _cents(limit*quantity)
            fee = _cents(limit*quantity*rate)
            order.update(filled_shares=quantity, fee_cents=fee, fill_notional_cents=notional,
                status="filled" if quantity==order["shares"] else "partial_expired" if quantity else "no_fill",
                model_evidence=evidence, resolved_at=now.isoformat(), fill_basis=PROTOCOL["fill_model"])
            if quantity:
                if order["side"]=="BUY":
                    account["cash_cents"] -= notional+fee
                    account["lots"].append({"lot_id":order["order_id"], "code":order["code"], "shares":quantity,
                        "entry_date":_stamp(order["window_start"]).date().isoformat(), "entry_price":float(limit),
                        "cost_cents":notional+fee, "context":order["context"], "entry_order_id":order["order_id"]})
                else:
                    lot = next(lot for lot in account["lots"] if lot["lot_id"]==order["lot_id"])
                    if quantity>lot["shares"] or lot["entry_date"] >= _stamp(order["window_start"]).date().isoformat():
                        raise ValueError("FORWARD_SELL_OWNERSHIP_OR_T1_INVALID")
                    cost = lot["cost_cents"] if quantity==lot["shares"] else round(lot["cost_cents"]*quantity/lot["shares"])
                    lot["shares"] -= quantity
                    lot["cost_cents"] -= cost
                    order["realized_pnl_cents"] = notional-fee-cost
                    account["cash_cents"] += notional-fee
            if account["cash_cents"] < _reserved(account):
                raise ValueError("FORWARD_CASH_INVARIANT_FAILED")
            results.append({"variant":variant,"order_id":order["order_id"],"status":order["status"],"filled_shares":quantity})
    return results


def observe_checkpoint(state: dict, inputs: dict, now: datetime) -> dict:
    from xiaocao.live.book_b_live_intraday import _sell_limit_price
    from xiaocao.live.kol_policy import exit_adjustment
    resolutions = resolve_orders(state, inputs.get("windows", {}), now)
    decisions = []
    for variant, account in state["accounts"].items():
        for lot in account["lots"]:
            if lot["shares"] <= 0:
                continue
            status = inputs.get("statuses", {}).get(variant, {}).get(lot["lot_id"], {})
            reason = status.get("sell_reason")
            if reason=="KOL_DISCRETIONARY_EXIT" and (variant=="no_kol" or not
                    exit_adjustment(inputs.get("policy", {"status":"absent"}),lot["code"])["triggered"]):
                status={**status,"triggered":False,"sell_block_reason":"KOL_CURRENT_AUTHORITY_UNPROVEN"}
            decision = {"variant":variant, "lot_id":lot["lot_id"], "status":status,"model_order":None}
            decisions.append(decision)
            if (status.get("triggered") is not True or status.get("sell_block_reason")
                    or status.get("market_guard_status") != "ok" or lot["entry_date"] >= now.date().isoformat()
                    or reason not in {"HARD_STOP","AI_EVENT_RISK_EXIT","KOL_DISCRETIONARY_EXIT","TRAILING_STOP","EOD_DISCIPLINE_1455"}
                    or (reason in {"TRAILING_STOP","EOD_DISCIPLINE_1455"} and
                        (inputs.get("checkpoint_phase") != "closing" or (now.hour,now.minute)<(14,45)))):
                continue
            if any(o["side"]=="SELL" and o["lot_id"]==lot["lot_id"] and
                   (o["status"] in {"pending","unknown"} or _stamp(o["created_at"]).date()==now.date()) for o in account["orders"]):
                continue
            try:
                observed = _stamp(status["market_guard_observed_at"])
                if observed.date()!=now.date() or not 0 <= (now-observed).total_seconds() <= 300:
                    continue
                _window(now)
            except (ValueError, KeyError):
                continue
            limit, _ = _sell_limit_price(status["latest_price"],status["market_guard_down_price"],
                status.get("best_bid_price") if (now-observed).total_seconds()<=30 else None,
                status.get("best_bid_volume") if (now-observed).total_seconds()<=30 else None)
            decision["model_order"] = _order(account, code=lot["code"], shares=lot["shares"], limit=limit,
                side="SELL", now=now, source=digest(inputs), lot_id=lot["lot_id"], context=status)
        risk = _risk(account, inputs["marks"], now)
        marked = _marked(account,inputs["marks"],now)
        account["marks"] = inputs["marks"]
        observation = {"observed_at":now.isoformat(),"cash_cents":account["cash_cents"],
            "reserved_cents":_reserved(account),"nav_cents":marked[0] if marked else None,
            "market_value_cents":marked[1] if marked else None,
            "risk":risk.as_dict(), "source_sha256":digest(inputs),
            "status":"marked" if marked else "missing_current_marks",
            "portfolio_sha256":digest({"cash":account["cash_cents"],"lots":account["lots"]})}
        account["valuations"].append(observation)
    return {"status":"observed", "resolutions":resolutions,"decisions":decisions}


def transact(root: Path, *, phase: str, inputs: dict, now: datetime) -> dict:
    now = _stamp(now.isoformat())
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    atomic_write(root/"protocol.json", json.dumps(PROTOCOL,ensure_ascii=False,sort_keys=True).encode(), immutable=True)
    with (root/".lock").open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state = _read_state(root/"state.json")
        if phase=="morning":
            result = plan_morning(state,inputs,now)
        elif phase in {"monitor","eod"}:
            result = observe_checkpoint(state,inputs,now)
        else:
            raise ValueError("FORWARD_PHASE_INVALID")
        event = {"phase":phase,"observed_at":now.isoformat(),"inputs":inputs,"result":result,
                 "previous_event_sha256":state["events"][-1]["event_sha256"] if state["events"] else None}
        event["event_sha256"] = digest(event)
        state["events"].append(event)
        state["state_sha256"] = digest({k:v for k,v in state.items() if k!="state_sha256"})
        atomic_write(root/"state.json",json.dumps(state,ensure_ascii=False,sort_keys=True,allow_nan=False).encode())
        return {"status":result["status"],"phase":phase,"event_sha256":event["event_sha256"],
                "state_path":str((root/"state.json").resolve()),"authority":0}


def performance(root: Path, *, as_of: datetime | None = None) -> dict:
    state = _read_state(Path(root)/"state.json")
    observations = [_stamp(e["observed_at"]) for e in state["events"] if e["inputs"].get("trading_dates")]
    cutoff = _stamp(as_of.isoformat()) if as_of else max(observations, default=None)
    through = max(observations, default=None)
    tail_unproved = cutoff is not None and (through is None or through.date() < cutoff.date())
    known_dates = {day for event in state["events"] for day in event["inputs"].get("trading_dates", [])
                   if state["morning_dates"] and day >= state["morning_dates"][0]
                   and cutoff is not None and day <= cutoff.date().isoformat()}
    expected = {day for day in known_dates if day < cutoff.date().isoformat() or cutoff.hour >= 15}
    coverage = {"status":"not_started" if not state["morning_dates"] else
                         "unproved_tail" if tail_unproved or through is None else "covered_through_report_date",
                "observed_through":through.date().isoformat() if through else None,
                "report_date":cutoff.date().isoformat() if cutoff else None,
                "unproved_tail":({"after":through.date().isoformat() if through else None,
                                   "through":cutoff.date().isoformat()} if tail_unproved else None)}
    accounts = {}
    for variant, account in state["accounts"].items():
        observed = account["valuations"][-1] if account["valuations"] else {}
        nav = (observed.get("nav_cents") if observed.get("portfolio_sha256")==digest(
            {"cash":account["cash_cents"],"lots":account["lots"]}) and not any(
                o["status"] in {"pending","unknown"} for o in account["orders"]) else None)
        eod={_stamp(v["observed_at"]).date().isoformat():v for v in account["valuations"]
             if _stamp(v["observed_at"]).hour>=15 and v["nav_cents"] is not None}
        peak=PROTOCOL["initial_capital_cents"]
        drawdown=0.
        for day in sorted(eod):
            peak=max(peak,eod[day]["nav_cents"])
            drawdown=max(drawdown,(1-eod[day]["nav_cents"]/peak)*100)
        accounts[variant] = {"cash":account["cash_cents"]/100, "reserved_cash":_reserved(account)/100,
            "marked_nav":nav/100 if nav is not None else None,
            "net_model_return_pct":(nav/PROTOCOL["initial_capital_cents"]-1)*100 if nav is not None else None,
            "open_lots":sum(lot["shares"]>0 for lot in account["lots"]),
            "planned_orders":len(account["orders"]), "unknown_orders":sum(o["status"]=="unknown" for o in account["orders"]),
            "pending_orders":sum(o["status"]=="pending" for o in account["orders"]),
            "no_fill_orders":sum(o["status"]=="no_fill" for o in account["orders"]),
            "partial_expired_orders":sum(o["status"]=="partial_expired" for o in account["orders"]),
            "filled_orders":sum(o["filled_shares"]>0 for o in account["orders"]),
            "estimated_fees":sum(o["fee_cents"] for o in account["orders"])/100,
            "realized_model_pnl":sum(o.get("realized_pnl_cents",0) for o in account["orders"])/100,
            "valuation_observed_at":observed.get("observed_at"), "fee_status":"protocol_model_rate",
            "eod_curve":eod, "missing_eod_dates":sorted(set(expected)-set(eod)),
            "observed_eod_max_drawdown_pct":drawdown if eod else None,
            "drawdown_coverage":("unproved_calendar_tail" if tail_unproved else
                                 "complete_expected_dates" if expected and not set(expected)-set(eod) else "incomplete"),
            "app_realized_profit":None, "manual_assistance":"not_applicable_research_model"}
    return {"schema_version":"app-b-forward-performance.v1", "authority":0, "promotion":"PROPOSAL_ONLY",
            "calendar_coverage":coverage, "missing_morning_dates":sorted(known_dates-set(state["morning_dates"])),
            "protocol_sha256":digest(PROTOCOL), "consumed_morning_days":state["morning_dates"], "accounts":accounts,
            "limitations":["model fills are not APP outcomes", "observed NAV does not prove complete daily drawdown",
                            "after-business execution timing is an explicit difference from APP opening"]}


def compare_app_control(root: Path, app_report: dict) -> list[dict]:
    """Compare actual recorded plans with each same-day funded control plan."""
    state = _read_state(Path(root) / "state.json")
    comparisons = []
    for event in state["events"]:
        variants = event.get("result", {}).get("variants", {})
        control = variants.get("app_b_control", {}).get("final_plan")
        if control is None:
            continue
        day = control["freeze"]["market_date"]
        records = [row for row in app_report.get("final_plans", []) if row["trade_date"] == day]
        if not records:
            comparisons.append({"trade_date":day,"status":"app_final_plan_unproved",
                "control_sha256":control["receipt_sha256"],"research_event_sha256":event["event_sha256"]})
        for record in records:
            comparisons.append({"trade_date":day,"status":"compared","app_run_id":record["run_id"],
                "app_receipt_path":record["source_path"],"app_receipt_sha256":record["source_sha256"],
                "research_event_sha256":event["event_sha256"],
                **compare_final_plans(record["final_plan"],control)})
    return comparisons
