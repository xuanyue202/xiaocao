"""Daily forward-signal capture for the live recommendation.

At 9:25 (decision time) the ONLY new, decision-time-available microstructure
signal is the call-auction order book (ticks/L2 only exist after 9:30; news/
sentiment need an external source). We therefore:
  1. snapshot each candidate's auction imbalance features,
  2. record them alongside the K/P/KP scores,
  3. emit tracked picks: variant A = pure K->P, variant B = K->P + auction
     imbalance tie-break, variant C = K survivors ranked by live mode-rotation
     rank_score,
  4. append everything to output/live/signal_snapshots.jsonl so forward_eval.py
     can later join realized returns -> A/B verdict + accumulated training rows.

Auction is latest-only on the API, so these features are meaningful ONLY on the
live (today) run; on past-date backtests they reflect the latest auction and are
flagged is_live=false.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path
from scipy.stats import rankdata
import numpy as np

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from quality_governor import ensure_quality_fields, num  # noqa: E402

OUT = Path("output/live/signal_snapshots.jsonl")
MODE_STAR_MAX_PER_MODE = 2
# NOTE: the original design (rank-weighted tiebreak, W=0.25) produced B == A on
# every live day (zero contrast), and auc_residual_imb saturates at +/-1 because
# the post-match residual book is one-sided by construction. Variant B is now a
# FORCED-CONTRAST swap (see capture()) using continuous auction features.


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


def _assign_mode_rotation_star(candidates, top_n=3, max_per_mode=MODE_STAR_MAX_PER_MODE):
    """Variant C: keep K survivors, then rank by mode-aware live rank_score.

    `rank_score` is produced by live_recommend from primary score, recent live
    all-hit mode PnL, macro focus, and open-risk penalty. This is a shadow
    forward-test variant; it does not replace the default paper buy set.
    """
    for c in candidates:
        c["mode_rank"] = 9999
        c["mode_star"] = False
        c["mode_score"] = num(c.get("rank_score")) or 0.0
    per_mode = {}
    rank = 0
    survivors = [c for c in candidates if c.get("kp_keep")]
    survivors.sort(
        key=lambda c: (
            -(num(c.get("rank_score")) or -1e9),
            -(num(c.get("primary_score")) or -1e9),
            -(num(c.get("p_score")) or -1e9),
            str(c.get("code") or ""),
        )
    )
    for c in survivors:
        mode = str(c.get("mode") or "unknown")
        if per_mode.get(mode, 0) >= max_per_mode:
            continue
        rank += 1
        c["mode_rank"] = rank
        c["mode_star"] = True
        c["mode_score"] = num(c.get("rank_score")) or 0.0
        per_mode[mode] = per_mode.get(mode, 0) + 1
        if rank >= top_n:
            break
    return candidates


def _replace_day_rows(out: Path, date_iso, is_live, new_lines, *, book: str = "B"):
    """Idempotent write: re-running capture for the same (date, is_live, book) replaces
    that day's rows instead of appending duplicates (mixed-run stars otherwise
    survive forward_eval's per-code dedup and pollute the A/B sample)."""
    kept = []
    if out.exists():
        with out.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    kept.append(line)
                    continue
                rec_book = str(rec.get("book") or "B")
                if (
                    rec.get("date") == date_iso
                    and bool(rec.get("is_live")) == bool(is_live)
                    and rec_book == book
                ):
                    continue  # replaced by this run
                kept.append(line)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for line in kept + new_lines:
            fh.write(line + "\n")
    tmp.replace(out)


