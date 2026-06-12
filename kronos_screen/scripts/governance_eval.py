"""Governance evaluation for the K->P secondary screen.

This script keeps parameter tuning separate from live trading code. It evaluates
walk-forward OOS K/P scores on one dataset, sweeps simple selection parameters,
and writes auditable CSV/JSON artifacts:

  - grid.csv: keep-fraction x top-N performance
  - months.csv: monthly edge for selected strategies
  - buckets.csv: board/mode/open-bucket diagnostics
  - summary.json: best parameters and risk notes

The target is the repository's core label: buy-date open -> next trading day's
close (returnPct), scored cross-sectionally within each buyDate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import rankdata, ttest_rel
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


def _fold_bounds(dates: np.ndarray, n_folds: int = 5, start_frac: float = 0.5) -> list[tuple[str, str]]:
    uniq = np.array(sorted(set(dates)))
    start = int(len(uniq) * start_frac)
    edges = np.linspace(start, len(uniq), n_folds + 1).astype(int)
    return [(str(uniq[edges[k]]), str(uniq[edges[k + 1] - 1])) for k in range(n_folds)]


def _load_embeddings(ds: Path, meta: pd.DataFrame, emb: str) -> np.ndarray:
    z = np.load(ds / f"emb_{emb}.npz")
    rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    order = meta["row_id"].map(rid2i).to_numpy()
    if pd.isna(order).any():
        raise ValueError(f"embedding row_id mismatch for {ds}/emb_{emb}.npz")
    return z["emb"][order.astype(int)]


def _wf_k_scores(meta: pd.DataFrame, X: np.ndarray, folds: list[tuple[str, str]], pca_k: int, alpha: float) -> np.ndarray:
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    out = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi)
        tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        scaler = StandardScaler().fit(X[tr])
        xtr = scaler.transform(X[tr])
        xte = scaler.transform(X[te])
        if xtr.shape[1] > pca_k:
            pca = PCA(pca_k, random_state=0).fit(xtr)
            xtr = pca.transform(xtr)
            xte = pca.transform(xte)
        out[te] = Ridge(alpha=alpha).fit(xtr, tgt[tr]).predict(xte)
    return out


def _wf_p_scores(meta: pd.DataFrame, X: np.ndarray, folds: list[tuple[str, str]]) -> np.ndarray:
    days = meta["buyDate"].to_numpy()
    tgt = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy()
    out = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi)
        tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        model = HistGradientBoostingRegressor(
            max_iter=250,
            learning_rate=0.05,
            max_depth=3,
            min_samples_leaf=30,
            l2_regularization=1.0,
            random_state=0,
        )
        out[te] = model.fit(X[tr], tgt[tr]).predict(X[te])
    return out


def _load_or_compute_scores(
    ds: Path,
    meta: pd.DataFrame,
    *,
    emb: str,
    pca_k: int,
    alpha: float,
    recompute: bool,
) -> tuple[np.ndarray, np.ndarray]:
    cached = ds / "oos_components.npz"
    if cached.exists() and not recompute and emb == "base":
        z = np.load(cached)
        if "K" in z and "P" in z and len(z["K"]) == len(meta):
            return z["K"], z["P"]

    folds = _fold_bounds(meta["buyDate"].to_numpy())
    E = _load_embeddings(ds, meta, emb)
    pf = pd.read_parquet(ds / "priorday_feats.parquet").set_index("row_id")
    Xp = np.nan_to_num(pf.reindex(meta["row_id"].to_numpy()).to_numpy(np.float32))
    return _wf_k_scores(meta, E, folds, pca_k, alpha), _wf_p_scores(meta, Xp, folds)


def _equity(daily: Iterable[float]) -> tuple[float, float, float]:
    arr = np.asarray(list(daily), dtype=float)
    if len(arr) == 0:
        return np.nan, np.nan, np.nan
    eq = np.cumprod(1 + arr / 100.0)
    max_dd = ((eq / np.maximum.accumulate(eq)) - 1).min() * 100.0
    sharpe = arr.mean() / (arr.std(ddof=1) + 1e-9) * np.sqrt(252) if len(arr) > 1 else np.nan
    return (eq[-1] - 1) * 100.0, max_dd, sharpe


def _day_rank(score: np.ndarray, days: np.ndarray) -> np.ndarray:
    out = np.full(len(score), np.nan)
    for d in sorted(set(days)):
        idx = np.where(days == d)[0]
        valid = idx[~np.isnan(score[idx])]
        if len(valid):
            out[valid] = (rankdata(score[valid]) - 1) / max(len(valid) - 1, 1)
    return out


def _select(
    idx: np.ndarray,
    K: np.ndarray,
    P: np.ndarray,
    rK: np.ndarray,
    *,
    keep_frac: float,
    top_n: int,
    method: str,
) -> np.ndarray:
    if len(idx) == 0:
        return idx
    if method == "p_only":
        keep = idx
    elif method == "k_rank_median":
        keep = idx[np.nan_to_num(rK[idx], nan=-1.0) >= np.median(np.nan_to_num(rK[idx], nan=-1.0))]
        if len(keep) == 0:
            keep = idx
    elif method == "k_top_frac":
        keep_n = max(1, int(round(len(idx) * keep_frac)))
        keep = idx[np.argsort(-np.nan_to_num(K[idx], nan=-1e9))[: min(keep_n, len(idx))]]
    elif method == "kp_soft_rank":
        rP = _rank_values(P[idx])
        score = np.nan_to_num(rK[idx], nan=0.0) + np.nan_to_num(rP, nan=0.0)
        return idx[np.argsort(-score)[: min(top_n, len(idx))]]
    else:
        raise ValueError(f"unknown method: {method}")
    return keep[np.argsort(-np.nan_to_num(P[keep], nan=-1e9))[: min(top_n, len(keep))]]


def _rank_values(vals: np.ndarray) -> np.ndarray:
    out = np.full(len(vals), np.nan)
    valid = ~np.isnan(vals)
    if valid.sum() == 1:
        out[valid] = 0.5
    elif valid.sum() > 1:
        out[valid] = (rankdata(vals[valid]) - 1) / (valid.sum() - 1)
    return out


def _eval_strategy(
    meta: pd.DataFrame,
    K: np.ndarray,
    P: np.ndarray,
    *,
    method: str,
    keep_frac: float,
    top_n: int,
) -> tuple[dict, np.ndarray, pd.DataFrame]:
    days = meta["buyDate"].to_numpy()
    ret = meta["returnPct"].to_numpy()
    ok = ~np.isnan(K) & ~np.isnan(P)
    rK = _day_rank(K, days)
    selected = np.zeros(len(meta), dtype=bool)
    daily_rows = []
    for d in sorted(set(days[ok])):
        idx = np.where(ok & (days == d))[0]
        chosen = _select(idx, K, P, rK, keep_frac=keep_frac, top_n=top_n, method=method)
        selected[chosen] = True
        daily_rows.append({
            "date": d,
            "month": str(d)[:7],
            "takeall_ret": float(ret[idx].mean()),
            "strategy_ret": float(ret[chosen].mean()) if len(chosen) else np.nan,
            "takeall_win": float((ret[idx] > 0).mean()),
            "strategy_win": float((ret[chosen] > 0).mean()) if len(chosen) else np.nan,
            "all_n": int(len(idx)),
            "selected_n": int(len(chosen)),
        })
    daily = pd.DataFrame(daily_rows).dropna(subset=["strategy_ret"])
    cum, dd, sharpe = _equity(daily["strategy_ret"])
    _, ta_dd, ta_sharpe = _equity(daily["takeall_ret"])
    paired_p = ttest_rel(daily["strategy_ret"], daily["takeall_ret"]).pvalue if len(daily) >= 3 else np.nan
    summary = {
        "method": method,
        "keep_frac": keep_frac,
        "top_n": top_n,
        "days": int(len(daily)),
        "all_n": int(daily["all_n"].sum()),
        "selected_n": int(daily["selected_n"].sum()),
        "avg_selected_n": float(daily["selected_n"].mean()),
        "takeall_day_ret": float(daily["takeall_ret"].mean()),
        "strategy_day_ret": float(daily["strategy_ret"].mean()),
        "edge": float(daily["strategy_ret"].mean() - daily["takeall_ret"].mean()),
        "takeall_win": float(daily["takeall_win"].mean() * 100),
        "strategy_win": float(daily["strategy_win"].mean() * 100),
        "cum": float(cum),
        "max_dd": float(dd),
        "sharpe": float(sharpe),
        "takeall_max_dd": float(ta_dd),
        "takeall_sharpe": float(ta_sharpe),
        "paired_p": float(paired_p) if paired_p == paired_p else np.nan,
    }
    return summary, selected, daily


def _month_rows(daily: pd.DataFrame, label: str) -> list[dict]:
    rows = []
    for month, g in daily.groupby("month"):
        p = ttest_rel(g["strategy_ret"], g["takeall_ret"]).pvalue if len(g) >= 3 else np.nan
        rows.append({
            "strategy": label,
            "month": month,
            "days": int(len(g)),
            "all_n": int(g["all_n"].sum()),
            "selected_n": int(g["selected_n"].sum()),
            "takeall_day_ret": float(g["takeall_ret"].mean()),
            "strategy_day_ret": float(g["strategy_ret"].mean()),
            "edge": float(g["strategy_ret"].mean() - g["takeall_ret"].mean()),
            "takeall_win": float(g["takeall_win"].mean() * 100),
            "strategy_win": float(g["strategy_win"].mean() * 100),
            "paired_p": float(p) if p == p else np.nan,
        })
    return rows


def _bucket_rows(meta: pd.DataFrame, selected: np.ndarray, K: np.ndarray, P: np.ndarray, label: str) -> list[dict]:
    df = meta.copy()
    df["selected"] = selected
    df["scored"] = ~np.isnan(K) & ~np.isnan(P)
    df["open_bucket"] = pd.cut(
        pd.to_numeric(df["openPctChange"], errors="coerce"),
        bins=[-100, -6, -3, 0, 3, 100],
        labels=["<=-6", "-6..-3", "-3..0", "0..3", ">3"],
    ).astype(str)
    rows = []
    for key in ["board", "mode", "open_bucket"]:
        for value, g in df[df["scored"]].groupby(key, dropna=False):
            sg = g[g["selected"]]
            if len(g) < 10 or len(sg) == 0:
                continue
            rows.append({
                "strategy": label,
                "bucket_type": key,
                "bucket": str(value),
                "all_n": int(len(g)),
                "selected_n": int(len(sg)),
                "takeall_ret": float(g["returnPct"].mean()),
                "selected_ret": float(sg["returnPct"].mean()),
                "edge": float(sg["returnPct"].mean() - g["returnPct"].mean()),
                "takeall_win": float((g["returnPct"] > 0).mean() * 100),
                "selected_win": float((sg["returnPct"] > 0).mean() * 100),
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--out", default=None)
    ap.add_argument("--emb", default="base")
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--pca-k", type=int, default=8)
    ap.add_argument("--alpha", type=float, default=10.0)
    ap.add_argument("--keep-fracs", default="0.25,0.34,0.5,0.67,0.8,1.0")
    ap.add_argument("--top-ns", default="2,3,4,5")
    args = ap.parse_args()

    ds = Path(args.ds)
    out = Path(args.out) if args.out else Path("output/kronos_governance") / ds.name
    out.mkdir(parents=True, exist_ok=True)

    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    K, P = _load_or_compute_scores(ds, meta, emb=args.emb, pca_k=args.pca_k, alpha=args.alpha, recompute=args.recompute)
    keep_fracs = [float(x) for x in args.keep_fracs.split(",") if x]
    top_ns = [int(x) for x in args.top_ns.split(",") if x]

    strategies: list[tuple[str, str, float, int]] = []
    for method in ["k_rank_median", "k_top_frac", "kp_soft_rank", "p_only"]:
        for top_n in top_ns:
            if method == "k_top_frac":
                for keep_frac in keep_fracs:
                    strategies.append((f"{method}_{keep_frac:g}_top{top_n}", method, keep_frac, top_n))
            else:
                strategies.append((f"{method}_top{top_n}", method, 0.5, top_n))

    grid_rows = []
    month_rows = []
    bucket_rows = []
    selected_by_label = {}
    daily_by_label = {}
    for label, method, keep_frac, top_n in strategies:
        summary, selected, daily = _eval_strategy(meta, K, P, method=method, keep_frac=keep_frac, top_n=top_n)
        summary["strategy"] = label
        grid_rows.append(summary)
        selected_by_label[label] = selected
        daily_by_label[label] = daily
        if label in {"k_rank_median_top3", "p_only_top3", "kp_soft_rank_top3", "k_top_frac_0.5_top3"}:
            month_rows.extend(_month_rows(daily, label))
            bucket_rows.extend(_bucket_rows(meta, selected, K, P, label))

    grid = pd.DataFrame(grid_rows).sort_values(["edge", "strategy_day_ret"], ascending=False)
    months = pd.DataFrame(month_rows)
    buckets = pd.DataFrame(bucket_rows)
    grid.to_csv(out / "grid.csv", index=False)
    months.to_csv(out / "months.csv", index=False)
    buckets.to_csv(out / "buckets.csv", index=False)

    default_rows = grid[grid["strategy"] == "k_rank_median_top3"]
    if default_rows.empty:
        default_rows = grid[grid["strategy"].astype(str).str.startswith("k_rank_median_")].head(1)
    default = (default_rows.iloc[0] if not default_rows.empty else grid.iloc[0]).to_dict()
    robust = grid[
        (grid["edge"] > 0)
        & (grid["paired_p"] <= 0.10)
        & (grid["avg_selected_n"] >= 2.5)
    ].head(10)
    best = grid.iloc[0].to_dict()
    summary = {
        "dataset": str(ds),
        "rows": int(len(meta)),
        "date_min": str(meta["buyDate"].min()),
        "date_max": str(meta["buyDate"].max()),
        "oos_date_min": str(meta.loc[(~np.isnan(K)) & (~np.isnan(P)), "buyDate"].min()),
        "oos_date_max": str(meta.loc[(~np.isnan(K)) & (~np.isnan(P)), "buyDate"].max()),
        "oos_rows": int(((~np.isnan(K)) & (~np.isnan(P))).sum()),
        "default": default,
        "best_by_edge": best,
        "robust_candidates": robust.to_dict(orient="records"),
        "artifacts": {
            "grid": str(out / "grid.csv"),
            "months": str(out / "months.csv"),
            "buckets": str(out / "buckets.csv"),
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"wrote {out}")
    print(f"default k_rank_median_top3: ret={default['strategy_day_ret']:+.3f}% edge={default['edge']:+.3f}% p={default['paired_p']:.3f}")
    print(f"best edge: {best['strategy']} ret={best['strategy_day_ret']:+.3f}% edge={best['edge']:+.3f}% p={best['paired_p']:.3f}")
    if len(robust):
        print("robust candidates:")
        for r in robust.head(5).to_dict(orient="records"):
            print(f"  {r['strategy']}: ret={r['strategy_day_ret']:+.3f}% edge={r['edge']:+.3f}% p={r['paired_p']:.3f}")


if __name__ == "__main__":
    main()
