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
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.foundersc_opencli import (  # noqa: E402
    release_foundersc_opencli_site_session,
    resolve_connected_opencli_profile,
)
from xiaocao.live.trading_runner import build_foundersc_execution  # noqa: E402
from wait_for_morning_freeze import wait_for_morning_freeze  # noqa: E402


def _china_date() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


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
        choices=("manual-limit", "opening-auction", "timed-order"),
        default="timed-order",
    )
    parser.add_argument("--freeze-wait-seconds", type=float, default=600.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    trade_date = _china_date() if args.date == "today" else args.date
    allocation_path = Path(str(args.allocation_facts).format(date=trade_date))
    profile = resolve_connected_opencli_profile(args.profile)
    release_foundersc_opencli_site_session(profile)
    execution, broker = build_foundersc_execution(
        args.state_dir,
        profile=profile,
        route=args.route,
    )
    trade_account_fingerprint = FounderscKeychainPreflight().trade_account_fingerprint()

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

    receipt = run_book_b_live_morning(
        BookBLiveMorningConfig(
            trade_date=trade_date,
            freeze_path=Path(args.freeze),
            allocation_facts_path=allocation_path,
            state_dir=Path(args.state_dir),
            logical_account_id="primary",
        ),
        preflight=lambda: broker.ensure_environment(
            target="live",
            expected_current="any",
            logical_account_id="primary",
        ),
        restore_environment=lambda: broker.ensure_environment(
            target="mock",
            expected_current="any",
            logical_account_id="primary",
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
        execute=lambda plan: execution.execute(plan, broker),
    )
    print(json.dumps(receipt.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if receipt.status in {"completed", "no_action", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
