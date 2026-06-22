#!/usr/bin/env python3
"""Cache-only annual validation for Xiaocao exit/posture priors.

This script turns selected `reference/experience` exit/主线 priors into
falsifiable, annual-history guard inputs. It intentionally does NOT mutate live
paper-trading state, does NOT record to the verdict ledger, and does NOT change
`exit_policy.py`. Passing output here is evidence for the human gate, not an
automatic strategy change.

Primary convention:
  base_ret  = current historical `mode_history.return_pct`
  strat_ret = counterfactual filter return, usually cash (0) when the candidate
              says the trade should not be allowed/held by that prior

The convention is deliberately conservative: it can validate broad annual
filters and strong-hold proxies, while intraday-only ideas such as locked
limit-down and post-limit-up fade are reported as sample-gated tags unless
there is enough same-convention data.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.research import guards  # noqa: E402
from xiaocao.strategy.mainline import compute_mainline  # noqa: E402

DEFAULT_CACHE = ROOT / "output" / ".cache" / "xiaocao.db"
DEFAULT_OUT_DIR = ROOT / "output" / "research" / "exit_priors"
LIVE_DIR = ROOT / "output" / "live"

DATE_RE = re.compile(r"^20\d\d-\d\d-\d\d$")


@dataclass(frozen=True)
class ModeTrade:
    day: str
    mode: str
    code: str
    return_pct: float


@dataclass(frozen=True)
class EnrichedTrade:
    day: str
    mode: str
    code: str
    return_pct: float
    detail_present: bool
    blocks: frozenset[str]
    mainline_strict: bool | None
    mainline_relaxed: bool | None
    big_cap: bool
    primary_score: float
    primary_score_label: str
    pct_change_rate: float | None
    open_pct: float | None
    strong_hold_strict: bool
    strong_hold_relaxed: bool


@dataclass(frozen=True)
class Candidate:
    name: str
    hypothesis_id: str
    claim: str
    keep: Callable[[EnrichedTrade], bool]
    eligible: Callable[[EnrichedTrade], bool]


def normalize_date(value: Any) -> str | None:
    s = str(value or "")[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if DATE_RE.match(s):
        return s
    return None


def num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out):
        return None
    return out


def _params_inner(params_json: str) -> dict[str, Any]:
    try:
        raw = json.loads(params_json)
    except json.JSONDecodeError:
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("params"), dict):
        return raw["params"]
    return raw if isinstance(raw, dict) else {}


def _endpoint_date(endpoint: str, params_json: str) -> str | None:
    inner = _params_inner(params_json)
    for key in ("date", "tradeDate", "trade_date", "paramTime", "endDate"):
        if key in inner:
            return normalize_date(inner.get(key))
    return None


def load_mode_history(cache_path: Path) -> tuple[list[ModeTrade], list[dict[str, Any]], dict[str, Any]]:
    valid: list[ModeTrade] = []
    invalid: list[dict[str, Any]] = []
    duplicate_keys = 0
    seen: set[tuple[str, str, str]] = set()
    with sqlite3.connect(f"file:{cache_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT mode, trade_date, code, return_pct FROM mode_history"
        ).fetchall()
    for mode, trade_date, code, ret in rows:
        reason = None
        day = normalize_date(trade_date)
        if not day:
            reason = "invalid_trade_date"
        elif str(mode).startswith("/stock/"):
            reason = "endpoint_row"
        elif not code:
            reason = "missing_code"
        if reason:
            invalid.append({
                "mode": mode,
                "trade_date": trade_date,
                "code": code,
                "return_pct": ret,
                "reason": reason,
            })
            continue
        key = (str(mode), day, str(code))
        if key in seen:
            duplicate_keys += 1
            invalid.append({
                "mode": mode,
                "trade_date": trade_date,
                "code": code,
                "return_pct": ret,
                "reason": "duplicate_mode_day_code",
            })
            continue
        seen.add(key)
        valid.append(ModeTrade(day=day, mode=str(mode), code=str(code), return_pct=float(ret)))
    summary = {
        "total_rows": len(rows),
        "valid_rows": len(valid),
        "invalid_rows": len(invalid),
        "duplicate_mode_day_code": duplicate_keys,
        "valid_days": len({t.day for t in valid}),
        "date_min": min((t.day for t in valid), default=None),
        "date_max": max((t.day for t in valid), default=None),
        "invalid_reason_counts": dict(Counter(str(r["reason"]) for r in invalid)),
    }
    return valid, invalid, summary


def _iter_detail_rows(data: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    if isinstance(data, dict):
        iterable = data.items()
    elif isinstance(data, list):
        iterable = ((r.get("code"), r) for r in data if isinstance(r, dict))
    else:
        iterable = []
    for code, row in iterable:
        if code and isinstance(row, dict):
            yield str(code), row


def load_stock_detail_index(cache_path: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    days: set[str] = set()
    rows_seen = 0
    for params_json, data in iter_cached_responses(cache_path, "/stock/xiao_cao_index_v2", include_params=True):
        day = _endpoint_date("/stock/xiao_cao_index_v2", params_json)
        if not day:
            continue
        days.add(day)
        for code, row in _iter_detail_rows(data):
            rows_seen += 1
            # Keep first row per (day, code); later cache fragments often repeat.
            index.setdefault((day, code), row)
    return index, {
        "endpoint": "/stock/xiao_cao_index_v2",
        "rows_seen": rows_seen,
        "unique_day_code": len(index),
        "days": len(days),
        "date_min": min(days) if days else None,
        "date_max": max(days) if days else None,
    }


def load_rank_history(cache_path: Path, *, model: int = 0) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    out: dict[str, list[dict[str, Any]]] = {}
    rows_seen = 0
    for params_json, data in iter_cached_responses(
        cache_path, "/stock/xiao_cao_industry_block_rank", include_params=True
    ):
        inner = _params_inner(params_json)
        if inner.get("model") != model:
            continue
        day = normalize_date(inner.get("date"))
        if not day:
            continue
        if isinstance(data, dict):
            rows = data.get("data") if isinstance(data.get("data"), list) else list(data.values())
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        rows_seen += len(rows)
        out[day] = [r for r in rows if isinstance(r, dict)]
    days = set(out)
    return out, {
        "endpoint": "/stock/xiao_cao_industry_block_rank",
        "model": model,
        "days": len(days),
        "rows_seen": rows_seen,
        "date_min": min(days) if days else None,
        "date_max": max(days) if days else None,
    }


def build_mainline_by_date(
    days: list[str],
    rank_by_date: dict[str, list[dict[str, Any]]],
    *,
    window: int,
    topk: int,
    min_hits: int,
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for i, day in enumerate(days):
        trailing = [rank_by_date.get(d, []) for d in days[max(0, i - window): i]]
        out[day] = compute_mainline(trailing, window=window, topk=topk, min_hits=min_hits)
    return out


def detail_blocks(row: dict[str, Any] | None) -> frozenset[str]:
    if not row:
        return frozenset()
    out: set[str] = set()
    for key in ("excIndustryCode", "industryBlockCodeList", "blockCodeList", "blockCategoryCodeList"):
        value = row.get(key)
        if isinstance(value, str):
            out.update(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, list):
            out.update(str(part) for part in value if part)
    for key in ("excIndustryStockList", "excBlockStockList"):
        value = row.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("code"):
                    out.add(str(item["code"]))
    return frozenset(out)


def primary_score(mode: str, row: dict[str, Any] | None) -> tuple[float, str]:
    row = row or {}
    xcjw = num(row.get("xcjw")) or 0.0
    cjs = num(row.get("cjs")) or 0.0
    jsjl = num(row.get("jsjl")) or 0.0
    jssb = num(row.get("jssb")) or 0.0
    if "起爆" in mode:
        return jssb, "jssb"
    if mode.startswith("接力"):
        return xcjw + max(jsjl, 0.0) * 0.5, "xcjw+0.5*jsjl"
    if mode in {"N字低吸", "孕线低吸"}:
        return xcjw + cjs * 0.6, "xcjw+0.6*cjs"
    return xcjw + cjs * 0.8, "xcjw+0.8*cjs"


def is_big_cap(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if bool(row.get("largeMarketValue") or row.get("middleLargeMarketValue")):
        return True
    market_value = num(row.get("marketValue")) or num(row.get("circulationMarketValue")) or 0.0
    return market_value >= 50_000_000_000


def strong_hold_proxy(
    *,
    mode: str,
    row: dict[str, Any] | None,
    mainline: bool | None,
    primary: float,
    big_cap: bool,
) -> bool:
    if not row or not mainline:
        return False
    xcjw = num(row.get("xcjw")) or 0.0
    jsjl = num(row.get("jsjl")) or 0.0
    pct = num(row.get("pctChangeRate")) or 0.0
    limit_like = bool(row.get("isLimitUp")) or pct >= 8.0
    trend_like = "接力" in mode or xcjw >= 300.0 or jsjl > 0.0 or big_cap
    return bool((trend_like or limit_like) and primary >= 150.0)


def enrich_trades(
    trades: list[ModeTrade],
    details: dict[tuple[str, str], dict[str, Any]],
    mainline_strict: dict[str, set[str]],
    mainline_relaxed: dict[str, set[str]],
) -> tuple[list[EnrichedTrade], dict[str, Any]]:
    out: list[EnrichedTrade] = []
    miss_detail = 0
    miss_mainline = 0
    for trade in trades:
        row = details.get((trade.day, trade.code))
        blocks = detail_blocks(row)
        strict_set = mainline_strict.get(trade.day)
        relaxed_set = mainline_relaxed.get(trade.day)
        strict = bool(blocks & strict_set) if strict_set is not None and blocks else None
        relaxed = bool(blocks & relaxed_set) if relaxed_set is not None and blocks else None
        if row is None:
            miss_detail += 1
        if strict is None:
            miss_mainline += 1
        primary, label = primary_score(trade.mode, row)
        big = is_big_cap(row)
        out.append(EnrichedTrade(
            day=trade.day,
            mode=trade.mode,
            code=trade.code,
            return_pct=trade.return_pct,
            detail_present=row is not None,
            blocks=blocks,
            mainline_strict=strict,
            mainline_relaxed=relaxed,
            big_cap=big,
            primary_score=primary,
            primary_score_label=label,
            pct_change_rate=num(row.get("pctChangeRate")) if row else None,
            open_pct=num(row.get("openPctChangeRate")) if row else None,
            strong_hold_strict=strong_hold_proxy(
                mode=trade.mode, row=row, mainline=strict, primary=primary, big_cap=big
            ),
            strong_hold_relaxed=strong_hold_proxy(
                mode=trade.mode, row=row, mainline=relaxed, primary=primary, big_cap=big
            ),
        ))
    return out, {
        "trades": len(out),
        "detail_missing": miss_detail,
        "detail_coverage_pct": round((len(out) - miss_detail) / len(out) * 100, 2) if out else 0.0,
        "mainline_missing": miss_mainline,
        "mainline_coverage_pct": round((len(out) - miss_mainline) / len(out) * 100, 2) if out else 0.0,
    }


def candidates() -> list[Candidate]:
    known_strict = lambda t: t.mainline_strict is not None
    known_relaxed = lambda t: t.mainline_relaxed is not None
    return [
        Candidate(
            name="xh013_mainline_only_strict",
            hypothesis_id="XH-013",
            claim="trend/mainline membership should be a hard filter for annual low-suck candidates (3d top5 all-hit)",
            eligible=known_strict,
            keep=lambda t: bool(t.mainline_strict),
        ),
        Candidate(
            name="xh013_mainline_only_relaxed",
            hypothesis_id="XH-013",
            claim="trend/mainline membership should be a hard filter for annual low-suck candidates (3d top5 2-hit)",
            eligible=known_relaxed,
            keep=lambda t: bool(t.mainline_relaxed),
        ),
        Candidate(
            name="xh003_mainline_or_bigcap",
            hypothesis_id="XH-003",
            claim="exit/selection should distinguish mainline/big-cap candidates from non-mainline weak names",
            eligible=known_strict,
            keep=lambda t: bool(t.mainline_strict or t.big_cap),
        ),
        Candidate(
            name="xh004_strong_hold_strict",
            hypothesis_id="XH-004",
            claim="strong-hold suppression proxy should only preserve mainline trend-like names (strict mainline)",
            eligible=known_strict,
            keep=lambda t: bool(t.strong_hold_strict),
        ),
        Candidate(
            name="xh004_strong_hold_relaxed",
            hypothesis_id="XH-004",
            claim="strong-hold suppression proxy should only preserve mainline trend-like names (relaxed mainline)",
            eligible=known_relaxed,
            keep=lambda t: bool(t.strong_hold_relaxed),
        ),
    ]


def result_rows(trades: list[EnrichedTrade], candidate: Candidate) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    kept = 0
    for trade in trades:
        if not candidate.eligible(trade):
            skipped += 1
            continue
        keep = candidate.keep(trade)
        if keep:
            kept += 1
        rows.append({
            "day": trade.day,
            "strat_ret": trade.return_pct if keep else 0.0,
            "base_ret": trade.return_pct,
            "code": trade.code,
            "mode": trade.mode,
            "kept": keep,
            "return_pct": trade.return_pct,
            "mainline_strict": trade.mainline_strict,
            "mainline_relaxed": trade.mainline_relaxed,
            "big_cap": trade.big_cap,
            "primary_score": round(trade.primary_score, 4),
            "strong_hold_strict": trade.strong_hold_strict,
            "strong_hold_relaxed": trade.strong_hold_relaxed,
        })
    return rows, {
        "eligible_rows": len(rows),
        "skipped_missing_context": skipped,
        "kept_rows": kept,
        "kept_pct": round(kept / len(rows) * 100, 2) if rows else 0.0,
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def bucket_report(rows: list[dict[str, Any]], *, min_bucket_trades: int) -> dict[str, Any]:
    bucket_defs = {
        "quarter": lambda r: f"{r['day'][:4]}Q{((int(r['day'][5:7]) - 1) // 3) + 1}",
        "month": lambda r: r["day"][:7],
        "mode": lambda r: str(r.get("mode") or ""),
        "mainline": lambda r: (
            "mainline" if r.get("mainline_strict") is True else
            "off_mainline" if r.get("mainline_strict") is False else
            "unknown"
        ),
    }
    out: dict[str, list[dict[str, Any]]] = {}
    collapse: list[dict[str, Any]] = []
    for group_name, key_fn in bucket_defs.items():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(key_fn(row))].append(row)
        stats = []
        for key, sub in sorted(grouped.items()):
            spreads = [float(r["strat_ret"]) - float(r["base_ret"]) for r in sub]
            rec = {
                "bucket": key,
                "n": len(sub),
                "days": len({str(r["day"]) for r in sub}),
                "spread": round(_mean(spreads), 6),
                "strat_mean": round(_mean([float(r["strat_ret"]) for r in sub]), 6),
                "base_mean": round(_mean([float(r["base_ret"]) for r in sub]), 6),
            }
            stats.append(rec)
            if group_name in {"quarter", "mode", "mainline"} and len(sub) >= min_bucket_trades and rec["spread"] <= 0:
                collapse.append({"group": group_name, **rec})
        out[group_name] = stats
    spreads = sorted(
        [max(0.0, float(r["strat_ret"]) - float(r["base_ret"])) for r in rows],
        reverse=True,
    )
    positive_sum = sum(spreads)
    top_n = max(1, math.ceil(len(spreads) * 0.05)) if spreads else 0
    top5_share = (sum(spreads[:top_n]) / positive_sum) if positive_sum > 0 else 1.0
    return {
        "buckets": out,
        "collapse_buckets": collapse,
        "right_tail_top5_share": round(top5_share, 6),
        "right_tail_ok": top5_share <= 0.75,
        "l2_pass": (not collapse) and top5_share <= 0.75,
        "min_bucket_trades": min_bucket_trades,
    }


def endpoint_coverage(cache_path: Path) -> list[dict[str, Any]]:
    endpoints = [
        "/stock/date_kline",
        "/stock/minute_line",
        "/stock/xiao_cao_index_v2",
        "/stock/sort_v2",
        "/stock/focus_xiao_cao_index/get_code_list_v2",
        "/stock/get_code_by_xiao_cao_block",
        "/stock/xiao_cao_industry_block_rank",
        "/stock/xiao_cao_block_category_rank_v3",
        "/stock/xiao_cao_environment_second_line_v2",
        "/stock/stock_call_auction",
    ]
    out = []
    for endpoint in endpoints:
        n = 0
        days: set[str] = set()
        for params_json, _ in iter_cached_responses(cache_path, endpoint, include_params=True):
            n += 1
            day = _endpoint_date(endpoint, params_json)
            if day:
                days.add(day)
        out.append({
            "endpoint": endpoint,
            "cache_rows": n,
            "days": len(days),
            "date_min": min(days) if days else None,
            "date_max": max(days) if days else None,
        })
    return out


def intraday_tag_report(cache_path: Path) -> dict[str, Any]:
    minute_days: set[str] = set()
    minute_rows = 0
    near_lock_proxy = 0
    for params_json, data in iter_cached_responses(cache_path, "/stock/minute_line", include_params=True):
        day = _endpoint_date("/stock/minute_line", params_json)
        if day:
            minute_days.add(day)
        if not isinstance(data, list):
            continue
        minute_rows += len(data)
        for row in data:
            if not isinstance(row, dict):
                continue
            pct = num(row.get("pctChangeRate"))
            if pct is not None and pct <= -9.5:
                near_lock_proxy += 1
    return {
        "xh002_limit_down_lock": {
            "status": "shadow_only",
            "reason": "minute cache has trade/pct but no reliable downPrice/bid liquidity for annual same-convention guard input",
            "minute_days": len(minute_days),
            "minute_rows": minute_rows,
            "near_limit_down_minute_rows": near_lock_proxy,
        },
        "xh006_limitup_fade": {
            "status": "shadow_only",
            "reason": "annual mode_history lacks intraday fill/exit convention needed to compare post-limit-up fade against production exits",
            "minute_days": len(minute_days),
        },
        "xh005_trend_tail": {
            "status": "tag_only",
            "reason": "trend-tail diffusion requires a separate labelled cycle dataset before it can be a guard candidate",
        },
    }


def live_path_report(live_dir: Path = LIVE_DIR) -> dict[str, Any]:
    def load_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    positions = load_jsonl(live_dir / "positions.jsonl")
    alerts = load_jsonl(live_dir / "alerts.jsonl")
    trades = load_jsonl(live_dir / "paper_trades.jsonl")
    return {
        "read_only": True,
        "positions_rows": len(positions),
        "book_a_rows": sum(1 for p in positions if p.get("book") == "A"),
        "book_b_rows": sum(1 for p in positions if p.get("book", "B") == "B"),
        "open_book_b_rows": sum(1 for p in positions if p.get("book", "B") == "B" and p.get("status", "open") == "open"),
        "hard_stop_closed_rows": sum(1 for p in positions if p.get("exit_reason") == "HARD_STOP"),
        "sell_blocked_alerts": sum(1 for a in alerts if a.get("alert") == "SELL_BLOCKED"),
        "sell_triggered_alerts": sum(1 for a in alerts if a.get("alert") == "SELL_TRIGGERED"),
        "paper_sell_trades": sum(1 for t in trades if t.get("side") == "SELL"),
        "invariant_note": "research script does not execute sells and does not write live account, trade, or position files",
    }


def evaluate_candidate(
    rows: list[dict[str, Any]],
    *,
    n_tried: int,
    min_days: int,
    min_bucket_trades: int,
) -> dict[str, Any]:
    guard_rows = [{"day": r["day"], "strat_ret": r["strat_ret"], "base_ret": r["base_ret"]} for r in rows]
    verdict = guards.evaluate_hypothesis(guard_rows, n_tried=n_tried, cache_only=True, min_days=min_days)
    l2 = bucket_report(rows, min_bucket_trades=min_bucket_trades)
    return {
        "verdict": verdict,
        "robustness": l2,
        "apply_ready": verdict["verdict"] == "PASS" and l2["l2_pass"],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Exit Prior Annual Validation",
        "",
        "Cache-only annual validation. No live state mutated. No ledger entry recorded.",
        "",
        "## Data Integrity",
        "",
    ]
    mh = payload["integrity"]["mode_history"]
    lines.append(
        f"- mode_history: {mh['valid_rows']} valid rows / {mh['valid_days']} days "
        f"({mh['date_min']}..{mh['date_max']}), invalid={mh['invalid_rows']}"
    )
    enrichment = payload["integrity"]["enrichment"]
    lines.append(
        f"- enrichment coverage: detail {enrichment['detail_coverage_pct']}%, "
        f"mainline {enrichment['mainline_coverage_pct']}%"
    )
    lines.append("- mainline construction uses prior trading days only.")
    lines.append("")
    lines.append("## Candidate Verdicts")
    lines.append("")
    lines.append("| candidate | hyp | rows | kept | guard | L2 | apply_ready | spread | p | rejected_by |")
    lines.append("|---|---:|---:|---:|---|---|---|---:|---:|---|")
    for item in payload["candidates"]:
        verdict = item["evaluation"]["verdict"]
        robust = item["evaluation"]["robustness"]
        pt = verdict["per_trade"]
        sig = verdict["significance"]
        rejected = ",".join(verdict["rejected_by"]) or "-"
        lines.append(
            f"| {item['name']} | {item['hypothesis_id']} | {item['coverage']['eligible_rows']} | "
            f"{item['coverage']['kept_rows']} | {verdict['verdict']} | "
            f"{'PASS' if robust['l2_pass'] else 'REJECTED'} | "
            f"{'YES' if item['evaluation']['apply_ready'] else 'NO'} | "
            f"{pt['spread']:+.4f} | {sig['p']:.4f} | {rejected} |"
        )
    lines.append("")
    lines.append("## Shadow-Only Tags")
    lines.append("")
    for key, value in payload["intraday_tags"].items():
        lines.append(f"- {key}: {value['status']} — {value['reason']}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    *,
    cache_path: Path = DEFAULT_CACHE,
    out_dir: Path = DEFAULT_OUT_DIR,
    min_days: int = 8,
    min_bucket_trades: int = 20,
    write_outputs: bool = True,
) -> dict[str, Any]:
    valid_trades, invalid_rows, mode_summary = load_mode_history(cache_path)
    days = sorted({t.day for t in valid_trades})
    details, detail_summary = load_stock_detail_index(cache_path)
    ranks, rank_summary = load_rank_history(cache_path, model=0)
    ml_strict = build_mainline_by_date(days, ranks, window=3, topk=5, min_hits=3)
    ml_relaxed = build_mainline_by_date(days, ranks, window=3, topk=5, min_hits=2)
    enriched, enrichment = enrich_trades(valid_trades, details, ml_strict, ml_relaxed)

    candidate_defs = candidates()
    n_tried = len(candidate_defs)
    candidate_payloads: list[dict[str, Any]] = []
    for candidate in candidate_defs:
        rows, coverage = result_rows(enriched, candidate)
        evaluation = evaluate_candidate(
            rows, n_tried=n_tried, min_days=min_days, min_bucket_trades=min_bucket_trades
        )
        candidate_payloads.append({
            "name": candidate.name,
            "hypothesis_id": candidate.hypothesis_id,
            "claim": candidate.claim,
            "coverage": coverage,
            "evaluation": evaluation,
            "rows": rows,
        })

    payload = {
        "integrity": {
            "cache_path": str(cache_path),
            "mode_history": mode_summary,
            "invalid_mode_history_examples": invalid_rows[:10],
            "endpoint_coverage": endpoint_coverage(cache_path),
            "stock_detail_index": detail_summary,
            "industry_rank": rank_summary,
            "enrichment": enrichment,
            "no_future_mainline": True,
        },
        "n_tried": n_tried,
        "candidates": candidate_payloads,
        "intraday_tags": intraday_tag_report(cache_path),
        "live_path": live_path_report(),
    }

    if write_outputs:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "integrity.json", payload["integrity"])
        write_json(out_dir / "intraday_tags.json", payload["intraday_tags"])
        write_json(out_dir / "live_path.json", payload["live_path"])
        for item in candidate_payloads:
            write_jsonl(out_dir / f"{item['name']}.jsonl", item["rows"])
            write_json(out_dir / f"{item['name']}_verdict.json", {
                "name": item["name"],
                "hypothesis_id": item["hypothesis_id"],
                "claim": item["claim"],
                "coverage": item["coverage"],
                "evaluation": item["evaluation"],
            })
        summary_payload = {**payload, "candidates": [{k: v for k, v in item.items() if k != "rows"} for item in candidate_payloads]}
        write_json(out_dir / "summary.json", summary_payload)
        write_summary(out_dir / "summary.md", summary_payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--min-days", type=int, default=8)
    parser.add_argument("--min-bucket-trades", type=int, default=20)
    parser.add_argument("--no-write", action="store_true", help="compute only; do not write output/research files")
    parser.add_argument("--json", action="store_true", help="print compact JSON summary")
    args = parser.parse_args()

    payload = run(
        cache_path=Path(args.cache),
        out_dir=Path(args.out_dir),
        min_days=args.min_days,
        min_bucket_trades=args.min_bucket_trades,
        write_outputs=not args.no_write,
    )
    compact = {
        "mode_history": payload["integrity"]["mode_history"],
        "enrichment": payload["integrity"]["enrichment"],
        "n_tried": payload["n_tried"],
        "candidates": [
            {
                "name": item["name"],
                "hypothesis_id": item["hypothesis_id"],
                "eligible_rows": item["coverage"]["eligible_rows"],
                "kept_rows": item["coverage"]["kept_rows"],
                "verdict": item["evaluation"]["verdict"]["verdict"],
                "l2_pass": item["evaluation"]["robustness"]["l2_pass"],
                "apply_ready": item["evaluation"]["apply_ready"],
                "spread": round(float(item["evaluation"]["verdict"]["per_trade"]["spread"]), 6),
                "p": round(float(item["evaluation"]["verdict"]["significance"]["p"]), 6),
                "rejected_by": item["evaluation"]["verdict"]["rejected_by"],
            }
            for item in payload["candidates"]
        ],
        "out_dir": None if args.no_write else str(Path(args.out_dir)),
    }
    if args.json:
        print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"mode_history: {compact['mode_history']['valid_rows']} rows / "
            f"{compact['mode_history']['valid_days']} days "
            f"({compact['mode_history']['date_min']}..{compact['mode_history']['date_max']})"
        )
        print(
            f"enrichment: detail={compact['enrichment']['detail_coverage_pct']}% "
            f"mainline={compact['enrichment']['mainline_coverage_pct']}%"
        )
        print(f"n_tried={compact['n_tried']}")
        for item in compact["candidates"]:
            print(
                f"{item['name']}: {item['verdict']} L2={'PASS' if item['l2_pass'] else 'REJECTED'} "
                f"apply_ready={'YES' if item['apply_ready'] else 'NO'} "
                f"spread={item['spread']:+.4f} p={item['p']:.4f} "
                f"rows={item['eligible_rows']} kept={item['kept_rows']}"
            )
        if not args.no_write:
            print(f"wrote -> {args.out_dir}")


if __name__ == "__main__":
    main()
