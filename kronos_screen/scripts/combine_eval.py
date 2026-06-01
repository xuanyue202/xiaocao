"""Build & validate the optimal COMBINED secondary screen.

Component OOS scores (walk-forward, within-day demeaned target):
  K = Kronos base emb (PCA8->Ridge), P = prior-day intraday (GBDT),
  S = structured (GBDT).
Combos use within-day RANK averaging (robust, no extra fitting):
  K+P, K+P+S, and weighted. Reports IC(t,p), daily fixed-capital backtest
  (top3/day & top50%: cum/Sharpe/maxDD/win), per-board, per-month.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp, rankdata
from ceiling_test import fold_bounds
from eval_directions import wf, STRUCT, BOOLS, load_daily_feats


def comp_scores(meta, ds, cache, folds):
    z = np.load(ds / "emb_base.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    Xs = meta[STRUCT].apply(pd.to_numeric, errors="coerce").copy()
    for b in BOOLS:
        Xs[b] = (meta[b].astype(str).str.lower() == "true").astype(float)
    Xs = np.nan_to_num(Xs.to_numpy(np.float32))
    pf = pd.read_parquet(ds / "priorday_feats.parquet").set_index("row_id").reindex(meta["row_id"].to_numpy())
    Xp = np.nan_to_num(pf.to_numpy(np.float32))
    K = wf(meta, lambda: E, folds, "ridge")
    P = wf(meta, lambda: Xp, folds, "gbdt")
    S = wf(meta, lambda: Xs, folds, "gbdt")
    return K, P, S


def day_rank(score, days):
    """within-day percentile rank in [0,1] (nan-safe)."""
    out = np.full(len(score), np.nan)
    for d in set(days[~np.isnan(score)]):
        m = np.where((days == d) & ~np.isnan(score))[0]
        if len(m) == 0: continue
        out[m] = (rankdata(score[m]) - 1) / max(len(m) - 1, 1)
    return out


def equity(daily):
    e = np.cumprod(1 + np.asarray(daily) / 100.0); peak = np.maximum.accumulate(e)
    d = np.asarray(daily)
    return (e[-1] - 1) * 100, (e / peak - 1).min() * 100, d.mean() / (d.std() + 1e-9) * np.sqrt(244)


def evalscore(meta, score, dl, label):
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    ics = []; dr3 = []; dr50 = []; w3 = []
    for d in dl:
        m = days == d
        if m.sum() < 3 or np.all(np.isnan(score[m])): continue
        idx = np.where(m)[0]; s = score[idx]
        if np.std(s[~np.isnan(s)]) == 0: continue
        c = spearmanr(s, ret[idx]).correlation
        if c == c: ics.append(c)
        order = idx[np.argsort(-np.nan_to_num(s, nan=-1e9))]
        k3 = min(3, len(idx)); k50 = max(1, int(round(len(idx) * 0.5)))
        dr3.append(ret[order[:k3]].mean()); dr50.append(ret[order[:k50]].mean())
        w3.append((ret[order[:k3]] > 0).mean())
    ics = np.array(ics); t, p = ttest_1samp(ics, 0)
    c3, d3, s3 = equity(dr3); c50, d50, s50 = equity(dr50)
    print(f"{label:<20}IC={ics.mean():+.3f}(t{t:+.2f},p{p:.3f}) | top3 {np.mean(dr3):+.2f}%/d win{np.mean(w3)*100:.0f}% cum{c3:+.0f}% Sh{s3:.2f} DD{d3:.0f} | top50 {np.mean(dr50):+.2f}%/d cum{c50:+.0f}% Sh{s50:.2f}")
    return np.mean(dr3)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db"); a = ap.parse_args()
    ds = Path(a.ds); meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    _, folds = fold_bounds(meta["buyDate"].to_numpy(), 5, 0.5)
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    K, P, S = comp_scores(meta, ds, a.cache, folds)
    rK, rP, rS = day_rank(K, days), day_rank(P, days), day_rank(S, days)
    dl = sorted(set(days[~np.isnan(K)]))
    ta = np.mean([ret[days == d].mean() for d in dl])
    print(f"OOS days={len(dl)}  take-all daily={ta:+.3f}%\n")
    evalscore(meta, K, dl, "K Kronos")
    evalscore(meta, P, dl, "P priorday")
    evalscore(meta, S, dl, "S structured")
    print("-- combinations (within-day rank-average) --")
    evalscore(meta, rK + rP, dl, "K+P")
    evalscore(meta, rK + rP + rS, dl, "K+P+S")
    evalscore(meta, 2 * rK + rP, dl, "2K+P")
    evalscore(meta, rK + 2 * rP, dl, "K+2P")
    # per-board + per-month for best combo (K+P)
    best = rK + rP
    print("\nper-board (K+P, top3/day vs take-all):")
    sel = np.zeros(len(meta), bool)
    for d in dl:
        idx = np.where(days == d)[0]; k = min(3, len(idx))
        sel[idx[np.argsort(-np.nan_to_num(best[idx], nan=-1e9))[:k]]] = True
    for b in ["主板", "创业", "科创", "北交"]:
        bm = (meta["board"].to_numpy() == b) & (days >= dl[0]); sm = sel & (meta["board"].to_numpy() == b)
        if bm.sum() == 0: continue
        print(f"  {b}: all {ret[bm].mean():+.2f}%/{(ret[bm]>0).mean()*100:.0f}%(n{int(bm.sum())})  sel {ret[sm].mean():+.2f}%/{(ret[sm]>0).mean()*100:.0f}%(n{int(sm.sum())})")
    meta["month"] = meta["buyDate"].str[:7]
    print("per-month (K+P top3 vs take-all):")
    for mo in sorted(set(meta.loc[days>=dl[0], "month"])):
        md = [d for d in dl if d[:7] == mo]
        if not md: continue
        tam = np.mean([ret[days == d].mean() for d in md])
        s3 = []
        for d in md:
            idx = np.where(days == d)[0]; k = min(3, len(idx))
            s3.append(ret[idx[np.argsort(-np.nan_to_num(best[idx], nan=-1e9))[:k]]].mean())
        print(f"  {mo} take-all {tam:+.2f}% K+P-top3 {np.mean(s3):+.2f}% edge {np.mean(s3)-tam:+.2f}%")


if __name__ == "__main__":
    main()
