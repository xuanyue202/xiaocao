"""Exit-calibration sensor — is the deterministic exit DECISION actually right?

Companion to scripts/posture_calibration.py, but for the exit layer. The exit
policy (src/xiaocao/live/exit_policy.py) makes a prediction at every checkpoint —
HOLD (defer / strong-hold suppress) or SELL (trigger) — and the live monitor
already RECORDS those decisions to output/live/alerts.jsonl ("recorded for forward
evaluation", exit_policy.py docstring). But nothing scores them. show_journal.py
only prints. This closes that open loop: score each recorded exit decision against
the position's REALIZED FORWARD PATH and surface which exit rules are systematically
wrong (= candidates for a research_exit_priors / §10 submission, never an auto edit).

A decision is a PREDICTION; the forward window is genuinely future:
  hold  (SELL_DEFERRED, SELL_SUPPRESSED_STRONG_HOLD)  right if fwd_ret > 0
        (we kept the position; not selling paid)
  sell  (SELL_TRIGGERED)                              right if fwd_ret <= 0
        (we exited; selling avoided further loss / holding would NOT have helped)

This directly measures the session's two live hypotheses, honestly:
  - if HOLD/suppress hit-rate is low  -> strong-hold is sitting in losers.
  - if SELL hit-rate is low (fwd up)  -> exits are CUTTING BOUNCES (the per-position
    analog of "别对回调空仓 — 空仓只留给持续主跌"; soft stops over-firing on dips).

Trap avoidance (this session paid for each of these in real debugging):
  - convention-mismatch: forward path is a SPLIT-SAFE, contiguous daily-return series
    (date_kline.pctChangeRate). It NEVER touches mode_history.return_pct
    (execution-juiced realized PnL, mean>>median) nor the alert's intraday latest_price.
  - lookahead: the forward window is STRICTLY AFTER the decision day (the decision
    day's own move is excluded by construction).
  - open window: forward_return returns None unless the full horizon is present, so a
    not-yet-closed decision is never scored.
  - coverage honesty: scoreable / total is always printed; date_kline froze at
    2026-05-29 for ~3 weeks, so early on most June decisions are NOT yet scoreable —
    the sensor reports that rather than inventing a number. It accumulates forward.

Caveat (stated, not hidden): the per-position counterfactual ignores opportunity cost
of redeployed capital — "sell was wrong because the stock bounced" is not a realized
loss if the freed cash did better. This is a rule-diagnostic sensor, not a P&L claim.

Cache-only. Ledgers live under output/live/ (runtime, gitignored). Sensor/research
only: it does NOT change exit_policy.py, does NOT touch the verdict ledger, and has
ZERO authority over the spine. A flagged rule is evidence for the human gate.
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

DB = ROOT / "output" / ".cache" / "xiaocao.db"
LIVE = ROOT / "output" / "live"
ALERTS = LIVE / "alerts.jsonl"
CALLS = LIVE / "exit_calls.jsonl"
SCORED = LIVE / "exit_calibration.jsonl"

# A single daily return beyond this is impossible for a real A-share trading day
# (BJSE caps at ±30%); a larger value is a split/rights artifact in bfq data or a
# bad bar, so it is dropped rather than allowed to poison a forward compound.
MAX_DAILY_RET = 0.45

# alert -> directional action. SELL_BLOCKED is a liquidity outcome, not a
# discretionary decision, so it is excluded (and lacks entry/price fields anyway).
ACTION = {
    "SELL_DEFERRED": "hold",
    "SELL_SUPPRESSED_STRONG_HOLD": "hold",
    "SELL_TRIGGERED": "sell",
}


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _norm_date(s):
    """alert latest_time/ts come in messy shapes:
    '2026-06-15 09:51:09:830', '2026-06-02 0957', '2026-06-02', '2026-06-22T15:12'.
    Return the ISO date 'YYYY-MM-DD' or None."""
    if not s:
        return None
    s = str(s).strip().replace("T", " ")
    head = s[:10]
    if len(head) == 10 and head[4] == "-" and head[7] == "-":
        return head
    return None


def return_series():
    """Per-code ordered list of (date, daily_return) from date_kline — SPLIT-SAFE.

    Uses pctChangeRate (the documented-good, split-safe daily-return field), which is a
    CONTIGUOUS trading-day series (no gaps to mis-chain). All real bars are kept so the
    series stays contiguous; an impossible single-day return (a split/rights artifact or
    BJSE listing-day pop) is handled in forward_return, which refuses to score any window
    containing one (|ret| > MAX_DAILY_RET) rather than dropping the bar and chaining a
    gap. Returns {code: [(date, ret), ...]} sorted by date, plus the freshest date across
    all codes (for staleness reporting).

    Note on coverage: small-cap low-suck names that are not in the date_kline cache have
    NO forward path here and are reported as no-price-history (not silently scored). That
    is the honest state until those codes enter the daily cache; an earlier
    daily_reconstructed tail-merge was removed because, with one date per code, it
    contributed nothing and risked chaining sparse dates as if they were adjacent days.
    """
    best = {}  # keep the longest cached response per code
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            code = data[0].get("code")
            if code and (code not in best or len(data) > len(best[code])):
                best[code] = data

    series = {}
    for code, bars in best.items():
        rows = []
        for b in bars:
            if not isinstance(b, dict):
                continue
            d = _norm_date(b.get("tradeDate"))
            pct = b.get("pctChangeRate")
            if d and isinstance(pct, (int, float)):
                rows.append((d, float(pct) / 100.0))
        if rows:
            rows.sort()
            series[code] = rows

    freshest = max((rows[-1][0] for rows in series.values() if rows), default=None)
    return series, freshest


def forward_return(rows, date, horizon):
    """Compounded daily return over the `horizon` trading days STRICTLY AFTER `date`.

    Lookahead-safe by construction: the decision day's own return is excluded (d > date).
    Returns None when the window is not yet closed (fewer than `horizon` future bars) OR
    when the window contains an impossible single-day return (|ret| > MAX_DAILY_RET — a
    split/rights artifact or a BJSE listing-day pop). Refusing to score such a window
    (rather than dropping the bar, which would chain non-adjacent days) keeps the series
    contiguous and never compounds a corrupt bar into a falsely-confident hit/miss.
    """
    dates = [d for d, _ in rows]
    after = [i for i, d in enumerate(dates) if d > date]  # first bar strictly after date
    if not after:
        return None
    start = after[0]
    fwd = rows[start:start + horizon]
    if len(fwd) < horizon:
        return None  # forward window not closed yet
    if any(abs(ret) > MAX_DAILY_RET for _, ret in fwd):
        return None  # corrupt/uncapped bar in the window -> unscored, not mis-scored
    comp = 1.0
    for _, ret in fwd:
        comp *= (1.0 + ret)
    return comp - 1.0


def score_call(action, fwd_ret):
    if fwd_ret is None or action not in ("hold", "sell"):
        return None
    if action == "hold":
        return fwd_ret > 0.0   # keeping the position paid
    return fwd_ret <= 0.0       # selling avoided further loss


def _rule_of(r):
    """The specific exit rule that fired, across alert classes:
    SELL_TRIGGERED -> sell_reason, SELL_DEFERRED -> reason (=deferred_sell_reason),
    SELL_SUPPRESSED_STRONG_HOLD -> strong_hold_reason."""
    return r.get("sell_reason") or r.get("reason") or r.get("strong_hold_reason") or None


def iter_decisions():
    """Yield ONE net exit decision per (code, day) from alerts.jsonl.

    alerts.jsonl is a per-poll DIAGNOSIS stream, not an execution log: many rows per
    (code, day). Crucially, the staged-exit design (exit_policy.py) DEFERS soft exits
    to the 14:55 pass, so a position is typically SELL_DEFERRED intraday and then
    SELL_TRIGGERED at 14:55 the SAME day — and a strong-hold can be suppressed early
    then sold at 14:55 too. Scoring the defer/suppress AND the trigger separately
    would double-count one position-day as both a (short-lived) hold and a sell on the
    same forward path — two mechanically-opposite votes. So we collapse to the net
    REALIZED stance per position-day:
        sold that day        -> SELL decision  (rule = the firing sell_reason)
        else held (suppress) -> HOLD decision  (rule = strong_hold_reason)
        else held (defer)    -> HOLD decision  (rule = DEFERRED_<deferred reason>)
    The HOLD cases are the positions we did NOT sell despite a signal/checkpoint — the
    position-level analog of "别对回调空仓 — don't sell the dip". Within a class the LAST
    non-null rule of the day wins (the firing rule shows up on later polls).
    Decision date = ts[:10] (canonical), falling back to latest_time. All alerts are
    Book B by construction (the monitor only decides Book B; Book A is next-close
    settle with no discretionary exit)."""
    if not ALERTS.exists():
        return
    acc = {}  # (code, date) -> aggregated per-poll state for the day
    order = []
    for line in ALERTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        alert = r.get("alert")
        if alert not in ACTION:
            continue
        code = r.get("code")
        date = _norm_date(r.get("ts")) or _norm_date(r.get("latest_time"))
        if not code or not date:
            continue
        key = (code, date)
        if key not in acc:
            acc[key] = {"code": code, "date": date, "name": r.get("name"),
                        "entry_date": r.get("entry_date"), "book": "B",
                        "trigger_rule": None, "trigger_phase": None,
                        "suppress_rule": None, "defer_rule": None,
                        "has_trigger": False, "has_suppress": False, "has_defer": False}
            order.append(key)
        g = acc[key]
        rule = _rule_of(r)
        if alert == "SELL_TRIGGERED":
            g["has_trigger"] = True
            if rule:
                g["trigger_rule"] = rule
            if r.get("decision_phase"):
                g["trigger_phase"] = r.get("decision_phase")
        elif alert == "SELL_SUPPRESSED_STRONG_HOLD":
            g["has_suppress"] = True
            if rule:
                g["suppress_rule"] = rule
        elif alert == "SELL_DEFERRED":
            g["has_defer"] = True
            if rule:
                g["defer_rule"] = rule
    for key in order:
        g = acc[key]
        base = {"code": g["code"], "date": g["date"], "name": g["name"],
                "entry_date": g["entry_date"], "book": "B"}
        if g["has_trigger"]:                      # realized stance: SOLD that day
            yield {**base, "alert": "SELL_TRIGGERED", "action": "sell",
                   "rule": g["trigger_rule"], "decision_phase": g["trigger_phase"]}
        elif g["has_suppress"]:                   # held via strong-hold suppression
            yield {**base, "alert": "SELL_SUPPRESSED_STRONG_HOLD", "action": "hold",
                   "rule": g["suppress_rule"], "decision_phase": None}
        elif g["has_defer"]:                       # held: deferred and not sold that day
            yield {**base, "alert": "SELL_DEFERRED", "action": "hold",
                   "rule": f"DEFERRED_{g['defer_rule']}" if g["defer_rule"] else None,
                   "decision_phase": None}


def summarize(scored):
    by = defaultdict(lambda: [0, 0])    # alert -> [hits, n]
    act = defaultdict(lambda: [0, 0])   # action -> [hits, n]
    rule = defaultdict(lambda: [0, 0])  # (action, rule) -> [hits, n]
    for s in scored:
        if s.get("right") is None:
            continue
        hit = 1 if s["right"] else 0
        by[s["alert"]][0] += hit
        by[s["alert"]][1] += 1
        act[s["action"]][0] += hit
        act[s["action"]][1] += 1
        rule[(s["action"], s.get("rule") or "(unlabeled)")][0] += hit
        rule[(s["action"], s.get("rule") or "(unlabeled)")][1] += 1
    tot_n = sum(v[1] for v in by.values())
    MIN_N = 5  # below this a hit-rate is noise, not signal — tag it, never act on it

    def _line(label, hit, n, *, flag_wrong=False):
        tag = "  · n<5, not yet meaningful" if n < MIN_N else (
            "  ⚠ systematically wrong → investigate" if flag_wrong and hit / n < 0.45 else "")
        print(f"      {label:<34} {hit:>3}/{n:<4} = {100*hit/n:>3.0f}%{tag}")

    print(f"\n  exit calibration ({tot_n} closed decisions, Book B):")
    print("    by action —")
    for action in ("sell", "hold"):
        hit, n = act[action]
        if n:
            interp = ("(right = stock fell after exit)" if action == "sell"
                      else "(right = position rose after we held)")
            _line(f"{action} {interp}", hit, n)
    print("    by decision class —")
    for alert in ("SELL_TRIGGERED", "SELL_DEFERRED", "SELL_SUPPRESSED_STRONG_HOLD"):
        hit, n = by[alert]
        if n:
            _line(alert, hit, n, flag_wrong=(n >= 10))
    if rule:
        print("    by exit rule (the actionable view) —")
        for (action, rname), (hit, n) in sorted(rule.items(), key=lambda kv: -kv[1][1]):
            if n:
                _line(f"{action} {rname}", hit, n, flag_wrong=(n >= 8))
    if tot_n:
        print("\n  reading: a rule/class < 45% over n>=8-10 is a distillation target — evidence for "
              "research_exit_priors + the §10 human gate, NEVER an auto edit to exit_policy.py.")
        print("  caveat: this scores the per-position forward path only; it ignores opportunity cost "
              "of redeployed capital, so a low sell hit-rate is NOT a P&L loss claim.")


def ingest():
    """Append any new exit decisions from alerts.jsonl to the calls ledger (deduped)."""
    LIVE.mkdir(parents=True, exist_ok=True)
    existing = set()
    if CALLS.exists():
        for line in CALLS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                existing.add((c["code"], c["date"]))   # one decision per position-day
    added = 0
    with CALLS.open("a", encoding="utf-8") as fh:
        for d in iter_decisions():
            if (d["code"], d["date"]) in existing:
                continue
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
            existing.add((d["code"], d["date"]))
            added += 1
    print(f"ingest: +{added} new exit decisions; {len(existing)} total recorded")


def score(horizon, verbose_skips=False):
    """Score every recorded call whose forward window has closed; print the summary."""
    series, freshest = return_series()
    # governance (convention-mismatch guard): the forward source must be a daily
    # PRICE-return series, not realized PnL. Pool returns across ALL codes (a single
    # stock's daily returns can legitimately be skewed mean>>median, so the per-series
    # realized-PnL test would false-positive). Real daily price returns center near 0
    # and are bounded by the A-share daily limit; realized/execution PnL is not.
    all_rets = [ret for rows in series.values() for _, ret in rows]
    if all_rets:
        srt = sorted(all_rets)
        med = srt[len(srt) // 2]
        p99 = sorted(abs(x) for x in all_rets)[min(len(srt) - 1, int(0.99 * len(srt)))]
        if abs(med) > 0.03 or p99 > 0.30:
            print(f"⚠ forward source does not look like a daily price-return series "
                  f"(median={med:.3f}, p99|ret|={p99:.3f}) — refusing to score (convention guard).")
            return
    if freshest:
        from datetime import date
        y, m, d = (int(x) for x in freshest.split("-"))
        lag = (date.today() - date(y, m, d)).days
        print(f"forward source: {len(series)} codes, freshest daily bar {freshest}"
              f"{f' (⚠ {lag}d stale — daily cache lags the live decisions)' if lag > 5 else ''}")

    calls = []
    if CALLS.exists():
        calls = [json.loads(l) for l in CALLS.read_text(encoding="utf-8").splitlines() if l.strip()]
    already = set()
    if SCORED.exists():
        for l in SCORED.read_text(encoding="utf-8").splitlines():
            if l.strip():
                c = json.loads(l)
                already.add((c["code"], c["date"]))

    newly, no_data, open_window = [], 0, 0
    for c in calls:
        if (c["code"], c["date"]) in already:
            continue
        rows = series.get(c["code"])
        if not rows:
            no_data += 1
            if verbose_skips:
                print(f"    skip (no price history): {c['code']} {c.get('name')}")
            continue
        fwd = forward_return(rows, c["date"], horizon)
        if fwd is None:
            open_window += 1
            continue
        c = dict(c)
        c["horizon"] = horizon
        c["fwd_ret"] = round(fwd, 4)
        c["right"] = score_call(c["action"], fwd)
        newly.append(c)

    if newly:
        LIVE.mkdir(parents=True, exist_ok=True)
        with SCORED.open("a", encoding="utf-8") as fh:
            for c in newly:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    all_scored = ([json.loads(l) for l in SCORED.read_text(encoding="utf-8").splitlines() if l.strip()]
                  if SCORED.exists() else [])
    total_calls = len(calls)
    print(f"exit scoring (H={horizon}): +{len(newly)} newly closed; {len(all_scored)} total scored "
          f"| {open_window} window-still-open, {no_data} no-price-history "
          f"(of {total_calls} recorded decisions)")
    if no_data and not all_scored:
        print("  note: forward source (date_kline) is frozen weeks behind the June decisions, and "
              "many low-suck names aren't in the daily cache. The sensor is recording now and will "
              "score forward as the daily cache advances — this is the honest coverage state, not a bug.")
    summarize(all_scored)


def report(horizon):
    all_scored = ([json.loads(l) for l in SCORED.read_text(encoding="utf-8").splitlines() if l.strip()]
                  if SCORED.exists() else [])
    n_calls = len(CALLS.read_text(encoding="utf-8").splitlines()) if CALLS.exists() else 0
    print(f"exit calibration report: {len(all_scored)} scored / {n_calls} recorded decisions")
    summarize(all_scored)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ingest", action="store_true", help="record new exit decisions from alerts.jsonl")
    ap.add_argument("--score", action="store_true", help="score recorded decisions whose window closed")
    ap.add_argument("--report", action="store_true", help="print the current calibration summary")
    ap.add_argument("--horizon", type=int, default=5, help="forward trading days (default 5)")
    ap.add_argument("--verbose-skips", action="store_true")
    a = ap.parse_args()

    if a.ingest:
        ingest()
    if a.score:
        score(a.horizon, a.verbose_skips)
    if a.report:
        report(a.horizon)
    if not (a.ingest or a.score or a.report):
        ap.print_help()


if __name__ == "__main__":
    main()
