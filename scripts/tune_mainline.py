"""Tune mainline (window, topk, min_hits) — Category B.

Reads cached block_rank rows from SQLite (api_cache table), recomputes
mainline membership per (date) for each candidate (window, topk, min_hits),
intersects with each signal's blocks, evaluates train/test stats.

Also tests inverted (off-mainline) and BKDL-vs-ZHBK source switch, motivated
by 0413-A: 短线 / 弱转强 模式 hunt for "新轮动卡位" — directions NOT yet in
the established main-line.

Cache-only — never calls the API.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from replay_lib import (  # noqa: E402
    CACHE_DB,
    SignalRecord,
    VALIDATED_EXCLUDE,
    evaluate,
    gate_validated_baseline,
    load_universe,
    trade_days_in_universe,
)
from xiaocao.strategy.mainline import compute_mainline  # noqa: E402


# Endpoint paths used by run_strategy: the FULL block rank (model=0) is what
# main-line should be derived from (per the comment in backtest.py:404).
BLOCK_RANK_ENDPOINT = "/stock/xiao_cao_industry_block_rank"
CATEGORY_RANK_ENDPOINT = "/stock/xiao_cao_block_category_rank_v3"


def load_rank_history(
    endpoint: str,
    model: int,
    days: list[str],
) -> dict[str, list[dict]]:
    """Pull cached block-rank responses keyed by date.

    Date format: API expects YYYYMMDD; we normalize.
    Returns {YYYY-MM-DD: rows}. Days with no cached entry are skipped silently.
    """
    out: dict[str, list[dict]] = {}
    with sqlite3.connect(CACHE_DB) as conn:
        rows = conn.execute(
            "SELECT params_json, response_json FROM api_cache WHERE endpoint=?",
            (endpoint,),
        ).fetchall()
    days_set = set(days)
    for params_json, resp_json in rows:
        try:
            params = json.loads(params_json)
        except json.JSONDecodeError:
            continue
        inner = params.get("params") if isinstance(params.get("params"), dict) else params
        if not isinstance(inner, dict):
            continue
        p_date = str(inner.get("date") or "")
        # Normalize: cache stores dates as YYYY-MM-DD (with hyphens) most of
        # the time, but YYYYMMDD has been seen historically — accept both.
        if len(p_date) == 8 and p_date.isdigit():
            p_date = f"{p_date[:4]}-{p_date[4:6]}-{p_date[6:]}"
        if p_date not in days_set:
            continue
        p_model = inner.get("model")
        if p_model != model:
            continue
        try:
            data = json.loads(resp_json)
        except json.JSONDecodeError:
            continue
        out[p_date] = data if isinstance(data, list) else (
            data.get("data") if isinstance(data, dict) else []
        )
    return out


def build_mainline_by_date(
    rank_by_date: dict[str, list[dict]],
    days: list[str],
    window: int,
    topk: int,
    min_hits: int,
) -> dict[str, set[str]]:
    """For each `d` in `days`, compute the trailing main-line set from the
    `window` PRIOR days' rank rows (matches backtest.py logic at line 462)."""
    out: dict[str, set[str]] = {}
    for i, d in enumerate(days):
        if i == 0:
            out[d] = set()
            continue
        trailing = [
            rank_by_date.get(t, []) for t in days[max(0, i - window):i]
        ]
        out[d] = compute_mainline(trailing, window=window, topk=topk, min_hits=min_hits)
    return out


