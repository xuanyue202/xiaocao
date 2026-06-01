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
from datetime import date as _date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
POSITIONS_FILE = OUT_DIR / "positions.jsonl"
ALERTS_FILE = OUT_DIR / "alerts.jsonl"
ACCOUNT_FILE = OUT_DIR / "paper_account.json"
TRADES_FILE = OUT_DIR / "paper_trades.jsonl"
HOLDINGS_FILE = OUT_DIR / "paper_holdings.json"
HOLDING_SNAPSHOTS_FILE = OUT_DIR / "paper_holdings_snapshots.jsonl"

PROFILE_DD = {"v5": 2.0, "v6": 0.5}
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_account() -> dict:
    if ACCOUNT_FILE.exists():
        with ACCOUNT_FILE.open(encoding="utf-8") as f:
            account = json.load(f)
        account.setdefault("initial_capital", DEFAULT_STARTING_CAPITAL)
        account.setdefault("cash", DEFAULT_STARTING_CAPITAL)
        account.setdefault("fee_rate", DEFAULT_FEE_RATE)
        account.setdefault("realized_pnl", 0.0)
        account.setdefault("total_fees", 0.0)
        return account
    return {
        "initial_capital": DEFAULT_STARTING_CAPITAL,
        "cash": DEFAULT_STARTING_CAPITAL,
        "fee_rate": DEFAULT_FEE_RATE,
        "realized_pnl": 0.0,
        "total_fees": 0.0,
        "created_at": _now_iso(),
    }


def _save_account(account: dict) -> None:
    ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    account["updated_at"] = _now_iso()
    tmp = ACCOUNT_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(ACCOUNT_FILE)


def _append_trade(record: dict) -> None:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TRADES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _position_key(position: dict) -> tuple[str, str]:
    return str(position.get("entry_date", "")), str(position.get("code", ""))


def _write_holdings_snapshot(statuses: list[dict]) -> dict:
    account = _load_account()
    status_by_key = {_position_key(s): s for s in statuses}
    holdings = []
    total_market_value = 0.0
    total_liquidation_value = 0.0
    total_cost = 0.0
    for p in _load_positions():
        s = status_by_key.get(_position_key(p))
        if not s:
            s = {
                "latest_price": p.get("entry_price", 0.0),
                "latest_time": "",
                "net_ret_pct": 0.0,
                "dd_pct": 0.0,
                "t1_blocked": _date.today().isoformat() == p.get("entry_date"),
                "shares": p.get("shares"),
            }
        shares = int(p.get("shares") or s.get("shares") or 0)
        latest_price = float(s.get("latest_price") or p.get("entry_price") or 0.0)
        fee_rate = float(p.get("fee_rate", account.get("fee_rate", DEFAULT_FEE_RATE)))
        market_value = round(shares * latest_price, 2)
        liquidation_value = round(market_value * (1 - fee_rate), 2)
        cost = round(float(p.get("entry_cash_out") or 0.0), 2)
        gross_pnl = round(market_value - float(p.get("gross_notional", cost)), 2)
        net_pnl = round(liquidation_value - cost, 2)
        total_market_value = round(total_market_value + market_value, 2)
        total_liquidation_value = round(total_liquidation_value + liquidation_value, 2)
        total_cost = round(total_cost + cost, 2)
        holdings.append({
            "code": p.get("code"),
            "name": p.get("name", ""),
            "entry_date": p.get("entry_date"),
            "entry_price": p.get("entry_price"),
            "latest_price": round(latest_price, 4),
            "latest_time": s.get("latest_time", ""),
            "shares": shares,
            "cost": cost,
            "market_value": market_value,
            "liquidation_value_after_fee": liquidation_value,
            "gross_unrealized_pnl": gross_pnl,
            "net_unrealized_pnl": net_pnl,
            "net_ret_pct": s.get("net_ret_pct"),
            "dd_pct": s.get("dd_pct"),
            "t1_blocked": s.get("t1_blocked"),
            "profile": p.get("profile", "v5"),
            "source": p.get("source", ""),
        })
    cash = round(float(account.get("cash", DEFAULT_STARTING_CAPITAL)), 2)
    snapshot = {
        "ts": _now_iso(),
        "date": _date.today().isoformat(),
        "cash": cash,
        "market_value": total_market_value,
        "liquidation_value_after_fee": total_liquidation_value,
        "total_equity_after_exit_fee": round(cash + total_liquidation_value, 2),
        "initial_capital": round(float(account.get("initial_capital", DEFAULT_STARTING_CAPITAL)), 2),
        "realized_pnl": round(float(account.get("realized_pnl", 0.0)), 2),
        "unrealized_pnl_after_fee": round(total_liquidation_value - total_cost, 2),
        "total_fees": round(float(account.get("total_fees", 0.0)), 2),
        "open_positions": len(holdings),
        "holdings": holdings,
    }
    if not ACCOUNT_FILE.exists():
        _save_account(account)
    HOLDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HOLDINGS_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(HOLDINGS_FILE)
    with HOLDING_SNAPSHOTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
    return snapshot


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    cache = SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db")
    return XiaocaoClient(
        base_url=settings.base_url, timeout=settings.timeout,
        retries=settings.retries, cache=cache,
    )


