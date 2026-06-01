"""Robustness of the within-day embedding screen: per-fold wIC and per-month
top-50% portfolio return vs take-all. Compares mini/small/base."""
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


def oos_scores(X, meta, folds, pca_k=8, alpha=10.0):
    ret = meta["returnPct"].to_numpy(); days = meta["buyDate"].to_numpy()
    tgt = ret - meta.groupby("buyDate")["returnPct"].transform("mean").to_numpy()
    oos = np.full(len(meta), np.nan)
    for (lo, hi) in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        sc = StandardScaler().fit(X[tr])
        Xtr, Xte = sc.transform(X[tr]), sc.transform(X[te])
        if X.shape[1] > pca_k:
            p = PCA(pca_k, random_state=0).fit(Xtr); Xtr, Xte = p.transform(Xtr), p.transform(Xte)
        oos[te] = Ridge(alpha=alpha).fit(Xtr, tgt[tr]).predict(Xte)
    return oos


def day_ic(pred, ret, days, dl):
    out = []
    for d in dl:
        m = days == d
        if m.sum() >= 3 and np.std(pred[m]) > 0:
            c = spearmanr(pred[m], ret[m]).correlation
            if c == c: out.append(c)
    return np.mean(out) if out else np.nan


def top_ret(pred, ret, days, dl, frac=0.5):
    rr = []
    for d in dl:
        m = np.where(days == d)[0]
        k = max(1, int(round(len(m) * frac)))
        rr.append(ret[m[np.argsort(-pred[m])[:k]]].mean())
    return np.mean(rr)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ds", required=True); a = ap.parse_args()
    ds = Path(a.ds); meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    ret = meta["returnPct"].to_numpy(); days = meta["buyDate"].to_numpy()
    _, folds = fold_bounds(days, 5, 0.5)
    dl_all = sorted(set(days[days >= folds[0][0]]))
    meta["month"] = meta["buyDate"].str[:7]

    for size in ["mini", "small", "base"]:
        z = np.load(ds / f"emb_{size}.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
        E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
        oos = oos_scores(E, meta, folds)
        mask = ~np.isnan(oos)
        # per-fold wIC
        fics = []
        for (lo, hi) in folds:
            te = mask & (days >= lo) & (days <= hi)
            dl = sorted(set(days[te]))
            if dl: fics.append(day_ic(oos[te], ret[te], days[te], dl))
        pooled = day_ic(oos[mask], ret[mask], days[mask], dl_all)
        print(f"\n=== {size}  pooled wIC={pooled:.3f}  per-fold wIC={[round(f,3) for f in fics]}")
        # per-month top50 vs take-all
        print(f"  {'month':<9}{'n':>4}{'takeall':>9}{'top50':>9}{'edge':>8}")
        for mo in sorted(meta.loc[mask, "month"].unique()):
            mm = mask & (meta["month"].to_numpy() == mo)
            dl = sorted(set(days[mm]))
            if not dl: continue
            ta = np.mean([ret[(days == d)].mean() for d in dl])
            tp = top_ret(oos, ret, days, dl, 0.5)
            print(f"  {mo:<9}{int(mm.sum()):>4}{ta:>+9.2f}{tp:>+9.2f}{tp-ta:>+8.2f}")


if __name__ == "__main__":
    main()
