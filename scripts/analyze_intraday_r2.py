"""Phase C R2 (9:31-9:35 弱转强) backtest using historical minute_line data.

Reads cached /stock/minute_line responses (backfilled by
backfill_intraday_minute.py), applies a simplified R2 9-step SOP filter
against each active trade, and compares the R2-passing subset's P&L to the
baseline.

R2 SOP (from user + 0419 line 554-560 + 0413-A 9:25-9:35 段). MVP version
implemented here uses only fields available from minute_line:

  step 5  (涨幅可控): pct at 9:35 ∈ (-3%, +4%]
                     0~1 最佳, 0~2 可接受, >4 = 已冲高
  step 7  (不冲高):    9:35 close ≥ 9:30-9:35 max_high * 0.985
                     即回撤未超过 1.5% 时算"还在节奏内"
  step W  (弱开倾向): open_pct ∈ [-3%, +1%]
                     "弱转强" 字面意思：要 weak open or flat open

Additional steps from full SOP that need extra data sources:
  step 1, 6  (先机预警): needs realtime selection endpoint (returns empty hist)
  step 2, 3  (一进二/首板属性): from EOD signals.json — not yet joined
  step 4     (排名靠前): needs realtime sort_v2 — not available historically

Output: side-by-side comparison
  - all 73 active trades (baseline v3)
  - R2-passing subset
  - avg / win / sum / per-month
"""
from __future__ import annotations

import csv
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CACHE = ROOT / "output" / ".cache" / "xiaocao.db"
SOURCE_DIR = ROOT / "output" / "xiaocao_8mo_v3_baseline"
OUT_MD = ROOT / "output" / "r2_intraday_analysis.md"


def load_minute_data() -> dict[tuple[str, str], list[dict]]:
    """{(YYYYMMDD, code): list of minute records sorted by time}."""
    out: dict[tuple[str, str], list[dict]] = {}
    with sqlite3.connect(str(CACHE)) as conn:
        rows = conn.execute(
            "SELECT params_json, response_json FROM api_cache WHERE endpoint='/stock/minute_line'"
        ).fetchall()
    for pj, rj in rows:
        try:
            params = json.loads(pj).get("params", {})
            data = json.loads(rj)
        except (json.JSONDecodeError, AttributeError):
            continue
        # Skip entries WITHOUT count — those are early probes that silently
        # returned today's data despite the tradeDate hint.
        if "count" not in params:
            continue
        td = str(params.get("tradeDate") or "")
        code = str(params.get("code") or "")
        if not td or not code or not isinstance(data, list):
            continue
        recs = sorted(
            [r for r in data if isinstance(r, dict) and r.get("tradeTime")],
            key=lambda r: str(r["tradeTime"]),
        )
        # Sanity: response tradeDate should match the requested tradeDate.
        if recs and str(recs[0].get("tradeDate") or "") != td:
            continue  # silently-ignored historical → skip
        out[(td, code)] = recs
    return out


