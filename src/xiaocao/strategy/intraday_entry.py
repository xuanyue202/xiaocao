"""Intraday entry-timing layer (Plan D).

Reads cached `/stock/minute_line` responses (with count param so they're real
historical data), computes intraday entry axes, and exposes filters that the
backtest score function consumes.

Discovered axes (per `reports/intraday_r2_validation_2026-04-26.md`):

  not_at_peak  — drawdown_from_peak ≥ DD_THRESHOLD (default 1.5%):
                 the stock has retraced from the 9:30-9:35 max — entering
                 here gives ~+1.4pp avg / ~+12pp win across both 1d and
                 5d_dd2 frames vs entering at 9:30 open
  weak_open    — REJECTED: anti-predictive on filtered universe
  pct_controlled — REJECTED: anti-predictive on filtered universe

Entry-price convention: when not_at_peak passes, buy at 9:35 close (records[5]
.trade) instead of 9:30 open. This shifts the baseline gain unit by the
9:30-9:35 absolute return, which is what the empirical lift captures.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

# Empirical 8mo TRAIN+TEST result on validated_v3 baseline (73 active trades):
#   STRONG  (drawdown ≤ 1.5%, n=45): 1d avg +4.54% / win 66.7%
#                                    5d_dd2 avg +7.77% / win 68.9%
#   RETRACED (drawdown > 1.5%, n=28): 1d avg +1.56% / win 39.3%
#                                     5d_dd2 avg +4.18% / win 35.7%
# So "still near peak by 9:35" = strong continuation candidate. The lift comes
# from FILTERING (retain STRONG only); 9:35-close entry itself caps upside vs
# 9:30-open entry because you pay the morning-surge premium.
DEFAULT_DD_THRESHOLD = 1.5
WINDOW_MINUTES = 6  # 0930, 0931, ..., 0935 inclusive


def load_minute_cache(
    cache_path: str | Path,
    require_count_param: bool = True,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """{(YYYYMMDD, code): minute records sorted by tradeTime}.

    `require_count_param`: when True (default), skip entries whose params lack
    `count` — those are early probes that silently returned today's data
    despite the tradeDate hint. Empirically only count-bearing entries are
    real historical (see scripts/probe_intraday_history.py + JS bundle K0
    line 9835).
    """
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    try:
        with sqlite3.connect(str(cache_path)) as conn:
            rows = conn.execute(
                "SELECT params_json, response_json FROM api_cache "
                "WHERE endpoint='/stock/minute_line'"
            ).fetchall()
    except sqlite3.Error:
        return {}
    for pj, rj in rows:
        try:
            params = json.loads(pj).get("params", {})
            data = json.loads(rj)
        except (json.JSONDecodeError, AttributeError):
            continue
        if require_count_param and "count" not in params:
            continue
        td = str(params.get("tradeDate") or "")
        code = str(params.get("code") or "")
        if not td or not code or not isinstance(data, list):
            continue
        recs = sorted(
            [r for r in data if isinstance(r, dict) and r.get("tradeTime")],
            key=lambda r: str(r["tradeTime"]),
        )
        # Sanity: response tradeDate must match the requested tradeDate
        # (otherwise it's a silent today-fallback).
        if recs and str(recs[0].get("tradeDate") or "") != td:
            continue
        out[(td, code)] = recs
    return out


def compute_intraday_axes(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute all intraday entry-timing axes from a day's minute records.

    Returns dict with:
      open_pct           — 9:30 cum pct vs preClose
      pct_at_935         — 9:35 cum pct vs preClose
      max_window_trade   — max trade price in 9:30-9:35
      drawdown_from_peak — (max_window - close_935) / max_window * 100
      entry_price        — 9:35 trade (the new buy price if filter passes)
      not_at_peak        — drawdown_from_peak ≥ DEFAULT_DD_THRESHOLD
      weak_open_ok       — open_pct ∈ [-3%, +1%]  (kept for diagnostics)
      pct_controlled     — pct_at_935 ∈ (-3%, +4%]  (kept for diagnostics)

    Returns None if records insufficient to evaluate.
    """
    if len(records) < WINDOW_MINUTES:
        return None
    open_rec = records[0]
    rec_935 = records[WINDOW_MINUTES - 1]
    open_pct_raw = open_rec.get("pctChangeRate")
    pct_935_raw = rec_935.get("pctChangeRate")
    close_935 = _to_float(rec_935.get("trade"))
    if open_pct_raw is None or pct_935_raw is None or close_935 <= 0:
        return None

    open_pct = float(open_pct_raw)
    pct_at_935 = float(pct_935_raw)

    window = records[:WINDOW_MINUTES]
    window_trades = [_to_float(r.get("trade")) for r in window]
    window_trades = [t for t in window_trades if t > 0]
    if not window_trades:
        return None
    max_window = max(window_trades)
    drawdown = (max_window - close_935) / max_window * 100 if max_window > 0 else 0.0

    return {
        "open_pct": round(open_pct, 4),
        "pct_at_935": round(pct_at_935, 4),
        "max_window_trade": round(max_window, 4),
        "drawdown_from_peak": round(drawdown, 4),
        "entry_price": close_935,
        # "still strong" = stock has held near 9:30-9:35 peak (drawdown small).
        # Empirically the +1.4pp avg / +12pp win subset on 1d and 5d_dd2.
        "still_strong": drawdown <= DEFAULT_DD_THRESHOLD,
        "weak_open_ok": -3.0 <= open_pct <= 1.0,
        "pct_controlled": -3.0 < pct_at_935 <= 4.0,
    }


