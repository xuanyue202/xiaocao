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

OUT_DIR = ROOT / "output" / "live"
POSITIONS_FILE = OUT_DIR / "positions.jsonl"
ALERTS_FILE = OUT_DIR / "alerts.jsonl"
ACCOUNT_FILE = OUT_DIR / "paper_account.json"
TRADES_FILE = OUT_DIR / "paper_trades.jsonl"
HOLDINGS_FILE = OUT_DIR / "paper_holdings.json"
HOLDING_SNAPSHOTS_FILE = OUT_DIR / "paper_holdings_snapshots.jsonl"
STOCK_SENTIMENT_FILE = OUT_DIR / "stock_sentiment.json"
SIGNAL_SNAPSHOTS_FILE = OUT_DIR / "signal_snapshots.jsonl"

PROFILE_DD = {"v5": 2.0, "v6": 0.5}
DEFAULT_STARTING_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001
MORNING_REVIEW_TIME = time(9, 35)
MIDDAY_REVIEW_TIME = time(10, 30)
AFTERNOON_TIGHTEN_TIME = time(14, 0)
EOD_DISCIPLINE_TIME = time(14, 55)
TRADE_CAL_RETRIES = 3
TRADE_CAL_RETRY_BACKOFF_SECONDS = 2.0


class TradingCalendarLookupError(RuntimeError):
    """Raised when the trade calendar API is unavailable."""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _market_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(A_SHARE_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=A_SHARE_TZ)
    return now.astimezone(A_SHARE_TZ)


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


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


def _load_signal_snapshot_map() -> dict[tuple[str, str], dict[str, object]]:
    if not SIGNAL_SNAPSHOTS_FILE.exists():
        return {}
    out: dict[tuple[str, str], dict[str, object]] = {}
    with SIGNAL_SNAPSHOTS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            code = str(row.get("code") or "")
            date = str(row.get("date") or "")[:10]
            if not code or not date:
                continue
            key = (date, code)
            prev = out.get(key)
            if prev is None or str(row.get("captured_at") or "") >= str(prev.get("captured_at") or ""):
                out[key] = row
    return out


def _kronos_context(position: dict, snapshot_map: dict[tuple[str, str], dict[str, object]]) -> dict[str, object]:
    code = str(position.get("code") or "")
    entry_date = str(position.get("entry_date") or "")[:10]
    row = snapshot_map.get((entry_date, code), {})

    def _num(key: str) -> float | None:
        value = row.get(key, position.get(key))
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    p_score = _num("p_score")
    k_score = _num("k_score")
    score = 0.0
    if p_score is not None:
        score += 0.6 * _clamp(p_score / 3.0)
    if k_score is not None:
        score += 0.2 * _clamp(k_score / 3.0)
    if bool(row.get("vb_star", position.get("vb_star", False))):
        score += 0.2
    elif bool(row.get("kp_star", position.get("kp_star", False))):
        score += 0.1
    return {
        "score": round(_clamp(score), 4),
        "p_score": p_score,
        "k_score": k_score,
        "vb_star": bool(row.get("vb_star", position.get("vb_star", False))),
        "kp_star": bool(row.get("kp_star", position.get("kp_star", False))),
    }


