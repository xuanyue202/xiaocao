"""Settle Book T — the paper-only low-turnover trend book.

Book T exits are independent from Book B:
  - wide daily trailing drawdown (TREND_TRAIL_DD)
  - low-turnover rebalance is handled by the next paired morning switch

No short-line strong-hold/composite logic is used here.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config.settings import load_settings  # noqa: E402
from xiaocao.live import accounts  # noqa: E402
from xiaocao.live.sell_blocks import load_blocked_sell_keys as _load_blocked_sell_keys  # noqa: E402
from xiaocao.strategy.params import TREND_BUDGET_RATIO, TREND_REBALANCE_R, TREND_TRAIL_DD  # noqa: E402
from xiaocao.strategy.trend_rules import (  # noqa: E402
    TREND_SWITCH_POLICY_HELD,
    classify_trend_alignment,
)

POS = Path("output/live/positions.jsonl")
ACCOUNT_T = Path("output/live/paper_account_T.json")
TRADES = Path("output/live/paper_trades.jsonl")
RECONSTRUCTED_DAILY = Path("output/live/daily_reconstructed.jsonl")
ALERTS = Path("output/live/alerts.jsonl")
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _f(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normal_date(value: Any) -> str | None:
    s = str(value or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) >= 10:
        return s[:10]
    return None


def _settlement_block_reason(
    blocked: dict[tuple[str, str, str, str], str],
    *,
    book: str,
    exit_date: str,
    code: str,
    entry_date: str,
) -> str | None:
    """Return a same-position, same-day execution block if one was observed."""
    return blocked.get((book, exit_date, code, entry_date))


def _load_reconstructed_daily(path: Path = RECONSTRUCTED_DAILY) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    if not path.exists():
        return out
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = row.get("code")
        d = _normal_date(row.get("date"))
        if not code or not d:
            continue
        out.setdefault(str(code), {})[d] = {
            "tradeDate": d,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "source": row.get("source", "minute_reconstructed"),
        }
    return out


def _kline_map(
    client: XiaocaoClient,
    code: str,
    reconstructed: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    try:
        kl = client.date_kline(code, count=260, freq="D", adj="bfq")
    except Exception:
        kl = []
    if not isinstance(kl, list):
        kl = []
    ser = {
        _normal_date(r.get("tradeDate")): r
        for r in kl
        if isinstance(r, dict) and _normal_date(r.get("tradeDate"))
    }
    ser.update(reconstructed.get(str(code), {}))
    return {k: v for k, v in ser.items() if k}


def _load_account() -> dict[str, Any]:
    return accounts.load_account(
        ACCOUNT_T,
        DEFAULT_STARTING_CAPITAL * TREND_BUDGET_RATIO,
        DEFAULT_FEE_RATE,
    )


def _trend_alignment_for_position(p: dict[str, Any]) -> dict[str, str]:
    return classify_trend_alignment(
        code=str(p.get("code") or ""),
        name=str(p.get("name") or ""),
        category_name=str(p.get("category_name") or ""),
        category_code=str(p.get("category_code") or ""),
    )


def _mark_trend_switch_context(
    p: dict[str, Any],
    *,
    fee_rate: float,
    alignment: dict[str, str],
) -> dict[str, Any]:
    p["trend_alignment"] = alignment["trend_alignment"]
    p["trend_alignment_reason"] = alignment["trend_alignment_reason"]
    p["trend_switch_policy"] = TREND_SWITCH_POLICY_HELD
    p["trend_switch_est_roundtrip_fee_bps"] = round(fee_rate * 2 * 10000, 2)


def _trend_exit_reason(
    *,
    dd_pct: float,
    trail_dd: float,
    hold_days: int,
    rebalance_days: int,
    alignment: dict[str, str],
) -> str | None:
    if dd_pct >= trail_dd:
        return "TREND_DAILY_TRAIL_STOP"
    return None


def _close_position(
    p: dict[str, Any],
    *,
    exit_date: str,
    exit_price: float,
    exit_reason: str,
    peak_price: float,
    dd_pct: float,
    hold_days: int,
    account: dict[str, Any],
) -> None:
    shares = int(p.get("shares") or 0)
    fee_rate = float(p.get("fee_rate") or account.get("fee_rate", DEFAULT_FEE_RATE))
    gross = round(exit_price * shares, 2)
    exit_fee = round(gross * fee_rate, 2)
    cash_in = round(gross - exit_fee, 2)
    entry_cash_out = float(p.get("entry_cash_out") or 0.0)
    realized = round(cash_in - entry_cash_out, 2)
    p.update({
        "status": "closed",
        "exit_date": exit_date,
        "exit_price": round(exit_price, 4),
        "exit_fee": exit_fee,
        "exit_cash_in": cash_in,
        "realized_pnl": realized,
        "exit_reason": exit_reason,
        "trend_exit_peak": round(peak_price, 4),
        "trend_exit_dd_pct": round(dd_pct, 4),
        "trend_hold_days": hold_days,
    })
    p.pop("trend_exit_blocked_date", None)
    p.pop("trend_exit_blocked_reason", None)
    account["cash"] = round(float(account.get("cash", 0.0)) + cash_in, 2)
    account["realized_pnl"] = round(float(account.get("realized_pnl", 0.0)) + realized, 2)
    account["total_fees"] = round(float(account.get("total_fees", 0.0)) + exit_fee, 2)
    account["last_sell_date"] = exit_date
    trade = {
        "ts": _now_iso(),
        "date": exit_date,
        "side": "SELL",
        "book": "T",
        "code": p.get("code"),
        "entry_date": p.get("entry_date"),
        "name": p.get("name", ""),
        "price": round(exit_price, 4),
        "shares": shares,
        "gross_notional": gross,
        "fee": exit_fee,
        "cash_after": account["cash"],
        "realized_pnl": realized,
        "reason": exit_reason,
        "trend_exit_peak": round(peak_price, 4),
        "trend_exit_dd_pct": round(dd_pct, 4),
        "trend_hold_days": hold_days,
        "trend_alignment": p.get("trend_alignment"),
        "trend_alignment_reason": p.get("trend_alignment_reason"),
        "trend_switch_policy": p.get("trend_switch_policy"),
        "trend_switch_est_roundtrip_fee_bps": p.get("trend_switch_est_roundtrip_fee_bps"),
    }
    return trade


def _main_locked() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat(), help="settle through this YYYY-MM-DD date")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    args = ap.parse_args()

    if not POS.exists():
        print("book T: no positions file")
        return
    positions = accounts.load_positions(POS)
    todo = [p for p in positions if p.get("book") == "T" and p.get("status", "open") == "open"]
    if not todo:
        print("book T: nothing to settle")
        return

    settings = load_settings(None)
    client = XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=SQLiteCache(args.cache),
    )
    reconstructed = _load_reconstructed_daily()
    account = _load_account()
    settle_through = str(args.date)[:10]
    # An intraday block can clear later.  At/after the 14:55 execution gate it
    # is final for the session, so a theoretical daily close must not override it.
    blocked_sell_keys = _load_blocked_sell_keys(ALERTS, book="T", not_before_time="14:55")
    settled = 0
    blocked_count = 0
    state_changed = False
    new_trades: list[dict[str, Any]] = []

    for p in todo:
        code = str(p.get("code") or "")
        entry_date = _normal_date(p.get("entry_date"))
        entry_price = _f(p.get("entry_price"))
        if not code or not entry_date or not entry_price:
            continue
        ser = _kline_map(client, code, reconstructed)
        dts = sorted(d for d in ser if d <= settle_through)
        if entry_date not in dts:
            continue
        i0 = dts.index(entry_date)
        if i0 + 1 >= len(dts):
            continue
        i1 = len(dts) - 1
        exit_date = dts[i1]
        close_px = _f(ser[exit_date].get("close"))
        if not close_px:
            continue
        peak = entry_price
        for d in dts[i0 : i1 + 1]:
            high = _f(ser[d].get("high"))
            close = _f(ser[d].get("close"))
            if high:
                peak = max(peak, high)
            elif close:
                peak = max(peak, close)
        dd_pct = (peak - close_px) / peak * 100.0 if peak > 0 else 0.0
        hold_days = i1 - i0
        rebalance_days = int(p.get("trend_rebalance_days") or TREND_REBALANCE_R)
        trail_dd = float(p.get("trend_trail_dd_pct") or TREND_TRAIL_DD)
        fee_rate = float(p.get("fee_rate") or account.get("fee_rate", DEFAULT_FEE_RATE))
        alignment = _trend_alignment_for_position(p)
        _mark_trend_switch_context(p, fee_rate=fee_rate, alignment=alignment)
        reason = _trend_exit_reason(
            dd_pct=dd_pct,
            trail_dd=trail_dd,
            hold_days=hold_days,
            rebalance_days=rebalance_days,
            alignment=alignment,
        )
        if reason is None:
            continue
        block_reason = _settlement_block_reason(
            blocked_sell_keys,
            book="T",
            exit_date=exit_date,
            code=code,
            entry_date=entry_date,
        )
        if block_reason:
            p["trend_exit_blocked_date"] = exit_date
            p["trend_exit_blocked_reason"] = block_reason
            blocked_count += 1
            state_changed = True
            continue
        new_trades.append(_close_position(
            p,
            exit_date=exit_date,
            exit_price=close_px,
            exit_reason=reason,
            peak_price=peak,
            dd_pct=dd_pct,
            hold_days=hold_days,
            account=account,
        ))
        settled += 1
        state_changed = True

    if state_changed:
        accounts.commit_ledger_transaction(
            live_dir=POS.parent,
            positions=positions,
            positions_path=POS,
            account=account,
            account_path=ACCOUNT_T,
            new_trades=new_trades,
            trades_path=TRADES,
        )
    print(f"book T: settled {settled} position(s)")
    if blocked_count:
        print(f"book T: preserved {blocked_count} position(s) due to SELL_BLOCKED liquidity facts")
    print(
        f"account T: cash={float(account.get('cash', 0.0)):,.2f} "
        f"realized={float(account.get('realized_pnl', 0.0)):+,.2f} "
        f"fees={float(account.get('total_fees', 0.0)):,.2f}"
    )


def main() -> None:
    with accounts.ledger_lock(accounts.ledger_lock_path(POS.parent)):
        accounts.recover_ledger_transaction(POS.parent)
        _main_locked()


if __name__ == "__main__":
    main()
