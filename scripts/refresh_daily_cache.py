#!/usr/bin/env python3
"""Keep the daily-bar record current despite the lagging date_kline feed.

The date_kline (daily OHLCV) endpoint can trail realtime by weeks, freezing
mode_history / the proxy-regime substrate (see AGENTS.md). minute_line stays
current, so at eod we reconstruct today's daily bar (from the `trade` field) for
the universe we actually care about — open positions + today's signals — and
append it to a provenance-tagged store the learning side can read. Rate-limited
and cache-first (minute persists to xiaocao.db).

Run at eod (after the day's minute data exists). Idempotent per (code,date).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from daily_from_minute import reconstruct  # noqa: E402
from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

LIVE = ROOT / "output" / "live"
STORE = LIVE / "daily_reconstructed.jsonl"


def _universe() -> set[str]:
    codes: set[str] = set()
    pos = LIVE / "positions.jsonl"
    if pos.exists():
        for line in pos.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("status") == "open" and r.get("code"):
                codes.add(str(r["code"]))
    snaps = LIVE / "signal_snapshots.jsonl"
    if snaps.exists():
        today = date.today().isoformat()
        for line in snaps.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("date", "")) == today and r.get("code"):
                codes.add(str(r["code"]))
    return codes


def _done(store: Path) -> set:
    if not store.exists():
        return set()
    out = set()
    for line in store.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            out.add((r["code"], r["date"]))
        except (json.JSONDecodeError, KeyError):
            pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=date.today().strftime("%Y%m%d"), help="YYYYMMDD (default today)")
    ap.add_argument("--sleep", type=float, default=2.0)
    a = ap.parse_args()

    codes = _universe()
    if not codes:
        print("refresh_daily_cache: no open positions / today signals — nothing to refresh")
        return
    done = _done(STORE)
    s = load_settings(None)
    client = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                           cache=SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db"))
    STORE.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    with STORE.open("a", encoding="utf-8") as fh:
        for code in sorted(codes):
            if (code, a.date) in done:
                continue
            bars = client.minute_line(code, trade_date=a.date, count=241)
            daily = reconstruct(bars)
            if daily:
                fh.write(json.dumps({"code": code, "date": a.date, "source": "minute_reconstructed", **daily},
                                    ensure_ascii=False) + "\n")
                fh.flush()
                ok += 1
            time.sleep(a.sleep)  # rate-limit: the API throttles on bursts
    print(f"refresh_daily_cache: reconstructed {ok}/{len(codes)} daily bars for {a.date} -> {STORE.name}")


if __name__ == "__main__":
    main()
