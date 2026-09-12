#!/usr/bin/env python3
"""Explicit APP-server simulation rehearsal, isolated from strategy ledgers.

This is the user-authorized engineering canary, not the morning producer.
It uses the existing manual-limit execution seam and real runtime authorization,
without claiming a trading-day quote, frozen candidate, or strategy allocation.
Always reuse a run ID after interruption. Only advance can start an order;
reconcile never prepares or submits an unclaimed plan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.capital_keychain import KeychainCapitalRuntime
from xiaocao.live.app_test_window import app_test_only
from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient, source_digest
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from xiaocao.live.trading_execution import (
    BookBOwnershipEvidence, ExecutionState, ExecutionStore, TradePlan, TradingExecution,
    account_writer_lock,
)


def write_once(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2, default=str, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Publish a complete file atomically, without overwriting another run.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_rehearsal_plan(capsule: dict) -> TradePlan:
    raw = dict(capsule["plan"])
    for key, value in raw.items():
        if value is not None and (key.endswith("_at") or key in {"recovery_deadline", "submit_not_before"}):
            raw[key] = datetime.fromisoformat(value)
    plan = TradePlan(**raw)
    budget = capsule.get("rehearsal_budget", {})
    budget_hash = hashlib.sha256(json.dumps(budget, sort_keys=True).encode()).hexdigest()
    if (capsule.get("schema_version") != 1 or capsule.get("plan_id") != plan.plan_id
            or not plan.plan_id.startswith("native-rehearsal:")
            or capsule.get("plan_hash") != plan.plan_hash or plan.validation_error()
            or plan.logical_account_id != "primary" or plan.environment != "live"
            or plan.shares not in {100, 200, 300, 400} or not 0 < plan.notional <= 1000
            or plan.side != "BUY" or plan.price_rule != "explicit_app_simulation_canary"
            or plan.allocation_proof_hash != budget_hash
            or budget.get("purpose") != "user_authorized_app_simulation_canary"
            or (budget.get("code"), budget.get("shares"), budget.get("limit_price"))
            != (plan.code, plan.shares, plan.limit_price)
            or capsule.get("strategy_eligibility_claimed") is not False):
        raise ValueError("REHEARSAL_INTENT_INVALID")
    return plan


def advance_cycle(execution, plan, *, reconcile_only=False):
    current = execution.store.current(plan.plan_id)
    if reconcile_only and (current is None or current.state in {
        ExecutionState.PLANNED, ExecutionState.VALIDATED, ExecutionState.PREPARED,
    }):
        raise ValueError("REHEARSAL_HAS_NO_SUBMIT_TO_RECONCILE")
    receipt = execution.execute(plan)
    # Cancellation has its own durable claim; a restart cannot replay it.
    if receipt.state in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL}:
        receipt = execution.cancel(plan)
    return receipt


@app_test_only
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "prepare", "advance", "reconcile"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--code", default="512010.XSHG")
    parser.add_argument("--price", type=float, default=0.35)
    parser.add_argument("--acknowledge-app-server-simulation", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_app_server_simulation:
        parser.error("this manual rehearsal requires the identified APP-server simulation")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", args.run_id):
        parser.error("invalid run ID")
    if not re.fullmatch(r"[0-9]{6}\.(XSHG|XSHE)", args.code):
        parser.error("invalid security code")
    if not 0 < args.price <= 10 or round(args.price, 2) != args.price:
        parser.error("100-share rehearsal requires a cent-aligned price and notional <= 1000")
    directory = ROOT / "output/research/foundersc_app_rehearsal" / args.run_id
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    native = FounderscNativeAXClient()
    broker = FounderscNativeAXBrokerAdapter(
        native=native, expected_fund_account_fingerprint=args.fingerprint,
    )
    current = datetime.now(timezone.utc)
    def snapshot():
        now = datetime.now(timezone.utc)
        return broker.read_live_account_snapshot(
            trade_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            expected_fund_account_fingerprint=args.fingerprint, now=now,
        )
    plan_path = directory / "intent.json"
    if args.action == "snapshot":
        result = snapshot()
    else:
        # Serialize against other tests and the production execution port.
        lock_root = ROOT / "output/live/book_b_live_execution/account_writer_locks"
        with account_writer_lock(lock_root, "primary"):
            if plan_path.exists():
                capsule = json.loads(plan_path.read_text())
                plan = read_rehearsal_plan(capsule)
                if (plan.code, plan.limit_price, capsule["fingerprint"]) != (args.code, args.price, args.fingerprint):
                    raise ValueError("REHEARSAL_INTENT_IMMUTABLE")
            else:
                if args.action == "reconcile":
                    raise ValueError("REHEARSAL_INTENT_MISSING")
                baseline = snapshot()
                if baseline["broker_summary"]["available_cash"] < args.price * 100:
                    raise ValueError("REHEARSAL_CASH_INSUFFICIENT")
                baseline_path = directory / "baseline.json"
                if baseline_path.exists():
                    # A crash between baseline and intent publication made no
                    # order. Preserve that baseline and require its same account/day.
                    prior = json.loads(baseline_path.read_text())
                    if (prior.get("trade_date"), prior.get("fund_account_binding_sha256")) != (
                        baseline["trade_date"], baseline["fund_account_binding_sha256"]
                    ):
                        raise ValueError("REHEARSAL_BASELINE_BINDING_MISMATCH")
                    baseline = prior
                else:
                    write_once(baseline_path, baseline)
                budget = {"purpose": "user_authorized_app_simulation_canary", "shares": 100,
                          "limit_price": args.price, "code": args.code,
                          "account_snapshot_sha256": baseline["snapshot_sha256"]}
                budget_hash = hashlib.sha256(json.dumps(budget, sort_keys=True).encode()).hexdigest()
                plan = TradePlan(
                    plan_id="native-rehearsal:" + args.run_id, strategy_run_id=args.run_id,
                    snapshot_ref=str(directory / "baseline.json"),
                    strategy_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    trade_date=current.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                    book="B", logical_account_id="primary", environment="live",
                    code=args.code, name="APP仿真工程试单", side="BUY", shares=100,
                    limit_price=args.price, basket_price=args.price, market_guard_status="ok",
                    market_guard_required=False, price_rule="explicit_app_simulation_canary",
                    created_at=current, recovery_deadline=current + timedelta(minutes=20),
                    allocation_proof_hash=budget_hash,
                )
                write_once(plan_path, {"schema_version": 1, "plan_id": plan.plan_id,
                           "plan": plan.canonical_payload(), "plan_hash": plan.plan_hash,
                           "fingerprint": args.fingerprint, "rehearsal_budget": budget,
                           "source_digest": source_digest(), "strategy_eligibility_claimed": False})
        store = ExecutionStore(directory / "events.jsonl")
        if args.action == "prepare":
            with account_writer_lock(lock_root, "primary"):
                if store.current(plan.plan_id) is not None:
                    raise ValueError("REHEARSAL_PREPARE_FORBIDDEN_AFTER_EXECUTION_STARTED")
                result = broker.prepare_readonly(plan, expected_fund_account_fingerprint=args.fingerprint).__dict__
        else:
            execution = TradingExecution(
                store=store, broker=broker, ledger=BookBOwnershipEvidence(directory / "ownership.jsonl"),
                safety_env_provider=KeychainCapitalRuntime().safety_env,
                auth_path=ROOT / "output/live/live_authorization.json",
                audit_path=directory / "safety-audit.jsonl", account_lock_dir=lock_root,
                notifier=lambda *_args, **_kwargs: None,
            )
            result = advance_cycle(execution, plan, reconcile_only=args.action == "reconcile").as_dict()
            write_once(directory / (stamp + "-execution.json"), result)
            # Always preserve a failed final read independently of the durable execution result.
            after = snapshot()
            write_once(directory / (stamp + "-after.json"), after)
    write_once(directory / (stamp + "-" + args.action + ".json"), result)
    print(json.dumps({"run_id": args.run_id, "action": args.action, "result": result}, ensure_ascii=False, default=str))
    if args.action in {"advance", "reconcile"}:
        return 0 if result["state"] in {"cancelled", "filled", "rejected", "skipped"} else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