def passes_filter(
    axes: dict[str, Any] | None,
    filter_name: str,
    dd_threshold: float = DEFAULT_DD_THRESHOLD,
) -> bool:
    """Check if a signal passes the named intraday filter.

    Available filters:
      "none" / None      — no filter, always pass
      "still_strong"     — drawdown_from_peak ≤ dd_threshold
                           (still near 9:30-9:35 peak; the empirical winner)
      "weak_open"        — open_pct ∈ [-3%, +1%]  (anti-predictive, kept
                           for diagnostic ablation only)
      "pct_controlled"   — pct_at_935 ∈ (-3%, +4%]  (anti-predictive)
    """
    if filter_name in (None, "none", ""):
        return True
    if axes is None:
        # Without minute data we can't evaluate → fail safe (skip the trade).
        # Forces the caller to pre-fetch minute data when using a filter.
        return False
    if filter_name == "still_strong":
        dd = axes.get("drawdown_from_peak", 999.0)
        return dd <= dd_threshold
    if filter_name == "weak_open":
        return bool(axes.get("weak_open_ok", False))
    if filter_name == "pct_controlled":
        return bool(axes.get("pct_controlled", False))
    raise ValueError(f"unknown intraday filter: {filter_name!r}")


def _to_float(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def diagnostic_summary(
    minute_data: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate stats over all loaded minute datasets — for sanity checks."""
    n_total = len(minute_data)
    if not n_total:
        return {"n": 0}
    valid = 0
    still_strong_count = 0
    pct_at_935_dist: list[float] = []
    drawdown_dist: list[float] = []
    for recs in minute_data.values():
        axes = compute_intraday_axes(recs)
        if axes is None:
            continue
        valid += 1
        if axes["still_strong"]:
            still_strong_count += 1
        pct_at_935_dist.append(axes["pct_at_935"])
        drawdown_dist.append(axes["drawdown_from_peak"])
    return {
        "n_total": n_total,
        "n_valid": valid,
        "still_strong_pass_pct": (still_strong_count / valid * 100) if valid else 0,
        "pct_at_935_median": (sorted(pct_at_935_dist)[len(pct_at_935_dist) // 2]
                               if pct_at_935_dist else None),
        "drawdown_median": (sorted(drawdown_dist)[len(drawdown_dist) // 2]
                             if drawdown_dist else None),
    }
