"""Replay intraday stop policies on historical minute data — validate the exit
layer BEFORE deploying it (the 2% sparse trailing stop went live unvalidated
and turned into a "sell the D+1 morning low" rule; decompose_pnl billed it
-0.58%/trade vs next close).

Universe: kronos_screen/data/ds/meta.parquet (mode candidates, ~7/day, 200d).
Entry: open[D] (validated convention). All policies share entry; only exits
differ:
  next_close   sell at close[D+1]                       (validated baseline)
  sparse2      2% trailing from peak @ live checkpoint grid (the old live policy)
  sparse4      4% trailing, same grid
  hard8        8% hard floor intraday + forced 14:55 exit  (the NEW staged policy)
  eod_only     forced 14:55 exit, no stop
  atr          trailing threshold = clip(1.0 x ATR14%, 3, 10), same grid

Caveats (documented, applies EQUALLY to all policies so ranking is fair):
- historical minute bars expose only per-minute trade price (no intraday OHLC),
  so peaks/executions use minute trade prints;
- multi-day limit-down lock (LIMIT_DOWN_NO_BID) is not modeled — exits assumed
  fillable at the checkpoint print.

Verdict discipline: a policy replaces the deployed default ONLY if it beats
next_close consistently on train AND test halves and across 6mo/3mo/1mo/1wk.
"""
from __future__ import annotations
import argparse, sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.config.settings import load_settings  # noqa: E402
from xiaocao.api.client import XiaocaoClient        # noqa: E402
from xiaocao.api.cache import SQLiteCache           # noqa: E402

META = ROOT / "kronos_screen/data/ds/meta.parquet"
CHECKPOINTS = ["0935", "0945", "0955", "1025", "1055", "1325", "1355", "1425", "1455"]
FEE = 0.0001


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _minutes(cli, code: str, date_iso: str) -> list[tuple[str, float]]:
    try:
        rows = cli.minute_line(code, "1min", "bfq", trade_date=date_iso.replace("-", ""), count=241)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = str(r.get("tradeTime") or "")[:4]
        px = _f(r.get("trade"))
        if t and px and px > 0:
            out.append((t, px))
    return out


def _kline(cli, code: str) -> dict[str, dict]:
    try:
        kl = cli.date_kline(code, count=400, freq="D", adj="bfq")
    except Exception:
        return {}
    if not isinstance(kl, list):
        return {}
    return {r["tradeDate"]: r for r in kl if isinstance(r, dict) and r.get("tradeDate")}


def _atr_pct(ser: dict[str, dict], dts: list[str], i: int, n: int = 14) -> float | None:
    """ATR% over the n days ending BEFORE index i (no lookahead)."""
    lo = max(1, i - n)
    trs = []
    for j in range(lo, i):
        h, l = _f(ser[dts[j]].get("high")), _f(ser[dts[j]].get("low"))
        pc = _f(ser[dts[j - 1]].get("close"))
        c = _f(ser[dts[j]].get("close"))
        if not (h and l and pc and c):
            continue
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr / c * 100)
    return sum(trs) / len(trs) if trs else None


def replay_trade(open0: float, close1: float, minutes1: list[tuple[str, float]],
                 atr_pct: float | None) -> dict[str, float]:
    """Exit price per policy for one trade. Entry = open0 on D, T+1 means all
    exits happen on D+1 using its minute prints."""
    def at_or_before(hhmm: str) -> float | None:
        px = None
        for t, p in minutes1:
            if t <= hhmm:
                px = p
            else:
                break
        return px

    last_1455 = at_or_before("1455") or close1

    def sparse_trailing(threshold: float) -> float:
        peak = open0
        k = 0
        for cp in CHECKPOINTS:
            while k < len(minutes1) and minutes1[k][0] <= cp:
                peak = max(peak, minutes1[k][1])
                k += 1
            price = at_or_before(cp)
            if price is None:
                continue
            dd = (peak - price) / peak * 100 if peak > 0 else 0.0
            if dd >= threshold:
                return price
        return last_1455

    atr_thr = min(10.0, max(3.0, atr_pct)) if atr_pct else 4.0
    return {
        "next_close": close1,
        "sparse2": sparse_trailing(2.0),
        "sparse4": sparse_trailing(4.0),
        "hard8": sparse_trailing(8.0),
        "eod_only": last_1455,
        "atr": sparse_trailing(atr_thr),
    }


