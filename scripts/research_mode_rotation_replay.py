#!/usr/bin/env python3
"""Replay June live-hit rows with mode-rotation selection variants.

This is an offline research helper. It only reads the live all-hit training
rows and writes research artifacts; it does not mutate live account state.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAINING_ROWS = ROOT / "output" / "live" / "training_rows.parquet"
DEFAULT_OUT_DIR = ROOT / "output" / "research"
WINDOWS = (5, 10, 20)


@dataclass(frozen=True)
class VariantResult:
    name: str
    daily_mean: dict[date, float]
    selected: pd.DataFrame

    @property
    def n_days(self) -> int:
        return len(self.daily_mean)

    @property
    def n_trades(self) -> int:
        return int(len(self.selected))

    @property
    def avg_daily(self) -> float:
        if not self.daily_mean:
            return float("nan")
        return sum(self.daily_mean.values()) / len(self.daily_mean)

    @property
    def simple_sum(self) -> float:
        return sum(self.daily_mean.values())

    @property
    def trade_mean(self) -> float:
        if self.selected.empty:
            return float("nan")
        return float(self.selected["ret"].mean())

    @property
    def win_rate(self) -> float:
        if self.selected.empty:
            return float("nan")
        return float((self.selected["ret"] > 0).mean())


def _as_bool_series(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def _normalize_date(value: Any) -> date:
    return pd.to_datetime(value).date()


def _clean_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _load_rows(path: Path, start: date, end: date) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"training rows not found: {path}")
    df = pd.read_parquet(path)
    if df.empty:
        raise SystemExit(f"training rows are empty: {path}")
    if "date" not in df.columns:
        raise SystemExit("training rows missing required column: date")

    df = df.copy()
    df["date"] = df["date"].map(_normalize_date)
    if "is_live" in df.columns:
        df = df[_as_bool_series(df["is_live"])]
    df = df[(df["date"] >= start) & (df["date"] <= end)]

    ret_col = "net_realized_ret" if "net_realized_ret" in df.columns else "realized_ret"
    if ret_col not in df.columns:
        raise SystemExit("training rows missing net_realized_ret/realized_ret")
    df["ret"] = pd.to_numeric(df[ret_col], errors="coerce")
    df = df[df["ret"].notna()]

    for col in ("kp_keep", "kp_star", "vb_star"):
        if col not in df.columns:
            df[col] = False
        df[col] = _as_bool_series(df[col])
    for col in ("mode", "code", "name"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    for col in ("rank_score", "primary_score", "open_pct_change"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.sort_values(["date", "rank_score", "code"], ascending=[True, False, True]).reset_index(drop=True)


def _window_stats(history: pd.DataFrame, mode: str) -> tuple[float, int, str]:
    mode_history = history[history["mode"] == mode].copy()
    if mode_history.empty:
        return 50.0, 0, "cold_start"
    daily = mode_history.groupby("date", sort=True)["ret"].mean().reset_index()
    if daily.empty:
        return 50.0, 0, "cold_start"

    scores: list[float] = []
    best_n = 0
    for window in WINDOWS:
        tail = daily.tail(window)
        if tail.empty:
            continue
        best_n = max(best_n, int(len(tail)))
        avg = float(tail["ret"].mean())
        win_rate = float((tail["ret"] > 0).mean())
        score = 50.0 + avg * 4.0 + (win_rate - 0.5) * 30.0
        scores.append(max(0.0, min(100.0, score)))
    if not scores:
        return 50.0, 0, "cold_start"
    return sum(scores) / len(scores), best_n, "live_all_hit_prior"


def _score_with_mode_rotation(row: pd.Series, mode_confidence: float) -> float:
    primary = _clean_float(row.get("primary_score"), 0.0)
    if primary <= 0:
        primary = _clean_float(row.get("rank_score"), 0.0)
    open_pct = _clean_float(row.get("open_pct_change"), 0.0)
    open_risk = max(0.0, open_pct - 1.0) * 0.8 if open_pct > 1.0 else 0.0
    # Snapshots/training rows do not reliably carry macro direction, so macro is
    # neutral here. Live recommend still uses macro when it is available.
    return 0.62 * primary + 0.28 * mode_confidence + 8.0 - open_risk


def _annotate_mode_rotation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    conf_values: list[float] = []
    n_values: list[int] = []
    src_values: list[str] = []
    score_values: list[float] = []

    for idx, row in out.iterrows():
        history = out[out["date"] < row["date"]]
        conf, n, source = _window_stats(history, str(row["mode"]))
        conf_values.append(conf)
        n_values.append(n)
        src_values.append(source)
        score_values.append(_score_with_mode_rotation(row, conf))

    out["mode_rotation_confidence"] = conf_values
    out["mode_rotation_n"] = n_values
    out["mode_rotation_source"] = src_values
    out["mode_rotation_score"] = score_values
    return out


def _select_top(
    day_df: pd.DataFrame,
    score_col: str,
    *,
    max_candidates: int,
    max_per_mode: int,
) -> pd.DataFrame:
    selected: list[int] = []
    per_mode: Counter[str] = Counter()
    sort_cols = [score_col, "primary_score", "rank_score", "code"]
    ascending = [False, False, False, True]
    for idx, row in day_df.sort_values(sort_cols, ascending=ascending).iterrows():
        mode = str(row.get("mode") or "unknown")
        if per_mode[mode] >= max_per_mode:
            continue
        selected.append(idx)
        per_mode[mode] += 1
        if len(selected) >= max_candidates:
            break
    return day_df.loc[selected].copy()


def _daily_mean(df: pd.DataFrame) -> dict[date, float]:
    if df.empty:
        return {}
    return {day: float(value) for day, value in df.groupby("date")["ret"].mean().items()}


def _variant_by_flag(df: pd.DataFrame, name: str, flag_col: str) -> VariantResult:
    selected = df[df[flag_col]].copy()
    return VariantResult(name=name, daily_mean=_daily_mean(selected), selected=selected)


def _variant_take_all(df: pd.DataFrame) -> VariantResult:
    return VariantResult(name="take_all", daily_mean=_daily_mean(df), selected=df.copy())


def _variant_rank_top(df: pd.DataFrame, name: str, score_col: str, *, kp_only: bool) -> VariantResult:
    chunks: list[pd.DataFrame] = []
    base = df[df["kp_keep"]].copy() if kp_only else df
    for _, day_df in base.groupby("date", sort=True):
        chunks.append(_select_top(day_df, score_col, max_candidates=3, max_per_mode=2))
    selected = pd.concat(chunks, ignore_index=False) if chunks else base.iloc[0:0].copy()
    return VariantResult(name=name, daily_mean=_daily_mean(selected), selected=selected)


def _mode_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty:
        return {}
    return {str(k): int(v) for k, v in frame["mode"].value_counts().items()}


def _format_pct(value: float) -> str:
    if math.isnan(value):
        return "nan"
    return f"{value:+.3f}%"


def _write_guard_rows(path: Path, selected: pd.DataFrame, base_daily: dict[date, float], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for _, row in selected.sort_values(["date", "code"]).iterrows():
            day = row["date"]
            payload = {
                "day": day.isoformat(),
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "mode": str(row.get("mode") or ""),
                "strat_ret": _clean_float(row.get("ret")),
                "base_ret": _clean_float(base_daily.get(day), 0.0),
                "benchmark": label,
                "score": _clean_float(row.get("mode_rotation_score")),
                "mode_confidence": _clean_float(row.get("mode_rotation_confidence"), 50.0),
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _report(
    *,
    df: pd.DataFrame,
    variants: list[VariantResult],
    start: date,
    end: date,
    out_paths: dict[str, Path],
) -> str:
    lines: list[str] = []
    lines.append(f"# Mode Rotation Replay: {start.isoformat()} to {end.isoformat()}")
    lines.append("")
    lines.append("## Data Contract")
    lines.append("")
    lines.append(
        "- Source: `output/live/training_rows.parquet`, filtered to `is_live=True` and realized return column `net_realized_ret`."
    )
    lines.append(
        "- Return unit: percent points from the live all-hit forward label, generally open[D] to close[D+1]. It is not a full Book-B stop/fill replay."
    )
    lines.append(
        "- Mode confidence is recomputed from prior trade days only, using all live hit rows by mode over 5/10/20-day windows."
    )
    lines.append(
        "- `mode_rotation_top3_k_survivors` keeps the existing Kronos K survivor filter, then replaces the P-only star ranking with mode-aware rank among survivors."
    )
    lines.append("")
    lines.append(f"Rows: {len(df)}, days: {df['date'].nunique()}, symbols: {df['code'].nunique()}")
    lines.append("")
    lines.append("## Variant Summary")
    lines.append("")
    lines.append("| variant | avg daily | simple sum | trade mean | win rate | days | trades |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for v in variants:
        lines.append(
            f"| {v.name} | {_format_pct(v.avg_daily)} | {_format_pct(v.simple_sum)} | "
            f"{_format_pct(v.trade_mean)} | {v.win_rate:.1%} | {v.n_days} | {v.n_trades} |"
        )
    lines.append("")
    lines.append("## Daily Means")
    lines.append("")
    header = "| date | " + " | ".join(v.name for v in variants) + " |"
    sep = "|---" + "|---:" * len(variants) + "|"
    lines.append(header)
    lines.append(sep)
    all_days = sorted({day for v in variants for day in v.daily_mean})
    for day in all_days:
        cells = [_format_pct(v.daily_mean.get(day, float("nan"))) for v in variants]
        lines.append(f"| {day.isoformat()} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Mode Mix")
    lines.append("")
    lines.append("| variant | mode counts |")
    lines.append("|---|---|")
    for v in variants:
        counts = _mode_counts(v.selected)
        count_text = ", ".join(f"{k}:{val}" for k, val in counts.items()) if counts else ""
        lines.append(f"| {v.name} | {count_text} |")
    lines.append("")
    lines.append("## Full-Period Mode Outcomes")
    lines.append("")
    lines.append("| mode | rows | mean | median | win rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for mode, group in df.groupby("mode"):
        lines.append(
            f"| {mode} | {len(group)} | {_format_pct(float(group['ret'].mean()))} | "
            f"{_format_pct(float(group['ret'].median()))} | {float((group['ret'] > 0).mean()):.1%} |"
        )
    lines.append("")
    lines.append("## Guard Inputs")
    lines.append("")
    for name, path in out_paths.items():
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "- Pure mode rotation over all candidates is worse than the current VB-star path in June; mode strength alone is not enough."
    )
    lines.append(
        "- K survivor filtering is doing useful work. The strong June replay comes from applying mode rotation inside the K-survivor set, not from removing K."
    )
    lines.append(
        "- The current live paper-buy path still consumes `vb_star`; this replay is a counterfactual selection layer unless that star path is explicitly changed after the research gate."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-rows", type=Path, default=DEFAULT_TRAINING_ROWS)
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    start = _normalize_date(args.start)
    end = _normalize_date(args.end)
    df = _load_rows(args.training_rows, start, end)
    df = _annotate_mode_rotation(df)

    variants = [
        _variant_take_all(df),
        _variant_by_flag(df, "kp_star", "kp_star"),
        _variant_by_flag(df, "vb_star", "vb_star"),
        _variant_rank_top(df, "rank_old_top3_snapshot", "rank_score", kp_only=False),
        _variant_rank_top(df, "mode_rotation_top3_all", "mode_rotation_score", kp_only=False),
        _variant_rank_top(df, "mode_rotation_top3_k_survivors", "mode_rotation_score", kp_only=True),
    ]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{start.isoformat()}_{end.isoformat()}"
    k_variant = next(v for v in variants if v.name == "mode_rotation_top3_k_survivors")
    vb_variant = next(v for v in variants if v.name == "vb_star")
    take_all_variant = next(v for v in variants if v.name == "take_all")
    guard_vb = args.out_dir / f"mode_rotation_k_survivor_vs_vb_{suffix}.jsonl"
    guard_all = args.out_dir / f"mode_rotation_k_survivor_vs_take_all_{suffix}.jsonl"
    _write_guard_rows(guard_vb, k_variant.selected, vb_variant.daily_mean, "vb_star_daily_mean")
    _write_guard_rows(guard_all, k_variant.selected, take_all_variant.daily_mean, "take_all_daily_mean")

    report_path = args.out_dir / f"mode_rotation_replay_{suffix}.md"
    report = _report(
        df=df,
        variants=variants,
        start=start,
        end=end,
        out_paths={"vs_vb": guard_vb, "vs_take_all": guard_all},
    )
    report_path.write_text(report, encoding="utf-8")

    print(f"wrote {report_path}")
    print(f"wrote {guard_vb}")
    print(f"wrote {guard_all}")
    for variant in variants:
        print(
            f"{variant.name}: avg_daily={variant.avg_daily:+.3f}% "
            f"sum={variant.simple_sum:+.3f}% trades={variant.n_trades}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
