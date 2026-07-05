"""Join captured live snapshots with realized next-close returns -> (1) A/B/C/D/E
verdict (A = K->P, B = K->P + auction imbalance, C = K survivors + mode
rotation rank, D = qibao benchmark modes, E = agent-reviewed AI intelligence short factor vs take-all),
(2) accumulated labeled training rows for future models.

Run any time after the outcome day's close is available (T+1+). Idempotent.
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from xiaocao.config.settings import load_settings
from xiaocao.api.client import XiaocaoClient
from xiaocao.api.cache import SQLiteCache

SNAP = Path("output/live/signal_snapshots.jsonl")
TRAIN = Path("output/live/training_rows.parquet")
RECONSTRUCTED_DAILY = Path("output/live/daily_reconstructed.jsonl")
DEFAULT_FEE_RATE = 0.0001
QIBAO_BENCHMARK_MODES = {"标杆短线起爆", "高开标杆起爆", "强攻标杆起爆"}
REQUIRED_TRAINING_COLUMNS = {
    "book": "B",
    "kp_star": False,
    "vb_star": False,
    "mode_star": False,
    "ai_intelligence_short_star": False,
    "ai_intelligence_short_rank": pd.NA,
    "ai_intelligence_short_score": pd.NA,
    "ai_intelligence_short_threshold": pd.NA,
    "ai_intelligence_short_surface": pd.NA,
    # Back-compat for pre-rename snapshots.
    "intelligence_long_star": False,
    "intelligence_long_rank": pd.NA,
    "intelligence_long_score": pd.NA,
    "intelligence_long_threshold": pd.NA,
    "intelligence_long_surface": pd.NA,
    "intelligence_factor_score_source": pd.NA,
    "intelligence_factor_keyword_score": pd.NA,
    "intelligence_factor_agent_score": pd.NA,
    "intelligence_factor_short_score": pd.NA,
    "intelligence_factor_trend_score": pd.NA,
    "intelligence_factor_trend_label": pd.NA,
    "stock_sentiment_score": pd.NA,
    "stock_sentiment_label": pd.NA,
    "stock_sentiment_data_quality": pd.NA,
    "stock_sentiment_evidence_state": pd.NA,
    "stock_sentiment_authority": pd.NA,
    "stock_sentiment_target_set": pd.NA,
    "mode_rank": pd.NA,
    "mode_score": pd.NA,
    "mode_confidence_source": pd.NA,
    "mode_confidence_reason": pd.NA,
    "mode_recent_avg": pd.NA,
    "mode_recent_n": pd.NA,
    "is_main_line": pd.NA,
    "is_big_cap": pd.NA,
    "direction": pd.NA,
    "direction_rank": pd.NA,
    "category_rank": pd.NA,
    "regime": pd.NA,
    "macro_focus_score": pd.NA,
    "macro_focus_reason": pd.NA,
    "open_risk_penalty": pd.NA,
    "qibaoBenchmarkKind": pd.NA,
    "qibaoBenchmarkLayer": pd.NA,
    "rawQibaoRank": pd.NA,
    "qibaoRankScore": pd.NA,
    "industryElectronic": pd.NA,
    "board20": pd.NA,
    "reason": pd.NA,
    "excIndustryCode": pd.NA,
    "blockCodeList": pd.NA,
    "blockCategoryCodeList": pd.NA,
}
PARQUET_STRING_COLUMNS = ("excIndustryCode", "blockCodeList", "blockCategoryCodeList")


def _normal_date(value) -> str | None:
    s = str(value or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) >= 10:
        return s[:10]
    return None


def _load_reconstructed_daily(path: Path = RECONSTRUCTED_DAILY) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = row.get("code")
        d = _normal_date(row.get("date"))
        if not code or not d:
            continue
        out[str(code)][d] = {
            "tradeDate": d,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("vol", row.get("volume")),
            "amount": row.get("amt", row.get("amount")),
            "source": row.get("source", "minute_reconstructed"),
        }
    return out


def qibao_benchmark_mask(df: pd.DataFrame) -> pd.Series:
    layer = (
        df["qibaoBenchmarkLayer"].fillna("").astype(str)
        if "qibaoBenchmarkLayer" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )
    mode = (
        df["mode"].fillna("").astype(str)
        if "mode" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )
    return (layer == "paper_buy") | mode.isin(QIBAO_BENCHMARK_MODES)


def ensure_training_schema(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col, default in REQUIRED_TRAINING_COLUMNS.items():
        if col not in out.columns:
            out[col] = default
    if "ai_intelligence_short_star" not in df.columns and "intelligence_long_star" in df.columns:
        out["ai_intelligence_short_star"] = out["intelligence_long_star"]
        out["ai_intelligence_short_rank"] = out["intelligence_long_rank"]
        out["ai_intelligence_short_score"] = out["intelligence_long_score"]
        out["ai_intelligence_short_threshold"] = out["intelligence_long_threshold"]
        out["ai_intelligence_short_surface"] = out["intelligence_long_surface"]
    for col in PARQUET_STRING_COLUMNS:
        out[col] = out[col].map(_metadata_to_string)
    out["qibao_benchmark_star"] = qibao_benchmark_mask(out)
    return out


def _metadata_to_string(value: object) -> object:
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(part) for part in value if part is not None and str(part).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if pd.isna(value):
        return pd.NA
    return str(value)


def day_mean(scored: pd.DataFrame, ret_col: str, mask_col: str | None = None) -> np.ndarray:
    per = []
    if mask_col and mask_col not in scored.columns:
        return np.array(per)
    for _, g in scored.groupby("date"):
        sel = g[g[mask_col] == True] if mask_col else g  # noqa: E712
        if len(sel):
            per.append(sel[ret_col].mean())
    return np.array(per)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", default=str(SNAP))
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--live-only", action="store_true", help="only score is_live=true rows")
    ap.add_argument("--fee-rate", type=float, default=DEFAULT_FEE_RATE,
                    help="one-way transaction fee rate, e.g. 0.0001 = 1bp")
    a = ap.parse_args()
    if not Path(a.snap).exists():
        print("no snapshots yet:", a.snap); return
    recs = [json.loads(l) for l in open(a.snap, encoding="utf-8") if l.strip()]
    df = pd.DataFrame(recs)
    if "book" not in df.columns:
        df["book"] = "B"
    df["book"] = df["book"].fillna("B").astype(str)
    df = df.drop_duplicates(["date", "code", "book"], keep="last")
    # The A/B/C/D continuous-optimization lane is Book B only. Book T uses
    # trend_guards / trend_optimize and must not be laundered through per-trade
    # short-line metrics.
    df = df[df["book"] == "B"].copy()
    if a.live_only:
        df = df[df["is_live"] == True]
    if df.empty:
        print("no rows to score"); return

    s = load_settings(None)
    cli = XiaocaoClient(base_url=s.base_url, timeout=s.timeout, retries=s.retries, cache=SQLiteCache(a.cache))
    reconstructed = _load_reconstructed_daily()

    # realized next-close return per (date, code): open[D] -> close[D+1]
    rets = {}
    for code in df["code"].unique():
        try:
            kl = cli.date_kline(code, count=400, freq="D", adj="qfq")
        except Exception:
            continue
        if not isinstance(kl, list):
            continue
        ser = {
            _normal_date(r.get("tradeDate")): r
            for r in kl
            if isinstance(r, dict) and _normal_date(r.get("tradeDate"))
        }
        # date_kline can lag; EOD reconstructs recent bars from minute_line.
        # Merge them here so current live labels are not blocked by the vendor
        # daily feed while still using date_kline for deeper history.
        ser.update(reconstructed.get(str(code), {}))
        dts = sorted(ser)
        for d in df.loc[df.code == code, "date"].unique():
            if d not in dts:
                continue
            i = dts.index(d)
            if i + 1 >= len(dts):
                continue  # outcome not yet available
            o = df.loc[(df.date == d) & (df.code == code), "open"].iloc[0]
            o = o or ser[d].get("open")
            cN = ser[dts[i + 1]].get("close")
            if o and cN:
                entry = float(o)
                exit_price = float(cN)
                gross_ret = (exit_price / entry - 1) * 100
                net_ret = ((exit_price * (1 - a.fee_rate)) / (entry * (1 + a.fee_rate)) - 1) * 100
                rets[(d, code)] = (gross_ret, net_ret)
    df["realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[0] for r in df.itertuples()
    ]
    df["net_realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[1] for r in df.itertuples()
    ]
    df["fee_rate"] = a.fee_rate
    scored = ensure_training_schema(df[df["realized_ret"].notna()].copy())
    print(f"snapshots={len(df)}  scored(outcome known)={len(scored)}  pending={len(df)-len(scored)}")
    if scored.empty:
        print("no outcomes available yet — re-run after T+1 close."); return

    # accumulate training rows
    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(TRAIN, index=False)
    print(f"accumulated {len(scored)} labeled training rows -> {TRAIN}")

    # A/B/C/D/E by day
    ta = day_mean(scored, "net_realized_ret")
    A = day_mean(scored, "net_realized_ret", "kp_star")
    B = day_mean(scored, "net_realized_ret", "vb_star")
    C = day_mean(scored, "net_realized_ret", "mode_star")
    D = day_mean(scored, "net_realized_ret", "qibao_benchmark_star")
    E = day_mean(scored, "net_realized_ret", "ai_intelligence_short_star")
    print(f"\nA/B/C/D/E over {scored['date'].nunique()} live days ({scored.date.min()}..{scored.date.max()}):")
    print(f"  net of fees   : one-way fee={a.fee_rate:.4%}")
    print(f"  take-all      : {ta.mean():+.2f}%/day  win {(scored.net_realized_ret>0).mean()*100:.0f}%")
    sa = scored[scored.kp_star == True]; sb = scored[scored.vb_star == True]
    print(f"  A  K->P        : {A.mean():+.2f}%/day  win {(sa.net_realized_ret>0).mean()*100:.0f}%  (n={len(sa)})")
    print(f"  B  K->P+auction: {B.mean():+.2f}%/day  win {(sb.net_realized_ret>0).mean()*100:.0f}%  (n={len(sb)})")
    if "mode_star" in scored.columns and len(C):
        sc = scored[scored.mode_star == True]
        print(f"  C  K->mode-rank: {C.mean():+.2f}%/day  win {(sc.net_realized_ret>0).mean()*100:.0f}%  (n={len(sc)})")
    if len(D):
        sd = scored[scored.qibao_benchmark_star == True]
        print(f"  D  qibao-bench : {D.mean():+.2f}%/day  win {(sd.net_realized_ret>0).mean()*100:.0f}%  (n={len(sd)})")
    if len(E):
        se = scored[scored.ai_intelligence_short_star == True]
        print(f"  E  AI-intel    : {E.mean():+.2f}%/day  win {(se.net_realized_ret>0).mean()*100:.0f}%  (n={len(se)})")
    # contrast frequency: days where B's pick set actually differs from A's.
    # Without contrast the A/B comparison carries no information.
    diff_days = sum(
        1 for _, g in scored.groupby("date")
        if set(g.loc[g.kp_star == True, "code"]) != set(g.loc[g.vb_star == True, "code"])
    )
    print(f"  A/B contrast   : B != A on {diff_days}/{scored['date'].nunique()} days"
          + ("  (zero contrast — verdict uninformative)" if diff_days == 0 else ""))
    e_pick_days = sum(
        1 for _, g in scored.groupby("date")
        if len(set(g.loc[g.ai_intelligence_short_star == True, "code"])) > 0
    )
    e_diff_b_days = sum(
        1 for _, g in scored.groupby("date")
        if set(g.loc[g.ai_intelligence_short_star == True, "code"])
        and set(g.loc[g.ai_intelligence_short_star == True, "code"]) != set(g.loc[g.vb_star == True, "code"])
    )
    print(f"  E contrast     : AI-intel picked on {e_pick_days}/{scored['date'].nunique()} days; "
          f"E != B on {e_diff_b_days}/{scored['date'].nunique()} days")
    if len(A) >= 8:
        from scipy.stats import ttest_rel
        n = min(len(A), len(B), len(ta))
        print(f"  paired vs take-all: A p={ttest_rel(A[:n],ta[:n])[1]:.3f}  B p={ttest_rel(B[:n],ta[:n])[1]:.3f}")
        if len(C) >= 8:
            n = min(len(C), len(ta))
            print(f"                      C p={ttest_rel(C[:n],ta[:n])[1]:.3f}")
        if len(D) >= 8:
            n = min(len(D), len(ta))
            print(f"                      D p={ttest_rel(D[:n],ta[:n])[1]:.3f}")
        if len(E) >= 8:
            n = min(len(E), len(ta))
            print(f"                      E p={ttest_rel(E[:n],ta[:n])[1]:.3f}")


if __name__ == "__main__":
    main()
