#!/usr/bin/env python3
"""Run the isolated native-Founder/Book-B live morning seam.

This command starts independently of ``auto_daily.sh`` and uses only the
native Founder App.  It waits only for the dated deterministic freeze, then
requests a bounded independently reviewed judgment before advancing immutable
plans through the durable broker execution module.  It
never initializes OpenCLI or waits for/writes a simulated fill.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_live_morning import (  # noqa: E402
    BookBLiveMorningConfig,
    load_book_b_live_capital_basis,
    reconcile_prior_day_canary_unknowns,
    run_book_b_live_morning,
    write_book_b_live_morning_receipt,
)
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.trading_runner import build_foundersc_native_execution  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.live.live_decision_support import calendar_provider, digest, read_policy  # noqa: E402
from wait_for_morning_freeze import wait_for_morning_freeze  # noqa: E402


def _china_date() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _wait_for_submit_window(target: datetime, *, heartbeat=None) -> None:
    """Keep the 09:20 task alive, but never wait across an unexpected window."""
    while True:
        current = datetime.now(target.tzinfo or ZoneInfo("Asia/Shanghai"))
        remaining = (target - current).total_seconds()
        if remaining <= 0:
            return
        if remaining > 15 * 60:
            raise RuntimeError("LIVE_SUBMIT_WINDOW_TOO_FAR")
        if heartbeat is not None:
            heartbeat()
        time.sleep(min(30.0, remaining))


def _passguard_evidence() -> dict:
    """State the unproven native-control boundary without reading its password."""
    return {
        "status": "pending",
        "trade_password_keychain_read": False,
        "unattended_recovery_proven": False,
        "policy": "fail_closed_if_prompted",
    }


def _market_observed_at(value: object, trade_date: str) -> str:
    text = str(value or "").strip()
    for fmt in ("%H:%M:%S:%f", "%H:%M:%S", "%H%M%S"):
        try:
            clock = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        return datetime.combine(
            date.fromisoformat(trade_date),
            clock,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ).isoformat()
    raise RuntimeError("LIVE_MARKET_GUARD_TIMESTAMP_UNPROVEN")


def _fresh_market_guard(client: XiaocaoClient, row: dict, trade_date: str) -> dict:
    code = str(row.get("code") or "")
    payload = client.second_line_detail_info(code)
    detail = payload.get(code) if isinstance(payload, dict) else None
    if not isinstance(detail, dict) or str(detail.get("code") or "") != code:
        raise RuntimeError("LIVE_MARKET_GUARD_CODE_UNPROVEN")
    raw_date = str(detail.get("tradeDate") or "")
    observed_date = (
        f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        if len(raw_date) >= 8 and raw_date[:8].isdigit()
        else raw_date[:10]
    )
    if observed_date != trade_date:
        raise RuntimeError("LIVE_MARKET_GUARD_DATE_MISMATCH")
    return {
        "market_guard_required": True,
        "market_guard_status": detail.get("tradeStatus"),
        "market_price": detail.get("trade"),
        "down_price": detail.get("downPrice"),
        "market_observed_at": _market_observed_at(
            detail.get("tradeTimestamp"), trade_date
        ),
    }


def _write_review_immutable(path: Path, payload: dict) -> None:
    """Publish complete JSON atomically without replacing a prior artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".review-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError("LIVE_REVIEW_ARTIFACT_IMMUTABILITY_VIOLATION")
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _review_rendezvous(request: dict, *, now=None, sleep=None, monotonic=None,
                       poll_seconds: float = 1.0) -> dict:
    """Expose one read-only request and wait for independently published policy.

    The parent performs full-source reasoning/review while this process waits.
    This consumer never invokes a model, publishes a decision, or touches keys.
    Both the wall-clock entry deadline and a monotonic 120-second cap apply.
    """
    now = now or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")))
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    started = monotonic()
    payload = dict(request)
    requested = datetime.fromisoformat(payload["requested_at"])
    entry_deadline = datetime.fromisoformat(payload["entry_deadline"])
    if requested.utcoffset() is None or entry_deadline.utcoffset() is None:
        raise ValueError("LIVE_REVIEW_AWARE_TIME_REQUIRED")
    budget = float(payload["max_wait_seconds"])
    if not math.isfinite(budget) or budget < 0 or not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise ValueError("LIVE_REVIEW_WAIT_BUDGET_INVALID")
    budget = min(120.0, budget)
    deadline = min(entry_deadline, requested + timedelta(seconds=budget))
    payload["max_wait_seconds"] = budget
    payload["freeze_path"] = str(Path(payload["freeze_path"]).resolve())
    payload["policy_root"] = str(Path(payload["policy_root"]).resolve())
    identifier = digest(payload)
    root = Path(payload["policy_root"]).parent / "context" / "live_review_requests"
    request_path = root / f"{identifier}.request.json"
    receipt_path = root / f"{identifier}.receipt.json"
    artifact = {**payload, "request_id": identifier, "request_sha256": identifier}
    _write_review_immutable(request_path, artifact)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if (receipt_path.is_symlink() or receipt.get("receipt_sha256") != digest(body)
                or receipt.get("request_id") != identifier):
            raise ValueError("LIVE_REVIEW_RECEIPT_BINDING_MISMATCH")
        return receipt
    print(json.dumps({"event": "book_b_live_review_requested", "request_id": identifier,
                      "request_sha256": identifier, "request_path": str(request_path),
                      "receipt_path": str(receipt_path), "request": artifact},
                     ensure_ascii=False, sort_keys=True), flush=True)
    latest: dict = {}
    status, reason = "timed_out", "LIVE_REVIEW_TIMEOUT_NEUTRAL_FALLBACK"
    while True:
        current = now()
        remaining = min(budget - (monotonic() - started), (deadline - current).total_seconds())
        if remaining <= 0:
            break
        latest = read_policy(Path(payload["policy_root"]), current)
        if monotonic() - started >= budget or now() >= deadline:
            break
        if latest.get("status") == "blocked":
            status, reason = "blocked", str(latest["reason"])
            break
        if latest.get("status") == "validated":
            as_of = datetime.fromisoformat(latest["record"]["decision"]["as_of"].replace("Z", "+00:00"))
            if as_of >= requested:
                status, reason = "validated", "LIVE_REVIEW_NEW_VALIDATED_POLICY"
                break
        sleep(min(1.0, poll_seconds, remaining))
    receipt = {
        "schema_version": "book-b-live-review-receipt.v1", "request_id": identifier,
        "request_sha256": identifier, "request_path": str(request_path), "receipt_path": str(receipt_path),
        "requested_at": requested.isoformat(), "completed_at": now().isoformat(),
        "entry_deadline": entry_deadline.isoformat(), "max_wait_seconds": budget,
        "waited_seconds": max(0.0, monotonic() - started), "status": status, "reason": reason,
        "supporting_health": "healthy" if status == "validated" else "degraded",
        "fallback": "neutral" if status == "timed_out" else None,
        "last_policy_status": latest.get("status"), "decision_id": latest.get("decision_id"),
        "decision_sha256": latest.get("decision_sha256"),
    }
    receipt["receipt_sha256"] = digest(receipt)
    _write_review_immutable(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument(
        "--freeze",
        default="output/live/book_b_live_freeze_{date}.jsonl",
        help="Immutable dated producer freeze; {date} is expanded",
    )
    parser.add_argument(
        "--allocation-facts",
        default="output/live/book_b_live_allocation_facts_{date}.json",
        help="Broker-sourced allocation facts; {date} is expanded",
    )
    parser.add_argument("--state-dir", default="output/live/book_b_live_execution")
    parser.add_argument("--policy-root", default="output/live/kol_policy/decisions")
    parser.add_argument(
        "--route",
        choices=("native-app",),
        default="native-app",
        help="Native Founder App only; OpenCLI trading/view is sunset",
    )
    parser.add_argument("--freeze-wait-seconds", type=float, default=600.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    trade_date = _china_date() if args.date == "today" else args.date
    freeze_path = Path(str(args.freeze).format(date=trade_date))
    allocation_path = Path(str(args.allocation_facts).format(date=trade_date))
    capital_runtime = KeychainCapitalRuntime()
    capital_receipt = capital_runtime.preflight()
    if capital_receipt["status"] != "ready":
        print(json.dumps({
            "trade_date": trade_date,
            "status": "blocked",
            "reason": "LIVE_CAPITAL_RUNTIME_NOT_READY",
            "capital_runtime": capital_receipt,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    keychain = FounderscKeychainPreflight()
    keychain_receipt = keychain.run(read_trade_secret=True)
    required_keychain_fields = (
        "trade_item_present",
        "trade_account_present",
        "trade_secret_readable",
        "trade_secret_nonempty",
    )
    keychain_error = "FOUNDER_NATIVE_TRADE_KEYCHAIN_NOT_READY"
    if not all(keychain_receipt.get(key) is True for key in required_keychain_fields):
        raise RuntimeError(keychain_error)
    trade_account_fingerprint = keychain.trade_account_fingerprint()
    if not trade_account_fingerprint:
        raise RuntimeError("FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING")
    execution, broker = build_foundersc_native_execution(
        args.state_dir,
        expected_fund_account_fingerprint=trade_account_fingerprint,
        safety_env_provider=capital_runtime.safety_env,
    )
    prior_reconciliations: tuple[dict, ...] = ()
    api_settings = load_settings(None)
    market_client = XiaocaoClient(
        base_url=api_settings.base_url,
        timeout=api_settings.timeout,
        retries=api_settings.retries,
        cache=None,
    )

    def read_allocation_facts() -> dict:
        nonlocal prior_reconciliations
        # The core reconciles open ordinary intents before this callback.
        prior_reconciliations = reconcile_prior_day_canary_unknowns(
            Path(args.state_dir),
            trade_date=trade_date,
            execute=lambda plan: execution.execute(plan, broker),
        )
        basis = load_book_b_live_capital_basis(Path(args.state_dir))
        allocation_kwargs = {
            "trade_date": trade_date,
            "logical_account_id": "primary",
            "settled_nav": basis.settled_nav,
            "current_open_exposure": basis.current_open_exposure,
            "capital_basis_source": basis.source,
            "expected_fund_account_fingerprint": trade_account_fingerprint,
        }
        allocation_kwargs["capital_basis_receipt_sha256"] = basis.receipt_sha256
        return broker.read_live_allocation_facts(
            **allocation_kwargs,
        )

    def preflight() -> dict:
        broker.ensure_login()
        native_receipt = broker.ensure_native_ready(
            require_order_capability=True,
            unlock_once=True,
        )
        environment_receipt = broker.ensure_environment(
            target="live",
            expected_current="any",
            logical_account_id="primary",
        )
        return {
            **environment_receipt,
            "website_authentication": {
                "status": "not_used",
                "route": "native-app",
                "reason": "OpenCLI trading/view is sunset",
            },
            "passguard": {
                **_passguard_evidence(),
                "status": "native_trade_ready",
                "trade_password_keychain_read": True,
                "unattended_recovery_proven": True,
                "single_attempt_unlock_available": True,
            },
            "native_order_surface": native_receipt,
        }

    def restore_environment() -> dict:
        return {
            "status": "native_environment_restore_not_applicable",
            "environment": "not_applicable",
            "route": "native-app",
        }

    def live_heartbeat() -> dict:
        return broker.ensure_environment(
            target="live",
            expected_current="live",
            logical_account_id="primary",
        )

    config = BookBLiveMorningConfig(
        trade_date=trade_date,
        freeze_path=freeze_path,
        allocation_facts_path=allocation_path,
        state_dir=Path(args.state_dir),
        logical_account_id="primary",
        policy_root=Path(args.policy_root),
    )
    receipt = run_book_b_live_morning(
        config,
        preflight=preflight,
        restore_environment=restore_environment,
        read_allocation_facts=read_allocation_facts,
        refresh_market_guard=lambda row: _fresh_market_guard(
            market_client, row, trade_date
        ),
        wait_for_dated_freeze=lambda: wait_for_morning_freeze(
            date=trade_date,
            live_dir=freeze_path.parent,
            timeout_sec=args.freeze_wait_seconds,
            poll_sec=args.poll_seconds,
            snapshot_path=freeze_path,
        ),
        prepare_only=lambda plan: broker.prepare_readonly(
            plan,
            expected_fund_account_fingerprint=trade_account_fingerprint,
        ),
        wait_for_submit_window=lambda target: _wait_for_submit_window(
            target,
            heartbeat=live_heartbeat,
        ),
        wait_for_reconcile=lambda: time.sleep(1.0),
        execute=lambda plan: execution.execute(plan, broker),
        trading_dates_provider=calendar_provider(market_client),
        account_snapshot_provider=lambda: broker.read_live_account_snapshot(
            trade_date=trade_date, logical_account_id="primary",
            expected_fund_account_fingerprint=trade_account_fingerprint,
        ),
        review_rendezvous=lambda request: _review_rendezvous(request, poll_seconds=args.poll_seconds),
    )
    receipt = replace(
        receipt,
        capital_runtime=capital_receipt,
        open_plan_reconciliations=receipt.open_plan_reconciliations,
        prior_reconciliations=prior_reconciliations,
    )
    write_book_b_live_morning_receipt(config, receipt)
    payload = receipt.as_dict()
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.status in {"completed", "no_action", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
