"""Try many secondary-screen signal directions, evaluate each walk-forward on
real OOS data, rank by return, and report the top-3 + a combined model.

Directions (each -> a within-day score, target = within-day demeaned next-close):
  K  Kronos base embedding (PCA8 -> Ridge)
  P  prior-day intraday microstructure (minute-derived; GBDT)
  S  xiaocao structured features (xcjw/cjs/jsjl/ranks; GBDT)
  D  prior-day DAILY bar features (ret/turnover/volRatio; GBDT)
  T  trivial factors (momentum/reversal/vol; Ridge)
  C  combined ALL features (GBDT)

Metrics per direction (walk-forward, expanding folds, OOS 2nd half):
  within-day IC (mean,t,p) ; daily top-3/day and top-50% next-close return.
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
from sklearn.ensemble import HistGradientBoostingRegressor
from ceiling_test import fold_bounds
from xiaocao.api.cache import iter_cached_responses

STRUCT = ["xcjw", "cjs", "jsjl", "jssb", "openPctChange", "directionRank",
          "categoryRank", "n_blocks", "n_cats"]
BOOLS = ["isMainLine", "isBigCap", "direction"]


def load_daily_feats(meta, cache):
    """prior-day daily-bar features from date_kline (decision-time safe)."""
    by = {}
    for data in iter_cached_responses(cache, "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("code") and k.get("tradeDate"):
                    by.setdefault(k["code"], {})[k["tradeDate"]] = k
    feats = []
    for r in meta.itertuples():
        days = by.get(r.code, {})
        ds = sorted(d for d in days if d < r.buyDate)
        if not ds:
            feats.append({}); continue
        p = days[ds[-1]]
        feats.append({
            "d_pctchg": p.get("pctChangeRate"), "d_turn": p.get("turnoverRatio"),
            "d_volratio": p.get("volRatio"),
            "d_amt": np.log((p.get("amt") or 0) + 1),
            "d_limitup": 1.0 if p.get("isLimitUp") else 0.0,
        })
    return pd.DataFrame(feats)


def hgb():
    return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, max_depth=3,
                                         min_samples_leaf=30, l2_regularization=1.0, random_state=0)


def wf(meta, build_X, folds, kind="gbdt"):
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    oos = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi); tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        X = build_X()
        if kind == "ridge":
            sc = StandardScaler().fit(X[tr]); Xtr = sc.transform(X[tr]); Xte = sc.transform(X[te])
            if X.shape[1] > 8:
                p = PCA(8, random_state=0).fit(Xtr); Xtr, Xte = p.transform(Xtr), p.transform(Xte)
            oos[te] = Ridge(alpha=10.0).fit(Xtr, tgt[tr]).predict(Xte)
        else:
            oos[te] = hgb().fit(X[tr], tgt[tr]).predict(X[te])
    return oos


def metrics(meta, oos):
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    mask = ~np.isnan(oos); dl = sorted(set(days[mask]))
    ics, t3, t50 = [], [], []
    for d in dl:
        m = days == d
        if m.sum() < 3 or np.std(oos[m]) == 0:
            continue
        c = spearmanr(oos[m], ret[m]).correlation
        if c == c: ics.append(c)
        idx = np.where(m)[0]
        k3 = min(3, len(idx)); k50 = max(1, int(round(len(idx) * 0.5)))
        order = idx[np.argsort(-oos[idx])]
        t3.append(ret[order[:k3]].mean()); t50.append(ret[order[:k50]].mean())
    ics = np.array(ics); tt, pp = ttest_1samp(ics, 0.0)
    return {"IC": ics.mean(), "t": tt, "p": pp, "top3": np.mean(t3), "top50": np.mean(t50),
            "ndays": len(ics)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / "emb_base.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    _, folds = fold_bounds(meta["buyDate"].to_numpy(), 5, 0.5)

    # structured
    Xs = meta[STRUCT].apply(pd.to_numeric, errors="coerce").copy()
    for b in BOOLS:
        Xs[b] = (meta[b].astype(str).str.lower() == "true").astype(float)
    Xs = Xs.to_numpy(np.float32)
    # daily
    Xd = load_daily_feats(meta, a.cache).apply(pd.to_numeric, errors="coerce").to_numpy(np.float32)
    # trivial
    def fac(fn): return np.array([fn(z) for z in E])  # placeholder; trivial uses daily
    # prior-day intraday (if available)
    pf_path = ds / "priorday_feats.parquet"
    Xp = None; pcols = []
    if pf_path.exists():
        pf = pd.read_parquet(pf_path).set_index("row_id")
        pf = pf.reindex(meta["row_id"].to_numpy())
        pcols = list(pf.columns); Xp = pf.to_numpy(np.float32)

    dirs = {
        "K Kronos-emb": (lambda: E, "ridge"),
        "S structured": (lambda: np.nan_to_num(Xs), "gbdt"),
        "D daily-bar":  (lambda: np.nan_to_num(Xd), "gbdt"),
    }
    if Xp is not None:
        dirs["P priorday-intraday"] = (lambda: np.nan_to_num(Xp), "gbdt")
        dirs["C combined-all"] = (lambda: np.nan_to_num(np.hstack([Xs, Xd, Xp,
                                  PCA(8, random_state=0).fit_transform(StandardScaler().fit_transform(E))])), "gbdt")

    # take-all baseline
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    oosmask = days >= folds[0][0]; dl = sorted(set(days[oosmask]))
    ta3 = np.mean([ret[days == d][np.argsort(np.zeros((days == d).sum()))][:3].mean() if (days==d).sum()>0 else 0 for d in dl])
    ta = np.mean([ret[days == d].mean() for d in dl])
    print(f"OOS days={len(dl)}  take-all daily ret={ta:+.3f}%  (Xp={'yes' if Xp is not None else 'NO-still-fetching'}, pcols={pcols})\n")
    print(f"{'direction':<22}{'IC':>8}{'t':>6}{'p':>7}{'top3%':>8}{'top50%':>8}{'ndays':>7}")
    res = {}
    for nm, (bx, kind) in dirs.items():
        oos = wf(meta, bx, folds, kind)
        m = metrics(meta, oos); res[nm] = m
        print(f"{nm:<22}{m['IC']:>8.3f}{m['t']:>6.2f}{m['p']:>7.3f}{m['top3']:>+8.2f}{m['top50']:>+8.2f}{m['ndays']:>7}")
    print(f"\ntake-all daily ret = {ta:+.3f}%")
    rank = sorted(res.items(), key=lambda kv: -kv[1]["top3"])
    print("\nTOP-3 directions by top3/day return:")
    for nm, m in rank[:3]:
        print(f"  {nm}: top3 {m['top3']:+.2f}%  top50 {m['top50']:+.2f}%  IC {m['IC']:+.3f} (p={m['p']:.3f})")


if __name__ == "__main__":
    main()
