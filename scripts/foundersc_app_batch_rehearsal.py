#!/usr/bin/env python3
"""Bounded, resumable APP simulation batch; submit 2–5, then cancel by exact ID.

Always reuse the same run ID after interruption. Once cleanup starts, a replay
can only reconcile/cancel existing claims, never start an untouched intent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.foundersc_app_rehearsal import read_rehearsal_plan, write_once
from xiaocao.live.capital_keychain import KeychainCapitalRuntime
from xiaocao.live.foundersc_native_ax import FounderscNativeAXClient, source_digest
from xiaocao.live.foundersc_native_broker import FounderscNativeAXBrokerAdapter
from xiaocao.live.trading_execution import (
    BookBOwnershipEvidence, ExecutionReceipt, ExecutionState, ExecutionStore, TradePlan,
    TradingExecution, account_writer_lock,
)

TERMINAL = {ExecutionState.CANCELLED, ExecutionState.FILLED,
            ExecutionState.REJECTED, ExecutionState.SKIPPED}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def create_batch(directory, *, run_id, fingerprint, code, prices, snapshot, shares=100):
    manifest = directory / "batch.json"
    if manifest.exists():
        batch = json.loads(manifest.read_text())
        plans = [read_rehearsal_plan(item) for item in batch["intents"]]
        baseline = batch["baseline"]
        if (batch.get("schema_version") != 1 or batch.get("run_id") != run_id
                or batch.get("fingerprint") != fingerprint
                or batch.get("baseline_hash") != _hash(baseline)
                or [p.limit_price for p in plans] != prices
                or any(p.code != code or p.shares != shares for p in plans)
                or len({p.plan_id for p in plans}) != len(prices)
                or any(item["fingerprint"] != fingerprint or
                       item["rehearsal_budget"]["account_snapshot_sha256"] != baseline["snapshot_sha256"]
                       for item in batch["intents"])
                or batch.get("total_notional") != sum(p.notional for p in plans)):
            raise ValueError("REHEARSAL_BATCH_IMMUTABLE")
        return batch, plans
    baseline = snapshot()
    total = sum(price * shares for price in prices)
    if not 0 < total <= min(1000, baseline["broker_summary"]["available_cash"]):
        raise ValueError("REHEARSAL_BATCH_BUDGET")
    now = datetime.now(timezone.utc)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    intents = []
    for index, price in enumerate(prices):
        budget = {"purpose": "user_authorized_app_simulation_canary", "shares": shares,
                  "limit_price": price, "code": code,
                  "account_snapshot_sha256": baseline["snapshot_sha256"]}
        plan = TradePlan(
            plan_id=f"native-rehearsal:{run_id}:{index}", strategy_run_id=run_id,
            snapshot_ref=str(manifest), strategy_sha=sha,
            trade_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            book="B", logical_account_id="primary", environment="live", code=code,
            name="APP仿真批量工程试单", side="BUY", shares=shares,
            limit_price=price, basket_price=price, market_guard_status="ok",
            market_guard_required=False, price_rule="explicit_app_simulation_canary",
            created_at=now, recovery_deadline=now + timedelta(minutes=20),
            allocation_proof_hash=_hash(budget))
        intents.append({"schema_version": 1, "plan_id": plan.plan_id,
                        "plan": plan.canonical_payload(), "plan_hash": plan.plan_hash,
                        "fingerprint": fingerprint, "rehearsal_budget": budget,
                        "strategy_eligibility_claimed": False})
    batch = {"schema_version": 1, "run_id": run_id, "fingerprint": fingerprint,
             "baseline": baseline, "baseline_hash": _hash(baseline),
             "total_notional": total, "intents": intents, "source_digest": source_digest()}
    write_once(manifest, batch)
    return batch, [read_rehearsal_plan(item) for item in intents]


def run_batch(execution, plans, *, directory, snapshot, cleanup_only=False):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    seal = directory / "cleanup-started.json"
    outcomes, errors, stages = {}, [], []
    def stage(name, plan, action):
        started = time.monotonic()
        try:
            result = action()
            outcomes[plan.plan_id] = result.as_dict()
            return result
        finally:
            stages.append({"stage": name, "plan_id": plan.plan_id,
                           "seconds": round(time.monotonic() - started, 4)})
    try:
        if not cleanup_only and not seal.exists():
            for plan in plans:
                receipt = stage("submit_or_reconcile", plan, lambda: execution.execute(plan))
                if receipt.state not in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL}:
                    break  # No new orders after the first unexpected outcome.
            write_once(directory / (stamp + "-outstanding.json"), snapshot())
    except Exception as exc:
        errors.append({"phase": "advance", "type": type(exc).__name__})
    finally:
        if not seal.exists():
            write_once(seal, {"started_at": stamp})
        for plan in reversed(plans):
            try:
                with account_writer_lock(execution.account_lock_dir, plan.logical_account_id):
                    prior = execution.store.current(plan.plan_id)
                    if prior is None:
                        prior = ExecutionReceipt(plan.plan_id, plan.plan_hash,
                            ExecutionState.PLANNED, remaining_shares=plan.shares)
                    if (prior.plan_hash == plan.plan_hash
                            and prior.state in {ExecutionState.PLANNED, ExecutionState.VALIDATED,
                                                ExecutionState.PREPARED}
                            and not any((prior.submit_claim_id, prior.cancel_claim_id,
                                prior.broker_order_id, prior.filled_shares,
                                prior.submit_chain_uncertain, prior.cancel_chain_uncertain))):
                        prior = execution.store.append(plan=plan, receipt=replace(prior,
                            state=ExecutionState.SKIPPED, reason="REHEARSAL_BATCH_ABORTED_UNSUBMITTED",
                            next_action="stop"), kind="rehearsal_unsubmitted_closed")
                if prior.state in TERMINAL:
                    outcomes[plan.plan_id] = prior.as_dict()
                    continue
                if not prior.submit_claim_id:
                    # An unclaimed failure is evidence, never a new submit in cleanup.
                    outcomes[plan.plan_id] = prior.as_dict()
                    continue
                receipt = prior
                if receipt.state not in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL}:
                    receipt = stage("reconcile", plan, lambda: execution.execute(plan))
                # cancel() itself proves the current exact row and reconciles
                # fills; do not duplicate a full read for an already-known ID.
                if receipt.state in {ExecutionState.ACKNOWLEDGED, ExecutionState.PARTIAL}:
                    stage("cancel", plan, lambda: execution.cancel(plan))
            except Exception as exc:
                errors.append({"phase": "cleanup", "plan_id": plan.plan_id,
                               "type": type(exc).__name__})
    after = None
    try:
        after = snapshot()
        write_once(directory / (stamp + "-after.json"), after)
    except Exception as exc:
        errors.append({"phase": "final_snapshot", "type": type(exc).__name__})
    result = {"outcomes": outcomes, "errors": errors, "stages": stages,
              "all_orders_terminal": all(
                  execution.store.current(p.plan_id) is not None and
                  execution.store.current(p.plan_id).state in TERMINAL for p in plans),
              "acceptance_complete": all(
                  execution.store.current(p.plan_id) is not None and
                  execution.store.current(p.plan_id).broker_order_id and
                  execution.store.current(p.plan_id).state in {ExecutionState.CANCELLED, ExecutionState.FILLED}
                  for p in plans),
              "final_snapshot_proven": after is not None}
    write_once(directory / (stamp + "-result.json"), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("advance", "cleanup"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--code", default="512010.XSHG")
    parser.add_argument("--shares", type=int, choices=(100, 200, 300), default=100)
    parser.add_argument("--prices", required=True, type=float, nargs="+")
    parser.add_argument("--acknowledge-app-server-simulation", action="store_true")
    args = parser.parse_args()
    if (not args.acknowledge_app_server_simulation
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", args.run_id)
            or not re.fullmatch(r"[0-9]{6}\.(XSHG|XSHE)", args.code)
            or not re.fullmatch(r"\d{3}\*{6}\d{3}", args.fingerprint)
            or not 2 <= len(args.prices) <= 5 or len(set(args.prices)) != len(args.prices)
            or any(not 0 < price <= 10 or round(price, 2) != price for price in args.prices)):
        parser.error("require APP simulation acknowledgement and 2–5 distinct valid limit prices")
    directory = ROOT / "output/research/foundersc_app_rehearsal" / args.run_id
    native = FounderscNativeAXClient()
    broker = FounderscNativeAXBrokerAdapter(native=native,
        expected_fund_account_fingerprint=args.fingerprint)
    def snapshot():
        now = datetime.now(timezone.utc)
        return broker.read_live_account_snapshot(
            trade_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            expected_fund_account_fingerprint=args.fingerprint, now=now)
    # Batch ownership -> account writer -> APP session is the fixed lock order.
    with account_writer_lock(directory / "batch-lock", "primary"):
        if args.action == "cleanup" and not (directory / "batch.json").exists():
            raise ValueError("REHEARSAL_BATCH_MISSING")
        lock_root = ROOT / "output/live/book_b_live_execution/account_writer_locks"
        with account_writer_lock(lock_root, "primary"):
            batch, plans = create_batch(directory, run_id=args.run_id,
                fingerprint=args.fingerprint, code=args.code, prices=args.prices, snapshot=snapshot, shares=args.shares)
        execution = TradingExecution(store=ExecutionStore(directory / "events.jsonl"), broker=broker,
            ledger=BookBOwnershipEvidence(directory / "ownership.jsonl"),
            safety_env_provider=KeychainCapitalRuntime().safety_env,
            auth_path=ROOT / "output/live/live_authorization.json",
            audit_path=directory / "safety-audit.jsonl", account_lock_dir=lock_root,
            notifier=lambda *_args, **_kwargs: None)
        result = run_batch(execution, plans, directory=directory, snapshot=snapshot,
                           cleanup_only=args.action == "cleanup")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        write_once(directory / (stamp + "-timings.json"), {"commands": native.command_timings})
    print(json.dumps({"run_id": args.run_id, **result}, ensure_ascii=False, default=str))
    complete = result["all_orders_terminal"] if args.action == "cleanup" else result["acceptance_complete"]
    return 0 if complete and result["final_snapshot_proven"] and not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
