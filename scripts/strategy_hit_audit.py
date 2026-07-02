#!/usr/bin/env python3
"""Project local strategy-hit evidence into a compact review table.

Reads local artifacts only:

- output/live/signal_snapshots.jsonl
- output/live/positions.jsonl
- output/live/paper_trades.jsonl
- output/cohorts/cohort_snapshots.jsonl

It is an observability tool, not a strategy actuator.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        try:
            row = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _code(row: dict[str, Any]) -> str:
    return str(row.get("code") or row.get("stockCode") or row.get("stockId") or "")


def _name(*rows: dict[str, Any] | None) -> str:
    for row in rows:
        if not row:
            continue
        v = row.get("name") or row.get("codeName") or row.get("stockName")
        if v:
            return str(v)
    return ""


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _md_escape(value: Any) -> str:
    return _fmt(value).replace("|", "\\|").replace("\n", " ")


def _latest_by_code(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = _code(row)
        if code:
            out[code] = row
    return out


def _group_by_code(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        code = _code(row)
        if code:
            out.setdefault(code, []).append(row)
    return out


def _signal_tier(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "-"
    parts: list[str] = []
    if signal.get("vb_star"):
        parts.append(f"★B{_fmt(signal.get('vb_rank'))}")
    if signal.get("kp_star"):
        parts.append(f"★KP{_fmt(signal.get('kp_rank'))}")
    if signal.get("mode_star"):
        parts.append(f"★M{_fmt(signal.get('mode_rank'))}")
    if not parts and signal.get("quality_tag"):
        parts.append(str(signal["quality_tag"]))
    return "/".join(parts) or "-"


def _book_b_buy(trades: list[dict[str, Any]], positions: list[dict[str, Any]]) -> dict[str, Any] | None:
    buys = [
        r for r in trades
        if str(r.get("side", "")).upper() == "BUY" and str(r.get("book", "B")) == "B"
    ]
    if buys:
        return buys[-1]
    buys = [r for r in positions if str(r.get("book", "B")) == "B" and r.get("entry_price")]
    return buys[-1] if buys else None


def _classification(signal: dict[str, Any] | None, buy: dict[str, Any] | None,
                    cohorts: list[dict[str, Any]]) -> str:
    if buy and signal:
        return "本地正式买入"
    if signal and signal.get("vb_star"):
        return "本地推荐未成交/无买入记录"
    if signal:
        return "本地观察信号"
    if cohorts:
        layers = {str(r.get("layer")) for r in cohorts}
        return "研究队列-基准" if "benchmark" in layers else "研究队列-观察"
    return "无本地证据"


def build_projection(*, date: str, root: Path = ROOT, codes: set[str] | None = None) -> list[dict[str, Any]]:
    signals = [r for r in _jsonl(root / "output" / "live" / "signal_snapshots.jsonl") if r.get("date") == date]
    positions = [r for r in _jsonl(root / "output" / "live" / "positions.jsonl") if r.get("entry_date") == date]
    trades = [r for r in _jsonl(root / "output" / "live" / "paper_trades.jsonl") if r.get("date") == date]
    cohorts = [r for r in _jsonl(root / "output" / "cohorts" / "cohort_snapshots.jsonl") if r.get("date") == date]

    sig_by_code = _latest_by_code(signals)
    pos_by_code = _group_by_code(positions)
    trade_by_code = _group_by_code(trades)
    cohort_by_code = _group_by_code(cohorts)

    all_codes = set(sig_by_code) | set(pos_by_code) | set(trade_by_code) | set(cohort_by_code)
    if codes:
        all_codes &= codes

    out: list[dict[str, Any]] = []
    for code in sorted(all_codes):
        signal = sig_by_code.get(code)
        positions_for_code = pos_by_code.get(code, [])
        trades_for_code = trade_by_code.get(code, [])
        cohorts_for_code = cohort_by_code.get(code, [])
        buy = _book_b_buy(trades_for_code, positions_for_code)
        cohort_ids = sorted({str(r.get("cohort_id")) for r in cohorts_for_code if r.get("cohort_id")})
        authority = sorted({str(r.get("authority")) for r in cohorts_for_code if r.get("authority") is not None})
        out.append({
            "code": code,
            "name": _name(signal, buy, positions_for_code[-1] if positions_for_code else None,
                          cohorts_for_code[-1] if cohorts_for_code else None),
            "classification": _classification(signal, buy, cohorts_for_code),
            "mode": signal.get("mode") if signal else "-",
            "signal_tier": _signal_tier(signal),
            "quality": signal.get("quality_tag") if signal else "-",
            "primary_score": signal.get("primary_score") if signal else None,
            "qibao_kind": signal.get("qibaoBenchmarkKind") if signal else "-",
            "book_b_buy": "yes" if buy else "no",
            "shares": buy.get("shares") if buy else None,
            "entry_price": buy.get("price") or buy.get("entry_price") if buy else None,
            "cohorts": ",".join(cohort_ids) if cohort_ids else "-",
            "cohort_authority": ",".join(authority) if authority else "-",
            "reason": signal.get("reason") if signal else (cohorts_for_code[-1].get("note") if cohorts_for_code else "-"),
        })
    return out


def render_markdown(rows: list[dict[str, Any]], *, date: str) -> str:
    lines = [
        f"# 策略命中审计 {date}",
        "",
        "这是本地证据投影表，只做复盘阅读。cohort 行保留原始 authority，不会变成买入信号。",
        "",
        "| 代码 | 名称 | 归类 | 模式 | 信号层级 | 质量 | 主分 | Book B买入 | 股数 | 成交/入场价 | cohort | authority | 原因 |",
        "|---|---|---|---|---|---:|---:|---|---:|---:|---|---:|---|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(_md_escape(r.get(k)) for k in [
            "code", "name", "classification", "mode", "signal_tier", "quality", "primary_score",
            "book_b_buy", "shares", "entry_price", "cohorts", "cohort_authority", "reason",
        ]) + " |")
    if not rows:
        lines.append("| - | - | 无本地证据 | - | - | - | - | - | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="trade date, YYYY-MM-DD")
    ap.add_argument("--codes", default="", help="optional comma-separated code filter")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("--output", help="optional output path; default prints to stdout")
    args = ap.parse_args()

    codes = {c.strip() for c in args.codes.split(",") if c.strip()} or None
    rows = build_projection(date=args.date, codes=codes)
    if args.format == "json":
        text = json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = render_markdown(rows, date=args.date)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {len(rows)} rows -> {out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
