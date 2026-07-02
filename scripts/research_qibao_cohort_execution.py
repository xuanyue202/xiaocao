"""Fill-aware validation for raw-qibao benchmark/watchlist cohorts.

This is cache-only and read-only.  It uses cached 1-minute bars to answer a
narrow execution question that the daily open->next-close research cannot:
would a small paper limit order have had a plausible 09:30-09:31 fill?

Outputs:
  - output/research/qibao_cohort_execution_summary.json
  - output/research/qibao_cohort_execution_summary.md
  - output/research/qibao_cohort_execution_<cohort>.jsonl

The cohort jsonl files use the research_run.py contract:
  {"day": "YYYY-MM-DD", "strat_ret": pct, "base_ret": pct}
where both returns are computed from cached minute bars.  Base is the same-day
qibao-pool mean among rows with enough minute coverage.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from research_raw_qibao_rank import (  # noqa: E402
    _code,
    _date,
    _is_20cm,
    _is_electronic,
    _name,
    _num,
    _open_pct,
    _pct,
    _return_open_to_close,
    load_klines,
    load_index_by_date,
    load_qibao_pool_by_date,
)
from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.research.cohorts import (  # noqa: E402
    QIBAO_BUYABLE_BENCHMARK,
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
    classify_qibao_raw_cohorts,
)


CACHE_PATH = ROOT / "output" / ".cache" / "xiaocao.db"
OUT_DIR = ROOT / "output" / "research"
COHORT_ORDER = [
    QIBAO_BUYABLE_BENCHMARK,
    QIBAO_HIGH_OPEN_WATCH,
    QIBAO_LIMITLIKE_WATCH,
]


def _minute_key(value: object) -> str:
    text = str(value or "").strip().replace(":", "")
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return ""


def _rows_from_minute_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("data", "list", "rows", "result"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def load_minute_lines(cache_path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    out: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    rows = iter_cached_responses(cache_path, "/stock/minute_line", include_params=True)
    for params_json, data in rows:
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        code = str(params.get("code") or "")
        day = _date(params.get("tradeDate"))
        if not code or not day:
            continue
        bars = _rows_from_minute_payload(data)
        if bars:
            out[code][day] = bars
    return dict(out)


def _price(row: dict[str, Any]) -> float | None:
    px = _num(row.get("trade") or row.get("close"), default=0.0)
    return px if px > 0 else None


def _window_stats(
    bars: list[dict[str, Any]],
    *,
    start_hhmm: str,
    end_hhmm: str,
) -> dict[str, Any] | None:
    start_key = _minute_key(start_hhmm)
    end_key = _minute_key(end_hhmm)
    amt = 0.0
    vol = 0.0
    prices: list[float] = []
    lo: float | None = None
    hi: float | None = None
    last_time = ""
    for row in bars:
        t = _minute_key(row.get("tradeTime"))
        if not t or t < start_key or t > end_key:
            continue
        px = _price(row)
        if px is None:
            continue
        prices.append(px)
        row_high = _num(row.get("high"), default=0.0) or px
        row_low = _num(row.get("low"), default=0.0) or px
        hi = row_high if hi is None else max(hi, row_high)
        lo = row_low if lo is None else min(lo, row_low)
        row_amt = _num(row.get("amt"), default=0.0)
        row_vol = _num(row.get("vol"), default=0.0)
        if row_amt > 0 and row_vol > 0:
            amt += row_amt
            vol += row_vol
        last_time = t
    if not prices:
        return None
    vwap = amt / vol if vol > 0 else sum(prices) / len(prices)
    return {
        "open": prices[0],
        "vwap": vwap,
        "low": lo,
        "high": hi,
        "last": prices[-1],
        "time": last_time,
        "volume": vol,
    }


def _last_trade(bars: list[dict[str, Any]]) -> tuple[float, str] | None:
    best: tuple[str, float] | None = None
    for row in bars:
        t = _minute_key(row.get("tradeTime"))
        px = _price(row)
        if not t or px is None:
            continue
        if best is None or t > best[0]:
            best = (t, px)
    if best is None:
        return None
    return best[1], best[0]


def _bfq_open_reference(
    code: str,
    day: str,
    minute_lines: dict[str, dict[str, list[dict[str, Any]]]],
    klines: dict[str, dict[str, dict[str, Any]]],
) -> tuple[float | None, str]:
    """Estimate the daily open on the same price axis as minute `trade`.

    Cached minute bars are bfq while cached date_kline rows are usually qfq.
    For a one-day adjustment factor, scale qfq open by bfq minute close /
    qfq daily close.  This keeps the fill limit anchored to the day open rather
    than the first cached 09:30/09:31 trade, which would make limit-touch
    tautological.
    """
    daily = (klines.get(code) or {}).get(day)
    bars = (minute_lines.get(code) or {}).get(day)
    if not daily or not bars:
        return None, "missing_open_reference"
    qfq_open = _num(daily.get("open"), default=0.0)
    qfq_close = _num(daily.get("close"), default=0.0)
    last = _last_trade(bars)
    if qfq_open <= 0 or qfq_close <= 0 or not last:
        return None, "invalid_open_reference"
    bfq_last, _last_time = last
    return qfq_open * (bfq_last / qfq_close), "daily_open_scaled_to_minute_bfq"


def _minute_fill_return(
    code: str,
    day: str,
    sell_day: str,
    minute_lines: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    open_reference: float | None = None,
    open_reference_basis: str | None = None,
    start_hhmm: str,
    end_hhmm: str,
    limit_premium_pct: float,
) -> tuple[float | None, dict[str, Any]]:
    by_day = minute_lines.get(code) or {}
    buy_bars = by_day.get(day)
    if not buy_bars:
        return None, {"reason": "missing_buy_minute"}
    window = _window_stats(buy_bars, start_hhmm=start_hhmm, end_hhmm=end_hhmm)
    if not window:
        return None, {"reason": "missing_buy_window"}
    open_px = float(open_reference) if open_reference and open_reference > 0 else float(window["open"])
    limit_px = open_px * (1 + limit_premium_pct / 100.0)
    low = float(window["low"])
    metadata: dict[str, Any] = {
        "entry_open": open_px,
        "open_reference_basis": open_reference_basis or "window_open_fallback",
        "fill_limit_price": limit_px,
        "fill_window_low": low,
        "fill_window_high": window.get("high"),
        "fill_window_vwap": window.get("vwap"),
        "fill_window_last": window.get("last"),
        "fill_window_time": window.get("time"),
        "fill_window_volume": window.get("volume"),
    }
    if low > limit_px:
        metadata["reason"] = "limit_not_touched"
        return None, metadata
    entry = min(float(window["vwap"]), limit_px)
    sell_bars = by_day.get(sell_day)
    if not sell_bars:
        metadata["reason"] = "missing_sell_minute"
        metadata["entry_price"] = entry
        return None, metadata
    sell = _last_trade(sell_bars)
    if not sell:
        metadata["reason"] = "missing_sell_close"
        metadata["entry_price"] = entry
        return None, metadata
    sell_px, sell_time = sell
    metadata["entry_price"] = entry
    metadata["exit_price"] = sell_px
    metadata["exit_time"] = sell_time
    metadata["reason"] = "filled"
    return (sell_px / entry - 1.0) * 100.0, metadata


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "win_rate": sum(1 for v in values if v > 0) / len(values) * 100.0,
        "best": max(values),
        "worst": min(values),
        "sum": sum(values),
    }


def _next_trade_day(day: str, trade_days: list[str]) -> str | None:
    try:
        idx = trade_days.index(day)
    except ValueError:
        return None
    if idx + 1 >= len(trade_days):
        return None
    return trade_days[idx + 1]


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    qibao_pool = load_qibao_pool_by_date(args.cache)
    index_by_date = load_index_by_date(args.cache)
    minute_lines = load_minute_lines(args.cache)
    klines = load_klines(args.cache)
    minute_dates = {
        day
        for by_day in minute_lines.values()
        for day in by_day
        if args.start <= day <= args.sell_end
    }
    trade_days = sorted(set(qibao_pool) | minute_dates)
    daily_trade_days = sorted(set(qibao_pool) | {d for by_day in klines.values() for d in by_day})
    dates = sorted(d for d in qibao_pool if args.start <= d <= args.end)

    cohort_rows: dict[str, list[dict[str, Any]]] = {cohort: [] for cohort in COHORT_ORDER}
    coverage: dict[str, Any] = {
        "qibao_dates": len(dates),
        "minute_line_code_days": sum(len(by_day) for by_day in minute_lines.values()),
        "dates_with_base_return": 0,
        "pool_codes": 0,
        "pool_codes_with_index": 0,
        "pool_codes_with_minute_return": 0,
        "selected": {cohort: 0 for cohort in COHORT_ORDER},
        "filled": {cohort: 0 for cohort in COHORT_ORDER},
        "skip_reasons": {cohort: {} for cohort in COHORT_ORDER},
    }
    per_date: list[dict[str, Any]] = []

    for day in dates:
        sell_day = _next_trade_day(day, trade_days)
        if not sell_day:
            continue
        pool = qibao_pool.get(day) or []
        by_code = index_by_date.get(day) or {}
        details = [by_code[c] for c in pool if c in by_code]
        details.sort(key=lambda r: _num(r.get("jssb")), reverse=True)
        coverage["pool_codes"] += len(pool)
        coverage["pool_codes_with_index"] += len(details)

        attempts_by_code: dict[str, tuple[float | None, dict[str, Any]]] = {}
        returns_by_code: dict[str, tuple[float, dict[str, Any]]] = {}
        minute_base_returns: list[float] = []
        daily_base_returns: list[float] = []
        base_skip = Counter()
        for row in details:
            code = _code(row)
            daily_ret = _return_open_to_close(code, day, daily_trade_days, klines, hold_days=1)
            if daily_ret is not None:
                daily_base_returns.append(daily_ret)
            open_ref, open_ref_basis = _bfq_open_reference(code, day, minute_lines, klines)
            ret, meta = _minute_fill_return(
                code,
                day,
                sell_day,
                minute_lines,
                open_reference=open_ref,
                open_reference_basis=open_ref_basis,
                start_hhmm=args.fill_window_start,
                end_hhmm=args.fill_window_end,
                limit_premium_pct=args.limit_premium_pct,
            )
            attempts_by_code[code] = (ret, meta)
            if ret is None:
                base_skip[str(meta.get("reason") or "unknown")] += 1
                continue
            returns_by_code[code] = (ret, meta)
            minute_base_returns.append(ret)
        coverage["pool_codes_with_minute_return"] += len(minute_base_returns)
        base_ret = statistics.mean(daily_base_returns) if daily_base_returns else None
        if base_ret is not None:
            coverage["dates_with_base_return"] += 1

        date_counts: dict[str, int] = {}
        for rank, row in enumerate(details, start=1):
            code = _code(row)
            cohorts = classify_qibao_raw_cohorts(row, rank)
            for cohort in cohorts:
                coverage["selected"][cohort] += 1
                ret_meta = returns_by_code.get(code)
                if not ret_meta:
                    _ret, skip_meta = attempts_by_code.get(code, (None, {"reason": "unknown"}))
                    reason = str(skip_meta.get("reason") or "unknown")
                    existing = Counter(coverage["skip_reasons"][cohort])
                    existing[reason] += 1
                    coverage["skip_reasons"][cohort] = dict(existing)
                    continue
                ret, meta = ret_meta
                if base_ret is None:
                    existing = Counter(coverage["skip_reasons"][cohort])
                    existing["missing_base_minute"] += 1
                    coverage["skip_reasons"][cohort] = dict(existing)
                    continue
                coverage["filled"][cohort] += 1
                date_counts[cohort] = date_counts.get(cohort, 0) + 1
                cohort_rows[cohort].append({
                    "day": day,
                    "sell_day": sell_day,
                    "code": code,
                    "name": _name(row),
                    "raw_rank": rank,
                    "strat_ret": ret,
                    "base_ret": base_ret,
                    "spread": ret - base_ret,
                    "jssb": _num(row.get("jssb")),
                    "xcjw": _num(row.get("xcjw")),
                    "short_line": _num(row.get("shortLineScore")),
                    "open_pct": _open_pct(row),
                    "pct": _pct(row),
                    "electronic": _is_electronic(row),
                    "board20": _is_20cm(code),
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in meta.items()},
                })
        per_date.append({
            "day": day,
            "sell_day": sell_day,
            "base_n": len(daily_base_returns),
            "minute_base_n": len(minute_base_returns),
            "base_ret": base_ret,
            "base_skip": dict(base_skip),
            **{f"n_{cohort}": date_counts.get(cohort, 0) for cohort in COHORT_ORDER},
        })

    summary: dict[str, Any] = {
        "assumptions": {
            "start": args.start,
            "end": args.end,
            "sell_end": args.sell_end,
            "return": "cached minute 09:30-09:31 limit-touch fill -> next trade-day cached minute last trade",
            "fill_model": f"entry=min(window_vwap, qfq daily open scaled to minute bfq*(1+{args.limit_premium_pct}%)) only if window_low touches limit; no basket retry for raw cohorts",
            "base_ret": "same-day qibao pool mean daily open->next-close return over rows with date_kline coverage",
            "cache": str(args.cache),
            "note": "price-touch fill is weaker than queue-liquidity proof for one-price limit-up rows; keep authority=0",
        },
        "coverage": coverage,
        "cohorts": {},
        "per_date_tail": per_date[-12:],
    }
    for cohort, rows in cohort_rows.items():
        strat = [r["strat_ret"] for r in rows]
        base = [r["base_ret"] for r in rows]
        spread = [r["spread"] for r in rows]
        by_day: dict[str, list[float]] = defaultdict(list)
        by_stock = Counter()
        for row in rows:
            by_day[row["day"]].append(row["spread"])
            by_stock[f"{row['code']} {row['name']}"] += 1
        day_spreads = {d: statistics.mean(v) for d, v in by_day.items()}
        top_days = sorted(day_spreads.items(), key=lambda item: item[1], reverse=True)[:5]
        worst_days = sorted(day_spreads.items(), key=lambda item: item[1])[:5]
        selected = int(coverage["selected"][cohort])
        filled = int(coverage["filled"][cohort])
        summary["cohorts"][cohort] = {
            "selected": selected,
            "filled": filled,
            "fill_rate": filled / selected * 100.0 if selected else 0.0,
            "days": len(by_day),
            "strat": _stats(strat),
            "base": _stats(base),
            "spread": _stats(spread),
            "skip_reasons": coverage["skip_reasons"][cohort],
            "top_days": top_days,
            "worst_days": worst_days,
            "top_stocks": by_stock.most_common(8),
            "examples_tail": rows[-8:],
        }
    summary["_cohort_rows"] = cohort_rows
    return summary


def write_outputs(summary: dict[str, Any], *, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cohort_rows = summary.pop("_cohort_rows")
    for cohort, rows in cohort_rows.items():
        research_path = out_dir / f"qibao_cohort_execution_{cohort}.jsonl"
        detail_path = out_dir / f"qibao_cohort_execution_{cohort}_details.jsonl"
        with research_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps({
                    "day": row["day"],
                    "strat_ret": row["strat_ret"],
                    "base_ret": row["base_ret"],
                    "code": row["code"],
                    "name": row["name"],
                    "raw_rank": row["raw_rank"],
                }, ensure_ascii=False) + "\n")
        with detail_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "qibao_cohort_execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "qibao_cohort_execution_summary.md").write_text(render_md(summary), encoding="utf-8")


def _fmt(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not math.isnan(float(value)):
        return f"{value:.{digits}f}"
    return "-"


def render_md(summary: dict[str, Any]) -> str:
    assumptions = summary["assumptions"]
    cov = summary["coverage"]
    lines: list[str] = []
    lines.append("# Qibao Cohort Execution Research")
    lines.append("")
    lines.append(f"- Window: {assumptions['start']}..{assumptions['end']}")
    lines.append(f"- Return: {assumptions['return']}")
    lines.append(f"- Fill: {assumptions['fill_model']}")
    lines.append(f"- Base: {assumptions['base_ret']}")
    lines.append(f"- Cache-only: `{Path(assumptions['cache']).relative_to(ROOT)}`")
    lines.append(f"- Note: {assumptions['note']}")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- qibao dates: {cov['qibao_dates']}")
    lines.append(f"- minute-line code-days: {cov['minute_line_code_days']}")
    lines.append(f"- dates with full-pool daily base return: {cov['dates_with_base_return']}")
    lines.append(f"- pool codes with index: {cov['pool_codes_with_index']} / {cov['pool_codes']}")
    lines.append(f"- pool codes with minute return: {cov['pool_codes_with_minute_return']} / {cov['pool_codes']}")
    lines.append("")
    lines.append("## Cohorts")
    lines.append("")
    lines.append("| cohort | selected | filled | fill rate | days | strat avg | base avg | spread avg | win |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cohort in COHORT_ORDER:
        item = summary["cohorts"][cohort]
        lines.append(
            f"| {cohort} | {item['selected']} | {item['filled']} | {_fmt(item['fill_rate'])}% | "
            f"{item['days']} | {_fmt(item['strat'].get('mean'))}% | {_fmt(item['base'].get('mean'))}% | "
            f"{_fmt(item['spread'].get('mean'))}% | {_fmt(item['strat'].get('win_rate'))}% |"
        )
    lines.append("")
    lines.append("## Skips")
    lines.append("")
    lines.append("| cohort | skip reasons |")
    lines.append("|---|---|")
    for cohort in COHORT_ORDER:
        reasons = summary["cohorts"][cohort]["skip_reasons"]
        text = ", ".join(f"{k}:{v}" for k, v in sorted(reasons.items())) or "-"
        lines.append(f"| {cohort} | {text} |")
    lines.append("")
    lines.append("## Concentration")
    lines.append("")
    for cohort in COHORT_ORDER:
        item = summary["cohorts"][cohort]
        lines.append(f"### {cohort}")
        lines.append("")
        lines.append(f"- top days: {', '.join(f'{d} {v:.2f}%' for d, v in item['top_days']) or '-'}")
        lines.append(f"- worst days: {', '.join(f'{d} {v:.2f}%' for d, v in item['worst_days']) or '-'}")
        lines.append(f"- top stocks: {', '.join(f'{name} x{n}' for name, n in item['top_stocks']) or '-'}")
        lines.append("")
    lines.append("## Tail Examples")
    lines.append("")
    for cohort in COHORT_ORDER:
        item = summary["cohorts"][cohort]
        lines.append(f"### {cohort}")
        lines.append("")
        lines.append("| day | code | name | rank | ret | base | spread | entry | exit | open% | pct% |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in item["examples_tail"]:
            lines.append(
                f"| {row['day']} | {row['code']} | {row['name']} | {row['raw_rank']} | "
                f"{_fmt(row['strat_ret'])}% | {_fmt(row['base_ret'])}% | {_fmt(row['spread'])}% | "
                f"{_fmt(row.get('entry_price'))} | {_fmt(row.get('exit_price'))} | "
                f"{_fmt(row['open_pct'])}% | {_fmt(row['pct'])}% |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-07-01")
    ap.add_argument("--end", default="2026-06-29")
    ap.add_argument("--sell-end", default="2026-06-30", help="latest sell-day allowed for next-day minute exits")
    ap.add_argument("--fill-window-start", default="0930")
    ap.add_argument("--fill-window-end", default="0931")
    ap.add_argument("--limit-premium-pct", type=float, default=0.5)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    summary = evaluate(args)
    write_outputs(summary, out_dir=args.out_dir)
    print(render_md({k: v for k, v in summary.items() if k != "_cohort_rows"}))
    print(f"\nWrote: {args.out_dir / 'qibao_cohort_execution_summary.md'}")


if __name__ == "__main__":
    main()
