"""LoRA fine-tune base Kronos for within-day secondary-screen ranking.

Frozen tokenizer (cached token ids) + frozen base transformer with LoRA
adapters on the last N blocks' attention projections + a linear head.
Loss = within-day (1 - Pearson(score, demeaned_return)). Trained on dates <
split, early-stopped on a tail-of-train val slice, evaluated on dates >= split
(the SAME OOS as the frozen floor). Reports OOS within-day IC and per-trade
top-50% vs take-all, compared to a single-split frozen PCA+Ridge baseline.
"""
from __future__ import annotations
import argparse, pickle, math, random
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from kronos_lib import load_kronos

SPLIT = "2025-12-23"


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, r=8, alpha=16):
        super().__init__()
        self.base = base
        for p in self.base.parameters():
            p.requires_grad = False
        self.r = r; self.scale = alpha / r
        self.A = nn.Parameter(torch.zeros(r, base.in_features))
        self.B = nn.Parameter(torch.zeros(base.out_features, r))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))

    def forward(self, x):
        return self.base(x) + self.scale * (x @ self.A.t() @ self.B.t())


def inject_lora(mdl, last_n=4, r=8, alpha=16):
    n_blocks = len(mdl.transformer)
    targets = range(n_blocks - last_n, n_blocks)
    n = 0
    for bi in targets:
        attn = mdl.transformer[bi].self_attn
        for name in ["q_proj", "k_proj", "v_proj", "out_proj"]:
            setattr(attn, name, LoRALinear(getattr(attn, name), r, alpha)); n += 1
    return n


class Scorer(nn.Module):
    def __init__(self, mdl, d_model):
        super().__init__()
        self.mdl = mdl
        self.head = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, 1))

    def forward(self, s1, s2, stamp, lengths):
        _, hidden = self.mdl.decode_s1(s1, s2, stamp)  # [B,T,d]
        idx = (lengths - 1).view(-1, 1, 1).expand(-1, 1, hidden.size(-1))
        last = hidden.gather(1, idx).squeeze(1)  # [B,d] true-last (causal-safe)
        return self.head(last).squeeze(-1)


def make_batch(rows, tokens, device):
    L = max(tokens[r]["s1"].shape[0] for r in rows)
    s1 = np.zeros((len(rows), L), np.int64); s2 = np.zeros((len(rows), L), np.int64)
    stamp = np.zeros((len(rows), L, 5), np.float32); lengths = np.zeros(len(rows), np.int64)
    for i, r in enumerate(rows):
        t = tokens[r]; n = t["s1"].shape[0]
        s1[i, :n] = t["s1"]; s2[i, :n] = t["s2"]; stamp[i, :n] = t["stamp"]; lengths[i] = n
    return (torch.from_numpy(s1).to(device), torch.from_numpy(s2).to(device),
            torch.from_numpy(stamp).to(device), torch.from_numpy(lengths).to(device))


def day_pearson_loss(scores, tgt, day_ids):
    loss = 0.0; nd = 0
    for d in torch.unique(day_ids):
        m = day_ids == d
        if m.sum() < 2: continue
        s = scores[m]; t = tgt[m]
        s = s - s.mean(); t = t - t.mean()
        denom = (s.norm() * t.norm() + 1e-6)
        loss = loss - (s * t).sum() / denom; nd += 1
    return loss / max(nd, 1)


def within_day_ic(pred, ret, days):
    out = []
    for d in set(days):
        m = days == d
        if m.sum() >= 3 and np.std(pred[m]) > 0:
            c = spearmanr(pred[m], ret[m]).correlation
            if c == c: out.append(c)
    return float(np.mean(out)) if out else float("nan")


def per_trade_top50(pred, ret, days):
    sel = np.zeros(len(ret), bool)
    for d in set(days):
        idx = np.where(days == d)[0]
        k = max(1, int(round(len(idx) * 0.5)))
        sel[idx[np.argsort(-pred[idx])[:k]]] = True
    return ret[sel].mean(), (ret[sel] > 0).mean() * 100, sel


