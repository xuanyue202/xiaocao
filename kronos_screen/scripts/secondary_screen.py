"""K->P secondary screen scorer for live daily recommendation.

Given today's candidate codes + a XiaocaoClient, compute:
  K = Kronos-base frozen-embedding score (daily K-line context < today)
  P = prior-day intraday GBDT score (yesterday's 1-min -> 5-min/feature model)
Pipeline tier per day: drop bottom-50% by K, rank survivors by P; top-N = ★.

Honest framing: this is a DEFENSIVE re-rank (drops predicted-worst, surfaces
better; cushions drawdowns + small win-rate lift) — not a proven alpha.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
MODEL = SCRIPTS.parent / "model"
from kronos_lib import load_kronos, embed_contexts          # noqa: E402
from build_priorday_feats import feats_from_minutes, trading_axis  # noqa: E402

PRICE = ["open", "high", "low", "close", "vol", "amt"]
_CACHE = {}


def _load():
    if "K" not in _CACHE:
        _CACHE["K"] = joblib.load(MODEL / "K_kronos.joblib")
        _CACHE["P"] = joblib.load(MODEL / "P_priorday.joblib")
        tok, mdl, dev, d = load_kronos("base")
        _CACHE["kron"] = (tok, mdl, dev)
    return _CACHE["K"], _CACHE["P"], _CACHE["kron"]


def _daily_context(client, code, date_iso, lookback=400, min_ctx=60):
    rows = client.date_kline(code, count=lookback + 10, freq="D", adj="qfq")
    if not isinstance(rows, list) or not rows:
        return None
    df = pd.DataFrame(rows)
    if "tradeDate" not in df:
        return None
    df = df[df["tradeDate"] < date_iso]  # strictly before today -> no look-ahead
    for c in PRICE:
        if c not in df:
            return None
    df = df.dropna(subset=PRICE).sort_values("tradeDate").tail(lookback)
    if len(df) < min_ctx:
        return None
    return df[PRICE].to_numpy(np.float32), df["tradeDate"].tolist()


def score(candidates, client, date_iso, cache_path="output/.cache/xiaocao.db", top_n=3):
    """candidates: list of dicts with at least 'code'. Mutates+returns them
    with k_score / p_score / kp_keep / kp_rank / kp_star, ordered best-first."""
    if not candidates:
        return candidates
    (Km, Pm, (tok, mdl, dev)) = _load()
    axis = trading_axis(cache_path); pos = {d: i for i, d in enumerate(axis)}
    prev = axis[pos[date_iso] - 1] if date_iso in pos and pos[date_iso] > 0 else (axis[-1] if axis else None)

    # ---- K: Kronos embedding score ----
    contexts = {}
    for i, c in enumerate(candidates):
        ctx = _daily_context(client, c["code"], date_iso)
        if ctx is not None:
            contexts[i] = {"ohlcav": ctx[0], "dates": ctx[1]}
    kscore = {i: np.nan for i in range(len(candidates))}
    if contexts:
        E, rids = embed_contexts(tok, mdl, dev, contexts, progress=False)
        Xk = Km["pca"].transform(Km["scaler"].transform(E))
        pk = Km["ridge"].predict(Xk)
        for j, rid in enumerate(rids):
            kscore[rid] = float(pk[j])

    # ---- P: prior-day intraday score ----
    pfeats = Pm["feats"]
    pscore = {i: np.nan for i in range(len(candidates))}
    if prev:
        rowsP = []
        idxP = []
        for i, c in enumerate(candidates):
            try:
                mins = client.minute_line(c["code"], trade_date=prev, count=241)
            except Exception:
                mins = None
            mins = mins if isinstance(mins, list) else (mins.get("data") if isinstance(mins, dict) else None)
            f = feats_from_minutes(mins) if mins else None
            if f is not None:
                rowsP.append([f.get(k, np.nan) for k in pfeats]); idxP.append(i)
        if rowsP:
            Xp = np.nan_to_num(np.array(rowsP, np.float32))
            pp = Pm["gbdt"].predict(Xp)
            for j, i in enumerate(idxP):
                pscore[i] = float(pp[j])

    for i, c in enumerate(candidates):
        c["k_score"] = kscore[i]; c["p_score"] = pscore[i]

    # ---- pipeline: drop bottom-50% by K, rank survivors by P ----
    ks = np.array([candidates[i]["k_score"] for i in range(len(candidates))], float)
    valid = ~np.isnan(ks)
    med = np.nanmedian(ks) if valid.any() else -np.inf
    for i, c in enumerate(candidates):
        c["kp_keep"] = bool(valid[i] and ks[i] >= med) if valid.any() else True
    survivors = [i for i, c in enumerate(candidates) if c["kp_keep"]]
    survivors.sort(key=lambda i: (-(candidates[i]["p_score"] if candidates[i]["p_score"] == candidates[i]["p_score"] else -1e9)))
    for rank, i in enumerate(survivors):
        candidates[i]["kp_rank"] = rank + 1
        candidates[i]["kp_star"] = rank < top_n
    for i, c in enumerate(candidates):
        c.setdefault("kp_rank", 9999); c.setdefault("kp_star", False)
    candidates.sort(key=lambda c: (0 if c["kp_star"] else (1 if c["kp_keep"] else 2), c["kp_rank"]))
    return candidates


if __name__ == "__main__":
    import argparse
    from xiaocao.config.settings import load_settings
    from xiaocao.api.client import XiaocaoClient
    from xiaocao.api.cache import SQLiteCache
    from xiaocao.datasource.api_source import ApiDataSource
    from xiaocao.strategy import run_strategy
    ap = argparse.ArgumentParser(); ap.add_argument("--date", required=True); ap.add_argument("--top-n", type=int, default=3)
    a = ap.parse_args()
    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache("output/.cache/xiaocao.db"))
    src = ApiDataSource(cli, hpqb_state=0, lpdx_state=0)
    rows = run_strategy(a.date, src, profile="validated_v5", adaptive_modes=False)
    cands = [{"code": r.get("code"), "name": r.get("name"), "mode": r.get("mode")} for r in rows if r.get("code")]
    print(f"{a.date}: {len(cands)} candidates")
    out = score(cands, cli, a.date, top_n=a.top_n)
    print(f"{'★':<2}{'rank':>5}  {'code':<12}{'mode':<14}{'Kscore':>9}{'Pscore':>9}{'keep':>6}")
    for c in out:
        print(f"{'★' if c['kp_star'] else ' ':<2}{c['kp_rank']:>5}  {str(c['code']):<12}{str(c['mode'])[:12]:<14}{c['k_score']:>+9.3f}{c['p_score']:>+9.3f}{str(c['kp_keep']):>6}")
