#!/usr/bin/env python3
"""Offline APP-adapter regression and coverage; never a trading-time gate."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "foundersc_native_ax", "foundersc_native_broker", "foundersc_keychain", "capital_keychain",
    "trading_execution", "trading_runner", "book_b_live_morning", "book_b_live_recovery",
    "book_b_live_intraday", "book_b_live_lifecycle",
]
ENTRYPOINTS = ["foundersc_native_ax", "foundersc_app_rehearsal", "book_b_live_morning", "book_b_live_intraday"]
TESTS = [
    "foundersc_native_ax", "foundersc_native_broker", "foundersc_keychain", "live_capital_keychain",
    "trading_execution", "trading_runner", "book_b_live_morning", "book_b_live_recovery",
    "book_b_live_lifecycle", "book_b_live_policy", "book_b_allocation", "live_monitor",
    "native_prepare_clear_behavior", "native_order_value_behavior", "foundersc_execution_integration",
    "foundersc_python_boundaries", "foundersc_query_faults", "foundersc_app_rehearsal",
    "foundersc_native_cli", "configure_foundersc_trade_keychain", "wait_for_agent_reviews",
    "wait_for_morning_freeze",
    "book_b_intraday_cli",
    "book_b_morning_cli",
    "foundersc_process_fencing",
]


def main() -> int:
    destination = ROOT / "output/research/foundersc_reliability"
    destination.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"),
           "COVERAGE_FILE": str(destination / ".coverage")}
    source = ",".join([*("xiaocao.live." + name for name in MODULES),
                       *("scripts." + name for name in ENTRYPOINTS)])
    command = [sys.executable, "-m", "coverage"]
    result = subprocess.run([*command, "run", "--branch", "--source=" + source,
        "-m", "pytest", *("tests/test_" + name + ".py" for name in TESTS),
        "-q", "--tb=short"], cwd=ROOT, env=env, check=False)
    for args in (["report"], ["json", "-o", str(destination / "coverage.json")],
                 ["html", "-d", str(destination / "html")]):
        report = subprocess.run([*command, *args], cwd=ROOT, env=env, check=False)
        if report.returncode:
            return result.returncode or report.returncode
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
