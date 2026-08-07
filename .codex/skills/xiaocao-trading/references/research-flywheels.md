# Kronos research and flywheels

Read this file only for K/P overlays, forward labels, training rows, guarded research, verdicts or flywheel state interpretation.

## Authority boundary

`docs/OPERATING_CONTRACT.md` owns executable ★E/mode, fill, allocation and Book-T semantics. This file describes research instrumentation only. A candidate, shadow variant or PASS never edits accounts/safety and never self-promotes to real capital.

## Variant map

- A `kp_star`: Kronos K survivors ranked by prior-day intraday P.
- B `vb_star`: K/P plus forced auction contrast; retained A/B set, not the default Book-B actuator.
- C `mode_star`: legacy mode-score rotation shadow.
- D `qibao_benchmark_star`: independent qibao benchmark.
- E `ai_intelligence_short_star`: structured intelligence shadow.
- F / ★E `mode_exec_star`: executable mode state using `executable_net_ret`.

`forward_eval.py --live-only` reports all six. Contrast frequency matters: B is uninformative when it rarely differs from A. Small-n E/F remains small-n.

## Daily research loop

```bash
PYTHONPATH=src python3 scripts/live_recommend.py
PYTHONPATH=src python3 kronos_screen/scripts/eod_capture.py
PYTHONPATH=src python3 kronos_screen/scripts/forward_eval.py --live-only
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_a.py
PYTHONPATH=src python3 scripts/live_monitor.py --book T --execute-sells
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_t.py
PYTHONPATH=src python3 kronos_screen/scripts/decompose_pnl.py
```

Use `continuous_optimize.py --record` and `trend_optimize.py --record` only in Friday/explicit optimize paths. Ordinary investigation is read-only.

Kronos requires the model artifacts under `kronos_screen/model`, a compatible Kronos checkout (`KRONOS_REPO`) and its Python dependencies. Missing models/deps must degrade to baseline recommendation, not break it.

## Guarded verdicts

`continuous_optimize.py` builds per-trade variant-versus-same-day-base results and applies cache-only, walk-forward train/test, per-trade equal weighting and multiple-comparison significance guards. Strategy-consumption verdicts for `mode_star` use only non-BJSE, opening-window-fillable `executable_net_ret`; theoretical `net_realized_ret` remains shadow evidence and cannot authorize Book-B promotion. `--export-variant ... --export-trades ...` writes the exact guard rows for a protocol-bound `research_run.py` manifest. REJECTED is evidence, not a pipeline error. Re-evaluation records only changed verdicts.

For another hypothesis, create `{day,strat_ret,base_ret}` JSONL and run:

```bash
PYTHONPATH=src python3 scripts/research_run.py --trades <file> --n-tried N
```

Book T uses `trend_optimize.py`/`trend_guards`, with compounded return, drawdown, turnover, walk-forward retention, per-hold significance and non-bull survival. It does not enter short-line `training_rows` or `continuous_optimize`.

## Flywheel state

`scripts/flywheel_selfcheck.py` reports:

- ① capital and ② capability should be spinning/wired; failure is a data/wiring anomaly.
- ③ `open`: normal, no unconsumed PASS.
- ③ `blocked`: PASS exists without consumption; route through weekly evidence mapping or a human proposal.
- ③ `closed`: future audited actuator state.

`rings.fully_closed=False` is normal while the strategy actuator is a human gate. A `heavier` knowledge scoreboard is backlog state: report its ratios and top cache-expressible queue items, not a trading failure.

Calibration is sensor-only. Exit/posture candidates staged by `--distill` have zero authority until operationalized, guarded and human-gated. Surface an exit rule only after its stated min-n floor.

## Canonical artifacts

- `output/live/signal_snapshots.jsonl`: book-scoped K/P, ★/★B/★M/★E, auction, qibao and mode evidence.
- `output/live/eod_features.jsonl`: TICK/order-flow features.
- `output/live/training_rows.parquet`: theoretical labels plus executable opening-window labels; Book T excluded.
- `kronos_screen/HYPOTHESES.jsonl`: verdict ledger.
- `reference/experience/xiaocao_hypotheses.jsonl`: candidate backlog, not verdict authority.
- `output/live/pnl_decompose.csv`: pick alpha, entry slippage and exit timing.
- `output/live/exit_calibration.jsonl` and `posture_calibration.jsonl`: sensor outputs.
- `output/research/runs/*/manifest.json`: protocol-bound research manifests.

On-demand exit tooling: `kronos_screen/scripts/backtest_intraday_stop.py` and `backtest_deploy_gate.py`. Historical findings are not live permissions; consult the current verdict ledger and contract.
