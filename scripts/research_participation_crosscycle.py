"""道→两体系→汇合: the allocator's core question, on REAL cross-cycle data.

The stock-level cross-cycle test killed trend SELECTION (momentum loses to the
market and crashes in bears). What compounds is PARTICIPATION — holding the
big-cap market. So the real allocator question, now testable against the 2022
bear + 2024 crash: does REGIME-TIMING the participation (be in the market in good
regimes, cash in bear) beat always-in on a RISK-ADJUSTED basis, out-of-sample?

market = equal-weight big-cap daily return (2021-2026). regime = trailing-W mean.
Strategies, walk-forward BOTH directions (fit regime->weight on train, apply test),
equal-average-exposure (so it's timing not leverage):
  flat        : always in (w=1)
  cash_in_bear: w=0 on bear regime, else 1
  regime_prop : w ∝ max(0, train regime mean) — sit out negative-EV regimes
Judged on Sharpe + compounded + max drawdown; PASS only if it beats flat OOS in
BOTH split directions. Cache-only. Usage: python3 scripts/research_participation_crosscycle.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import iter_cached_responses  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"
MIN_UNIV = 100


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
def _std(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
def _sharpe(xs):
    s = _std(xs)
    return (_mean(xs) / s) * (252 ** 0.5) if s > 1e-12 else 0.0  # annualized (daily)
def _compound(xs):
    c = 1.0
    for r in xs:
        c *= 1.0 + r / 100.0
    return (c - 1.0) * 100.0
def _maxdd(xs):
    eq = peak = 1.0
    mdd = 0.0
    for r in xs:
        eq *= 1.0 + r / 100.0
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100.0


def build_market_daily():
    best = {}
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            code = data[0].get("code")
            if code and (code not in best or len(data) > len(best[code])):
                best[code] = data
    by_date = defaultdict(dict)
    for code, bars in best.items():
        ds = [b.get("tradeDate") for b in bars if isinstance(b, dict) and b.get("tradeDate")]
        if not ds or min(ds) >= "2023-01-01":
            continue
        for b in bars:
            td, close = b.get("tradeDate"), b.get("close")
            if td and isinstance(close, (int, float)) and close > 0:
                by_date[td][code] = float(close)
    days = sorted(d for d in by_date if len(by_date[d]) >= MIN_UNIV)
    series = []  # (day, daily_return_pct, regime)
    for i in range(1, len(days)):
        prev, cur = by_date[days[i - 1]], by_date[days[i]]
        rs = [(cur[c] / prev[c] - 1.0) * 100.0 for c in cur if c in prev]
        if rs:
            series.append([days[i], _mean(rs)])
    # regime = trailing-20d mean daily return through YESTERDAY (exclude day i —
    # the position on day i is decided at its open from info known before i; using
    # day i's own return here would be lookahead and inflate any sit-out rule).
    for i in range(len(series)):
        lo = max(0, i - 20)
        m = _mean([s[1] for s in series[lo:i]]) if i > 0 else 0.0
        reg = "bear" if m < -0.3 else "divergence" if m < 0 else "trend_strong" if m > 0.3 else "neutral"
        series[i].append(reg)
    return series


def weight(train, kind):
    by = defaultdict(list)
    for _, r, reg in train:
        by[reg].append(r)
    if kind == "flat":
        raw = {reg: 1.0 for reg in by}
    elif kind == "cash_in_bear":
        raw = {reg: (0.0 if reg == "bear" else 1.0) for reg in by}
    else:  # regime_prop
        raw = {reg: max(0.0, _mean(rs)) for reg, rs in by.items()}
    norm = _mean([raw.get(reg, 1.0) for _, _, reg in train]) or 1.0
    return {reg: w / norm for reg, w in raw.items()}


def evalu(series, kind):
    n = len(series)
    mid = n // 2
    out = []
    for tr, te in [(series[:mid], series[mid:]), (series[mid:], series[:mid])]:
        w = weight(tr, kind)
        s = [w.get(reg, 1.0) * r for _, r, reg in te]
        f = [r for _, r, reg in te]
        out.append((_sharpe(s), _sharpe(f), _compound(s), _compound(f),
                    _maxdd(s), _maxdd(f), _mean([w.get(reg, 1.0) for _, _, reg in te])))
    return out


def main():
    series = build_market_daily()
    print(f"big-cap market daily series: {len(series)} days {series[0][0]}..{series[-1][0]}")
    rdist = defaultdict(int)
    for _, _, reg in series:
        rdist[reg] += 1
    print("regime-day distribution:", dict(rdist))
    print(f"\nbuy&hold market: compound {_compound([r for _,r,_ in series]):+.0f}%  "
          f"Sharpe(ann) {_sharpe([r for _,r,_ in series]):+.2f}  maxDD {_maxdd([r for _,r,_ in series]):.0f}%\n")
    print(f"{'strategy':<14} {'split':<8} {'avgExp':>6} {'Sharpe s/flat':>16} {'comp s/flat':>18} {'maxDD s/flat':>16}")
    print("-" * 84)
    for kind in ["cash_in_bear", "regime_prop"]:
        res = evalu(series, kind)
        deltas = []
        for k, (ss, fs, sc, fc, sd, fd, ae) in enumerate(res):
            print(f"{kind:<14} {('fwd' if k==0 else 'rev'):<8} {ae:>5.2f}x "
                  f"{ss:>+7.2f}/{fs:>+7.2f} {sc:>+8.0f}/{fc:>+8.0f}% {sd:>6.0f}/{fd:>6.0f}%")
            deltas.append(ss - fs)
        ok = all(d > 0 for d in deltas)
        print(f"{'':<14} -> OOS Sharpe Δ both splits: {deltas[0]:+.2f}, {deltas[1]:+.2f}  "
              f"{'BOTH+ (beats always-in)' if ok else 'NOT both+'}\n")
    print("read: a regime-timing rule must beat always-in OOS in BOTH split directions on Sharpe.")


if __name__ == "__main__":
    main()
