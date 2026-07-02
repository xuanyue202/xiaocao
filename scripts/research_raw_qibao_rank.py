"""Validate raw qibao rank cohorts against the current emitted qibao rule.

This is intentionally cache-first and read-only: it decodes
``output/.cache/xiaocao.db`` and never instantiates a live API client.  If the
coverage report shows missing pool/index/price data, backfill it with small
rate-limited CLI batches first, then rerun this script.

Outputs:
  - output/research/raw_qibao_rank_summary.json
  - output/research/raw_qibao_rank_summary.md
  - output/research/raw_qibao_rank_<variant>.jsonl

The jsonl files use the research_run.py contract:
  {"day": "YYYY-MM-DD", "strat_ret": pct, "base_ret": pct}
where base_ret is that day's qibao-pool open->next-close mean return.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.strategy.runner import MAX_OPEN_PCT_CHANGE  # noqa: E402
from xiaocao.strategy.rules import check_qibao, pick_big_ones  # noqa: E402


CACHE_PATH = ROOT / "output" / ".cache" / "xiaocao.db"
OUT_DIR = ROOT / "output" / "research"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> str:
    s = str(value or "")[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stockCode") or row.get("stockId") or "")


def _name(row: dict[str, Any]) -> str:
    return str(row.get("codeName") or row.get("name") or row.get("stockName") or "")


def _pct(row: dict[str, Any]) -> float:
    return _num(row.get("entityPctChangeRate") or row.get("pctChangeRate") or row.get("pctChange"))


def _open_pct(row: dict[str, Any]) -> float:
    return _num(row.get("openPctChangeRate") or row.get("openPctChange"))


def _is_limit_like(row: dict[str, Any]) -> bool:
    return _num(row.get("isLimitUp")) == 1 or _pct(row) >= 9.5


def _is_20cm(code: str) -> bool:
    return code.startswith(("300", "301", "688"))


def _is_near20_or_long_entity(row: dict[str, Any]) -> bool:
    code = _code(row)
    total_pct = _num(row.get("pctChangeRate") or row.get("pctChange") or row.get("entityPctChangeRate"))
    return (_is_20cm(code) and (total_pct >= 18.0 or _num(row.get("limitupdays")) > 0)) or _pct(row) >= 9.5


def _is_electronic(row: dict[str, Any]) -> bool:
    items = row.get("excIndustryStockList") or []
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("code") == "T08.ZHBK" or item.get("codeName") == "电子":
            return True
    return False


def _rows_from_index_response(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        rows: list[dict[str, Any]] = []
        for key, value in data.items():
            if isinstance(value, dict):
                if "code" not in value:
                    value = {**value, "code": key}
                rows.append(value)
        return rows
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def load_qibao_pool_by_date(cache_path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    rows = iter_cached_responses(cache_path, "/stock/focus_xiao_cao_index/get_code_list_v2", include_params=True)
    for params_json, data in rows:
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        if str(params.get("groups")) != "2":
            continue
        date = _date(params.get("date"))
        if not date:
            continue
        codes = data.get("data") if isinstance(data, dict) else data
        if isinstance(codes, list):
            out[date] = [str(c) for c in codes if c]
    return out


def load_index_by_date(cache_path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    rows = iter_cached_responses(cache_path, "/stock/xiao_cao_index_v2", include_params=True)
    for params_json, data in rows:
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        date = _date(params.get("date"))
        if not date:
            continue
        for row in _rows_from_index_response(data):
            code = _code(row)
            if code:
                out[date][code] = row
    return dict(out)


def load_rank_rows(cache_path: Path, endpoint: str, model: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    rows = iter_cached_responses(cache_path, endpoint, include_params=True)
    for params_json, data in rows:
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        if int(_num(params.get("model"), -1)) != model:
            continue
        date = _date(params.get("date"))
        if not date:
            continue
        if isinstance(data, dict):
            if isinstance(data.get("localCategoryRankList"), list):
                out[date] = data["localCategoryRankList"]
            elif isinstance(data.get("globalCategoryRankList"), list):
                out[date] = data["globalCategoryRankList"]
            elif isinstance(data.get("data"), list):
                out[date] = data["data"]
            else:
                out[date] = [v for v in data.values() if isinstance(v, dict)]
        elif isinstance(data, list):
            out[date] = [r for r in data if isinstance(r, dict)]
    return out


def load_klines(cache_path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    rows = iter_cached_responses(cache_path, "/stock/date_kline", include_params=True)
    for params_json, data in rows:
        try:
            params = json.loads(params_json).get("params", {})
        except (json.JSONDecodeError, AttributeError):
            continue
        code = str(params.get("code") or "")
        if not code:
            continue
        krows = data
        if isinstance(data, dict):
            for key in ("data", "list", "rows", "result"):
                if isinstance(data.get(key), list):
                    krows = data[key]
                    break
        if not isinstance(krows, list):
            continue
        for row in krows:
            if not isinstance(row, dict):
                continue
            day = _date(row.get("tradeDate") or row.get("date"))
            if day:
                out[code][day] = row
    return dict(out)


def _return_open_to_close(
    code: str,
    day: str,
    trade_days: list[str],
    klines: dict[str, dict[str, dict[str, Any]]],
    *,
    hold_days: int = 1,
) -> float | None:
    try:
        idx = trade_days.index(day)
    except ValueError:
        return None
    sell_idx = idx + hold_days
    if sell_idx >= len(trade_days):
        return None
    sell_day = trade_days[sell_idx]
    by_day = klines.get(code) or {}
    buy = by_day.get(day)
    sell = by_day.get(sell_day)
    if not buy or not sell:
        return None
    buy_open = _num(buy.get("open"), default=0.0)
    sell_close = _num(sell.get("close"), default=0.0)
    if buy_open <= 0 or sell_close <= 0:
        return None
    return (sell_close / buy_open - 1.0) * 100.0


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


def _variant_defs() -> dict[str, Callable[[list[dict[str, Any]], list[dict[str, Any]]], list[dict[str, Any]]]]:
    def base_raw_elec20(row: dict[str, Any], rank: int) -> bool:
        code = _code(row)
        return rank <= 10 and (_is_electronic(row) or _is_20cm(code)) and _pct(row) > 0

    def teacher_like(rows: list[dict[str, Any]], emitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for rank, row in enumerate(rows[:10], start=1):
            if not base_raw_elec20(row, rank):
                continue
            if _open_pct(row) > MAX_OPEN_PCT_CHANGE or _is_near20_or_long_entity(row):
                continue
            out.append(row)
        return out

    def teacher_like_wide(rows: list[dict[str, Any]], emitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [r for r in rows[:10] if (_is_electronic(r) or _is_20cm(_code(r)))]

    return {
        "emitted_qibao_after_xh037": lambda rows, emitted: emitted,
        "raw_top5_jssb": lambda rows, emitted: rows[:5],
        "raw_top10_jssb": lambda rows, emitted: rows[:10],
        "raw_top10_electronic": lambda rows, emitted: [r for r in rows[:10] if _is_electronic(r)],
        "raw_top10_elec_or_20cm": teacher_like_wide,
        "raw_top10_elec20_open_le6_red_notlimit": teacher_like,
        "raw_top10_elec20_high_open_watch": lambda rows, emitted: [
            row for rank, row in enumerate(rows[:10], start=1)
            if base_raw_elec20(row, rank) and _open_pct(row) > MAX_OPEN_PCT_CHANGE and not _is_near20_or_long_entity(row)
        ],
        "raw_top10_elec20_limitlike_watch": lambda rows, emitted: [
            row for rank, row in enumerate(rows[:10], start=1)
            if base_raw_elec20(row, rank) and _is_near20_or_long_entity(row)
        ],
        "raw_top10_elec20_high_open_any_red": lambda rows, emitted: [
            row for rank, row in enumerate(rows[:10], start=1)
            if base_raw_elec20(row, rank) and _open_pct(row) > MAX_OPEN_PCT_CHANGE
        ],
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    qibao_pool = load_qibao_pool_by_date(args.cache)
    index_by_date = load_index_by_date(args.cache)
    block_rank = load_rank_rows(args.cache, "/stock/xiao_cao_industry_block_rank", model=1)
    category_rank = load_rank_rows(args.cache, "/stock/xiao_cao_block_category_rank_v3", model=0)
    klines = load_klines(args.cache)
    variants = {"strict_emitted_qibao_pre_xh037": lambda rows, emitted: emitted, **_variant_defs()}

    dates = sorted(d for d in qibao_pool if args.start <= d <= args.end)
    trade_days = sorted(set(dates) | {d for by_day in klines.values() for d in by_day if args.start <= d <= args.end})

    variant_trades: dict[str, list[dict[str, Any]]] = {name: [] for name in variants}
    per_date_rows: list[dict[str, Any]] = []
    coverage = {
        "qibao_dates": len(dates),
        "dates_with_any_index": 0,
        "dates_with_full_pool_index": 0,
        "dates_with_base_return": 0,
        "pool_codes": 0,
        "pool_codes_with_index": 0,
        "pool_codes_with_next_return": 0,
    }

    for day in dates:
        pool = qibao_pool.get(day) or []
        by_code = index_by_date.get(day) or {}
        details = [by_code[c] for c in pool if c in by_code]
        coverage["pool_codes"] += len(pool)
        coverage["pool_codes_with_index"] += len(details)
        if details:
            coverage["dates_with_any_index"] += 1
        if pool and len(details) == len(pool):
            coverage["dates_with_full_pool_index"] += 1

        details.sort(key=lambda r: _num(r.get("jssb")), reverse=True)
        base_returns: list[float] = []
        returns_by_code: dict[str, float] = {}
        for row in details:
            ret = _return_open_to_close(_code(row), day, trade_days, klines, hold_days=args.hold_days)
            if ret is None:
                continue
            returns_by_code[_code(row)] = ret
            base_returns.append(ret)
        coverage["pool_codes_with_next_return"] += len(base_returns)
        if not base_returns:
            continue
        coverage["dates_with_base_return"] += 1
        base_ret = statistics.mean(base_returns)

        emitted = check_qibao(
            details,
            pick_big_ones(block_rank.get(day, []), 5),
            pick_big_ones(category_rank.get(day, []), 3),
            day,
        )
        emitted_codes = {_code(row) for row in emitted if _open_pct(row) < MAX_OPEN_PCT_CHANGE}
        emitted_details = [row for row in details if _code(row) in emitted_codes]
        strict_emitted_codes = {
            _code(row)
            for row in emitted
            if row.get("mode") in {"红盘起爆主攻", "方向红盘起爆"}
            and _open_pct(row) < MAX_OPEN_PCT_CHANGE
        }
        strict_emitted_details = [row for row in details if _code(row) in strict_emitted_codes]

        row_counts: dict[str, int] = {}
        for name, selector in variants.items():
            if name == "strict_emitted_qibao_pre_xh037":
                selected = strict_emitted_details
            else:
                selected = selector(details, emitted_details)
            row_counts[name] = len(selected)
            for row in selected:
                code = _code(row)
                ret = returns_by_code.get(code)
                if ret is None:
                    continue
                variant_trades[name].append({
                    "day": day,
                    "code": code,
                    "name": _name(row),
                    "raw_rank": details.index(row) + 1,
                    "strat_ret": ret,
                    "base_ret": base_ret,
                    "jssb": _num(row.get("jssb")),
                    "xcjw": _num(row.get("xcjw")),
                    "open_pct": _open_pct(row),
                    "pct": _pct(row),
                    "electronic": _is_electronic(row),
                    "board20": _is_20cm(code),
                })
        per_date_rows.append({
            "day": day,
            "pool": len(pool),
            "indexed": len(details),
            "base_n": len(base_returns),
            "base_ret": base_ret,
            **{f"n_{k}": v for k, v in row_counts.items()},
        })

    summary: dict[str, Any] = {
        "assumptions": {
            "start": args.start,
            "end": args.end,
            "hold_days": args.hold_days,
            "return": "signal-day qfq open -> D+hold_days qfq close",
            "base_ret": "same-day qibao pool mean return over rows with price data",
            "cache": str(args.cache),
            "note": "cache-only; no API calls; raw qibao rank is a research/watchlist cohort, not proof of 9:25 tradability",
        },
        "coverage": coverage,
        "variants": {},
        "per_date_tail": per_date_rows[-10:],
    }
    for name, rows in variant_trades.items():
        strat = [r["strat_ret"] for r in rows]
        base = [r["base_ret"] for r in rows]
        spread = [r["strat_ret"] - r["base_ret"] for r in rows]
        by_day: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            by_day[row["day"]].append(row["strat_ret"] - row["base_ret"])
        train_days = sorted(by_day)[: len(by_day) // 2]
        test_days = sorted(by_day)[len(by_day) // 2:]
        summary["variants"][name] = {
            "trades": len(rows),
            "days": len(by_day),
            "strat": _stats(strat),
            "base": _stats(base),
            "spread": _stats(spread),
            "train_day_edge": statistics.mean([statistics.mean(by_day[d]) for d in train_days]) if train_days else 0.0,
            "test_day_edge": statistics.mean([statistics.mean(by_day[d]) for d in test_days]) if test_days else 0.0,
            "examples_tail": rows[-8:],
        }
    summary["_variant_rows"] = variant_trades
    return summary


def write_outputs(summary: dict[str, Any], *, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_rows = summary.pop("_variant_rows")
    for name, rows in variant_rows.items():
        path = out_dir / f"raw_qibao_rank_{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps({
                    "day": row["day"],
                    "strat_ret": row["strat_ret"],
                    "base_ret": row["base_ret"],
                    "code": row["code"],
                    "name": row["name"],
                    "raw_rank": row["raw_rank"],
                }, ensure_ascii=False) + "\n")
    (out_dir / "raw_qibao_rank_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (out_dir / "raw_qibao_rank_summary.md").write_text(render_md(summary), encoding="utf-8")


def _fmt(v: Any, digits: int = 2) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.{digits}f}"
    return "-"


def render_md(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    assumptions = summary["assumptions"]
    cov = summary["coverage"]
    lines.append("# Raw Qibao Rank Research")
    lines.append("")
    lines.append(f"- Window: {assumptions['start']}..{assumptions['end']}")
    lines.append(f"- Return: {assumptions['return']}")
    lines.append(f"- Base: {assumptions['base_ret']}")
    lines.append(f"- Cache-only: `{Path(assumptions['cache']).relative_to(ROOT)}`")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- qibao dates: {cov['qibao_dates']}")
    lines.append(f"- dates with index/base return: {cov['dates_with_any_index']} / {cov['dates_with_base_return']}")
    lines.append(f"- pool codes with index: {cov['pool_codes_with_index']} / {cov['pool_codes']}")
    lines.append(f"- pool codes with next return: {cov['pool_codes_with_next_return']} / {cov['pool_codes']}")
    lines.append("")
    lines.append("## Variants")
    lines.append("")
    lines.append("| variant | trades | days | strat avg | base avg | spread avg | win | train edge | test edge |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, item in summary["variants"].items():
        lines.append(
            f"| {name} | {item['trades']} | {item['days']} | "
            f"{_fmt(item['strat'].get('mean'))}% | {_fmt(item['base'].get('mean'))}% | "
            f"{_fmt(item['spread'].get('mean'))}% | {_fmt(item['strat'].get('win_rate'))}% | "
            f"{_fmt(item['train_day_edge'])}% | {_fmt(item['test_day_edge'])}% |"
        )
    lines.append("")
    lines.append("## Tail Examples")
    lines.append("")
    for name, item in summary["variants"].items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append("| day | code | name | rank | ret | base | jssb | open | pct | electronic | 20cm |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|---|")
        for r in item["examples_tail"]:
            lines.append(
                f"| {r['day']} | {r['code']} | {r['name']} | {r['raw_rank']} | "
                f"{_fmt(r['strat_ret'])}% | {_fmt(r['base_ret'])}% | {_fmt(r['jssb'])} | "
                f"{_fmt(r['open_pct'])}% | {_fmt(r['pct'])}% | {r['electronic']} | {r['board20']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-07-01")
    ap.add_argument("--end", default="2026-06-29")
    ap.add_argument("--hold-days", type=int, default=1)
    ap.add_argument("--cache", type=Path, default=CACHE_PATH)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    summary = evaluate(args)
    write_outputs(summary, out_dir=args.out_dir)
    print(render_md(summary))
    print(f"\nWrote: {args.out_dir / 'raw_qibao_rank_summary.md'}")


if __name__ == "__main__":
    main()
