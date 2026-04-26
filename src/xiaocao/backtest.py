"""Backtest harness for strategy signals.

Schema (matches the previously-produced output/xiaocao_backtest_*/):

- `signals_<YYYY-MM-DD>.json` — one file per trading day, the raw output of
  `run_strategy(date, ...)`.
- `trades.csv` — one row per closed trade.
  Columns: buyDate, sellDate, code, name, mode, returnPct, xcjw, cjs, jsjl,
           openPctChange, reason, droppedModes
- `summary.json` — aggregate stats.
  Two views:
    * `overall_signal_level`  — every signal counts (one mode = one row).
    * `overall_stock_day_level` — collapsed by (date, code), one bet per name.
  Plus `mode_summary` (avg/win/median per mode) and `last_day_signals`.

Buy/sell convention:
- Buy at signal-day qfq daily OPEN.
- Sell at next trading day qfq daily CLOSE.
- 1-day overnight hold.
- Last day of the requested range produces signals but no trade
  (no follow-up trading day to sell into).
"""
from __future__ import annotations

import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date, timedelta as _td
from pathlib import Path
from typing import Any, Iterable

from xiaocao.api.client import RANK_MODEL_FOCUS, XiaocaoClient
from xiaocao.api.errors import XiaocaoError
from xiaocao.strategy.bigcap import bigcap_codes
from xiaocao.strategy.mainline import compute_mainline
from xiaocao.strategy.regime import classify_regime
from xiaocao.utils.dates import lookback_start