def _stock_sentiment_context(
    code: str,
    *,
    smallgrass: dict[str, object],
    sentiment_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    external = sentiment_map.get(code)
    proxy_score = float(smallgrass.get("score", 0.0) or 0.0)
    if external is not None:
        ext_score = float(external.get("score", 0.0) or 0.0)
        score = _clamp(0.7 * ext_score + 0.3 * proxy_score)
        source = "external+smallgrass"
    else:
        ext_score = None
        score = _clamp(proxy_score)
        source = str(smallgrass.get("source") or "smallgrass_proxy")
    return {
        "score": round(score, 4),
        "source": source,
        "external_score": ext_score,
        "proxy_score": round(proxy_score, 4),
    }


def _realtime_strength_context(detail: dict, latest_price: float, peak: float) -> dict[str, object]:
    if not detail:
        return {"score": 0.0, "source": "missing"}

    def _f(key: str) -> float | None:
        try:
            value = detail.get(key)
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    pct_change = _f("pctChangeRate") or 0.0
    high = _f("high") or latest_price
    open_px = _f("open") or latest_price
    up_price = _f("upPrice")
    buy_vol1 = _f("buyVol1") or 0.0
    sell_vol1 = _f("sellVol1") or 0.0
    vol_in = _f("volIn") or 0.0
    vol_out = _f("volOut") or 0.0

    near_high = _clamp((latest_price / max(high, 1e-9) - 0.985) / 0.015)
    open_follow = _clamp((latest_price / max(open_px, 1e-9) - 1.0) / 0.05)
    order_imb = _clamp((buy_vol1 - sell_vol1) / (buy_vol1 + sell_vol1 + 1e-9))
    flow_imb = _clamp((vol_in - vol_out) / (vol_in + vol_out + 1e-9))
    limit_prox = 0.0
    if up_price and up_price > 0:
        limit_prox = _clamp((latest_price / up_price - 0.97) / 0.03)

    score = _clamp(
        0.30 * _clamp(pct_change / 8.0)
        + 0.20 * near_high
        + 0.20 * open_follow
        + 0.15 * order_imb
        + 0.10 * flow_imb
        + 0.05 * limit_prox
    )
    return {
        "score": round(score, 4),
        "pct_change_rate": pct_change,
        "near_high": round(near_high, 4),
        "open_follow": round(open_follow, 4),
        "order_imbalance": round(order_imb, 4),
        "flow_imbalance": round(flow_imb, 4),
        "limit_proximity": round(limit_prox, 4),
        "peak": peak,
    }


def _decision_score_context(
    *,
    market: dict[str, object],
    stock_sentiment: dict[str, object],
    realtime: dict[str, object],
    kronos: dict[str, object],
) -> dict[str, object]:
    market_score = float(market.get("score", 0.0) or 0.0)
    stock_score = float(stock_sentiment.get("score", 0.0) or 0.0)
    realtime_score = float(realtime.get("score", 0.0) or 0.0)
    kronos_score = float(kronos.get("score", 0.0) or 0.0)
    composite = _clamp(
        0.30 * market_score
        + 0.25 * stock_score
        + 0.30 * realtime_score
        + 0.15 * kronos_score
    )
    return {
        "market_score": round(market_score, 4),
        "stock_sentiment_score": round(stock_score, 4),
        "realtime_score": round(realtime_score, 4),
        "kronos_score": round(kronos_score, 4),
        "composite_score": round(composite, 4),
    }


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
    # A limit-down stock with no best-bid liquidity cannot be sold in reality.
    # The realtime feed can round `trade`, so allow a tiny tolerance around the
    # official downPrice instead of requiring exact float equality.
    tolerance = max(0.01, down_price * 0.0005) if down_price > 0 else 0.0
    if down_price > 0 and trade > 0 and trade <= down_price + tolerance and buy_vol1 <= 0:
        return "LIMIT_DOWN_NO_BID"
    return None


def _strong_hold_reason(
    position: dict,
    detail: dict,
    latest_price: float,
    peak: float,
    *,
    strict: bool = False,
) -> str | None:
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
    if pct_change_rate >= 9.5:
        return "LIMIT_UP_DAY"
    if is_trend_leader and pct_change_rate >= 8.0 and day_high > 0 and latest_price >= day_high * 0.995:
        return "TURNED_LEADER_NEAR_HIGH"
    if strict:
        return None
    if is_trend_leader and peak > 0 and latest_price >= peak * 0.995 and pct_change_rate >= 6.0:
        return "STRONG_TREND_HOLD"
    return None


def _decide_sell_action(
    position: dict,
    *,
    detail: dict,
    latest_price: float,
    peak: float,
    dd_pct: float,
    dd_threshold: float,
    t1_blocked: bool,
    hold_days: int,
    signal_score: float = 0.0,
    now: datetime | None = None,
) -> dict[str, object]:
    now_time = _market_now(now).time()
    soft_hold_reason = _strong_hold_reason(position, detail, latest_price, peak, strict=False)

    if t1_blocked:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": None,
            "decision_phase": "t1_blocked",
        }

    # Hard risk floor always comes first unless the stock is clearly proving it
    # is turning into a leader / limit-up style exception.
    if dd_pct >= dd_threshold and not soft_hold_reason:
        return {
            "triggered": True,
            "sell_reason": "TRAILING_STOP",
            "hold_reason": None,
            "decision_phase": "risk_floor",
        }

    if hold_days < 1:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": soft_hold_reason,
            "decision_phase": "same_day",
        }

    if now_time >= EOD_DISCIPLINE_TIME:
        strict_hold_reason = _strong_hold_reason(position, detail, latest_price, peak, strict=True)
        if strict_hold_reason:
            return {
                "triggered": False,
                "sell_reason": None,
                "hold_reason": strict_hold_reason,
                "decision_phase": "eod_discipline",
            }
        return {
            "triggered": True,
            "sell_reason": "EOD_DISCIPLINE_1455",
            "hold_reason": None,
            "decision_phase": "eod_discipline",
        }

    if now_time < MORNING_REVIEW_TIME:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": soft_hold_reason,
            "decision_phase": "opening_buffer",
        }

    if now_time < MIDDAY_REVIEW_TIME:
        phase = "morning_assessment"
        sell_cut = -0.15
        hold_cut = 0.25
        sell_reason = "COMPOSITE_MORNING_EXIT"
    elif now_time < AFTERNOON_TIGHTEN_TIME:
        phase = "midday_reassessment"
        sell_cut = -0.02
        hold_cut = 0.18
        sell_reason = "COMPOSITE_MIDDAY_EXIT"
    else:
        phase = "afternoon_tighten"
        sell_cut = 0.10
        hold_cut = 0.28
        sell_reason = "COMPOSITE_AFTERNOON_EXIT"

    if signal_score <= sell_cut:
        return {
            "triggered": True,
            "sell_reason": sell_reason,
            "hold_reason": None,
            "decision_phase": phase,
        }

    if soft_hold_reason and signal_score >= hold_cut:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": soft_hold_reason,
            "decision_phase": phase,
        }

    return {
        "triggered": False,
        "sell_reason": None,
        "hold_reason": None,
        "decision_phase": phase,
    }


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


