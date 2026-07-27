#!/usr/bin/env python3
"""Replay the exact Book-B mode switch on executable live all-hit labels.

This is intentionally not a second implementation.  It imports the same mode
state, candidate selector, target weights, and board-lot planner consumed by
the live recommendation and paper actuator.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

from xiaocao.api.cache import SQLiteCache
from xiaocao.api.client import XiaocaoClient
from xiaocao.backtest import list_trade_days
from xiaocao.config import load_settings
from xiaocao.strategy.mode_switch import (
    ACTIVE,
    PROVISIONAL,
    annotate_candidates,
    decide_modes,
    load_live_executable_evidence,
    plan_board_lot_orders,
    select_executable_candidates,
)


DEFAULT_TRAINING = ROOT / "output" / "live" / "training_rows.parquet"
DEFAULT_INITIAL_CAPITAL = 100000.0
DEFAULT_FEE_RATE = 0.0001


def _client() -> XiaocaoClient:
    settings = load_settings(None)
    return XiaocaoClient(
        base_url=settings.base_url,
        timeout=settings.timeout,
        retries=settings.retries,
        cache=SQLiteCache(ROOT / "output" / ".cache" / "xiaocao.db"),
    )


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def _load_candidates(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).copy()
    if "is_live" in frame.columns:
        frame = frame[frame["is_live"].map(_truthy)]
    if "book" in frame.columns:
        frame = frame[frame["book"].fillna("B").astype(str).eq("B")]
    frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame[~frame["code"].astype(str).str.endswith(".BJSE")]
    return frame.sort_values(["date", "code"]).drop_duplicates(["date", "code"], keep="last")


def _float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if pd.notna(out) else default


def run_replay(
    *,
    training_path: Path,
    start: str,
    end: str,
    initial_capital: float,
    fee_rate: float,
    trade_days: list[str],
) -> dict[str, Any]:
    frame = _load_candidates(training_path)
    evidence = load_live_executable_evidence(training_path)
    replay_days = [day for day in trade_days if start <= day <= end]
    candidates_by_day = {
        day: group.to_dict(orient="records")
        for day, group in frame[frame["date"].between(start, end)].groupby("date")
    }

    cohorts: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    mode_audit: list[dict[str, Any]] = []
    for day_index, day in enumerate(replay_days):
        settled_pnl = sum(cohort["pnl"] for cohort in cohorts if cohort["exit_index"] < day_index)
        nav = initial_capital + settled_pnl
        open_cost = sum(cohort["cost"] for cohort in cohorts if cohort["exit_index"] >= day_index)
        cash = max(0.0, nav - open_cost)

        raw_candidates = candidates_by_day.get(day, [])
        modes = {str(row.get("mode") or "") for row in raw_candidates if row.get("mode")}
        decisions = decide_modes(modes, day, evidence, trade_days)
        annotated = annotate_candidates(raw_candidates, decisions)
        ranked = select_executable_candidates(annotated, top_n=3)
        fillable = []
        for row in sorted(ranked, key=lambda item: int(_float(item.get("mode_exec_candidate_rank"), 9999))):
            if not row.get("mode_trade_eligible"):
                continue
            if not _truthy(row.get("executable_fillable")):
                continue
            price = _float(row.get("executable_entry_price"))
            ret = _float(row.get("executable_net_ret"), float("nan"))
            if price <= 0 or pd.isna(ret):
                continue
            executable = dict(row)
            executable["execution_price"] = price
            fillable.append(executable)
        orders = plan_board_lot_orders(
            fillable,
            nav=nav,
            cash_limit=min(cash, nav * 0.50),
            fee_rate=fee_rate,
            price_key="execution_price",
            max_batch_ratio=0.50,
        )
        positions = []
        cost = 0.0
        pnl = 0.0
        market_pnl = 0.0
        for row in orders:
            cash_out = _float(row.get("mode_exec_planned_cash_out"))
            net_ret = _float(row.get("executable_net_ret"))
            market_ret = _float(row.get("market_return_pct"))
            position_pnl = cash_out * net_ret / 100.0
            cost += cash_out
            pnl += position_pnl
            market_pnl += cash_out * market_ret / 100.0
            positions.append({
                "code": row.get("code"),
                "name": row.get("name"),
                "mode": row.get("mode"),
                "mode_state": row.get("mode_state"),
                "shares": int(row.get("mode_exec_planned_shares") or 0),
                "entry_price": _float(row.get("execution_price")),
                "entry_basis": row.get("executable_entry_basis"),
                "target_weight": _float(row.get("mode_exec_target_weight")),
                "cash_out": cash_out,
                "net_return_pct": net_ret,
                "market_return_pct": market_ret,
                "pnl": position_pnl,
            })
        if cost > 0:
            cohorts.append({
                "signal_date": day,
                "entry_index": day_index,
                "exit_index": day_index + 1,
                "cost": cost,
                "pnl": pnl,
                "market_pnl": market_pnl,
                "positions": positions,
            })

        close_settled = sum(cohort["pnl"] for cohort in cohorts if cohort["exit_index"] <= day_index)
        equity_close = initial_capital + close_settled
        daily.append({
            "date": day,
            "nav_at_decision": round(nav, 4),
            "cash_at_decision": round(cash, 4),
            "mode_states": {
                mode: {
                    "state": decision.state,
                    "window": decision.selected_window,
                    "reason": decision.reason,
                }
                for mode, decision in decisions.items()
            },
            "eligible_candidates": sum(bool(row.get("mode_trade_eligible")) for row in ranked),
            "bought": len(positions),
            "batch_cost": round(cost, 4),
            "batch_exposure_pct": round(cost / nav * 100.0, 6) if nav else 0.0,
            "batch_pnl": round(pnl, 4),
            "batch_market_return_pct": round(market_pnl / cost * 100.0, 6) if cost else 0.0,
            "batch_market_pnl": round(market_pnl, 4),
            "equity_close": round(equity_close, 4),
            "positions": positions,
        })
        for mode, decision in decisions.items():
            mode_audit.append({"date": day, "mode": mode, **asdict(decision)})

    final_equity = initial_capital + sum(cohort["pnl"] for cohort in cohorts)
    market_equity = initial_capital + sum(cohort["market_pnl"] for cohort in cohorts)
    peak = initial_capital
    max_drawdown = 0.0
    for row in daily:
        equity = float(row["equity_close"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
    # The final signal settles on D+1, which can lie just beyond the requested
    # signal window. Include that terminal equity so MDD is fully settled.
    peak = max(peak, final_equity)
    max_drawdown = max(max_drawdown, (peak - final_equity) / peak if peak else 0.0)
    return {
        "summary": {
            "start": start,
            "end": end,
            "initial_capital": initial_capital,
            "final_equity": round(final_equity, 2),
            "return_pct": round((final_equity / initial_capital - 1.0) * 100.0, 4),
            "same_exposure_market_equity": round(market_equity, 2),
            "same_exposure_market_return_pct": round((market_equity / initial_capital - 1.0) * 100.0, 4),
            "alpha_market_pp": round((final_equity - market_equity) / initial_capital * 100.0, 4),
            "max_drawdown_pct": round(max_drawdown * 100.0, 4),
            "trade_days": sum(row["bought"] > 0 for row in daily),
            "positions": sum(int(row["bought"]) for row in daily),
            "average_exposure_pct": round(
                sum(float(row["batch_exposure_pct"]) for row in daily) / len(daily), 4
            ) if daily else 0.0,
            "evidence_rows": len(evidence),
        },
        "daily": daily,
        "cohorts": cohorts,
        "mode_audit": mode_audit,
    }


def markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        f"# Shared Mode-Switch Replay {summary['start']}..{summary['end']}",
        "",
        "## Summary",
        "",
        "| item | value |",
        "|---|---:|",
        f"| strategy return | {summary['return_pct']:+.2f}% |",
        f"| final equity | {summary['final_equity']:,.2f} |",
        f"| same-exposure four-index gross return | {summary['same_exposure_market_return_pct']:+.2f}% |",
        f"| strategy - market | {summary['alpha_market_pp']:+.2f}pp |",
        f"| max drawdown | {summary['max_drawdown_pct']:.2f}% |",
        f"| trade days / positions | {summary['trade_days']} / {summary['positions']} |",
        f"| average daily new exposure | {summary['average_exposure_pct']:.2f}% |",
        f"| executable evidence rows | {summary['evidence_rows']} |",
        "",
        "## Daily",
        "",
        "| date | mode decisions | bought | exposure | 4-index | batch PnL | equity close |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in result["daily"]:
        labels = ", ".join(
            f"{position['name']}[{position['mode']}/{position['mode_state']}]"
            for position in row["positions"]
        ) or "cash"
        mode_states = ", ".join(
            f"{mode}:{payload['state']}["
            f"{str(payload['window']) + 'd' if payload['window'] else '-'}]"
            for mode, payload in row["mode_states"].items()
        ) or "no candidates"
        lines.append(
            f"| {row['date']} | {mode_states} | {labels} | {row['batch_exposure_pct']:.2f}% | "
            f"{row['batch_market_return_pct']:+.2f}% | "
            f"{row['batch_pnl']:+,.2f} | {row['equity_close']:,.2f} |"
        )
    lines.extend([
        "",
        "## Contract",
        "",
        "- Evidence: live all-hit executable opening-window net returns only; BJSE excluded.",
        "- As-of: D signal becomes mode evidence at D+2 morning; no D-1 outcome leakage.",
        "- State evidence retains the validated 25%/45%/50% weights for 1/2/3 mode signals.",
        "- ACTIVE requires positive one-sided 80% lower bounds versus both the executable pool and four-index benchmark.",
        "- Recent 5-day dual-alpha mean and majority strength promotes directly to ACTIVE; deterioration cools ACTIVE to PROVISIONAL.",
        "- Every eligible mode contributes only its first-ranked stock; any ACTIVE batch targets 50% of NAV, including a single stock.",
        "- Ranking rebuilds mode confidence from the conservative side of the same dual-alpha evidence; no mode_history fallback.",
        "- Ranking and allocation call the same functions as live ★E and Book B.",
        "- Drawdown includes the final signal batch after its D+1 close settlement.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, default=DEFAULT_TRAINING)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL)
    parser.add_argument("--fee-rate", type=float, default=DEFAULT_FEE_RATE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    client = _client()
    calendar_start = min(args.start, "2025-08-01")
    trade_days = list_trade_days(client, calendar_start, args.end)
    if not trade_days:
        raise SystemExit("trade calendar unavailable")
    result = run_replay(
        training_path=args.training,
        start=args.start,
        end=args.end,
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
        trade_days=trade_days,
    )
    suffix = f"{args.start}_{args.end}"
    output = args.output or ROOT / "output" / "research" / f"mode_switch_replay_{suffix}.md"
    json_output = args.json_output or ROOT / "output" / "research" / f"mode_switch_replay_{suffix}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(result), encoding="utf-8")
    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(markdown(result))
    print(f"wrote {output}")
    print(f"wrote {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
