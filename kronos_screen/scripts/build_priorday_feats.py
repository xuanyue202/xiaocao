"""Prior-day (D-1) intraday microstructure features for each candidate.

Decision-time-safe: buying at D open, the full D-1 session is known. Fetches
historical 1-min bars for (code, D-1) via XiaocaoClient (cached) and derives
小草-style 盘口 features: 尾盘强度, 收盘位置, 振幅, 量比分布, 主力净流入路径, VWAP偏离.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.config.settings import load_settings
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache
from xiaocao.api.cache import iter_cached_responses


def trading_axis(cache):
    ds = set()
    for data in iter_cached_responses(cache, "/stock/date_kline"):
        if isinstance(data, list):
            for k in data:
                if isinstance(k, dict) and k.get("tradeDate"):
                    ds.add(k["tradeDate"])
    return sorted(ds)


def feats_from_minutes(rows):
    df = pd.DataFrame(rows)
    if df.empty or "trade" not in df:
        return None
    px = pd.to_numeric(df["trade"], errors="coerce").to_numpy()
    vol = pd.to_numeric(df.get("vol"), errors="coerce").to_numpy()
    amt = pd.to_numeric(df.get("amt"), errors="coerce").to_numpy()
    mainin = pd.to_numeric(df.get("mainIn"), errors="coerce").to_numpy() if "mainIn" in df else None
    trend = pd.to_numeric(df.get("trendLine"), errors="coerce").to_numpy() if "trendLine" in df else None
    pcr = pd.to_numeric(df.get("pctChangeRate"), errors="coerce").to_numpy()
    fin = np.isfinite(px); px = px[fin]
    if len(px) < 30:
        return None
    n = len(px); o = px[0]; c = px[-1]; hi = px.max(); lo = px.min()
    v = vol[:n] if vol is not None else np.ones(n)
    am = amt[:n] if amt is not None else np.zeros(n)
    vwap = (px * v).sum() / (v.sum() + 1e-9)
    tail = max(1, n // 8); head = max(1, n // 8); q = max(1, n // 4)
    rets = np.diff(px) / (px[:-1] + 1e-9)
    out = {
        "pd_ret": c / o - 1.0,
        "pd_tail_ret": c / px[-tail] - 1.0,
        "pd_head_ret": px[head] / o - 1.0,
        "pd_close_pos": (c - lo) / (hi - lo + 1e-9),
        "pd_amplitude": (hi - lo) / (o + 1e-9),
        "pd_vwap_dev": c / (vwap + 1e-9) - 1.0,
        "pd_close_pcr": float(pcr[-1]) if len(pcr) else np.nan,
        # NEW: 三段动量
        "pd_q1_ret": px[q] / o - 1.0,
        "pd_q4_ret": c / px[-q] - 1.0,
        "pd_late_accel": (c / px[-q] - 1.0) - (px[q] / o - 1.0),   # 尾盘 vs 早盘加速
        # NEW: 分钟涨跌结构
        "pd_upmin_ratio": float((rets > 0).mean()),
        "pd_ret_std": float(np.std(rets)),
        "pd_max_drawup": float((np.maximum.accumulate(px) / px - 1.0).max()),  # 盘中最大回撤(从高点)
        # NEW: 量价配合
        "pd_tail_volshare": v[-tail:].sum() / (v.sum() + 1e-9),
        "pd_head_volshare": v[:head].sum() / (v.sum() + 1e-9),
        "pd_vol_skew": (v[-q:].sum() - v[:q].sum()) / (v.sum() + 1e-9),  # 量能前后偏移
    }
    if mainin is not None and np.isfinite(mainin).any():
        mi = np.nan_to_num(mainin[:n]); ta = am.sum() + 1e-9
        out["pd_mainin_sum"] = float(mi.sum())
        out["pd_mainin_tail"] = float(mi[-tail:].sum())
        out["pd_mainin_trend"] = float(mi[-tail:].sum() - mi[:head].sum())
        out["pd_mainin_amt_ratio"] = float(mi.sum() / ta)        # 主力净流入占成交额
        out["pd_mainin_late_ratio"] = float(mi[-q:].sum() / ta)  # 尾盘主力占比
    if trend is not None and np.isfinite(trend).any():
        tr = np.nan_to_num(trend[:n])
        out["pd_trend_end"] = float(tr[-1])
        out["pd_trend_slope"] = float(tr[-1] - tr[max(0, n - q)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="kronos_screen/data/ds")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet")
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache(a.cache))
    axis = trading_axis(a.cache); pos = {d: i for i, d in enumerate(axis)}

    out_rows = []
    miss = 0
    for i, r in enumerate(meta.itertuples()):
        bd = r.buyDate  # dashed iso, matches date_kline tradeDate
        if bd not in pos or pos[bd] == 0:
            miss += 1; continue
        prev_iso = axis[pos[bd] - 1]
        try:
            rows = cli.minute_line(r.code, trade_date=prev_iso, count=241)
        except Exception:
            miss += 1; continue
        rows = rows if isinstance(rows, list) else (rows.get("data") if isinstance(rows, dict) else None)
        f = feats_from_minutes(rows) if rows else None
        if f is None:
            miss += 1; continue
        f["row_id"] = int(r.row_id); out_rows.append(f)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(meta)} ok={len(out_rows)} miss={miss}", flush=True)
    df = pd.DataFrame(out_rows)
    df.to_parquet(ds / "priorday_feats.parquet", index=False)
    print(f"saved priorday_feats.parquet rows={len(df)} cols={[c for c in df.columns if c!='row_id']} miss={miss}", flush=True)


if __name__ == "__main__":
    main()
