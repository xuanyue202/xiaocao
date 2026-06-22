"""Is 赚钱效应 (money-making effect) a PERSISTENT, OOS-transferable gate?

User's reframe: don't finely time regime (屎上雕花) — just trade where 赚钱效应 is
high, sit out the bear. My earlier gate used trailing MEAN RETURN (price momentum)
and failed OOS because it mean-reverts. 赚钱效应 is different: it is reflexive
(limit-ups/strong gains beget more), so it may PERSIST — and a persistent signal
can be reacted to (lagged) without lookahead.

Signal = daily 赚钱效应 proxy among big-caps: fraction with pctChangeRate > +5%
(speculation/strength intensity), and limit-up count. Tests:
  1. PERSISTENCE — autocorrelation at lags 1/5/20 (price momentum ~0; reflexive >0?)
  2. GATE — participate (w=1) when LAGGED trailing-W 赚钱效应 ≥ train median, else
     w=down; equal-avg-exposure (timing not leverage), walk-forward BOTH splits,
     judged on Sharpe vs always-in. Lagged => no lookahead.

Cross-cycle (2021-2026, real bear). Cache-only. Usage: python3 scripts/research_money_effect.py
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
    return (_mean(xs) / s) * (252 ** 0.5) if s > 1e-12 else 0.0
def _autocorr(xs, lag):
    n = len(xs) - lag
    if n < 3:
        return 0.0
    a, b = xs[:-lag], xs[lag:]
    ma, mb = _mean(a), _mean(b)
    sa, sb = _std(a), _std(b)
    if sa <= 1e-12 or sb <= 1e-12:
        return 0.0
    return (sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)) / (sa * sb)
def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def build():
    best = {}
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list) and data and isinstance(data[0], dict):
            code = data[0].get("code")
            if code and (code not in best or len(data) > len(best[code])):
                best[code] = data
    by_date = defaultdict(list)  # date -> [(pct, isLimitUp)]
    for code, bars in best.items():
        ds = [b.get("tradeDate") for b in bars if isinstance(b, dict) and b.get("tradeDate")]
        if not ds or min(ds) >= "2023-01-01":
            continue
        for b in bars:
            td, pct = b.get("tradeDate"), b.get("pctChangeRate")
            if td and isinstance(pct, (int, float)):
                by_date[td].append((float(pct), int(b.get("isLimitUp") or 0)))
    days = sorted(d for d in by_date if len(by_date[d]) >= MIN_UNIV)
    series = []  # (day, market_ret, money_effect, limitups)
    for d in days:
        rows = by_date[d]
        mret = _mean([p for p, _ in rows])
        eff = _mean([1.0 if p > 5 else 0.0 for p, _ in rows]) * 100  # % of big-caps up >5%
        lu = sum(lu for _, lu in rows)
        series.append([d, mret, eff, lu])
    return series


def gate_eval(series, W, down_w):
    """w=1 if LAGGED trailing-W money-effect >= train median, else down_w. Equal-avg-exp."""
    eff = [s[2] for s in series]
    # lagged trailing-W mean money-effect (through yesterday)
    trail = []
    for i in range(len(series)):
        lo = max(0, i - W)
        trail.append(_mean(eff[lo:i]) if i > 0 else eff[0])
    mret = [s[1] for s in series]
    n = len(series)
    mid = n // 2
    out = []
    for tr_idx, te_idx in [(range(mid), range(mid, n)), (range(mid, n), range(mid))]:
        thr = _median([trail[i] for i in tr_idx])
        raw = {i: (1.0 if trail[i] >= thr else down_w) for i in te_idx}
        norm = _mean(list(raw.values())) or 1.0
        s = [(raw[i] / norm) * mret[i] for i in te_idx]
        f = [mret[i] for i in te_idx]
        out.append((_sharpe(s), _sharpe(f), _mean([raw[i] / norm for i in te_idx])))
    return out


def main():
    series = build()
    print(f"big-cap panel: {len(series)} days {series[0][0]}..{series[-1][0]}")
    eff = [s[2] for s in series]
    mret = [s[1] for s in series]
    print(f"赚钱效应 (% big-caps up>5%): mean {_mean(eff):.1f}%  | total limit-ups {sum(s[3] for s in series)}")
    print("\n1) PERSISTENCE (autocorrelation) — reflexive signal should beat price momentum:")
    print(f"   赚钱效应  lag1 {_autocorr(eff,1):+.2f}  lag5 {_autocorr(eff,5):+.2f}  lag20 {_autocorr(eff,20):+.2f}")
    print(f"   mean-ret  lag1 {_autocorr(mret,1):+.2f}  lag5 {_autocorr(mret,5):+.2f}  lag20 {_autocorr(mret,20):+.2f}")
    print("\n2) GATE (lagged, equal-avg-exposure, walk-forward BOTH splits) vs always-in:")
    print(f"   {'W':>3} {'down_w':>7} {'avgExp':>7} {'Sharpe gate/flat (fwd)':>24} {'(rev)':>16} {'both+?':>7}")
    for W in (10, 20):
        for dw in (0.0, 0.5):
            res = gate_eval(series, W, dw)
            (gf, ff, ef), (gr, fr, er) = res
            both = (gf > ff) and (gr > fr)
            print(f"   {W:>3} {dw:>7.1f} {ef:>5.2f}/{er:.2f} "
                  f"{gf:>+9.2f}/{ff:>+9.2f}        {gr:>+7.2f}/{fr:>+7.2f}   {'YES' if both else 'no':>7}")
    print("\nread: gate must beat always-in OOS on Sharpe in BOTH split directions. "
          "If 赚钱效应 autocorr >> mean-ret autocorr but the gate still fails, the effect is "
          "real-time JUDGMENT, not a mechanical lagged timer (= belongs in the playbook/道-layer).")


if __name__ == "__main__":
    main()
