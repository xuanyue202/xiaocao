"""Build prior-day MINUTE K-line contexts for Kronos (the microstructure that
daily bars miss). For each candidate: prior trading day's 1-min trades (cached)
-> 5-min OHLCV bars (48/day) -> Kronos context. Decision-time-safe (D-1 done).
"""
from __future__ import annotations
import argparse, pickle
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.config.settings import load_settings
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache, iter_cached_responses


def axis(cache):
    ds = set()
    for data in iter_cached_responses(cache, "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate"):
                    ds.add(k["tradeDate"])
    return sorted(ds)


def to_5min(rows):
    df = pd.DataFrame(rows)
    if df.empty or "trade" not in df:
        return None
    df = df[pd.to_numeric(df["trade"], errors="coerce").notna()].copy()
    if len(df) < 60:
        return None
    px = pd.to_numeric(df["trade"], errors="coerce").to_numpy()
    vol = pd.to_numeric(df.get("vol"), errors="coerce").fillna(0).to_numpy()
    amt = pd.to_numeric(df.get("amt"), errors="coerce").fillna(0).to_numpy()
    tt = df["tradeTime"].astype(str).str.zfill(4).to_numpy()
    td = str(df["tradeDate"].iloc[0])
    n = len(px); bars = []; stamps = []
    for s in range(0, n, 5):
        e = min(s + 5, n)
        seg = px[s:e]
        bars.append([seg[0], seg.max(), seg.min(), seg[-1], vol[s:e].sum(), amt[s:e].sum()])
        hhmm = tt[s]
        stamps.append(f"{td[:4]}-{td[4:6]}-{td[6:]} {hhmm[:2]}:{hhmm[2:]}:00")
    return np.array(bars, dtype=np.float32), stamps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-ds", default="kronos_screen/data/ds")
    ap.add_argument("--out", default="kronos_screen/data/ds_min")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    meta = pd.read_parquet(Path(a.src_ds) / "meta.parquet").reset_index(drop=True)
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache(a.cache))
    ax = axis(a.cache); pos = {d: i for i, d in enumerate(ax)}
    contexts = {}; keep = []
    miss = 0
    for i, r in enumerate(meta.itertuples()):
        if r.buyDate not in pos or pos[r.buyDate] == 0:
            miss += 1; continue
        prev = ax[pos[r.buyDate] - 1]
        try:
            rows = cli.minute_line(r.code, trade_date=prev, count=241)
        except Exception:
            miss += 1; continue
        rows = rows if isinstance(rows, list) else (rows.get("data") if isinstance(rows, dict) else None)
        res = to_5min(rows) if rows else None
        if res is None or not np.isfinite(res[0]).all():
            miss += 1; continue
        contexts[int(r.row_id)] = {"ohlcav": res[0], "dates": res[1]}
        keep.append(int(r.row_id))
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(meta)} ok={len(keep)} miss={miss}", flush=True)
    meta[meta["row_id"].isin(keep)].to_parquet(out / "meta.parquet", index=False)
    pickle.dump(contexts, open(out / "contexts.pkl", "wb"), protocol=4)
    print(f"saved {out}: contexts={len(contexts)} bars/ctx~{len(next(iter(contexts.values()))['ohlcav'])} miss={miss}", flush=True)


if __name__ == "__main__":
    main()
