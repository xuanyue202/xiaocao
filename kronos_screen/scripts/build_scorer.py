"""Train & save the deployable two-stage secondary screen.

Stage-2a K: Kronos base emb -> StandardScaler -> PCA(8) -> Ridge  (drop bottom 50%)
Stage-2b P: prior-day intraday features -> GBDT                   (rank survivors)
Both trained on within-day demeaned next-close return over ALL labeled data.
Saves artifacts to kronos_screen/model/ and writes a JSON spec.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingRegressor

DS = Path("kronos_screen/data/ds")
OUT = Path("kronos_screen/model"); OUT.mkdir(parents=True, exist_ok=True)


def main():
    meta = pd.read_parquet(DS / "meta.parquet").reset_index(drop=True)
    z = np.load(DS / "emb_base.npz"); rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(rid2i).to_numpy()]
    pf = pd.read_parquet(DS / "priorday_feats.parquet").set_index("row_id").reindex(meta["row_id"].to_numpy())
    PFEATS = list(pf.columns)
    Xp = np.nan_to_num(pf[PFEATS].to_numpy(np.float32))
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()

    # K
    scaler = StandardScaler().fit(E)
    pca = PCA(8, random_state=0).fit(scaler.transform(E))
    ridgeK = Ridge(alpha=10.0).fit(pca.transform(scaler.transform(E)), tgt)
    # P
    gbdtP = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.05, max_depth=3,
                                          min_samples_leaf=30, l2_regularization=1.0,
                                          random_state=0).fit(Xp, tgt)
    joblib.dump({"scaler": scaler, "pca": pca, "ridge": ridgeK}, OUT / "K_kronos.joblib")
    joblib.dump({"gbdt": gbdtP, "feats": PFEATS}, OUT / "P_priorday.joblib")
    spec = {
        "name": "two-stage secondary screen (K-filter -> P-pick)",
        "stage_2a_K": "Kronos base frozen embedding (last-hidden) -> StandardScaler -> PCA(8) -> Ridge(alpha=10); drop bottom 50% of day's candidates by K-score",
        "stage_2b_P": "prior-day(D-1) intraday features -> HistGBDT; rank survivors, take top N (default 3-4)",
        "P_features": PFEATS,
        "live_inputs": {
            "K": "Kronos base emb of code's daily K-line context (bars < buyDate), via kronos_lib.embed_contexts",
            "P": "minute_line(code, prevTradingDay, count=241) -> build_priorday_feats.feats_from_minutes",
            "optional_live": "stock_call_auction(code, today) imbalance (buyVol2-sellVol2)/pctChange as final tie-break (not backtestable)"
        },
        "validated_oos": {"period": "2025-12-23..2026-05-27", "days": 93,
                          "pipe_top3": {"dayRet%": 1.76, "win%": 57.7, "Sharpe": 5.29, "cum%": 402, "pairedP": 0.017},
                          "take_all": {"dayRet%": 0.847, "win%": 50.8, "Sharpe": 3.04, "cum%": 112},
                          "caveat": "edge concentrated in 主板; main-board-only paired p=0.147 (borderline); robust across N=3-5 and 4/6 months"},
    }
    json.dump(spec, open(OUT / "spec.json", "w"), ensure_ascii=False, indent=2)
    print("saved K_kronos.joblib, P_priorday.joblib, spec.json to", OUT)

    # ---- self-test: reproduce pipeline selection on full sample (sanity, in-sample) ----
    days = meta["buyDate"].to_numpy(); ret = meta["returnPct"].to_numpy()
    K = ridgeK.predict(pca.transform(scaler.transform(E)))
    P = gbdtP.predict(Xp)
    sel = np.zeros(len(meta), bool)
    for d in set(days):
        idx = np.where(days == d)[0]
        if len(idx) == 0: continue
        kk = K[idx]; keep = idx[kk >= np.median(kk)]; keep = keep if len(keep) else idx
        sel[keep[np.argsort(-P[keep])[:min(3, len(keep))]]] = True
    print(f"[in-sample sanity] pipe-top3 ret={ret[sel].mean():+.2f}% win={(ret[sel]>0).mean()*100:.0f}%  vs all {ret.mean():+.2f}%/{(ret>0).mean()*100:.0f}%")


if __name__ == "__main__":
    main()
