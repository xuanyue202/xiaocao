"""Probe whether the Kronos embedding carries ANY screening signal when used
well: PCA-reduce (kill the 832-dim curse) + linear/ridge head, walk-forward.
Also a within-fold standardization. If even this shows ~0 IC, the embedding
genuinely lacks secondary-screening signal."""
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


def wf_ic(X, meta, folds, ks=(8, 16, 32), ridge_alpha=10.0, pca=True):
    rets = meta["returnPct"].to_numpy(); dates = meta["buyDate"].to_numpy()
    res = {}
    for k in ks:
        oos = np.full(len(meta), np.nan)
        for (lo, hi) in folds:
            te = (dates >= lo) & (dates <= hi); tr = dates < lo
            if tr.sum() < 100 or te.sum() < 10:
                continue
            sc = StandardScaler().fit(X[tr]); Xtr = sc.transform(X[tr]); Xte = sc.transform(X[te])
            if pca and X.shape[1] > k:
                p = PCA(n_components=k, random_state=0).fit(Xtr)
                Xtr = p.transform(Xtr); Xte = p.transform(Xte)
            m = Ridge(alpha=ridge_alpha).fit(Xtr, rets[tr])
            oos[te] = m.predict(Xte)
        mask = ~np.isnan(oos)
        ic = spearmanr(oos[mask], rets[mask]).correlation
        # top20 selection
        sel = np.zeros(len(meta), bool)
        for (lo, hi) in folds:
            te = (dates >= lo) & (dates <= hi) & mask
            idx = np.where(te)[0]
            if len(idx) == 0: continue
            sel[idx[np.argsort(-oos[idx])[:max(1, int(len(idx)*0.2))]]] = True
        res[k] = (ic, rets[sel].mean(), (rets[sel] > 0).mean()*100, int(sel.sum()))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--emb", default="base")
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz"); emb = z["emb"]; rids = z["row_ids"]
    rid2i = {int(r): i for i, r in enumerate(rids)}
    E = emb[meta["row_id"].map(rid2i).to_numpy()]
    struct = make_struct(meta).to_numpy(dtype=np.float32)
    struct = np.nan_to_num(struct)
    _, folds = fold_bounds(meta["buyDate"].to_numpy(), 5, 0.5)
    base = meta.loc[meta["buyDate"] >= folds[0][0], "returnPct"]
    print(f"baseline OOS ret {base.mean():+.3f}% win {(base>0).mean()*100:.1f}%  n={len(base)}\n")
    print(f"{'feature':<18}{'k':>4}{'IC':>8}{'top20 ret':>11}{'top20 win':>11}{'n':>6}")
    for name, X in [(f"emb-{a.emb}", E), ("struct", struct), ("hybrid", np.hstack([struct, E]))]:
        r = wf_ic(X, meta, folds)
        for k, (ic, ret, win, n) in r.items():
            print(f"{name:<18}{k:>4}{ic:>8.3f}{ret:>+11.2f}{win:>10.0f}%{n:>6}")


if __name__ == "__main__":
    main()
