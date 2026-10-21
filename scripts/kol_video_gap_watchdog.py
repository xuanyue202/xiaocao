#!/usr/bin/env python3
"""Independently diagnose missing Xiaocao acquisition/Handoff without capture."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from xiaocao.api import XiaocaoClient
from xiaocao.api.cache import SQLiteCache
from xiaocao.config import load_settings
from xiaocao.kol.video_gap_watchdog import (
    CHINA, _rows, completed_trade_days, inspect_video_gaps, notification_transition,
)
from xiaocao.kol.xiaocao_wechat import DEFAULT_CONTACT, DEFAULT_WECHAT_CLI


def read_history(start: str, end: str, executable: Path, runner=subprocess.run) -> dict:
    merged = None
    for offset in range(0, 2000, 200):
        result = runner([str(executable), "history", DEFAULT_CONTACT, "--start-time", start,
            "--end-time", end, "--offset", str(offset), "--limit", "200", "--voice", "off",
            "--format", "json"], check=True, capture_output=True, text=True, timeout=30)
        page = json.loads(result.stdout)
        if (page.get("chat") != DEFAULT_CONTACT or not page.get("username")
            or page.get("failures") not in (None, []) or not isinstance(page.get("messages"), list)
            or page.get("offset") != offset or page.get("limit") != 200
            or page.get("count") != len(page["messages"])):
            raise ValueError("history_readback_incomplete")
        if merged is None:
            merged = {"chat": page["chat"], "username": page["username"], "messages": [], "failures": []}
        if page["username"] != merged["username"]:
            raise ValueError("history_contact_binding_changed")
        merged["messages"].extend(page["messages"])
        if len(page["messages"]) < 200:
            return merged
    raise ValueError("history_pagination_incomplete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription-dir", type=Path, default=Path("output/live/kol_xiaocao_live/wechat_subscription"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/live/kol_video_gap_watchdog"))
    parser.add_argument("--wechat-cli", type=Path, default=DEFAULT_WECHAT_CLI)
    parser.add_argument("--mailbox-events", type=Path, default=Path("output/live/kol_mailbox/events.jsonl"))
    args = parser.parse_args()
    now = datetime.now(CHINA)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        settings = load_settings()
        client = XiaocaoClient(base_url=settings.base_url, cache=SQLiteCache("output/.cache/xiaocao.db"),
                               timeout=10, retries=1, minimum_request_interval=1.0)
        rows = client.get_trade_cal((now.date()-timedelta(days=40)).isoformat(), now.date().isoformat(), "SSE", 1)
        calendar = completed_trade_days(rows, now, count=3)
        start = (datetime.fromisoformat(calendar[0]).date()+timedelta(days=1)).isoformat()
        history = read_history(start, now.strftime("%Y-%m-%d %H:%M:%S"), args.wechat_cli)
        result = inspect_video_gaps(args.subscription_dir, calendar[-2:], now, history,
                                   coverage_start=start, acknowledgments=_rows(args.mailbox_events))
        result["history_evidence_sha256"] = hashlib.sha256(json.dumps(history, sort_keys=True).encode()).hexdigest()
        result["history_message_count"] = len(history["messages"])
    except Exception as exc:
        # Never export raw command errors, message text, passwords or URLs.
        reason = str(exc) if re.fullmatch(r"[a-z_]+", str(exc)) else type(exc).__name__
        result = {"status": "degraded", "observed_at": now.isoformat(), "failure_code": reason,
                  "history_checked": False, "gaps": []}
    state = args.output_dir / "status.json"
    with (args.output_dir / "state.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = json.loads(state.read_text()) if state.exists() else None
        result = notification_transition(result, previous)
        tmp = state.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        os.replace(tmp, state)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
