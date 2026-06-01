"""Daily forward-signal capture for the live recommendation.

At 9:25 (decision time) the ONLY new, decision-time-available microstructure
signal is the call-auction order book (ticks/L2 only exist after 9:30; news/
sentiment need an external source). We therefore:
  1. snapshot each candidate's auction imbalance features,
  2. record them alongside the K/P/KP scores,
  3. emit an A/B pair of picks: variant A = pure K->P, variant B = K->P + auction
     imbalance tie-break,
  4. append everything to output/live/signal_snapshots.jsonl so forward_eval.py
     can later join realized returns -> A/B verdict + accumulated training rows.

Auction is latest-only on the API, so these features are meaningful ONLY on the
live (today) run; on past-date backtests they reflect the latest auction and are
flagged is_live=false.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from scipy.stats import rankdata
import numpy as np

OUT = Path("output/live/signal_snapshots.jsonl")
# Auction-imbalance tiebreak weight. Small => P-score stays primary; auction
# only reorders near-ties. Live-only signal; validate forward in paper trading.
TIEBREAK_W = 0.25


def auction_features(client, code, date_iso):
    try:
        rows = client.stock_call_auction(code, date_iso)
    except Exception:
        return {}
    if not isinstance(rows, list) or not rows:
        return {}
    # final 9:25 snapshot
    fin = [r for r in rows if isinstance(r, dict) and str(r.get("tradeTimestamp") or "") >= "092500"]
    r = (fin or rows)[-1]
    def f(k):
        try:
            return float(r.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    vol = f("vol"); bv2 = f("buyVol2"); sv2 = f("sellVol2"); trade = f("trade")
    return {
        "auc_date": r.get("tradeDate"),
        "auc_pct": f("pctChangeRate"),                                  # 竞价涨幅
        "auc_match_vol": vol,                                            # 撮合量
        "auc_amt": vol * trade,                                          # 竞价成交额
        "auc_residual_imb": (bv2 - sv2) / (bv2 + sv2 + 1e-9),            # 未成交买卖压差 [-1,1]
        "auc_buy_residual_ratio": bv2 / (vol + 1e-9),                    # 残余买盘/撮合量
        "auc_status": r.get("tradeStatus"),
    }


def _wd_rank(vals):
    a = np.array([v if v is not None and v == v else np.nan for v in vals], float)
    out = np.full(len(a), np.nan); m = ~np.isnan(a)
    if m.sum() >= 2:
        out[m] = (rankdata(a[m]) - 1) / (m.sum() - 1)
    elif m.sum() == 1:
        out[m] = 0.5
    return out


def capture(candidates, client, date_iso, is_live, top_n=3, out=OUT):
    """Attach auction features + A/B variant flags to candidates; append snapshot.
    Variant A pick = existing kp_star. Variant B = re-rank K-survivors by
    rank(P) + rank(auction residual imbalance)."""
    if not candidates:
        return candidates
    for c in candidates:
        c.update(auction_features(client, c["code"], date_iso))
    # variant B: among K-survivors, rank by P with auction imbalance as a
    # FINAL TIEBREAK (P dominates; auction only reorders near-ties). The
    # tiebreak weight is small so a strong P signal is never overridden.
    surv = [c for c in candidates if c.get("kp_keep")]
    if surv:
        rp = _wd_rank([c.get("p_score") for c in surv])
        ra = _wd_rank([c.get("auc_residual_imb") for c in surv])   # 残余买卖压差
        rap = _wd_rank([c.get("auc_pct") for c in surv])           # 竞价涨幅
        auc_composite = 0.5 * np.nan_to_num(ra, nan=0.5) + 0.5 * np.nan_to_num(rap, nan=0.5)
        comb = np.nan_to_num(rp, nan=0.0) + TIEBREAK_W * auc_composite
        for c, v in zip(surv, comb):
            c["vb_score"] = float(v)
        order = np.argsort(-comb)
        for rank, j in enumerate(order):
            surv[j]["vb_rank"] = rank + 1
            surv[j]["vb_star"] = rank < top_n
    for c in candidates:
        c.setdefault("vb_rank", 9999); c.setdefault("vb_star", False)

    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    with out.open("a", encoding="utf-8") as fh:
        for c in candidates:
            rec = {
                "captured_at": ts, "date": date_iso, "is_live": bool(is_live),
                "code": c.get("code"), "name": c.get("name"), "mode": c.get("mode"),
                "flags": c.get("flags"),
                "xcjw": c.get("xcjw"), "cjs": c.get("cjs"), "jsjl": c.get("jsjl"),
                "k_score": c.get("k_score"), "p_score": c.get("p_score"),
                "kp_keep": c.get("kp_keep"), "kp_rank": c.get("kp_rank"), "kp_star": c.get("kp_star"),
                "vb_rank": c.get("vb_rank"), "vb_star": c.get("vb_star"), "vb_score": c.get("vb_score"),
                "open": c.get("open"), "open_pct_change": c.get("open_pct_change"),
                "basket_price": c.get("basket_price"), "basket_rule": c.get("basket_rule"),
                "basket_slippage_pct": c.get("basket_slippage_pct"),
                **{k: c.get(k) for k in ("auc_date", "auc_pct", "auc_match_vol", "auc_amt",
                                          "auc_residual_imb", "auc_buy_residual_ratio", "auc_status")},
            }
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    return candidates