def list_trade_days(client: XiaocaoClient, start: str, end: str, exchange: str = "SSE") -> list[str]:
    rows = client.get_trade_cal(start, end, exchange, 1)
    out: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        v = row.get("calDate") or row.get("tradeDate") or row.get("date")
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


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_klines(
    client: XiaocaoClient,
    codes: Iterable[str],
    end_date: str,
    count: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch daily qfq klines for a batch of codes (best-effort)."""
    code_list = sorted({c for c in codes if c})
    if not code_list:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    workers = max(1, min(8, len(code_list)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(client.date_kline, code, count=count, freq="D", adj="qfq", param_time=end_date): code
            for code in code_list
        }
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                rows = fut.result()
            except XiaocaoError:
                continue
            if isinstance(rows, list):
                out[code] = rows
            elif isinstance(rows, dict):
                for key in ("data", "list", "rows", "result"):
                    if isinstance(rows.get(key), list):
                        out[code] = rows[key]
                        break
    return out


def _kline_by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        td = row.get("tradeDate")
        if td is None:
            continue
        td = str(td)
        if len(td) == 8 and td.isdigit():
            td = f"{td[:4]}-{td[4:6]}-{td[6:]}"
        else:
            td = td[:10]
        by[td] = row
    return by


def score_trades(
    signals_by_date: dict[str, list[dict[str, Any]]],
    trade_days: list[str],
    klines: dict[str, dict[str, dict[str, Any]]],
    *,
    hold_days: int = 1,
    exit_rule: str = "next_close",
    max_dd_pct: float = 5.0,
    entry_rule: str = "open",
    intraday_minute_data: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
    intraday_dd_threshold: float = 1.5,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Compute closed trades. Returns (trades, incomplete_signal_dates).

    Default behavior (hold_days=1, exit_rule="next_close", entry_rule="open")
    preserves the 1-day backtest convention exactly: buy at signal-day OPEN
    (= 9:25 集合竞价 fill at 9:30), sell at next trading day's CLOSE.

    Multi-day exit (Plan B): set hold_days ≥ 2 with exit_rule ∈
      - "hold_to_n":      sell at trade_days[idx + hold_days] CLOSE
      - "max_dd":         exit on first day where drawdown from running peak
                          (HIGH after entry) exceeds max_dd_pct; if no such
                          day, fall back to hold_to_n
      - "max_favorable":  sell at the day with the max favorable excursion
                          (HIGH) in the window — backward-looking; useful for
                          ceiling analysis, not realistic execution

    Entry modes (Plan D): `entry_rule` ∈
      - "open" (default):       buy at signal-day 9:30 open (= 9:25 集合竞价
                                fill); all signals taken.
      - "confirmation_935":     "9:35 加仓 mode" — buy at 9:35 close ONLY when
                                the stock is STILL STRONG (drawdown from
                                9:30-9:35 max ≤ intraday_dd_threshold);
                                SKIP signals that retraced significantly.
                                Empirical: STRONG subset has 1d avg +4.54%
                                vs RETRACED +1.56% on 8mo TRAIN+TEST.
                                Models an INDEPENDENT trade unit alongside
                                any 9:25 集合竞价 position — user sizes
                                positions flexibly in real ops. Note: 9:35
                                entry price > 9:30 open due to morning surge,
                                so per-trade return is lower than 9:30-open
                                same-subset (+2.15% vs +4.54% on 1d), but
                                still positive-EV add-on capacity.

    For "confirmation_935" without minute data: SKIP (fail-safe; caller
    should pre-fetch via scripts/backfill_intraday_minute.py).
    """
    from xiaocao.strategy.intraday_entry import compute_intraday_axes

    use_intraday_entry = entry_rule == "confirmation_935"
    if entry_rule not in {"open", "confirmation_935"}:
        raise ValueError(f"unknown entry_rule {entry_rule!r}")

    def _resolve_entry(buy_date: str, code: str, fallback_open: float | None
                       ) -> tuple[float | None, dict[str, Any] | None]:
        """Return (entry_price, intraday_axes) for a signal.
        entry_price=None means SKIP this signal."""
        if not use_intraday_entry:
            return fallback_open, None
        td = buy_date.replace("-", "")
        recs = (intraday_minute_data or {}).get((td, str(code)))
        axes = compute_intraday_axes(recs) if recs else None
        if axes is None:
            return None, None  # no minute data → skip (fail-safe)
        if axes["drawdown_from_peak"] > intraday_dd_threshold:
            return None, axes  # retraced (weak signal) → skip 9:35 add-on
        return float(axes["entry_price"]), axes

    day_idx = {d: i for i, d in enumerate(trade_days)}
    trades: list[dict[str, Any]] = []
    incomplete: list[str] = []

    # 1d BC path
    if hold_days == 1 and exit_rule == "next_close":
        for buy_date in sorted(signals_by_date):
            idx = day_idx.get(buy_date)
            if idx is None or idx + 1 >= len(trade_days):
                if signals_by_date[buy_date]:
                    incomplete.append(buy_date)
                continue
            sell_date = trade_days[idx + 1]
            for sig in signals_by_date[buy_date]:
                code = sig.get("code")
                if not code:
                    continue
                kbd = klines.get(str(code), {})
                buy_row = kbd.get(buy_date)
                sell_row = kbd.get(sell_date)
                buy_open = _to_float(buy_row.get("open")) if buy_row else None
                sell_close = _to_float(sell_row.get("close")) if sell_row else None
                if buy_open is None or sell_close is None or buy_open == 0:
                    continue
                entry_price, axes = _resolve_entry(buy_date, str(code), buy_open)
                if entry_price is None or entry_price == 0:
                    continue
                ret = (sell_close / entry_price - 1) * 100
                t = _trade_row(sig, buy_date, sell_date, ret)
                if axes is not None:
                    t["intradayDrawdown"] = axes.get("drawdown_from_peak")
                    t["intradayEntry"] = entry_price
                    t["intradayPctAt935"] = axes.get("pct_at_935")
                trades.append(t)
        return trades, incomplete

    # Multi-day path (Plan B)
    if hold_days < 1:
        raise ValueError(f"hold_days must be ≥ 1, got {hold_days}")
    if exit_rule not in {"next_close", "hold_to_n", "max_dd", "max_favorable"}:
        raise ValueError(f"unknown exit_rule {exit_rule!r}")

    for buy_date in sorted(signals_by_date):
        idx = day_idx.get(buy_date)
        if idx is None or idx + 1 >= len(trade_days):
            if signals_by_date[buy_date]:
                incomplete.append(buy_date)
            continue
        # Window: trade_days[idx+1 .. idx+hold_days] (clipped at end of trade_days)
        last_idx = min(idx + hold_days, len(trade_days) - 1)
        if last_idx <= idx:
            if signals_by_date[buy_date]:
                incomplete.append(buy_date)
            continue
        window_dates = trade_days[idx + 1: last_idx + 1]
        for sig in signals_by_date[buy_date]:
            code = sig.get("code")
            if not code:
                continue
            kbd = klines.get(str(code), {})
            buy_row = kbd.get(buy_date)
            buy_open = _to_float(buy_row.get("open")) if buy_row else None
            if buy_open is None or buy_open == 0:
                continue
            entry_price, axes = _resolve_entry(buy_date, str(code), buy_open)
            if entry_price is None or entry_price == 0:
                continue

            # Walk window, compute exit per rule
            sell_date, sell_price, exit_kind = _resolve_exit(
                kbd, window_dates, entry_price, exit_rule, max_dd_pct,
            )
            if sell_date is None or sell_price is None:
                continue
            ret = (sell_price / entry_price - 1) * 100
            t = _trade_row(sig, buy_date, sell_date, ret)
            t["holdDays"] = day_idx[sell_date] - idx
            t["exitKind"] = exit_kind
            if axes is not None:
                t["intradayDrawdown"] = axes.get("drawdown_from_peak")
                t["intradayEntry"] = entry_price
                t["intradayPctAt935"] = axes.get("pct_at_935")
            trades.append(t)
    return trades, incomplete


def _trade_row(
    sig: dict[str, Any], buy_date: str, sell_date: str, ret: float,
) -> dict[str, Any]:
    return {
        "buyDate": buy_date,
        "sellDate": sell_date,
        "code": sig.get("code"),
        "name": sig.get("name") or "",
        "mode": sig.get("mode") or "",
        "returnPct": ret,
        "xcjw": _to_float(sig.get("xcjw")) or 0.0,
        "cjs": _to_float(sig.get("cjs")) or 0.0,
        "jsjl": _to_float(sig.get("jsjl")) or 0.0,
        "openPctChange": _to_float(sig.get("openPctChange")) or 0.0,
        "reason": sig.get("reason") or "",
        "droppedModes": ",".join(sig.get("dropped_modes") or []),
        "regime": sig.get("regime") or "",
        "isMainLine": bool(sig.get("is_main_line")) if "is_main_line" in sig else "",
        "isBigCap": bool(sig.get("is_big_cap")) if "is_big_cap" in sig else "",
        "adaptiveActive": (
            bool(sig.get("adaptive_active"))
            if "adaptive_active" in sig else ""
        ),
        "adaptiveReason": sig.get("adaptive_reason") or "",
    }


def _resolve_exit(
    kbd: dict[str, dict[str, Any]],
    window_dates: list[str],
    buy_open: float,
    rule: str,
    max_dd_pct: float,
) -> tuple[str | None, float | None, str | None]:
    """Walk forward through the hold-window and pick the exit price.

    Returns (sell_date, sell_price, exit_kind) where exit_kind ∈
    {"hold_to_n", "max_dd_stop", "max_favorable", "incomplete"}.
    """
    if not window_dates:
        return None, None, None

    rows = [(d, kbd.get(d)) for d in window_dates]
    rows = [(d, r) for d, r in rows if r]
    if not rows:
        return None, None, None

    last_date, last_row = rows[-1]
    last_close = _to_float(last_row.get("close"))

    if rule == "hold_to_n":
        if last_close is None:
            return None, None, None
        return last_date, last_close, "hold_to_n"

    if rule == "next_close":
        # 1d shortcut even when called via multi_day: just close of first window day
        first_date, first_row = rows[0]
        first_close = _to_float(first_row.get("close"))
        if first_close is None:
            return None, None, None
        return first_date, first_close, "next_close"

    if rule == "max_favorable":
        # Sell at day with maximum HIGH (forward-looking ceiling proxy).
        best = max(rows, key=lambda dr: _to_float(dr[1].get("high")) or float("-inf"))
        bdate, brow = best
        bhigh = _to_float(brow.get("high"))
        if bhigh is None:
            return None, None, None
        return bdate, bhigh, "max_favorable"

    if rule == "max_dd":
        # Trailing stop. Conservative ordering to avoid intraday look-ahead:
        # within a single trading day, check today's LOW against the peak set
        # by PREVIOUS days only (ignoring today's HIGH). Only after the
        # drawdown check do we incorporate today's HIGH into the peak for
        # subsequent days. This prevents the model from "selling at today's
        # peak * 0.98" when intraday the LOW could precede the HIGH.
        peak = buy_open
        for d, r in rows:
            low = _to_float(r.get("low"))
            if low is not None and peak > 0:
                drawdown_pct = (peak - low) / peak * 100
                if drawdown_pct >= max_dd_pct:
                    stop_price = peak * (1 - max_dd_pct / 100)
                    return d, stop_price, "max_dd_stop"
            high = _to_float(r.get("high"))
            if high is not None and high > peak:
                peak = high
        if last_close is None:
            return None, None, None
        return last_date, last_close, "hold_to_n"

    # Unknown rule
    return None, None, None




def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    wins = sum(1 for v in values if v > 0)
    return {
        "count": len(values),
        "avg": statistics.mean(values),
        "median": statistics.median(values),
        "win_rate": wins / len(values) * 100,
        "best": max(values),
        "worst": min(values),
        "sum": sum(values),
    }


def aggregate_summary(
    trades: list[dict[str, Any]],
    *,
    period_requested: str,
    trade_days: list[str],
    incomplete: list[str],
    last_day_signals: list[dict[str, Any]],
    strategy_args: dict[str, Any],
    regime_by_date: dict[str, str] | None = None,
) -> dict[str, Any]:
    def _is_active(t: dict[str, Any]) -> bool:
        # When the field is absent or ""/empty, treat the trade as active —
        # we only mark "shadow" (False) when adaptive explicitly tagged it.
        v = t.get("adaptiveActive")
        if v == "" or v is None:
            return True
        return bool(v)

    active_trades = [t for t in trades if _is_active(t)]
    shadow_trades = [t for t in trades if not _is_active(t)]

    by_signal = [t["returnPct"] for t in trades]
    active_signal = [t["returnPct"] for t in active_trades]
    shadow_signal = [t["returnPct"] for t in shadow_trades]

    by_stock_day: dict[tuple[str, str], float] = {}
    for t in trades:
        # Within a (buyDate, code), all rows have the same return — collapse.
        by_stock_day[(t["buyDate"], t["code"])] = t["returnPct"]
    active_stock_day: dict[tuple[str, str], float] = {}
    for t in active_trades:
        active_stock_day[(t["buyDate"], t["code"])] = t["returnPct"]

    by_mode: dict[str, list[float]] = {}
    by_mode_active: dict[str, list[float]] = {}
    for t in trades:
        m = t["mode"] or "_unknown"
        by_mode.setdefault(m, []).append(t["returnPct"])
        if _is_active(t):
            by_mode_active.setdefault(m, []).append(t["returnPct"])
    mode_summary = sorted(
        (
            {
                "mode": m,
                "all": _stats(v),
                "active": _stats(by_mode_active.get(m, [])),
            }
            for m, v in by_mode.items()
        ),
        key=lambda r: r["all"].get("avg", 0.0),
        reverse=True,
    )

    # B-track structural slices: by-regime and by-mainline
    regime_summary: list[dict[str, Any]] = []
    mainline_summary: list[dict[str, Any]] = []
    bigcap_summary: list[dict[str, Any]] = []
    if regime_by_date or any(t.get("regime") for t in trades):
        by_regime: dict[str, list[float]] = {}
        for t in trades:
            r = t.get("regime") or (regime_by_date or {}).get(t["buyDate"]) or "_unknown"
            by_regime.setdefault(r, []).append(t["returnPct"])
        regime_summary = sorted(
            ({"regime": r, **_stats(v)} for r, v in by_regime.items()),
            key=lambda r: r.get("avg", 0.0),
            reverse=True,
        )
    if any("isMainLine" in t for t in trades):
        by_main: dict[str, list[float]] = {"main_line": [], "off": []}
        for t in trades:
            (by_main["main_line"] if t.get("isMainLine") else by_main["off"]).append(t["returnPct"])
        mainline_summary = [
            {"bucket": k, **_stats(v)} for k, v in by_main.items() if v
        ]
    if any("isBigCap" in t for t in trades):
        by_bc: dict[str, list[float]] = {"big_cap": [], "small_cap": []}
        for t in trades:
            (by_bc["big_cap"] if t.get("isBigCap") else by_bc["small_cap"]).append(t["returnPct"])
        bigcap_summary = [
            {"bucket": k, **_stats(v)} for k, v in by_bc.items() if v
        ]

    return {
        "assumptions": {
            "period_requested": period_requested,
            "actual_trade_days": len(trade_days),
            "first_trade_day": trade_days[0] if trade_days else None,
            "last_trade_day": trade_days[-1] if trade_days else None,
            "incomplete_signal_dates": incomplete,
            "buy_price": "signal day qfq daily open",
            "sell_price": "next trading day qfq daily close",
            "source": "xiaocao backtest, api source",
            "strategy_args": strategy_args,
        },
        "overall_signal_level": _stats(by_signal),
        "overall_stock_day_level": _stats(list(by_stock_day.values())),
        "active_signal_level": _stats(active_signal),
        "active_stock_day_level": _stats(list(active_stock_day.values())),
        "shadow_signal_level": _stats(shadow_signal),
        "mode_summary": mode_summary,
        "regime_summary": regime_summary,
        "mainline_summary": mainline_summary,
        "bigcap_summary": bigcap_summary,
        "last_day_signals": last_day_signals[:50],
    }


def _json_default(obj: Any) -> Any:
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, frozenset):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def write_output_dir(
    out_dir: Path,
    signals_by_date: dict[str, list[dict[str, Any]]],
    trades: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for date, signals in signals_by_date.items():
        (out_dir / f"signals_{date}.json").write_text(
            json.dumps(signals, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    if trades:
        with (out_dir / "trades.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(trades[0].keys()))
            writer.writeheader()
            writer.writerows(trades)
    else:
        (out_dir / "trades.csv").write_text("", encoding="utf-8-sig")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


class _MemoizingRankSource:
    """Wraps a source and caches `get_industry_block_rank` for the backtest run.

    run_strategy fetches block_rank itself; we also need it for rolling main-line
    computation. Memoizing avoids paying the cost twice while keeping run_strategy's
    interface clean. All other attribute access pass-through.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._block_rank: dict[tuple[str, Any], list[dict[str, Any]]] = {}

    def get_industry_block_rank(self, date: str, model: Any) -> list[dict[str, Any]]:
        key = (date, model)
        if key not in self._block_rank:
            self._block_rank[key] = self._inner.get_industry_block_rank(date, model)
        return self._block_rank[key]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def run_backtest(
    client: XiaocaoClient,
    source: Any,
    *,
    start: str,
    end: str,
    output_dir: Path,
    exchange: str = "SSE",
    kline_count: int = 30,
    progress: Any | None = None,
    # B-track enrichment knobs
    enrich: bool = True,
    mainline_window: int = 3,
    mainline_topk: int = 5,
    mainline_min_hits: int | None = None,
    bigcap_top_pct: float = 0.2,
    workers: int = 1,
    adaptive_modes: bool = False,
    reset_mode_history: bool = True,
    warmup_start: str | None = None,
    # Plan B — multi-day persistence scoring
    hold_days: int = 1,
    exit_rule: str = "next_close",
    max_dd_pct: float = 5.0,
    # Plan D — intraday entry-timing
    entry_rule: str = "open",
    intraday_dd_threshold: float = 1.5,
    **strategy_kwargs: Any,
) -> dict[str, Any]:
    """Run a backtest and write artifacts to `output_dir`. Returns the summary dict.

    When `enrich=True`, the harness pre-computes per-day market_overview-derived
    regime, rolling main-line block set, and a static big-cap pool, and feeds
    them into run_strategy so signals carry those annotations.
    """
    from xiaocao.strategy import run_strategy

    trade_days = list_trade_days(client, start, end, exchange)
    if not trade_days:
        raise ValueError(f"No trading days in [{start}, {end}]")

    # Optional warmup phase: a prior window whose trades are recorded into
    # mode_history so adaptive gating has real evidence by `start`. Warmup
    # signals are NOT counted toward the final summary — they only seed
    # mode_history.
    warmup_days: list[str] = []
    if warmup_start and adaptive_modes:
        warmup_days = list_trade_days(client, warmup_start, start, exchange)
        # Drop the boundary day if it equals the actual start
        warmup_days = [d for d in warmup_days if d < trade_days[0]]

    cached_source = _MemoizingRankSource(source)
    block_model = strategy_kwargs.get("block_model", RANK_MODEL_FOCUS)
    # Main-line uses the FULL rank (model=0), which lists every industry with
    # a non-zero score, vs. FOCUS (model=1) which is sparse and produces an
    # almost-empty main-line set across days. Strategy still uses its own
    # block_model for picking strong directions.
    mainline_rank_model = 0

    # Static big-cap pool — fetched once. Skipped if enrichment disabled or
    # strategy_kwargs already supplied bigcap_codes.
    bc_pool: set[str] | None = strategy_kwargs.get("bigcap_codes")
    if enrich and bc_pool is None:
        try:
            info = client.stock_info()
            bc_pool = bigcap_codes(info, top_pct=bigcap_top_pct)
        except XiaocaoError:
            bc_pool = None

    # Phase 1: pre-fetch block_rank for all trade days in parallel — both the
    # strategy model (sparse) and the main-line model (full).
    if workers > 1:
        with ThreadPoolExecutor(max_workers=min(workers, len(trade_days))) as pool:
            for model in (block_model, mainline_rank_model):
                list(pool.map(
                    lambda d, m=model: cached_source.get_industry_block_rank(d, m),
                    trade_days,
                ))

    # Phase 2: per-day signal generation. Each day's call is independent — the
    # source is shared (the memoization cache is read-only at this point). For
    # non-enrich runs we can parallelize directly. For enrich runs we still
    # parallelize since main-line uses the prebuilt history (computed below
    # per-day from the cached rank, not from a mutating list).
    overview_by_date: dict[str, dict[str, Any]] = {}
    regime_by_date: dict[str, str] = {}
    signals_by_date: dict[str, list[dict[str, Any]]] = {}

    rank_by_date: dict[str, list[dict[str, Any]]] = {
        d: cached_source.get_industry_block_rank(d, mainline_rank_model) or []
        for d in trade_days
    }

    # market_overview is NOT date-aware — it returns current live state. So
    # we skip it for any day strictly in the past. For live (today) backtests
    # the call is meaningful. Determined once.
    today_iso = _date.today().isoformat()

    def _run_one_day(d: str) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any] | None]:
        per_day_kwargs = dict(strategy_kwargs)
        regime: str | None = None
        ov: dict[str, Any] | None = None
        if enrich:
            if d >= today_iso:
                try:
                    response = client.market_overview()
                    if isinstance(response, dict):
                        ov = response
                        regime = classify_regime(ov)
                        per_day_kwargs.setdefault("regime", regime)
                except XiaocaoError:
                    pass
            # Build trailing main-line from already-fetched rank history.
            idx = trade_days.index(d)
            if idx > 0:
                trailing = [rank_by_date[t] for t in trade_days[max(0, idx - mainline_window):idx]]
                ml = compute_mainline(
                    trailing,
                    window=mainline_window,
                    topk=mainline_topk,
                    min_hits=mainline_min_hits,
                )
                if ml:
                    per_day_kwargs.setdefault("mainline_blocks", ml)
            if bc_pool:
                per_day_kwargs.setdefault("bigcap_codes", bc_pool)
        signals = run_strategy(d, cached_source, **per_day_kwargs)
        return d, signals, regime, ov

    # Backtest defaults: adaptive uses PERMISSIVE Tier 4 (no recent evidence
    # → enable, so the first run primes mode_history without locking itself
    # out). After history accumulates, regular Tier 1-3 rules discriminate.
    # Live `strategy run` keeps strict_dormant=True so dormant modes are not
    # traded on stale or absent evidence.
    cache = getattr(client, "cache", None)
    if adaptive_modes and (cache is None or not hasattr(cache, "has_seed_evidence")):
        adaptive_modes = False

    if adaptive_modes:
        # Sequential mode is REQUIRED: today's mode set depends on the rolling
        # outcomes recorded from prior days in this same loop. By default we
        # clear the window first so re-runs are repeatable; pass
        # `reset_mode_history=False` to preserve and consume prior runs' data.
        if reset_mode_history and cache is not None and hasattr(cache, "clear_mode_history"):
            clear_lower = warmup_days[0] if warmup_days else trade_days[0]
            cache.clear_mode_history(date_start=clear_lower, date_end=trade_days[-1])
            cache.clear_mode_history(
                date_start=trade_days[-1],
                date_end=(_date.fromisoformat(trade_days[-1]) + _td(days=1)).isoformat(),
            )

        # Per-day kline fetches with count=4 anchored at past dates DON'T WORK
        # — the kline API ignores paramTime and returns the latest count days.
        # So we fetch ONCE up-front with a count large enough to cover from
        # the earliest day in the run all the way to today. Local kline_index
        # is then consulted by all per-day score_trades calls below.
        adaptive_kline_index: dict[str, dict[str, dict[str, Any]]] = {}

        def _ensure_klines_for_codes(codes: set[str]) -> None:
            """Fetch klines once for any new code, with count spanning to today."""
            new_codes = {c for c in codes if c and c not in adaptive_kline_index}
            if not new_codes:
                return
            try:
                first = _date.fromisoformat((warmup_days or trade_days)[0])
                days_to_today = max(0, (_date.today() - first).days)
                bulk_count = max(int(days_to_today * 5 / 7) + 5, len(trade_days) + len(warmup_days) + 5)
            except ValueError:
                bulk_count = max(120, len(trade_days) + len(warmup_days) + 5)
            kraw = fetch_klines(client, new_codes, trade_days[-1], count=bulk_count)
            for c, rows in kraw.items():
                adaptive_kline_index[c] = _kline_by_date(rows)

        # Warmup loop: same flow as scored loop but signals are NOT recorded
        # into signals_by_date / regime_by_date — only the trade outcomes are
        # written to mode_history. Pre-fetch warmup ranks first.
        if warmup_days:
            for wd in warmup_days:
                cached_source.get_industry_block_rank(wd, mainline_rank_model)
            for w_idx, wd in enumerate(warmup_days):
                # Warmup runs WITHOUT adaptive gating — its job is to seed
                # mode_history with real outcomes, not consult an empty cache
                # (which would Tier4-disable everything and produce no trades).
                w_kwargs = dict(strategy_kwargs)
                w_kwargs.pop("adaptive_modes", None)
                w_kwargs.pop("adaptive_cache", None)
                w_kwargs.pop("adaptive_trade_days", None)
                if enrich and bc_pool:
                    w_kwargs.setdefault("bigcap_codes", bc_pool)
                w_signals = run_strategy(wd, cached_source, **w_kwargs)
                if cache is not None and (w_idx + 1 < len(warmup_days) or trade_days):
                    next_d = warmup_days[w_idx + 1] if w_idx + 1 < len(warmup_days) else trade_days[0]
                    sig_codes = {s.get("code") for s in w_signals if s.get("code")}
                    if sig_codes:
                        _ensure_klines_for_codes(sig_codes)
                        klocal = {c: adaptive_kline_index.get(c, {}) for c in sig_codes}
                        partial_trades, _ = score_trades({wd: w_signals}, [wd, next_d], klocal)
                        if partial_trades:
                            cache.record_trades(partial_trades)
                if progress is not None:
                    progress(f"WARMUP {wd}", len(w_signals))

        for d_idx, d in enumerate(trade_days):
            # Inject cache + flag so run_strategy can call adaptive_mode_filter.
            extra_kwargs = dict(strategy_kwargs)
            extra_kwargs["adaptive_modes"] = True
            extra_kwargs["adaptive_cache"] = cache
            extra_kwargs["adaptive_trade_days"] = warmup_days + trade_days
            # Resolve regime/main-line/big-cap exactly like _run_one_day, then
            # call run_strategy directly (we can't reuse _run_one_day because
            # it doesn't pass the adaptive kwargs).
            regime: str | None = None
            ov: dict[str, Any] | None = None
            if enrich:
                if d >= today_iso:
                    try:
                        response = client.market_overview()
                        if isinstance(response, dict):
                            ov = response
                            regime = classify_regime(ov)
                            extra_kwargs.setdefault("regime", regime)
                    except XiaocaoError:
                        pass
                if d_idx > 0:
                    trailing = [rank_by_date[t] for t in trade_days[max(0, d_idx - mainline_window):d_idx]]
                    ml = compute_mainline(
                        trailing,
                        window=mainline_window,
                        topk=mainline_topk,
                        min_hits=mainline_min_hits,
                    )
                    if ml:
                        extra_kwargs.setdefault("mainline_blocks", ml)
                if bc_pool:
                    extra_kwargs.setdefault("bigcap_codes", bc_pool)
            signals = run_strategy(d, cached_source, **extra_kwargs)
            signals_by_date[d] = signals
            if regime is not None:
                regime_by_date[d] = regime
            if ov is not None:
                overview_by_date[d] = ov
            # Score TODAY's signals against next day's open/close so the next
            # iteration sees these outcomes in mode_history. Reuse the bulk
            # kline_index built during warmup; only fetch new codes.
            if cache is not None and d_idx + 1 < len(trade_days):
                next_d = trade_days[d_idx + 1]
                sig_codes = {s.get("code") for s in signals if s.get("code")}
                if sig_codes:
                    _ensure_klines_for_codes(sig_codes)
                    daily_klines = {c: adaptive_kline_index.get(c, {}) for c in sig_codes}
                    partial_trades, _ = score_trades({d: signals}, [d, next_d], daily_klines)
                    if partial_trades:
                        cache.record_trades(partial_trades)
            if progress is not None:
                progress(d, len(signals))
    elif workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_one_day, d) for d in trade_days]
            completed = 0
            for fut in as_completed(futures):
                d, signals, regime, ov = fut.result()
                signals_by_date[d] = signals
                if regime is not None:
                    regime_by_date[d] = regime
                if ov is not None:
                    overview_by_date[d] = ov
                completed += 1
                if progress is not None:
                    progress(d, len(signals))
    else:
        for d in trade_days:
            d, signals, regime, ov = _run_one_day(d)
            signals_by_date[d] = signals
            if regime is not None:
                regime_by_date[d] = regime
            if ov is not None:
                overview_by_date[d] = ov
            if progress is not None:
                progress(d, len(signals))

    kline_end = trade_days[-1]
    all_codes = {s.get("code") for sigs in signals_by_date.values() for s in sigs if s.get("code")}
    # The /stock/date_kline endpoint anchors its response at "today" rather
    # than at paramTime when paramTime is in the past — observed empirically.
    # That means the requested count must span from the EARLIEST trade day in
    # the range all the way to "today", or the early signals' buy/sell prices
    # will silently be missing and their trades dropped from trades.csv.
    # Compute a calendar-day span and pad generously (calendar≈1.5×trading).
    try:
        first = _date.fromisoformat(trade_days[0])
        days_to_today = max(0, (_date.today() - first).days)
        spanning_count = int(days_to_today * 5 / 7) + 5
    except ValueError:
        spanning_count = len(trade_days) + 5
    effective_kline_count = max(kline_count, spanning_count, len(trade_days) + 5)
    klines_raw = fetch_klines(client, all_codes, kline_end, count=effective_kline_count)
    klines = {code: _kline_by_date(rows) for code, rows in klines_raw.items()}

    intraday_minute_data = None
    if entry_rule == "confirmation_935":
        cache_obj = getattr(client, "cache", None)
        cache_path = getattr(cache_obj, "path", None) if cache_obj is not None else None
        if cache_path:
            from xiaocao.strategy.intraday_entry import load_minute_cache
            intraday_minute_data = load_minute_cache(cache_path)

    trades, incomplete = score_trades(
        signals_by_date, trade_days, klines,
        hold_days=hold_days, exit_rule=exit_rule, max_dd_pct=max_dd_pct,
        entry_rule=entry_rule,
        intraday_minute_data=intraday_minute_data,
        intraday_dd_threshold=intraday_dd_threshold,
    )
    summary = aggregate_summary(
        trades,
        period_requested=f"{start} to {end}",
        trade_days=trade_days,
        incomplete=incomplete,
        last_day_signals=signals_by_date.get(trade_days[-1], []),
        strategy_args={k: v for k, v in strategy_kwargs.items() if v is not None},
        regime_by_date=regime_by_date or None,
    )
    if enrich:
        summary["enrichment"] = {
            "regime_distribution": _count(regime_by_date.values()),
            "mainline_window": mainline_window,
            "mainline_topk": mainline_topk,
            "bigcap_top_pct": bigcap_top_pct,
            "bigcap_pool_size": len(bc_pool) if bc_pool else 0,
        }
    # Always persist trade outcomes to mode_history (when a cache is hooked
    # up) so subsequent runs and live `strategy run --adaptive-modes` can
    # consult them. Idempotent on (mode, trade_date, code).
    cache_for_history = getattr(client, "cache", None)
    if cache_for_history is not None and hasattr(cache_for_history, "record_trades") and trades:
        cache_for_history.record_trades(trades)

    write_output_dir(output_dir, signals_by_date, trades, summary)
    return summary


def _count(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out
