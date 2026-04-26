"""Bench direction_sort_key candidates against validated_v2 baseline.

Each candidate triggers fresh /stock/sort_v2 calls with a new sort_id (and
potentially fresh /stock/xiao_cao_index_v2 calls for newly-selected codes).
The cache absorbs everything; future replays are free.

Strategy: run 3 backtests per candidate (Dec-Jan, Feb-Mar, Apr) — same
windows used by the validated_v2 cross-window check — then compare per-window
avg / win / n. PASS = beat baseline on TRAIN (Dec-Jan + Feb-Mar both) and
non-collapse on TEST (Apr).

Usage: python3 scripts/tune_sort_keys.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CANDIDATES = [
    # (label, --direction-sort-key value, --pool-sort-key value)
    ("baseline (dir=47, pool=38)",   "directionCjs",     "xiaocaoXCJW"),
    ("pool=xcjwV2 (dir=47, p=48)",   "directionCjs",     "xcjwV2"),
    ("pool=xiaocaoCJS (dir=47, p=40)", "directionCjs",   "xiaocaoCJS"),
    ("dir+pool=V2 (dir=54, p=48)",   "directionCjsV2",   "xcjwV2"),
]

WINDOWS = [
    ("Dec25-Jan26", "2025-12-01", "2026-01-31"),
    ("Feb-Mar26", "2026-02-01", "2026-03-31"),
    ("Apr26 (TEST)", "2026-04-01", "2026-04-30"),
]


def run_one(label: str, dir_sort_key: str, pool_sort_key: str, start: str, end: str) -> dict:
    out_dir = ROOT / "output" / "tune_sort_keys" / f"{dir_sort_key}_{pool_sort_key}_{start}_{end}"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Bypass --profile because preset.direction_sort_key would override the flag
    # (see runner.py:111). Inline validated_v2's other components instead.
    cmd = [
        "xiaocao", "backtest", "run",
        "--start", start, "--end", end,
        "--direction-sort-key", dir_sort_key,
        "--pool-sort-key", pool_sort_key,
        "--sort-id", "40",
        "--exclude-modes", "接力低弱转2,方向内绿盘低吸前3名",
        "--exclude-main-line",
        "--workers", "4",
        "--no-adaptive-modes",
        "--quiet",
        "--output", str(out_dir),
    ]
    print(f"  → {label} on {start}..{end}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    FAIL: {r.stderr[-500:]}")
        return {}
    summary_path = out_dir / "summary.json"
    if not summary_path.exists():
        print(f"    FAIL: no summary.json")
        return {}
    return json.loads(summary_path.read_text(encoding="utf-8"))


def main() -> None:
    print(f"Benching {len(CANDIDATES)} (direction, pool) pairs × {len(WINDOWS)} windows = {len(CANDIDATES)*len(WINDOWS)} runs")
    rows = []
    for label, dir_sort_key, pool_sort_key in CANDIDATES:
        for win_label, start, end in WINDOWS:
            summary = run_one(label, dir_sort_key, pool_sort_key, start, end)
            sig = summary.get("overall_signal_level") or {}
            active = summary.get("active_signal_level") or {}
            level = active if active.get("count") else sig
            rows.append({
                "candidate": label,
                "window": win_label,
                "n": level.get("count", 0),
                "avg": level.get("avg", 0),
                "win": level.get("win_rate", 0),
                "median": level.get("median", 0),
                "sum": level.get("sum", 0),
            })

    print(f"\n{'candidate':<28} {'window':<14} {'n':>4} {'avg':>9} {'win':>7} {'med':>9} {'sum':>9}")
    for r in rows:
        print(f"{r['candidate']:<28} {r['window']:<14} {r['n']:>4} {r['avg']:>+8.2f}% {r['win']:>6.1f}% {r['median']:>+8.2f}% {r['sum']:>+8.1f}%")

    # Build per-window comparison vs baseline
    by_label = {}
    for r in rows:
        by_label.setdefault(r["candidate"], {})[r["window"]] = r
    baseline_label = CANDIDATES[0][0]
    print(f"\n=== Δ vs baseline ({baseline_label}) ===")
    print(f"{'candidate':<28} {'window':<14} {'Δ avg':>8} {'Δ win':>8} {'Δ n':>5}")
    for label, _dir, _pool in CANDIDATES[1:]:
        for win_label, _, _ in WINDOWS:
            r = by_label.get(label, {}).get(win_label, {})
            b = by_label.get(baseline_label, {}).get(win_label, {})
            if not r or not b:
                continue
            print(
                f"{label:<28} {win_label:<14} "
                f"{r['avg'] - b['avg']:>+7.2f}% "
                f"{r['win'] - b['win']:>+7.1f}pp "
                f"{r['n'] - b['n']:>+5d}"
            )


if __name__ == "__main__":
    main()
