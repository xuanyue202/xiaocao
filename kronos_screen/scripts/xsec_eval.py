"""Cross-sectional (within-day) evaluation — the screen's real job is to pick
the best AMONG each day's candidates, not to time the market. Predicting
absolute return mostly predicts the market-day common factor (noise for
selection). So:
  target  = within-day demeaned return (returnPct - that day's mean)
  metric  = within-day rank-IC (mean over days), and a daily top-K portfolio
            (each day take top frac of candidates, equal weight) vs take-all.
Embedding is PCA-reduced per-fold (fit on train) to kill the 832-dim curse.
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
from ceiling_test import make_struct, fold_bounds


def within_day_ic(pred, ret, days, day_list):
    ics = []
    for d in day_list:
        m = days == d
        if m.sum() >= 3 and np.std(pred[m]) > 0:
            c = spearmanr(pred[m], ret[m]).correlation
            if c == c:
                ics.append(c)
    return float(np.mean(ics)) if ics else np.nan, len(ics)


def daily_topk(pred, ret, days, day_list, frac):
    """Mean over days of the top-frac candidates' realized return."""
    day_rets, sel_n = [], 0
    for d in day_list:
        m = np.where(days == d)[0]
        if len(m) == 0:
            continue
        k = max(1, int(round(len(m) * frac)))
        top = m[np.argsort(-pred[m])[:k]]
        day_rets.append(ret[top].mean()); sel_n += k
    return float(np.mean(day_rets)), sel_n, float(np.mean([(ret[np.where(days==d)[0][np.argsort(-pred[np.where(days==d)[0]])[:max(1,int(round((days==d).sum()*frac)))]]] > 0).mean() for d in day_list]))*100


def run(X, meta, folds, name, pca_k=8):
    ret = meta["returnPct"].to_numpy()
    days = meta["buyDate"].to_numpy()
    # within-day demeaned target
    dmean = meta.groupby("buyDate")["returnPct"].transform("mean").to_numpy()
    tgt = ret - dmean
    oos = np.full(len(meta), np.nan)
    for (lo, hi) in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        sc = StandardScaler().fit(X[tr]); Xtr = sc.transform(X[tr]); Xte = sc.transform(X[te])
        if X.shape[1] > pca_k:
            p = PCA(n_components=pca_k, random_state=0).fit(Xtr)
            Xtr, Xte = p.transform(Xtr), p.transform(Xte)
        m = Ridge(alpha=10.0).fit(Xtr, tgt[tr])
        oos[te] = m.predict(Xte)
    mask = ~np.isnan(oos)
    dl = sorted(set(days[mask]))
    ic, nday = within_day_ic(oos[mask], ret[mask], days[mask], dl)
    out = {"name": name, "wIC": ic, "ndays": nday}
    for frac in (0.5, 0.34, 0.25):
        r, n, w = daily_topk(oos, ret, days, dl, frac)
        out[f"top{int(frac*100)}"] = (r, w)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--emb", default="base")
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    struct = np.nan_to_num(make_struct(meta).to_numpy(dtype=np.float32))
    _, folds = fold_bounds(meta["buyDate"].to_numpy(), 5, 0.5)

    days = meta["buyDate"].to_numpy()
    oosm = days >= folds[0][0]
    dl = sorted(set(days[oosm]))
    # take-all daily baseline
    base = float(np.mean([meta.loc[meta.buyDate == d, "returnPct"].mean() for d in dl]))
    bwin = float(np.mean([(meta.loc[meta.buyDate == d, "returnPct"] > 0).mean() for d in dl])) * 100
    print(f"OOS days={len(dl)}  take-all daily ret={base:+.3f}% win={bwin:.1f}%\n")
    print(f"{'config':<16}{'wIC':>8}{'top50 r/w':>16}{'top34 r/w':>16}{'top25 r/w':>16}")
    for nm, X in [(f"emb-{a.emb}", E), ("struct", struct), ("hybrid", np.hstack([struct, E]))]:
        o = run(X, meta, folds, nm)
        def c(f): return f"{o[f'top{f}'][0]:+.2f}/{o[f'top{f}'][1]:.0f}%"
        print(f"{nm:<16}{o['wIC']:>8.3f}{c(50):>16}{c(34):>16}{c(25):>16}")


if __name__ == "__main__":
    main()