def _realtime_detail(client: XiaocaoClient, code: str) -> dict:
    try:
        payload = client.second_line_detail_info(code)
    except Exception:
        return {}
    if isinstance(payload, dict):
        if isinstance(payload.get(code), dict):
            return payload.get(code) or {}
        if payload.get("code") == code:
            return payload
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row.get("code") == code:
                return row
    return {}


def _sell_block_reason(detail: dict) -> str | None:
    if not detail:
        return None
    try:
        trade = float(detail.get("trade") or detail.get("close") or 0.0)
    except (TypeError, ValueError):
        trade = 0.0
    try:
        down_price = float(detail.get("downPrice") or 0.0)
    except (TypeError, ValueError):
        down_price = 0.0
    try:
        buy_vol1 = float(detail.get("buyVol1") or 0.0)
    except (TypeError, ValueError):
        buy_vol1 = 0.0
    if down_price > 0 and abs(trade - down_price) < 1e-6 and buy_vol1 <= 0:
        return "LIMIT_DOWN_NO_BID"
    return None


def _strong_hold_reason(position: dict, detail: dict, latest_price: float, peak: float) -> str | None:
    if not detail:
        return None
    mode = str(position.get("mode") or "")
    flags = str(position.get("flags") or "")
    try:
        xcjw = float(position.get("xcjw") or 0.0)
    except (TypeError, ValueError):
        xcjw = 0.0
    try:
        jsjl = float(position.get("jsjl") or 0.0)
    except (TypeError, ValueError):
        jsjl = 0.0
    try:
        up_price = float(detail.get("upPrice") or 0.0)
    except (TypeError, ValueError):
        up_price = 0.0
    try:
        pct_change_rate = float(detail.get("pctChangeRate") or 0.0)
    except (TypeError, ValueError):
        pct_change_rate = 0.0
    try:
        day_high = float(detail.get("high") or 0.0)
    except (TypeError, ValueError):
        day_high = 0.0

    is_trend_leader = ("接力" in mode) or ("连板" in mode) or ("★KP" in flags and jsjl > 0) or xcjw >= 300

    if up_price > 0 and latest_price >= up_price * 0.997:
        return "NEAR_LIMIT_UP"
    if is_trend_leader and pct_change_rate >= 8.0 and day_high > 0 and latest_price >= day_high * 0.995:
        return "STRONG_UPTREND_NEAR_HIGH"
    if pct_change_rate >= 9.5:
        return "LIMIT_UP_DAY"
    if is_trend_leader and peak > 0 and latest_price >= peak * 0.995 and pct_change_rate >= 6.0:
        return "STRONG_TREND_HOLD"
    return None


def _load_all_positions() -> list[dict]:
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
                out.append(p)
            except json.JSONDecodeError:
                continue
    return out


def _load_positions() -> list[dict]:
    return [p for p in _load_all_positions() if p.get("status", "open") == "open"]


