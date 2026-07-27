"""Join captured live snapshots with realized next-close returns -> (1) A/B/C/D/E/F
verdict (A = K->P, B = K->P + auction imbalance, C = K survivors + legacy
mode rank, D = qibao benchmark modes, E = agent-reviewed AI intelligence
shadow, F = executable mode-qualified ★E),
(2) accumulated labeled training rows for future models.

Run any time after the outcome day's close is available (T+1+). Idempotent.
"""
from __future__ import annotations
import argparse, json, time
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
MARKET_INDEX_CODES = ("000001.XSHG", "399001.XSHE", "399006.XSHE", "000852.XSHG")
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
    "stock_rank_score": pd.NA,
    "mode_exec_star": False,
    "mode_exec_rank": pd.NA,
    "mode_exec_score": pd.NA,
    "mode_exec_rank_score": pd.NA,
    "mode_exec_mode_confidence": 50.0,
    "mode_exec_confidence_source": pd.NA,
    "mode_exec_confidence_reason": pd.NA,
    "mode_exec_target_weight": 0.0,
    "mode_exec_candidate_rank": pd.NA,
    "mode_state": pd.NA,
    "mode_state_reason": pd.NA,
    "mode_state_window": pd.NA,
    "mode_state_max_picks": 0,
    "mode_trade_eligible": False,
    "mode_evidence_source": pd.NA,
    "mode_evidence_latest_date": pd.NA,
    "mode_evidence_days": 0,
    "mode_evidence_signals": 0,
    "mode_evidence_market_days": 0,
    "mode_evidence_effective_days": 0.0,
    "mode_evidence_weighting": pd.NA,
    "mode_return_raw": pd.NA,
    "mode_alpha_pool": pd.NA,
    "mode_alpha_pool_lcb80": pd.NA,
    "mode_alpha_market": pd.NA,
    "mode_alpha_market_lcb80": pd.NA,
    "mode_fast_health": pd.NA,
    "mode_fast_authority": "shadow_only",
    "mode_fast_days": 0,
    "mode_fast_signals": 0,
    "mode_fast_alpha_pool": pd.NA,
    "mode_fast_alpha_market": pd.NA,
    "mode_fast_positive_pool_days": 0,
    "mode_fast_positive_market_days": 0,
    "executable_fillable": False,
    "executable_entry_price": pd.NA,
    "executable_entry_basis": pd.NA,
    "executable_skip_reason": pd.NA,
    "executable_net_ret": pd.NA,
    "market_return_pct": pd.NA,
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
PARQUET_STRING_COLUMNS = (
    "excIndustryCode",
    "blockCodeList",
    "blockCategoryCodeList",
    "mode_state",
    "mode_state_reason",
    "mode_evidence_source",
    "mode_evidence_latest_date",
    "mode_evidence_weighting",
    "mode_fast_health",
    "mode_fast_authority",
    "mode_exec_confidence_source",
    "mode_exec_confidence_reason",
    "executable_entry_basis",
    "executable_skip_reason",
)


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


def _daily_series(client, code: str, reconstructed: dict[str, dict[str, dict]], *, count: int = 400) -> dict[str, dict]:
    try:
        payload = client.date_kline(code, count=count, freq="D", adj="qfq")
    except Exception:
        payload = []
    rows = payload if isinstance(payload, list) else []
    series: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("tradeDate"):
            continue
        series[_normal_date(row.get("tradeDate"))] = row
    series.update(reconstructed.get(str(code), {}))
    return series


def _market_return_map(
    client,
    signal_dates: list[str],
    reconstructed: dict[str, dict[str, dict]],
) -> dict[str, float]:
    """Four-index equal-weight open[D] -> close[D+1] benchmark."""
    by_day: dict[str, list[float]] = defaultdict(list)
    wanted = set(signal_dates)
    for code in MARKET_INDEX_CODES:
        series = _daily_series(client, code, reconstructed)
        dates = sorted(series)
        position = {day: index for index, day in enumerate(dates)}
        for day in wanted:
            index = position.get(day)
            if index is None or index + 1 >= len(dates):
                continue
            entry = _to_float(series[day].get("open"))
            exit_price = _to_float(series[dates[index + 1]].get("close"))
            if entry is not None and entry > 0 and exit_price is not None and exit_price > 0:
                by_day[day].append((exit_price / entry - 1.0) * 100.0)
    return {
        day: float(np.mean(values))
        for day, values in by_day.items()
        if len(values) == len(MARKET_INDEX_CODES)
    }


def _to_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _previous_executable_rows(path: Path = TRAIN) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return {}
    required = {"date", "code", "executable_fillable"}
    if frame.empty or not required.issubset(frame.columns):
        return {}
    fields = (
        "executable_fillable",
        "executable_entry_price",
        "executable_entry_basis",
        "executable_skip_reason",
        "executable_net_ret",
    )
    out: dict[tuple[str, str], dict] = {}
    for row in frame.to_dict(orient="records"):
        if all(field not in row for field in fields):
            continue
        key = (str(row.get("date") or "")[:10], str(row.get("code") or ""))
        out[key] = {field: row.get(field) for field in fields}
    return out


