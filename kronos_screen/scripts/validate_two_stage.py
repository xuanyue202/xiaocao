"""Definitive validation of the two-stage screen on real OOS data.

Stage 1 (primary): xiaocao mode signals (the candidate pool, from backtest).
Stage 2 (secondary): frozen Kronos-base embedding -> per-fold StandardScaler ->
PCA(8) -> Ridge on within-day demeaned return; each day keep the top fraction.

All scores are walk-forward OOS (model trained only on strictly-prior days).
Reports: (A) IC significance, (B) realistic daily fixed-capital backtest vs the
current take-all screen, (C) honest per-trade economics, (D) per board,
(E) per-month robustness.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from ceiling_test import fold_bounds


def wf_scores(E, meta, folds, k=8, alpha=10.0):
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    oos = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        sc = StandardScaler().fit(E[tr]); p = PCA(k, random_state=0).fit(sc.transform(E[tr]))
        oos[te] = Ridge(alpha=alpha).fit(p.transform(sc.transform(E[tr])), tgt[tr]).predict(p.transform(sc.transform(E[te])))
    return oos


def equity(daily):
    e = np.cumprod(1 + np.asarray(daily) / 100.0)
    peak = np.maximum.accumulate(e); dd = (e / peak - 1).min() * 100
    d = np.asarray(daily)
    return (e[-1] - 1) * 100, dd, d.mean() / (d.std() + 1e-9) * np.sqrt(244), e


def daily_port(meta, oos, dl, frac=None, fixed=None):
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    dr, dw, sel = [], [], np.zeros(len(meta), bool)
    for d in dl:
        m = np.where(days == d)[0]
        if len(m) == 0: continue
        k = fixed if fixed else max(1, int(round(len(m) * frac)))
        k = min(k, len(m))
        top = m[np.argsort(-oos[m])[:k]]
        sel[top] = True; dr.append(ret[top].mean()); dw.append((ret[top] > 0).mean())
    return np.array(dr), np.mean(dw) * 100, sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--emb", default="base")
    a = ap.parse_args()
    ds = Path(a.ds); meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    _, folds = fold_bounds(days, 5, 0.5)
    oos = wf_scores(E, meta, folds)
    mask = ~np.isnan(oos); dl = sorted(set(days[mask]))
    meta["month"] = meta["buyDate"].str[:7]

    print(f"==== TWO-STAGE VALIDATION (emb={a.emb}) ====")
    print(f"OOS {dl[0]}..{dl[-1]}  days={len(dl)}  candidates={int(mask.sum())}\n")

    # (A) IC significance
    dic = []
    for d in dl:
        m = days == d
        if m.sum() >= 3 and np.std(oos[m]) > 0:
            c = spearmanr(oos[m], ret[m]).correlation
            if c == c: dic.append(c)
    dic = np.array(dic); t, p = ttest_1samp(dic, 0.0)
    print(f"(A) within-day IC: mean={dic.mean():.3f}  t={t:.2f}  p={p:.4f}  %days>0={(dic>0).mean()*100:.0f}%  (n_days={len(dic)})")

    # (B) realistic daily fixed-capital backtest
    print("\n(B) daily fixed-capital backtest (1 unit/day split across selected, next-close exit):")
    ta = np.array([ret[days == d].mean() for d in dl])
    taw = np.mean([(ret[days == d] > 0).mean() for d in dl]) * 100
    tot, dd, sh, _ = equity(ta)
    print(f"  {'strategy':<22}{'cum%':>8}{'avgDay%':>9}{'win%':>7}{'maxDD%':>8}{'Sharpe':>8}")
    print(f"  {'take-all (current)':<22}{tot:>8.1f}{ta.mean():>9.3f}{taw:>7.1f}{dd:>8.1f}{sh:>8.2f}")
    for lab, kw in [("Kronos top50%", dict(frac=0.5)), ("Kronos top34%", dict(frac=0.34))]:
        dr, w, _ = daily_port(meta, oos, dl, **kw)
        tot, dd, sh, _ = equity(dr)
        print(f"  {lab:<22}{tot:>8.1f}{dr.mean():>9.3f}{w:>7.1f}{dd:>8.1f}{sh:>8.2f}")

    # (C) honest per-trade
    _, _, sel = daily_port(meta, oos, dl, frac=0.5)
    bot = mask & ~sel
    print("\n(C) per-trade (equal-weight per trade):")
    print(f"  take-all : ret={ret[mask].mean():+.3f}% win={(ret[mask]>0).mean()*100:.1f}% n={mask.sum()}")
    print(f"  top50    : ret={ret[sel].mean():+.3f}% win={(ret[sel]>0).mean()*100:.1f}% n={sel.sum()}")
    print(f"  bottom50 : ret={ret[bot].mean():+.3f}% win={(ret[bot]>0).mean()*100:.1f}% n={bot.sum()}")
    print(f"  top-bottom spread = {ret[sel].mean()-ret[bot].mean():+.3f}%/trade")

    # (D) per board
    print("\n(D) per-board (top50 vs take-all, per-trade):")
    for b in ["主板", "创业", "科创", "北交"]:
        bm = mask & (meta["board"].to_numpy() == b); sm = sel & (meta["board"].to_numpy() == b)
        if bm.sum() == 0: continue
        print(f"  {b:<5} all n={int(bm.sum()):>4} {ret[bm].mean():+.2f}%/{(ret[bm]>0).mean()*100:.0f}%   top50 n={int(sm.sum()):>4} {ret[sm].mean():+.2f}%/{(ret[sm]>0).mean()*100:.0f}%")

    # (E) per-month robustness
    print("\n(E) per-month (daily top50 edge over take-all):")
    for mo in sorted(set(meta.loc[mask, "month"])):
        md = [d for d in dl if d[:7] == mo]
        if not md: continue
        tam = np.mean([ret[days == d].mean() for d in md])
        drm, _, _ = daily_port(meta, oos, md, frac=0.5)
        print(f"  {mo}  take-all {tam:+.2f}%  top50 {drm.mean():+.2f}%  edge {drm.mean()-tam:+.2f}%")


if __name__ == "__main__":
    main()