def _execute_simulated_sells(client: XiaocaoClient, triggered_alerts: list[dict]) -> tuple[int, int]:
    if not triggered_alerts:
        return 0, 0
    positions = _load_all_positions()
    account = _load_account()
    closed = 0
    blocked = 0
    for alert in triggered_alerts:
        for p in positions:
            if p.get("status", "open") != "open":
                continue
            if p.get("code") != alert["code"] or p.get("entry_date") != alert["entry_date"]:
                continue
            detail = _realtime_detail(client, str(p.get("code") or ""))
            blocked_reason = _sell_block_reason(detail)
            if blocked_reason:
                blocked += 1
                with ALERTS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": _now_iso(),
                        "alert": "SELL_BLOCKED",
                        "reason": blocked_reason,
                        "code": p.get("code"),
                        "name": p.get("name", ""),
                        "entry_date": p.get("entry_date"),
                    }, ensure_ascii=False) + "\n")
                break
            shares = int(p.get("shares") or alert.get("shares") or 0)
            if shares <= 0:
                break
            exit_price = float(alert["latest_price"])
            fee_rate = float(p.get("fee_rate", account.get("fee_rate", DEFAULT_FEE_RATE)))
            gross_notional = round(exit_price * shares, 2)
            exit_fee = round(gross_notional * fee_rate, 2)
            exit_cash_in = round(gross_notional - exit_fee, 2)
            entry_cash_out = float(
                p.get("entry_cash_out")
                or (float(p["entry_price"]) * shares * (1 + fee_rate))
            )
            realized_pnl = round(exit_cash_in - entry_cash_out, 2)
            account["cash"] = round(float(account.get("cash", 0.0)) + exit_cash_in, 2)
            account["realized_pnl"] = round(float(account.get("realized_pnl", 0.0)) + realized_pnl, 2)
            account["total_fees"] = round(float(account.get("total_fees", 0.0)) + exit_fee, 2)
            account["last_sell_date"] = _date.today().isoformat()
            p.update({
                "status": "closed",
                "exit_date": _date.today().isoformat(),
                "exit_price": round(exit_price, 4),
                "exit_fee": exit_fee,
                "exit_cash_in": exit_cash_in,
                "realized_pnl": realized_pnl,
                "exit_reason": "TRAILING_STOP",
            })
            _append_trade({
                "ts": _now_iso(), "date": _date.today().isoformat(), "side": "SELL",
                "code": p.get("code"), "name": p.get("name", ""),
                "price": round(exit_price, 4), "shares": shares,
                "gross_notional": gross_notional, "fee": exit_fee,
                "cash_after": account["cash"], "realized_pnl": realized_pnl,
                "reason": "TRAILING_STOP",
            })
            closed += 1
            break
    if closed:
        with POSITIONS_FILE.open("w", encoding="utf-8") as f:
            for p in positions:
                f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
        _save_account(account)
    return closed, blocked


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


def _is_trading_day(today_iso: str, client: XiaocaoClient) -> tuple[bool, str]:
    lookback = (_date.fromisoformat(today_iso) - timedelta(days=14)).isoformat()
    days = _trading_dates_between(lookback, today_iso, client)
    latest = days[-1] if days else ""
    return latest == today_iso, latest


