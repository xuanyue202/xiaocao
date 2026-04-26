"""Cross-window comparison: 2025-04→08 vs 2025-12→2026-04 (8mo seed).

Once the 2025-04→08 backtest output exists at output/xiaocao_xwin_v3, this
script:

1. Re-scores both windows under each scoring variant (1d / 3d_dd2 / 5d_dd2 /
   sweep dd 0.5..2.5)
2. Outputs head-to-head matrix
3. Decides: is dd=2% the cross-window winner? Or does dd=0.5% hold up too?

Decision rule:
  - If both windows favor dd=2% → ship v5 confirmed
  - If both windows favor dd=0.5% → upgrade v5 to dd=0.5%
  - If windows DISAGREE on dd optimum → over-fit risk → keep dd=2% as
    conservative default; flag dd=0.5% as period-dependent

Usage:
  python3 scripts/cross_window_compare.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.backtest import score_trades  # noqa: E402

OUT_MD = ROOT / "output" / "cross_window_validation.md"

WINDOWS = {
    "8mo (Sep25-Apr26)": ROOT / "output" / "xiaocao_8mo_v3_baseline",
    "xwin (Apr-Aug 2025)": ROOT / "output" / "xiaocao_xwin_v3",
}

DD_SWEEP = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
HOLD_DAYS_SWEEP = [3, 5]


def load_signals(d: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for sf in sorted(d.glob("signals_*.json")):
        date = sf.stem.replace("signals_", "")
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out[date] = data
    return out


def load_trade_days(d: Path) -> list[str]:
    return sorted({sf.stem.replace("signals_", "") for sf in d.glob("signals_*.json")})


def load_klines() -> dict[str, dict[str, dict]]:
    import sqlite3
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    with sqlite3.connect(str(ROOT / "output" / ".cache" / "xiaocao.db")) as conn:
        rows = conn.execute(
            "SELECT response_json FROM api_cache WHERE endpoint='/stock/date_kline'"
        ).fetchall()
    for (rj,) in rows:
        try:
            data = json.loads(rj)
        except json.JSONDecodeError:
            continue
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
        "avg": round(statistics.mean(rets), 2),
        "win": round(sum(1 for r in rets if r > 1) / len(rets) * 100, 1),
        "sum": round(sum(rets), 1),
    }


def run_variant(signals: dict, trade_days: list, klines: dict,
                hold_days: int, exit_rule: str, max_dd_pct: float) -> dict:
    trades, _ = score_trades(
        signals, trade_days, klines,
        hold_days=hold_days, exit_rule=exit_rule, max_dd_pct=max_dd_pct,
    )
    active = [t for t in trades if (t.get("adaptiveActive") is True)
              or t.get("adaptiveActive") in ("", None)]
    rets = [float(t["returnPct"]) for t in active if t.get("returnPct") is not None]
    return stats(rets)


def main() -> None:
    klines = load_klines()
    print(f"Loaded klines: {len(klines)} stocks")

    available_windows = {label: d for label, d in WINDOWS.items() if d.exists()}
    if len(available_windows) < 2:
        print(f"⚠ only {len(available_windows)} window(s) available: {list(available_windows.keys())}")
        if not available_windows:
            sys.exit("No window data found")

    # Run all variants on each window
    results: dict[str, dict] = {}
    for label, d in available_windows.items():
        signals = load_signals(d)
        trade_days = load_trade_days(d)
        if not signals:
            print(f"  {label}: no signals, skipping")
            continue
        wresults: dict[str, dict] = {}
        # 1d baseline
        wresults["1d"] = run_variant(signals, trade_days, klines, 1, "next_close", 5.0)
        # dd sweep at hold=3 and hold=5
        for hd in HOLD_DAYS_SWEEP:
            for dd in DD_SWEEP:
                wresults[f"{hd}d_dd{dd}"] = run_variant(signals, trade_days, klines,
                                                        hd, "max_dd", dd)
        results[label] = wresults

    # Render
    L: list[str] = []
    L.append("# Cross-window validation — Plan E")
    L.append("")
    L.append("Re-scores both windows from cached signals_*.json under each scoring variant.")
    L.append("")
    for label, wresults in results.items():
        L.append(f"## {label}")
        L.append("")
        L.append("| variant | n | avg | win | sum |")
        L.append("|---|---|---|---|---|")
        for variant, s in wresults.items():
            avg = f"{s['avg']:+.2f}%" if s['avg'] is not None else "—"
            win = f"{s['win']:.1f}%" if s['win'] is not None else "—"
            sm = f"{s['sum']:+.1f}%" if s['sum'] is not None else "—"
            L.append(f"| {variant} | {s['n']} | {avg} | {win} | {sm} |")
        L.append("")

    # Cross-window decision
    if len(results) >= 2:
        L.append("## Cross-window decision")
        L.append("")
        L.append("| variant | " + " | ".join(label for label in results) + " |")
        L.append("|---|" + "|".join("---" for _ in results) + "|")
        all_variants = list(next(iter(results.values())).keys())
        for v in all_variants:
            row = [v]
            for label in results:
                s = results[label].get(v, {})
                row.append(f"{s.get('avg', 0):+.2f}% (n={s.get('n', 0)})" if s.get('avg') is not None else "—")
            L.append("| " + " | ".join(row) + " |")
        L.append("")

        # Find best variant per window
        for label, wresults in results.items():
            best_v = max(wresults.items(), key=lambda x: x[1]['avg'] if x[1]['avg'] is not None else -999)
            L.append(f"- **{label}** best: `{best_v[0]}` (avg {best_v[1]['avg']:+.2f}%)")
        L.append("")
        L.append("### Verdict")
        L.append("")
        bests = []
        for label, wresults in results.items():
            best_v = max(wresults.items(), key=lambda x: x[1]['avg'] if x[1]['avg'] is not None else -999)
            bests.append((label, best_v[0]))
        if len(set(b[1] for b in bests)) == 1:
            L.append(f"- 两个 window 都偏好 `{bests[0][1]}` → 信号稳健，可以 ship 该 variant")
        else:
            L.append("- 两个 window best variant 不一致 — 存在 over-fit 风险")
            for label, best in bests:
                L.append(f"  - {label}: {best}")
            L.append("- 建议：保守取交集 / 用更宽松（dd=2%）作 default，激进的 dd=0.5% 仅作研究")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"\nWrote: {OUT_MD.relative_to(ROOT)}")
    print()
    for label, wresults in results.items():
        best_v = max(wresults.items(), key=lambda x: x[1]['avg'] if x[1]['avg'] is not None else -999)
        print(f"  {label}: best variant = {best_v[0]} (avg {best_v[1]['avg']:+.2f}%, n={best_v[1]['n']})")


if __name__ == "__main__":
    main()
