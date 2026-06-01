"""Tune live recommendation ranking against historical signal GT.

This is intentionally cache/file-only: it reads historical `signals_*.json`
and `trades.csv`, then evaluates daily top-N selection rules with random
date-level train/validation splits. The goal is robustness, not a single
in-sample best score.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "output" / "mode_history_rebuild_orderfix_20260518"
OUT_DIR = ROOT / "output" / "rank_tuning"
EXCLUDE_MODES = {"接力低弱转2", "方向内绿盘低吸前3名"}
WINDOWS = (5, 10, 20)
WINDOW_WEIGHTS = {5: 0.50, 10: 0.30, 20: 0.20}


@dataclass(frozen=True)
class SignalOutcome:
    date: str
    code: str
    name: str
    mode: str
    return_pct: float
    open_pct: float
    xcjw: float
    cjs: float
    jsjl: float
    jssb: float
    direction_rank: int
    category_rank: int


@dataclass(frozen=True)
class Config:
    score_w: float
    conf_w: float
    macro_w: float
    open_w: float
    score_denom: float
    macro_top: float
    macro_second: float
    macro_third: float
    open_cap: float
    deep_low_cut: float
    max_candidates: int
    max_per_mode: int


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = -1) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _primary_score(sig: SignalOutcome) -> float:
    if "起爆" in sig.mode:
        return sig.jssb
    if sig.mode.startswith("接力"):
        return sig.xcjw + max(sig.jsjl, 0.0) * 0.5
    if sig.mode in {"N字低吸", "孕线低吸"}:
        return sig.xcjw + sig.cjs * 0.6
    return sig.xcjw + sig.cjs * 0.8


def _macro_rank_value(rank: int, cfg: Config) -> float:
    if rank < 0:
        return 0.0
    if rank == 0:
        return cfg.macro_top
    if rank == 1:
        return cfg.macro_second
    if rank == 2:
        return cfg.macro_third
    return cfg.macro_third * 0.75


def _macro_score(sig: SignalOutcome, cfg: Config) -> float:
    return max(
        _macro_rank_value(sig.direction_rank, cfg),
        _macro_rank_value(sig.category_rank, cfg),
    )


def _open_risk(sig: SignalOutcome, cfg: Config) -> float:
    op = sig.open_pct
    if sig.mode.startswith("接力") or "起爆" in sig.mode:
        high = max(0.0, op - 3.0) * 8.0
        weak = max(0.0, -2.0 - op) * 5.0
        return min(35.0, high + weak)
    deep = max(0.0, cfg.deep_low_cut - op) * 8.0
    chase = max(0.0, op - 1.5) * 6.0
    return min(35.0, deep + chase)


def _mode_confidence(
    sig: SignalOutcome,
    history_by_mode: dict[str, dict[str, list[float]]],
    trade_days: list[str],
    day_index: dict[str, int],
) -> float:
    idx = day_index[sig.date]
    weighted = 0.0
    weight_sum = 0.0
    max_n = 0
    mode_hist = history_by_mode.get(sig.mode, {})
    for window in WINDOWS:
        prior_days = trade_days[max(0, idx - window):idx]
        vals: list[float] = []
        for d in prior_days:
            vals.extend(mode_hist.get(d, []))
        if not vals:
            continue
        avg = statistics.mean(vals)
        weight = WINDOW_WEIGHTS[window]
        weighted += avg * weight
        weight_sum += weight
        max_n = max(max_n, len(vals))
    if weight_sum <= 0:
        return 50.0
    recent_avg = weighted / weight_sum
    raw = 50.0 + max(-10.0, min(10.0, recent_avg)) * 4.0
    shrink = min(1.0, max_n / 8.0)
    return max(0.0, min(100.0, 50.0 + (raw - 50.0) * shrink))


def _signal_key(sig: SignalOutcome) -> tuple[str, str, str]:
    return sig.date, sig.mode, sig.code


def build_confidence_by_signal(
    rows: list[SignalOutcome],
    history_by_mode: dict[str, dict[str, list[float]]],
    trade_days: list[str],
    day_index: dict[str, int],
) -> dict[tuple[str, str, str], float]:
    return {
        _signal_key(sig): _mode_confidence(sig, history_by_mode, trade_days, day_index)
        for sig in rows
    }


def _rank_score(
    sig: SignalOutcome,
    cfg: Config,
    confidence_by_signal: dict[tuple[str, str, str], float],
) -> float:
    score_fit = min(140.0, _primary_score(sig) / cfg.score_denom * 100.0)
    conf = confidence_by_signal.get(_signal_key(sig), 50.0)
    macro = _macro_score(sig, cfg)
    risk = _open_risk(sig, cfg)
    return score_fit * cfg.score_w + conf * cfg.conf_w + macro * cfg.macro_w - risk * cfg.open_w


def load_data(source_dir: Path) -> list[SignalOutcome]:
    trades_path = source_dir / "trades.csv"
    if not trades_path.exists():
        raise SystemExit(f"missing {trades_path}")
    trades: dict[tuple[str, str, str], dict[str, str]] = {}
    with trades_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            trades[(row["buyDate"], row["mode"], row["code"])] = row

    rows: list[SignalOutcome] = []
    for path in sorted(source_dir.glob("signals_*.json")):
        date = path.stem.replace("signals_", "")
        try:
            signals = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(signals, list):
            continue
        for sig in signals:
            if not isinstance(sig, dict):
                continue
            key = (date, str(sig.get("mode") or ""), str(sig.get("code") or ""))
            tr = trades.get(key)
            if tr is None:
                continue
            rows.append(
                SignalOutcome(
                    date=date,
                    code=key[2],
                    name=str(sig.get("name") or tr.get("name") or ""),
                    mode=key[1],
                    return_pct=_f(tr.get("returnPct")),
                    open_pct=_f(tr.get("openPctChange"), _f(sig.get("openPctChange"))),
                    xcjw=_f(sig.get("xcjw"), _f(tr.get("xcjw"))),
                    cjs=_f(sig.get("cjs"), _f(tr.get("cjs"))),
                    jsjl=_f(sig.get("jsjl"), _f(tr.get("jsjl"))),
                    jssb=_f(sig.get("jssb")),
                    direction_rank=_i(sig.get("directionRank")),
                    category_rank=_i(sig.get("categoryRank")),
                )
            )
    return rows


def split_by_day(rows: list[SignalOutcome]) -> tuple[list[str], dict[str, list[SignalOutcome]]]:
    by_day: dict[str, list[SignalOutcome]] = {}
    for row in rows:
        by_day.setdefault(row.date, []).append(row)
    return sorted(by_day), by_day


def build_history(rows: list[SignalOutcome]) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        out.setdefault(row.mode, {}).setdefault(row.date, []).append(row.return_pct)
    return out


def select_day(
    signals: list[SignalOutcome],
    cfg: Config,
    confidence_by_signal: dict[tuple[str, str, str], float],
) -> list[SignalOutcome]:
    candidates = [
        s for s in signals
        if s.mode not in EXCLUDE_MODES and s.open_pct < cfg.open_cap
    ]
    ranked = sorted(
        candidates,
        key=lambda s: (
            -_rank_score(s, cfg, confidence_by_signal),
            -_primary_score(s),
            s.code,
        ),
    )
    selected: list[SignalOutcome] = []
    by_mode: dict[str, int] = {}
    for sig in ranked:
        if len(selected) >= cfg.max_candidates:
            break
        if by_mode.get(sig.mode, 0) >= cfg.max_per_mode:
            continue
        selected.append(sig)
        by_mode[sig.mode] = by_mode.get(sig.mode, 0) + 1
    return selected


@dataclass(frozen=True)
class EvalStats:
    n: int
    days: int
    avg: float
    median: float
    win: float
    total: float
    daily_avg: float
    daily_win: float
    worst_day: float
    sharpe_like: float


def stats_for(returns: list[float], daily_returns: list[float]) -> EvalStats:
    if not returns:
        return EvalStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    wins = sum(1 for v in returns if v > 0)
    day_wins = sum(1 for v in daily_returns if v > 0)
    daily_std = statistics.pstdev(daily_returns) if len(daily_returns) > 1 else 0.0
    daily_avg = statistics.mean(daily_returns) if daily_returns else 0.0
    sharpe = daily_avg / daily_std if daily_std > 0 else 0.0
    return EvalStats(
        n=len(returns),
        days=len(daily_returns),
        avg=statistics.mean(returns),
        median=statistics.median(returns),
        win=wins / len(returns) * 100,
        total=sum(returns),
        daily_avg=daily_avg,
        daily_win=day_wins / len(daily_returns) * 100 if daily_returns else 0.0,
        worst_day=min(daily_returns) if daily_returns else 0.0,
        sharpe_like=sharpe,
    )


def evaluate(
    cfg: Config,
    days: set[str],
    by_day: dict[str, list[SignalOutcome]],
    confidence_by_signal: dict[tuple[str, str, str], float],
) -> EvalStats:
    returns: list[float] = []
    daily_returns: list[float] = []
    for day in sorted(days):
        selected = select_day(by_day.get(day, []), cfg, confidence_by_signal)
        if not selected:
            continue
        vals = [s.return_pct for s in selected]
        returns.extend(vals)
        daily_returns.append(statistics.mean(vals))
    return stats_for(returns, daily_returns)


def random_config(rng: random.Random) -> Config:
    return Config(
        score_w=rng.choice([0.45, 0.50, 0.55, 0.60, 0.65, 0.70]),
        conf_w=rng.choice([0.10, 0.15, 0.20, 0.25, 0.30]),
        macro_w=rng.choice([0.00, 0.08, 0.12, 0.16, 0.20, 0.24, 0.30]),
        open_w=rng.choice([0.6, 0.8, 1.0, 1.2, 1.5]),
        score_denom=rng.choice([250.0, 300.0, 350.0, 400.0, 500.0]),
        macro_top=rng.choice([80.0, 90.0, 100.0, 115.0, 130.0]),
        macro_second=rng.choice([55.0, 70.0, 85.0, 100.0]),
        macro_third=rng.choice([40.0, 55.0, 70.0]),
        open_cap=rng.choice([4.0, 5.0, 6.0, 8.0, 12.0]),
        deep_low_cut=rng.choice([-10.0, -9.0, -8.5, -8.0, -7.0]),
        max_candidates=rng.choice([2, 3, 4]),
        max_per_mode=rng.choice([1, 2, 3]),
    )


def current_config() -> Config:
    return Config(
        score_w=0.60,
        conf_w=0.25,
        macro_w=0.18,
        open_w=1.0,
        score_denom=350.0,
        macro_top=100.0,
        macro_second=85.0,
        macro_third=70.0,
        open_cap=6.0,
        deep_low_cut=-7.0,
        max_candidates=3,
        max_per_mode=2,
    )


def robust_score(train: EvalStats, val: EvalStats) -> float:
    if train.n < 80 or val.n < 30:
        return -999.0
    if val.daily_avg <= 0:
        return -999.0 + val.daily_avg
    return (
        min(train.daily_avg, val.daily_avg) * 2.0
        + val.avg * 0.40
        + val.win * 0.015
        + val.sharpe_like * 0.40
        + min(0.0, val.worst_day) * 0.05
        - max(0.0, train.daily_avg - val.daily_avg) * 0.50
    )


def make_split(days: list[str], rng: random.Random, train_frac: float = 2 / 3) -> tuple[set[str], set[str]]:
    shuffled = list(days)
    rng.shuffle(shuffled)
    cut = int(len(shuffled) * train_frac)
    return set(shuffled[:cut]), set(shuffled[cut:])


def fmt_stats(s: EvalStats) -> str:
    return (
        f"n={s.n} days={s.days} avg={s.avg:+.2f}% med={s.median:+.2f}% "
        f"win={s.win:.1f}% daily={s.daily_avg:+.2f}% worstDay={s.worst_day:+.2f}%"
    )


def cfg_dict(cfg: Config) -> dict[str, Any]:
    return cfg.__dict__.copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--samples", type=int, default=4000)
    parser.add_argument("--splits", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    rows = load_data(args.source_dir)
    trade_days, by_day = split_by_day(rows)
    day_index = {d: i for i, d in enumerate(trade_days)}
    history_by_mode = build_history(rows)
    confidence_by_signal = build_confidence_by_signal(rows, history_by_mode, trade_days, day_index)
    usable_days = [d for d in trade_days if by_day.get(d)]
    rng = random.Random(args.seed)
    splits = [make_split(usable_days, random.Random(args.seed + i)) for i in range(args.splits)]

    configs = [current_config()]
    seen = {current_config()}
    while len(configs) < args.samples + 1:
        cfg = random_config(rng)
        if cfg in seen:
            continue
        seen.add(cfg)
        configs.append(cfg)

    scored: list[dict[str, Any]] = []
    for cfg in configs:
        train_scores: list[EvalStats] = []
        val_scores: list[EvalStats] = []
        robust_values: list[float] = []
        for train_days, val_days in splits:
            tr = evaluate(cfg, train_days, by_day, confidence_by_signal)
            va = evaluate(cfg, val_days, by_day, confidence_by_signal)
            train_scores.append(tr)
            val_scores.append(va)
            robust_values.append(robust_score(tr, va))
        mean_robust = statistics.mean(robust_values)
        min_val_daily = min(s.daily_avg for s in val_scores)
        mean_val_daily = statistics.mean(s.daily_avg for s in val_scores)
        mean_val_avg = statistics.mean(s.avg for s in val_scores)
        mean_val_win = statistics.mean(s.win for s in val_scores)
        scored.append({
            "config": cfg,
            "robust": mean_robust,
            "min_val_daily": min_val_daily,
            "mean_val_daily": mean_val_daily,
            "mean_val_avg": mean_val_avg,
            "mean_val_win": mean_val_win,
            "train": train_scores,
            "val": val_scores,
        })

    scored.sort(
        key=lambda x: (
            x["robust"],
            x["min_val_daily"],
            x["mean_val_daily"],
            x["mean_val_avg"],
        ),
        reverse=True,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "live_rank_tuning_results.json"
    md_path = OUT_DIR / "live_rank_tuning_report.md"
    payload = [
        {
            "rank": i + 1,
            "robust": row["robust"],
            "min_val_daily": row["min_val_daily"],
            "mean_val_daily": row["mean_val_daily"],
            "mean_val_avg": row["mean_val_avg"],
            "mean_val_win": row["mean_val_win"],
            "config": cfg_dict(row["config"]),
        }
        for i, row in enumerate(scored[: args.top])
    ]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    current = next(row for row in scored if row["config"] == current_config())
    lines: list[str] = []
    lines.append("# Live Recommend Rank Tuning")
    lines.append("")
    lines.append(f"- Source: `{args.source_dir.relative_to(ROOT)}`")
    lines.append(f"- Signals with GT: {len(rows)}")
    lines.append(f"- Trade days: {usable_days[0]} .. {usable_days[-1]} ({len(usable_days)} days)")
    lines.append(f"- Random date splits: {args.splits}, train=2/3 validate=1/3")
    lines.append(f"- Sampled configs: {len(configs)}")
    lines.append("")
    lines.append("## Current Config")
    lines.append("")
    lines.append(f"- Robust score: {current['robust']:+.3f}")
    lines.append(f"- Mean validation daily avg: {current['mean_val_daily']:+.3f}%")
    lines.append(f"- Min validation daily avg: {current['min_val_daily']:+.3f}%")
    lines.append(f"- Mean validation trade avg/win: {current['mean_val_avg']:+.3f}% / {current['mean_val_win']:.1f}%")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(cfg_dict(current_config()), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Top Robust Configs")
    lines.append("")
    lines.append("| rank | robust | min val daily | mean val daily | val avg | val win | config |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|")
    for i, row in enumerate(scored[: args.top], start=1):
        cfg = row["config"]
        lines.append(
            f"| {i} | {row['robust']:+.3f} | {row['min_val_daily']:+.3f}% | "
            f"{row['mean_val_daily']:+.3f}% | {row['mean_val_avg']:+.3f}% | "
            f"{row['mean_val_win']:.1f}% | `{json.dumps(cfg_dict(cfg), ensure_ascii=False, sort_keys=True)}` |"
        )
    lines.append("")
    best = scored[0]
    lines.append("## Best Split Details")
    lines.append("")
    for idx, (tr, va) in enumerate(zip(best["train"], best["val"]), start=1):
        lines.append(f"- Split {idx}: train {fmt_stats(tr)}; val {fmt_stats(va)}")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Loaded {len(rows)} signal outcomes across {len(usable_days)} days")
    print(f"Wrote {md_path.relative_to(ROOT)}")
    print(f"Wrote {json_path.relative_to(ROOT)}")
    print("Current:", f"robust={current['robust']:+.3f}", f"valDaily={current['mean_val_daily']:+.3f}%")
    print("Best:", f"robust={scored[0]['robust']:+.3f}", f"valDaily={scored[0]['mean_val_daily']:+.3f}%")
    print(json.dumps(cfg_dict(scored[0]["config"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