def load_active_trades() -> list[dict]:
    out = []
    with (SOURCE_DIR / "trades.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("adaptiveActive", "").strip().lower() not in ("true", ""):
                continue
            out.append(r)
    return out


def evaluate_r2(records: list[dict]) -> dict:
    """Compute R2 SOP signals from minute records.

    Minute-record schema (per /stock/minute_line w/ count=241, codeType=0):
      tradeDate (YYYYMMDD), tradeTime (HHMM), trade (price at minute),
      pctChange (cum vs preClose, abs), pctChangeRate (cum vs preClose, %),
      vol/amt/totalVal, plus indicator lines (trendLine, mainIn, etc.)

    Note: open/high/low/close fields are typically NULL per minute; only `trade`
    is populated. pctChangeRate at minute t = (trade_t - preClose) / preClose * 100.
    """
    if len(records) < 6:
        return {"valid": False, "reason": f"too few records (n={len(records)})"}

    open_rec = records[0]   # 0930
    rec_935 = records[5]    # 0935 (5 minutes later)

    open_price = float(open_rec.get("trade") or 0)
    open_pct_raw = open_rec.get("pctChangeRate")
    pct_at_935_raw = rec_935.get("pctChangeRate")
    close_935 = float(rec_935.get("trade") or 0)

    if open_price <= 0 or open_pct_raw is None or pct_at_935_raw is None or close_935 <= 0:
        return {"valid": False, "reason": "missing trade or pctChangeRate fields"}

    open_pct = float(open_pct_raw)
    pct_at_935 = float(pct_at_935_raw)

    # Max trade in window 9:30-9:35 (records[0..5])
    window = records[:6]
    window_trades = [float(r.get("trade") or 0) for r in window]
    max_window = max(window_trades) if window_trades else close_935
    drawdown_from_peak = (max_window - close_935) / max_window * 100 if max_window > 0 else 0

    # SOP checks
    # Weak/flat open: open_pct ∈ [-3, +1]
    weak_open_ok = -3.0 <= open_pct <= 1.0
    # Pct controlled: 9:35 cum pct ∈ (-3, +4]
    pct_controlled = -3.0 < pct_at_935 <= 4.0
    # Pct ideal range (0-2%) for max alignment with SOP
    pct_ideal = -1.0 <= pct_at_935 <= 2.0
    # Not at peak: drawdown ≤ 1.5%
    not_at_peak = drawdown_from_peak <= 1.5

    r2_pass = weak_open_ok and pct_controlled and not_at_peak
    r2_pass_strict = weak_open_ok and pct_ideal and not_at_peak

    return {
        "valid": True,
        "open_pct": round(open_pct, 2),
        "pct_935": round(pct_at_935, 2),
        "max_window": round(max_window, 2),
        "drawdown_from_peak": round(drawdown_from_peak, 2),
        "weak_open_ok": weak_open_ok,
        "pct_controlled": pct_controlled,
        "pct_ideal": pct_ideal,
        "not_at_peak": not_at_peak,
        "r2_pass": r2_pass,
        "r2_pass_strict": r2_pass_strict,
    }


def stats(rows: list[float]) -> str:
    if not rows:
        return "n=0"
    n = len(rows)
    avg = statistics.mean(rows)
    win = sum(1 for r in rows if r > 1) / n * 100
    return f"n={n} avg={avg:+.2f}% win={win:.1f}% sum={sum(rows):+.1f}%"


def main() -> None:
    minute_data = load_minute_data()
    print(f"Loaded {len(minute_data)} cached (date, code) minute datasets")

    trades = load_active_trades()
    print(f"Active trades: {len(trades)}")

    enriched: list[dict] = []
    missing = 0
    invalid = 0
    for t in trades:
        td = t["buyDate"].replace("-", "")
        code = t["code"]
        recs = minute_data.get((td, code))
        if recs is None:
            missing += 1
            continue
        r2 = evaluate_r2(recs)
        if not r2.get("valid"):
            invalid += 1
            continue
        try:
            ret = float(t["returnPct"])
        except (TypeError, ValueError):
            continue
        enriched.append({
            "buyDate": t["buyDate"], "code": code, "mode": t["mode"],
            "ret": ret, **r2,
        })

    print(f"Enriched: {len(enriched)}, missing minute data: {missing}, invalid: {invalid}\n")

    all_rets = [e["ret"] for e in enriched]
    pass_rets = [e["ret"] for e in enriched if e["r2_pass"]]
    pass_strict_rets = [e["ret"] for e in enriched if e["r2_pass_strict"]]
    fail_rets = [e["ret"] for e in enriched if not e["r2_pass"]]

    print("=" * 70)
    print("R2 9-step SOP filter — selection comparison")
    print("=" * 70)
    print(f"Baseline (all active):             {stats(all_rets)}")
    print(f"R2 PASS (weak_open + pct + peak):  {stats(pass_rets)}")
    print(f"R2 PASS strict (pct ∈ [-1,+2]):    {stats(pass_strict_rets)}")
    print(f"R2 FAIL (would skip):              {stats(fail_rets)}")
    print()

    # Per-axis breakdown to see which step contributes most
    print("Single-axis filters (each independent):")
    for axis in ("weak_open_ok", "pct_controlled", "pct_ideal", "not_at_peak"):
        kept = [e["ret"] for e in enriched if e[axis]]
        skipped = [e["ret"] for e in enriched if not e[axis]]
        print(f"  {axis}:")
        print(f"    KEPT (axis ok):     {stats(kept)}")
        print(f"    SKIPPED (axis bad): {stats(skipped)}")
    print()

    # Per-month
    print("R2 PASS per-month:")
    by_m: dict[str, list[float]] = defaultdict(list)
    by_m_pass: dict[str, list[float]] = defaultdict(list)
    for e in enriched:
        m = e["buyDate"][:7]
        by_m[m].append(e["ret"])
        if e["r2_pass"]:
            by_m_pass[m].append(e["ret"])
    for m in sorted(by_m):
        b = stats(by_m[m]); r = stats(by_m_pass[m]) if by_m_pass.get(m) else "n=0"
        print(f"  {m}  baseline: {b}")
        print(f"          R2 PASS: {r}")
    print()

    # Markdown report
    L: list[str] = []
    L.append("# R2 9:31-9:35 弱转强 SOP — 历史 backtest (Plan C2 MVP)")
    L.append("")
    L.append(f"- Source: `{SOURCE_DIR.relative_to(ROOT)}/trades.csv`")
    L.append(f"- Active trades enriched: {len(enriched)} / {len(trades)}")
    L.append("- R2 SOP rules (MVP, only minute_line-derivable):")
    L.append("  - weak_open: open_pct ∈ [-3%, +1%]")
    L.append("  - pct_controlled: 9:35 cum pct ∈ (-3%, +4%]")
    L.append("  - pct_ideal (strict): 9:35 cum pct ∈ [-1%, +2%]")
    L.append("  - not_at_peak: drawdown from 9:30-9:35 max ≤ 1.5%")
    L.append("")
    L.append("## Selection comparison")
    L.append("")
    L.append("| variant | n | avg | win | sum |")
    L.append("|---|---|---|---|---|")
    for label, vals in [
        ("baseline (all 73 active)", all_rets),
        ("R2 PASS (3-axis combo)", pass_rets),
        ("R2 PASS strict (pct ∈ [-1,+2])", pass_strict_rets),
        ("R2 FAIL (would skip)", fail_rets),
    ]:
        if vals:
            L.append(f"| {label} | {len(vals)} | {statistics.mean(vals):+.2f}% | "
                     f"{sum(1 for v in vals if v>1)/len(vals)*100:.1f}% | "
                     f"{sum(vals):+.1f}% |")
        else:
            L.append(f"| {label} | 0 | – | – | – |")
    L.append("")
    L.append("## Per-axis ablation")
    L.append("")
    L.append("| axis | kept_n | kept_avg | kept_win | skipped_n | skipped_avg |")
    L.append("|---|---|---|---|---|---|")
    for axis in ("weak_open_ok", "pct_controlled", "pct_ideal", "not_at_peak"):
        kept = [e["ret"] for e in enriched if e[axis]]
        skipped = [e["ret"] for e in enriched if not e[axis]]
        ka = statistics.mean(kept) if kept else 0
        kw = sum(1 for v in kept if v > 1) / len(kept) * 100 if kept else 0
        sa = statistics.mean(skipped) if skipped else 0
        L.append(f"| {axis} | {len(kept)} | {ka:+.2f}% | {kw:.1f}% | "
                 f"{len(skipped)} | {sa:+.2f}% |")
    L.append("")
    L.append("## Per-trade detail (sorted by ret)")
    L.append("")
    L.append("| date | code | mode | open_pct | pct_935 | dd | pass | strict | ret |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for e in sorted(enriched, key=lambda x: -x["ret"]):
        L.append(
            f"| {e['buyDate']} | {e['code']} | {e['mode']} | "
            f"{e['open_pct']:+.2f}% | {e['pct_935']:+.2f}% | "
            f"{e['drawdown_from_peak']:.2f}% | "
            f"{'Y' if e['r2_pass'] else '-'} | "
            f"{'Y' if e['r2_pass_strict'] else '-'} | "
            f"{e['ret']:+.2f}% |"
        )

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote: {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
