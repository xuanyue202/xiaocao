"""Paper trading v6 — daily signal log + slippage verification (Plan E follow-up).

Two modes (run via subcommand):

  log    — Generate v6 active signals for a date (default today/latest), record
           entry candidates with theoretical entry/stop. Append to
           output/paper_v6/signals.jsonl. Run once per trading day.

  replay — Walk past signals.jsonl, backfill minute_line for any signal whose
           hold window has elapsed, replay max_dd 0.5% trailing stop on real
           minute data, compute theoretical-vs-actual fill slippage. Output
           output/paper_v6/slippage_report.md.

Workflow for the user:
  daily:    `python3 scripts/paper_trade_v6.py log`              # at EOD
  weekly:   `python3 scripts/paper_trade_v6.py replay`           # after 1-2 wk

Slippage = (actual_fill_price - theoretical_stop_price) / theoretical_stop * 100

  - negative ↓ = adverse (real fill worse than theoretical)
  - positive ↑ = favorable (real fill better)
  - zero ⏤ = theoretical assumption holds

If aggregate slippage on stop-out trades is < -0.3% on average, dd=0.5%
advantage is likely eroded vs dd=2.0%; reconsider v6 ship.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import date as _date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.datasource.api_source import ApiDataSource  # noqa: E402
from xiaocao.strategy import run_strategy  # noqa: E402

OUT_DIR = ROOT / "output" / "paper_v6"
SIGNALS_LOG = OUT_DIR / "signals.jsonl"
REPORT_MD = OUT_DIR / "slippage_report.md"

V6_DD_PCT = 0.5
V6_HOLD_DAYS = 3


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _resolve_date(date_arg: str) -> str:
    if date_arg == "today":
        return _date.today().isoformat()
    if date_arg == "latest":
        # Find the latest cached trade day from date_kline cache
        latest = ""
        cache_path = ROOT / "output" / ".cache" / "xiaocao.db"
        for data in iter_cached_responses(cache_path, "/stock/date_kline"):
            if not isinstance(data, list):
                continue
            for row in data:
                if isinstance(row, dict):
                    latest = max(latest, str(row.get("tradeDate") or ""))
        if latest:
            d = latest[:10]
            if len(d) == 8 and d.isdigit():
                d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            return d
        return _date.today().isoformat()
    return date_arg


def cmd_log(args: argparse.Namespace) -> None:
    """Record v6 active signals for `args.date`."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date_iso = _resolve_date(args.date)
    print(f"Generating v6 signals for {date_iso}...")

    client = _client()
    source = ApiDataSource(client, hpqb_state=0, lpdx_state=0)

    # Run v6 profile signal generation
    rows = run_strategy(date_iso, source, profile="validated_v6", adaptive_modes=False)
    if not rows:
        print(f"  No signals on {date_iso}")
        return

    actives = [r for r in rows if r.get("adaptive_active") in (True, None)]
    print(f"  Got {len(rows)} signals, {len(actives)} active")

    # Get each stock's open price (theoretical entry) for the date
    # by fetching today's daily kline
    log_rows = []
    for r in actives:
        code = r.get("code")
        if not code:
            continue
        # Fetch daily kline for this code spanning to date_iso
        try:
            klines = client.date_kline(code, count=5, freq="D", adj="qfq")
        except Exception:
            continue
        if not isinstance(klines, list):
            continue
        # Find buy_date row
        kbd = {str(k.get("tradeDate", ""))[:10]: k for k in klines if isinstance(k, dict)}
        # tradeDate may be YYYYMMDD
        td_compact = date_iso.replace("-", "")
        row_for_date = kbd.get(date_iso) or kbd.get(td_compact)
        if not row_for_date:
            continue
        try:
            entry_open = float(row_for_date.get("open") or 0)
        except (TypeError, ValueError):
            continue
        if entry_open <= 0:
            continue
        log_rows.append({
            "logDate": _date.today().isoformat(),
            "buyDate": date_iso,
            "code": code,
            "name": r.get("name", ""),
            "mode": r.get("mode", ""),
            "entry_open": entry_open,
            "theoretical_dd_pct": V6_DD_PCT,
            "hold_days": V6_HOLD_DAYS,
            # Will be filled at replay time
            "replayed": False,
        })

    if not log_rows:
        print("  No actionable signals after kline lookup; nothing logged")
        return

    with SIGNALS_LOG.open("a", encoding="utf-8") as f:
        for row in log_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  Logged {len(log_rows)} signals to {SIGNALS_LOG.relative_to(ROOT)}")


