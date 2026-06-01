"""Join captured live snapshots with realized next-close returns -> (1) A/B
verdict (variant A = K->P vs variant B = K->P + auction imbalance vs take-all),
(2) accumulated labeled training rows for future models.

Run any time after the outcome day's close is available (T+1+). Idempotent.
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.config.settings import load_settings
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache

SNAP = Path("output/live/signal_snapshots.jsonl")
TRAIN = Path("output/live/training_rows.parquet")
DEFAULT_FEE_RATE = 0.0001


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", default=str(SNAP))
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--live-only", action="store_true", help="only score is_live=true rows")
    ap.add_argument("--fee-rate", type=float, default=DEFAULT_FEE_RATE,
                    help="one-way transaction fee rate, e.g. 0.0001 = 1bp")
    a = ap.parse_args()
    if not Path(a.snap).exists():
        print("no snapshots yet:", a.snap); return
    recs = [json.loads(l) for l in open(a.snap, encoding="utf-8") if l.strip()]
    df = pd.DataFrame(recs).drop_duplicates(["date", "code"], keep="last")
    if a.live_only:
        df = df[df["is_live"] == True]
    if df.empty:
        print("no rows to score"); return

    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache(a.cache))

    # realized next-close return per (date, code): open[D] -> close[D+1]
    rets = {}
    for code in df["code"].unique():
        try:
            kl = cli.date_kline(code, count=400, freq="D", adj="qfq")
        except Exception:
            continue
        if not isinstance(kl, list):
            continue
        ser = {r["tradeDate"]: r for r in kl if isinstance(r, dict) and r.get("tradeDate")}
        dts = sorted(ser)
        for d in df.loc[df.code == code, "date"].unique():
            if d not in dts:
                continue
            i = dts.index(d)
            if i + 1 >= len(dts):
                continue  # outcome not yet available
            o = df.loc[(df.date == d) & (df.code == code), "open"].iloc[0]
            o = o or ser[d].get("open")
            cN = ser[dts[i + 1]].get("close")
            if o and cN:
                entry = float(o)
                exit_price = float(cN)
                gross_ret = (exit_price / entry - 1) * 100
                net_ret = ((exit_price * (1 - a.fee_rate)) / (entry * (1 + a.fee_rate)) - 1) * 100
                rets[(d, code)] = (gross_ret, net_ret)
    df["realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[0] for r in df.itertuples()
    ]
    df["net_realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[1] for r in df.itertuples()
    ]
    df["fee_rate"] = a.fee_rate
    scored = df[df["realized_ret"].notna()].copy()
    print(f"snapshots={len(df)}  scored(outcome known)={len(scored)}  pending={len(df)-len(scored)}")
    if scored.empty:
        print("no outcomes available yet — re-run after T+1 close."); return

    # accumulate training rows
    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(TRAIN, index=False)
    print(f"accumulated {len(scored)} labeled training rows -> {TRAIN}")

    # A/B by day
    def day_mean(mask_col, ret_col):
        per = []
        for d, g in scored.groupby("date"):
            sel = g[g[mask_col] == True] if mask_col else g
            if len(sel):
                per.append(sel[ret_col].mean())
        return np.array(per)
    ta = day_mean(None, "net_realized_ret")
    A = day_mean("kp_star", "net_realized_ret")
    B = day_mean("vb_star", "net_realized_ret")
    print(f"\nA/B over {scored['date'].nunique()} live days ({scored.date.min()}..{scored.date.max()}):")
    print(f"  net of fees   : one-way fee={a.fee_rate:.4%}")
    print(f"  take-all      : {ta.mean():+.2f}%/day  win {(scored.net_realized_ret>0).mean()*100:.0f}%")
    sa = scored[scored.kp_star == True]; sb = scored[scored.vb_star == True]
    print(f"  A  K->P        : {A.mean():+.2f}%/day  win {(sa.net_realized_ret>0).mean()*100:.0f}%  (n={len(sa)})")
    print(f"  B  K->P+auction: {B.mean():+.2f}%/day  win {(sb.net_realized_ret>0).mean()*100:.0f}%  (n={len(sb)})")
    if len(A) >= 8:
        from scipy.stats import ttest_rel
        n = min(len(A), len(B), len(ta))
        print(f"  paired vs take-all: A p={ttest_rel(A[:n],ta[:n])[1]:.3f}  B p={ttest_rel(B[:n],ta[:n])[1]:.3f}")


if __name__ == "__main__":
    main()
