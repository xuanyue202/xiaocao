"""Backtest a deploy-ratio gate: should the paper book cut/stop buying on
regime-negative days?

Earlier finding (STATE.md): no decision-time environmental gate improved the
SCREEN consistently. This tests the narrower question — gating the DEPLOY
(buy / don't buy the whole basket) — which never got its own train+test pass.

Day-level basket = equal-weight mean returnPct (open[D] -> close[D+1]) of all
mode candidates that day (kronos_screen/data/ds/meta.parquet, ~200 days).
Gates use ONLY prior-day index data (decision-time safe at 9:25):
  g_prev_neg   prior-day SSE close-to-close return < 0
  g_below_ma20 prior close < MA20(prior closes)
  g_2d_drop    2-day SSE return < -1%
Verdict discipline: a gate ships ONLY if basket(gate-on) < basket(gate-off) on
train AND test halves, and the delta keeps its sign across 6mo/3mo windows.
Also prints the take-all baseline health by window (edge decay vs bad-tape).
"""
from __future__ import annotations
import argparse, sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.config.settings import load_settings  # noqa: E402
from xiaocao.api.client import XiaocaoClient        # noqa: E402
from xiaocao.api.cache import SQLiteCache           # noqa: E402

META = ROOT / "kronos_screen/data/ds/meta.parquet"
INDEX_CODE = "000001.XSHG"  # 上证指数


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    a = ap.parse_args()

    meta = pd.read_parquet(META)
    day = meta.groupby("buyDate")["returnPct"].agg(["mean", "count"]).reset_index()
    day.columns = ["date", "basket_ret", "n"]

    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                        cache=SQLiteCache(a.cache))
    kl = cli.date_kline(INDEX_CODE, count=400, freq="D", adj="bfq")
    idx = pd.DataFrame([r for r in kl if isinstance(r, dict)])[["tradeDate", "close"]]
    idx["close"] = idx["close"].astype(float)
    idx = idx.sort_values("tradeDate").reset_index(drop=True)
    idx["ret1"] = idx["close"].pct_change() * 100
    idx["ret2"] = idx["close"].pct_change(2) * 100
    idx["ma20"] = idx["close"].rolling(20).mean()
    # decision-time: signals known at 9:25 of D = computed through D-1 close
    idx["g_prev_neg"] = idx["ret1"] < 0
    idx["g_below_ma20"] = idx["close"] < idx["ma20"]
    idx["g_2d_drop"] = idx["ret2"] < -1.0
    sig = idx.set_index("tradeDate")[["g_prev_neg", "g_below_ma20", "g_2d_drop"]].shift(1)
    # shift(1) on trading-date index: row D carries D-1's signal
    sig = sig.reset_index()

    df = day.merge(sig, left_on="date", right_on="tradeDate", how="inner")
    print(f"days joined: {len(df)}/{len(day)} (candidates {meta.shape[0]})")

    # baseline health by window
    end_dt = datetime.fromisoformat(df["date"].max())
    print("\n-- take-all baseline (mean basket %/day, win-days) --")
    for label, nd in (("ALL", None), ("6mo", 182), ("3mo", 91), ("1mo", 30), ("1wk", 7)):
        sub = df if nd is None else df[df["date"] >= (end_dt - timedelta(days=nd)).date().isoformat()]
        if len(sub):
            print(f"  {label:>4}: {sub['basket_ret'].mean():+6.2f}%/day  "
                  f"win {(sub['basket_ret'] > 0).mean()*100:3.0f}%  (n={len(sub)}d)")

    days_sorted = sorted(df["date"].unique())
    split = days_sorted[int(len(days_sorted) * 0.6)]
    print(f"\n-- deploy gates (train < {split} <= test) --")
    print(f"{'gate':<14}{'set':>6}{'n_on/n_off':>12}{'ret_on':>9}{'ret_off':>9}{'delta':>9}")
    for g in ("g_prev_neg", "g_below_ma20", "g_2d_drop"):
        verdicts = []
        for label, sub in (("ALL", df),
                           ("train", df[df["date"] < split]),
                           ("test", df[df["date"] >= split]),
                           ("6mo", df[df["date"] >= (end_dt - timedelta(days=182)).date().isoformat()]),
                           ("3mo", df[df["date"] >= (end_dt - timedelta(days=91)).date().isoformat()])):
            on = sub[sub[g] == True]["basket_ret"]
            off = sub[sub[g] == False]["basket_ret"]
            if len(on) < 3 or len(off) < 3:
                print(f"{g:<14}{label:>6}{'n/a':>12}")
                continue
            delta = on.mean() - off.mean()
            verdicts.append((label, delta))
            print(f"{g:<14}{label:>6}{f'{len(on)}/{len(off)}':>12}"
                  f"{on.mean():>+9.2f}{off.mean():>+9.2f}{delta:>+9.2f}")
        core = [d for l, d in verdicts if l in ("train", "test", "6mo", "3mo")]
        ok = len(core) >= 4 and all(d < 0 for d in core)
        print(f"{'':<14}VERDICT: {'PASS — gate-on days consistently worse' if ok else 'FAIL — not consistent'}\n")


if __name__ == "__main__":
    main()
