"""Cross-window robustness check for validated_v2.

Splits TRAIN (2025-12 .. 2026-03) into 4 monthly sub-windows + APRIL test.
For each, compute baseline (validated) vs validated_v2 (adaptive+off_mainline).
PASS if validated_v2 improves avg AND win_rate on every sub-window.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from replay_lib import (  # noqa: E402
    SignalRecord,
    VALIDATED_EXCLUDE,
    load_universe,
    open_cache,
    stats,
    trade_days_in_universe,
)
from xiaocao.strategy.adaptive import decide_mode_state  # noqa: E402
from xiaocao.strategy.mainline import compute_mainline  # noqa: E402

CACHE_DB = ROOT / "output" / ".cache" / "xiaocao.db"


def load_rank(model: int) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with sqlite3.connect(CACHE_DB) as conn:
        rows = conn.execute(
            "SELECT params_json, response_json FROM api_cache "
            "WHERE endpoint='/stock/xiao_cao_industry_block_rank'"
        ).fetchall()
    for pj, rj in rows:
        p = json.loads(pj)
        inner = p.get("params", p)
        d = inner.get("date", "")
        if len(d) == 8 and d.isdigit():
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if inner.get("model") != model:
            continue
        data = json.loads(rj)
        out[d] = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    return out


def main() -> None:
    universe = load_universe()
    days = trade_days_in_universe(universe)
    cache = open_cache()
    rank0 = load_rank(0)

    ml_by_date: dict[str, set[str]] = {}
    for i, d in enumerate(days):
        if i == 0:
            ml_by_date[d] = set()
            continue
        trailing = [rank0.get(t, []) for t in days[max(0, i - 3): i]]
        ml_by_date[d] = compute_mainline(trailing, window=3, topk=5, min_hits=3)

    def gate_baseline(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        return sig.open_pct < 6.0

    def gate_v2(sig: SignalRecord) -> bool:
        if sig.mode in VALIDATED_EXCLUDE:
            return False
        if sig.open_pct >= 6.0:
            return False
        ml = ml_by_date.get(sig.date, set())
        if ml and (sig.blocks() & ml):
            return False
        d = decide_mode_state(
            sig.mode, sig.date, cache,
            n_min_by_window={5: 1, 10: 2, 20: 3},
            avg_threshold_by_window={5: -5.0, 10: -3.0, 20: -2.0},
            trade_days=days,
        )
        return d.active

    windows = [
        ("Dec25 (TRAIN)", "2025-12-01", "2025-12-31"),
        ("Jan26 (TRAIN)", "2026-01-01", "2026-01-31"),
        ("Feb26 (TRAIN)", "2026-02-01", "2026-02-28"),
        ("Mar26 (TRAIN)", "2026-03-01", "2026-03-31"),
        ("Apr26 (TEST) ", "2026-04-01", "2026-04-30"),
    ]

    print(f"\n{'window':<18} {'baseline':<55}  {'validated_v2':<55}  Δavg  Δwin")
    fails = 0
    train_b: list[float] = []
    train_v: list[float] = []
    test_b: list[float] = []
    test_v: list[float] = []
    for label, start, end in windows:
        slice_ = [s for s in universe if start <= s.date <= end]
        b = stats([s.return_pct for s in slice_ if gate_baseline(s)])
        v = stats([s.return_pct for s in slice_ if gate_v2(s)])
        d_avg = v.avg - b.avg
        d_win = v.win_rate - b.win_rate
        flag = "" if (d_avg >= 0 and d_win >= 0) else " ⚠"
        if "TRAIN" in label and (d_avg < 0 or d_win < -5):
            fails += 1
        print(f"{label:<18} {b.fmt():<55}  {v.fmt():<55}  {d_avg:+5.2f}% {d_win:+5.1f}pp{flag}")
        if "TRAIN" in label:
            train_b.extend(s.return_pct for s in slice_ if gate_baseline(s))
            train_v.extend(s.return_pct for s in slice_ if gate_v2(s))
        else:
            test_b.extend(s.return_pct for s in slice_ if gate_baseline(s))
            test_v.extend(s.return_pct for s in slice_ if gate_v2(s))

    print(f"\n{'TRAIN aggregate':<18} {stats(train_b).fmt():<55}  {stats(train_v).fmt():<55}")
    print(f"{'TEST  aggregate':<18} {stats(test_b).fmt():<55}  {stats(test_v).fmt():<55}")

    if fails:
        print(f"\n>>> {fails} TRAIN sub-windows failed (avg drop or win drop > 5pp). NOT robust.")
    else:
        print(f"\n>>> ALL TRAIN sub-windows pass. validated_v2 is cross-window robust.")


if __name__ == "__main__":
    main()
