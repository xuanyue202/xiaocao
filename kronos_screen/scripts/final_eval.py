"""Deliverable measurement: daily top-K portfolio backtest of the Kronos
secondary screen vs the current take-all screen, using walk-forward OOS
scores (each day scored by a model trained only on strictly-prior days).

Model: base frozen embedding -> per-fold StandardScaler -> PCA(8) ->
Ridge(alpha=10) on within-day demeaned return. Selection: each day keep the
top fraction (and a fixed-N variant). Equity = compound daily equal-weight
return of selected names.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from ceiling_test import fold_bounds


def walk_forward_scores(E, meta, folds, pca_k=8, alpha=10.0):
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    oos = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        sc = StandardScaler().fit(E[tr])
        p = PCA(pca_k, random_state=0).fit(sc.transform(E[tr]))
        Xtr = p.transform(sc.transform(E[tr])); Xte = p.transform(sc.transform(E[te]))
        oos[te] = Ridge(alpha=alpha).fit(Xtr, tgt[tr]).predict(Xte)
    return oos


def equity(daily_rets):
    eq = np.cumprod(1 + np.array(daily_rets) / 100.0)
    total = (eq[-1] - 1) * 100
    peak = np.maximum.accumulate(eq); dd = (eq / peak - 1).min() * 100
    dr = np.array(daily_rets)
    sharpe = dr.mean() / (dr.std() + 1e-9) * np.sqrt(244)
    return total, dd, sharpe


def daily_select(meta, oos, days_list, frac=None, fixed=None):
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    drets, dwins, sel_idx = [], [], []
    for d in days_list:
        m = np.where(days == d)[0]
        if len(m) == 0: continue
        order = m[np.argsort(-oos[m])]
        k = fixed if fixed else max(1, int(round(len(m) * frac)))
        k = min(k, len(m))
        top = order[:k]
        sel_idx.extend(top.tolist())
        drets.append(ret[top].mean()); dwins.append((ret[top] > 0).mean())
    return np.array(drets), np.mean(dwins) * 100, np.array(sel_idx)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ds", required=True)
    ap.add_argument("--emb", default="base"); a = ap.parse_args()
    ds = Path(a.ds); meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    _, folds = fold_bounds(days, 5, 0.5)
    oos = walk_forward_scores(E, meta, folds)
    np.save(ds / "oos_scores.npy", oos)
    mask = ~np.isnan(oos); dl = sorted(set(days[mask]))

    # take-all daily
    ta = np.array([ret[days == d].mean() for d in dl])
    ta_win = np.mean([(ret[days == d] > 0).mean() for d in dl]) * 100
    print(f"OOS {dl[0]}..{dl[-1]}  days={len(dl)}  trades={mask.sum()}\n")
    t, dd, sh = equity(ta)
    print(f"{'strategy':<20}{'cumRet%':>9}{'avgDay%':>9}{'win%':>7}{'maxDD%':>8}{'Sharpe':>8}{'trades':>8}")
    print(f"{'take-all (current)':<20}{t:>9.1f}{ta.mean():>9.3f}{ta_win:>7.1f}{dd:>8.1f}{sh:>8.2f}{int(mask.sum()):>8}")
    for label, kw in [("Kronos top50%", dict(frac=0.5)), ("Kronos top34%", dict(frac=0.34)),
                      ("Kronos top-3/day", dict(fixed=3)), ("Kronos top-2/day", dict(fixed=2))]:
        dr, win, sidx = daily_select(meta, oos, dl, **kw)
        t, dd, sh = equity(dr)
        print(f"{label:<20}{t:>9.1f}{dr.mean():>9.3f}{win:>7.1f}{dd:>8.1f}{sh:>8.2f}{len(sidx):>8}")

    # per-board top50 vs take-all
    print("\nper-board (OOS, top50% vs take-all):")
    dr, win, sidx = daily_select(meta, oos, dl, frac=0.5)
    selmask = np.zeros(len(meta), bool); selmask[sidx] = True
    for b in ["主板", "创业", "科创", "北交"]:
        bm = mask & (meta["board"].to_numpy() == b)
        sm = selmask & (meta["board"].to_numpy() == b)
        if bm.sum() == 0: continue
        print(f"  {b:<5} take-all n={int(bm.sum()):>4} ret={ret[bm].mean():+.2f}% win={(ret[bm]>0).mean()*100:.0f}%"
              f"   |  top50 n={int(sm.sum()):>4} ret={ret[sm].mean():+.2f}% win={(ret[sm]>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