@torch.no_grad()
def predict_all(model, rows, tokens, device, bs=64):
    model.eval(); out = {}
    rows = sorted(rows, key=lambda r: tokens[r]["s1"].shape[0])
    for i in range(0, len(rows), bs):
        chunk = rows[i:i + bs]
        s1, s2, st, ln = make_batch(chunk, tokens, device)
        sc = model(s1, s2, st, ln).cpu().numpy()
        for r, v in zip(chunk, sc): out[r] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", required=True)
    ap.add_argument("--last-n", type=int, default=4)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--days-per-batch", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    ds = Path(a.ds)
    meta = pd.read_parquet(ds / "meta.parquet").reset_index(drop=True)
    tokens = pickle.load(open(ds / "tokens_base.pkl", "rb"))
    ret = meta["returnPct"].to_numpy(); days = meta["buyDate"].to_numpy()
    rid = meta["row_id"].to_numpy()
    dmean = meta.groupby("buyDate")["returnPct"].transform("mean").to_numpy()
    tgt = ret - dmean
    rid2pos = {int(r): i for i, r in enumerate(rid)}

    is_test = days >= SPLIT
    train_days = sorted(set(days[~is_test]))
    val_days = set(train_days[-20:]); fit_days = [d for d in train_days if d not in val_days]
    test_rows = [int(r) for r, d in zip(rid, days) if d >= SPLIT]

    # ---- frozen single-split baseline (same split) ----
    z = np.load(ds / "emb_base.npz"); e_rid2i = {int(r): i for i, r in enumerate(z["row_ids"])}
    E = z["emb"][meta["row_id"].map(e_rid2i).to_numpy()]
    tr = (~is_test); te = is_test
    sc = StandardScaler().fit(E[tr]); pca = PCA(8, random_state=0).fit(sc.transform(E[tr]))
    base_pred = Ridge(alpha=10).fit(pca.transform(sc.transform(E[tr])), tgt[tr]).predict(pca.transform(sc.transform(E[te])))
    fic = within_day_ic(base_pred, ret[te], days[te])
    fr, fw, _ = per_trade_top50(base_pred, ret[te], days[te])
    ta = ret[te].mean(); ta_w = (ret[te] > 0).mean() * 100
    print(f"[baseline frozen single-split] OOS wIC={fic:.3f}  top50 {fr:+.3f}%/{fw:.1f}%  (take-all {ta:+.3f}%/{ta_w:.1f}%)", flush=True)

    # ---- LoRA model ----
    tok, mdl, dev, dm = load_kronos("base")
    for p in mdl.parameters(): p.requires_grad = False
    nl = inject_lora(mdl, a.last_n, a.rank)
    model = Scorer(mdl, dm).to(dev)
    trainable = [p for p in model.parameters() if p.requires_grad]
    nparam = sum(p.numel() for p in trainable)
    print(f"LoRA injected {nl} layers (last {a.last_n} blocks), trainable params={nparam/1e3:.1f}K", flush=True)
    opt = torch.optim.AdamW(trainable, lr=8e-4, weight_decay=1e-2)

    by_day = {d: [int(r) for r, dd in zip(rid, days) if dd == d] for d in fit_days}
    best_val = -1e9; best_state = None; patience = 0
    for ep in range(a.epochs):
        model.train(); random.shuffle(fit_days)
        for i in range(0, len(fit_days), a.days_per_batch):
            chunk_days = fit_days[i:i + a.days_per_batch]
            rows = [r for d in chunk_days for r in by_day[d]]
            if len(rows) < 4: continue
            s1, s2, st, ln = make_batch(rows, tokens, dev)
            scores = model(s1, s2, st, ln)
            t = torch.tensor([tgt[rid2pos[r]] for r in rows], dtype=torch.float32, device=dev)
            dids = torch.tensor([hash(days[rid2pos[r]]) % (1 << 30) for r in rows], device=dev)
            loss = day_pearson_loss(scores, t, dids)
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0); opt.step()
        # val
        vrows = [int(r) for r, d in zip(rid, days) if d in val_days]
        vp = predict_all(model, vrows, tokens, dev)
        vpred = np.array([vp[r] for r in vrows]); vret = np.array([ret[rid2pos[r]] for r in vrows])
        vday = np.array([days[rid2pos[r]] for r in vrows])
        vic = within_day_ic(vpred, vret, vday)
        if vic > best_val:
            best_val = vic; best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}; patience = 0
        else:
            patience += 1
        print(f"  ep{ep:02d} val_wIC={vic:.3f} best={best_val:.3f} pat={patience}", flush=True)
        if patience >= 12: break

    if best_state: model.load_state_dict(best_state)
    tp = predict_all(model, test_rows, tokens, dev)
    tpred = np.array([tp[r] for r in test_rows]); tret = np.array([ret[rid2pos[r]] for r in test_rows])
    tday = np.array([days[rid2pos[r]] for r in test_rows])
    lic = within_day_ic(tpred, tret, tday)
    lr_, lw_, _ = per_trade_top50(tpred, tret, tday)
    print(f"\n[LoRA] OOS wIC={lic:.3f}  top50 {lr_:+.3f}%/{lw_:.1f}%   (frozen floor wIC={fic:.3f} top50 {fr:+.3f}%)", flush=True)
    torch.save({"state": model.state_dict(), "oos_wic": lic}, ds / "lora_base.pt")


if __name__ == "__main__":
    main()
