#!/usr/bin/env python3
"""Run the isolated Founder/Book-B live morning seam.

This command starts independently of ``auto_daily.sh``.  It switches only the
Founder environment selector to live, waits only for the dated deterministic
freeze, then advances immutable plans through the durable broker execution
module.  It never waits for or writes a simulated fill.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_live_morning import (  # noqa: E402
    BookBLiveMorningConfig,
    load_book_b_live_capital_basis,
    reconcile_open_book_b_plans,
    reconcile_prior_day_canary_unknowns,
    run_book_b_live_morning,
)
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.foundersc_opencli import (  # noqa: E402
    release_foundersc_opencli_site_session,
    resolve_connected_opencli_profile,
)
from xiaocao.live.trading_runner import (  # noqa: E402
    build_foundersc_execution,
    build_foundersc_native_execution,
)
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
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


def _bounded_no_order_retry(action, *, attempts: int = 3):
    """Retry only login/readback/environment actions that cannot place an order."""
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            return action()
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.0)
    assert last_error is not None
    raise last_error


def _website_authentication_evidence(login_receipt: dict) -> dict:
    """Keep only credential-free proof fields from the Founder login receipt."""
    fields = (
        "status",
        "status_reason",
        "template_name",
        "template_version",
        "authentication_path",
        "initial_auth_state",
        "keychain_login_read",
        "login_form_binding_proven",
        "login_submit_click_count",
        "post_auth_readback_proven",
        "session_reuse_proven",
        "fresh_login_proven",
    )
    return {key: login_receipt.get(key) for key in fields}


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
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--route",
        choices=(
            "native-app",
            "package-limit",
            "manual-limit",
            "opening-auction",
            "timed-order",
        ),
        default="native-app",
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
    if args.route == "native-app":
        profile = None
        keychain_receipt = keychain.run(read_trade_secret=True)
        required_keychain_fields = (
            "trade_item_present",
            "trade_account_present",
            "trade_secret_readable",
            "trade_secret_nonempty",
        )
        keychain_error = "FOUNDER_NATIVE_TRADE_KEYCHAIN_NOT_READY"
    else:
        profile = resolve_connected_opencli_profile(args.profile)
        release_foundersc_opencli_site_session(profile)
        keychain_receipt = keychain.run(read_login_secret=True)
        required_keychain_fields = (
            "login_item_present",
            "login_secret_readable",
            "login_secret_nonempty",
            "trade_item_present",
            "trade_account_present",
        )
        keychain_error = "FOUNDER_LOGIN_KEYCHAIN_OR_TRADE_METADATA_NOT_READY"
    if not all(keychain_receipt.get(key) is True for key in required_keychain_fields):
        raise RuntimeError(keychain_error)
    trade_account_fingerprint = keychain.trade_account_fingerprint()
    if not trade_account_fingerprint:
        raise RuntimeError("FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING")
    if args.route == "native-app":
        execution, broker = build_foundersc_native_execution(
            args.state_dir,
            expected_fund_account_fingerprint=trade_account_fingerprint,
            safety_env_provider=capital_runtime.safety_env,
        )
    else:
        execution, broker = build_foundersc_execution(
            args.state_dir,
            profile=profile,
            route=args.route,
            expected_fund_account_fingerprint=trade_account_fingerprint,
            safety_env_provider=capital_runtime.safety_env,
        )
    prior_reconciliations: tuple[dict, ...] = ()
    open_plan_reconciliations: tuple[dict, ...] = ()
    api_settings = load_settings(None)
    market_client = XiaocaoClient(
        base_url=api_settings.base_url,
        timeout=api_settings.timeout,
        retries=api_settings.retries,
        cache=None,
    )

    def read_allocation_facts() -> dict:
        nonlocal open_plan_reconciliations, prior_reconciliations
        open_plan_reconciliations = reconcile_open_book_b_plans(
            Path(args.state_dir),
            trade_date=trade_date,
            execute=lambda plan: execution.execute(plan, broker),
        )
        prior_reconciliations = reconcile_prior_day_canary_unknowns(
            Path(args.state_dir),
            trade_date=trade_date,
            execute=lambda plan: execution.execute(plan, broker),
        )
        basis = load_book_b_live_capital_basis(Path(args.state_dir))
        return broker.read_live_allocation_facts(
            trade_date=trade_date,
            logical_account_id="primary",
            settled_nav=basis.settled_nav,
            current_open_exposure=basis.current_open_exposure,
            capital_basis_source=basis.source,
            expected_fund_account_fingerprint=(
                trade_account_fingerprint
            ),
        )

    def preflight() -> dict:
        native_receipt = None
        if args.route == "native-app":
            login_receipt = broker.ensure_login()
            native_receipt = broker.ensure_native_ready(
                require_order_capability=True,
                unlock_once=True,
            )
            environment_receipt = broker.ensure_environment(
                target="live",
                expected_current="any",
                logical_account_id="primary",
            )
        else:
            login_receipt = _bounded_no_order_retry(broker.ensure_login)
            environment_receipt = _bounded_no_order_retry(
                lambda: broker.ensure_environment(
                    target="live",
                    expected_current="any",
                    logical_account_id="primary",
                )
            )
        return {
            **environment_receipt,
            "website_authentication": (
                {
                    "status": "not_used",
                    "route": "native-app",
                    "reason": "Founder web/OpenCLI authentication is outside this route",
                }
                if args.route == "native-app"
                else _website_authentication_evidence(login_receipt)
            ),
            "passguard": (
                {
                    **_passguard_evidence(),
                    "status": "native_trade_ready",
                    "trade_password_keychain_read": True,
                    "unattended_recovery_proven": True,
                    "single_attempt_unlock_available": True,
                }
                if native_receipt is not None
                else _passguard_evidence()
            ),
            "native_order_surface": native_receipt,
        }

    if args.route == "native-app":
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
    else:
        def restore_environment() -> dict:
            return _bounded_no_order_retry(
                lambda: broker.ensure_environment(
                    target="mock",
                    expected_current="any",
                    logical_account_id="primary",
                )
            )

        def live_heartbeat() -> dict:
            return _bounded_no_order_retry(
                lambda: broker.ensure_environment(
                    target="live",
                    expected_current="live",
                    logical_account_id="primary",
                )
            )

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date=trade_date,
            freeze_path=freeze_path,
            allocation_facts_path=allocation_path,
            state_dir=Path(args.state_dir),
            logical_account_id="primary",
        ),
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
    )
    payload = receipt.as_dict()
    payload["capital_runtime"] = capital_receipt
    payload["open_plan_reconciliations"] = list(open_plan_reconciliations)
    payload["prior_reconciliations"] = list(prior_reconciliations)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.status in {"completed", "no_action", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
