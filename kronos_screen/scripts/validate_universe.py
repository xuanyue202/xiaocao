"""High-power within-day IC validation of the frozen-base Kronos ranker on the
broad cached universe (~400 names/day). Walk-forward, PCA8+Ridge on within-day
demeaned next-close return. Reports OOS within-day IC with t-test (many names/
day => tight estimate) and a top-decile vs bottom-decile spread."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/uni")
    ap.add_argument("--emb", default="base")
    ap.add_argument("--start-frac", type=float, default=0.5)
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{a.emb}.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()

    uniq = np.array(sorted(set(days)))
    start = int(len(uniq) * a.start_frac)
    test_days = uniq[start:]
    oos = np.full(len(meta), np.nan)
    for d in test_days:
        tr = days < d  # expanding, strictly prior days (no same-day leak)
        te = days == d
        if tr.sum() < 500:
            continue
        sc = StandardScaler().fit(E[tr]); p = PCA(8, random_state=0).fit(sc.transform(E[tr]))
        oos[te] = Ridge(alpha=10.0).fit(p.transform(sc.transform(E[tr])), tgt[tr]).predict(p.transform(sc.transform(E[te])))
    mask = ~np.isnan(oos); dl = sorted(set(days[mask]))

    dic, spreads = [], []
    for d in dl:
        m = days == d
        if m.sum() < 20 or np.std(oos[m]) == 0:
            continue
        dic.append(spearmanr(oos[m], ret[m]).correlation)
        idx = np.where(m)[0]; k = max(1, int(len(idx) * 0.1))
        top = idx[np.argsort(-oos[idx])[:k]]; bot = idx[np.argsort(oos[idx])[:k]]
        spreads.append(ret[top].mean() - ret[bot].mean())
    dic = np.array(dic); spreads = np.array(spreads)
    t, p = ttest_1samp(dic, 0.0); ts, ps = ttest_1samp(spreads, 0.0)
    print(f"==== BROAD-UNIVERSE VALIDATION (emb={a.emb}) ====")
    print(f"OOS test-days={len(dl)}  avg names/day={int(mask.sum()/len(dl))}  total rows={int(mask.sum())}")
    print(f"within-day IC: mean={dic.mean():.4f}  std={dic.std():.3f}  t={t:.2f}  p={p:.5f}  %days>0={(dic>0).mean()*100:.0f}%")
    print(f"top10%-bottom10% next-close spread: mean={spreads.mean():+.3f}%/day  t={ts:.2f}  p={ps:.5f}  %days>0={(spreads>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
