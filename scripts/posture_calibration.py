"""Judgment-layer calibration — is the posture call (道-layer) actually right?

The session proved the edge lives in the COARSE posture judgment (赚钱效应/regime →
play or sit out), not mechanical timing. This loop compounds that layer honestly:
score each dated posture call against the realized forward market outcome, build a
calibration ledger, and surface which posture types are systematically wrong (=
distillation targets for the next transcript pass).

A posture call = {date, posture, action} where action ∈ {aggressive, defensive,
neutral}. Scoring (the call is a PREDICTION, forward window is genuinely future):
  aggressive  right if forward market return > 0   (participation rewarded)
  defensive   right if forward market return ≤ 0   (sit-out avoided loss)
  neutral     excluded from hit-rate (no directional claim)

Forward outcome = mean big-cap market return over the next `horizon` trading days
(cross-cycle date_kline, 2021-2026). Regime features use data_guard.trailing so
they are lookahead-safe BY CONSTRUCTION.

Modes:
  --backfill-proxy   bootstrap: score the DETERMINISTIC proxy-regime posture over
                     history (the baseline the discretionary judgment must beat)
  --record DATE POSTURE ACTION   append a forward posture call (morning automation)
  --score            score calls whose forward window has closed + print summary

Cache-only. The ledgers live under output/live/ (runtime, gitignored).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402
from xiaocao.research import data_guard as dg  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
LIVE = ROOT / "output" / "live"
CALLS = LIVE / "posture_calls.jsonl"
SCORED = LIVE / "posture_calibration.jsonl"

ACTION = {  # posture/regime label -> directional action
    "bear": "defensive", "divergence": "defensive", "主跌": "defensive", "空仓": "defensive",
    "trend_strong": "aggressive", "trend_continuing": "aggressive", "进攻": "aggressive", "持有": "aggressive",
    "neutral": "neutral", "recovery": "neutral", "观望": "neutral",
}


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0


def market_panel():
    best = {}
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            code = data[0].get("code")
            if code and (code not in best or len(data) > len(best[code])):
                best[code] = data
    by_date = defaultdict(list)
    for code, bars in best.items():
        ds = [b.get("tradeDate") for b in bars if isinstance(b, dict) and b.get("tradeDate")]
        if not ds or min(ds) >= "2023-01-01":
            continue
        for b in bars:
            td, pct = b.get("tradeDate"), b.get("pctChangeRate")
            if td and isinstance(pct, (int, float)):
                by_date[td].append(float(pct))
    days = sorted(d for d in by_date if len(by_date[d]) >= 100)
    daily = {d: _mean(by_date[d]) for d in days}
    return days, daily


def forward_return(days, daily, date, horizon):
    """Mean market return over the `horizon` days AFTER `date` (genuinely future)."""
    if date not in days:
        # find first day >= date
        later = [d for d in days if d > date]
        if not later:
            return None
        i = days.index(later[0]) - 1
    else:
        i = days.index(date)
    fwd = [daily[days[j]] for j in range(i + 1, min(i + 1 + horizon, len(days)))]
    return _mean(fwd) if len(fwd) == horizon else None


def score_call(action, fwd_ret):
    if fwd_ret is None or action == "neutral":
        return None
    if action == "aggressive":
        return fwd_ret > 0
    return fwd_ret <= 0  # defensive


def summarize(scored):
    by_action = defaultdict(lambda: [0, 0])
    for s in scored:
        if s.get("right") is None:
            continue
        by_action[s["action"]][0] += 1 if s["right"] else 0
        by_action[s["action"]][1] += 1
    print(f"\n  posture calibration ({sum(v[1] for v in by_action.values())} directional calls):")
    for act in ("aggressive", "defensive"):
        hit, n = by_action[act]
        if n:
            print(f"    {act:<10} hit-rate {hit}/{n} = {100*hit/n:.0f}%  "
                  f"{'(systematically wrong → distill)' if hit/n < 0.45 and n >= 10 else ''}")
    tot_hit = sum(v[0] for v in by_action.values())
    tot_n = sum(v[1] for v in by_action.values())
    if tot_n:
        print(f"    OVERALL    {tot_hit}/{tot_n} = {100*tot_hit/tot_n:.0f}%  "
              f"(>55% = the judgment call adds value; ~50% = no better than coin)")


def backfill_proxy(horizon, W):
    """Baseline: score the deterministic trailing-breadth regime posture over history.
    Uses data_guard.trailing => lookahead-safe (no day-i leakage)."""
    days, daily = market_panel()
    series = [daily[d] for d in days]
    scored = []
    for i in range(W, len(days) - horizon):
        trail = dg.trailing(series, i, W)             # lookahead-safe: excludes day i
        m = _mean(trail)
        regime = "bear" if m < -0.3 else "divergence" if m < 0 else "trend_strong" if m > 0.3 else "neutral"
        action = ACTION[regime]
        fwd = forward_return(days, daily, days[i], horizon)
        right = score_call(action, fwd)
        scored.append({"date": days[i], "posture": regime, "action": action,
                       "fwd_ret": fwd, "right": right, "source": "proxy_regime"})
    print(f"backfill-proxy (deterministic regime baseline, H={horizon}, W={W}): "
          f"{len(scored)} calls over {days[W]}..{days[-horizon-1]}")
    summarize(scored)
    print("\n  ^ this is the BASELINE the discretionary judgment layer must beat. "
          "A ~50% deterministic baseline is expected (regime doesn't predict forward — "
          "that's why timing must be coarse JUDGMENT, not a mechanical param).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill-proxy", action="store_true")
    ap.add_argument("--record", nargs=3, metavar=("DATE", "POSTURE", "ACTION"))
    ap.add_argument("--record-current", action="store_true",
                    help="append today's standing posture from posture_current.json (morning automation)")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--window", type=int, default=20)
    a = ap.parse_args()

    if a.backfill_proxy:
        backfill_proxy(a.horizon, a.window)
        return
    if a.record_current:
        import datetime
        pc = ROOT / "reference" / "experience" / "posture_current.json"
        if not pc.exists():
            print("no posture_current.json"); return
        cur = json.loads(pc.read_text(encoding="utf-8"))
        regime = cur.get("regime", "neutral")
        today = datetime.date.today().isoformat()
        LIVE.mkdir(parents=True, exist_ok=True)
        existing = {json.loads(l).get("date") for l in CALLS.read_text().splitlines()} if CALLS.exists() else set()
        if today in existing:
            print(f"posture call for {today} already recorded"); return
        with CALLS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"date": today, "posture": regime, "action": ACTION.get(regime, "neutral"),
                                 "as_of": cur.get("as_of"), "source": "posture_current"}, ensure_ascii=False) + "\n")
        print(f"recorded standing posture call: {today} {regime} ({ACTION.get(regime,'neutral')})")
        return
    if a.record:
        LIVE.mkdir(parents=True, exist_ok=True)
        date, posture, action = a.record
        with CALLS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"date": date, "posture": posture,
                                 "action": action or ACTION.get(posture, "neutral")}, ensure_ascii=False) + "\n")
        print(f"recorded posture call: {date} {posture} ({action})")
        return
    if a.score:
        if not CALLS.exists():
            print("no posture_calls.jsonl yet — morning automation records calls; this scores them once "
                  "their forward window closes.")
            return
        days, daily = market_panel()
        already = set()
        if SCORED.exists():
            already = {json.loads(l)["date"] for l in SCORED.read_text().splitlines() if l.strip()}
        calls = [json.loads(l) for l in CALLS.read_text().splitlines() if l.strip()]
        newly = []
        for c in calls:
            if c["date"] in already:
                continue
            fwd = forward_return(days, daily, c["date"], a.horizon)
            if fwd is None:
                continue  # forward window not closed yet
            c["fwd_ret"] = fwd
            c["right"] = score_call(c["action"], fwd)
            newly.append(c)
        if newly:
            LIVE.mkdir(parents=True, exist_ok=True)
            with SCORED.open("a", encoding="utf-8") as fh:
                for c in newly:
                    fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        all_scored = ([json.loads(l) for l in SCORED.read_text().splitlines() if l.strip()]
                      if SCORED.exists() else [])
        print(f"posture scoring: +{len(newly)} newly closed calls; {len(all_scored)} total scored")
        summarize(all_scored)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
