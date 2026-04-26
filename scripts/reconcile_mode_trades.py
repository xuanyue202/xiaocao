"""Reconcile mode trade counts (Plan A2) + per-trade context dump (feeds A3).

Question: report 写绿断低吸 17 笔，cache mode_history 33 笔。来源差异是什么？
Answer (after running across all modes):
  - v3_seed trades.csv = raw rule emissions (no adaptive shadow)
  - mode_history       = warmup-shadowed + post-warmup-active 的并集
  - v3_adaptive trades = post-shadow active (excludes warmup + adaptive shadows)
  - report 的 N        = v3_adaptive 在 TRAIN 区间内的子集

This script does two things:
  1. Per-mode reconciliation table (counts across each source × month)
  2. Per-trade jsonl dump including DBR at entry, precondition_pass, scores —
     A3 (per-mode DBR calibration) consumes this jsonl directly

Usage:
  python3 scripts/reconcile_mode_trades.py [--mode 绿断低吸]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache  # noqa: E402
from xiaocao.strategy.state import build_state_index, get_state  # noqa: E402

CACHE_DB = ROOT / "output" / ".cache" / "xiaocao.db"
SEED_DIR = ROOT / "output" / "xiaocao_8mo_v3_seed"          # raw rule (no adaptive)
ADAPTIVE_DIR = ROOT / "output" / "xiaocao_8mo_v3_adaptive"  # post-shadow active
TRAIN_START = "2025-12-01"
TRAIN_END = "2026-03-31"
DBR_THRESHOLD = 0.55  # v3.3 default precondition

# All modes that have ≥ 5 mode_history entries (worth reconciling)
INTERESTING_MODES = [
    "接力低弱转1", "方向内绿盘低吸前3名", "首红断低吸", "绿断低吸",
    "N字低吸", "接力低弱转2", "红断低吸",
]


def load_trades_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_signals_index(signal_dir: Path) -> dict[tuple[str, str, str], dict]:
    """{(date, code, mode): signal_dict} from signals_*.json."""
    out: dict[tuple[str, str, str], dict] = {}
    if not signal_dir.exists():
        return out
    for sf in sorted(signal_dir.glob("signals_*.json")):
        date = sf.stem.replace("signals_", "")
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        for s in data:
            if not isinstance(s, dict):
                continue
            mode = s.get("mode", "")
            code = str(s.get("code", ""))
            if mode and code:
                out[(date, code, mode)] = s
    return out


def load_mode_history() -> list[tuple[str, str, str, float]]:
    """[(mode, date, code, return_pct), ...]."""
    import sqlite3
    out: list[tuple[str, str, str, float]] = []
    with sqlite3.connect(str(CACHE_DB)) as conn:
        for mode, date, code, ret in conn.execute(
            "SELECT mode, trade_date, code, return_pct FROM mode_history"
        ):
            out.append((mode, str(date)[:10], str(code), float(ret)))
    return out


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def reconcile(
    mode: str,
    seed_trades: list[dict],
    adaptive_trades: list[dict],
    mode_history: list[tuple[str, str, str, float]],
) -> dict:
    seed = [t for t in seed_trades if t.get("mode") == mode]
    adaptive = [t for t in adaptive_trades if t.get("mode") == mode]
    mhist = [t for t in mode_history if t[0] == mode]

    by_month_seed = defaultdict(int)
    by_month_adapt = defaultdict(int)
    by_month_mhist = defaultdict(int)
    for t in seed:
        by_month_seed[t["buyDate"][:7]] += 1
    for t in adaptive:
        by_month_adapt[t["buyDate"][:7]] += 1
    for _, d, _, _ in mhist:
        by_month_mhist[d[:7]] += 1

    train_active = sum(1 for t in adaptive if TRAIN_START <= t["buyDate"] <= TRAIN_END)

    return {
        "mode": mode,
        "seed_total": len(seed),
        "adaptive_total": len(adaptive),
        "mode_history_total": len(mhist),
        "train_active": train_active,
        "by_month_seed": dict(by_month_seed),
        "by_month_adaptive": dict(by_month_adapt),
        "by_month_mhist": dict(by_month_mhist),
    }


def per_trade_dump(
    mode: str,
    seed_trades: list[dict],
    adaptive_trades: list[dict],
    state_index: dict,
    seed_signals: dict,
    adaptive_signals: dict,
) -> list[dict]:
    """One row per RAW seed trade. Fields:
      date, code, ret, mode, in_seed=True, in_adaptive=bool,
      open_pct, scores, state axes, dbr_at_entry, precondition_pass.
    A3 input: filter to is_winner / is_loser by ret threshold.
    """
    adaptive_keys = {(t["buyDate"], t["code"]) for t in adaptive_trades if t.get("mode") == mode}
    seed_for_mode = [t for t in seed_trades if t.get("mode") == mode]
    rows: list[dict] = []
    for t in seed_for_mode:
        d, code = t["buyDate"], t["code"]
        sig = seed_signals.get((d, code, mode), {})
        if not sig:
            sig = adaptive_signals.get((d, code, mode), {})
        st = get_state(d, state_index)
        dbr = float(st.duan_ban_recovery)
        ret = _f(t.get("returnPct"))
        rows.append({
            "date": d,
            "code": code,
            "mode": mode,
            "ret": round(ret, 3),
            "in_seed": True,
            "in_adaptive": (d, code) in adaptive_keys,
            "in_train": TRAIN_START <= d <= TRAIN_END,
            "open_pct": _f(t.get("openPctChange")),
            "xcjw": _f(sig.get("xcjw")),
            "jsjl": _f(sig.get("jsjl")),
            "cjs": _f(sig.get("cjs")),
            "jssb": _f(sig.get("jssb")),
            "direction": bool(sig.get("direction", False)),
            "is_main_line": bool(sig.get("is_main_line", False)),
            "is_big_cap": bool(sig.get("is_big_cap", False)),
            "regime": str(t.get("regime") or sig.get("regime") or ""),
            "dbr": round(dbr, 4),
            "precondition_pass": dbr >= DBR_THRESHOLD,
            "state_reward": round(st.reward, 4),
            "state_risk": round(st.risk, 4),
            "state_continuity": round(st.continuity, 4),
        })
    return sorted(rows, key=lambda r: (r["date"], r["code"]))


def render_md(reconciliations: list[dict], target_dump: list[dict], target_mode: str) -> str:
    L: list[str] = []
    L.append("# Mode trades reconciliation (Plan A2 + A3 input)")
    L.append("")
    L.append(f"- Cache: `{CACHE_DB.relative_to(ROOT)}`")
    L.append(f"- Seed dir: `{SEED_DIR.relative_to(ROOT)}`")
    L.append(f"- Adaptive dir: `{ADAPTIVE_DIR.relative_to(ROOT)}`")
    L.append(f"- TRAIN window: {TRAIN_START} → {TRAIN_END}")
    L.append(f"- DBR precondition threshold: ≥ {DBR_THRESHOLD}")
    L.append("")
    L.append("## Cross-mode reconciliation")
    L.append("")
    L.append("| mode | seed (raw) | mode_history | adaptive (post-shadow) | TRAIN active | seed - adaptive |")
    L.append("|---|---|---|---|---|---|")
    for r in reconciliations:
        L.append(
            f"| {r['mode']} | {r['seed_total']} | {r['mode_history_total']} | "
            f"{r['adaptive_total']} | {r['train_active']} | {r['seed_total'] - r['adaptive_total']} |"
        )
    L.append("")

    L.append(f"## {target_mode} per-month decomposition")
    L.append("")
    target_recon = next((r for r in reconciliations if r["mode"] == target_mode), None)
    if target_recon:
        months = sorted(set(target_recon["by_month_seed"]) |
                        set(target_recon["by_month_adaptive"]) |
                        set(target_recon["by_month_mhist"]))
        L.append("| month | seed | mode_history | adaptive |")
        L.append("|---|---|---|---|")
        for m in months:
            L.append(
                f"| {m} | {target_recon['by_month_seed'].get(m, 0)} | "
                f"{target_recon['by_month_mhist'].get(m, 0)} | "
                f"{target_recon['by_month_adaptive'].get(m, 0)} |"
            )
        L.append("")

    L.append(f"## {target_mode} per-trade detail (sorted by date)")
    L.append("")
    L.append("| date | code | ret | open | jssb | xcjw | cjs | dir | main | big | regime | DBR | precond | active |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in target_dump:
        L.append(
            f"| {t['date']} | {t['code']} | {t['ret']:+.2f}% | {t['open_pct']:+.2f}% | "
            f"{t['jssb']:.0f} | {t['xcjw']:.0f} | {t['cjs']:.0f} | "
            f"{'Y' if t['direction'] else '-'} | "
            f"{'Y' if t['is_main_line'] else '-'} | "
            f"{'Y' if t['is_big_cap'] else '-'} | "
            f"{t['regime'][:8]} | {t['dbr']:.3f} | "
            f"{'pass' if t['precondition_pass'] else 'FAIL'} | "
            f"{'Y' if t['in_adaptive'] else '-'} |"
        )
    L.append("")

    # A3 preview: DBR distribution for winners vs losers
    wins = [t for t in target_dump if t["ret"] > 1.0]
    losses = [t for t in target_dump if t["ret"] < -1.0]
    middle = [t for t in target_dump if -1.0 <= t["ret"] <= 1.0]
    L.append(f"## {target_mode} DBR distribution (A3 preview)")
    L.append("")
    L.append(f"- winners (ret > +1%, n={len(wins)}): " +
             (f"DBR median {statistics.median([t['dbr'] for t in wins]):.3f}, "
              f"min {min(t['dbr'] for t in wins):.3f}, "
              f"max {max(t['dbr'] for t in wins):.3f}" if wins else "—"))
    L.append(f"- losers (ret < -1%, n={len(losses)}): " +
             (f"DBR median {statistics.median([t['dbr'] for t in losses]):.3f}, "
              f"min {min(t['dbr'] for t in losses):.3f}, "
              f"max {max(t['dbr'] for t in losses):.3f}" if losses else "—"))
    L.append(f"- middle (-1% .. +1%, n={len(middle)}): " +
             (f"DBR median {statistics.median([t['dbr'] for t in middle]):.3f}" if middle else "—"))
    L.append("")
    pre_pass = sum(1 for t in target_dump if t["precondition_pass"])
    L.append(f"- precondition (DBR ≥ {DBR_THRESHOLD}) pass rate: {pre_pass}/{len(target_dump)} "
             f"= {(pre_pass/len(target_dump)*100 if target_dump else 0):.1f}%")
    if pre_pass == 0:
        L.append("")
        L.append(f"  ⚠ **{target_mode} 100% precondition fail** —— v3.6 实测的根因。"
                 f"per-mode 阈值校准（A3）必须降低这个 mode 的 DBR threshold。")
    L.append("")

    return "\n".join(L)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="绿断低吸",
                        help="target mode for per-trade dump (default 绿断低吸)")
    args = parser.parse_args()

    cache = SQLiteCache(str(CACHE_DB))
    state_index = build_state_index(cache)

    seed_trades = load_trades_csv(SEED_DIR / "trades.csv")
    adaptive_trades = load_trades_csv(ADAPTIVE_DIR / "trades.csv")
    mhist = load_mode_history()
    seed_signals = load_signals_index(SEED_DIR)
    adaptive_signals = load_signals_index(ADAPTIVE_DIR)

    print(f"Loaded: seed={len(seed_trades)} adaptive={len(adaptive_trades)} "
          f"mode_history={len(mhist)} seed_signals={len(seed_signals)} "
          f"adaptive_signals={len(adaptive_signals)}")

    reconciliations = [
        reconcile(m, seed_trades, adaptive_trades, mhist)
        for m in INTERESTING_MODES
    ]

    target_dump = per_trade_dump(
        args.mode, seed_trades, adaptive_trades, state_index, seed_signals, adaptive_signals
    )

    # Per-mode jsonl for A3
    out_dir = ROOT / "output"
    jsonl_path = out_dir / "mode_trades_dump.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for m in INTERESTING_MODES:
            for t in per_trade_dump(m, seed_trades, adaptive_trades, state_index,
                                    seed_signals, adaptive_signals):
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    md_path = out_dir / "reconcile_mode_trades.md"
    md_path.write_text(render_md(reconciliations, target_dump, args.mode), encoding="utf-8")

    print(f"\nReconciliation summary (target={args.mode}):")
    target = next(r for r in reconciliations if r["mode"] == args.mode)
    print(f"  seed (raw): {target['seed_total']}")
    print(f"  mode_history: {target['mode_history_total']}")
    print(f"  adaptive (post-shadow): {target['adaptive_total']}")
    print(f"  TRAIN active: {target['train_active']}  ← report's '17' = this")
    print(f"  per-trade rows: {len(target_dump)}")
    print(f"  DBR ≥ {DBR_THRESHOLD} pass rate: "
          f"{sum(1 for t in target_dump if t['precondition_pass'])}/{len(target_dump)}")
    print(f"\nWrote: {md_path.relative_to(ROOT)}")
    print(f"Wrote: {jsonl_path.relative_to(ROOT)} (A3 input, all 7 modes)")


if __name__ == "__main__":
    main()