def _compute_status(client: XiaocaoClient, position: dict, today_iso: str) -> dict:
    """Pull minute data from entry_date through today, compute peak + dd + status."""
    code = position["code"]
    entry_date = position["entry_date"]
    entry_price = float(position["entry_price"])
    profile = position.get("profile", "v5")
    dd_threshold = PROFILE_DD.get(profile, 2.0)
    fee_rate = float(position.get("fee_rate", 0.0001))

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
    net_ret_pct = ((latest_price * (1 - fee_rate)) / (entry_price * (1 + fee_rate)) - 1) * 100

    # T+1 logic: if today == entry_date, we can't sell
    t1_blocked = (today_iso == entry_date)
    detail = _realtime_detail(client, code)
    strong_hold_reason = _strong_hold_reason(position, detail, latest_price, peak)
    triggered = (dd_pct >= dd_threshold) and not t1_blocked and not strong_hold_reason
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
        "net_ret_pct": round(net_ret_pct, 4),
        "fee_rate": fee_rate,
        "days_processed": days_processed,
        "t1_blocked": t1_blocked,
        "strong_hold_reason": strong_hold_reason,
        "triggered": triggered,
        "shares": position.get("shares"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="只检查指定 code")
    parser.add_argument("--no-notify", action="store_true",
                        help="禁用 macOS 通知（保留 stdout + alerts.jsonl）")
    parser.add_argument("--execute-sells", action="store_true",
                        help="触发 T+1 止损时执行模拟卖出，更新 positions/account/trades")
    args = parser.parse_args()

    client = _client()
    today_iso = _date.today().isoformat()
    is_trading_day, latest_trading_day = _is_trading_day(today_iso, client)
    if not is_trading_day:
        print(
            f"Non-trading day; skip live monitor "
            f"(today={today_iso}, latest_trading={latest_trading_day or 'unknown'})"
        )
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    positions = _load_positions()
    if args.code:
        positions = [p for p in positions if p.get("code") == args.code]
    if not positions:
        snapshot = _write_holdings_snapshot([])
        print(f"No open positions in {POSITIONS_FILE.relative_to(ROOT)}")
        print(
            f"Account: cash={snapshot['cash']:.2f}, "
            f"equity={snapshot['total_equity_after_exit_fee']:.2f}, "
            f"open_positions=0"
        )
        return

    print(f"Monitoring {len(positions)} open position(s) at {today_iso}\n")
    print(f"{'code':<14} {'profile':<6} {'entry':>7} {'peak':>7} {'latest':>7} "
          f"{'dd':>7} {'ret':>7} {'net':>7} {'status':<14}")
    print("-" * 80)

    triggered_alerts = []
    statuses = []
    for p in positions:
        s = _compute_status(client, p, today_iso)
        statuses.append(s)
        status_label = (
            "🔔 SELL"
            if s["triggered"] else
            f"hold:{s['strong_hold_reason']}"
            if s.get("strong_hold_reason") else
            "T+1_blocked" if s["t1_blocked"] else
            "hold"
        )
        print(
            f"{s['code']:<14} {s['profile']:<6} {s['entry_price']:>7.2f} "
            f"{s['peak']:>7.2f} {s['latest_price']:>7.2f} "
            f"{s['dd_pct']:>+6.2f}% {s['ret_pct']:>+6.2f}% "
            f"{s['net_ret_pct']:>+6.2f}% {status_label:<14}"
        )
        if s.get("strong_hold_reason"):
            with ALERTS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": _now_iso(),
                    "alert": "SELL_SUPPRESSED_STRONG_HOLD",
                    **s,
                }, ensure_ascii=False) + "\n")
        if s["triggered"]:
            triggered_alerts.append(s)

    if triggered_alerts:
        print(f"\n🔔 {len(triggered_alerts)} 个 SELL 信号触发")
        for s in triggered_alerts:
            msg = (
                f"卖 {s['name']} ({s['code']}) — "
                f"dd {s['dd_pct']:+.2f}% ≥ {s['dd_threshold_pct']:.1f}% "
                f"({s['profile']}); 当前 {s['latest_price']:.2f} (entry {s['entry_price']:.2f}, "
                f"peak {s['peak']:.2f}, ret {s['ret_pct']:+.2f}%, "
                f"net {s['net_ret_pct']:+.2f}% after fee {s['fee_rate']:.4%})"
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
        if args.execute_sells:
            closed, blocked = _execute_simulated_sells(client, triggered_alerts)
            account = _load_account()
            print(
                f"\nSimulated sells executed: {closed}; "
                f"blocked={blocked}; "
                f"cash={float(account.get('cash', 0.0)):.2f}, "
                f"realized_pnl={float(account.get('realized_pnl', 0.0)):+.2f}, "
                f"total_fees={float(account.get('total_fees', 0.0)):.2f}"
            )
    else:
        print(f"\nNo sell triggers. {sum(1 for p in positions)} position(s) holding.")
    snapshot = _write_holdings_snapshot(statuses)
    print(
        f"Holdings snapshot: cash={snapshot['cash']:.2f}, "
        f"holdings_value={snapshot['liquidation_value_after_fee']:.2f}, "
        f"equity={snapshot['total_equity_after_exit_fee']:.2f}, "
        f"open_positions={snapshot['open_positions']} -> "
        f"{HOLDINGS_FILE.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
