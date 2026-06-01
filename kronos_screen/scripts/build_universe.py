"""Broad-universe cross-section for a high-power IC validation.

For a subsample of trading days, take EVERY cached code with enough history and
a same-day open + next-day close, label = open[D]->close[D+1] return (the
secondary next_close definition), context = bars < D. Hundreds of names/day
gives a far more powerful within-day IC test than the ~7 mode candidates/day.
"""
from __future__ import annotations
import argparse, pickle
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.api.cache import iter_cached_responses

FEATS = ["open", "high", "low", "close", "vol", "amt"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--out", default="kronos_screen/data/uni")
    ap.add_argument("--every", type=int, default=6, help="take every Nth trading day")
    ap.add_argument("--min-ctx", type=int, default=60)
    ap.add_argument("--lookback", type=int, default=400)
    ap.add_argument("--max-codes-per-day", type=int, default=500)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    # build per-code date->row
    by = defaultdict(dict)
    for data in iter_cached_responses(a.cache, "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if isinstance(k, dict) and k.get("code") and k.get("tradeDate"):
                by[k["code"]][k["tradeDate"]] = k
    # global trading-day axis
    alldates = sorted({d for c in by.values() for d in c})
    didx = {d: i for i, d in enumerate(alldates)}
    sample_days = alldates[a.lookback // 5:: a.every]  # skip very early (thin history)

    contexts = {}; rows = []; rid = 0
    rng = np.random.default_rng(0)
    for code, days in by.items():
        ds = sorted(days)
        arr_all = {d: days[d] for d in ds}
        for D in ds:
            if D not in didx:
                continue
        # handled below per sample-day
    # iterate by day for efficiency
    for D in sample_days:
        i = didx[D]
        if i + 1 >= len(alldates):
            continue
        Dn = alldates[i + 1]
        cand = []
        for code, days in by.items():
            if D in days and Dn in days:
                cand.append(code)
        rng.shuffle(cand)
        cand = cand[: a.max_codes_per_day]
        for code in cand:
            days = by[code]
            prior = [d for d in sorted(days) if d < D]
            if len(prior) < a.min_ctx:
                continue
            o = days[D].get("open"); cN = days[Dn].get("close")
            if not o or not cN or o <= 0:
                continue
            prior = prior[-a.lookback:]
            ctx = np.array([[days[d][f] for f in FEATS] for d in prior], dtype=np.float32)
            if not np.isfinite(ctx).all():
                continue
            contexts[rid] = {"ohlcav": ctx, "dates": prior}
            rows.append({"row_id": rid, "buyDate": D, "code": code,
                         "returnPct": (cN / o - 1) * 100})
            rid += 1
    meta = pd.DataFrame(rows)
    meta.to_parquet(out / "meta.parquet", index=False)
    pickle.dump(contexts, open(out / "contexts.pkl", "wb"), protocol=4)
    print(f"days={len(set(meta.buyDate))} rows={len(meta)} "
          f"median_per_day={int(meta.groupby('buyDate').size().median())}", flush=True)


if __name__ == "__main__":
    main()
