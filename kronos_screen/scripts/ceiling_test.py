"""Walk-forward ceiling test: does a Kronos embedding add screening signal?

Compares 4 feature sets with purged expanding-window time folds:
  A. take-all        (no model) -> the current secondary screen's OOS return
  B. structured-only HGB
  C. embedding-only  HGB
  D. hybrid (struct + embedding) HGB

Target = returnPct (regression). Within each OOS fold we rank candidates by
predicted return and measure the realized avg return / win of the selected
top-K subset, plus rank-IC and win-AUC. The model earns its keep only if it
lifts OOS return above take-all *consistently across folds*.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score

# decision-time-available structured features (no same-day breadth leak)
NUM_FEATS = ["xcjw", "cjs", "jsjl", "jssb", "openPctChange",
             "directionRank", "categoryRank", "n_blocks", "n_cats"]
CAT_FEATS = ["mode", "board", "excIndustry"]
BOOL_FEATS = ["isMainLine", "isBigCap", "direction"]


def make_struct(meta: pd.DataFrame) -> pd.DataFrame:
    X = meta[NUM_FEATS].apply(pd.to_numeric, errors="coerce").copy()
    for b in BOOL_FEATS:
        X[b] = (meta[b].astype(str).str.lower() == "true").astype(float)
    dummies = pd.get_dummies(meta[CAT_FEATS].astype(str), prefix=CAT_FEATS)
    return pd.concat([X.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)


def fold_bounds(dates: np.ndarray, n_folds: int, start_frac: float):
    uniq = np.array(sorted(set(dates)))
    n = len(uniq)
    start = int(n * start_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    return uniq, [(uniq[edges[k]], uniq[edges[k + 1] - 1]) for k in range(n_folds)]


def hgb():
    return HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_depth=3,
        min_samples_leaf=30, l2_regularization=1.0, random_state=0)


def eval_set(name, Xall, meta, folds, topk_fracs):
    rets = meta["returnPct"].to_numpy()
    wins = meta["win"].to_numpy()
    dates = meta["buyDate"].to_numpy()
    oos_pred = np.full(len(meta), np.nan)
    per_fold = []
    for (lo, hi) in folds:
        te = (dates >= lo) & (dates <= hi)
        tr = dates < lo  # expanding; embargo: strictly-before day (label is next-close)
        if tr.sum() < 100 or te.sum() < 10:
            continue
        if Xall is None:  # take-all baseline: no model, score=0
            oos_pred[te] = 0.0
            per_fold.append((lo, hi, te.sum(), np.nan, rets[te].mean(), wins[te].mean()))
            continue
        m = hgb().fit(Xall[tr], rets[tr])
        p = m.predict(Xall[te])
        oos_pred[te] = p
        ic = spearmanr(p, rets[te]).correlation
        per_fold.append((lo, hi, te.sum(), ic, rets[te].mean(), wins[te].mean()))
    mask = ~np.isnan(oos_pred)
    out = {"name": name, "n_oos": int(mask.sum()),
           "baseline_ret": float(rets[mask].mean()), "baseline_win": float(wins[mask].mean() * 100)}
    if Xall is not None:
        ic_all = spearmanr(oos_pred[mask], rets[mask]).correlation
        try:
            auc = roc_auc_score(wins[mask], oos_pred[mask])
        except ValueError:
            auc = np.nan
        out["IC"] = ic_all; out["AUC"] = auc
        out["fold_ICs"] = [round(f[3], 3) for f in per_fold if f[3] == f[3]]
        # top-K selection within each fold
        for frac in topk_fracs:
            sel = np.zeros(len(meta), dtype=bool)
            for (lo, hi) in folds:
                te = (dates >= lo) & (dates <= hi) & mask
                if te.sum() == 0:
                    continue
                idx = np.where(te)[0]
                k = max(1, int(len(idx) * frac))
                top = idx[np.argsort(-oos_pred[idx])[:k]]
                sel[top] = True
            out[f"top{int(frac*100)}_ret"] = float(rets[sel].mean())
            out[f"top{int(frac*100)}_win"] = float(wins[sel].mean() * 100)
            out[f"top{int(frac*100)}_n"] = int(sel.sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--emb", default="base", choices=["mini", "small", "base"])
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--start-frac", type=float, default=0.5)
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz")
    emb = z["emb"]; emb_rids = z["row_ids"]
    # align embeddings to meta by row_id
    rid2i = {int(r): i for i, r in enumerate(emb_rids)}
    order = meta["row_id"].map(rid2i).to_numpy()
    assert not np.isnan(order.astype(float)).any(), "row_id mismatch"
    E = emb[order]

    struct = make_struct(meta).to_numpy(dtype=np.float32)
    uniq, folds = fold_bounds(meta["buyDate"].to_numpy(), a.n_folds, a.start_frac)
    print(f"n={len(meta)} feats struct={struct.shape[1]} emb={E.shape[1]} folds={len(folds)} "
          f"OOS dates {folds[0][0]}..{folds[-1][1]}", flush=True)

    topk = [0.5, 0.3, 0.2]
    configs = [("A take-all", None),
               ("B struct", struct),
               (f"C emb-{a.emb}", E),
               (f"D hybrid", np.hstack([struct, E]))]
    rows = [eval_set(n, X, meta, folds, topk) for n, X in configs]

    base_ret = rows[0]["baseline_ret"]; base_win = rows[0]["baseline_win"]
    print(f"\nOOS take-all baseline: ret={base_ret:+.3f}%  win={base_win:.1f}%  (n={rows[0]['n_oos']})")
    print(f"\n{'config':<14}{'IC':>7}{'AUC':>7}{'top50 ret/win':>18}{'top30 ret/win':>18}{'top20 ret/win':>18}")
    for r in rows[1:]:
        def cell(f): return f"{r[f'top{f}_ret']:+.2f}/{r[f'top{f}_win']:.0f}%"
        print(f"{r['name']:<14}{r.get('IC',float('nan')):>7.3f}{r.get('AUC',float('nan')):>7.3f}"
              f"{cell(50):>18}{cell(30):>18}{cell(20):>18}")
    print("\nper-fold ICs:")
    for r in rows[1:]:
        print(f"  {r['name']:<14}{r.get('fold_ICs')}")


if __name__ == "__main__":
    main()