def capture(candidates, client, date_iso, is_live, top_n=3, out=OUT, book="B"):
    """Attach auction features + A/B variant flags to candidates; write snapshot.
    Variant A = existing kp_star (pure K->P top-N by P).
    Variant B = FORCED CONTRAST: among K-survivors, compute a continuous
    auction-quality score q = rank(auc_buy_residual_ratio)/2 + rank(auc_pct)/2;
    if the auction-worst A pick scores below the best non-A survivor's q, swap
    it out for that survivor (highest P among non-A). This guarantees A != B
    whenever the auction signal actually disagrees, so forward A/B accumulates
    informative contrast (the old W=0.25 rank tiebreak never changed a pick).
    Idempotent per (date, is_live)."""
    if not candidates:
        return candidates
    for c in candidates:
        c.update(ensure_quality_fields(c))
    for c in candidates:
        c.update(auction_features(client, c["code"], date_iso))
    surv = [c for c in candidates if c.get("kp_keep")]
    if surv:
        rq_ratio = _wd_rank([c.get("auc_buy_residual_ratio") for c in surv])  # 残余买盘/撮合量 (连续)
        rq_pct = _wd_rank([c.get("auc_pct") for c in surv])                   # 竞价涨幅
        q = 0.5 * np.nan_to_num(rq_ratio, nan=0.5) + 0.5 * np.nan_to_num(rq_pct, nan=0.5)
        for c, v in zip(surv, q):
            c["vb_score"] = float(v)  # auction quality, NOT a combined rank
        a_picks = [c for c in surv if c.get("kp_star")]
        others = sorted(
            [c for c in surv if not c.get("kp_star")],
            key=lambda c: -(c.get("p_score") if c.get("p_score") is not None else -1e9),
        )
        b_set = list(a_picks)
        swapped = False
        if a_picks and others:
            worst = min(a_picks, key=lambda c: c.get("vb_score", 0.5))
            repl = others[0]
            if repl.get("vb_score", 0.5) > worst.get("vb_score", 0.5):
                b_set = [c for c in a_picks if c is not worst] + [repl]
                swapped = True
        b_sorted = sorted(
            b_set,
            key=lambda c: -(c.get("p_score") if c.get("p_score") is not None else -1e9),
        )
        for rank, c in enumerate(b_sorted, 1):
            c["vb_rank"] = rank
            c["vb_star"] = True
        for c in surv:
            c["vb_swap"] = swapped
    for c in candidates:
        c.setdefault("vb_rank", 9999); c.setdefault("vb_star", False)
    _assign_mode_rotation_star(candidates, top_n=top_n)

    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    new_lines = []
    for c in candidates:
        q = ensure_quality_fields(c)
        c.update({
            "primary_score": q.get("primary_score"),
            "primary_score_label": q.get("primary_score_label"),
            "rank_score": q.get("rank_score"),
            "mode_confidence": q.get("mode_confidence"),
            "quality_tag": q.get("quality_tag"),
            "quality_fields_fallback": q.get("quality_fields_fallback"),
        })
        rec = {
            "captured_at": ts, "date": date_iso, "book": str(book or "B"), "is_live": bool(is_live),
            "code": c.get("code"), "name": c.get("name"), "mode": c.get("mode"),
            "flags": c.get("flags"),
            "xcjw": c.get("xcjw"), "cjs": c.get("cjs"), "jsjl": c.get("jsjl"),
            "jssb": c.get("jssb"),
            "primary_score": c.get("primary_score"),
            "primary_score_label": c.get("primary_score_label"),
            "rank_score": c.get("rank_score"),
            "mode_confidence": c.get("mode_confidence"),
            "mode_recent_avg": c.get("mode_recent_avg"),
            "mode_recent_n": c.get("mode_recent_n"),
            "mode_confidence_source": c.get("mode_confidence_source"),
            "mode_confidence_reason": c.get("mode_confidence_reason"),
            "quality_tag": c.get("quality_tag"),
            "quality_fields_fallback": c.get("quality_fields_fallback"),
            "k_score": c.get("k_score"), "p_score": c.get("p_score"),
            "kp_keep": c.get("kp_keep"), "kp_rank": c.get("kp_rank"), "kp_star": c.get("kp_star"),
            "vb_rank": c.get("vb_rank"), "vb_star": c.get("vb_star"), "vb_score": c.get("vb_score"),
            "vb_swap": c.get("vb_swap"),
            "mode_rank": c.get("mode_rank"), "mode_star": c.get("mode_star"), "mode_score": c.get("mode_score"),
            "is_main_line": c.get("is_main_line"),
            "is_big_cap": c.get("is_big_cap"),
            "direction": c.get("direction"),
            "direction_rank": c.get("direction_rank"),
            "category_rank": c.get("category_rank"),
            "regime": c.get("regime"),
            "macro_focus_score": c.get("macro_focus_score"),
            "macro_focus_reason": c.get("macro_focus_reason"),
            "open_risk_penalty": c.get("open_risk_penalty"),
            "rawQibaoRank": c.get("rawQibaoRank"),
            "qibaoRankScore": c.get("qibaoRankScore"),
            "qibaoBenchmarkKind": c.get("qibaoBenchmarkKind"),
            "qibaoBenchmarkLayer": c.get("qibaoBenchmarkLayer"),
            "industryElectronic": c.get("industryElectronic"),
            "board20": c.get("board20"),
            "open": c.get("open"), "open_pct_change": c.get("open_pct_change"),
            "reason": c.get("reason"),
            "excIndustryCode": c.get("excIndustryCode"),
            "blockCodeList": c.get("blockCodeList"),
            "blockCategoryCodeList": c.get("blockCategoryCodeList"),
            "basket_price": c.get("basket_price"), "basket_rule": c.get("basket_rule"),
            "basket_slippage_pct": c.get("basket_slippage_pct"),
            **{k: c.get(k) for k in ("auc_date", "auc_pct", "auc_match_vol", "auc_amt",
                                      "auc_residual_imb", "auc_buy_residual_ratio", "auc_status")},
        }
        new_lines.append(json.dumps(rec, ensure_ascii=False, default=str))
    _replace_day_rows(out, date_iso, is_live, new_lines, book=str(book or "B"))
    return candidates
