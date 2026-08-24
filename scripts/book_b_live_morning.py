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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.book_b_live_morning import (  # noqa: E402
    BookBLiveMorningConfig,
    load_book_b_live_capital_basis,
    run_book_b_live_morning,
)
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.foundersc_opencli import (  # noqa: E402
    release_foundersc_opencli_site_session,
    resolve_connected_opencli_profile,
)
from xiaocao.live.trading_runner import build_foundersc_execution  # noqa: E402
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument("--freeze", default="output/live/signal_snapshots.jsonl")
    parser.add_argument(
        "--allocation-facts",
        default="output/live/book_b_live_allocation_facts_{date}.json",
        help="Broker-sourced allocation facts; {date} is expanded",
    )
    parser.add_argument("--state-dir", default="output/live/book_b_live_execution")
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--route",
        choices=("package-limit", "manual-limit", "opening-auction", "timed-order"),
        default="package-limit",
    )
    parser.add_argument("--freeze-wait-seconds", type=float, default=600.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    trade_date = _china_date() if args.date == "today" else args.date
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
    profile = resolve_connected_opencli_profile(args.profile)
    release_foundersc_opencli_site_session(profile)
    keychain = FounderscKeychainPreflight()
    keychain_receipt = keychain.run(read_login_secret=True)
    if not all(
        keychain_receipt.get(key) is True
        for key in (
            "login_item_present",
            "login_secret_readable",
            "login_secret_nonempty",
            "trade_item_present",
            "trade_account_present",
        )
    ):
        raise RuntimeError("FOUNDER_LOGIN_KEYCHAIN_OR_TRADE_METADATA_NOT_READY")
    trade_account_fingerprint = keychain.trade_account_fingerprint()
    if not trade_account_fingerprint:
        raise RuntimeError("FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING")
    execution, broker = build_foundersc_execution(
        args.state_dir,
        profile=profile,
        route=args.route,
        expected_fund_account_fingerprint=trade_account_fingerprint,
        safety_env_provider=capital_runtime.safety_env,
    )

    def read_allocation_facts() -> dict:
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
            "website_authentication": _website_authentication_evidence(
                login_receipt
            ),
            "passguard": _passguard_evidence(),
        }

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date=trade_date,
            freeze_path=Path(args.freeze),
            allocation_facts_path=allocation_path,
            state_dir=Path(args.state_dir),
            logical_account_id="primary",
        ),
        preflight=preflight,
        restore_environment=lambda: _bounded_no_order_retry(
            lambda: broker.ensure_environment(
                target="mock",
                expected_current="any",
                logical_account_id="primary",
            )
        ),
        read_allocation_facts=read_allocation_facts,
        wait_for_dated_freeze=lambda: wait_for_morning_freeze(
            date=trade_date,
            live_dir=Path(args.freeze).parent,
            timeout_sec=args.freeze_wait_seconds,
            poll_sec=args.poll_seconds,
            snapshot_path=Path(args.freeze),
        ),
        prepare_only=lambda plan: broker.prepare_readonly(
            plan,
            expected_fund_account_fingerprint=trade_account_fingerprint,
        ),
        wait_for_submit_window=lambda target: _wait_for_submit_window(
            target,
            heartbeat=lambda: _bounded_no_order_retry(
                lambda: broker.ensure_environment(
                    target="live",
                    expected_current="live",
                    logical_account_id="primary",
                )
            ),
        ),
        wait_for_reconcile=lambda: time.sleep(1.0),
        execute=lambda plan: execution.execute(plan, broker),
    )
    payload = receipt.as_dict()
    payload["capital_runtime"] = capital_receipt
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.status in {"completed", "no_action", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
