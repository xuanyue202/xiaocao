"""Backtest quality-governor policies under slot-cash sizing.

Default input is the local gate-ablation `picks.csv` built from cached OOS
labels. The script is deliberately conservative:

- filtered slots stay in cash;
- no capital is reallocated from filtered names into survivors;
- fee is subtracted from kept trades;
- board-lot and historical fill-window filters are applied only when the input
  supplies the needed columns, and are reported in metadata otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from quality_governor import ensure_quality_fields, num  # noqa: E402


DEFAULT_PICKS = Path("output/gate_ablation_20260617/picks.csv")
DEFAULT_OUT = Path("output/quality_governor_backtest")


def _policy_mask(df: pd.DataFrame, policy: str) -> pd.Series:
    if policy == "no_governor":
        return pd.Series(True, index=df.index)
    if policy == "primary_ge_150":
        return df["primary_score"].astype(float) >= 150.0
    if policy == "hard_combo_p_gt_neg1_primary_ge_150":
        return (df["primary_score"].astype(float) >= 150.0) & (df["P"].astype(float) > -1.0)
    raise ValueError(f"unknown policy: {policy}")


def _metrics(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {
            "days": 0,
            "avg_day_ret": np.nan,
            "cum_ret": np.nan,
            "sharpe": np.nan,
            "max_dd": np.nan,
            "win_days": np.nan,
        }
    curve = np.cumprod(1.0 + a / 100.0)
    peak = np.maximum.accumulate(curve)
    sd = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
    return {
        "days": int(len(a)),
        "avg_day_ret": float(np.mean(a)),
        "cum_ret": float((curve[-1] - 1.0) * 100.0),
        "sharpe": float(np.mean(a) / sd * np.sqrt(240.0)) if sd > 0 else np.nan,
        "max_dd": float(np.min(curve / peak - 1.0) * 100.0),
        "win_days": float(np.mean(a > 0) * 100.0),
    }


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["ret", "P", "primary", "primary_score"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "primary_score" not in out.columns:
        out["primary_score"] = np.nan
    if "primary" in out.columns:
        out["primary_score"] = out["primary_score"].where(out["primary_score"].notna(), out["primary"])
    rows = []
    for rec in out.to_dict("records"):
        rec = ensure_quality_fields(rec)
        if pd.isna(rec.get("primary_score")) and rec.get("primary") is not None:
            rec["primary_score"] = rec.get("primary")
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"])
    out["ret"] = pd.to_numeric(out["ret"], errors="coerce").fillna(0.0)
    out["P"] = pd.to_numeric(out["P"], errors="coerce")
    out["primary_score"] = pd.to_numeric(out["primary_score"], errors="coerce").fillna(0.0)
    return out


def _evaluate(
    df: pd.DataFrame,
    *,
    policies: list[str],
    fee_rate: float,
    price_col: str | None,
    slot_notional: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fee_pct = fee_rate * 2.0 * 100.0
    daily_rows: list[dict] = []
    summary_rows: list[dict] = []
    fn_rows: list[dict] = []
    has_price = bool(price_col and price_col in df.columns)
    for (dataset, date), day in df.groupby(["dataset", "date"], sort=True):
        base_n = len(day)
        for policy in policies:
            mask = _policy_mask(day, policy).fillna(False)
            kept = day.loc[mask].copy()
            rejected = day.loc[~mask].copy()
            contrib = []
            for _, row in kept.iterrows():
                deploy_frac = 1.0
                if has_price:
                    price = num(row.get(price_col))
                    if price and price > 0 and slot_notional > 0:
                        shares = int((slot_notional / (price * (1.0 + fee_rate))) / 100) * 100
                        deploy_frac = max(0.0, min(1.0, shares * price / slot_notional))
                    else:
                        deploy_frac = 0.0
                contrib.append((float(row["ret"]) - fee_pct) * deploy_frac)
            day_ret = float(np.sum(contrib) / base_n) if base_n else 0.0
            daily_rows.append({
                "dataset": dataset,
                "date": date.date().isoformat(),
                "policy": policy,
                "base_slots": base_n,
                "kept_slots": len(kept),
                "cash_slots": base_n - len(kept),
                "ret": day_ret,
            })
            fn_rows.append({
                "dataset": dataset,
                "date": date.date().isoformat(),
                "policy": policy,
                "rejected_trades": len(rejected),
                "rejected_positive_trades": int((rejected["ret"] > 0).sum()),
                "rejected_avg_ret": float(rejected["ret"].mean()) if len(rejected) else np.nan,
            })
    daily = pd.DataFrame(daily_rows)
    false_negative = pd.DataFrame(fn_rows)
    for (dataset, policy), group in daily.groupby(["dataset", "policy"], sort=True):
        m = _metrics(group["ret"].tolist())
        rejected = false_negative[
            (false_negative["dataset"] == dataset) & (false_negative["policy"] == policy)
        ]
        rej = int(rejected["rejected_trades"].sum())
        rej_pos = int(rejected["rejected_positive_trades"].sum())
        summary_rows.append({
            "dataset": dataset,
            "policy": policy,
            **m,
            "rejected_trades": rej,
            "rejected_positive_trades": rej_pos,
            "rejected_positive_rate": float(rej_pos / rej * 100.0) if rej else np.nan,
        })
    return pd.DataFrame(summary_rows), daily, false_negative


def _walk_forward(daily: pd.DataFrame, policies: list[str], min_train_days: int, test_days: int) -> pd.DataFrame:
    rows: list[dict] = []
    for dataset, ds in daily.groupby("dataset", sort=True):
        dates = sorted(ds["date"].unique())
        start = min_train_days
        while start < len(dates):
            train_dates = dates[:start]
            test_dates = dates[start:start + test_days]
            if not test_dates:
                break
            train = ds[ds["date"].isin(train_dates)]
            test = ds[ds["date"].isin(test_dates)]
            train_scores = {
                policy: float(train.loc[train["policy"] == policy, "ret"].mean())
                for policy in policies
            }
            chosen = max(policies, key=lambda p: train_scores[p])
            no_gate_test = float(test.loc[test["policy"] == "no_governor", "ret"].mean())
            chosen_test = float(test.loc[test["policy"] == chosen, "ret"].mean())
            rows.append({
                "dataset": dataset,
                "train_days": len(train_dates),
                "test_days": len(test_dates),
                "chosen_policy": chosen,
                "train_ret": train_scores[chosen],
                "test_ret": chosen_test,
                "no_governor_test_ret": no_gate_test,
                "test_edge_vs_no_governor": chosen_test - no_gate_test,
            })
            start += test_days
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", default=str(DEFAULT_PICKS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--fee-rate", type=float, default=0.0001)
    ap.add_argument("--price-col", default=None,
                    help="optional fill/entry price column for board-lot sizing")
    ap.add_argument("--slot-notional", type=float, default=10000.0)
    ap.add_argument("--min-train-days", type=int, default=40)
    ap.add_argument("--test-days", type=int, default=20)
    args = ap.parse_args()

    picks_path = Path(args.picks)
    if not picks_path.exists():
        raise SystemExit(f"missing picks file: {picks_path}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(picks_path)
    if "variant" in df.columns:
        df = df[df["variant"] == "no_gate_k50_p_top3"].copy()
    df = _prepare(df)
    policies = ["no_governor", "primary_ge_150", "hard_combo_p_gt_neg1_primary_ge_150"]
    summary, daily, false_negative = _evaluate(
        df,
        policies=policies,
        fee_rate=float(args.fee_rate),
        price_col=args.price_col,
        slot_notional=float(args.slot_notional),
    )
    walk = _walk_forward(daily, policies, int(args.min_train_days), int(args.test_days))
    summary.to_csv(out_dir / "summary.csv", index=False)
    daily.to_csv(out_dir / "daily.csv", index=False)
    false_negative.to_csv(out_dir / "false_negative.csv", index=False)
    walk.to_csv(out_dir / "walk_forward.csv", index=False)
    metadata = {
        "picks": str(picks_path),
        "fee_rate": float(args.fee_rate),
        "slot_cash_sizing": True,
        "board_lot_applied": bool(args.price_col and args.price_col in df.columns),
        "fill_window_applied": {"fill_window_low", "fill_limit_price"}.issubset(df.columns),
        "policies": policies,
        "note": "fill-window constraints require historical fill_window_low/fill_limit_price columns",
    }
    with (out_dir / "metadata.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(summary.to_string(index=False))
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