def _load_signals() -> list[dict]:
    if not SIGNALS_LOG.exists():
        return []
    out = []
    with SIGNALS_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _save_signals(rows: list[dict]) -> None:
    with SIGNALS_LOG.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cmd_replay(args: argparse.Namespace) -> None:
    """Backfill minute_line for completed signals + compute slippage."""
    rows = _load_signals()
    if not rows:
        print(f"No logged signals at {SIGNALS_LOG}")
        return

    today = _date.today()
    client = _client()

    # Backfill minute_line for buy_date of each not-yet-replayed signal
    pending = [r for r in rows if not r.get("replayed")]
    print(f"Loaded {len(rows)} logged signals, {len(pending)} pending replay")

    # Filter to those whose hold window has elapsed (today >= buy_date + hold_days)
    ready = []
    for r in pending:
        try:
            buy = _date.fromisoformat(r["buyDate"])
        except (KeyError, ValueError):
            continue
        if (today - buy).days >= V6_HOLD_DAYS:
            ready.append(r)
    print(f"  {len(ready)} ready for replay (buy_date + {V6_HOLD_DAYS}d ≤ today)")

    # Backfill minute_line
    from concurrent.futures import ThreadPoolExecutor, as_completed
    fetch_targets = [(r["buyDate"], r["code"]) for r in ready]
    if fetch_targets:
        print(f"  Fetching minute_line for {len(fetch_targets)} (date, code)...")
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = {pool.submit(client.minute_line, code, "1min", "bfq", date, 241, 0): (date, code)
                    for date, code in fetch_targets}
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception:
                    pass

    # Replay each ready signal
    from xiaocao.strategy.intraday_entry import load_minute_cache
    from xiaocao.backtest import score_trades, _kline_by_date
    minute_data = load_minute_cache(ROOT / "output" / ".cache" / "xiaocao.db")

    replay_rows = []
    for r in ready:
        td = r["buyDate"].replace("-", "")
        recs = minute_data.get((td, r["code"]))
        if not recs:
            print(f"  ! no minute data for ({r['buyDate']}, {r['code']})")
            continue
        entry_open = r["entry_open"]

        # Walk minutes in order, track peak, find when stop triggers.
        # For paper-trading slippage check, we model fill at the THIS minute's
        # close (the minute that triggered the stop). Theoretical fill =
        # peak * (1 - dd_pct/100).
        peak = entry_open
        theoretical_fill = None
        actual_fill = None
        trigger_time = None
        for rec in recs:
            try:
                t = float(rec.get("trade") or 0)
            except (ValueError, TypeError):
                continue
            if t <= 0:
                continue
            if t > peak:
                peak = t
            stop_threshold = peak * (1 - V6_DD_PCT / 100)
            if t <= stop_threshold:
                theoretical_fill = stop_threshold
                actual_fill = t  # the minute close that breached the threshold
                trigger_time = rec.get("tradeTime")
                break

        if actual_fill is None:
            # No stop trigger within the day → would carry over to next day(s)
            # For paper-trading purposes, mark as "not stopped intra-day"
            r["replay_kind"] = "no_stop_d1"
            r["actual_fill"] = None
            r["theoretical_fill"] = None
            r["slippage_pct"] = None
        else:
            slippage_pct = (actual_fill - theoretical_fill) / theoretical_fill * 100
            r["replay_kind"] = "stopped_d1"
            r["actual_fill"] = round(actual_fill, 4)
            r["theoretical_fill"] = round(theoretical_fill, 4)
            r["trigger_time"] = trigger_time
            r["slippage_pct"] = round(slippage_pct, 4)
            replay_rows.append(r)

        r["replayed"] = True

    _save_signals(rows)

    # Aggregate
    stopped = [r for r in rows if r.get("replay_kind") == "stopped_d1"]
    no_stop = [r for r in rows if r.get("replay_kind") == "no_stop_d1"]
    pending_remaining = [r for r in rows if not r.get("replayed")]

    print(f"\nReplay summary:")
    print(f"  Stopped on day+1: {len(stopped)}")
    print(f"  No stop d+1 (carried to d+2/d+3): {len(no_stop)}")
    print(f"  Still pending: {len(pending_remaining)}")

    if stopped:
        slips = [s["slippage_pct"] for s in stopped if s.get("slippage_pct") is not None]
        if slips:
            print(f"\nSlippage (stopped trades, {len(slips)} samples):")
            print(f"  median: {statistics.median(slips):+.3f}%")
            print(f"  mean:   {statistics.mean(slips):+.3f}%")
            print(f"  min/max: {min(slips):+.3f}% / {max(slips):+.3f}%")
            adverse = sum(1 for s in slips if s < -0.1)
            print(f"  adverse (slippage < -0.1%): {adverse} / {len(slips)}")

    # Markdown report
    L = ["# Paper trading v6 — slippage verification", ""]
    L.append(f"- Logged signals: {len(rows)}")
    L.append(f"- Replayed (stop on d+1): {len(stopped)}")
    L.append(f"- Replayed (no stop d+1): {len(no_stop)}")
    L.append(f"- Pending: {len(pending_remaining)}")
    L.append("")
    if stopped:
        slips = [s["slippage_pct"] for s in stopped if s.get("slippage_pct") is not None]
        if slips:
            L.append("## Slippage stats (stopped on day+1)")
            L.append("")
            L.append(f"- n: {len(slips)}")
            L.append(f"- median: {statistics.median(slips):+.3f}%")
            L.append(f"- mean: {statistics.mean(slips):+.3f}%")
            L.append(f"- range: [{min(slips):+.3f}%, {max(slips):+.3f}%]")
            L.append("")
            L.append("## Per-trade detail (stopped)")
            L.append("")
            L.append("| buyDate | code | mode | entry | peak | theo | actual | slip | trigger |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            for s in sorted(stopped, key=lambda x: (x.get("buyDate", ""), x.get("code", ""))):
                L.append(
                    f"| {s.get('buyDate', '')} | {s.get('code', '')} | {s.get('mode', '')} | "
                    f"{s.get('entry_open', 0):.2f} | "
                    f"{s.get('theoretical_fill', 0)/((100-V6_DD_PCT)/100):.2f} | "
                    f"{s.get('theoretical_fill', 0):.2f} | "
                    f"{s.get('actual_fill', 0):.2f} | "
                    f"{s.get('slippage_pct', 0):+.3f}% | "
                    f"{s.get('trigger_time', '')} |"
                )
    if no_stop:
        L.append("")
        L.append(f"## No-stop trades (carried beyond d+1, n={len(no_stop)})")
        L.append("")
        L.append("These trades did not trigger 0.5% stop within d+1's minute_line. Either")
        L.append("strong continuous uptrend (no retrace) or stop falls on d+2 / d+3 (need")
        L.append("backfilling next-day minute_line to fully replay).")

    REPORT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"\nWrote: {REPORT_MD.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log", help="Record v6 signals for a date")
    p_log.add_argument("--date", default="latest")
    p_log.set_defaults(handler=cmd_log)

    p_replay = sub.add_parser("replay", help="Replay completed signals + slippage")
    p_replay.set_defaults(handler=cmd_replay)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
