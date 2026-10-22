#!/usr/bin/env python3
"""Advance isolated, forward-only Book-B research after production work."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
import re
import sqlite3
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
import live_monitor as monitor
from xiaocao.live.buy_guards import evaluate_buy_market_guard, _TRADING_STATUSES
from xiaocao.live.live_decision_support import calendar_provider, read_policy
from xiaocao.live.morning_bundle import acquire_bundle, read_consumed_rows
from xiaocao.live.book_b_capital import digest
from xiaocao.research.book_b_forward import CHINA, PROTOCOL, _read_state, _stamp, performance, transact, compare_app_control, morning_quote_codes
from xiaocao.utils.atomic_files import atomic_write


class CachedMarket:
    """Share identical reads within this checkpoint and rate-limit every miss."""
    def __init__(self, client):
        self.client, self.cache, self.last_call = client, {}, 0.

    def __getattr__(self, name):
        method = getattr(self.client,name)
        if not callable(method):
            return method
        def call(*args,**kwargs):
            key = digest({"method":name,"args":args,"kwargs":kwargs})
            if key not in self.cache:
                time.sleep(max(0.,.6-(time.monotonic()-self.last_call)))
                self.last_call = time.monotonic()
                self.cache[key] = method(*args,**kwargs)
            return self.cache[key]
        return call


def window_evidence(client, order: dict, now: datetime) -> dict:
    result = {"code":order["code"],"window_start":order["window_start"],"window_end":order["window_end"],
              "observed_at":now.isoformat(),"complete":False,"bars":[]}
    start,end = _stamp(order["window_start"]),_stamp(order["window_end"])
    if now <= end+timedelta(minutes=1):
        return result
    rows = client.minute_line(order["code"],"1min","bfq",trade_date=start.strftime("%Y%m%d"),count=241)
    result["request"] = {"source":"xiaocao_api","code":order["code"],"trade_date":start.date().isoformat()}
    result["raw_rows"] = rows
    if not isinstance(rows,list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            return result
        raw_code = str(row.get("code") or row.get("stockId") or "")
        raw_date = str(row.get("tradeDate") or "").replace("-", "")
        if raw_code != order["code"] or raw_date != start.strftime("%Y%m%d"):
            return result
        raw_time = str(row.get("tradeTime") or "").replace(":","")[:4]
        if len(raw_time)!=4 or not raw_time.isdigit():
            continue
        try:
            at = start.replace(hour=int(raw_time[:2]),minute=int(raw_time[2:]),second=0,microsecond=0)
        except ValueError:
            return result
        if not start <= at <= end:
            continue
        try:
            price,volume,amount = float(row["trade"]),float(row["vol"]),float(row["amt"])
            # Prove share units with contemporaneous notional, not an assumed lot conversion.
            if price<=0 or volume<=0 or not .9 <= amount/volume/price <= 1.1:
                return result
        except (KeyError,ValueError,TypeError,ZeroDivisionError):
            return result
        result["bars"].append({"at":at.isoformat(),"price":price,"volume_shares":volume})
    expected = {(start+timedelta(minutes=i)).isoformat() for i in range(PROTOCOL["window_minutes"])}
    result["complete"] = len(result["bars"])==len(expected) and {b["at"] for b in result["bars"]}==expected
    return result


def write_reports(root: Path, now: datetime) -> dict:
    research = root/"output/research/app_b_forward"
    report = performance(research, as_of=now)
    report["as_of"] = now.isoformat()
    result = {"status":"reported","path":str(research/"performance.json"),"authority":0}
    from xiaocao.research.app_b_lifecycle_report import build_lifecycle_report
    try:
        app = build_lifecycle_report(root/"output/live/book_b_live_execution")
        app["report_observed_at"] = now.isoformat()
        # Hash the report clock together with the exact economic evidence.
        app["receipt_sha256"] = digest({k:v for k,v in app.items() if k!="receipt_sha256"})
        result["app_lifecycle_status"] = "recorded"
    except (ValueError, OSError, sqlite3.Error) as exc:
        result["app_lifecycle_status"] = "unproved"
        result["app_lifecycle_failure"] = type(exc).__name__
        app = {"schema_version":"app-b-lifecycle-report.v1","authority":0,"status":"unproved",
               "report_observed_at":now.isoformat(),"reason":type(exc).__name__,"final_plans":[]}
        app["receipt_sha256"] = digest(app)
    atomic_write(research/"app_lifecycle.json",json.dumps(app,ensure_ascii=False,sort_keys=True).encode())
    report["app_plan_comparisons"] = compare_app_control(research,app)
    atomic_write(research/"performance.json",json.dumps(report,ensure_ascii=False,sort_keys=True).encode())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("morning","monitor","eod","report"),required=True)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--checkpoint-phase", choices=("opening", "sparse", "precheck", "closing"))
    args = parser.parse_args(argv)
    if (args.phase == "monitor") != bool(args.checkpoint_phase):
        parser.error("--checkpoint-phase is required only for --phase monitor")
    root = args.root.resolve()
    research = root/"output/research/app_b_forward"
    now = datetime.now(CHINA)
    today = now.date().isoformat()
    if args.phase=="report":
        print(json.dumps(write_reports(root,now),ensure_ascii=False,sort_keys=True))
        return 0
    client = CachedMarket(monitor._client())
    trading_dates = calendar_provider(client)(now)
    if today not in trading_dates:
        print(json.dumps({"status":"NON_TRADING_DAY","authority":0}))
        return 0
    state = _read_state(research/"state.json")
    if args.phase=="morning" and today in state["morning_dates"]:
        print(json.dumps({"status":"already_consumed","authority":0}))
        return 0
    if args.phase!="morning" and not state["morning_dates"]:
        print(json.dumps({"status":"not_started","authority":0,"reports":write_reports(root,now)}))
        return 0
    policy = read_policy(root/"output/live/kol_policy/decisions",now)
    inputs = {"trading_dates":[d for d in trading_dates if d >= (state["morning_dates"][0] if state["morning_dates"] else today)], "policy":policy,"marks":{},"statuses":{},"windows":{},"market_guards":{},
              "source_code_sha":os.environ.get("XIAOCAO_DAILY_SOURCE_REVISION") or subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
              "runtime_run_id":os.environ.get("XIAOCAO_DAILY_RUN_ID"), "checkpoint_phase":args.checkpoint_phase}
    codes = {lot["code"] for account in state["accounts"].values() for lot in account["lots"] if lot["shares"]>0}
    for account in state["accounts"].values():
        for order in account["orders"]:
            if order["status"] in {"pending","unknown"}:
                codes.add(order["code"])
                if order["order_id"] not in inputs["windows"]:
                    inputs["windows"][order["order_id"]] = window_evidence(client,order,now)
    if args.phase=="morning":
        freeze = acquire_bundle(root/"output/live",today,repair=False)
        if freeze.get("status")!="ready":
            raise ValueError("FORWARD_ORIGINAL_BUNDLE_UNAVAILABLE")
        rows = read_consumed_rows(freeze,today,live_dir=root/"output/live")
        inputs.update(rows=rows,freeze=freeze)
        codes.update(morning_quote_codes(rows, freeze, policy))
        # This is the existing Book-A performance sensor, read only.
        sys.path.insert(0,str(root/"kronos_screen/scripts"))
        from paper_record import _kill_switch_factor
        inputs["performance_factor"] = _kill_switch_factor()[0]
    for code in sorted(codes):
        detail = monitor._realtime_detail(client,code)
        stamp = monitor._detail_observed_at(detail,today)
        valid_day = monitor._detail_trade_date(detail)==today
        inputs["marks"][code] = {"price":detail.get("trade"),"observed_at":stamp.isoformat() if stamp else None,
                                  "status":"ok" if valid_day and (str(detail.get("tradeStatus") or "").lower() in _TRADING_STATUSES or re.fullmatch(r"t[0-9]+", str(detail.get("tradeStatus") or "").lower())) else "unproved",
                                  "source":detail}
        if args.phase=="morning":
            candidate = next((r for r in inputs["rows"] if r.get("code")==code),{})
            guard_row = {**candidate, "market_guard_required":True, "date":today,
                "market_guard_status":detail.get("tradeStatus"),"down_price":detail.get("downPrice"),
                "latest_price":detail.get("trade"),"market_observed_at":stamp.isoformat() if stamp and valid_day else None}
            allowed,reason,evidence = evaluate_buy_market_guard(guard_row,now=datetime.now(CHINA),
                require_authoritative=True,max_age_seconds=60,allow_opening_auction_quote=True)
            inputs["market_guards"][code] = {"allowed":allowed,"reason":reason,"evidence":evidence,
                "observed_at":stamp.isoformat() if stamp else None}
    if args.phase!="morning":
        market = monitor._market_sentiment_context(client)
        sentiment = monitor._load_stock_sentiment_map(today)
        snapshots = monitor._load_signal_snapshot_map()
        for variant,account in state["accounts"].items():
            inputs["statuses"][variant] = {}
            for lot in account["lots"]:
                if lot["shares"]<=0:
                    continue
                position = {**lot["context"],"book":"B","status":"open","code":lot["code"],
                    "entry_date":lot["entry_date"],"entry_price":lot["entry_price"],"shares":lot["shares"],
                    "profile":"v5","fee_rate":PROTOCOL["fee_rate"]}
                status = monitor._compute_status(client,position,today,book="B",market_context=market,
                    sentiment_map=sentiment,snapshot_map=snapshots,
                    kol_decision=policy if variant!="no_kol" else {"status":"neutral"})
                raw_status = str(status.get("market_guard_status") or "").lower()
                if raw_status in _TRADING_STATUSES or re.fullmatch(r"t[0-9]+",raw_status):
                    status["market_guard_status"] = "ok"
                inputs["statuses"][variant][lot["lot_id"]] = status
    # Persist actual acquisition completion; no model order starts before this instant.
    now = datetime.now(CHINA)
    current_policy = read_policy(root/"output/live/kol_policy/decisions",now)
    if args.phase == "morning" and any(policy.get(k) != current_policy.get(k)
            for k in ("status", "book", "runtime", "decision_sha256")):
        raise ValueError("FORWARD_POLICY_CHANGED_DURING_ACQUISITION")
    inputs["policy"] = current_policy
    result = transact(research,phase=args.phase,inputs=inputs,now=now)
    result["reports"] = write_reports(root,now)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
