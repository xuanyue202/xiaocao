"""Per-mode DBR threshold calibration (Plan A3, depends on A2 jsonl dump).

Input: output/mode_trades_dump.jsonl (produced by reconcile_mode_trades.py).
Each row has dbr (state.duan_ban_recovery at entry) + ret (returnPct).

For each mode, classify trades:
  WIN  = ret >  +1%
  LOSS = ret <  -1%
  MID  = -1% ≤ ret ≤ +1%   (treated as noise)

Then compute (DBR_median_win, DBR_median_loss, DBR_p25_win, DBR_p75_loss).

Decision tree per mode:
  Case A — well-separated, winners higher DBR (DBR predictive)
    median_win > median_loss + 0.10
    → threshold = max(p25_win, p75_loss); ≥ threshold = pass
  Case B — well-separated, losers higher DBR (DBR anti-predictive)
    median_loss > median_win + 0.10
    → invert: ≤ threshold = pass; threshold = min(p75_win, p25_loss)
    OR: drop DBR precondition for this mode
  Case C — overlap (|delta| ≤ 0.10) → DBR not useful as precondition
    → drop DBR precondition; let adaptive modulation handle it

Output:
  output/calibrate_dbr_per_mode.md (per-mode table + decision per mode)
  output/per_mode_dbr_thresholds.json (mode → {threshold, direction, action})
    where action ∈ {"keep_ge", "keep_le", "drop"}

A4 / A8 will plug per_mode_dbr_thresholds.json into MODE_PROFILE precondition field.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

INPUT_JSONL = ROOT / "output" / "mode_trades_dump.jsonl"
OUTPUT_MD = ROOT / "output" / "calibrate_dbr_per_mode.md"
OUTPUT_JSON = ROOT / "output" / "per_mode_dbr_thresholds.json"

# Min sample size for a mode to even attempt per-mode calibration
MIN_TOTAL = 10
MIN_PER_SIDE = 5  # need ≥ 5 winners AND ≥ 5 losers
SEPARATION = 0.10  # |median_win - median_loss| > this → "well-separated"


def load_dump(path: Path) -> dict[str, list[dict]]:
    by_mode: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            mode = d.get("mode")
            if mode:
                by_mode[mode].append(d)
    return dict(by_mode)


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def calibrate(mode: str, trades: list[dict]) -> dict:
    n_total = len(trades)
    if n_total < MIN_TOTAL:
        return {
            "mode": mode,
            "n_total": n_total,
            "action": "skip",
            "reason": f"sample n={n_total} < {MIN_TOTAL}",
        }

    wins = [t for t in trades if t["ret"] > 1.0]
    losses = [t for t in trades if t["ret"] < -1.0]
    middle = [t for t in trades if -1.0 <= t["ret"] <= 1.0]

    if len(wins) < MIN_PER_SIDE or len(losses) < MIN_PER_SIDE:
        return {
            "mode": mode,
            "n_total": n_total,
            "n_wins": len(wins),
            "n_losses": len(losses),
            "action": "skip",
            "reason": f"per-side n insufficient (wins={len(wins)}, losses={len(losses)})",
        }

    win_dbrs = [t["dbr"] for t in wins]
    loss_dbrs = [t["dbr"] for t in losses]
    mid_dbrs = [t["dbr"] for t in middle]

    med_w = statistics.median(win_dbrs)
    med_l = statistics.median(loss_dbrs)
    p25_w = quantile(win_dbrs, 0.25)
    p75_w = quantile(win_dbrs, 0.75)
    p25_l = quantile(loss_dbrs, 0.25)
    p75_l = quantile(loss_dbrs, 0.75)

    delta = med_w - med_l

    if abs(delta) <= SEPARATION:
        # Case C: overlap
        action = "drop"
        threshold = None
        reason = (
            f"DBR distributions overlap: median_win={med_w:.3f}, "
            f"median_loss={med_l:.3f}, |Δ|={abs(delta):.3f} ≤ {SEPARATION}. "
            "DBR not predictive for this mode → drop precondition; "
            "let adaptive fitness modulation handle it."
        )
    elif delta > SEPARATION:
        # Case A: winners higher DBR (positive predictive)
        action = "keep_ge"
        # Threshold catches most winners + excludes most losers.
        # Use max(p25_win, p75_loss) so we keep ≥ 75% winners and exclude ≥ 75% losers.
        threshold = round(max(p25_w, p75_l), 3)
        kept_win = sum(1 for v in win_dbrs if v >= threshold)
        kept_loss = sum(1 for v in loss_dbrs if v >= threshold)
        reason = (
            f"DBR positively predictive: median_win={med_w:.3f} > "
            f"median_loss={med_l:.3f} (Δ={delta:+.3f}). "
            f"threshold {threshold} keeps {kept_win}/{len(wins)} winners "
            f"and {kept_loss}/{len(losses)} losers."
        )
    else:
        # Case B: losers higher DBR (anti-predictive)
        action = "keep_le"
        threshold = round(min(p75_w, p25_l), 3)
        kept_win = sum(1 for v in win_dbrs if v <= threshold)
        kept_loss = sum(1 for v in loss_dbrs if v <= threshold)
        # If even Case B with anti-threshold doesn't help, fall back to drop
        if kept_win < 0.5 * len(wins):
            action = "drop"
            threshold = None
            reason = (
                f"DBR anti-predictive (median_loss={med_l:.3f} > "
                f"median_win={med_w:.3f}, Δ={delta:+.3f}) but inverted threshold "
                f"({threshold}) only keeps {kept_win}/{len(wins)} winners. "
                "Better to drop DBR precondition entirely."
            )
        else:
            reason = (
                f"DBR anti-predictive: median_loss={med_l:.3f} > "
                f"median_win={med_w:.3f} (Δ={delta:+.3f}). "
                f"Inverted threshold ≤ {threshold} keeps "
                f"{kept_win}/{len(wins)} winners and {kept_loss}/{len(losses)} losers."
            )

    return {
        "mode": mode,
        "n_total": n_total,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_mid": len(middle),
        "win_dbr": {
            "median": round(med_w, 4),
            "p25": round(p25_w, 4),
            "p75": round(p75_w, 4),
            "min": round(min(win_dbrs), 4),
            "max": round(max(win_dbrs), 4),
        },
        "loss_dbr": {
            "median": round(med_l, 4),
            "p25": round(p25_l, 4),
            "p75": round(p75_l, 4),
            "min": round(min(loss_dbrs), 4),
            "max": round(max(loss_dbrs), 4),
        },
        "mid_dbr": {
            "median": round(statistics.median(mid_dbrs), 4) if mid_dbrs else None,
        },
        "delta_med": round(delta, 4),
        "action": action,
        "threshold": threshold,
        "reason": reason,
    }


def render_md(results: list[dict]) -> str:
    L: list[str] = []
    L.append("# Per-mode DBR threshold calibration (Plan A3)")
    L.append("")
    L.append(f"- Input: `{INPUT_JSONL.relative_to(ROOT)}`")
    L.append(f"- WIN ret > +1% / LOSS ret < -1% / MID -1% ≤ ret ≤ +1%")
    L.append(f"- Min total {MIN_TOTAL} trades; min per-side {MIN_PER_SIDE}; "
             f"separation threshold {SEPARATION}")
    L.append("")
    L.append("## Per-mode results")
    L.append("")
    L.append("| mode | n | wins | losses | win-DBR med | loss-DBR med | Δ | action | threshold |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        if r["action"] == "skip":
            L.append(f"| {r['mode']} | {r['n_total']} | – | – | – | – | – | "
                     f"**skip** | – |")
        else:
            L.append(
                f"| {r['mode']} | {r['n_total']} | {r['n_wins']} | {r['n_losses']} | "
                f"{r['win_dbr']['median']} | {r['loss_dbr']['median']} | "
                f"{r['delta_med']:+.3f} | **{r['action']}** | "
                f"{'–' if r['threshold'] is None else r['threshold']} |"
            )
    L.append("")
    L.append("## Decision per mode")
    L.append("")
    for r in results:
        L.append(f"### {r['mode']} (n={r['n_total']})")
        if r["action"] == "skip":
            L.append(f"- **skip**: {r['reason']}")
        else:
            wd = r["win_dbr"]; ld = r["loss_dbr"]
            L.append(f"- WIN  (n={r['n_wins']}): DBR median={wd['median']}, "
                     f"p25={wd['p25']}, p75={wd['p75']}, range [{wd['min']}, {wd['max']}]")
            L.append(f"- LOSS (n={r['n_losses']}): DBR median={ld['median']}, "
                     f"p25={ld['p25']}, p75={ld['p75']}, range [{ld['min']}, {ld['max']}]")
            if r["mid_dbr"]["median"] is not None:
                L.append(f"- MID  (n={r['n_mid']}): DBR median={r['mid_dbr']['median']}")
            L.append(f"- **action**: `{r['action']}`"
                     + (f", **threshold**: {r['threshold']}" if r["threshold"] is not None else ""))
            L.append(f"- **reasoning**: {r['reason']}")
        L.append("")

    L.append("## How to plug into MODE_PROFILE")
    L.append("")
    L.append("- `keep_ge` thresholds: replace current `precondition='duan_ban_recovery >= 0.55'` "
             "with mode-specific `>= threshold`")
    L.append("- `keep_le` thresholds: introduce inverted precondition `duan_ban_recovery <= threshold`")
    L.append("- `drop`: remove precondition entirely; the mode relies purely on adaptive "
             "fitness modulation (no hard short-circuit)")
    L.append("- modes not listed (sample too small): keep current global default but flag as "
             "「待校准」in the next 2-3 month data accumulation")
    L.append("")

    return "\n".join(L)


def main() -> None:
    if not INPUT_JSONL.exists():
        sys.exit(f"Missing {INPUT_JSONL}. Run scripts/reconcile_mode_trades.py first.")

    by_mode = load_dump(INPUT_JSONL)
    print(f"Loaded {sum(len(v) for v in by_mode.values())} trades across {len(by_mode)} modes")

    results = [calibrate(mode, trades) for mode, trades in
               sorted(by_mode.items(), key=lambda x: -len(x[1]))]

    OUTPUT_MD.write_text(render_md(results), encoding="utf-8")

    threshold_cfg = {
        r["mode"]: {
            "action": r["action"],
            "threshold": r.get("threshold"),
            "n_total": r["n_total"],
            "delta_med": r.get("delta_med"),
        }
        for r in results
    }
    OUTPUT_JSON.write_text(
        json.dumps(threshold_cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\nPer-mode decisions:")
    for r in results:
        flag = (f"action={r['action']:<8s} thr={r.get('threshold')}" if r["action"] != "skip"
                else "action=skip")
        print(f"  {r['mode']:<24s} n={r['n_total']:>3d} {flag}")
    print(f"\nWrote: {OUTPUT_MD.relative_to(ROOT)}")
    print(f"Wrote: {OUTPUT_JSON.relative_to(ROOT)}  (A8 will plug into MODE_PROFILE)")


if __name__ == "__main__":
    main()
