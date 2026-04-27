"""Per-mode multi-day tune (Plan B+ follow-up).

For each strategy mode in v3 baseline active trades, sweep (hold_days,
exit_rule, max_dd_pct) and find each mode's best scoring config. Then
report whether per-mode tuning gives additional lift over the global
5d max_dd 2% (validated_v5 default).

Approach: re-score the same v3 active trade set (signals_*.json from
output/xiaocao_8mo_v3_baseline) under each scoring variant, segment by
mode, compare avg/win/sum.

Output: output/per_mode_multi_day_tune.md
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
from xiaocao.backtest import score_trades  # noqa: E402

DEFAULT_SOURCE = ROOT / "output" / "xiaocao_8mo_v3_baseline"
DEFAULT_OUT_MD = ROOT / "output" / "per_mode_multi_day_tune.md"

# Scoring variants to sweep (entry always = 9:30 open for T+1 compatibility)
VARIANTS = [
    ("1d_baseline", {"hold_days": 1, "exit_rule": "next_close"}),
    ("2d_hold_to_n", {"hold_days": 2, "exit_rule": "hold_to_n"}),
    ("3d_hold_to_n", {"hold_days": 3, "exit_rule": "hold_to_n"}),
    ("5d_hold_to_n", {"hold_days": 5, "exit_rule": "hold_to_n"}),
    ("3d_dd2", {"hold_days": 3, "exit_rule": "max_dd", "max_dd_pct": 2.0}),
    ("3d_dd3", {"hold_days": 3, "exit_rule": "max_dd", "max_dd_pct": 3.0}),
    ("5d_dd2", {"hold_days": 5, "exit_rule": "max_dd", "max_dd_pct": 2.0}),  # v5 default
    ("5d_dd3", {"hold_days": 5, "exit_rule": "max_dd", "max_dd_pct": 3.0}),
    ("5d_dd4", {"hold_days": 5, "exit_rule": "max_dd", "max_dd_pct": 4.0}),
    ("7d_dd2", {"hold_days": 7, "exit_rule": "max_dd", "max_dd_pct": 2.0}),
    ("7d_dd3", {"hold_days": 7, "exit_rule": "max_dd", "max_dd_pct": 3.0}),
    ("10d_dd3", {"hold_days": 10, "exit_rule": "max_dd", "max_dd_pct": 3.0}),
]


def load_signals_by_date(signal_dir: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for sf in sorted(signal_dir.glob("signals_*.json")):
        date = sf.stem.replace("signals_", "")
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out[date] = data
    return out


def load_trade_days(signal_dir: Path) -> list[str]:
    return sorted({sf.stem.replace("signals_", "")
                   for sf in signal_dir.glob("signals_*.json")})


def load_klines_from_cache(cache_path: Path) -> dict[str, dict[str, dict]]:
    """{code: {date: row}} — daily kline, freq=D adj=qfq."""
    from xiaocao.api.cache import iter_cached_responses

    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for data in iter_cached_responses(cache_path, "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            code = str(k.get("code") or "")
            td = str(k.get("tradeDate") or "")[:10]
            if len(td) == 8 and td.isdigit():
                td = f"{td[:4]}-{td[4:6]}-{td[6:]}"
            if code and td:
                out[code][td] = k
    return dict(out)


def stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0, "avg": None, "win": None, "sum": None}
    return {
        "n": len(rets),
        "avg": round(statistics.mean(rets), 3),
        "win": round(sum(1 for r in rets if r > 1) / len(rets) * 100, 1),
        "sum": round(sum(rets), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="backtest output dir (signals_*.json + trades.csv)")
    parser.add_argument("--output", default=str(DEFAULT_OUT_MD),
                        help="markdown report path")
    args = parser.parse_args()

    source_dir = Path(args.source)
    out_md = Path(args.output)
    cache_path = ROOT / "output" / ".cache" / "xiaocao.db"
    if not cache_path.exists():
        sys.exit(f"missing cache {cache_path}")
    if not source_dir.exists():
        sys.exit(f"missing source dir {source_dir}")

    signals_by_date = load_signals_by_date(source_dir)
    trade_days = load_trade_days(source_dir)
    klines = load_klines_from_cache(cache_path)
    print(f"source: {source_dir}")
    print(f"signals dates: {len(signals_by_date)}, trade_days: {len(trade_days)}, klines: {len(klines)}")

    # Run each variant
    variant_to_mode_rets: dict[str, dict[str, list[float]]] = {}
    for label, kwargs in VARIANTS:
        trades, _ = score_trades(signals_by_date, trade_days, klines, **kwargs)
        # Filter to active only
        active = [t for t in trades if (
            (t.get("adaptiveActive") is True) or t.get("adaptiveActive") == ""
            or t.get("adaptiveActive") is None
        )]
        # Group by mode
        by_mode: dict[str, list[float]] = defaultdict(list)
        for t in active:
            mode = t.get("mode") or "_unknown"
            try:
                by_mode[mode].append(float(t["returnPct"]))
            except (ValueError, TypeError):
                continue
        variant_to_mode_rets[label] = dict(by_mode)

    # Get all modes present
    all_modes: set = set()
    for v in variant_to_mode_rets.values():
        all_modes.update(v.keys())
    modes = sorted(all_modes)

    # Render
    L: list[str] = []
    L.append("# Per-mode multi-day exit tune (Plan B follow-up)")
    L.append("")
    L.append(f"- Source: `{source_dir.relative_to(ROOT)}/signals_*.json` re-scored under each variant")
    L.append(f"- Entry uniformly = 9:30 open (T+1 compatible, validated_v3 baseline)")
    L.append(f"- v5 ship default = `5d_dd2` (5d hold + max_dd 2%)")
    L.append("")

    # Global summary
    L.append("## Global (all modes combined)")
    L.append("")
    L.append("| variant | n | avg | win | sum |")
    L.append("|---|---|---|---|---|")
    for label, _ in VARIANTS:
        total: list[float] = []
        for m in modes:
            total.extend(variant_to_mode_rets[label].get(m, []))
        s = stats(total)
        marker = "  ← v5 default" if label == "5d_dd2" else ""
        L.append(f"| {label}{marker} | {s['n']} | {s['avg']}% | {s['win']}% | {s['sum']}% |")
    L.append("")

    # Per-mode best variant
    L.append("## Per-mode best variant (sorted by trade count)")
    L.append("")
    L.append("| mode | n | best variant (by avg) | avg | win | v5(5d_dd2) avg | Δ avg |")
    L.append("|---|---|---|---|---|---|---|")
    mode_rows = []
    for m in modes:
        n = max(len(variant_to_mode_rets[v[0]].get(m, [])) for v in VARIANTS)
        mode_rows.append((m, n))
    mode_rows.sort(key=lambda x: -x[1])

    for m, _ in mode_rows:
        # Find best variant by avg, requiring n>=5 for stability
        best_label = None
        best_avg = float("-inf")
        best_n = 0
        best_win = 0
        for label, _ in VARIANTS:
            rets = variant_to_mode_rets[label].get(m, [])
            if len(rets) < 5:
                continue
            s = stats(rets)
            if s["avg"] is not None and s["avg"] > best_avg:
                best_avg = s["avg"]
                best_label = label
                best_n = s["n"]
                best_win = s["win"]
        v5_rets = variant_to_mode_rets["5d_dd2"].get(m, [])
        v5_s = stats(v5_rets)
        v5_avg = v5_s["avg"]
        delta = (best_avg - v5_avg) if (best_avg is not None and v5_avg is not None and best_label) else None
        L.append(
            f"| {m} | {best_n if best_label else '<5'} | "
            f"{best_label or 'n/a'} | "
            f"{best_avg:+.2f}%" + (f" | {best_win:.1f}%" if best_label else " | n/a") +
            (f" | {v5_avg:+.2f}% | {delta:+.2f}pp |" if delta is not None else " | n/a | n/a |")
        )
    L.append("")

    # Per-mode full matrix
    L.append("## Per-mode full matrix (avg returns by variant)")
    L.append("")
    header = "| mode | " + " | ".join(label for label, _ in VARIANTS) + " |"
    sep = "|---|" + "|".join("---" for _ in VARIANTS) + "|"
    L.append(header)
    L.append(sep)
    for m, _ in mode_rows:
        row = [f"| {m}"]
        for label, _ in VARIANTS:
            rets = variant_to_mode_rets[label].get(m, [])
            if not rets or len(rets) < 3:
                row.append(" – ")
                continue
            avg = statistics.mean(rets)
            row.append(f" {avg:+.2f}% (n={len(rets)})")
        L.append("|".join(row) + " |")
    L.append("")

    L.append("## Decision framework")
    L.append("")
    L.append("- If a mode's best variant is `5d_dd2` → ship v5 default applies")
    L.append("- If best avg differs by ≥ 0.5pp AND n ≥ 8 → consider per-mode override")
    L.append("- If best is hold_to_n variants (no max_dd) → that mode benefits from no trailing stop")
    L.append("- If n < 5 → keep v5 default; insufficient sample for per-mode tune")
    L.append("")

    out_md.write_text("\n".join(L), encoding="utf-8")
    print(f"\nWrote: {out_md}")

    # Console summary
    print("\nGlobal summary across variants:")
    for label, _ in VARIANTS:
        total: list[float] = []
        for m in modes:
            total.extend(variant_to_mode_rets[label].get(m, []))
        s = stats(total)
        marker = "  ← v5 default" if label == "5d_dd2" else ""
        print(f"  {label:<20} n={s['n']:>3} avg={s['avg']:>+6.2f}% win={s['win']}% sum={s['sum']:>+7.1f}%{marker}")


if __name__ == "__main__":
    main()