def gate_with_mainline(
    mainline_by_date: dict[str, set[str]],
    *,
    require: bool,
    max_open_pct: float = 6.0,
):
    def gate(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= max_open_pct:
            return False
        ml = mainline_by_date.get(sig.date, set())
        if not ml:
            # No mainline yet — fall back to baseline behavior (allow).
            return True
        intersect = bool(sig.blocks() & ml)
        return intersect if require else not intersect
    return gate


def main() -> None:
    universe = load_universe()
    days = trade_days_in_universe(universe)
    print(f"universe: {len(universe)} signals, {len(days)} days")

    # Sample: how many signals carry block info at all?
    with_blocks = sum(1 for s in universe if s.blocks())
    print(f"  signals with block info: {with_blocks}/{len(universe)} ({100*with_blocks/len(universe):.0f}%)")
    if with_blocks == 0:
        print("\n!!! signals have no block info — old backtest output without rules.py block fields. !!!")
        print("    Re-run seed backtest with current code, then retry.")
        return

    # Load cached block_rank with model=0 (FULL — what mainline uses)
    rank_full = load_rank_history(BLOCK_RANK_ENDPOINT, model=0, days=days)
    rank_focus = load_rank_history(BLOCK_RANK_ENDPOINT, model=1, days=days)
    cat_rank = load_rank_history(CATEGORY_RANK_ENDPOINT, model=0, days=days)
    print(f"  cached rank rows (model=0/full): {len(rank_full)}/{len(days)} days")
    print(f"  cached rank rows (model=1/focus): {len(rank_focus)}/{len(days)} days")
    print(f"  cached category-rank rows (model=0): {len(cat_rank)}/{len(days)} days")

    # Baseline
    base_gate = gate_validated_baseline(max_open_pct=6.0)
    bt, _, bv, _ = evaluate(universe, base_gate)
    print(f"\n=== baseline (validated, no mainline filter) ===")
    print(f"  TRAIN active: {bt.fmt()}")
    print(f"  TEST  active: {bv.fmt()}")

    # Grid: (window, topk, min_hits)
    print(f"\n=== mainline grid (FULL rank, model=0): require_main_line=True ===")
    print(f"{'(W, K, hits)':<14} {'TRAIN active':<46} {'TEST active':<46}  Δtr   Δte")
    for window, topk, hits in product([2, 3, 5], [3, 5, 7], [None]):
        ml_by_date = build_mainline_by_date(
            rank_full, days, window, topk, hits if hits is not None else max(1, window)
        )
        gate = gate_with_mainline(ml_by_date, require=True)
        ta, _, va, _ = evaluate(universe, gate)
        actual_hits = hits if hits is not None else max(1, window)
        cfg = f"({window},{topk},{actual_hits})"
        print(f"{cfg:<14} {ta.fmt():<46} {va.fmt():<46}  {ta.avg-bt.avg:+5.2f} {va.avg-bv.avg:+5.2f}")

    # Looser min_hits variants
    print(f"\n=== mainline grid: looser min_hits ===")
    for window, topk, hits in [
        (3, 5, 2),  # 3 days, 5 top, present in 2/3
        (5, 5, 3),  # 5 days, 5 top, present in 3/5
        (5, 7, 3),
        (5, 10, 3),
    ]:
        ml_by_date = build_mainline_by_date(rank_full, days, window, topk, hits)
        gate = gate_with_mainline(ml_by_date, require=True)
        ta, _, va, _ = evaluate(universe, gate)
        cfg = f"({window},{topk},{hits})"
        print(f"{cfg:<14} {ta.fmt():<46} {va.fmt():<46}  {ta.avg-bt.avg:+5.2f} {va.avg-bv.avg:+5.2f}")

    # Inverted: exclude main-line (off-mainline preference per 0413-A)
    print(f"\n=== mainline grid: exclude_main_line (off-mainline preference) ===")
    print(f"{'(W, K, hits)':<14} {'TRAIN active':<46} {'TEST active':<46}  Δtr   Δte")
    for window, topk in [(3, 5), (3, 7), (5, 5), (5, 7), (2, 5)]:
        hits = max(1, window)
        ml_by_date = build_mainline_by_date(rank_full, days, window, topk, hits)
        gate = gate_with_mainline(ml_by_date, require=False)
        ta, _, va, _ = evaluate(universe, gate)
        cfg = f"({window},{topk},{hits})"
        print(f"{cfg:<14} {ta.fmt():<46} {va.fmt():<46}  {ta.avg-bt.avg:+5.2f} {va.avg-bv.avg:+5.2f}")

    # Sanity: how many signals are "in main-line" under default (3,5,3)?
    ml_default = build_mainline_by_date(rank_full, days, 3, 5, 3)
    in_ml = sum(1 for s in universe if s.blocks() & ml_default.get(s.date, set()))
    print(f"\n=== default mainline (3,5,3) coverage ===")
    print(f"  signals in mainline: {in_ml}/{len(universe)} ({100*in_ml/len(universe):.0f}%)")


if __name__ == "__main__":
    main()
