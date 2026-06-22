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
from xiaocao.research import calibration_distill as cd  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
LIVE = ROOT / "output" / "live"
CALLS = LIVE / "posture_calls.jsonl"
SCORED = LIVE / "posture_calibration.jsonl"
CANDIDATES = LIVE / "calibration_candidates.jsonl"  # distill bridge -> human gate

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


def decompose_defensive(horizon, W):
    """The distillation step: WHEN is the defensive posture actually right?

    The baseline flagged defensive (trailing breadth bad) as 42% — systematically
    wrong. Decompose it by SEVERITY (how bad) and DURATION (how long it's been
    bad), lookahead-safe, to find the coarse sub-condition (if any) where sitting
    out genuinely pays. This refines the JUDGMENT prior — make it coarser/rarer —
    not a mechanical param.
    """
    days, daily = market_panel()
    series = [daily[d] for d in days]
    sev_buckets = {"mild [-0.8,-0.3)": [], "moderate [-1.5,-0.8)": [], "severe (<-1.5)": []}
    dur_buckets = {"1-3 d": [], "4-10 d": [], ">10 d": []}
    run = 0
    for i in range(W, len(days) - horizon):
        m = _mean(dg.trailing(series, i, W))            # lookahead-safe
        defensive = m < -0.3
        run = run + 1 if defensive else 0
        if not defensive:
            continue
        fwd = forward_return(days, daily, days[i], horizon)
        right = score_call("defensive", fwd)
        if right is None:
            continue
        sev = "severe (<-1.5)" if m < -1.5 else "moderate [-1.5,-0.8)" if m < -0.8 else "mild [-0.8,-0.3)"
        dur = ">10 d" if run > 10 else "4-10 d" if run > 3 else "1-3 d"
        sev_buckets[sev].append(right)
        dur_buckets[dur].append(right)

    def show(name, buckets):
        print(f"\n  defensive hit-rate by {name} (right = market actually fell forward):")
        for k, v in buckets.items():
            if v:
                hr = 100 * sum(v) / len(v)
                flag = "✓ calibrated (sit out)" if hr >= 55 else "✗ still wrong (bounces)" if hr < 50 else ""
                print(f"    {k:<22} {sum(v):>3}/{len(v):<4} = {hr:>3.0f}%   {flag}")
    print(f"\ndecompose-defensive (H={horizon}, W={W}): when is sitting out actually right?")
    show("SEVERITY", sev_buckets)
    show("DURATION (consecutive defensive days)", dur_buckets)
    print("\n  refinement: keep defensive ONLY where it calibrates ≥55%; elsewhere the coarse "
          "judgment is 'don't sit out a dip — wait for severe/sustained collapse'. (prior, not param)")


def distill(horizon, min_n=10):
    """The distill bridge: stage a falsifiable CANDIDATE for any posture ACTION that
    scores <45% over n>=min_n. Runtime-staged for the human gate — it never edits the
    spine. The posture layer's 'research' is a transcript re-distillation + a refined
    prior in XIAOCAO_PLAYBOOK.md (a prior, never an auto param)."""
    all_scored = ([json.loads(l) for l in SCORED.read_text(encoding="utf-8").splitlines() if l.strip()]
                  if SCORED.exists() else [])
    flags = cd.flagged(all_scored, key=lambda s: s.get("action"), min_n=min_n)
    cands = []
    for f in flags:
        action = f["key"]
        if action not in ("aggressive", "defensive"):
            continue
        meaning = ("being aggressive (participating) when the market then fell"
                   if action == "aggressive" else
                   "sitting out (defensive) when the market then rose — 踏空 the bounce")
        cands.append({
            "cand_key": f"posture:{action}",
            "sensor": "posture_calibration",
            "claim": f"Posture action '{action}' calibrates {f['rate']*100:.0f}% over H={horizon}d "
                     f"forward (n={f['n']}); it is wrong by {meaning}.",
            "n": f["n"], "rate": f["rate"], "horizon": horizon,
            "next": "decompose (--decompose) by severity/duration, then refine the prior in "
                    "docs/XIAOCAO_PLAYBOOK.md / re-distill the latest transcript (prior, not a param)",
            "authority": 0,
        })
    n = cd.stage(CANDIDATES, cands)
    print(f"distill: {len(cands)} flagged posture action(s); +{n} new candidate(s) staged to "
          f"{CANDIDATES.name} (min_n={min_n}, threshold<45%). Priors only — ZERO spine authority.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill-proxy", action="store_true")
    ap.add_argument("--decompose", action="store_true", help="decompose the defensive miscalibration")
    ap.add_argument("--distill", action="store_true",
                    help="stage a candidate prior for any action <45% over n>=10 (human gate)")
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
    if a.decompose:
        decompose_defensive(a.horizon, a.window)
        return
    if a.distill:
        distill(a.horizon)
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
