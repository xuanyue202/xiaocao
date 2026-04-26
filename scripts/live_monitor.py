"""Live position monitor — poll minute_line, alert when trailing stop triggers.

Reads `output/live/positions.jsonl` (user-maintained, one JSON per line) and
for each open position:

  1. Fetches today's minute_line up to current minute
  2. Tracks running peak from entry_price up through latest minute
  3. Computes drawdown_from_peak = (peak - latest) / peak * 100
  4. If drawdown ≥ profile threshold (v5=2.0% / v6=0.5%) → SELL alert
  5. Otherwise → HOLD with current dd diagnostics

Alerts go to:
  - stdout (terminal print)
  - macOS notification (osascript)
  - output/live/alerts.jsonl (append-only audit log)

Multi-day positions: the peak is tracked from entry_date forward across all
days. If today < entry_date+1, T+1 means we cannot sell anyway, so we still
report dd as diagnostic but mark the alert as "T1_BLOCKED" (don't fire
notification).

Usage:
    python3 scripts/live_monitor.py                  # check all open positions
    python3 scripts/live_monitor.py --code 002347.XSHE  # single position
    python3 scripts/live_monitor.py --no-notify     # skip macOS notification

Position file format (`output/live/positions.jsonl`, one JSON per line):
    {"code": "002347.XSHE", "name": "泰尔股份",
     "entry_date": "2026-04-28", "entry_price": 8.50,
     "profile": "v6", "shares": 1000,
     "status": "open"}

Mark `"status": "closed"` after you've sold to skip from monitoring.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date as _date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
POSITIONS_FILE = OUT_DIR / "positions.jsonl"
ALERTS_FILE = OUT_DIR / "alerts.jsonl"

PROFILE_DD = {"v5": 2.0, "v6": 0.5}


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _load_positions() -> list[dict]:
    if not POSITIONS_FILE.exists():
        return []
    out = []
    with POSITIONS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                p = json.loads(line)
                if p.get("status", "open") == "open":
                    out.append(p)
            except json.JSONDecodeError:
                continue
    return out


def _macos_notify(title: str, body: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        # Escape quotes for AppleScript
        title_safe = title.replace('"', '\\"').replace("'", "\\'")
        body_safe = body.replace('"', '\\"').replace("'", "\\'")
        subprocess.run([
            "osascript", "-e",
            f'display notification "{body_safe}" with title "{title_safe}" sound name "Glass"',
        ], check=False, capture_output=True, timeout=5)
    except Exception:
        pass


def _trading_dates_between(start: str, end: str, client: XiaocaoClient) -> list[str]:
    """Return list of YYYY-MM-DD trading days between start and end inclusive."""
    try:
        rows = client.get_trade_cal(start, end, "SSE", 1)
    except Exception:
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        v = r.get("calDate") or r.get("tradeDate") or r.get("date")
        if v is None:
            continue
        v = str(v)
        if len(v) == 8 and v.isdigit():
            v = f"{v[:4]}-{v[4:6]}-{v[6:]}"
        else:
            v = v[:10]
        if start <= v <= end:
            out.append(v)
    return sorted(set(out))


def _compute_status(client: XiaocaoClient, position: dict, today_iso: str) -> dict:
    """Pull minute data from entry_date through today, compute peak + dd + status."""
    code = position["code"]
    entry_date = position["entry_date"]
    entry_price = float(position["entry_price"])
    profile = position.get("profile", "v5")
    dd_threshold = PROFILE_DD.get(profile, 2.0)

    # Trading days from entry_date to today
    trade_days = _trading_dates_between(entry_date, today_iso, client)
    if not trade_days:
        # Fallback: just today if we can't get cal
        trade_days = [today_iso]

    # Peak starts at entry_price (= 9:30 open of entry_date).
    # Per backtest convention, intraday of entry_date is NOT used for stop logic
    # (T+1 means we can't sell anyway). We track peak across day+1 onwards.
    peak = entry_price
    latest_price = entry_price
    latest_time = ""
    days_processed = 0

    for d in trade_days:
        if d == entry_date:
            # Skip entry-day intraday for peak tracking (matches backtest)
            continue
        try:
            recs = client.minute_line(code, "1min", "bfq", trade_date=d.replace("-", ""), count=241)
        except Exception:
            continue
        if not isinstance(recs, list) or not recs:
            continue
        days_processed += 1
        for r in recs:
            try:
                t = float(r.get("trade") or 0)
            except (TypeError, ValueError):
                continue
            if t <= 0:
                continue
            if t > peak:
                peak = t
            latest_price = t
            latest_time = f"{d} {r.get('tradeTime', '')}"

    if peak <= 0:
        peak = entry_price
    if latest_price <= 0:
        latest_price = entry_price

    dd_pct = (peak - latest_price) / peak * 100 if peak > 0 else 0.0
    ret_pct = (latest_price - entry_price) / entry_price * 100

    # T+1 logic: if today == entry_date, we can't sell
    t1_blocked = (today_iso == entry_date)

    triggered = (dd_pct >= dd_threshold) and not t1_blocked
    return {
        "code": code,
        "name": position.get("name", ""),
        "profile": profile,
        "dd_threshold_pct": dd_threshold,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "peak": round(peak, 4),
        "latest_price": round(latest_price, 4),
        "latest_time": latest_time,
        "dd_pct": round(dd_pct, 4),
        "ret_pct": round(ret_pct, 4),
        "days_processed": days_processed,
        "t1_blocked": t1_blocked,
        "triggered": triggered,
        "shares": position.get("shares"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="只检查指定 code")
    parser.add_argument("--no-notify", action="store_true",
                        help="禁用 macOS 通知（保留 stdout + alerts.jsonl）")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    positions = _load_positions()
    if args.code:
        positions = [p for p in positions if p.get("code") == args.code]
    if not positions:
        print(f"No open positions in {POSITIONS_FILE.relative_to(ROOT)}")
        return

    client = _client()
    today_iso = _date.today().isoformat()

    print(f"Monitoring {len(positions)} open position(s) at {today_iso}\n")
    print(f"{'code':<14} {'profile':<6} {'entry':>7} {'peak':>7} {'latest':>7} "
          f"{'dd':>7} {'ret':>7} {'status':<14}")
    print("-" * 80)

    triggered_alerts = []
    for p in positions:
        s = _compute_status(client, p, today_iso)
        status_label = (
            "🔔 SELL"
            if s["triggered"] else
            "T+1_blocked" if s["t1_blocked"] else
            "hold"
        )
        print(
            f"{s['code']:<14} {s['profile']:<6} {s['entry_price']:>7.2f} "
            f"{s['peak']:>7.2f} {s['latest_price']:>7.2f} "
            f"{s['dd_pct']:>+6.2f}% {s['ret_pct']:>+6.2f}% {status_label:<14}"
        )
        if s["triggered"]:
            triggered_alerts.append(s)

    if triggered_alerts:
        print(f"\n🔔 {len(triggered_alerts)} 个 SELL 信号触发")
        for s in triggered_alerts:
            msg = (
                f"卖 {s['name']} ({s['code']}) — "
                f"dd {s['dd_pct']:+.2f}% ≥ {s['dd_threshold_pct']:.1f}% "
                f"({s['profile']}); 当前 {s['latest_price']:.2f} (entry {s['entry_price']:.2f}, "
                f"peak {s['peak']:.2f}, ret {s['ret_pct']:+.2f}%)"
            )
            print("  " + msg)
            if not args.no_notify:
                _macos_notify(f"卖点触发 {s['code']}", msg)
            # Append to alerts log
            with ALERTS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": _date.today().isoformat(),
                    "alert": "SELL_TRIGGERED",
                    **s,
                }, ensure_ascii=False) + "\n")
    else:
        print(f"\nNo sell triggers. {sum(1 for p in positions)} position(s) holding.")


if __name__ == "__main__":
    main()
