"""Create a re-labeled dataset dir: same candidates/features/embeddings as the
base ds, but returnPct swapped to a higher-SNR exit (from a new trades.csv).
Symlinks emb_base.npz / priorday_feats.parquet / contexts.pkl so all existing
eval scripts work unchanged."""
from __future__ import annotations
import argparse, os
from pathlib import Path
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="kronos_screen/data/ds")
    ap.add_argument("--trades", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base = Path(a.base); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    meta = pd.read_parquet(base / "meta.parquet")
    t = pd.read_csv(a.trades); t.columns = [c.lstrip("﻿") for c in t.columns]
    lab = (t.groupby(["buyDate", "code", "mode"], as_index=False)
             .agg(newret=("returnPct", "first"), newsell=("sellDate", "first")))
    m = meta.merge(lab, on=["buyDate", "code", "mode"], how="inner")
    m["returnPct"] = m["newret"].astype(float)
    m["win"] = (m["returnPct"] > 0).astype(int)
    m["sellDate"] = m["newsell"]
    m = m.drop(columns=["newret", "newsell"])
    m.to_parquet(out / "meta.parquet", index=False)
    for f in ["emb_base.npz", "priorday_feats.parquet", "contexts.pkl"]:
        link = out / f
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink((base / f).resolve(), link)
    print(f"{a.out}: rows={len(m)} (base {len(meta)})  avg_newret={m.returnPct.mean():+.2f}%  win={m.win.mean()*100:.1f}%")


if __name__ == "__main__":
    main()
