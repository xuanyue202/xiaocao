"""Compare Book B paper returns with A-share index benchmarks.

Read-only utility for the recurring "does the short-line book beat the market?"
question. It reads live Book B snapshots/positions and index daily klines.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.api.client import XiaocaoClient  # noqa: E402
from xiaocao.config import load_settings  # noqa: E402
from xiaocao.live.status import build_digest  # noqa: E402
from xiaocao.live.paper_research import day, fingerprint, money, number, read_json, read_jsonl  # noqa: E402

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
        result = float(number(value, "number"))
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    return read_json(path)


def iter_positions(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


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
    for row in read_jsonl(path):
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


CHINA = ZoneInfo("Asia/Shanghai")


def observed_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing observation timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA)
    return parsed.astimezone(CHINA)


def dated_snapshot(rows: list[dict[str, Any]], date: str) -> dict[str, Any]:
    candidates = []
    for row in rows:
        if row.get("date") != date or row.get("book") != "B":
            continue
        ts = observed_time(row.get("ts"))
        if ts.date().isoformat() != date or ts.time() < time(15):
            continue
        candidates.append((ts, row))
    if not candidates:
        raise ValueError(f"missing exact dated EOD Book B snapshot: {date}")
    latest = max(ts for ts, _ in candidates)
    selected = [row for ts, row in candidates if ts == latest]
    if len({fingerprint(row) for row in selected}) != 1:
        raise ValueError(f"conflicting snapshots at {latest.isoformat()}")
    row = selected[0]
    if row.get("equity_basis") in ("cost_basis", "proxy", "fallback") or row.get("evidence_status") in ("unknown", "degraded"):
        raise ValueError(f"unproved or proxy endpoint mark: {date}")
    initial = money(row.get("initial_capital"), "snapshot initial_capital", nonnegative=True)
    cash = money(row.get("cash"), "snapshot cash", nonnegative=True)
    equity = money(row.get("total_equity_after_exit_fee"), "snapshot equity", nonnegative=True)
    realized = money(row.get("realized_pnl"), "snapshot realized_pnl")
    unrealized = money(row.get("unrealized_pnl_after_fee"), "snapshot unrealized_pnl")
    holdings = row.get("holdings")
    if not isinstance(holdings, list) or row.get("open_positions") != len(holdings):
        raise ValueError("snapshot holdings coverage is unproved")
    liquidation = cost = Decimal(0)
    identities = set()
    for holding in holdings:
        if not isinstance(holding, dict) or holding.get("book") != "B":
            raise ValueError("snapshot holding book is unproved")
        identity = (holding.get("code"), day(holding.get("entry_date")))
        if not identity[0] or identity in identities or identity[1] > date:
            raise ValueError("invalid/duplicate snapshot lot")
        identities.add(identity)
        shares = number(holding.get("shares"), "holding shares")
        if shares <= 0 or shares != shares.to_integral_value():
            raise ValueError("invalid holding shares")
        mark = observed_time(holding.get("latest_time"))
        if mark.date().isoformat() != date or mark.time() < time(15) or mark > latest:
            raise ValueError("holding lacks same-day closing mark evidence")
        if holding.get("source") == "public" or holding.get("mark_basis") in ("cost_basis", "fallback", "proxy"):
            raise ValueError("holding has unsupported mark evidence")
        if number(holding.get("latest_price"), "holding latest_price") <= 0:
            raise ValueError("invalid holding closing price")
        liquidation += money(holding.get("liquidation_value_after_fee"), "holding liquidation", nonnegative=True)
        cost += money(holding.get("cost"), "holding cost", nonnegative=True)
    if equity != cash + liquidation or unrealized != liquidation - cost:
        raise ValueError("snapshot equity/holding accounting does not close")
    flows = money(row.get("net_external_flows", 0), "snapshot net_external_flows")
    if initial <= 0 or equity != initial + flows + realized + unrealized:
        raise ValueError("snapshot capital/PnL accounting does not close")
    return row


def period_portfolio(start: str, end: str) -> dict[str, Any]:
    result = {"return_pct": None, "initial_capital": None, "start_equity": None,
              "equity": None, "cash": None, "realized_pnl": None, "unrealized_pnl": None,
              "period_pnl": None, "net_external_flows": None, "evidence_status": "unknown",
              "return_basis": "unknown", "result_kind": "paper_modeled_portfolio",
              "boundary": "start EOD to end EOD; external flows in (start, end]",
              "source_evidence": {}}
    try:
        day(start)
        day(end)
        if start >= end:
            raise ValueError("period requires start < end")
        if (LIVE_DIR / ".ledger_txn" / "pending.json").exists():
            raise ValueError("unresolved paper ledger transaction")
        snapshots = read_jsonl(LIVE_DIR / "paper_holdings_snapshots.jsonl")
        first = dated_snapshot(snapshots, start)
        last = dated_snapshot(snapshots, end)
        start_ts, end_ts = observed_time(first["ts"]), observed_time(last["ts"])
        initial = money(first["initial_capital"], "initial_capital")
        for observation in snapshots:
            if observation.get("book") == "B" and start <= str(observation.get("date") or "") <= end:
                if money(observation.get("initial_capital"), "observed initial_capital") != initial:
                    raise ValueError("intervening capital baseline change")
                if "net_external_flows" in observation and not ("net_external_flows" in first and "net_external_flows" in last):
                    raise ValueError("intervening flow evidence lacks endpoint counters")
        if money(last["initial_capital"], "end initial_capital") != initial:
            raise ValueError("capital baseline changed within period")
        start_equity = money(first["total_equity_after_exit_fee"], "start equity")
        end_equity = money(last["total_equity_after_exit_fee"], "end equity")
        flow_path = LIVE_DIR / "paper_capital_flows.jsonl"
        flow_rows = read_jsonl(flow_path) if flow_path.exists() else []
        flows = []
        ids = set()
        for flow in flow_rows:
            if flow.get("book") != "B":
                continue
            flow_day = day(flow.get("date"))
            if not start <= flow_day <= end:
                continue
            flow_ts = observed_time(flow.get("ts"))
            if flow_ts.date().isoformat() != flow_day:
                raise ValueError("flow observation date mismatch")
            if not start_ts < flow_ts <= end_ts:
                continue
            flow_id = flow.get("flow_id")
            if not flow_id or flow_id in ids or flow.get("verified") is not True or not flow.get("source_evidence"):
                raise ValueError("unverified/duplicate external flow")
            ids.add(flow_id)
            amount = money(flow.get("amount"), "external flow")
            flows.append((flow_ts, amount, flow))
        net_flow = sum((amount for _, amount, _ in flows), Decimal(0))
        explicit_flows = "net_external_flows" in first or "net_external_flows" in last
        if explicit_flows and not ("net_external_flows" in first and "net_external_flows" in last):
            raise ValueError("incomplete endpoint external-flow counters")
        delta = money(last.get("net_external_flows", 0), "end flows") - money(first.get("net_external_flows", 0), "start flows")
        if net_flow != delta:
            raise ValueError("dated flow evidence does not match endpoint capital counters")
        for observation in snapshots:
            if observation.get("book") != "B" or "net_external_flows" not in observation:
                continue
            if not start <= str(observation.get("date") or "") <= end:
                continue
            observation_ts = observed_time(observation.get("ts"))
            if not start_ts <= observation_ts <= end_ts:
                continue
            observed_delta = money(observation["net_external_flows"], "observed flows") - money(first.get("net_external_flows", 0), "start flows")
            proved_delta = sum((amount for ts, amount, _ in flows if ts <= observation_ts), Decimal(0))
            if observed_delta != proved_delta:
                raise ValueError("intervening snapshot funding is not backed by dated flow evidence")
        # Legacy producer writes fixed-capital paper snapshots. Retain this
        # contract assumption explicitly; it is not a claim of flow discovery.
        flow_basis = "verified_dated_flows" if flow_path.exists() else "fixed_paper_capital_contract_assumption_no_intervening_flow_evidence"
        duration = Decimal(str((end_ts - start_ts).total_seconds()))
        denominator = start_equity + sum((amount * Decimal(str((end_ts - ts).total_seconds())) / duration
                                          for ts, amount, _ in flows), Decimal(0))
        if denominator <= 0:
            raise ValueError("non-positive flow-adjusted return denominator")
        pnl = end_equity - start_equity - net_flow
        result.update(return_pct=round(float(pnl / denominator * 100), 4),
                      initial_capital=float(initial), start_equity=float(start_equity),
                      equity=float(end_equity), cash=float(money(last["cash"], "cash")),
                      realized_pnl=float(money(last["realized_pnl"], "realized_pnl")),
                      unrealized_pnl=float(money(last["unrealized_pnl_after_fee"], "unrealized_pnl")),
                      period_pnl=float(pnl), net_external_flows=float(net_flow), evidence_status="verified",
                      return_basis="modified_dietz_eod_to_eod" if flows else "eod_to_eod",
                      flow_basis=flow_basis,
                      source_evidence={"start_snapshot_sha256": fingerprint(first),
                                       "end_snapshot_sha256": fingerprint(last),
                                       "period_flows_sha256": fingerprint([row for _, _, row in flows])})
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        result["evidence_reason"] = str(exc)
    return result


def paper_stats(start: str, end: str) -> dict[str, Any]:
    portfolio = period_portfolio(start, end)
    returns: list[float] = []
    by_mode: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "returns": []})
    by_exit: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "pnl": 0.0, "returns": []})
    positions, closed, opened, unknown = [], [], [], []
    cohort_evidence = []
    cohort_complete = True
    identities = set()
    try:
        for p in read_jsonl(LIVE_DIR / "positions.jsonl"):
            if p.get("book") != "B":
                continue
            entry_date = day(p.get("entry_date"))
            if not start <= entry_date <= end:
                continue
            identity = (p.get("code"), entry_date)
            if not identity[0] or identity in identities:
                raise ValueError("invalid/duplicate cohort lot identity")
            identities.add(identity)
            shares = number(p.get("shares"), "cohort shares")
            if shares <= 0 or shares != shares.to_integral_value():
                raise ValueError("invalid cohort shares")
            cost = money(p.get("entry_cash_out"), "cohort entry cost", nonnegative=True)
            if cost <= 0:
                raise ValueError("invalid cohort cost")
            positions.append(p)
            evidence = {k: p.get(k) for k in ("book", "code", "entry_date", "shares", "entry_cash_out", "mode")}
            exit_date = p.get("exit_date")
            if p.get("status") == "closed" and exit_date and day(exit_date) <= end:
                if exit_date < entry_date:
                    raise ValueError("cohort exit precedes entry")
                pnl = money(p.get("realized_pnl"), "cohort realized_pnl")
                cost = money(p.get("entry_cash_out"), "cohort entry cost", nonnegative=True)
                if cost <= 0:
                    raise ValueError("invalid cohort cost")
                ret = float(pnl / cost * 100)
                closed.append(p)
                returns.append(ret)
                for groups, key in ((by_mode, str(p.get("mode") or "unknown")),
                                    (by_exit, str(p.get("exit_reason") or "unknown"))):
                    groups[key]["n"] += 1
                    groups[key]["pnl"] += float(pnl)
                    groups[key]["returns"].append(ret)
                evidence.update(exit_date=exit_date, realized_pnl=float(pnl), exit_reason=p.get("exit_reason"))
            elif p.get("status") == "open" or (p.get("status") == "closed" and exit_date and day(exit_date) > end):
                opened.append(p)
            else:
                unknown.append(p)
            cohort_evidence.append(evidence)
        cohort_status = "unknown" if unknown else "available"
    except (OSError, ValueError, TypeError) as exc:
        cohort_status = "unknown"
        cohort_complete = False
        portfolio["cohort_evidence_reason"] = str(exc)
        positions, closed, opened, returns, cohort_evidence = [], [], [], [], []
        by_mode.clear()
        by_exit.clear()
    decomp = defaultdict(float)
    decomp_status = "missing"
    path = LIVE_DIR / "pnl_decompose.csv"
    if path.exists():
        try:
            with path.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    entry, exit_ = str(row.get("entry_date") or ""), str(row.get("exit_date") or "")
                    if start <= entry <= end and entry <= exit_ <= end:
                        for key in ("m_pick_alpha", "m_entry_slippage", "m_exit_timing", "fees", "realized_pnl"):
                            decomp[key] += float(money(row.get(key), key))
            decomp_status = "available"
        except (OSError, ValueError, TypeError) as exc:
            decomp.clear()
            decomp_status = "unknown"
            portfolio["decompose_evidence_reason"] = str(exc)
    return {
        **portfolio, "start": start, "end": end,
        "buy_count": len(positions) if cohort_complete else None,
        "closed_count": len(closed) if cohort_complete else None, "open_count": len(opened) if cohort_complete else None,
        "unknown_status_count": len(unknown), "cohort_evidence_status": cohort_status,
        "cohort_kind": "entry_date_trade_cohort; unweighted closed-lot statistics, not portfolio returns",
        "cohort_sha256": fingerprint(cohort_evidence),
        "closed_avg_ret_pct": round(statistics.mean(returns), 4) if returns else None,
        "closed_median_ret_pct": round(statistics.median(returns), 4) if returns else None,
        "closed_win_rate_pct": round(sum(r > 0 for r in returns) / len(returns) * 100, 4) if returns else None,
        "mode_breakdown": summarize_groups(by_mode), "exit_breakdown": summarize_groups(by_exit),
        "pnl_decompose": {k: round(v, 2) for k, v in decomp.items()},
        "pnl_decompose_evidence_status": decomp_status,
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
    try:
        reconstructed = load_reconstructed(reconstructed_path)
    except (OSError, ValueError) as exc:
        return [{"code": code, "name": name, "error": f"invalid reconstructed evidence: {exc}"}
                for code, name in index_map.items()]
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
        "paper_vs_index_avg_open_pp": None,  # EOD portfolio boundary does not match start-open benchmark.
        "paper_vs_index_avg_close_pp": round(paper["return_pct"] - avg_close, 4) if avg_close is not None and paper.get("return_pct") is not None else None,
    }


def display(value: Any, spec: str, suffix: str = "") -> str:
    try:
        parsed = float(number(value, "display"))
        if not math.isfinite(parsed):
            return "N/A"
        return format(parsed, spec) + suffix
    except (ValueError, TypeError, OverflowError):
        return "N/A"


def markdown(report: dict[str, Any]) -> str:
    paper = report["paper"]
    lines = [
        f"# Paper Vs Market {paper['start']}..{paper['end']}", "", "## Summary", "",
        "Paper modeled portfolio NAV; this is not a broker-confirmed or executable return.",
        str(paper.get("boundary", "EOD to EOD")),
        f"Evidence: {paper.get('evidence_status', 'unknown')} — {paper.get('evidence_reason', paper.get('return_basis', 'unknown'))}",
        f"Flow basis: {paper.get('flow_basis', 'unknown')}", "",
        "| item | value |", "|---|---:|",
        f"| Book B portfolio return | {display(paper.get('return_pct'), '+.2f', '%')} |",
        f"| start / end equity | {display(paper.get('start_equity'), ',.2f')} / {display(paper.get('equity'), ',.2f')} |",
        f"| end cash | {display(paper.get('cash'), ',.2f')} |",
        f"| period PnL / external flows | {display(paper.get('period_pnl'), '+,.2f')} / {display(paper.get('net_external_flows'), '+,.2f')} |",
        f"| end cumulative realized / unrealized | {display(paper.get('realized_pnl'), '+,.2f')} / {display(paper.get('unrealized_pnl'), '+,.2f')} |",
        f"| entry cohort buys / closed by end / open as of end | {display(paper.get('buy_count'), '.0f')} / {display(paper.get('closed_count'), '.0f')} / {display(paper.get('open_count'), '.0f')} |",
        f"| cohort closed avg / median / win-rate | {display(paper.get('closed_avg_ret_pct'), '+.2f', '%')} / {display(paper.get('closed_median_ret_pct'), '+.2f', '%')} / {display(paper.get('closed_win_rate_pct'), '.2f', '%')} |",
        f"| index coverage | {report.get('index_coverage', '0/0')} |",
        f"| avg index close->close | {display(report.get('index_avg_close_to_close_pct'), '+.2f', '%')} |",
        f"| Book B - avg index close->close | {display(report.get('paper_vs_index_avg_close_pp'), '+.2f', 'pp')} |",
        "", "Entry cohort statistics are unweighted closed-lot outcomes, separate from portfolio return.",
        f"Cohort evidence: {paper.get('cohort_evidence_status', 'unknown')}",
        "", "## Indices", "", "| index | open->end close | close->close | close MDD |",
        "|---|---:|---:|---:|",
    ]
    for row in report["indices"]:
        if "error" in row:
            lines.append(f"| {row['name']} {row['code']} | {row['error']} | - | - |")
        else:
            lines.append(f"| {row['name']} {row['code']} | {display(row.get('open_to_close_pct'), '+.2f', '%')} | "
                         f"{display(row.get('close_to_close_pct'), '+.2f', '%')} | {display(row.get('close_mdd_pct'), '+.2f', '%')} |")
    for title, key in (("Mode Breakdown (trade cohort)", "mode_breakdown"), ("Exit Breakdown (trade cohort)", "exit_breakdown")):
        lines += ["", f"## {title}", "", "| group | n | avg ret | pnl |", "|---|---:|---:|---:|"]
        for row in paper.get(key, []):
            lines.append(f"| {row['key']} | {row['n']} | {display(row.get('avg_ret_pct'), '+.2f', '%')} | {display(row.get('pnl'), '+,.2f')} |")
    decomp = paper.get("pnl_decompose") or {}
    if decomp:
        lines += ["", "## PnL Decompose (trade cohort)", "", "| item | contribution |", "|---|---:|"]
        for key, sign in (("m_pick_alpha", 1), ("m_entry_slippage", -1), ("m_exit_timing", 1), ("fees", -1), ("realized_pnl", 1)):
            value = decomp.get(key)
            lines.append(f"| {key} | {display(value * sign if value is not None else None, '+,.2f')} |")
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
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) if args.format == "json" else markdown(report)
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
