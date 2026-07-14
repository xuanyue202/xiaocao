"""Compare Book B paper returns with A-share index benchmarks.

Read-only utility for the recurring "does the short-line book beat the market?"
question. It reads live Book B snapshots/positions and index daily klines.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.live.status import build_digest  # noqa: E402

LIVE_DIR = ROOT / "output" / "live"
RECONSTRUCTED_DAILY = LIVE_DIR / "daily_reconstructed.jsonl"
DEFAULT_INDICES = {
    "000001.XSHG": "上证指数",
    "399001.XSHE": "深证成指",
    "399006.XSHE": "创业板指",
    "000852.XSHG": "中证1000",
}


def f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def iter_positions(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def client() -> XiaocaoClient:
    settings = load_settings(None)
    return XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db"),
    )


def rows_from_kline(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "list", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def normal_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def load_reconstructed(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = str(row.get("code") or "")
        day = normal_date(row.get("date"))
        if code and day:
            out[code][day] = {**row, "tradeDate": day}
    return out


def close_mdd(rows: list[dict[str, Any]]) -> float:
    peak = 0.0
    mdd = 0.0
    for row in rows:
        close = f(row.get("close"))
        if close <= 0:
            continue
        peak = max(peak, close)
        if peak:
            mdd = min(mdd, (close / peak - 1.0) * 100.0)
    return mdd


def summarize_groups(groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for key, value in groups.items():
        returns = value["returns"]
        rows.append({
            "key": key,
            "n": value["n"],
            "avg_ret_pct": round(statistics.mean(returns), 4) if returns else 0.0,
            "pnl": round(value["pnl"], 2),
        })
    return sorted(rows, key=lambda x: x["pnl"])


def paper_stats(start: str, end: str) -> dict[str, Any]:
    account = load_json(LIVE_DIR / "paper_account.json")
    digest = build_digest(live_dir=LIVE_DIR, market_date=end)
    initial = f(account.get("initial_capital"), 100000.0)
    book_b = digest.get("book_b") or {}
    positions = [
        p for p in iter_positions(LIVE_DIR / "positions.jsonl")
        if p.get("book", "B") == "B" and start <= str(p.get("entry_date") or "") <= end
    ]
    closed = [p for p in positions if p.get("status") == "closed"]
    opened = [p for p in positions if p.get("status", "open") == "open"]
    returns: list[float] = []
    by_mode: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "returns": []})
    by_exit: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "returns": []})
    for p in closed:
        pnl = f(p.get("realized_pnl"))
        cost = f(p.get("entry_cash_out"))
        ret = pnl / cost * 100.0 if cost else 0.0
        returns.append(ret)
        mode = str(p.get("mode") or "unknown")
        by_mode[mode]["n"] += 1
        by_mode[mode]["pnl"] += pnl
        by_mode[mode]["returns"].append(ret)
        reason = str(p.get("exit_reason") or "unknown")
        by_exit[reason]["n"] += 1
        by_exit[reason]["pnl"] += pnl
        by_exit[reason]["returns"].append(ret)
    decomp = defaultdict(float)
    path = LIVE_DIR / "pnl_decompose.csv"
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if start <= str(row.get("entry_date") or "") and str(row.get("exit_date") or "") <= end:
                    for key in ("m_pick_alpha", "m_entry_slippage", "m_exit_timing", "fees", "realized_pnl"):
                        decomp[key] += f(row.get(key))
    equity = f(book_b.get("equity"))
    return {
        "start": start,
        "end": end,
        "initial_capital": initial,
        "equity": equity,
        "return_pct": round((equity / initial - 1.0) * 100.0, 4) if initial else 0.0,
        "cash": f(book_b.get("cash")),
        "realized_pnl": f(book_b.get("realized_pnl")),
        "unrealized_pnl": f(book_b.get("unrealized_pnl")),
        "buy_count": len(positions),
        "closed_count": len(closed),
        "open_count": len(opened),
        "closed_avg_ret_pct": round(statistics.mean(returns), 4) if returns else 0.0,
        "closed_median_ret_pct": round(statistics.median(returns), 4) if returns else 0.0,
        "closed_win_rate_pct": round(sum(1 for r in returns if r > 0) / len(returns) * 100.0, 4) if returns else 0.0,
        "mode_breakdown": summarize_groups(by_mode),
        "exit_breakdown": summarize_groups(by_exit),
        "pnl_decompose": {k: round(v, 2) for k, v in decomp.items()},
    }


def index_report(
    c: XiaocaoClient,
    *,
    start: str,
    end: str,
    index_map: dict[str, str],
    count: int,
    reconstructed_path: Path = RECONSTRUCTED_DAILY,
) -> list[dict[str, Any]]:
    reconstructed = load_reconstructed(reconstructed_path)
    indices = []
    for code, name in index_map.items():
        rows = rows_from_kline(c.date_kline(code, count=count, freq="D", adj="qfq"))
        by_date = {normal_date(r.get("tradeDate")): r for r in rows}
        by_date.update(reconstructed.get(code, {}))
        if start not in by_date or end not in by_date:
            indices.append({"code": code, "name": name, "error": "missing start/end bar"})
            continue
        seq = [by_date[day] for day in sorted(day for day in by_date if start <= day <= end)]
        s = by_date[start]
        e = by_date[end]
        start_open = f(s.get("open"))
        start_close = f(s.get("close"))
        end_close = f(e.get("close"))
        if start_open <= 0 or start_close <= 0 or end_close <= 0:
            indices.append({
                "code": code,
                "name": name,
                "error": "invalid non-positive start/end price",
            })
            continue
        indices.append({
            "code": code,
            "name": name,
            "open_to_close_pct": round((end_close / start_open - 1.0) * 100.0, 4),
            "close_to_close_pct": round((end_close / start_close - 1.0) * 100.0, 4),
            "close_mdd_pct": round(close_mdd(seq), 4),
            "end_source": str(e.get("source") or "date_kline"),
        })
    return indices


def build_report(start: str, end: str, index_map: dict[str, str], count: int) -> dict[str, Any]:
    c = client()
    paper = paper_stats(start, end)
    indices = index_report(c, start=start, end=end, index_map=index_map, count=count)
    valid_by_code = {str(r.get("code")): r for r in indices if "error" not in r}
    required_codes = tuple(DEFAULT_INDICES)
    valid_standard = [valid_by_code[code] for code in required_codes if code in valid_by_code]
    complete = len(valid_standard) == len(required_codes)
    avg_open = statistics.mean(r["open_to_close_pct"] for r in valid_standard) if complete else None
    avg_close = statistics.mean(r["close_to_close_pct"] for r in valid_standard) if complete else None
    return {
        "paper": paper,
        "indices": indices,
        "index_coverage": f"{len(valid_standard)}/{len(required_codes)}",
        "index_avg_open_to_close_pct": round(avg_open, 4) if avg_open is not None else None,
        "index_avg_close_to_close_pct": round(avg_close, 4) if avg_close is not None else None,
        "paper_vs_index_avg_open_pp": round(paper["return_pct"] - avg_open, 4) if avg_open is not None else None,
        "paper_vs_index_avg_close_pp": round(paper["return_pct"] - avg_close, 4) if avg_close is not None else None,
    }


def markdown(report: dict[str, Any]) -> str:
    paper = report["paper"]
    avg_index = report.get("index_avg_open_to_close_pct")
    spread = report.get("paper_vs_index_avg_open_pp")
    avg_index_text = f"{avg_index:+.2f}%" if avg_index is not None else "N/A"
    spread_text = f"{spread:+.2f}pp" if spread is not None else "N/A"
    lines = [
        f"# Paper Vs Market {paper['start']}..{paper['end']}",
        "",
        "## Summary",
        "",
        "| item | value |",
        "|---|---:|",
        f"| Book B return | {paper['return_pct']:+.2f}% |",
        f"| equity / cash | {paper['equity']:,.2f} / {paper['cash']:,.2f} |",
        f"| realized / unrealized | {paper['realized_pnl']:+,.2f} / {paper['unrealized_pnl']:+,.2f} |",
        f"| buys / closed / open | {paper['buy_count']} / {paper['closed_count']} / {paper['open_count']} |",
        f"| closed avg / median / win-rate | {paper['closed_avg_ret_pct']:+.2f}% / {paper['closed_median_ret_pct']:+.2f}% / {paper['closed_win_rate_pct']:.2f}% |",
        f"| index coverage | {report.get('index_coverage', '0/0')} |",
        f"| avg index open->close | {avg_index_text} |",
        f"| Book B - avg index | {spread_text} |",
        "",
        "## Indices",
        "",
        "| index | open->end close | close->close | close MDD |",
        "|---|---:|---:|---:|",
    ]
    for row in report["indices"]:
        if "error" in row:
            lines.append(f"| {row['name']} {row['code']} | {row['error']} | - | - |")
        else:
            lines.append(
                f"| {row['name']} {row['code']} | {row['open_to_close_pct']:+.2f}% | "
                f"{row['close_to_close_pct']:+.2f}% | {row['close_mdd_pct']:+.2f}% |"
            )
    lines += ["", "## Mode Breakdown", "", "| mode | n | avg ret | pnl |", "|---|---:|---:|---:|"]
    for row in paper["mode_breakdown"]:
        lines.append(f"| {row['key']} | {row['n']} | {row['avg_ret_pct']:+.2f}% | {row['pnl']:+,.2f} |")
    lines += ["", "## Exit Breakdown", "", "| exit | n | avg ret | pnl |", "|---|---:|---:|---:|"]
    for row in paper["exit_breakdown"]:
        lines.append(f"| {row['key']} | {row['n']} | {row['avg_ret_pct']:+.2f}% | {row['pnl']:+,.2f} |")
    decomp = paper.get("pnl_decompose") or {}
    if decomp:
        lines += [
            "",
            "## PnL Decompose",
            "",
            "| item | contribution |",
            "|---|---:|",
            f"| pick_alpha | {f(decomp.get('m_pick_alpha')):+,.2f} |",
            f"| entry_slippage_cost | {-f(decomp.get('m_entry_slippage')):+,.2f} |",
            f"| exit_timing | {f(decomp.get('m_exit_timing')):+,.2f} |",
            f"| fees | {-f(decomp.get('fees')):+,.2f} |",
            f"| realized_pnl | {f(decomp.get('realized_pnl')):+,.2f} |",
        ]
    return "\n".join(lines) + "\n"


def parse_indices(text: str) -> dict[str, str]:
    if not text:
        return dict(DEFAULT_INDICES)
    out = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            code, name = part.split("=", 1)
            out[code.strip()] = name.strip() or code.strip()
        else:
            out[part] = DEFAULT_INDICES.get(part, part)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-06-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--indices", default="")
    ap.add_argument("--count", type=int, default=80)
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--output", default="")
    args = ap.parse_args()
    end = args.end or str(build_digest(live_dir=LIVE_DIR).get("market_date") or "")
    report = build_report(args.start, end, parse_indices(args.indices), args.count)
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