def _has_alert_recorded(
    alert_type: str,
    *,
    code: str,
    entry_date: str,
    alert_date: str,
    reason: str | None = None,
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
                today_iso = _date.today().isoformat()
                if not _has_alert_recorded(
                    "SELL_BLOCKED",
                    code=str(p.get("code") or ""),
                    entry_date=str(p.get("entry_date") or ""),
                    alert_date=today_iso,
                    reason=blocked_reason,
                ):
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
                "exit_reason": str(alert.get("sell_reason") or "TRAILING_STOP"),
            })
            _append_trade({
                "ts": _now_iso(), "date": _date.today().isoformat(), "side": "SELL",
                "code": p.get("code"), "name": p.get("name", ""),
                "price": round(exit_price, 4), "shares": shares,
                "gross_notional": gross_notional, "fee": exit_fee,
                "cash_after": account["cash"], "realized_pnl": realized_pnl,
                "reason": str(alert.get("sell_reason") or "TRAILING_STOP"),
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


def _compute_status(
    client: XiaocaoClient,
    position: dict,
    today_iso: str,
    *,
    market_context: dict[str, object],
    sentiment_map: dict[str, dict[str, object]],
    snapshot_map: dict[tuple[str, str], dict[str, object]],
) -> dict:
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

    # Use realtime trade to mark current PnL. T+1 blocks selling, not valuation.
    if detail_date == today_iso and detail_trade and detail_trade > 0:
        latest_price = detail_trade
        latest_time = f"{today_iso} {detail_ts}".strip()
        if detail_high and detail_high > peak:
            peak = detail_high

    dd_pct = (peak - latest_price) / peak * 100 if peak > 0 else 0.0
    ret_pct = (latest_price - entry_price) / entry_price * 100
    net_ret_pct = ((latest_price * (1 - fee_rate)) / (entry_price * (1 + fee_rate)) - 1) * 100

    # T+1 logic: if today == entry_date, we can't sell
    t1_blocked = (today_iso == entry_date)
    smallgrass_context = _smallgrass_context(client, code)
    stock_sentiment_context = _stock_sentiment_context(
        code,
        smallgrass=smallgrass_context,
        sentiment_map=sentiment_map,
    )
    kronos_context = _kronos_context(position, snapshot_map)
    realtime_context = _realtime_strength_context(detail, latest_price, peak)
    score_context = _decision_score_context(
        market=market_context,
        stock_sentiment=stock_sentiment_context,
        realtime=realtime_context,
        kronos=kronos_context,
    )
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
    )
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
        "hold_days": hold_days,
        "t1_blocked": t1_blocked,
        "strong_hold_reason": decision["hold_reason"],
        "sell_reason": decision["sell_reason"],
        "decision_phase": decision["decision_phase"],
        "triggered": bool(decision["triggered"]),
        **score_context,
        "market_regime": market_context.get("regime"),
        "stock_sentiment_source": stock_sentiment_context.get("source"),
        "smallgrass_score": smallgrass_context.get("score"),
        "kronos_p_score": kronos_context.get("p_score"),
        "kronos_k_score": kronos_context.get("k_score"),
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

    market_context = _market_sentiment_context(client)
    sentiment_map = _load_stock_sentiment_map(today_iso)
    snapshot_map = _load_signal_snapshot_map()

    print(f"Monitoring {len(positions)} open position(s) at {today_iso}\n")
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
                market_context=market_context,
                sentiment_map=sentiment_map,
                snapshot_map=snapshot_map,
            )
            statuses.append(s)
            status_label = (
                f"🔔 {s['sell_reason']}"
                if s["triggered"] else
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
            )
            if not already_logged:
                if not args.no_notify:
                    _macos_notify(f"卖点触发 {s['code']}", msg)
                with ALERTS_FILE.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": today_iso,
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
