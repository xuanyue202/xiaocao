#!/usr/bin/env python3
"""Trend-leader basket counterfactual from cached minute bars.

Default cohort is the 2026-06-01 Xiaocao trend-leader basket discussed in the
June review: buy at entry-day close and hold to checkpoint closes. This is a
fast stage-1 instrument for Book T work: validate the concrete cohort first,
then decide whether it deserves a broader trend-book replay.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
DEFAULT_BASKET = [
    {"code": "600487.XSHG", "name": "亨通光电", "theme": "CPO"},
    {"code": "601869.XSHG", "name": "长飞光纤", "theme": "CPO"},
    {"code": "600183.XSHG", "name": "生益科技", "theme": "元器件"},
    {"code": "300408.XSHE", "name": "三环集团", "theme": "元器件"},
    {"code": "002463.XSHE", "name": "沪电股份", "theme": "PCB"},
    {"code": "300308.XSHE", "name": "中际旭创", "theme": "CPO"},
]


def compact_date(value: str) -> str:
    s = str(value).strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10].replace("-", "")
    return s[:8]


def iso_date(value: str) -> str:
    s = compact_date(value)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def parse_basket(text: str) -> list[dict[str, str]]:
    if not text:
        return list(DEFAULT_BASKET)
    out: list[dict[str, str]] = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        code, rest = item.split(":", 1) if ":" in item else (item, "")
        name, theme = (rest.split("/", 1) + [""])[:2] if rest else ("", "")
        out.append({"code": code.strip(), "name": name.strip() or code.strip(), "theme": theme.strip()})
    return out


def f(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def minute_bar(rows: list[dict[str, Any]]) -> dict[str, float] | None:
    points = []
    for row in rows:
        trade = f(row.get("trade"))
        if trade is None:
            continue
        try:
            minute = int(row.get("tradeMinutes"))
        except (TypeError, ValueError):
            minute = len(points)
        points.append((minute, trade))
    if not points:
        return None
    points.sort(key=lambda x: x[0])
    prices = [p for _, p in points]
    return {"open": prices[0], "close": prices[-1], "high": max(prices), "low": min(prices), "bars": len(prices)}


def cached_minute_bar(cache_path: Path, code: str, date: str) -> dict[str, float] | None:
    target_date = compact_date(date)
    best: dict[str, float] | None = None
    for params_json, data in iter_cached_responses(cache_path, "/stock/minute_line", include_params=True):
        try:
            params = json.loads(params_json).get("params", {})
        except json.JSONDecodeError:
            continue
        if params.get("code") != code or compact_date(str(params.get("tradeDate") or "")) != target_date:
            continue
        if params.get("freq") not in (None, "1min"):
            continue
        if not isinstance(data, list):
            continue
        bar = minute_bar([r for r in data if isinstance(r, dict)])
        if bar and (best is None or bar["bars"] > best["bars"]):
            best = bar
    return best


def load_cached_minute_bars(
    cache_path: Path,
    *,
    codes: set[str],
    dates: set[str],
) -> dict[tuple[str, str], dict[str, float]]:
    target_dates = {compact_date(d) for d in dates}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for params_json, data in iter_cached_responses(cache_path, "/stock/minute_line", include_params=True):
        try:
            params = json.loads(params_json).get("params", {})
        except json.JSONDecodeError:
            continue
        code = str(params.get("code") or "")
        trade_date = compact_date(str(params.get("tradeDate") or ""))
        if code not in codes or trade_date not in target_dates:
            continue
        if params.get("freq") not in (None, "1min"):
            continue
        if not isinstance(data, list):
            continue
        bar = minute_bar([r for r in data if isinstance(r, dict)])
        key = (code, iso_date(trade_date))
        if bar and (key not in out or bar["bars"] > out[key]["bars"]):
            out[key] = bar
    return out


def client() -> XiaocaoClient:
    settings = load_settings(None)
    return XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=SQLiteCache(DB),
    )


def fetch_minute_bar(c: XiaocaoClient, code: str, date: str) -> dict[str, float] | None:
    rows = c.minute_line(code, trade_date=compact_date(date), count=241, freq="1min", adj="bfq")
    if not isinstance(rows, list):
        return None
    return minute_bar([r for r in rows if isinstance(r, dict)])


def build_report(
    *,
    basket: list[dict[str, str]],
    entry_date: str,
    checkpoints: list[str],
    entry_price: str,
    allow_api: bool,
    sleep_sec: float,
) -> dict[str, Any]:
    c = client() if allow_api else None
    rows = []
    missing: list[dict[str, str]] = []
    all_dates = {entry_date, *checkpoints}
    cached = load_cached_minute_bars(
        DB,
        codes={stock["code"] for stock in basket},
        dates={compact_date(d) for d in all_dates},
    )
    for stock in basket:
        code = stock["code"]
        bars: dict[str, dict[str, float]] = {}
        for d in [entry_date, *checkpoints]:
            key = (code, iso_date(d))
            bar = cached.get(key)
            source = "cache"
            if bar is None and c is not None:
                time.sleep(max(0.0, sleep_sec))
                bar = fetch_minute_bar(c, code, d)
                source = "api"
                if bar is not None:
                    cached[key] = bar
            if bar is None:
                missing.append({"code": code, "date": iso_date(d)})
                continue
            bars[iso_date(d)] = {**bar, "source": source}
        entry_bar = bars.get(iso_date(entry_date))
        if not entry_bar:
            continue
        entry = entry_bar.get(entry_price)
        item: dict[str, Any] = {
            "code": code,
            "name": stock.get("name") or code,
            "theme": stock.get("theme") or "",
            "entry_date": iso_date(entry_date),
            "entry_price_basis": entry_price,
            "entry_price": round(float(entry), 4),
            "checkpoint_returns": {},
            "bars": bars,
        }
        for d in checkpoints:
            bar = bars.get(iso_date(d))
            if not bar:
                continue
            ret = (float(bar["close"]) / float(entry) - 1.0) * 100.0
            item["checkpoint_returns"][iso_date(d)] = round(ret, 4)
        rows.append(item)
    equal_weight = {}
    for d in checkpoints:
        key = iso_date(d)
        vals = [r["checkpoint_returns"][key] for r in rows if key in r["checkpoint_returns"]]
        if vals:
            equal_weight[key] = round(statistics.mean(vals), 4)
    return {
        "entry_date": iso_date(entry_date),
        "entry_price_basis": entry_price,
        "checkpoints": [iso_date(d) for d in checkpoints],
        "equal_weight_returns": equal_weight,
        "rows": rows,
        "missing": missing,
        "source": "cached /stock/minute_line trade prices; optional --allow-api only fills missing bars",
    }


def markdown(report: dict[str, Any]) -> str:
    cps = report["checkpoints"]
    title = f"# Trend Leader Basket Counterfactual {report['entry_date']}"
    lines = [
        title,
        "",
        f"- Entry: {report['entry_date']} {report['entry_price_basis']}",
        f"- Data: {report['source']}",
        "- Fees/slippage: excluded; this is a holding counterfactual, not an execution backtest.",
        "",
        "## Equal Weight",
        "",
        "| checkpoint | return |",
        "|---|---:|",
    ]
    for d in cps:
        val = report["equal_weight_returns"].get(d)
        lines.append(f"| {d} | {val:+.1f}% |" if val is not None else f"| {d} | missing |")
    lines += ["", "## Constituents", "", "| code | name | theme | entry | " + " | ".join(cps) + " |", "|---|---|---|---:|" + "|".join(["---:"] * len(cps)) + "|"]
    for row in report["rows"]:
        vals = []
        for d in cps:
            v = row["checkpoint_returns"].get(d)
            vals.append(f"{v:+.1f}%" if v is not None else "-")
        lines.append(
            f"| {row['code']} | {row['name']} | {row.get('theme','')} | "
            f"{row['entry_price']:.2f} | " + " | ".join(vals) + " |"
        )
    if report["missing"]:
        lines += ["", "## Missing Bars", "", "| code | date |", "|---|---|"]
        for row in report["missing"]:
            lines.append(f"| {row['code']} | {row['date']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entry-date", default="2026-06-01")
    ap.add_argument("--checkpoints", default="2026-06-08,2026-06-19")
    ap.add_argument("--entry-price", choices=("open", "close"), default="close")
    ap.add_argument("--basket", default="", help="comma list: code:name/theme,code:name/theme")
    ap.add_argument("--allow-api", action="store_true", help="fetch only missing minute bars, rate-limited")
    ap.add_argument("--sleep-sec", type=float, default=0.7)
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    checkpoints = [d.strip() for d in args.checkpoints.split(",") if d.strip()]
    report = build_report(
        basket=parse_basket(args.basket),
        entry_date=args.entry_date,
        checkpoints=checkpoints,
        entry_price=args.entry_price,
        allow_api=args.allow_api,
        sleep_sec=args.sleep_sec,
    )
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) if args.format == "json" else markdown(report)
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
