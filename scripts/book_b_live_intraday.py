#!/usr/bin/env python3
"""Run one broker-reconciled Book B live lifecycle checkpoint.

The command never reads or writes paper account files.  It consumes native
Founder positions/orders/trades plus positions-funds readback, monitors only
broker-proved Xiaocao-owned lots,
and hands authorized SELL intents to TradingExecution.  The optional handoff
still cannot submit without the pre-existing two-key real-capital runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import live_monitor as monitor  # noqa: E402
from xiaocao.live.book_b_live_intraday import run_book_b_live_intraday  # noqa: E402
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402
from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight  # noqa: E402
from xiaocao.live.trading_runner import build_foundersc_native_execution  # noqa: E402


def _china_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today")
    parser.add_argument(
        "--phase",
        required=True,
        choices=("opening", "sparse", "precheck", "closing", "eod"),
    )
    parser.add_argument(
        "--state-dir", default="output/live/book_b_live_execution"
    )
    parser.add_argument("--freeze-dir", default="output/live")
    parser.add_argument(
        "--execute-sells",
        action="store_true",
        help="Hand authorized SELL intents to TradingExecution; the two-key gate still applies",
    )
    args = parser.parse_args(argv)

    current = _china_now()
    trade_date = current.date().isoformat() if args.date == "today" else args.date
    state_dir = Path(args.state_dir)
    run_id = (
        f"{trade_date}-{args.phase}-"
        f"{current.strftime('%Y%m%dT%H%M%S%f%z')}-{os.getpid()}"
    )
    run_dir = state_dir / "runs" / "intraday"
    run_path = run_dir / f"{trade_date}-{args.phase}.json"
    archive_path = run_dir / "archive" / f"{run_id}.json"
    try:
        keychain = FounderscKeychainPreflight()
        keychain_receipt = keychain.run(read_trade_secret=True)
        required = (
            "trade_item_present",
            "trade_account_present",
            "trade_secret_readable",
            "trade_secret_nonempty",
        )
        if not all(keychain_receipt.get(field) is True for field in required):
            raise RuntimeError("FOUNDER_NATIVE_TRADE_KEYCHAIN_NOT_READY")
        fingerprint = keychain.trade_account_fingerprint()
        if not fingerprint:
            raise RuntimeError("FOUNDER_TRADE_ACCOUNT_FINGERPRINT_MISSING")
        capital_runtime = KeychainCapitalRuntime()
        execution, broker = build_foundersc_native_execution(
            state_dir,
            expected_fund_account_fingerprint=fingerprint,
            safety_env_provider=capital_runtime.safety_env,
        )
        client = monitor._client()
        market_context: dict[str, object] | None = None
        sentiment_map: dict[str, dict[str, object]] | None = None
        snapshot_map: dict[tuple[str, str, str], dict[str, object]] | None = None
        broker_login_ready = False

        def ensure_broker_login() -> None:
            nonlocal broker_login_ready
            if broker_login_ready:
                return
            broker.ensure_login()
            broker_login_ready = True

        def account_snapshot_provider() -> dict:
            ensure_broker_login()
            reader = getattr(broker, "read_live_account_snapshot", None)
            if not callable(reader):
                raise RuntimeError("NATIVE_LIVE_ACCOUNT_SNAPSHOT_PORT_MISSING")
            return reader(
                trade_date=trade_date,
                logical_account_id="primary",
                expected_fund_account_fingerprint=fingerprint,
            )

        def status_provider(lots) -> list[dict]:
            nonlocal market_context, sentiment_map, snapshot_map
            market_context = monitor._market_sentiment_context(client)
            sentiment_map = monitor._load_stock_sentiment_map(trade_date)
            snapshot_map = monitor._load_signal_snapshot_map()
            statuses: list[dict] = []
            for lot in lots:
                position = {
                    "book": "B",
                    "status": "open",
                    "code": lot.code,
                    "name": lot.name,
                    "entry_date": lot.entry_date,
                    "entry_price": lot.entry_price,
                    "shares": lot.shares,
                    "fee_rate": lot.buy_fee_rate,
                    "profile": "v5",
                    **dict(lot.monitor_context),
                }
                status = monitor._compute_status(
                    client,
                    position,
                    trade_date,
                    book="B",
                    market_context=market_context,
                    sentiment_map=sentiment_map,
                    snapshot_map=snapshot_map,
                )
                statuses.append({**status, "owned_lot_id": lot.owned_lot_id})
            return statuses

        def execute_plan(plan):
            ensure_broker_login()
            return execution.execute(plan, broker)

        receipt = run_book_b_live_intraday(
            state_dir=state_dir,
            trade_date=trade_date,
            phase=args.phase,
            account_snapshot_provider=account_snapshot_provider,
            status_provider=status_provider,
            execute=execute_plan,
            now=_china_now,
            strategy_sha=_git_sha(),
            freeze_dir=Path(args.freeze_dir),
            execute_sells=args.execute_sells,
        )
        payload = receipt.as_dict()
        payload["route"] = "native-app"
        payload["paper_ledger_used"] = False
        payload["execute_sells_requested"] = args.execute_sells
        payload["run_id"] = run_id
        payload["run_receipt_path"] = str(archive_path)
        _write_json_atomic(archive_path, payload)
        _write_json_atomic(run_path, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        return 0 if payload["status"] in {"settled", "no_action", "observed", "executed"} else 2
    except Exception as exc:
        payload = {
            "trade_date": trade_date,
            "phase": args.phase,
            "status": "blocked",
            "reason": str(exc) or type(exc).__name__,
            "route": "native-app",
            "paper_ledger_used": False,
            "execute_sells_requested": args.execute_sells,
            "run_id": run_id,
            "run_receipt_path": str(archive_path),
        }
        _write_json_atomic(archive_path, payload)
        if payload["reason"] != "LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING":
            _write_json_atomic(run_path, payload)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
