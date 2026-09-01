"""Live position monitor — poll minute_line and make time-aware sell decisions.

Reads `output/live/positions.jsonl` (user-maintained, one JSON per line) and
for each open position:

  1. Fetches today's minute_line up to current minute
  2. Tracks running peak from entry_price up through latest minute
  3. Computes drawdown_from_peak = (peak - latest) / peak * 100
  4. Applies hard trailing-stop risk control (v5=2.0% / v6=0.5%)
  5. For stale positions (entry_date < today), applies:
       - post-09:35 early rotation exit unless the stock is clearly becoming
         a leader / near limit-up
       - 14:55 discipline exit unless the stock still meets that stronger hold
         exception
  6. Otherwise → HOLD with current diagnostics

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
import time as _time
from datetime import date as _date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.strategy.regime import (  # noqa: E402
    classify_regime,
    limit_down_count,
    limit_up_count,
    negative_total,
    positive_total,
)
from xiaocao.utils.trading_session import A_SHARE_TZ  # noqa: E402
from xiaocao.live.exit_policy import (  # noqa: E402
    AFTERNOON_TIGHTEN_TIME,
    EOD_DISCIPLINE_TIME,
    MIDDAY_REVIEW_TIME,
    MORNING_REVIEW_TIME,
    PROFILE_DD,
    PROFILE_HARD_DD,
    clamp as _clamp,
    decide_sell_action as _decide_sell_action,
    decision_score_context as _decision_score_context,
    market_now as _market_now,
    realtime_strength_context as _realtime_strength_context,
    sell_block_reason as _sell_block_reason,
    strong_hold_reason as _strong_hold_reason,
)
from xiaocao.live import accounts, contexts, intelligence_policy, journal, paper_exit  # noqa: E402
from xiaocao.live.instrument_contract import (  # noqa: E402
    InstrumentContractError,
    contract_from_record,
    has_explicit_instrument_contract,
    is_sellable,
)
from xiaocao.live.notify import notify as _notify  # noqa: E402
from xiaocao.strategy.params import TREND_BUDGET_RATIO, TREND_REBALANCE_R, TREND_TRAIL_DD  # noqa: E402

OUT_DIR = ROOT / "output" / "live"
POSITIONS_FILE = OUT_DIR / "positions.jsonl"
ALERTS_FILE = OUT_DIR / "alerts.jsonl"
ACCOUNT_FILE = OUT_DIR / "paper_account.json"
ACCOUNT_T_FILE = OUT_DIR / "paper_account_T.json"
TRADES_FILE = OUT_DIR / "paper_trades.jsonl"
HOLDINGS_FILE = OUT_DIR / "paper_holdings.json"
HOLDINGS_T_FILE = OUT_DIR / "paper_holdings_T.json"
HOLDING_SNAPSHOTS_FILE = OUT_DIR / "paper_holdings_snapshots.jsonl"
HOLDING_T_SNAPSHOTS_FILE = OUT_DIR / "paper_holdings_T_snapshots.jsonl"
STOCK_SENTIMENT_FILE = OUT_DIR / "stock_sentiment.json"
SIGNAL_SNAPSHOTS_FILE = OUT_DIR / "signal_snapshots.jsonl"

# PROFILE_DD / PROFILE_HARD_DD and the phase-time constants now live in
# xiaocao.live.exit_policy (imported above) — the single importable source for the
# staged-exit rules. The live loop executes decide_sell_action from there; a
# backtest *can* import the same module for 回测=实盘 parity, but the existing
# backtest_intraday_stop.py is a separate comparison harness that does NOT import
# it yet (parity available by construction, not yet exercised). See
# docs/OPERATING_CONTRACT.md §4 and src/xiaocao/live/exit_policy.py.
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
TRADE_CAL_RETRIES = 3
TRADE_CAL_RETRY_BACKOFF_SECONDS = 2.0


class TradingCalendarLookupError(RuntimeError):
    """Raised when the trade calendar API is unavailable."""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Account/position I/O is defined once in xiaocao.live.accounts (the real-money
# state SSOT, shared with paper_record); these are thin wrappers binding it to
# this script's path/constant defaults so existing call sites are unchanged.
def _account_file(book: str) -> Path:
    return ACCOUNT_T_FILE if book == "T" else ACCOUNT_FILE


def _holdings_file(book: str) -> Path:
    return HOLDINGS_T_FILE if book == "T" else HOLDINGS_FILE


def _holding_snapshots_file(book: str) -> Path:
    return HOLDING_T_SNAPSHOTS_FILE if book == "T" else HOLDING_SNAPSHOTS_FILE


def _load_account(book: str = "B") -> dict:
    initial = DEFAULT_STARTING_CAPITAL * TREND_BUDGET_RATIO if book == "T" else DEFAULT_STARTING_CAPITAL
    return accounts.load_account(_account_file(book), initial, DEFAULT_FEE_RATE)


def _save_account(account: dict, book: str = "B") -> None:
    accounts.save_account(account, _account_file(book))


def _append_trade(record: dict) -> None:
    accounts.append_trade(record, TRADES_FILE)


def _position_key(position: dict) -> tuple[str, str]:
    return accounts.position_key(position)


def _write_holdings_snapshot(statuses: list[dict], *, book: str = "B") -> dict:
    account = _load_account(book)
    status_by_key = {_position_key(s): s for s in statuses}
    holdings = []
    total_market_value = 0.0
    total_liquidation_value = 0.0
    total_cost = 0.0
    for p in _load_positions(book):
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
        if has_explicit_instrument_contract(p):
            try:
                contract = contract_from_record(p, strict=True)
                assert contract is not None
                fee_rate = contract.sell_fee_rate
            except InstrumentContractError:
                # Keep valuation conservative and visible for an unverified
                # row; execution remains fail-closed elsewhere.
                fee_rate = float(p.get("sell_fee_rate") or fee_rate)
        market_value = round(shares * latest_price, 2)
        liquidation_value = round(market_value * (1 - fee_rate), 2)
        cost = round(float(p.get("entry_cash_out") or 0.0), 2)
        gross_pnl = round(market_value - float(p.get("gross_notional", cost)), 2)
        net_pnl = round(liquidation_value - cost, 2)
        total_market_value = round(total_market_value + market_value, 2)
        total_liquidation_value = round(total_liquidation_value + liquidation_value, 2)
        total_cost = round(total_cost + cost, 2)
        holdings.append({
            "book": book,
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
        "book": book,
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
    account_path = _account_file(book)
    holdings_path = _holdings_file(book)
    snapshots_path = _holding_snapshots_file(book)
    if not account_path.exists():
        _save_account(account, book)
    holdings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = holdings_path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(holdings_path)
    with snapshots_path.open("a", encoding="utf-8") as f:
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
    def _mark_source(row: dict) -> dict:
        result = dict(row)
        result.setdefault("code", code)
        result.setdefault("_source", "xiaocao_api")
        return result

    try:
        payload = client.second_line_detail_info(code)
    except Exception:
        return {}
    if isinstance(payload, dict):
        if isinstance(payload.get(code), dict):
            return _mark_source(payload.get(code) or {})
        if payload.get("code") == code:
            return _mark_source(payload)
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row.get("code") == code:
                return _mark_source(row)
    return {}


def _detail_trade_date(detail: dict) -> str:
    raw = str(detail.get("tradeDate") or "")[:10]
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _detail_float(detail: dict, key: str) -> float | None:
    try:
        value = detail.get(key)
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _detail_observed_at(detail: dict, trade_date: str) -> datetime | None:
    raw = str(detail.get("tradeTimestamp") or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=A_SHARE_TZ)
    for fmt in ("%H:%M:%S:%f", "%H:%M:%S", "%H%M%S"):
        try:
            clock = datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
        return datetime.combine(_date.fromisoformat(trade_date), clock, tzinfo=A_SHARE_TZ)
    return None


def _find_code_row(payload: object, code: str) -> dict:
    if isinstance(payload, dict):
        direct = payload.get(code)
        if isinstance(direct, dict):
            return direct
        if payload.get("code") == code:
            return payload
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict) and row.get("code") == code:
                return row
            if isinstance(row, dict) and row.get("stockId") == code:
                return row
    return {}


def _market_sentiment_context(client: XiaocaoClient) -> dict[str, object]:
    try:
        overview = client.market_overview()
    except Exception:
        overview = {}
    if not isinstance(overview, dict):
        overview = {}
    regime = classify_regime(overview)
    pos = positive_total(overview) if overview else 0
    neg = negative_total(overview) if overview else 0
    lu = limit_up_count(overview) if overview else 0
    ld = limit_down_count(overview) if overview else 0
    breadth = (pos - neg) / (pos + neg + 1e-9) if (pos or neg) else 0.0
    extreme = (lu - ld) / (lu + ld + 10.0)
    regime_base = {
        "bear": -0.9,
        "divergence": -0.45,
        "neutral": 0.0,
        "recovery": 0.2,
        "trend_continuing": 0.55,
        "trend_strong": 0.85,
    }.get(regime, 0.0)
    score = _clamp(0.55 * breadth + 0.20 * extreme + 0.25 * regime_base)
    return {
        "overview": overview,
        "regime": regime,
        "positive_total": pos,
        "negative_total": neg,
        "limit_up_count": lu,
        "limit_down_count": ld,
        "score": round(score, 4),
    }


def _smallgrass_context(client: XiaocaoClient, code: str) -> dict[str, object]:
    try:
        payload = client.get_technical_index(stock_ids=code, indicator="smallGrass")
    except Exception:
        payload = []
    row = _find_code_row(payload, code)
    if not row:
        return {"score": 0.0, "source": "missing"}

    pieces: list[float] = []

    def _f(key: str) -> float | None:
        try:
            value = row.get(key)
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    ema = _f("ema")
    aaa = _f("aaaLine")
    bbb = _f("bbbLine")
    nline = _f("nline")
    mline = _f("mline")

    if ema is not None and aaa is not None:
        pieces.append(_clamp((ema - aaa) / 40.0))
    if aaa is not None and bbb is not None:
        pieces.append(_clamp((aaa - bbb) / 20.0))
    if ema is not None:
        pieces.append(_clamp((ema - 50.0) / 50.0))
    if nline is not None:
        pieces.append(_clamp((nline - 50.0) / 50.0))
    if mline is not None:
        pieces.append(_clamp((mline - 50.0) / 50.0))

    score = sum(pieces) / len(pieces) if pieces else 0.0
    return {
        "score": round(_clamp(score), 4),
        "source": "smallgrass_proxy",
        "ema": ema,
        "aaaLine": aaa,
        "bbbLine": bbb,
        "nline": nline,
        "mline": mline,
    }


def _load_stock_sentiment_map(today_iso: str) -> dict[str, dict[str, object]]:
    if not STOCK_SENTIMENT_FILE.exists():
        return {}
    try:
        with STOCK_SENTIMENT_FILE.open(encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    def _ingest(item: object, out: dict[str, dict[str, object]]) -> None:
        if not isinstance(item, dict):
            return
        code = str(item.get("code") or item.get("stockId") or "").strip()
        if not code:
            return
        item_date = str(item.get("date") or item.get("tradeDate") or today_iso)[:10]
        if item_date and item_date != today_iso:
            return
        score = item.get("score", item.get("sentiment_score"))
        try:
            score_f = _clamp(float(score))
        except (TypeError, ValueError):
            return
        out[code] = {"score": round(score_f, 4), **item}

    out: dict[str, dict[str, object]] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                item = {"code": key, **value}
                _ingest(item, out)
    elif isinstance(payload, list):
        for item in payload:
            _ingest(item, out)
    return out


# Pure/file-based decision-context builders live in xiaocao.live.contexts (now
# independently unit-tested); thin wrappers bind them to this script's paths.
def _load_signal_snapshot_map() -> dict[tuple[str, str, str], dict[str, object]]:
    return contexts.load_signal_snapshot_map(SIGNAL_SNAPSHOTS_FILE)


def _kronos_context(position: dict, snapshot_map: dict[tuple[str, str, str], dict[str, object]]) -> dict[str, object]:
    return contexts.kronos_context(position, snapshot_map)


def _stock_sentiment_context(
    code: str,
    *,
    smallgrass: dict[str, object],
    sentiment_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    return contexts.stock_sentiment_context(code, smallgrass=smallgrass, sentiment_map=sentiment_map)


def _load_all_positions() -> list[dict]:
    return accounts.load_positions(POSITIONS_FILE)


def _load_positions(book: str = "B") -> list[dict]:
    # book A (validated open->next-close reference) is a pure accounting book
    # settled by settle_book_a.py — never monitored or stop-managed here.
    return [
        p for p in _load_all_positions()
        if p.get("status", "open") == "open" and p.get("book", "B") == book
    ]


def _has_alert_recorded(
    alert_type: str,
    *,
    code: str,
    entry_date: str,
    alert_date: str,
    reason: str | None = None,
    book: str = "B",
) -> bool:
    if not ALERTS_FILE.exists():
        return False
    with ALERTS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(row.get("ts") or "")
            row_date = ts[:10]
            if row.get("alert") != alert_type:
                continue
            if str(row.get("book") or "B") != book:
                continue
            if str(row.get("code") or "") != code:
                continue
            if str(row.get("entry_date") or "") != entry_date:
                continue
            if row_date != alert_date:
                continue
            if reason is not None and str(row.get("reason") or row.get("sell_reason") or "") != reason:
                continue
            return True
    return False


def _execute_simulated_sells(client: XiaocaoClient, triggered_alerts: list[dict], *, book: str = "B") -> tuple[int, int]:
    today_iso = _date.today().isoformat()
    initial = (
        DEFAULT_STARTING_CAPITAL * TREND_BUDGET_RATIO
        if book == "T"
        else DEFAULT_STARTING_CAPITAL
    )
    return paper_exit.execute_simulated_sells(
        triggered_alerts,
        book=book,
        live_dir=OUT_DIR,
        positions_path=POSITIONS_FILE,
        account_path=_account_file(book),
        trades_path=TRADES_FILE,
        alerts_path=ALERTS_FILE,
        initial_capital=initial,
        default_fee_rate=DEFAULT_FEE_RATE,
        trade_date=today_iso,
        detail_provider=lambda code: _realtime_detail(client, code),
        timestamp_provider=lambda _alert: _now_iso(),
    )


def _trading_dates_between(start: str, end: str, client: XiaocaoClient) -> list[str]:
    """Return list of YYYY-MM-DD trading days between start and end inclusive."""
    last_error: Exception | None = None
    rows: list[dict] | None = None
    for attempt in range(TRADE_CAL_RETRIES + 1):
        try:
            rows = client.get_trade_cal(start, end, "SSE", 1)
            break
        except Exception as exc:
            last_error = exc
            if attempt >= TRADE_CAL_RETRIES:
                break
            delay = TRADE_CAL_RETRY_BACKOFF_SECONDS * (attempt + 1)
            print(
                f"trade_cal retry {attempt + 1}/{TRADE_CAL_RETRIES} after error: {exc}",
                file=sys.stderr,
            )
            _time.sleep(delay)
    if rows is None:
        raise TradingCalendarLookupError(
            f"trade calendar lookup failed for {start}..{end}: {last_error}"
        ) from last_error
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


def _decide_trend_sell_action(
    position: dict,
    *,
    dd_pct: float,
    t1_blocked: bool,
    hold_days: int,
    dd_threshold: float = TREND_TRAIL_DD,
    now: datetime | None = None,
) -> dict[str, object]:
    """Book T exit policy: wide trailing stop; rebalance waits for paired switch.

    This intentionally does not call short-line strong_hold_reason or composite
    scoring. The trend book has its own lifecycle and cannot suppress Book-B
    exits for the same stock.
    """
    if t1_blocked:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": None,
            "decision_phase": "t1_blocked",
        }
    if dd_pct >= dd_threshold:
        return {
            "triggered": True,
            "sell_reason": "TREND_TRAIL_STOP",
            "hold_reason": None,
            "decision_phase": "trend_risk",
        }
    target_days = int(position.get("trend_rebalance_days") or TREND_REBALANCE_R)
    if hold_days >= target_days and _market_now(now).time() >= EOD_DISCIPLINE_TIME:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": None,
            "decision_phase": "trend_rebalance_due_wait_paired_switch",
        }
    return {
        "triggered": False,
        "sell_reason": None,
        "hold_reason": "TREND_HOLD",
        "decision_phase": "trend_monitor",
    }


def _compute_status(
    client: XiaocaoClient,
    position: dict,
    today_iso: str,
    *,
    book: str,
    market_context: dict[str, object],
    sentiment_map: dict[str, dict[str, object]],
    snapshot_map: dict[tuple[str, str, str], dict[str, object]],
) -> dict:
    """Pull minute data from entry_date through today, compute peak + dd + status."""
    code = position["code"]
    entry_date = position["entry_date"]
    entry_price = float(position["entry_price"])
    profile = position.get("profile", "v5")
    if book == "T":
        dd_threshold = float(position.get("trend_trail_dd_pct") or TREND_TRAIL_DD)
        hard_dd_threshold = dd_threshold
    else:
        dd_threshold = PROFILE_DD.get(profile, 2.0)
        hard_dd_threshold = PROFILE_HARD_DD.get(profile, 8.0)
    entry_fee_rate = float(position.get("fee_rate", 0.0001))
    exit_fee_rate = entry_fee_rate

    # Trading days from entry_date to today
    trade_days = _trading_dates_between(entry_date, today_iso, client)
    if not trade_days:
        # Fallback: just today if we can't get cal
        trade_days = [today_iso]
    hold_days = max(0, len(trade_days) - 1)

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

    detail = _realtime_detail(client, code)
    detail_trade = _detail_float(detail, "trade")
    detail_high = _detail_float(detail, "high")
    detail_date = _detail_trade_date(detail)
    detail_ts = str(detail.get("tradeTimestamp") or "")
    detail_observed_at = _detail_observed_at(detail, today_iso)

    # Use realtime trade to mark current PnL. T+1 blocks selling, not valuation.
    if detail_date == today_iso and detail_trade and detail_trade > 0:
        latest_price = detail_trade
        latest_time = f"{today_iso} {detail_ts}".strip()
        if detail_high and detail_high > peak:
            peak = detail_high

    dd_pct = (peak - latest_price) / peak * 100 if peak > 0 else 0.0
    ret_pct = (latest_price - entry_price) / entry_price * 100
    # T+1/T+0 comes from the explicit instrument contract. Legacy equity rows
    # keep the old T+1 behaviour until they are migrated; an ETF without a
    # verified contract is blocked rather than treated as a stock.
    instrument_contract = None
    instrument_contract_status = "legacy_equity"
    sellability_reason = None
    has_instrument_metadata = bool(
        has_explicit_instrument_contract(position)
    )
    if has_instrument_metadata:
        try:
            instrument_contract = contract_from_record(position, strict=True)
            assert instrument_contract is not None
            entry_fee_rate = instrument_contract.buy_fee_rate
            exit_fee_rate = instrument_contract.sell_fee_rate
            t1_blocked = not is_sellable(
                instrument_contract,
                entry_date=entry_date,
                as_of=today_iso,
            )
            instrument_contract_status = "verified"
            if t1_blocked:
                sellability_reason = instrument_contract.settlement_cycle
        except InstrumentContractError as exc:
            t1_blocked = True
            instrument_contract_status = "unverified"
            sellability_reason = str(exc)
    else:
        t1_blocked = (today_iso == entry_date)
    net_ret_pct = (
        (latest_price * (1 - exit_fee_rate))
        / (entry_price * (1 + entry_fee_rate))
        - 1
    ) * 100
    smallgrass_context = _smallgrass_context(client, code)
    stock_sentiment_context = _stock_sentiment_context(
        code,
        smallgrass=smallgrass_context,
        sentiment_map=sentiment_map,
    )
    event_risk = intelligence_policy.event_risk_exit(sentiment_map.get(code))
    kronos_context = _kronos_context(position, snapshot_map)
    realtime_context = _realtime_strength_context(detail, latest_price, peak)
    score_context = _decision_score_context(
        market=market_context,
        stock_sentiment=stock_sentiment_context,
        realtime=realtime_context,
        kronos=kronos_context,
    )
    if book == "T":
        decision = _decide_trend_sell_action(
            position,
            dd_pct=dd_pct,
            dd_threshold=dd_threshold,
            t1_blocked=t1_blocked,
            hold_days=hold_days,
        )
    else:
        decision = _decide_sell_action(
            position,
            detail=detail,
            latest_price=latest_price,
            peak=peak,
            dd_pct=dd_pct,
            dd_threshold=dd_threshold,
            t1_blocked=t1_blocked,
            hold_days=hold_days,
            signal_score=float(score_context.get("composite_score", 0.0) or 0.0),
            event_risk=event_risk,
            hard_dd_threshold=hard_dd_threshold,
        )
    return {
        "book": book,
        "code": code,
        "name": position.get("name", ""),
        "profile": profile,
        "dd_threshold_pct": dd_threshold,
        "hard_dd_threshold_pct": hard_dd_threshold,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "peak": round(peak, 4),
        "latest_price": round(latest_price, 4),
        "latest_time": latest_time,
        "market_guard_status": detail.get("tradeStatus"),
        "market_guard_observed_at": (
            detail_observed_at.isoformat()
            if detail_observed_at is not None
            else None
        ),
        "market_guard_down_price": _detail_float(detail, "downPrice"),
        "sell_block_reason": _sell_block_reason(detail),
        "dd_pct": round(dd_pct, 4),
        "ret_pct": round(ret_pct, 4),
        "net_ret_pct": round(net_ret_pct, 4),
        "fee_rate": entry_fee_rate,
        "entry_fee_rate": entry_fee_rate,
        "exit_fee_rate": exit_fee_rate,
        "days_processed": days_processed,
        "hold_days": hold_days,
        "t1_blocked": t1_blocked,
        "instrument_contract_status": instrument_contract_status,
        "sellability_reason": sellability_reason,
        "lot_size": instrument_contract.lot_size if instrument_contract is not None else position.get("lot_size", 100),
        "strong_hold_reason": decision["hold_reason"],
        "sell_reason": decision["sell_reason"],
        "deferred_sell_reason": decision.get("deferred_sell_reason"),
        "decision_phase": decision["decision_phase"],
        "triggered": bool(decision["triggered"]),
        "ai_event_risk_exit": bool(event_risk.get("triggered")),
        "ai_event_risk_event_types": event_risk.get("event_types") or [],
        "ai_event_risk_reason": event_risk.get("reason") or "",
        **score_context,
        "market_regime": market_context.get("regime"),
        "stock_sentiment_source": stock_sentiment_context.get("source"),
        "smallgrass_score": smallgrass_context.get("score"),
        "kronos_p_score": kronos_context.get("p_score"),
        "kronos_k_score": kronos_context.get("k_score"),
        "shares": position.get("shares"),
    }


def _decision_packet(statuses: list[dict], snapshot: dict) -> dict:
    """Compact the per-position statuses into one deterministic decision packet
    for the journal — so a later fresh-context agent consumes structured state
    instead of re-scraping holdings/alerts/positions files."""
    triggered = [
        {"book": s.get("book", "B"), "code": s["code"], "name": s.get("name"), "sell_reason": s.get("sell_reason")}
        for s in statuses if s.get("triggered")
    ]
    deferred = [
        {"book": s.get("book", "B"), "code": s["code"], "name": s.get("name"), "deferred_sell_reason": s.get("deferred_sell_reason")}
        for s in statuses if s.get("deferred_sell_reason")
    ]
    holds = [
        {"book": s.get("book", "B"), "code": s["code"], "name": s.get("name"), "reason": s.get("strong_hold_reason") or s.get("decision_phase")}
        for s in statuses if not s.get("triggered") and not s.get("deferred_sell_reason")
    ]
    positions = [
        {
            "book": s.get("book", "B"),
            "code": s["code"], "name": s.get("name"),
            "dd_pct": s.get("dd_pct"), "ret_pct": s.get("ret_pct"), "net_ret_pct": s.get("net_ret_pct"),
            "composite_score": s.get("composite_score"), "decision_phase": s.get("decision_phase"),
            "sell_reason": s.get("sell_reason"), "deferred_sell_reason": s.get("deferred_sell_reason"),
            "strong_hold_reason": s.get("strong_hold_reason"), "t1_blocked": s.get("t1_blocked"),
        }
        for s in statuses
    ]
    return {
        "book": snapshot.get("book", "B"),
        "open_positions": snapshot.get("open_positions"),
        "cash": snapshot.get("cash"),
        "equity": snapshot.get("total_equity_after_exit_fee"),
        "triggered": triggered,
        "deferred": deferred,
        "holds": holds,
        "positions": positions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", help="只检查指定 code")
    parser.add_argument("--book", choices=["B", "T"], default="B",
                        help="which paper book to monitor; default B (short-line)")
    parser.add_argument("--no-notify", action="store_true",
                        help="禁用 macOS 通知（保留 stdout + alerts.jsonl）")
    parser.add_argument("--execute-sells", action="store_true",
                        help="触发 T+1 止损时执行模拟卖出，更新 positions/account/trades")
    args = parser.parse_args()

    client = _client()
    today_iso = _date.today().isoformat()
    try:
        is_trading_day, latest_trading_day = _is_trading_day(today_iso, client)
    except TradingCalendarLookupError as exc:
        print(f"Trading calendar lookup failed; skip live monitor ({exc})", file=sys.stderr)
        raise SystemExit(2)
    if not is_trading_day:
        print(
            f"Non-trading day; skip live monitor "
            f"(today={today_iso}, latest_trading={latest_trading_day or 'unknown'})"
        )
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    book = args.book
    positions = _load_positions(book)
    if args.code:
        positions = [p for p in positions if p.get("code") == args.code]
    if not positions:
        snapshot = _write_holdings_snapshot([], book=book)
        print(f"No open Book {book} positions in {POSITIONS_FILE.relative_to(ROOT)}")
        print(
            f"Account: cash={snapshot['cash']:.2f}, "
            f"equity={snapshot['total_equity_after_exit_fee']:.2f}, "
            f"open_positions=0"
        )
        journal.append_decision(
            automation="live_monitor" if book == "B" else "live_monitor_book_t",
            market_date=today_iso,
            path=OUT_DIR / "decision_journal.jsonl",
            deterministic=_decision_packet([], snapshot),
            posture={},
        )
        return

    market_context = _market_sentiment_context(client)
    sentiment_map = _load_stock_sentiment_map(today_iso)
    snapshot_map = _load_signal_snapshot_map()

    print(f"Monitoring {len(positions)} open Book {book} position(s) at {today_iso}\n")
    print(
        f"Market regime={market_context.get('regime')} "
        f"score={float(market_context.get('score', 0.0)):+.2f} "
        f"(pos={market_context.get('positive_total', 0)}, neg={market_context.get('negative_total', 0)}, "
        f"lu={market_context.get('limit_up_count', 0)}, ld={market_context.get('limit_down_count', 0)})\n"
    )
    print(f"{'code':<14} {'profile':<6} {'entry':>7} {'peak':>7} {'latest':>7} "
          f"{'dd':>7} {'ret':>7} {'net':>7} {'score':>7} {'status':<28}")
    print("-" * 120)

    triggered_alerts = []
    statuses = []
    try:
        for p in positions:
            s = _compute_status(
                client,
                p,
                today_iso,
                book=book,
                market_context=market_context,
                sentiment_map=sentiment_map,
                snapshot_map=snapshot_map,
            )
            statuses.append(s)
            status_label = (
                f"🔔 {s['sell_reason']}"
                if s["triggered"] else
                f"defer:{s['deferred_sell_reason']}"
                if s.get("deferred_sell_reason") else
                f"hold:{s['strong_hold_reason']}"
                if s.get("strong_hold_reason") else
                "T+1_blocked" if s["t1_blocked"] else
                f"hold:{s['decision_phase']}"
            )
            print(
                f"{s['code']:<14} {s['profile']:<6} {s['entry_price']:>7.2f} "
                f"{s['peak']:>7.2f} {s['latest_price']:>7.2f} "
                f"{s['dd_pct']:>+6.2f}% {s['ret_pct']:>+6.2f}% "
                f"{s['net_ret_pct']:>+6.2f}% {s['composite_score']:>+6.2f} "
                f"{status_label:<28}"
            )
            if s.get("strong_hold_reason"):
                with ALERTS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": _now_iso(),
                        "alert": "SELL_SUPPRESSED_STRONG_HOLD",
                        **s,
                    }, ensure_ascii=False) + "\n")
            if s.get("deferred_sell_reason"):
                # diagnosed intraday, executed at the 14:55 pass — recorded so
                # forward eval can compare deferred vs immediate exit prices
                if not _has_alert_recorded(
                    "SELL_DEFERRED",
                    code=str(s.get("code") or ""),
                    entry_date=str(s.get("entry_date") or ""),
                    alert_date=_date.today().isoformat(),
                    reason=str(s.get("deferred_sell_reason") or ""),
                    book=book,
                ):
                    with ALERTS_FILE.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "ts": _now_iso(),
                            "alert": "SELL_DEFERRED",
                            "book": book,
                            "reason": s.get("deferred_sell_reason"),
                            **s,
                        }, ensure_ascii=False) + "\n")
            if s["triggered"]:
                triggered_alerts.append(s)
    except TradingCalendarLookupError as exc:
        print(f"Trading calendar lookup failed during position scan ({exc})", file=sys.stderr)
        raise SystemExit(2)

    if triggered_alerts:
        print(f"\n🔔 {len(triggered_alerts)} 个 SELL 信号触发")
        for s in triggered_alerts:
            msg = (
                f"卖 {s['name']} ({s['code']}) — "
                f"{s['sell_reason']}；"
                f"dd {s['dd_pct']:+.2f}% / 阈值 {s['dd_threshold_pct']:.1f}% "
                f"({s['profile']}); 当前 {s['latest_price']:.2f} (entry {s['entry_price']:.2f}, "
                f"peak {s['peak']:.2f}, ret {s['ret_pct']:+.2f}%, "
                f"net {s['net_ret_pct']:+.2f}% after fee {s['fee_rate']:.4%}, "
                f"hold_days {s['hold_days']}, composite {s['composite_score']:+.2f}, "
                f"market {s['market_score']:+.2f}/stock {s['stock_sentiment_score']:+.2f}/"
                f"rt {s['realtime_score']:+.2f}/kronos {s['kronos_score']:+.2f})"
            )
            print("  " + msg)
            today_iso = _date.today().isoformat()
            already_logged = _has_alert_recorded(
                "SELL_TRIGGERED",
                code=str(s.get("code") or ""),
                entry_date=str(s.get("entry_date") or ""),
                alert_date=today_iso,
                reason=str(s.get("sell_reason") or ""),
                book=book,
            )
            if not already_logged:
                if not args.no_notify:
                    # macOS popup + WeCom relay (when XIAOCAO_WECOM_* is set)
                    _notify(f"卖点触发 {s['code']}", msg, macos=True)
                with ALERTS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": today_iso,
                        "alert": "SELL_TRIGGERED",
                        "book": book,
                        **s,
                    }, ensure_ascii=False) + "\n")
        if args.execute_sells:
            closed, blocked = _execute_simulated_sells(client, triggered_alerts, book=book)
            account = _load_account(book)
            print(
                f"\nSimulated sells executed: {closed}; "
                f"blocked={blocked}; "
                f"cash={float(account.get('cash', 0.0)):.2f}, "
                f"realized_pnl={float(account.get('realized_pnl', 0.0)):+.2f}, "
                f"total_fees={float(account.get('total_fees', 0.0)):.2f}"
            )
    else:
        print(f"\nNo sell triggers. {sum(1 for p in positions)} position(s) holding.")
    snapshot = _write_holdings_snapshot(statuses, book=book)
    print(
        f"Holdings snapshot: cash={snapshot['cash']:.2f}, "
        f"holdings_value={snapshot['liquidation_value_after_fee']:.2f}, "
        f"equity={snapshot['total_equity_after_exit_fee']:.2f}, "
        f"open_positions={snapshot['open_positions']} -> "
        f"{_holdings_file(book).relative_to(ROOT)}"
    )
    journal.append_decision(
        automation="live_monitor" if book == "B" else "live_monitor_book_t",
        market_date=today_iso,
        path=OUT_DIR / "decision_journal.jsonl",
        deterministic=_decision_packet(statuses, snapshot),
        posture={
            "regime": market_context.get("regime"),
            "score": round(float(market_context.get("score", 0.0) or 0.0), 4),
            "positive_total": market_context.get("positive_total"),
            "negative_total": market_context.get("negative_total"),
            "limit_up_count": market_context.get("limit_up_count"),
            "limit_down_count": market_context.get("limit_down_count"),
        },
    )


if __name__ == "__main__":
    main()
