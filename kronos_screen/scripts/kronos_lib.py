"""Kronos loading + frozen embedding extraction (no weight updates).

Embedding = last-timestep hidden state from Kronos.decode_s1 over a stock's
K-line context. Preprocessing mirrors KronosPredictor.predict (per-series
z-score + clip). Tokenizer encode is run at each sequence's true length
(the tokenizer's encoder is non-causal, so padding would leak) via
length-bucketed batches for MPS throughput.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import torch

import os
# Kronos repo location (clone of github.com/shiyu-coder/Kronos). Override via
# env for portability (e.g. when running from the skill's bundled runtime).
KRONOS_REPO = Path(os.environ.get("KRONOS_REPO",
                   str(Path(__file__).resolve().parents[2] / "Kronos")))
sys.path.insert(0, str(KRONOS_REPO))
from model import Kronos, KronosTokenizer  # noqa: E402

SIZES = {
    "mini":  ("NeoQuasar/Kronos-Tokenizer-2k",   "NeoQuasar/Kronos-mini",  256),
    "small": ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-small", 512),
    "base":  ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-base",  832),
}


def pick_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def load_kronos(size: str, device: str | None = None, model_path: str | None = None):
    """Load tokenizer + predictor. If model_path is given, the predictor is
    loaded from that local dir (e.g. a fine-tuned checkpoint); the tokenizer
    still comes from the matching pretrained HF id (we don't fine-tune it)."""
    tok_id, mdl_id, d_model = SIZES[size]
    device = device or pick_device()
    # Live automation should not phone home or emit Hugging Face auth warnings
    # when the Kronos weights are already cached. Set KRONOS_ALLOW_HF_DOWNLOAD=1
    # for an explicit refresh/download path.
    local_files_only = os.environ.get("KRONOS_ALLOW_HF_DOWNLOAD", "0").lower() not in {"1", "true", "yes"}
    tok = KronosTokenizer.from_pretrained(tok_id, local_files_only=local_files_only).to(device).eval()
    mdl = Kronos.from_pretrained(model_path or mdl_id, local_files_only=local_files_only).to(device).eval()
    return tok, mdl, device, d_model


def _time_feats(dates: list[str]) -> np.ndarray:
    ts = pd.to_datetime(pd.Series(dates))
    return np.stack([ts.dt.minute, ts.dt.hour, ts.dt.weekday, ts.dt.day, ts.dt.month], axis=1).astype(np.float32)


def _norm(arr: np.ndarray, clip: float = 5.0) -> np.ndarray:
    mean = arr.mean(0); std = arr.std(0)
    x = (arr - mean) / (std + 1e-5)
    return np.clip(x, -clip, clip).astype(np.float32)


@torch.no_grad()
def embed_contexts(tok, mdl, device, contexts: dict[int, dict], *, max_len: int = 512,
                   batch_size: int = 64, progress: bool = True) -> tuple[np.ndarray, list[int]]:
    """Return (embeddings[N, d_model], row_ids) aligned to contexts.keys()."""
    items = []
    for rid, c in contexts.items():
        arr = c["ohlcav"][-max_len:]
        x = _norm(arr)
        stamp = _time_feats(c["dates"][-max_len:])
        items.append((rid, x, stamp))
    # bucket by length for safe (non-padded) tokenizer encode
    items.sort(key=lambda t: t[1].shape[0])
    embs: dict[int, np.ndarray] = {}
    i = 0
    n = len(items)
    while i < n:
        L = items[i][1].shape[0]
        j = i
        batch = []
        while j < n and items[j][1].shape[0] == L and len(batch) < batch_size:
            batch.append(items[j]); j += 1
        xb = torch.from_numpy(np.stack([b[1] for b in batch])).to(device)
        sb = torch.from_numpy(np.stack([b[2] for b in batch])).to(device)
        s1, s2 = tok.encode(xb, half=True)
        _, hidden = mdl.decode_s1(s1, s2, sb)
        last = hidden[:, -1, :].float().cpu().numpy()
        for k, b in enumerate(batch):
            embs[b[0]] = last[k]
        i = j
        if progress:
            print(f"  embedded {i}/{n}", end="\r", flush=True)
    if progress:
        print()
    rids = list(contexts.keys())
    E = np.stack([embs[r] for r in rids]).astype(np.float32)
    return E, rids


if __name__ == "__main__":
    # smoke test
    import pickle, argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="small")
    ap.add_argument("--contexts", required=True)
    ap.add_argument("--limit", type=int, default=128)
    a = ap.parse_args()
    tok, mdl, dev, d = load_kronos(a.size)
    print("loaded", a.size, "d_model", d, "device", dev)
    ctx = pickle.load(open(a.contexts, "rb"))
    sub = dict(list(ctx.items())[: a.limit])
    E, rids = embed_contexts(tok, mdl, dev, sub)
    print("emb shape", E.shape, "rids", len(rids), "finite", np.isfinite(E).all())
