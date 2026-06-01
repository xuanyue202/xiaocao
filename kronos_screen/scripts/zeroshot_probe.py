"""Paper's method: zero-shot generative forecasting -> rank by predicted return.

For each candidate: context = bars < buyDate. Forecast H=2 steps (bar D, bar
D+1) with Monte-Carlo rollouts averaged (paper shows IC rises with samples).
Predicted signal = pred_close[D+1] / last_hist_close - 1. Rank within day;
report within-day IC + daily top-K portfolio vs take-all and vs frozen probe.
"""
from __future__ import annotations
import argparse, pickle
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from kronos_lib import load_kronos, KRONOS_REPO  # noqa
import sys
sys.path.insert(0, str(KRONOS_REPO))
from model import KronosPredictor

COLS = ["open", "high", "low", "close", "volume", "amount"]  # ohlcav order


def within_day_ic(pred, ret, days):
    out = []
    for d in set(days):
        m = days == d
        if m.sum() >= 3 and np.std(pred[m]) > 0:
            c = spearmanr(pred[m], ret[m]).correlation
            if c == c: out.append(c)
    return float(np.mean(out)) if out else float("nan")


def topk(pred, ret, days, frac=0.5):
    rr = []
    for d in set(days):
        idx = np.where(days == d)[0]
        k = max(1, int(round(len(idx) * frac)))
        rr.append(ret[idx[np.argsort(-pred[idx])[:k]]].mean())
    sel = np.zeros(len(ret), bool)
    for d in set(days):
        idx = np.where(days == d)[0]; k = max(1, int(round(len(idx) * frac)))
        sel[idx[np.argsort(-pred[idx])[:k]]] = True
    return float(np.mean(rr)), (ret[sel] > 0).mean() * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--size", default="base")
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--T", type=float, default=1.0)
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--bucket", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model-path", default=None, help="local fine-tuned predictor dir")
    ap.add_argument("--tag", default="", help="output suffix")
    a = ap.parse_args()
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    contexts = pickle.load(open(ds / "contexts.pkl", "rb"))
    tok, mdl, dev, d = load_kronos(a.size, model_path=a.model_path)
    predictor = KronosPredictor(mdl, tok, device=dev, max_context=512)

    rows = meta.to_dict("records")
    if a.limit: rows = rows[: a.limit]
    # build per-row inputs
    items = []
    for r in rows:
        rid = int(r["row_id"]); c = contexts[rid]
        arr = c["ohlcav"][-512:]; dates = c["dates"][-512:]
        df = pd.DataFrame(arr, columns=COLS)
        items.append((rid, df, pd.to_datetime(pd.Series(dates)),
                      pd.to_datetime(pd.Series([r["buyDate"], r["sellDate"]])),
                      float(arr[-1, 3])))  # last hist close
    items.sort(key=lambda t: len(t[1]))
    pred_sig = {}
    i, n = 0, len(items)
    while i < n:
        L = len(items[i][1]); j = i; batch = []
        while j < n and len(items[j][1]) == L and len(batch) < a.bucket:
            batch.append(items[j]); j += 1
        df_list = [b[1] for b in batch]
        xts = [b[2] for b in batch]; yts = [b[3] for b in batch]
        preds = predictor.predict_batch(df_list, xts, yts, pred_len=2, T=a.T,
                                        top_p=a.top_p, sample_count=a.samples, verbose=False)
        for b, p in zip(batch, preds):
            pc = float(p["close"].iloc[-1])
            pred_sig[b[0]] = pc / b[4] - 1.0
        i = j
        print(f"  forecast {i}/{n}", end="\r", flush=True)
    print()

    sub = meta[meta["row_id"].isin(pred_sig)].copy()
    sub["sig"] = sub["row_id"].map(pred_sig)
    ret = sub["returnPct"].to_numpy(); days = sub["buyDate"].to_numpy(); sig = sub["sig"].to_numpy()
    ic = within_day_ic(sig, ret, days)
    r50, w50 = topk(sig, ret, days, 0.5)
    ta = float(np.mean([ret[days == dd].mean() for dd in set(days)]))
    print(f"\n[zero-shot {a.size} H=2 samples={a.samples} T={a.T} p={a.top_p}] n={len(sub)}")
    print(f"  within-day IC = {ic:.3f}")
    print(f"  take-all daily ret = {ta:+.3f}%")
    print(f"  top50% daily ret   = {r50:+.3f}%  win={w50:.1f}%")
    # OOS-only (compare to frozen floor)
    oos = sub["buyDate"] >= "2025-12-23"
    if oos.sum() > 50:
        ic_o = within_day_ic(sig[oos.to_numpy()], ret[oos.to_numpy()], days[oos.to_numpy()])
        r_o, w_o = topk(sig[oos.to_numpy()], ret[oos.to_numpy()], days[oos.to_numpy()], 0.5)
        print(f"  [OOS 2025-12-23+] wIC={ic_o:.3f}  top50 {r_o:+.3f}%/{w_o:.1f}%")
    np.save(ds / f"zeroshot_{a.size}_sig.npy",
            np.array([(k, v) for k, v in pred_sig.items()]))


if __name__ == "__main__":
    main()
