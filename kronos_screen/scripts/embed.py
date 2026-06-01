"""Compute & cache frozen Kronos embeddings for all dataset contexts."""
from __future__ import annotations
import argparse, pickle
from pathlib import Path
import numpy as np
from kronos_lib import load_kronos, embed_contexts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True, help="dataset dir with contexts.pkl")
    ap.add_argument("--size", default="base", choices=["mini", "small", "base"])
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--model-path", default=None, help="local fine-tuned predictor dir")
    ap.add_argument("--tag", default=None, help="output suffix (e.g. 'ft')")
    a = ap.parse_args()
    ds = Path(a.ds)
    contexts = pickle.load(open(ds / "contexts.pkl", "rb"))
    tok, mdl, dev, d = load_kronos(a.size, model_path=a.model_path)
    print(f"size={a.size} d_model={d} device={dev} n_ctx={len(contexts)}", flush=True)
    E, rids = embed_contexts(tok, mdl, dev, contexts, max_len=a.max_len, batch_size=a.batch_size)
    suffix = a.size + (f"_{a.tag}" if a.tag else "")
    out = ds / f"emb_{suffix}.npz"
    np.savez(out, emb=E, row_ids=np.array(rids, dtype=np.int64))
    print(f"saved {out}  shape={E.shape}", flush=True)


if __name__ == "__main__":
    main()
