"""道→两体系→汇合, step 2: regime-conditional EXPOSURE SIZING of the short-line book.

Iteration 1 showed short-line's risk-adjusted edge swings hard by regime (Sharpe
0.01 bear → 0.49 trend_strong; only `neutral` is negative). XH-011 rejected
DISABLING short-line by regime (bear is flat, not negative — disabling kills
positive-EV trades). But it never tested continuous SIZING: scale exposure toward
high-Sharpe regimes, size down / sit out negative-EV ones. That is the 汇合
allocator applied to the one book we can actually measure.

Honest test (the trap is leverage masquerading as skill):
  - weights are fit on TRAIN regime stats, applied to TEST (walk-forward, both
    split directions = out-of-sample)
  - EQUAL AVERAGE EXPOSURE: weights normalized so avg deployed capital == flat's,
    so any Sharpe gain is from TIMING (concentration), NOT leverage
  - risk-adjusted: judged on SHARPE (mean/std) + compounded + max drawdown, not
    raw return; plus the short-line per-day guards as a secondary return-significance check
  - "sometimes cash is best": negative-EV regimes get weight 0 (空仓)

Cache-only. Usage: python3 scripts/research_regime_sizing.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import SQLiteCache, iter_cached_responses  # noqa: E402
from xiaocao.research import guards  # noqa: E402
from xiaocao.strategy import regime as regime_mod  # noqa: E402

DB = ROOT / "output" / ".cache" / "xiaocao.db"


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


def regime_known():
    cnt = defaultdict(int)
    for data in iter_cached_responses(str(DB), "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate") and k.get("code"):
                    cnt[k["tradeDate"]] += 1
    return {d for d, c in cnt.items() if c >= 30}


def shortline_daily(cache, known):
    """[(day, regime, mean_trade_return_pct)] sorted by day, regime-known days only."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT trade_date, return_pct FROM mode_history WHERE mode NOT LIKE '/stock/%'").fetchall()
    finally:
        con.close()
    by_day = defaultdict(list)
    for d, r in rows:
        if d in known:
            by_day[d].append(float(r))
    out = []
    for d in sorted(by_day):
        out.append((d, regime_mod.derive_proxy_regime(d, cache), _mean(by_day[d])))
    return out


def weight_fn(train, kind):
    """Fit regime->weight on TRAIN. kind: prop|sharpe|binary. Negative-EV -> 0 (空仓)."""
    by = defaultdict(list)
    for _, reg, r in train:
        by[reg].append(r)
    raw = {}
    for reg, rs in by.items():
        if kind == "prop":
            raw[reg] = max(0.0, _mean(rs))
        elif kind == "sharpe":
            raw[reg] = max(0.0, _sharpe(rs))
        else:  # binary
            raw[reg] = 1.0 if _mean(rs) > 0 else 0.0
    # normalize so AVERAGE exposure over TRAIN days == 1 (equal capital vs flat)
    tw = _mean([raw.get(reg, 0.0) for _, reg, _ in train])
    if tw <= 1e-12:
        return {reg: 1.0 for reg in raw}, 1.0
    return {reg: w / tw for reg, w in raw.items()}, tw


def eval_split(days, train_idx, test_idx, kind):
    train = [days[i] for i in train_idx]
    test = [days[i] for i in test_idx]
    w, _ = weight_fn(train, kind)
    flat = [r for _, _, r in test]
    strat = [w.get(reg, 1.0) * r for _, reg, r in test]
    avg_exp = _mean([w.get(reg, 1.0) for _, reg, _ in test])
    # NOTE: do NOT compound the daily mean-trade-return series — return_pct is a
    # per-trade realized return attributed to its entry day, so compounding daily
    # means double-counts multi-day holds (it produces absurd +1000%+ figures).
    # Mean daily return + Sharpe + maxDD are the honest, comparison-safe metrics.
    return {
        "n": len(test), "avg_exposure": avg_exp,
        "flat_sharpe": _sharpe(flat), "strat_sharpe": _sharpe(strat),
        "flat_mean": _mean(flat), "strat_mean": _mean(strat),
        "flat_dd": _maxdd(flat), "strat_dd": _maxdd(strat),
        "guards_rows": [{"day": d, "strat_ret": w.get(reg, 1.0) * r, "base_ret": r}
                        for d, reg, r in test],
    }


def main():
    cache = SQLiteCache(DB)
    known = regime_known()
    days = shortline_daily(cache, known)
    n = len(days)
    mid = n // 2
    splits = [("fwd train1→test2", range(mid), range(mid, n)),
              ("rev train2→test1", range(mid, n), range(mid))]
    KINDS = ["prop", "sharpe", "binary"]
    print(f"short-line daily series: {n} regime-known days ({days[0][0]}..{days[-1][0]})")
    print("equal-avg-exposure regime sizing, walk-forward BOTH directions (OOS).")
    print(f"n_tried (Bonferroni) = {len(KINDS)}\n")
    print(f"{'kind':<8} {'split':<18} {'avgExp':>6} {'Sharpe flat→strat':>20} "
          f"{'meanDaily% flat→strat':>22} {'maxDD flat→strat':>18}")
    print("-" * 96)
    summary = defaultdict(list)
    for kind in KINDS:
        rows_all = []
        for name, tr, te in splits:
            r = eval_split(days, list(tr), list(te), kind)
            rows_all += r["guards_rows"]
            print(f"{kind:<8} {name:<18} {r['avg_exposure']:>5.2f}x "
                  f"{r['flat_sharpe']:>+8.3f}→{r['strat_sharpe']:>+8.3f}   "
                  f"{r['flat_mean']:>+8.3f}→{r['strat_mean']:>+8.3f}%  "
                  f"{r['flat_dd']:>6.1f}→{r['strat_dd']:>6.1f}%")
            summary[kind].append(r["strat_sharpe"] - r["flat_sharpe"])
        v = guards.evaluate_hypothesis(rows_all, n_tried=len(KINDS), cache_only=True)
        ds = summary[kind]
        oos_ok = all(d > 0 for d in ds)
        print(f"{'':<8} -> OOS Sharpe Δ both splits: {ds[0]:+.3f}, {ds[1]:+.3f}  "
              f"{'BOTH+' if oos_ok else 'NOT both+'}; per-day guards(return): {v['verdict']}"
              f"{' ('+','.join(v['rejected_by'])+')' if v['rejected_by'] else ''}\n")
    print("read: Sharpe must improve OUT-OF-SAMPLE in BOTH split directions (not just one),")
    print("at ~1x avg exposure (so it's timing not leverage). Else: shelve.")


if __name__ == "__main__":
    main()
