#!/usr/bin/env python3
"""道→两体系→汇合, step 1: each book's RISK-ADJUSTED return BY REGIME (+ cash).

Aggregate "trend vs short-line" hides the one thing that matters for cross-cycle
compounding: neither book is good every regime, and sometimes cash wins. So we
profile both books conditioned on the proxy regime (derived from cached
date_kline), plus a cash baseline (0), to answer:
  - which book wins in which regime?
  - is there a regime where cash dominates BOTH (空仓 is correct)?
This is the evidence the execution-layer allocator (汇合) must be built on.

Honest units (different horizons, both "% realized per position"):
  - 短线低吸 : per-TRADE return_pct from mode_history, by ENTRY-day regime
  - 趋势主线  : per-HOLD return (non-overlapping R-day) from mainline_signal, by entry regime
Risk-adjusted = mean / std (a per-position Sharpe-like ratio; NOT annualized).

Cache-only. Usage: python3 scripts/research_regime_profile.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.strategy import mainline_signal as ms  # noqa: E402
from xiaocao.strategy import regime as regime_mod  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
REGIMES = ["bear", "divergence", "neutral", "recovery", "trend_continuing", "trend_strong"]


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
def _std(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
def _sharpe(xs):
    s = _std(xs)
    return (_mean(xs) / s) if s > 1e-12 else 0.0
def _win(xs): return _mean([1.0 if x > 0 else 0.0 for x in xs]) if xs else 0.0


def regime_known():
    cnt = defaultdict(int)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate") and k.get("code"):
                    cnt[k["tradeDate"]] += 1
    return {d for d, c in cnt.items() if c >= 30}


def short_line_by_regime(cache, known):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, return_pct FROM mode_history WHERE mode NOT LIKE '/stock/%'").fetchall()
    finally:
        con.close()
    by = defaultdict(list)
    for d, r in rows:
        if d in known:
            by[regime_mod.derive_proxy_regime(d, cache)].append(float(r))
    return by


def trend_by_regime(cache, known, *, L=60, R=60, M=3):
    panel = ms.load_concept_panel(DB)
    days = panel["days"]
    by = defaultdict(list)         # absolute per-hold return
    by_alpha = defaultdict(list)   # per-hold alpha vs avg-theme
    i = L
    while i < len(days) - R:
        picks = ms.select_by_trend_strength(panel, i, L=L, M=M)
        sf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in picks]
        sf = [x for x in sf if x is not None]
        allf = [ms.cum_return(panel["ret"], days, c, i, i + R) for c in panel["num"][days[i]]]
        allf = [x for x in allf if x is not None]
        if sf and len(allf) >= 10:
            reg = regime_mod.derive_proxy_regime(days[i], cache) if days[i] in known else "unknown"
            ret = _mean(sf)
            by[reg].append(ret)
            by_alpha[reg].append(ret - _mean(allf))
        i += R
    return by, by_alpha


def _fmt(xs):
    if not xs:
        return f"{'·':>7} {'·':>6} {'·':>5} {0:>4}"
    return f"{_mean(xs):>+7.2f} {_sharpe(xs):>+6.2f} {_win(xs)*100:>4.0f}% {len(xs):>4}"


def main():
    cache = SQLiteCache(DB)
    known = regime_known()
    sl = short_line_by_regime(cache, known)
    tr, tr_alpha = trend_by_regime(cache, known)

    print(f"regime-known days: {len(known)}  |  short-line trades: {sum(len(v) for v in sl.values())}  "
          f"|  trend holds: {sum(len(v) for v in tr.values())}\n")
    print("per-position: mean% / Sharpe(mean/std) / win% / n   — risk-adjusted by regime")
    print(f"{'regime':<18}| {'短线低吸 (per-trade)':^26}| {'趋势主线 (per-hold abs)':^26}| {'cash':>5} | best")
    print("-" * 92)
    for r in REGIMES:
        s, t = sl.get(r, []), tr.get(r, [])
        # decide winner by mean (cash=0)
        cand = {"short": _mean(s) if s else None, "trend": _mean(t) if t else None, "cash": 0.0}
        live = {k: v for k, v in cand.items() if v is not None}
        best = max(live, key=live.get)
        if live.get("short", -9) <= 0 and live.get("trend", -9) <= 0:
            best = "cash"
        print(f"{r:<18}| {_fmt(s):>26}| {_fmt(t):>26}| {0.0:>5.1f} | {best}")
    # unknowns
    if sl.get("neutral") is None:
        pass
    print()
    print("trend vs avg-theme ALPHA by regime (per-hold): ", end="")
    print(" ".join(f"{r[:4]}={_mean(tr_alpha.get(r, [])):+.1f}pp(n{len(tr_alpha.get(r, []))})"
                   for r in REGIMES if tr_alpha.get(r)))
    nb = sum(len(sl.get(r, [])) for r in ("bear", "divergence"))
    print(f"\nsample skew: bear+divergence short-line trades = {nb} "
          f"(of {sum(len(v) for v in sl.values())}); a real bear MARKET (not just bad days) "
          f"is likely absent — note when concluding cross-cycle.")


if __name__ == "__main__":
    main()
