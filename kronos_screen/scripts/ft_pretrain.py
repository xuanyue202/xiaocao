"""Official-recipe continued pre-training of the Kronos predictor on A-share
daily K-lines (self-supervised next-token objective; full fine-tune, NO LoRA).

Faithful to finetune/train_predictor.py but adapted for single-device MPS, no
Comet, no DDP, and reading K-lines straight from the xiaocao cache (no qlib).

Leak-free: training/val windows END strictly before the OOS forecast period
(OOS buys start 2025-12-23), so the fine-tuned model never sees OOS bars.
"""
from __future__ import annotations
import argparse, time
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from kronos_lib import load_kronos
from xiaocao.api.cache import iter_cached_responses

FEATS = ["open", "high", "low", "close", "vol", "amt"]
OOS_START = "2025-12-23"
VAL_START = "2025-12-01"   # val windows end in [VAL_START, OOS_START)


def build_series(cache_path):
    by = defaultdict(lambda: defaultdict(dict))
    for data in iter_cached_responses(cache_path, "/stock/date_kline"):
        if not isinstance(data, list):
            continue
        for k in data:
            if not isinstance(k, dict):
                continue
            code = k.get("code"); td = k.get("tradeDate")
            if not code or not td:
                continue
            rec = by[code][td]
            for c in FEATS:
                rec[c] = k.get(c)
    out = {}
    for code, days in by.items():
        df = pd.DataFrame([{"date": d, **v} for d, v in days.items()])
        df = df.dropna(subset=FEATS).sort_values("date").reset_index(drop=True)
        out[code] = df
    return out


class WinDS(Dataset):
    def __init__(self, windows, clip=5.0):
        self.w = windows; self.clip = clip

    def __len__(self): return len(self.w)

    def __getitem__(self, i):
        x, stamp = self.w[i]  # x [L,6] raw, stamp [L,5]
        past = x[:-1]  # all but last as "lookback" proxy isn't exact; we normalize on lookback below
        return x, stamp


def make_windows(series, lookback, predict, clip=5.0):
    L = lookback + predict + 1
    train, val = [], []
    for code, df in series.items():
        if len(df) < L:
            continue
        dates = df["date"].to_numpy()
        feats = df[FEATS].to_numpy(np.float32)
        ts = pd.to_datetime(df["date"])
        stamp = np.stack([ts.dt.minute, ts.dt.hour, ts.dt.weekday, ts.dt.day, ts.dt.month], 1).astype(np.float32)
        for s in range(len(df) - L + 1):
            e = s + L
            end_date = dates[e - 1]
            if end_date >= OOS_START:
                continue  # leak guard
            x = feats[s:e].copy()
            # per-window z-score on the lookback portion (no future leak)
            past = x[:lookback]
            mu = past.mean(0); sd = past.std(0)
            xn = np.clip((x - mu) / (sd + 1e-5), -clip, clip).astype(np.float32)
            item = (xn, stamp[s:e])
            (val if end_date >= VAL_START else train).append(item)
    return train, val


def run_epoch(model, tok, loader, device, opt=None, max_steps=None, log_every=0):
    train = opt is not None
    model.train(train)
    tot, n = 0.0, 0
    t0 = time.time()
    for step, (x, stamp) in enumerate(loader):
        if max_steps and step >= max_steps:
            break
        x = x.to(device); stamp = stamp.to(device)
        with torch.no_grad():
            s1, s2 = tok.encode(x, half=True)
        tin0, tin1 = s1[:, :-1], s2[:, :-1]
        tout0, tout1 = s1[:, 1:], s2[:, 1:]
        ctx = torch.enable_grad() if train else torch.no_grad()
        with ctx:
            logits = model(tin0, tin1, stamp[:, :-1, :])
            loss, _, _ = model.head.compute_loss(logits[0], logits[1], tout0, tout1)
            if train:
                opt.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 3.0); opt.step()
        tot += loss.item(); n += 1
        if log_every and train and n % log_every == 0:
            print(f"    step {n} loss={tot/n:.4f} ({n/(time.time()-t0):.2f} it/s)", flush=True)
    return tot / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="base", choices=["small", "base"])
    ap.add_argument("--out", default="kronos_screen/data/ft_base")
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--lookback", type=int, default=90)
    ap.add_argument("--predict", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=4e-5)
    ap.add_argument("--max-steps", type=int, default=1200)
    ap.add_argument("--val-cap", type=int, default=2000)
    ap.add_argument("--patience", type=int, default=2)
    a = ap.parse_args()

    print("building series from cache...", flush=True)
    series = build_series(a.cache)
    train_w, val_w = make_windows(series, a.lookback, a.predict)
    import random as _r; _r.Random(0).shuffle(val_w)
    val_w = val_w[: a.val_cap]
    print(f"codes={len(series)}  train_windows={len(train_w)}  val_windows(capped)={len(val_w)}", flush=True)
    tok, mdl, dev, d = load_kronos(a.size)
    for p in tok.parameters(): p.requires_grad = False
    tok.eval()
    for p in mdl.parameters(): p.requires_grad = True
    tl = DataLoader(WinDS(train_w), batch_size=a.batch_size, shuffle=True, drop_last=True)
    vl = DataLoader(WinDS(val_w), batch_size=a.batch_size, shuffle=False)
    opt = torch.optim.AdamW(mdl.parameters(), lr=a.lr, betas=(0.9, 0.95), weight_decay=0.1)

    base_val = run_epoch(mdl, tok, vl, dev)  # pre-FT val loss
    print(f"[ep -1] pre-FT val_loss={base_val:.4f}", flush=True)
    best = base_val; bad = 0
    outdir = Path(a.out)
    for ep in range(a.epochs):
        t0 = time.time()
        tr = run_epoch(mdl, tok, tl, dev, opt, max_steps=a.max_steps, log_every=100)
        va = run_epoch(mdl, tok, vl, dev)
        print(f"[ep {ep}] train={tr:.4f} val={va:.4f} ({time.time()-t0:.0f}s)", flush=True)
        if va < best - 1e-4:
            best = va; bad = 0
            mdl.save_pretrained(outdir); print(f"  saved best -> {outdir} (val {best:.4f})", flush=True)
        else:
            bad += 1
            if bad >= a.patience:
                print("early stop", flush=True); break
    print(f"DONE best_val={best:.4f} (pre-FT {base_val:.4f})", flush=True)


if __name__ == "__main__":
    main()
