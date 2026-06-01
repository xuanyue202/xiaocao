"""Encode every context once with the frozen base tokenizer and cache the
(s1, s2) token ids + time stamps. LoRA training then only runs the transformer
(decode_s1), not the tokenizer — big speedup, and gradients don't flow through
the discrete tokenizer anyway."""
from __future__ import annotations
import argparse, pickle
from pathlib import Path
import numpy as np
import torch
from kronos_lib import load_kronos, _norm, _time_feats


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--size", default="base")
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=64)
    a = ap.parse_args()
    ds = Path(a.ds)
    contexts = pickle.load(open(ds / "contexts.pkl", "rb"))
    tok, mdl, dev, d = load_kronos(a.size)
    items = []
    for rid, c in contexts.items():
        arr = c["ohlcav"][-a.max_len:]
        items.append((rid, _norm(arr), _time_feats(c["dates"][-a.max_len:])))
    items.sort(key=lambda t: t[1].shape[0])
    out = {}
    i, n = 0, len(items)
    while i < n:
        L = items[i][1].shape[0]; j = i; batch = []
        while j < n and items[j][1].shape[0] == L and len(batch) < a.batch_size:
            batch.append(items[j]); j += 1
        xb = torch.from_numpy(np.stack([b[1] for b in batch])).to(dev)
        s1, s2 = tok.encode(xb, half=True)
        s1 = s1.cpu().numpy().astype(np.int32); s2 = s2.cpu().numpy().astype(np.int32)
        for kk, b in enumerate(batch):
            out[b[0]] = {"s1": s1[kk], "s2": s2[kk], "stamp": b[2].astype(np.float32)}
        i = j
        print(f"  tokenized {i}/{n}", end="\r", flush=True)
    print()
    with open(ds / f"tokens_{a.size}.pkl", "wb") as f:
        pickle.dump(out, f, protocol=4)
    print(f"saved tokens_{a.size}.pkl  n={len(out)}  vocab_dims s1/s2 from tokenizer")


if __name__ == "__main__":
    main()