def _is_known_executable(record: dict | None) -> bool:
    if not record:
        return False
    reason = record.get("executable_skip_reason")
    fillable = record.get("executable_fillable")
    try:
        has_fill = not pd.isna(fillable) and bool(fillable)
        has_reason = reason is not None and not pd.isna(reason) and bool(str(reason).strip())
    except (TypeError, ValueError):
        return False
    return has_fill or has_reason


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
        values = pd.to_numeric(sel[ret_col], errors="coerce").dropna() if len(sel) else pd.Series(dtype=float)
        if len(values):
            per.append(values.mean())
    return np.array(per)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", default=str(SNAP))
    ap.add_argument("--cache", default="output/.cache/xiaocao.db")
    ap.add_argument("--live-only", action="store_true", help="only score is_live=true rows")
    ap.add_argument("--fee-rate", type=float, default=DEFAULT_FEE_RATE,
                    help="one-way transaction fee rate, e.g. 0.0001 = 1bp")
    ap.add_argument(
        "--backfill-executable-max",
        type=int,
        default=20,
        help="maximum missing all-hit opening-window fills to backfill this run",
    )
    ap.add_argument(
        "--backfill-sleep-sec",
        type=float,
        default=0.55,
        help="rate-limit pause between executable minute-line backfills",
    )
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

    # Statistical label: signal open[D] -> close[D+1].  This remains in the
    # dataset for shape research, but it cannot open the mode trading gate.
    rets = {}
    exit_prices = {}
    for code in df["code"].unique():
        ser = _daily_series(cli, str(code), reconstructed)
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
                exit_prices[(d, code)] = exit_price
    df["realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[0] for r in df.itertuples()
    ]
    df["net_realized_ret"] = [
        rets.get((r.date, r.code), (None, None))[1] for r in df.itertuples()
    ]
    df["fee_rate"] = a.fee_rate
    market_returns = _market_return_map(
        cli,
        sorted({str(day)[:10] for day in df["date"].unique()}),
        reconstructed,
    )
    df["market_return_pct"] = [market_returns.get(str(r.date)[:10]) for r in df.itertuples()]

    # Executable all-hit label: the same opening-window fill model used by
    # Book B, including basket abandonment and user board permissions.  Reuse
    # prior labels and rate-limit only newly settled rows.
    import paper_record as paper_fill

    previous_exec = _previous_executable_rows()
    executable: dict[tuple[str, str], dict] = {}
    backfilled = 0
    max_backfill = max(0, int(a.backfill_executable_max))
    for row in df.itertuples():
        day = str(row.date)[:10]
        code = str(row.code)
        key = (day, code)
        if key not in rets:
            continue
        prior = previous_exec.get(key)
        if _is_known_executable(prior):
            executable[key] = dict(prior or {})
            continue
        if code.endswith(".BJSE"):
            executable[key] = {
                "executable_fillable": False,
                "executable_entry_price": None,
                "executable_entry_basis": None,
                "executable_skip_reason": "NO_USER_BOARD_PERMISSION",
                "executable_net_ret": None,
            }
            continue
        if backfilled >= max_backfill:
            continue
        record = row._asdict()
        window = paper_fill._fill_window_stats(
            cli,
            code,
            day,
            start_hhmm="0930",
            end_hhmm="0931",
        )
        backfilled += 1
        if a.backfill_sleep_sec > 0:
            time.sleep(float(a.backfill_sleep_sec))
        # A missing minute window is missing evidence, not permission to use
        # the paper fill fallback.  Leave it pending so a later EOD can retry.
        if window is None:
            continue
        fill_price, basis, _, meta = paper_fill._fill_price_from_window(
            record,
            window=window,
            limit_premium_pct=0.5,
        )
        if fill_price is None:
            executable[key] = {
                "executable_fillable": False,
                "executable_entry_price": None,
                "executable_entry_basis": basis,
                "executable_skip_reason": meta.get("skip_reason") or "NO_EXECUTABLE_OPENING_FILL",
                "executable_net_ret": None,
            }
            continue
        exit_price = exit_prices.get(key)
        if not exit_price:
            continue
        executable[key] = {
            "executable_fillable": True,
            "executable_entry_price": float(fill_price),
            "executable_entry_basis": basis,
            "executable_skip_reason": None,
            "executable_net_ret": (
                (float(exit_price) * (1 - a.fee_rate))
                / (float(fill_price) * (1 + a.fee_rate))
                - 1.0
            ) * 100.0,
        }
    for field in (
        "executable_fillable",
        "executable_entry_price",
        "executable_entry_basis",
        "executable_skip_reason",
        "executable_net_ret",
    ):
        df[field] = [executable.get((str(r.date)[:10], str(r.code)), {}).get(field) for r in df.itertuples()]

    scored = ensure_training_schema(df[df["realized_ret"].notna()].copy())
    executable_known = int(pd.to_numeric(scored["executable_net_ret"], errors="coerce").notna().sum())
    print(
        f"snapshots={len(df)}  scored(outcome known)={len(scored)}  "
        f"pending={len(df)-len(scored)}  executable={executable_known}  "
        f"backfilled={backfilled}"
    )
    if scored.empty:
        print("no outcomes available yet — re-run after T+1 close."); return

    # accumulate training rows
    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(TRAIN, index=False)
    print(f"accumulated {len(scored)} labeled training rows -> {TRAIN}")

    # A/B/C/D/E/F by day
    ta = day_mean(scored, "net_realized_ret")
    A = day_mean(scored, "net_realized_ret", "kp_star")
    B = day_mean(scored, "net_realized_ret", "vb_star")
    C = day_mean(scored, "net_realized_ret", "mode_star")
    D = day_mean(scored, "net_realized_ret", "qibao_benchmark_star")
    E = day_mean(scored, "net_realized_ret", "ai_intelligence_short_star")
    F = day_mean(scored, "executable_net_ret", "mode_exec_star")
    print(f"\nA/B/C/D/E/F over {scored['date'].nunique()} live days ({scored.date.min()}..{scored.date.max()}):")
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
    if len(F):
        sf = scored[(scored.mode_exec_star == True) & scored.executable_net_ret.notna()]  # noqa: E712
        print(
            f"  F  mode-exec   : {F.mean():+.2f}%/day  "
            f"win {(sf.executable_net_ret>0).mean()*100:.0f}%  (n={len(sf)})"
        )
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
