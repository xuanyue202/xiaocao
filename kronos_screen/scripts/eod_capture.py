"""End-of-day capture for continuous optimization.

After 15:00, for each of the day's candidates, snapshot today's TICK order-flow
(each_trade: buy/sell 逐笔) + intraday minute path. These are NOT entry-decision
features (ticks exist only after 9:30) — they are accumulated to (a) enrich the
prior-day P model over time, (b) build exit/intraday models, (c) grow the
dataset for getting more out of Kronos later.

Tick data is latest-only -> run same-day after close (past-date runs are flagged
is_live=false). Appends compact features to output/live/eod_features.jsonl;
raw ticks optional (--save-raw) under output/live/eod/<date>/.
"""
from __future__ import annotations
import argparse, gzip, json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.config.settings import load_settings
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache
from xiaocao.datasource.api_source import ApiDataSource
from xiaocao.strategy import run_strategy

EOD = Path("output/live/eod_features.jsonl")
SNAP = Path("output/live/signal_snapshots.jsonl")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def tick_features(ticks):
    if not ticks:
        return {}
    df = pd.DataFrame(ticks)
    amt = pd.to_numeric(df.get("amt"), errors="coerce").fillna(0).to_numpy()
    buy = (df.get("flag") == "buy").to_numpy()
    tt = df.get("tradeTime").astype(str).str.zfill(6).to_numpy() if "tradeTime" in df else np.array([""] * len(df))
    tot = amt.sum() + 1e-9
    net = amt[buy].sum() - amt[~buy].sum()
    big = amt >= (np.quantile(amt, 0.9) if len(amt) > 10 else amt.max() + 1)  # 大单=额前10%
    big_net = amt[big & buy].sum() - amt[big & ~buy].sum()
    late = tt >= "143000"
    late_net = amt[late & buy].sum() - amt[late & ~buy].sum()
    return {
        "tk_n": int(len(df)),
        "tk_net_ratio": float(net / tot),                 # 净主买额占比
        "tk_buy_ratio": float(amt[buy].sum() / tot),      # 主买额占比
        "tk_big_net_ratio": float(big_net / tot),         # 大单净额占比
        "tk_late_net_ratio": float(late_net / tot),       # 尾盘净主买占比
        "tk_buycnt_ratio": float(buy.mean()),             # 买单笔数占比
        "tk_avg_amt": float(amt.mean()),
        "tk_amt_total": float(tot),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="today")
    ap.add_argument("--count", type=int, default=20000, help="ticks per stock (latest N of today)")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--save-raw", action="store_true", help="also gzip raw ticks per stock")
    a = ap.parse_args()
    date_iso = _today() if a.date == "today" else a.date
    is_live = (date_iso == _today())
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache(a.cache))

    # candidate codes: prefer today's recommendation snapshot, else re-run strategy
    codes = []
    if SNAP.exists():
        snaps = [json.loads(l) for l in open(SNAP, encoding="utf-8") if l.strip()]
        codes = sorted({r["code"] for r in snaps if r.get("date") == date_iso and r.get("code")})
    if not codes:
        src = ApiDataSource(cli, hpqb_state=0, lpdx_state=0)
        rows = run_strategy(date_iso, src, profile="validated_v5", adaptive_modes=False)
        codes = sorted({r.get("code") for r in rows if r.get("code")})
    if not codes:
        print(f"{date_iso}: no candidates"); return

    EOD.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = EOD.parent / "eod" / date_iso
    if a.save_raw:
        raw_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    n_ok = 0
    with EOD.open("a", encoding="utf-8") as fh:
        for code in codes:
            try:
                ticks = cli.each_trade(code, count=a.count)
            except Exception:
                ticks = []
            feats = tick_features(ticks)
            if not feats:
                continue
            if a.save_raw and ticks:
                with gzip.open(raw_dir / f"{code}_ticks.json.gz", "wt", encoding="utf-8") as zf:
                    json.dump(ticks, zf, ensure_ascii=False, default=str)
            rec = {"captured_at": ts, "date": date_iso, "is_live": is_live, "code": code, **feats}
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            n_ok += 1
    print(f"{date_iso}: EOD tick features for {n_ok}/{len(codes)} codes -> {EOD} (is_live={is_live}, raw={'yes' if a.save_raw else 'no'})")


if __name__ == "__main__":
    main()
