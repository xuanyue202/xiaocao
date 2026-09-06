"""Staged exit policy — the deterministic exit decision shared by the live
monitor and backtest replay (so 回测 = 实盘 by construction).

Extracted verbatim from scripts/live_monitor.py. Behaviour is unchanged; this
module exists so the staged-exit rules become independently importable and
unit-testable, and so backtest tooling *can* be wired to replay the same
decide_sell_action the live loop executes (delivering 回测=实盘 parity for the
stop layer). NOTE: backtest_intraday_stop.py is a separate policy-COMPARISON
harness (it replays next_close/sparse/hard8/… alternatives, not the production
decision) and does not import this module — so the parity is available by
construction but not yet exercised by an existing backtest. See
docs/OPERATING_CONTRACT.md §4.

Key invariant (validated via decompose_pnl on the 06-01..06-12 book): intraday
checkpoints only EXECUTE the hard floor; ordinary trailing/composite exits are
DIAGNOSED intraday and executed at the 14:55 discipline pass, because sparse
checkpoints otherwise turn a 2% trailing stop into a "sell the D+1 morning low"
rule. The validated exit reference is the next close.
"""
from __future__ import annotations

from datetime import datetime, time

from xiaocao.utils.trading_session import A_SHARE_TZ
# Drawdown thresholds live in the parameter registry (the frozen-vs-tunable SSOT).
#   PROFILE_DD      : soft trailing dd%% per profile, executed at 14:55 not intraday
#   PROFILE_HARD_DD : intraday hard floor — the only stop executed at intraday checkpoints
from xiaocao.strategy.params import PROFILE_DD, PROFILE_HARD_DD  # noqa: F401

MORNING_REVIEW_TIME = time(9, 35)
MIDDAY_REVIEW_TIME = time(10, 30)
AFTERNOON_TIGHTEN_TIME = time(14, 0)
EOD_DISCIPLINE_TIME = time(14, 55)


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def market_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(A_SHARE_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=A_SHARE_TZ)
    return now.astimezone(A_SHARE_TZ)


def realtime_strength_context(detail: dict, latest_price: float, peak: float) -> dict[str, object]:
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

    near_high = clamp((latest_price / max(high, 1e-9) - 0.985) / 0.015)
    open_follow = clamp((latest_price / max(open_px, 1e-9) - 1.0) / 0.05)
    order_imb = clamp((buy_vol1 - sell_vol1) / (buy_vol1 + sell_vol1 + 1e-9))
    flow_imb = clamp((vol_in - vol_out) / (vol_in + vol_out + 1e-9))
    limit_prox = 0.0
    if up_price and up_price > 0:
        limit_prox = clamp((latest_price / up_price - 0.97) / 0.03)

    score = clamp(
        0.30 * clamp(pct_change / 8.0)
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


def decision_score_context(
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
    composite = clamp(
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


def sell_block_reason(detail: dict) -> str | None:
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


def strong_hold_reason(
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


def decide_sell_action(
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
    event_risk: dict[str, object] | None = None,
    kol_exit: dict[str, object] | None = None,
    hard_dd_threshold: float = 8.0,
    now: datetime | None = None,
) -> dict[str, object]:
    now_time = market_now(now).time()
    soft_hold_reason = strong_hold_reason(position, detail, latest_price, peak, strict=False)

    if t1_blocked:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": None,
            "decision_phase": "t1_blocked",
        }

    if event_risk and event_risk.get("triggered"):
        return {
            "triggered": True,
            "sell_reason": "AI_EVENT_RISK_EXIT",
            "hold_reason": None,
            "decision_phase": "event_risk",
            "event_risk": event_risk,
        }

    # Staged execution: intraday checkpoints only EXECUTE the hard floor
    # (catastrophic damage / liquidity escape). Ordinary trailing-stop or
    # composite deterioration is DIAGNOSED intraday (deferred_sell_reason,
    # recorded for forward evaluation) and executed at the 14:55 discipline
    # pass. Rationale (decompose_pnl on the 06-01..06-12 book): sparse
    # checkpoints turned the 2% trailing stop into a "sell the D+1 morning
    # low" rule; the validated exit reference is next close.
    if dd_pct >= hard_dd_threshold and not soft_hold_reason:
        return {
            "triggered": True,
            "sell_reason": "HARD_STOP",
            "hold_reason": None,
            "decision_phase": "risk_floor",
        }

    # The separately reviewed, time-bound KOL consumer supplies this request.
    # It cannot suppress an existing hard/event exit or bypass T+1 above.
    if kol_exit and kol_exit.get("triggered") is True and kol_exit.get("decision_id"):
        return {
            "triggered": True,
            "sell_reason": "KOL_DISCRETIONARY_EXIT",
            "hold_reason": None,
            "decision_phase": "kol_discretionary",
            "kol_decision_id": kol_exit["decision_id"],
        }

    if hold_days < 1:
        return {
            "triggered": False,
            "sell_reason": None,
            "hold_reason": soft_hold_reason,
            "decision_phase": "same_day",
        }

    if now_time >= EOD_DISCIPLINE_TIME:
        strict_hold_reason = strong_hold_reason(position, detail, latest_price, peak, strict=True)
        if strict_hold_reason:
            return {
                "triggered": False,
                "sell_reason": None,
                "hold_reason": strict_hold_reason,
                "decision_phase": "eod_discipline",
            }
        # attribute correctly: stop condition met -> TRAILING_STOP (executed
        # at the discipline pass), otherwise plain discipline exit
        return {
            "triggered": True,
            "sell_reason": "TRAILING_STOP" if dd_pct >= dd_threshold else "EOD_DISCIPLINE_1455",
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

    deferred_sell_reason = None
    if signal_score <= sell_cut:
        deferred_sell_reason = sell_reason
    elif dd_pct >= dd_threshold and not soft_hold_reason:
        deferred_sell_reason = "TRAILING_STOP"
    if deferred_sell_reason:
        # diagnosed intraday, executed at >= 14:55 (or earlier by hard floor)
        return {
            "triggered": False,
            "sell_reason": None,
            "deferred_sell_reason": deferred_sell_reason,
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
