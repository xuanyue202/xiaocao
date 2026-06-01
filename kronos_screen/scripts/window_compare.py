"""K->P pipeline vs take-all, win-rate & P&L across 6mo/3mo/1mo/1week windows.

Walk-forward OOS scores (K=Kronos PCA8->Ridge, P=prior-day intraday GBDT),
within-day demeaned target. Pipeline per day: K drops bottom 50% -> P top-N.
Windows end at the last buy date; metrics are per-trade win/avg + daily-
fixed-capital cumulative.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ttest_rel
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor


def wf(meta, X, folds, kind):
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    oos = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 150 or te.sum() < 10:
            continue
        if kind == "ridge":
            sc = StandardScaler().fit(X[tr]); p = PCA(8, random_state=0).fit(sc.transform(X[tr]))
            oos[te] = Ridge(alpha=10).fit(p.transform(sc.transform(X[tr])), tgt[tr]).predict(p.transform(sc.transform(X[te])))
        else:
            m = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, max_depth=3,
                                              min_samples_leaf=30, l2_regularization=1.0, random_state=0)
            oos[te] = m.fit(X[tr], tgt[tr]).predict(X[te])
    return oos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/ds_wide")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / "emb_base.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    pf = pd.read_parquet(ds / "priorday_feats.parquet").set_index("row_id").reindex(meta["row_id"].to_numpy())
    Xp = np.nan_to_num(pf.to_numpy(np.float32))
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()

    uniq = np.array(sorted(set(days)))
    # OOS from ~45% so the 6-month window is covered
    edges = np.linspace(int(len(uniq) * 0.45), len(uniq), 6).astype(int)
    folds = [(uniq[edges[k]], uniq[edges[k + 1] - 1]) for k in range(5)]
    K = wf(meta, E, folds, "ridge"); P = wf(meta, Xp, folds, "gbdt")

    # pipeline selection per day
    sel = np.zeros(len(meta), bool); score_ok = ~np.isnan(K)
    for d in set(days[score_ok]):
        idx = np.where((days == d) & score_ok)[0]
        if len(idx) == 0: continue
        kk = K[idx]; keep = idx[kk >= np.median(kk)]; keep = keep if len(keep) else idx
        sel[keep[np.argsort(-np.nan_to_num(P[keep], nan=-1e9))[:min(a.n, len(keep))]]] = True

    last = uniq[-1]
    wins = {"6月(120d)": uniq[max(0, len(uniq) - 120)], "3月(60d)": uniq[max(0, len(uniq) - 60)],
            "1月(20d)": uniq[max(0, len(uniq) - 20)], "1周(5d)": uniq[max(0, len(uniq) - 5)]}
    print(f"dataset {a.ds}  candidates={len(meta)} ({int(len(meta)/len(uniq))}/day)  OOS scored from {uniq[edges[0]]}\n")
    print(f"{'window':<12}{'takeall n/win/ret':>26}{'PIPE n/win/ret':>26}{'edge%':>8}{'pipe cum%':>10}")
    for label, start in wins.items():
        wm = (days >= start) & score_ok
        if wm.sum() == 0: continue
        ta = ret[wm]; ta_w = (ta > 0).mean() * 100
        sm = wm & sel
        ps = ret[sm]; pw = (ps > 0).mean() * 100
        # daily cumulative for pipeline (fixed capital/day)
        dl = sorted(set(days[sm])); dr = [ret[sm & (days == d)].mean() for d in dl]
        cum = (np.cumprod(1 + np.array(dr) / 100).prod() ** 1 - 1) * 100 if dr else 0
        cum = (np.prod(1 + np.array(dr) / 100) - 1) * 100 if dr else 0
        edge = ps.mean() - ta.mean()
        print(f"{label:<12}{f'{wm.sum()}/{ta_w:.0f}%/{ta.mean():+.2f}%':>26}{f'{sm.sum()}/{pw:.0f}%/{ps.mean():+.2f}%':>26}{edge:>+8.2f}{cum:>+10.0f}")
    # significance over full OOS
    dlo = sorted(set(days[score_ok & (days >= uniq[edges[0]])]))
    pr = [ret[sel & (days == d)].mean() for d in dlo if (sel & (days == d)).sum() > 0]
    ta = [ret[score_ok & (days == d)].mean() for d in dlo]
    # align
    paired = [(ret[sel & (days==d)].mean(), ret[score_ok & (days==d)].mean()) for d in dlo if (sel&(days==d)).sum()>0]
    pa = np.array([x[0] for x in paired]); tb = np.array([x[1] for x in paired])
    print(f"\nfull OOS ({len(paired)} days): PIPE {pa.mean():+.2f}%/d vs take-all {tb.mean():+.2f}%/d  edge {pa.mean()-tb.mean():+.2f}  pairedP={ttest_rel(pa,tb)[1]:.3f}")


if __name__ == "__main__":
    main()