def net_ret(entry: float, exitp: float) -> float:
    return ((exitp * (1 - FEE)) / (entry * (1 + FEE)) - 1) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--sample", type=int, default=0, help="cap number of trades (most recent first); 0 = all")
    ap.add_argument("--out", default="output/kronos_stop_backtest.parquet")
    a = ap.parse_args()

    meta = pd.read_parquet(META).sort_values("buyDate")
    if a.sample:
        meta = meta.tail(a.sample)
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries,
                        cache=SQLiteCache(a.cache))

    kl_cache: dict[str, dict] = {}
    rows = []
    skipped = 0
    n = len(meta)
    for idx, m in enumerate(meta.itertuples(), 1):
        code, d0 = m.code, m.buyDate
        if code not in kl_cache:
            kl_cache[code] = _kline(cli, code)
        ser = kl_cache[code]
        dts = sorted(ser)
        if d0 not in dts:
            skipped += 1
            continue
        i = dts.index(d0)
        if i + 1 >= len(dts):
            skipped += 1
            continue
        d1 = dts[i + 1]
        open0 = _f(ser[d0].get("open"))
        close1 = _f(ser[d1].get("close"))
        if not (open0 and close1):
            skipped += 1
            continue
        minutes1 = _minutes(cli, code, d1)
        if not minutes1:
            skipped += 1
            continue
        atr = _atr_pct(ser, dts, i)
        exits = replay_trade(open0, close1, minutes1, atr)
        row = {"buyDate": d0, "sellDate": d1, "code": code, "mode": m.mode,
               "open0": open0, "close1": close1, "atr_pct": atr}
        for k, xp in exits.items():
            row[f"ret_{k}"] = net_ret(open0, xp)
            row[f"exit_{k}"] = xp
        rows.append(row)
        if idx % 100 == 0:
            print(f"  {idx}/{n} replayed ({skipped} skipped)...", flush=True)

    df = pd.DataFrame(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"\nreplayed {len(df)} trades ({skipped} skipped, no-kline/no-minutes) -> {out}")
    report(df)


def report(df: pd.DataFrame) -> None:
    policies = ["next_close", "sparse2", "sparse4", "hard8", "eod_only", "atr"]
    end = df["buyDate"].max()
    end_dt = datetime.fromisoformat(end)
    windows = {
        "ALL": None, "6mo": 182, "3mo": 91, "1mo": 30, "1wk": 7,
    }
    # train/test halves by date
    days = sorted(df["buyDate"].unique())
    split = days[int(len(days) * 0.6)]

    def stats(sub: pd.DataFrame, pol: str) -> str:
        r = sub[f"ret_{pol}"]
        if not len(r):
            return "  n/a"
        return f"{r.mean():+6.2f}%/{(r > 0).mean() * 100:3.0f}%"

    print(f"\n{'policy':<11}", end="")
    for w in windows:
        print(f"{w:>14}", end="")
    print(f"{'train':>14}{'test':>14}")
    for pol in policies:
        print(f"{pol:<11}", end="")
        for w, ndays in windows.items():
            sub = df if ndays is None else df[df["buyDate"] >= (end_dt - timedelta(days=ndays)).date().isoformat()]
            print(f"{stats(sub, pol):>14}", end="")
        print(f"{stats(df[df['buyDate'] < split], pol):>14}", end="")
        print(f"{stats(df[df['buyDate'] >= split], pol):>14}")
    print(f"\n(avg %/trade net of {FEE:.2%} each way / win rate; train<{split}<=test)")
    print("verdict rule: a stop policy must beat next_close on train AND test AND all windows")


if __name__ == "__main__":
    main()
