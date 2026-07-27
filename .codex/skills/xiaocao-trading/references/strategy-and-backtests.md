# Recommendations, reports, strategies and backtests

Read this file only for direct recommendations, reports, strategy runs, cohorts, paper-vs-market analysis or backtests.

## Direct live recommendation

```bash
PYTHONPATH=src python3 scripts/live_recommend.py
PYTHONPATH=src python3 scripts/live_recommend.py --date 2026-04-28
```

Output: `output/live/recommend_YYYY-MM-DD.md`.

Key report fields: `entry` (9:30 open reference), `basket` (abandon bound), v5/v6 initial stop, `open_pct`, flags, K/P overlays and ★E executable mode evidence. For any fill/allocation interpretation, read `docs/OPERATING_CONTRACT.md` instead of inferring from the report.

The frozen 9:25 same-day signal set remains the reference signal after close. If output says `候选股: NONE`, report it directly unless investigation was requested.

## Reports

```bash
PYTHONPATH=src python3 -m xiaocao report premarket --date latest --source api --output reports/premarket/latest.md
PYTHONPATH=src python3 -m xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md
PYTHONPATH=src python3 -m xiaocao report afterclose --date latest --source api --format json --output output/afterclose.json
PYTHONPATH=src python3 -m xiaocao report daily --date latest --source api --output reports/latest.md
PYTHONPATH=src python3 -m xiaocao report daily --source local --date 2024-10-25 --output output/daily_2024-10-25.md
```

## Strategy runs

```bash
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --source api --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --source api --profile validated_v5 --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --modes dixi --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --modes direction --direction-sort-key directionCjs --max-per-direction 5 --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --explain --format markdown
PYTHONPATH=src python3 -m xiaocao strategy run --source local --date 2024-10-25 --format table
```

Use local source only when `results/YYYY-MM-DD_detail.csv` exists. The bundled runtime is API-first and carries no historical result set.

## Backtests and validation

```bash
PYTHONPATH=src python3 -m xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --profile validated_v5 --workers 6
PYTHONPATH=src python3 -m xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --exclude-modes 接力低弱转2 --output output/xiaocao_backtest_no_jslrz2
PYTHONPATH=src python3 -m xiaocao backtest validate --windows 2026-03-01:2026-03-31,2026-04-01:2026-04-24 --variant '--profile validated_v5' --workers 4
```

Backtest outputs include daily signal JSON, `trades.csv` and `summary.json`. A backtest result is not live authority; promotion still follows the research protocol and human gate.

## Paper strategy versus A-share indices

```bash
PYTHONPATH=src python3 scripts/research_paper_vs_market.py \
  --start 2026-06-01 \
  --output output/research/paper_vs_market_2026-06-01_latest.md
```

Compare Book B with 上证, 深成指, 创业板指 and 中证1000. Aggregated index/spread is valid only at coverage `4/4`.

## Cohorts and qibao execution research

`scripts/cohort_snapshot.py --date <date>` writes authority-0 benchmark/watchlist samples to `output/cohorts/cohort_snapshots.jsonl`. They are not buy inputs.

For fill-aware qibao research:

1. `scripts/backfill_qibao_cohort_minutes.py` caches only missing code-days at a low request rate.
2. `scripts/research_qibao_cohort_execution.py` writes `output/research/qibao_cohort_execution_*.jsonl`.
3. `scripts/research_run.py` applies cache-only train/test guards.

The benchmark base must be the full same-day qibao pool return, never a partially backfilled minute subset. Scale daily open into the minute price axis before testing the `open*1.005` touch. Even PASS remains authority 0 until the human gate.

Current human-gated paper-only promotions are raw-qibao top10 electronic/20cm `high_open_watch` at 6%–10% as `高开标杆起爆`, and `limitlike_watch` as `强攻标杆起爆`. They do not authorize real capital.

## Trend participation counterfactual

```bash
PYTHONPATH=src python3 scripts/research_trend_leader_basket.py \
  --entry-date 2026-06-01 \
  --checkpoints 2026-06-08,2026-06-19 \
  --output output/research/trend_leader_basket_2026-06-01.md
```

This path is cache-first and uses minute `trade`. Add `--allow-api` only for rate-limited missing bars.
