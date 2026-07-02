#!/usr/bin/env python3
"""Walk-forward OOS validation for K-survivor mode-rotation selection.

The research question is whether the live candidate set should paper-trade
`mode_star`: keep the K-good half of each day, then rank survivors by the
mode-aware live rank score instead of P alone.

Inputs are cache/local artifacts only:
  - historical Kronos dataset under kronos_screen/data/ds
  - optional June live all-hit rows under output/live/training_rows.parquet
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DS = ROOT / "kronos_screen" / "data" / "ds"
DEFAULT_LIVE = ROOT / "output" / "live" / "training_rows.parquet"
DEFAULT_OUT = ROOT / "output" / "research"
WINDOWS = (5, 10, 20)
WINDOW_WEIGHTS = {5: 0.50, 10: 0.30, 20: 0.20}
FEE_RATE = 0.0001


@dataclass(frozen=True)
class Variant:
    name: str
    selected: pd.DataFrame
    daily: pd.DataFrame
    cash_slots: int | None = None

    @property
    def avg_daily(self) -> float:
        return float(self.daily["ret"].mean()) if not self.daily.empty else float("nan")

    @property
    def simple_sum(self) -> float:
        return float(self.daily["ret"].sum()) if not self.daily.empty else float("nan")

    @property
    def trade_mean(self) -> float:
        return float(self.selected["ret"].mean()) if not self.selected.empty else float("nan")

    @property
    def win_rate(self) -> float:
        return float((self.selected["ret"] > 0).mean()) if not self.selected.empty else float("nan")


def _net_return(ret_pct: float, fee_rate: float = FEE_RATE) -> float:
    return ((1.0 + ret_pct / 100.0) * (1.0 - fee_rate) / (1.0 + fee_rate) - 1.0) * 100.0


def _num(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _rank_pct(vals: np.ndarray) -> np.ndarray:
    out = np.full(len(vals), np.nan)
    valid = ~np.isnan(vals)
    if valid.sum() == 1:
        out[valid] = 0.5
    elif valid.sum() > 1:
        out[valid] = (rankdata(vals[valid]) - 1) / (valid.sum() - 1)
    return out


def _filled_rank_pct(vals: np.ndarray, fill: float = 0.5) -> np.ndarray:
    ranks = _rank_pct(vals)
    return np.nan_to_num(ranks, nan=fill)


def _date_folds(days: Iterable[str], *, min_train_days: int, test_days: int) -> list[tuple[str, str]]:
    uniq = sorted(set(str(d)[:10] for d in days))
    folds: list[tuple[str, str]] = []
    start = min_train_days
    while start < len(uniq):
        end = min(len(uniq), start + test_days)
        folds.append((uniq[start], uniq[end - 1]))
        start = end
    return folds


def _load_historical_scores(ds: Path, min_train_days: int, test_days: int) -> pd.DataFrame:
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    z = np.load(ds / "emb_base.npz")
    rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    order = meta["row_id"].map(rid2i).to_numpy()
    if pd.isna(order).any():
        raise SystemExit(f"embedding row_id mismatch under {ds}")
    E = z["emb"][order.astype(int)]
    pf = pd.read_parquet(ds / "priorday_feats.parquet").set_index("row_id")
    Xp = np.nan_to_num(pf.reindex(meta["row_id"].to_numpy()).to_numpy(np.float32))

    days = meta["buyDate"].astype(str).to_numpy()
    target = (meta["returnPct"] - meta.groupby("buyDate")["returnPct"].transform("mean")).to_numpy(float)
    folds = _date_folds(days, min_train_days=min_train_days, test_days=test_days)
    K = np.full(len(meta), np.nan)
    P = np.full(len(meta), np.nan)
    for lo, hi in folds:
        te = (days >= lo) & (days <= hi)
        tr = days < lo
        if tr.sum() < 100 or te.sum() < 10:
            continue
        scaler = StandardScaler().fit(E[tr])
        xtr = scaler.transform(E[tr])
        xte = scaler.transform(E[te])
        pca = PCA(min(8, xtr.shape[1]), random_state=0).fit(xtr)
        K[te] = Ridge(alpha=10.0).fit(pca.transform(xtr), target[tr]).predict(pca.transform(xte))

        model = HistGradientBoostingRegressor(
            max_iter=250,
            learning_rate=0.05,
            max_depth=3,
            min_samples_leaf=30,
            l2_regularization=1.0,
            random_state=0,
        )
        P[te] = model.fit(Xp[tr], target[tr]).predict(Xp[te])

    out = pd.DataFrame({
        "date": meta["buyDate"].astype(str),
        "code": meta["code"].astype(str),
        "name": meta["name"].astype(str),
        "mode": meta["mode"].astype(str),
        "xcjw": pd.to_numeric(meta["xcjw"], errors="coerce").fillna(0.0),
        "cjs": pd.to_numeric(meta["cjs"], errors="coerce").fillna(0.0),
        "jsjl": pd.to_numeric(meta["jsjl"], errors="coerce").fillna(0.0),
        "jssb": pd.to_numeric(meta.get("jssb", 0.0), errors="coerce").fillna(0.0),
        "open_pct_change": pd.to_numeric(meta["openPctChange"], errors="coerce").fillna(0.0),
        "direction_rank": pd.to_numeric(meta.get("directionRank", -1), errors="coerce").fillna(-1).astype(int),
        "category_rank": pd.to_numeric(meta.get("categoryRank", -1), errors="coerce").fillna(-1).astype(int),
        "ret": [_net_return(float(x)) for x in meta["returnPct"].to_numpy(float)],
        "k_score": K,
        "p_score": P,
        "source": "historical_expanding_oos",
    })
    return out.dropna(subset=["k_score", "p_score", "ret"]).reset_index(drop=True)


def _load_live_rows(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame()
    ret_col = "net_realized_ret" if "net_realized_ret" in df.columns else "realized_ret"
    required = {"date", "code", "mode", ret_col, "k_score", "p_score"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    if "is_live" in df.columns:
        df = df[df["is_live"].astype(bool)]
    out = pd.DataFrame({
        "date": df["date"].astype(str).str[:10],
        "code": df["code"].astype(str),
        "name": df.get("name", "").astype(str),
        "mode": df["mode"].astype(str),
        "xcjw": pd.to_numeric(df.get("xcjw", 0.0), errors="coerce").fillna(0.0),
        "cjs": pd.to_numeric(df.get("cjs", 0.0), errors="coerce").fillna(0.0),
        "jsjl": pd.to_numeric(df.get("jsjl", 0.0), errors="coerce").fillna(0.0),
        "jssb": pd.to_numeric(df.get("jssb", 0.0), errors="coerce").fillna(0.0),
        "open_pct_change": pd.to_numeric(df.get("open_pct_change", 0.0), errors="coerce").fillna(0.0),
        "direction_rank": -1,
        "category_rank": -1,
        "ret": pd.to_numeric(df[ret_col], errors="coerce"),
        "k_score": pd.to_numeric(df["k_score"], errors="coerce"),
        "p_score": pd.to_numeric(df["p_score"], errors="coerce"),
        "source": "live_training_rows",
    })
    return out.dropna(subset=["ret", "k_score", "p_score"]).reset_index(drop=True)


def _primary(row: pd.Series) -> float:
    mode = str(row["mode"])
    xcjw = _num(row.get("xcjw"))
    cjs = _num(row.get("cjs"))
    jsjl = _num(row.get("jsjl"))
    jssb = _num(row.get("jssb"))
    if "起爆" in mode:
        return jssb
    if mode.startswith("接力"):
        return xcjw + max(jsjl, 0.0) * 0.5
    if mode in {"N字低吸", "孕线低吸"}:
        return xcjw + cjs * 0.6
    return xcjw + cjs * 0.8


def _focus_rank_score(rank: object) -> float:
    r = int(_num(rank, -1))
    if r < 0:
        return 0.0
    return {0: 100.0, 1: 85.0, 2: 70.0}.get(r, 55.0)


def _open_risk(mode: str, open_pct: float) -> float:
    if mode.startswith("接力") or "起爆" in mode:
        return min(35.0, max(0.0, open_pct - 3.0) * 8.0 + max(0.0, -2.0 - open_pct) * 5.0)
    return min(35.0, max(0.0, -7.0 - open_pct) * 8.0 + max(0.0, open_pct - 1.5) * 6.0)


def _mode_confidence(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["date", "code"]).reset_index(drop=True).copy()
    trade_days = sorted(df["date"].unique())
    day_pos = {d: i for i, d in enumerate(trade_days)}
    confidences: list[float] = []
    recent_avg_values: list[float] = []
    n_values: list[int] = []
    for row in df.itertuples():
        idx = day_pos[row.date]
        weighted_sum = 0.0
        weight_sum = 0.0
        max_n = 0
        for window in WINDOWS:
            prior_days = set(trade_days[max(0, idx - window):idx])
            vals = df.loc[(df["date"].isin(prior_days)) & (df["mode"] == row.mode), "ret"]
            n = int(vals.count())
            if n <= 0:
                continue
            avg = float(vals.mean())
            weight = WINDOW_WEIGHTS[window]
            weighted_sum += avg * weight
            weight_sum += weight
            max_n = max(max_n, n)
        if weight_sum <= 0:
            confidences.append(50.0)
            recent_avg_values.append(0.0)
            n_values.append(0)
            continue
        recent_avg = weighted_sum / weight_sum
        raw = 50.0 + max(-10.0, min(10.0, recent_avg)) * 4.0
        shrink = min(1.0, max_n / 8.0)
        confidences.append(max(0.0, min(100.0, 50.0 + (raw - 50.0) * shrink)))
        recent_avg_values.append(recent_avg)
        n_values.append(max_n)
    df["mode_confidence"] = confidences
    df["mode_recent_avg"] = recent_avg_values
    df["mode_recent_n"] = n_values
    return df


def _annotate(df: pd.DataFrame) -> pd.DataFrame:
    out = _mode_confidence(df)
    primaries = []
    rank_scores = []
    macro_scores = []
    for _, row in out.iterrows():
        primary = _primary(row)
        score_fit = min(140.0, primary / 350.0 * 100.0)
        macro = max(_focus_rank_score(row.get("direction_rank")), _focus_rank_score(row.get("category_rank")))
        risk = _open_risk(str(row["mode"]), _num(row.get("open_pct_change")))
        rank = score_fit * 0.60 + _num(row.get("mode_confidence"), 50.0) * 0.25 + macro * 0.18 - risk
        primaries.append(primary)
        macro_scores.append(macro)
        rank_scores.append(rank)
    out["primary_score"] = primaries
    out["macro_focus_score"] = macro_scores
    out["rank_score"] = rank_scores
    return out


def _with_k_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["kp_keep"] = False
    out["k_rank_pct"] = np.nan
    for day, g in out.groupby("date"):
        idx = g.index.to_numpy()
        ranks = _rank_pct(out.loc[idx, "k_score"].to_numpy(float))
        out.loc[idx, "k_rank_pct"] = ranks
        median = np.nanmedian(ranks)
        out.loc[idx, "kp_keep"] = ranks >= median
    return out


def _select_day(day_df: pd.DataFrame, score_col: str, *, max_per_mode: int = 2, top_n: int = 3) -> pd.DataFrame:
    chosen: list[int] = []
    per_mode: Counter[str] = Counter()
    for idx, row in day_df.sort_values([score_col, "primary_score", "code"], ascending=[False, False, True]).iterrows():
        mode = str(row["mode"])
        if per_mode[mode] >= max_per_mode:
            continue
        chosen.append(idx)
        per_mode[mode] += 1
        if len(chosen) >= top_n:
            break
    return day_df.loc[chosen].copy()


def _with_combo_score(day_df: pd.DataFrame, *, p_weight: float, mode_weight: float, out_col: str) -> pd.DataFrame:
    out = day_df.copy()
    p_rank = _filled_rank_pct(out["p_score"].to_numpy(float))
    mode_rank = _filled_rank_pct(out["mode_confidence"].to_numpy(float))
    # Centering keeps P as the anchor and makes +/- mode weights easier to compare
    # across daily pools with different candidate counts.
    out[out_col] = p_weight * p_rank + mode_weight * (mode_rank - 0.5)
    out["p_rank_pct"] = p_rank
    out["mode_rank_pct"] = mode_rank
    return out


def _variant(
    df: pd.DataFrame,
    name: str,
    selector: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    cash_slots: int | None = None,
) -> Variant:
    pieces = []
    daily_rows = []
    for _, g in df.groupby("date", sort=True):
        pick = selector(g)
        if not pick.empty:
            pieces.append(pick)
        day = str(g["date"].iloc[0])
        if cash_slots is not None:
            daily_rows.append({"date": day, "ret": float(pick["ret"].sum()) / cash_slots})
        else:
            daily_rows.append({"date": day, "ret": float(pick["ret"].mean()) if not pick.empty else 0.0})
    selected = pd.concat(pieces, ignore_index=False) if pieces else df.iloc[0:0].copy()
    daily = pd.DataFrame(daily_rows, columns=["date", "ret"])
    return Variant(name, selected, daily, cash_slots=cash_slots)


def _take_all(df: pd.DataFrame) -> Variant:
    daily = df.groupby("date", as_index=False)["ret"].mean()
    return Variant("take_all", df.copy(), daily)


def _pipe_selector(g: pd.DataFrame) -> pd.DataFrame:
    return g[g["kp_keep"]].sort_values("p_score", ascending=False).head(3).copy()


def _combo_selector(
    *,
    p_weight: float,
    mode_weight: float,
    max_per_mode: int | None = None,
) -> Callable[[pd.DataFrame], pd.DataFrame]:
    score_col = "combo_score"

    def select(g: pd.DataFrame) -> pd.DataFrame:
        pool = _with_combo_score(g[g["kp_keep"]], p_weight=p_weight, mode_weight=mode_weight, out_col=score_col)
        if max_per_mode is None:
            return pool.sort_values([score_col, "p_score", "primary_score", "code"], ascending=[False, False, False, True]).head(3)
        return _select_day(pool, score_col, max_per_mode=max_per_mode, top_n=3)

    return select


def _bad_mode_veto_selector(threshold: float) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def select(g: pd.DataFrame) -> pd.DataFrame:
        pool = g[(g["kp_keep"]) & (g["mode_confidence"] >= threshold)]
        return pool.sort_values("p_score", ascending=False).head(3).copy()

    return select


def _bad_recent_veto_selector(cutoff: float, *, min_n: int = 8) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def select(g: pd.DataFrame) -> pd.DataFrame:
        bad = (g["mode_recent_n"] >= min_n) & (g["mode_recent_avg"] < cutoff)
        pool = g[(g["kp_keep"]) & (~bad)]
        return pool.sort_values("p_score", ascending=False).head(3).copy()

    return select


def _router_variant(
    name: str,
    left: Variant,
    right: Variant,
    *,
    lookback: int,
) -> Variant:
    left_daily = left.daily.set_index("date")["ret"].to_dict()
    right_daily = right.daily.set_index("date")["ret"].to_dict()
    left_sel = {d: g for d, g in left.selected.groupby("date")}
    right_sel = {d: g for d, g in right.selected.groupby("date")}
    days = sorted(set(left_daily) & set(right_daily))
    picks = []
    daily_rows = []
    for i, day in enumerate(days):
        prior = days[max(0, i - lookback):i]
        edge = np.mean([right_daily[d] - left_daily[d] for d in prior]) if prior else 0.0
        use_right = edge > 0.0
        source = right_sel if use_right else left_sel
        ret_source = right_daily if use_right else left_daily
        pick = source.get(day)
        if pick is not None and not pick.empty:
            part = pick.copy()
            part["router_used"] = "right" if use_right else "left"
            picks.append(part)
        daily_rows.append({"date": day, "ret": float(ret_source.get(day, 0.0))})
    selected = pd.concat(picks, ignore_index=False) if picks else left.selected.iloc[0:0].copy()
    daily = pd.DataFrame(daily_rows)
    return Variant(name, selected, daily)


def _write_guard(path: Path, selected: pd.DataFrame, base_daily: pd.DataFrame, label: str) -> None:
    base = {str(r.date): float(r.ret) for r in base_daily.itertuples()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in selected.sort_values(["date", "code"]).itertuples():
            day = str(row.date)
            if day not in base:
                raise RuntimeError(f"missing baseline day {day} for {path}")
            f.write(json.dumps({
                "day": day,
                "code": row.code,
                "name": row.name,
                "mode": row.mode,
                "strat_ret": float(row.ret),
                "base_ret": float(base[day]),
                "benchmark": label,
                "rank_score": float(row.rank_score),
                "mode_confidence": float(row.mode_confidence),
                "k_score": float(row.k_score),
                "p_score": float(row.p_score),
                "source": row.source,
            }, ensure_ascii=False) + "\n")


def _write_daily_guard(path: Path, variant: Variant, base_daily: pd.DataFrame, label: str) -> None:
    base = {str(r.date): float(r.ret) for r in base_daily.itertuples()}
    strat = {str(r.date): float(r.ret) for r in variant.daily.itertuples()}
    missing = sorted(set(base) - set(strat))
    if missing:
        raise RuntimeError(f"missing strategy days for {variant.name}: {missing[:5]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for day in sorted(base):
            f.write(json.dumps({
                "day": day,
                "strat_ret": float(strat[day]),
                "base_ret": float(base[day]),
                "benchmark": label,
                "variant": variant.name,
                "portfolio_day": True,
            }, ensure_ascii=False) + "\n")


def _write_slot_guard(path: Path, variant: Variant, base_daily: pd.DataFrame, label: str, *, slots: int = 3) -> None:
    """Write a slot-level guard file.

    This is the fair contract for veto variants: if a bad-mode filter leaves only
    one or two names, the remaining slots are explicit 0% cash returns instead of
    disappearing from the per-trade guard.
    """
    base = {str(r.date): float(r.ret) for r in base_daily.itertuples()}
    by_day = {str(d): g.copy() for d, g in variant.selected.groupby("date")} if not variant.selected.empty else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for day in sorted(base):
            rows = by_day.get(day)
            if rows is not None and not rows.empty:
                rows = rows.sort_values(["p_score", "rank_score", "code"], ascending=[False, False, True])
            for slot in range(slots):
                payload = {
                    "day": day,
                    "strat_ret": 0.0,
                    "base_ret": float(base.get(day, 0.0)),
                    "benchmark": label,
                    "variant": variant.name,
                    "slot": slot + 1,
                    "code": f"CASH_SLOT_{slot + 1}",
                    "name": "cash",
                    "mode": "cash",
                }
                if rows is not None and slot < len(rows):
                    row = rows.iloc[slot]
                    payload.update({
                        "strat_ret": float(row["ret"]),
                        "code": str(row["code"]),
                        "name": str(row.get("name", "")),
                        "mode": str(row["mode"]),
                        "rank_score": float(row.get("rank_score", 0.0)),
                        "mode_confidence": float(row.get("mode_confidence", 50.0)),
                        "k_score": float(row.get("k_score", 0.0)),
                        "p_score": float(row.get("p_score", 0.0)),
                        "source": str(row.get("source", "")),
                    })
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _fmt(x: float) -> str:
    return f"{x:+.3f}%" if x == x else "nan"


def _edge_table(variants: list[Variant], base_name: str) -> list[str]:
    base = next(v for v in variants if v.name == base_name)
    base_daily = base.daily.rename(columns={"ret": "base"})
    lines = [
        "| variant | days | avg daily | edge vs pipe | avg picks/day | zero-pick days |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant in variants:
        joined = variant.daily.rename(columns={"ret": "ret"}).merge(base_daily, on="date", how="inner")
        edge = float((joined["ret"] - joined["base"]).mean()) if not joined.empty else float("nan")
        pick_counts = variant.selected.groupby("date").size() if not variant.selected.empty else pd.Series(dtype=float)
        avg_picks = float(pick_counts.reindex(joined["date"], fill_value=0).mean()) if not joined.empty else float("nan")
        zero_days = int((pick_counts.reindex(joined["date"], fill_value=0) == 0).sum()) if not joined.empty else 0
        lines.append(
            f"| {variant.name} | {len(joined)} | {_fmt(variant.avg_daily)} | {_fmt(edge)} | {avg_picks:.2f} | {zero_days} |"
        )
    return lines


def _report(df: pd.DataFrame, variants: list[Variant], out_paths: dict[str, Path]) -> str:
    lines = [
        "# K Survivors + Mode Rotation OOS Validation",
        "",
        "## Data Contract",
        "",
        "- Historical K/P scores are expanding walk-forward OOS from `kronos_screen/data/ds`.",
        "- June rows are live all-hit rows from `output/live/training_rows.parquet`.",
        "- Mode confidence uses prior buy dates only over 5/10/20-day all-hit mode returns.",
        "- Return unit is net percent after 1bp one-way fee where historical rows had only gross `returnPct`.",
        "",
        f"Rows: {len(df)}, days: {df['date'].nunique()}, span: {df['date'].min()}..{df['date'].max()}",
        "",
        "## Variant Summary",
        "",
        "| variant | avg daily | simple sum | trade mean | win rate | days | trades |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for v in variants:
        lines.append(
            f"| {v.name} | {_fmt(v.avg_daily)} | {_fmt(v.simple_sum)} | {_fmt(v.trade_mean)} | "
            f"{v.win_rate:.1%} | {len(v.daily)} | {len(v.selected)} |"
        )
    lines.extend([
        "",
        "## Edge vs Current PIPE",
        "",
        "PIPE is `K good half -> P top3`. Non-slot variants match today's default `paper_record.py` sizing: deployable cash is re-equal-weighted across actually buyable picks.",
        "",
        *_edge_table(variants, "pipe_k50_p_top3"),
        "",
        "## Slot-Cash Edge vs Slot-Cash PIPE",
        "",
        "This is the stricter quality-governor-style sizing: if a filter removes a pick, that slot stays cash and is not reallocated.",
        "",
        *_edge_table([v for v in variants if v.cash_slots is not None], "pipe_k50_p_top3_slotcash"),
    ])
    lines.extend(["", "## Monthly Edge vs Current PIPE", ""])
    pipe = next(v for v in variants if v.name == "pipe_k50_p_top3")
    mode = next(v for v in variants if v.name == "mode_rotation_k_survivors")
    joined = pipe.daily.rename(columns={"ret": "pipe"}).merge(
        mode.daily.rename(columns={"ret": "mode"}), on="date", how="inner"
    )
    joined["month"] = joined["date"].str[:7]
    lines.append("| month | days | pipe | mode | edge |")
    lines.append("|---|---:|---:|---:|---:|")
    for month, g in joined.groupby("month"):
        edge = float((g["mode"] - g["pipe"]).mean())
        lines.append(f"| {month} | {len(g)} | {_fmt(float(g['pipe'].mean()))} | {_fmt(float(g['mode'].mean()))} | {_fmt(edge)} |")
    lines.extend(["", "## Guard Inputs", ""])
    for name, path in out_paths.items():
        lines.append(f"- {name}: `{path}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ds", type=Path, default=DEFAULT_DS)
    parser.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--min-train-days", type=int, default=45)
    parser.add_argument("--test-days", type=int, default=20)
    args = parser.parse_args()

    hist = _load_historical_scores(args.ds, args.min_train_days, args.test_days)
    live = _load_live_rows(args.live)
    df = pd.concat([hist, live], ignore_index=True)
    df = df.sort_values(["date", "code"]).drop_duplicates(["date", "code"], keep="last").reset_index(drop=True)
    df = _with_k_flags(_annotate(df))

    p_plus_050_selector = _combo_selector(p_weight=1.0, mode_weight=0.50)
    p_minus_050_selector = _combo_selector(p_weight=1.0, mode_weight=-0.50)
    veto50_selector = _bad_mode_veto_selector(50.0)
    recent_bad0_selector = _bad_recent_veto_selector(0.0)
    recent_bad05_selector = _bad_recent_veto_selector(-0.5)

    variants = [
        _take_all(df),
        _variant(df, "p_top3", lambda g: g.sort_values("p_score", ascending=False).head(3)),
        _variant(df, "pipe_k50_p_top3", _pipe_selector),
        _variant(df, "pipe_k50_p_top3_slotcash", _pipe_selector, cash_slots=3),
        _variant(df, "mode_rotation_all", lambda g: _select_day(g, "rank_score")),
        _variant(df, "mode_rotation_k_survivors", lambda g: _select_day(g[g["kp_keep"]], "rank_score")),
        _variant(df, "mode_rotation_k_survivors_slotcash", lambda g: _select_day(g[g["kp_keep"]], "rank_score"), cash_slots=3),
        _variant(df, "k_mode_conf_only_diverse", _combo_selector(p_weight=0.0, mode_weight=1.0, max_per_mode=2)),
        _variant(df, "k_mode_conf_plus_p_025_diverse", _combo_selector(p_weight=0.25, mode_weight=1.0, max_per_mode=2)),
        _variant(df, "k_p_plus_mode_025", _combo_selector(p_weight=1.0, mode_weight=0.25)),
        _variant(df, "k_p_plus_mode_050", p_plus_050_selector),
        _variant(df, "k_p_plus_mode_050_slotcash", p_plus_050_selector, cash_slots=3),
        _variant(df, "k_p_plus_mode_100", _combo_selector(p_weight=1.0, mode_weight=1.00)),
        _variant(df, "k_p_minus_hot_mode_025", _combo_selector(p_weight=1.0, mode_weight=-0.25)),
        _variant(df, "k_p_minus_hot_mode_050", p_minus_050_selector),
        _variant(df, "k_p_minus_hot_mode_050_slotcash", p_minus_050_selector, cash_slots=3),
        _variant(df, "k_mode_plus_p_050_diverse", _combo_selector(p_weight=0.50, mode_weight=1.0, max_per_mode=2)),
        _variant(df, "k_mode_plus_p_100_diverse", _combo_selector(p_weight=1.00, mode_weight=1.0, max_per_mode=2)),
        _variant(df, "k_bad_mode_veto_conf35_redeploy", _bad_mode_veto_selector(35.0)),
        _variant(df, "k_bad_mode_veto_conf40_redeploy", _bad_mode_veto_selector(40.0)),
        _variant(df, "k_bad_mode_veto_conf45_redeploy", _bad_mode_veto_selector(45.0)),
        _variant(df, "k_bad_mode_veto_conf50_redeploy", veto50_selector),
        _variant(df, "k_bad_mode_veto_conf35_slotcash", _bad_mode_veto_selector(35.0), cash_slots=3),
        _variant(df, "k_bad_mode_veto_conf40_slotcash", _bad_mode_veto_selector(40.0), cash_slots=3),
        _variant(df, "k_bad_mode_veto_conf45_slotcash", _bad_mode_veto_selector(45.0), cash_slots=3),
        _variant(df, "k_bad_mode_veto_conf50_slotcash", veto50_selector, cash_slots=3),
        _variant(df, "k_bad_recent_avg_lt0_n8_redeploy", recent_bad0_selector),
        _variant(df, "k_bad_recent_avg_lt0_n8_slotcash", recent_bad0_selector, cash_slots=3),
        _variant(df, "k_bad_recent_avg_lt-0p5_n8_redeploy", recent_bad05_selector),
        _variant(df, "k_bad_recent_avg_lt-0p5_n8_slotcash", recent_bad05_selector, cash_slots=3),
    ]
    pipe_for_router = next(v for v in variants if v.name == "pipe_k50_p_top3")
    mode_for_router = next(v for v in variants if v.name == "mode_rotation_k_survivors")
    p_minus_for_router = next(v for v in variants if v.name == "k_p_minus_hot_mode_050")
    veto50_for_router = next(v for v in variants if v.name == "k_bad_mode_veto_conf50_redeploy")
    variants.extend([
        _router_variant("router_pipe_or_mode_lb10", pipe_for_router, mode_for_router, lookback=10),
        _router_variant("router_pipe_or_mode_lb20", pipe_for_router, mode_for_router, lookback=20),
        _router_variant("router_pipe_or_mode_lb40", pipe_for_router, mode_for_router, lookback=40),
        _router_variant("router_pipe_or_p_minus_hot_lb20", pipe_for_router, p_minus_for_router, lookback=20),
        _router_variant("router_pipe_or_veto50_lb20", pipe_for_router, veto50_for_router, lookback=20),
    ])

    start, end = df["date"].min(), df["date"].max()
    suffix = f"{start}_{end}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    mode = next(v for v in variants if v.name == "mode_rotation_k_survivors")
    pipe = next(v for v in variants if v.name == "pipe_k50_p_top3")
    take = next(v for v in variants if v.name == "take_all")
    pure_mode = next(v for v in variants if v.name == "k_mode_conf_only_diverse")
    vs_pipe = args.out_dir / f"kp_mode_rotation_oos_vs_pipe_{suffix}.jsonl"
    vs_take = args.out_dir / f"kp_mode_rotation_oos_vs_take_all_{suffix}.jsonl"
    vs_pure_mode = args.out_dir / f"kp_mode_conf_only_vs_pipe_{suffix}.jsonl"
    p_plus = next(v for v in variants if v.name == "k_p_plus_mode_050")
    p_minus = next(v for v in variants if v.name == "k_p_minus_hot_mode_050")
    p_plus_slot = next(v for v in variants if v.name == "k_p_plus_mode_050_slotcash")
    p_minus_slot = next(v for v in variants if v.name == "k_p_minus_hot_mode_050_slotcash")
    pipe_slot = next(v for v in variants if v.name == "pipe_k50_p_top3_slotcash")
    veto50_redeploy = next(v for v in variants if v.name == "k_bad_mode_veto_conf50_redeploy")
    veto50 = next(v for v in variants if v.name == "k_bad_mode_veto_conf50_slotcash")
    recent_bad0 = next(v for v in variants if v.name == "k_bad_recent_avg_lt0_n8_redeploy")
    recent_bad0_slot = next(v for v in variants if v.name == "k_bad_recent_avg_lt0_n8_slotcash")
    router_pminus = next(v for v in variants if v.name == "router_pipe_or_p_minus_hot_lb20")
    router_veto50 = next(v for v in variants if v.name == "router_pipe_or_veto50_lb20")
    vs_p_plus = args.out_dir / f"kp_p_plus_mode_050_vs_pipe_{suffix}.jsonl"
    vs_p_minus = args.out_dir / f"kp_p_minus_hot_mode_050_vs_pipe_{suffix}.jsonl"
    vs_p_plus_slot = args.out_dir / f"kp_p_plus_mode_050_slotcash_vs_pipe_slotcash_{suffix}.jsonl"
    vs_p_minus_slot = args.out_dir / f"kp_p_minus_hot_mode_050_slotcash_vs_pipe_slotcash_{suffix}.jsonl"
    vs_veto50_redeploy = args.out_dir / f"kp_bad_mode_veto_conf50_redeploy_daily_vs_pipe_{suffix}.jsonl"
    vs_veto50 = args.out_dir / f"kp_bad_mode_veto_conf50_slotcash_vs_pipe_slotcash_{suffix}.jsonl"
    vs_recent_bad0 = args.out_dir / f"kp_bad_recent_avg_lt0_n8_redeploy_daily_vs_pipe_{suffix}.jsonl"
    vs_recent_bad0_slot = args.out_dir / f"kp_bad_recent_avg_lt0_n8_slotcash_vs_pipe_slotcash_{suffix}.jsonl"
    vs_router_pminus = args.out_dir / f"kp_router_pipe_or_p_minus_hot_lb20_daily_vs_pipe_{suffix}.jsonl"
    vs_router_veto50 = args.out_dir / f"kp_router_pipe_or_veto50_lb20_daily_vs_pipe_{suffix}.jsonl"
    _write_guard(vs_pipe, mode.selected, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_guard(vs_take, mode.selected, take.daily, "take_all_daily_mean")
    _write_guard(vs_pure_mode, pure_mode.selected, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_guard(vs_p_plus, p_plus.selected, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_guard(vs_p_minus, p_minus.selected, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_slot_guard(vs_p_plus_slot, p_plus_slot, pipe_slot.daily, "pipe_k50_p_top3_slotcash_daily")
    _write_slot_guard(vs_p_minus_slot, p_minus_slot, pipe_slot.daily, "pipe_k50_p_top3_slotcash_daily")
    _write_daily_guard(vs_veto50_redeploy, veto50_redeploy, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_slot_guard(vs_veto50, veto50, pipe_slot.daily, "pipe_k50_p_top3_slotcash_daily")
    _write_daily_guard(vs_recent_bad0, recent_bad0, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_slot_guard(vs_recent_bad0_slot, recent_bad0_slot, pipe_slot.daily, "pipe_k50_p_top3_slotcash_daily")
    _write_daily_guard(vs_router_pminus, router_pminus, pipe.daily, "pipe_k50_p_top3_daily_mean")
    _write_daily_guard(vs_router_veto50, router_veto50, pipe.daily, "pipe_k50_p_top3_daily_mean")
    rows_path = args.out_dir / f"kp_mode_rotation_oos_rows_{suffix}.parquet"
    df.to_parquet(rows_path, index=False)
    report_path = args.out_dir / f"kp_mode_rotation_oos_{suffix}.md"
    report_path.write_text(_report(df, variants, {
        "mode_vs_pipe": vs_pipe,
        "mode_vs_take_all": vs_take,
        "mode_conf_only_vs_pipe": vs_pure_mode,
        "p_plus_mode_050_vs_pipe_slot_guard": vs_p_plus,
        "p_minus_hot_mode_050_vs_pipe": vs_p_minus,
        "p_plus_mode_050_slotcash_vs_pipe_slotcash": vs_p_plus_slot,
        "p_minus_hot_mode_050_slotcash_vs_pipe_slotcash": vs_p_minus_slot,
        "bad_mode_veto_conf50_redeploy_daily_vs_pipe": vs_veto50_redeploy,
        "bad_mode_veto_conf50_slotcash_vs_pipe_slotcash": vs_veto50,
        "bad_recent_avg_lt0_n8_redeploy_daily_vs_pipe": vs_recent_bad0,
        "bad_recent_avg_lt0_n8_slotcash_vs_pipe_slotcash": vs_recent_bad0_slot,
        "router_pipe_or_p_minus_hot_lb20_daily_vs_pipe": vs_router_pminus,
        "router_pipe_or_veto50_lb20_daily_vs_pipe": vs_router_veto50,
        "rows": rows_path,
    }), encoding="utf-8")

    print(f"wrote {report_path}")
    print(f"wrote {vs_pipe}")
    print(f"wrote {vs_take}")
    print(f"wrote {vs_pure_mode}")
    print(f"wrote {vs_p_plus}")
    print(f"wrote {vs_p_minus}")
    print(f"wrote {vs_p_plus_slot}")
    print(f"wrote {vs_p_minus_slot}")
    print(f"wrote {vs_veto50_redeploy}")
    print(f"wrote {vs_veto50}")
    print(f"wrote {vs_recent_bad0}")
    print(f"wrote {vs_recent_bad0_slot}")
    print(f"wrote {vs_router_pminus}")
    print(f"wrote {vs_router_veto50}")
    print(f"wrote {rows_path}")
    for variant in variants:
        print(f"{variant.name}: avg_daily={variant.avg_daily:+.3f}% sum={variant.simple_sum:+.3f}% trades={len(variant.selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
