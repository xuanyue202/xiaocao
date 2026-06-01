"""Principled two-signal secondary screen (no OOS weight cherry-picking):
  Pipeline: K (Kronos) drops the worst half of each day's candidates, then
  P (prior-day intraday) ranks the survivors; take top-N.
Compared to each single signal and take-all, with per-month robustness and a
paired significance test on the daily edge. Saves OOS component scores."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_rel
from ceiling_test import fold_bounds
from combine_eval import comp_scores, day_rank, equity


def select(meta, days, ret, dl, scorer, n=3):
    sel = np.zeros(len(meta), bool); dr, dw = [], []
    for d in dl:
        idx = np.where(days == d)[0]
        chosen = scorer(idx)
        if len(chosen) == 0: continue
        sel[chosen] = True; dr.append(ret[chosen].mean()); dw.append((ret[chosen] > 0).mean())
    return np.array(dr), np.mean(dw) * 100, sel


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db"); ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    ds = Path(a.ds); meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    _, folds = fold_bounds(meta["buyDate"].to_numpy(), 5, 0.5)
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    K, P, S = comp_scores(meta, ds, a.cache, folds)
    np.savez(ds / "oos_components.npz", K=K, P=P, S=S, row_id=meta["row_id"].to_numpy())
    rK, rP = day_rank(K, days), day_rank(P, days)
    dl = sorted(set(days[~np.isnan(K)]))
    ta = np.array([ret[days == d].mean() for d in dl])

    def topn(score, n):
        return lambda idx: idx[np.argsort(-np.nan_to_num(score[idx], nan=-1e9))[:min(n, len(idx))]]

    def pipe(n):  # K drops bottom half, P picks top-n among survivors
        def f(idx):
            if len(idx) == 0: return idx
            keep = idx[np.nan_to_num(rK[idx], nan=-1) >= np.median(np.nan_to_num(rK[idx], nan=-1))]
            keep = keep if len(keep) else idx
            return keep[np.argsort(-np.nan_to_num(P[keep], nan=-1e9))[:min(n, len(keep))]]
        return f

    print(f"OOS days={len(dl)}  take-all daily={ta.mean():+.3f}%  win={np.mean([(ret[days==d]>0).mean() for d in dl])*100:.1f}%\n")
    print(f"{'strategy':<26}{'dayRet%':>9}{'win%':>7}{'cum%':>8}{'Sharpe':>8}{'maxDD':>7}{'pairP':>8}")
    strategies = {
        f"take-all": None,
        f"K top{a.n}": topn(K, a.n), f"P top{a.n}": topn(P, a.n),
        f"K+P rank top{a.n}": topn(rK + rP, a.n),
        f"PIPE K50->P top{a.n}": pipe(a.n),
        f"K top50%": (lambda idx: idx[np.argsort(-np.nan_to_num(K[idx], nan=-1e9))[:max(1, len(idx)//2)]]),
        f"K+P rank top50%": (lambda idx: idx[np.argsort(-np.nan_to_num((rK+rP)[idx], nan=-1e9))[:max(1, len(idx)//2)]]),
    }
    best = None
    for nm, sc in strategies.items():
        if sc is None:
            dr = ta; w = np.mean([(ret[days==d]>0).mean() for d in dl])*100
        else:
            dr, w, _ = select(meta, days, ret, dl, sc)
        cum, dd, sh = equity(dr)
        p = ttest_rel(dr, ta)[1] if sc is not None and len(dr) == len(ta) else np.nan
        print(f"{nm:<26}{dr.mean():>+9.3f}{w:>7.1f}{cum:>+8.0f}{sh:>8.2f}{dd:>7.0f}{p:>8.3f}")

    # per-month for the pipeline
    meta["month"] = meta["buyDate"].str[:7]
    print(f"\nper-month edge (PIPE K50->P top{a.n} vs take-all):")
    pos = 0; tot = 0
    for mo in sorted(set(meta.loc[days >= dl[0], "month"])):
        md = [d for d in dl if d[:7] == mo]
        if not md: continue
        tam = np.mean([ret[days == d].mean() for d in md])
        dr, _, _ = select(meta, days, ret, md, pipe(a.n))
        edge = dr.mean() - tam; pos += edge > 0; tot += 1
        print(f"  {mo} take-all {tam:+.2f}% pipe {dr.mean():+.2f}% edge {edge:+.2f}%")
    print(f"  months with positive edge: {pos}/{tot}")


if __name__ == "__main__":
    main()
