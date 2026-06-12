"""Random 150/50 day validation for secondary-screen ideas.

This is an offline experiment only; it does not change live trading. For each
seed, randomly choose 150 buy dates for training and 50 for validation, then
compare:

  - take-all
  - P-only topN
  - current PIPE: K median -> P topN
  - soft K+P rank topN
  - tail-veto: train a bottom-30% risk model, veto high-risk names, then P topN

The tail-veto model is trained from cross-fitted train-day K/P scores so the
gate does not learn from fully in-sample K/P predictions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, ttest_rel
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


STRUCT_NUM = [
    "xcjw", "cjs", "jsjl", "jssb", "openPctChange",
    "directionRank", "categoryRank", "n_blocks", "n_cats",
]
STRUCT_BOOL = ["isMainLine", "isBigCap", "direction", "is_main_line"]
STRUCT_CAT = ["mode", "board"]


def primary_score(meta: pd.DataFrame) -> np.ndarray:
    mode = meta["mode"].astype(str)
    xcjw = pd.to_numeric(meta.get("xcjw"), errors="coerce").fillna(0).to_numpy(float)
    cjs = pd.to_numeric(meta.get("cjs"), errors="coerce").fillna(0).to_numpy(float)
    jsjl = pd.to_numeric(meta.get("jsjl"), errors="coerce").fillna(0).to_numpy(float)
    jssb = pd.to_numeric(meta.get("jssb"), errors="coerce").fillna(0).to_numpy(float)
    out = xcjw + cjs * 0.8
    qibao = mode.str.contains("起爆", na=False).to_numpy()
    jieli = mode.str.startswith("接力", na=False).to_numpy()
    nshape = mode.isin(["N字低吸", "孕线低吸"]).to_numpy()
    out[qibao] = jssb[qibao]
    out[jieli] = xcjw[jieli] + np.maximum(jsjl[jieli], 0) * 0.5
    out[nshape] = xcjw[nshape] + cjs[nshape] * 0.6
    return out


def load_data(ds: Path, emb: str) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / f"emb_{emb}.npz")
    rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    order = meta["row_id"].map(rid2i).to_numpy()
    if pd.isna(order).any():
        raise ValueError("embedding row_id mismatch")
    E = z["emb"][order.astype(int)]
    pf = pd.read_parquet(ds / "priorday_feats.parquet").set_index("row_id")
    Xp = np.nan_to_num(pf.reindex(meta["row_id"].to_numpy()).to_numpy(np.float32))
    return meta, E, Xp


def day_demeaned_target(meta: pd.DataFrame) -> np.ndarray:
    return (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy(float)


def fit_predict_kp(
    meta: pd.DataFrame,
    E: np.ndarray,
    Xp: np.ndarray,
    train_mask: np.ndarray,
    pred_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    tgt = day_demeaned_target(meta)
    sc = StandardScaler().fit(E[train_mask])
    Xtr = sc.transform(E[train_mask])
    Xte = sc.transform(E[pred_mask])
    pca = PCA(8, random_state=0).fit(Xtr)
    k_model = Ridge(alpha=10.0).fit(pca.transform(Xtr), tgt[train_mask])
    K = np.full(len(meta), np.nan)
    K[pred_mask] = k_model.predict(pca.transform(Xte))

    p_model = HistGradientBoostingRegressor(
        max_iter=250,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=30,
        l2_regularization=1.0,
        random_state=0,
    ).fit(Xp[train_mask], tgt[train_mask])
    P = np.full(len(meta), np.nan)
    P[pred_mask] = p_model.predict(Xp[pred_mask])
    return K, P


def crossfit_train_scores(
    meta: pd.DataFrame,
    E: np.ndarray,
    Xp: np.ndarray,
    train_days: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    days = np.array(train_days)
    rng.shuffle(days)
    folds = np.array_split(days, 5)
    K = np.full(len(meta), np.nan)
    P = np.full(len(meta), np.nan)
    all_days = meta["buyDate"].to_numpy()
    for fold in folds:
        pred_mask = np.isin(all_days, fold)
        sub_train_mask = np.isin(all_days, np.setdiff1d(train_days, fold))
        if sub_train_mask.sum() < 100 or pred_mask.sum() == 0:
            continue
        k, p = fit_predict_kp(meta, E, Xp, sub_train_mask, pred_mask)
        K[pred_mask] = k[pred_mask]
        P[pred_mask] = p[pred_mask]
    return K, P


def day_rank(vals: np.ndarray, days: np.ndarray) -> np.ndarray:
    out = np.full(len(vals), np.nan)
    for d in sorted(set(days)):
        idx = np.where(days == d)[0]
        valid = idx[~np.isnan(vals[idx])]
        if len(valid) == 1:
            out[valid] = 0.5
        elif len(valid) > 1:
            out[valid] = (rankdata(vals[valid]) - 1) / (len(valid) - 1)
    return out


def _rank_values(vals: np.ndarray) -> np.ndarray:
    out = np.full(len(vals), np.nan)
    valid = ~np.isnan(vals)
    if valid.sum() == 1:
        out[valid] = 0.5
    elif valid.sum() > 1:
        out[valid] = (rankdata(vals[valid]) - 1) / (valid.sum() - 1)
    return out


def bottom_label(meta: pd.DataFrame, train_mask: np.ndarray, q: float = 0.30) -> np.ndarray:
    ret = meta["returnPct"].to_numpy(float)
    days = meta["buyDate"].to_numpy()
    y = np.zeros(len(meta), dtype=int)
    for d in sorted(set(days[train_mask])):
        idx = np.where(train_mask & (days == d))[0]
        if len(idx) < 3:
            continue
        cutoff = np.quantile(ret[idx], q)
        y[idx] = ret[idx] <= cutoff
    return y


def struct_frame(meta: pd.DataFrame) -> pd.DataFrame:
    X = meta[[c for c in STRUCT_NUM if c in meta.columns]].apply(pd.to_numeric, errors="coerce")
    for c in STRUCT_BOOL:
        if c in meta.columns:
            X[c] = meta[c].astype(str).str.lower().isin(["true", "1"]).astype(float)
    X["primary_score"] = primary_score(meta)
    X["candidate_n"] = meta.groupby("buyDate")["code"].transform("size").astype(float)
    X["open_bucket_code"] = pd.cut(
        pd.to_numeric(meta["openPctChange"], errors="coerce"),
        bins=[-100, -6, -3, 0, 3, 100],
        labels=[0, 1, 2, 3, 4],
    ).astype(float)
    dummies = pd.get_dummies(meta[[c for c in STRUCT_CAT if c in meta.columns]].astype(str), prefix=STRUCT_CAT)
    return pd.concat([X.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1).fillna(0.0)


def gate_features(meta: pd.DataFrame, K: np.ndarray, P: np.ndarray) -> pd.DataFrame:
    days = meta["buyDate"].to_numpy()
    rK = day_rank(K, days)
    rP = day_rank(P, days)
    X = struct_frame(meta)
    X["k_score"] = np.nan_to_num(K, nan=0.0)
    X["p_score"] = np.nan_to_num(P, nan=0.0)
    X["k_rank"] = np.nan_to_num(rK, nan=0.5)
    X["p_rank"] = np.nan_to_num(rP, nan=0.5)
    X["rank_gap_p_minus_k"] = X["p_rank"] - X["k_rank"]
    return X


def train_gate(
    meta: pd.DataFrame,
    K_oof: np.ndarray,
    P_oof: np.ndarray,
    train_mask: np.ndarray,
    seed: int,
) -> HistGradientBoostingClassifier:
    X = gate_features(meta, K_oof, P_oof)
    y = bottom_label(meta, train_mask)
    mask = train_mask & ~np.isnan(K_oof) & ~np.isnan(P_oof)
    return HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.05,
        max_depth=3,
        min_samples_leaf=25,
        l2_regularization=1.0,
        random_state=seed,
    ).fit(X.loc[mask].to_numpy(np.float32), y[mask])


def choose_by_strategy(
    idx: np.ndarray,
    K: np.ndarray,
    P: np.ndarray,
    risk: np.ndarray,
    strategy: str,
    top_n: int,
    risk_threshold: float,
) -> np.ndarray:
    if len(idx) == 0:
        return idx
    if strategy == "p_only":
        pool = idx
        score = P
    elif strategy == "pipe":
        keep = idx[np.nan_to_num(K[idx], nan=-1e9) >= np.median(np.nan_to_num(K[idx], nan=-1e9))]
        pool = keep if len(keep) else idx
        score = P
    elif strategy == "soft_kp":
        pool = idx
        score = np.full(len(K), np.nan)
        score[idx] = np.nan_to_num(_rank_values(K[idx]), nan=0.5) + np.nan_to_num(_rank_values(P[idx]), nan=0.5)
    elif strategy == "tail_veto":
        safe = idx[risk[idx] < risk_threshold]
        pool = safe if len(safe) else idx[np.argsort(risk[idx])[: min(top_n, len(idx))]]
        score = P
    else:
        raise ValueError(strategy)
    return pool[np.argsort(-np.nan_to_num(score[pool], nan=-1e9))[: min(top_n, len(pool))]]


def evaluate(
    meta: pd.DataFrame,
    K: np.ndarray,
    P: np.ndarray,
    risk: np.ndarray,
    val_days: np.ndarray,
    *,
    strategy: str,
    top_n: int,
    risk_threshold: float,
) -> tuple[dict, pd.DataFrame, np.ndarray]:
    days = meta["buyDate"].to_numpy()
    ret = meta["returnPct"].to_numpy(float)
    selected = np.zeros(len(meta), dtype=bool)
    rows = []
    for d in sorted(val_days):
        idx = np.where(days == d)[0]
        chosen = choose_by_strategy(idx, K, P, risk, strategy, top_n, risk_threshold)
        selected[chosen] = True
        rows.append({
            "date": d,
            "takeall_ret": float(ret[idx].mean()),
            "strategy_ret": float(ret[chosen].mean()) if len(chosen) else 0.0,
            "takeall_win": float((ret[idx] > 0).mean()),
            "strategy_win": float((ret[chosen] > 0).mean()) if len(chosen) else 0.0,
            "all_n": int(len(idx)),
            "selected_n": int(len(chosen)),
        })
    daily = pd.DataFrame(rows)
    p = ttest_rel(daily["strategy_ret"], daily["takeall_ret"]).pvalue if len(daily) >= 3 else np.nan
    out = {
        "strategy": strategy,
        "top_n": top_n,
        "risk_threshold": risk_threshold if strategy == "tail_veto" else np.nan,
        "days": int(len(daily)),
        "all_n": int(daily["all_n"].sum()),
        "selected_n": int(daily["selected_n"].sum()),
        "avg_selected_n": float(daily["selected_n"].mean()),
        "takeall_day_ret": float(daily["takeall_ret"].mean()),
        "strategy_day_ret": float(daily["strategy_ret"].mean()),
        "edge": float(daily["strategy_ret"].mean() - daily["takeall_ret"].mean()),
        "takeall_win": float(daily["takeall_win"].mean() * 100),
        "strategy_win": float(daily["strategy_win"].mean() * 100),
        "paired_p": float(p) if p == p else np.nan,
    }
    return out, daily, selected


def tune_threshold(
    meta: pd.DataFrame,
    K_oof: np.ndarray,
    P_oof: np.ndarray,
    risk_oof: np.ndarray,
    train_days: np.ndarray,
    top_n: int,
) -> float:
    candidates = np.arange(0.35, 0.86, 0.05)
    best_t = 0.65
    best_key = (-1e9, -1e9)
    for t in candidates:
        m, _, _ = evaluate(meta, K_oof, P_oof, risk_oof, train_days, strategy="tail_veto", top_n=top_n, risk_threshold=float(t))
        if m["avg_selected_n"] < 2.4:
            continue
        key = (m["edge"], m["strategy_day_ret"])
        if key > best_key:
            best_key = key
            best_t = float(t)
    return best_t


def run_one(meta: pd.DataFrame, E: np.ndarray, Xp: np.ndarray, seed: int, train_days_n: int, top_n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    all_days = np.array(sorted(meta["buyDate"].unique()))
    train_days = np.sort(rng.choice(all_days, size=train_days_n, replace=False))
    val_days = np.array([d for d in all_days if d not in set(train_days)])
    day_arr = meta["buyDate"].to_numpy()
    train_mask = np.isin(day_arr, train_days)
    val_mask = np.isin(day_arr, val_days)

    K_oof, P_oof = crossfit_train_scores(meta, E, Xp, train_days, seed)
    gate = train_gate(meta, K_oof, P_oof, train_mask, seed)
    X_gate_train = gate_features(meta, K_oof, P_oof)
    risk_oof = np.full(len(meta), np.nan)
    mask_oof = train_mask & ~np.isnan(K_oof) & ~np.isnan(P_oof)
    risk_oof[mask_oof] = gate.predict_proba(X_gate_train.loc[mask_oof].to_numpy(np.float32))[:, 1]
    threshold = tune_threshold(meta, K_oof, P_oof, risk_oof, train_days, top_n)

    K_val, P_val = fit_predict_kp(meta, E, Xp, train_mask, val_mask)
    X_gate_val = gate_features(meta, K_val, P_val)
    risk_val = np.full(len(meta), np.nan)
    risk_val[val_mask] = gate.predict_proba(X_gate_val.loc[val_mask].to_numpy(np.float32))[:, 1]

    metrics = []
    daily_parts = []
    for strategy in ["p_only", "pipe", "soft_kp", "tail_veto"]:
        m, daily, _ = evaluate(meta, K_val, P_val, risk_val, val_days, strategy=strategy, top_n=top_n, risk_threshold=threshold)
        m["seed"] = seed
        m["train_days"] = int(len(train_days))
        m["val_days"] = int(len(val_days))
        m["risk_threshold_tuned"] = threshold
        metrics.append(m)
        d = daily.copy()
        d["seed"] = seed
        d["strategy"] = strategy
        daily_parts.append(d)
    return pd.DataFrame(metrics), pd.concat(daily_parts, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--out", default="output/kronos_random_split")
    ap.add_argument("--emb", default="base")
    ap.add_argument("--seeds", default="0,1,2,3,4,5,6,7,8,9")
    ap.add_argument("--train-days", type=int, default=150)
    ap.add_argument("--top-n", type=int, default=3)
    args = ap.parse_args()

    ds = Path(args.ds)
    out = Path(args.out) / ds.name
    out.mkdir(parents=True, exist_ok=True)
    meta, E, Xp = load_data(ds, args.emb)
    seeds = [int(x) for x in args.seeds.split(",") if x]
    metrics_all = []
    daily_all = []
    for seed in seeds:
        print(f"[seed {seed}] random {args.train_days}/{meta['buyDate'].nunique() - args.train_days} days", flush=True)
        metrics, daily = run_one(meta, E, Xp, seed, args.train_days, args.top_n)
        metrics_all.append(metrics)
        daily_all.append(daily)

    metrics_df = pd.concat(metrics_all, ignore_index=True)
    daily_df = pd.concat(daily_all, ignore_index=True)
    metrics_df.to_csv(out / "metrics.csv", index=False)
    daily_df.to_csv(out / "daily.csv", index=False)
    summary = (
        metrics_df.groupby("strategy")
        .agg(
            n=("seed", "count"),
            ret_mean=("strategy_day_ret", "mean"),
            ret_std=("strategy_day_ret", "std"),
            edge_mean=("edge", "mean"),
            edge_std=("edge", "std"),
            win_mean=("strategy_win", "mean"),
            selected_mean=("avg_selected_n", "mean"),
            positive_edges=("edge", lambda s: int((s > 0).sum())),
            p_median=("paired_p", "median"),
        )
        .reset_index()
        .sort_values("edge_mean", ascending=False)
    )
    summary.to_csv(out / "summary.csv", index=False)
    payload = {
        "dataset": str(ds),
        "rows": int(len(meta)),
        "days": int(meta["buyDate"].nunique()),
        "train_days": args.train_days,
        "val_days": int(meta["buyDate"].nunique() - args.train_days),
        "top_n": args.top_n,
        "seeds": seeds,
        "artifacts": {
            "metrics": str(out / "metrics.csv"),
            "daily": str(out / "daily.csv"),
            "summary": str(out / "summary.csv"),
        },
        "summary": summary.to_dict(orient="records"),
    }
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
