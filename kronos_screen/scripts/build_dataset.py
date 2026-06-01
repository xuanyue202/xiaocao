"""Assemble the secondary-screening training set.

Inputs (all cache-only, no network):
  - a full-year xiaocao backtest trades.csv (structured features + next_close label)
  - the date_kline SQLite cache (per-code daily OHLCV for Kronos context)

Outputs (under --out):
  - meta.parquet     : one row per labeled candidate (features + label + board + ctx_len)
  - contexts.pkl     : {row_id: {"ohlcav": np.float32[N,6], "dates": [iso,...]}}

Discipline: Kronos context for a buy on day D uses ONLY bars with tradeDate < D
(decision at D-open can see <= D-1 close). No look-ahead.
"""
from __future__ import annotations
import argparse, json, pickle, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.api.cache import iter_cached_responses

PRICE_COLS = ["open", "high", "low", "close", "vol", "amt"]  # -> Kronos open,high,low,close,volume,amount


def classify_board(code: str) -> str:
    num, _, ex = code.partition(".")
    if ex == "BJSE" or num[:2] in ("43", "83", "87", "88") or num[:3] == "920":
        return "北交"
    if ex == "XSHG" and num[:3] in ("688", "689"):
        return "科创"
    if ex == "XSHE" and num[:3] in ("300", "301"):
        return "创业"
    return "主板"


def build_kline_index(cache_path: str) -> dict[str, pd.DataFrame]:
    by_code: dict[str, dict[str, list]] = {}
    for data in iter_cached_responses(cache_path, "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            code = k.get("code"); td = k.get("tradeDate")
            if not code or not td:
                continue
            rec = by_code.setdefault(code, {"tradeDate": []})
            rec["tradeDate"].append(td)
            for c in PRICE_COLS:
                rec.setdefault(c, []).append(k.get(c))
    out: dict[str, pd.DataFrame] = {}
    for code, rec in by_code.items():
        df = pd.DataFrame(rec).drop_duplicates("tradeDate").sort_values("tradeDate")
        out[code] = df.reset_index(drop=True)
    return out


def load_signal_feats(signals_dir: Path) -> dict[tuple, dict]:
    """(date, code, mode) -> extra decision-time features from signals_*.json.
    Excludes pctChange (full-day move = look-ahead at open)."""
    out: dict[tuple, dict] = {}
    for f in signals_dir.glob("signals_*.json"):
        try:
            arr = json.load(open(f))
        except Exception:
            continue
        for s in arr:
            key = (s.get("date"), s.get("code"), s.get("mode"))
            out[key] = {
                "jssb": s.get("jssb"),
                "direction": bool(s.get("direction")),
                "directionRank": s.get("directionRank"),
                "categoryRank": s.get("categoryRank"),
                "is_main_line": bool(s.get("is_main_line")),
                "n_blocks": len(s.get("blockCodeList") or []),
                "n_cats": len(s.get("blockCategoryCodeList") or []),
                "excIndustry": s.get("excIndustryCode"),
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", required=True)
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lookback", type=int, default=400)
    ap.add_argument("--min-ctx", type=int, default=60)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    trades = pd.read_csv(args.trades)
    trades.columns = [c.lstrip("﻿") for c in trades.columns]
    sig_feats = load_signal_feats(Path(args.trades).parent)
    print(f"trades rows={len(trades)}  dates {trades.buyDate.min()}..{trades.buyDate.max()}  sig_feats={len(sig_feats)}", flush=True)

    klines = build_kline_index(args.cache)
    print(f"kline codes={len(klines)}", flush=True)

    feat_cols = ["xcjw", "cjs", "jsjl", "openPctChange"]
    meta_rows = []
    contexts: dict[int, dict] = {}
    dropped = defaultdict(int)

    for i, r in trades.iterrows():
        code = r["code"]; bd = r["buyDate"]
        df = klines.get(code)
        if df is None:
            dropped["no_kline"] += 1; continue
        ctx = df[df["tradeDate"] < bd]
        if len(ctx) < args.min_ctx:
            dropped["short_ctx"] += 1; continue
        ctx = ctx.tail(args.lookback)
        arr = ctx[PRICE_COLS].to_numpy(dtype=np.float32)
        if not np.isfinite(arr).all():
            dropped["nan_ctx"] += 1; continue
        rid = int(i)
        contexts[rid] = {"ohlcav": arr, "dates": ctx["tradeDate"].tolist()}
        ret = float(r["returnPct"])
        extra = sig_feats.get((bd, code, r["mode"]), {})
        meta_rows.append({
            "row_id": rid, "buyDate": bd, "sellDate": r["sellDate"], "code": code,
            "name": r.get("name"), "mode": r["mode"], "board": classify_board(code),
            **{c: pd.to_numeric(r.get(c), errors="coerce") for c in feat_cols},
            "regime": r.get("regime"), "isMainLine": r.get("isMainLine"),
            "isBigCap": r.get("isBigCap"),
            "jssb": pd.to_numeric(extra.get("jssb"), errors="coerce"),
            "direction": extra.get("direction"),
            "directionRank": pd.to_numeric(extra.get("directionRank"), errors="coerce"),
            "categoryRank": pd.to_numeric(extra.get("categoryRank"), errors="coerce"),
            "is_main_line": extra.get("is_main_line"),
            "n_blocks": extra.get("n_blocks"), "n_cats": extra.get("n_cats"),
            "excIndustry": extra.get("excIndustry"),
            "returnPct": ret, "win": int(ret > 0), "ctx_len": len(ctx),
        })

    meta = pd.DataFrame(meta_rows)
    meta.to_parquet(out / "meta.parquet", index=False)
    with open(out / "contexts.pkl", "wb") as f:
        pickle.dump(contexts, f, protocol=4)

    print(f"kept={len(meta)} dropped={dict(dropped)}", flush=True)
    print(f"label: win_rate={meta.win.mean()*100:.1f}%  avg_ret={meta.returnPct.mean():+.2f}%", flush=True)
    print("by board:\n", meta.groupby("board").agg(n=("win","size"), win=("win","mean"), ret=("returnPct","mean")), flush=True)
    print(f"saved -> {out}/meta.parquet + contexts.pkl", flush=True)


if __name__ == "__main__":
    sys.exit(main())
