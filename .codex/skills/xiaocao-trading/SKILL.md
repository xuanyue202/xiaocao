---
name: xiaocao-trading
description: Use when working with the local xiaocao repository to run A-share Xiaocao live morning recommendations, intraday position monitoring, market overview, market environment, stock/index quotes, block and sector data, stock pools, Xiaocao indicators, reports, strategy runs, and backtests.
metadata:
  short-description: Run Xiaocao trading and market-data workflows
---

# Xiaocao Trading

## Scope

Use this skill for Xiaocao workflows. Prefer an existing project checkout when one is available; otherwise use the bundled runtime shipped inside this skill.

Runtime selection:

1. If the current workspace or requested path contains `pyproject.toml` and `src/xiaocao/`, set `XIAOCAO_ROOT` to that repo.
2. Otherwise set `XIAOCAO_ROOT` to this skill's bundled runtime:

```text
<this skill directory>/assets/xiaocao-runtime
```

Run commands from `XIAOCAO_ROOT`. Prefer source execution:

```bash
PYTHONPATH=src python3 -m xiaocao ...
PYTHONPATH=src python3 scripts/live_recommend.py
```

The bundled runtime includes the Xiaocao CLI/package source, live scripts, docs, `stocks.json`, and `xiaocao.yaml.example`. It intentionally does not include local historical `results/`, large `output/` caches, or private `xiaocao.yaml`.

Python dependencies are declared in `pyproject.toml` (`requests`, `PyYAML`; `pytest` for e2e checks). If a command fails with a missing dependency, install from `XIAOCAO_ROOT`:

```bash
python3 -m pip install -e .
```

Use `table` for human-readable checks, `json` for follow-up analysis, and `csv` when the user wants a spreadsheet/export.

## Operating Contract & Capital Safety (read first)

`docs/OPERATING_CONTRACT.md` is the single source of truth (SSOT) for the trading口径: book A/B exit policy, the staged-exit rule, fill model, quality governor, kill-switch, and the capital-safety boundary. When a question is about *what the system should do*, follow the contract, not ad-hoc reasoning.

Architecture principle — **the deterministic spine runs without an LLM** (data, fills, stops, accounting, safety are code in `src/xiaocao/live/`); the agent is for **judgment** (posture, anomaly triage, hold exceptions) and **research**. Do not hand-compute fills, edit account balances, or decide to place a real order — the scripts do that.

Capital safety (two-key): xiaocao is paper-only. A real-capital order is structurally impossible without BOTH `XIAOCAO_LIVE_TRADING_ENABLED=true` AND a human-signed `output/live/live_authorization.json` (minted only by `scripts/authorize_live.py`). An automation can never self-authorize live trading. See `src/xiaocao/live/safety.py`.

Agent-facing tools (prefer these over re-scraping files):

- `python3 scripts/show_journal.py --date today` — what earlier runs concluded today (cross-context continuity). Read this at the start of an intraday/EOD run instead of re-deriving the day from scattered files.
- `python3 scripts/status.py` (`--json`, `--push-feishu`) — the situational-awareness digest: book A vs book B realized spread, equity/cash, today's decisions, open holdings.
- `python3 scripts/research_run.py --trades <file> --n-tried N` — judge a cache-built results file under the discipline guards (cache-only, walk-forward, per-trade-not-day-weighted, multiple-comparison significance); it refuses to call a day-weighting artifact "validated".
- `python3 scripts/data_doctor.py` — dirty-data doctor. **Run it before trusting any A/B verdict**: it catches duplicate (date,code,is_live) snapshots (the 06-01 bug that made an A/B result meaningless), book A/B account drift, and stale positions. Exits non-zero on a critical finding.
- `python3 scripts/flywheel_selfcheck.py` — are both compounding loops wired and spinning (and is the loop still actually running)?
- MCP read tools (optional): `python3 -m xiaocao.mcp.server` exposes the same read-only surface to an MCP client — `live_status`, `data_health_report`, `recent_decisions`, `ledger_verdicts`, `judge_hypothesis`, `operating_contract`, `flywheel_status` (never live trading).

## Live Trading

Use this section for morning recommendations, 9:25 candidates, intraday monitoring, sell alerts, open positions, v5/v6 tracking, or paper trading questions.

Morning recommendation:

```bash
PYTHONPATH=src python3 scripts/live_recommend.py
PYTHONPATH=src python3 scripts/live_recommend.py --date 2026-04-28
```

Output is written to:

```text
output/live/recommend_YYYY-MM-DD.md
```

Key fields:

- `entry`: today's 9:30 open price, used as the 9:25 call-auction fill reference.
- `basket`: early-session basket reference price.
- `v5 init stop`: entry x 0.98.
- `v6 init stop`: entry x 0.995.
- `open_pct`: opening percentage change.
- `flags`: direction/main-line/big-cap tags, plus Kronos K→P tags `★KP<rank>` (a top secondary pick) / `KP↓` (Kronos dropped to the bottom half) when the overlay is active.

When the Kronos K→P overlay is available, the report adds two sections:

- `## ★ Kronos K→P 优先` — variant A baseline: pure K→P picks (Kronos embedding drops the worst half, prior-day intraday model ranks survivors).
- `## ★B 实盘推荐` — the live trade set: same K→P with the **9:25 call-auction imbalance** folded in as a final tiebreak (weight 0.25; only meaningful on a live same-day run). `★` vs `★B` form an A/B pair for forward validation.

Flags to control it: `--no-kronos` disables the overlay; `--kronos-top-n N` sets the number of ★ picks (default 3). The overlay is fail-safe — if models/deps are missing it prints a skip note and the baseline recommendation is unaffected. See `## Kronos Secondary Screen & Continuous Optimization`.

Profile meanings:

- `v5`: 5 trading days, trailing stop when drawdown from post-entry peak reaches 2%.
- `v6`: 3 trading days, trailing stop when drawdown from post-entry peak reaches 0.5%.

Position records live in:

```text
output/live/positions.jsonl
```

Example position record:

```jsonl
{"code":"002347.XSHE","name":"泰尔股份","entry_date":"2026-04-28","entry_price":8.50,"profile":"v5","shares":1000,"status":"open"}
```

Intraday monitor:

```bash
PYTHONPATH=src python3 scripts/live_monitor.py
```

The monitor reads `status="open"` positions, prints entry/peak/latest/drawdown/return state, writes alerts to `output/live/alerts.jsonl`, and applies T+1 blocking on the entry date.

If the recommendation output is `候选股: NONE`, report that result directly unless the user explicitly asks to investigate.

## Automation Workflows

Use this section for Codex automations, recurring runs, scheduled monitors, or other hands-off daily Xiaocao jobs. Keep the automation prompt minimal: it should identify the workflow only. Put command choices, output inspection, anomaly policy, and response format here so the automation can be moved or recreated without duplicating business logic.

Run all commands from `XIAOCAO_ROOT`. If `.venv/bin/python` exists, prefer it for direct Python scripts; otherwise use `PYTHONPATH=src python3`.

Recommended China-market automation cadence:

- Morning recommendation + paper-buy confirmation: 09:23 on trading weekdays. This is a two-phase workflow inside one automation run: first produce the 9:25 recommendation/snapshot, then confirm paper fills after the opening execution window has settled.
- Opening dense intraday monitor: 09:35, 09:45, 09:55. Keep this denser because early realized volatility, auction follow-through, and first stop-loss signals cluster near the open.
- Sparse intraday monitor: 10:25, 10:55, 13:25, 13:55. This is enough for ordinary holding surveillance after the open; do not poll every 10 minutes all day unless explicitly requested.
- Closing-discipline intraday monitor: 14:25 and 14:55. Treat this as risk cleanup and quantitative discipline, not optimistic discretionary extension.
- EOD capture/evaluation: 15:10.

For Codex cron automations on a UTC+8 machine, store RRULE times as the equivalent UTC wall-clock values so the app displays and runs at the intended China local times.

Morning automation workflow:

```bash
bash scripts/auto_daily.sh morning
```

`auto_daily.sh morning` is intentionally a small orchestration, not just a recommendation call:

1. `scripts/live_recommend.py` waits until the 9:25 auction snapshot is usable, writes the recommendation, captures ★/★B forward signals, and records news/sentiment when available.
2. `kronos_screen/scripts/paper_record.py` confirms the paper buy after the opening execution window. Treat `basket` as the **abandon bound only, never the fill assumption**. The fill model is a realistic paper limit order: `L = min(open × (1 + 0.5%), basket_price)`; after the 9:30-9:31 window settles, fill at `min(window VWAP, L)`. If the window never trades through `L`, the pick is **skipped** and audited in `output/live/paper_skips.jsonl` (`SKIPPED / LIMIT_NOT_REACHED`). If minute data is unavailable it falls back to `L` and marks `fill_fallback`. It also records **book A** — the validated reference policy (buy at the open reference, sell at next close, no stop) — as a parallel virtual book, and applies a **kill-switch**: if book A's last 5 exit-days cum return < -3% it halves book B's deploy, < -5% it pauses book B buys entirely (book A and data capture always continue).

Use a two-stage reply for the morning automation. Keep the single orchestrated `auto_daily.sh morning` process running so the 9:35 opening-dense monitor sees confirmed positions, but as soon as the log shows `wrote .../recommend_<date>.md` or that recommendation file exists, inspect it and immediately send an interim Chinese update with today's ★B table and whether ★B differs from ★. The interim table must include `basket`, `basket_rule`, and the produced one-sentence stock sentiment/news summary; mark `paper_buy` as pending/`待模拟成交` and do not call the morning automation finished yet. Then continue waiting for `paper_record.py`; after the paper-buy phase completes, send the complete morning summary with fills, fees, account cash, posture, and anomalies.

If the recommendation output is `候选股: NONE` or no ★B result is present, report that interim state immediately and continue only if the orchestration is still doing useful paper-record/data-capture work. If the user asks for visibility while the paper phase is waiting, provide the interim recommendation from `recommend_<date>.md` rather than waiting for the final fill report.

After it finishes, inspect the current date's morning log plus the live outputs that exist:

- `output/live/auto/<date>_morning.log`
- `output/live/recommend_<date>.md`
- `output/live/signal_snapshots.jsonl`
- `output/live/positions.jsonl`
- `output/live/paper_account.json`
- `output/live/paper_trades.jsonl`

Reply in Chinese with a concise morning summary.

Present today's ★B live picks as one Markdown table, not as scattered paragraphs. In the interim 9:25 recommendation update, use the recommendation-oriented columns below and mark execution fields pending. In the final post-paper-record update, bias the table toward execution details: keep the recommendation fields compact, and make `basket`, simulated fill price, buy shares, notional, per-position weight, and fill model easy to scan.
Always use the same columns, and fill missing values with `-`:

| Column | Content |
|---|---|
| `★B` | Prefer ★B rank; if unavailable, fall back to ★/candidate rank and say so |
| `code` | Stock code |
| `name` | Stock name |
| `mode` | Recommendation mode |
| `basket` | Basket price |
| `basket_rule` | Basket rule |
| `sim_price` | Actual simulated buy price from Book B after `paper_record.py`; pending/`待模拟成交` in the interim update |
| `shares` | Simulated Book B buy shares |
| `notional` | Simulated gross buy notional |
| `position_pct` | Simulated notional as a percentage of initial capital, and include current open-position exposure in the account summary when available |
| `K/P` | Kscore and Pscore when available |
| `open_pct` | Opening percentage change |
| `auc_pct` | 9:25 auction percentage change |
| `auc_residual_imb` | 9:25 residual auction pressure |
| `basis` | Short recommendation basis: mode/score, flags, and any produced small-grass indicators |
| `sentiment/news` | Short label plus compressed news keyword; keep this cell brief |
| `paper_buy` | Fee, fill basis, fill limit, window VWAP/high/low, and fallback/skip status when positions were recorded |

Interpret `auc_residual_imb` with care: the post-match residual book is one-sided **by construction**, so this value saturates at +/-1 and is effectively only a sign (kept for the record, no longer used for selection). The ★B variant is a **forced-contrast** set: among K-survivors, if the auction-worst ★ pick (by `q = rank(残余买盘/撮合量)/2 + rank(竞价涨幅)/2`) scores below the best non-★ survivor, it is swapped out (`vb_swap=true`). Mention in the summary whether today's ★B differed from ★.

After the table, summarize simulated buys, fees, remaining cash, total open Book B exposure when available, and whether paper fills used the opening-window cap model or a fallback. The final summary should answer first: "basket vs actual simulated fill", "how many shares", "how much capital was deployed", and "what is the resulting position/cash state". Highlight only real anomalies:
script failure, missing expected output, NONE/no ★B result, missing paper-record output,
insufficient cash, or suspicious data/output behavior.

At the open, also frame the day's posture from the available broad-market and information context: market regime, rising/falling breadth, limit-up/limit-down counts, major sentiment/news summaries that were actually produced, and whether the day should be treated as optimistic, neutral, or defensive. Use this posture to explain risk appetite; do not invent news or sentiment that is not present in outputs.

Intraday monitor automation workflow:

```bash
.venv/bin/python scripts/live_monitor.py --execute-sells
```

If `.venv/bin/python` is unavailable, run:

```bash
PYTHONPATH=src python3 scripts/live_monitor.py --execute-sells
```

If the script reports a non-trading-day skip, treat it as normal and keep the reply brief. Otherwise inspect:

- `output/live/paper_account.json`
- `output/live/paper_holdings.json`
- `output/live/positions.jsonl`
- `output/live/alerts.jsonl`

Reply in Chinese with a concise cash/equity/open-position summary. Treat `T+1_blocked` as diagnostic only. Sell execution is **staged**: intraday checkpoints only execute `HARD_STOP` (drawdown ≥ 8% hard floor) or liquidity escapes; ordinary trailing-stop / composite deterioration is only **diagnosed** intraday (`defer:<reason>` in the status column, `SELL_DEFERRED` in alerts) and executed at the 14:55 discipline pass — a deferred diagnosis is normal, not an anomaly. Highlight only actual executed sells, `HARD_STOP` triggers, script failures, missing/corrupt account or position files, or other real anomalies. Book A positions (`book="A"`) are settled separately by `settle_book_a.py` and never appear in the monitor.

Opening-dense monitor runs should pay extra attention to market regime, breadth, limit-up/limit-down counts, stock sentiment, and whether the opening action confirms or rejects the morning recommendation posture. Sparse intraday monitor runs should stay quiet unless there is an actual sell signal, simulated sell, data problem, or meaningful regime/position deterioration.

Closing-discipline monitor runs should be conservative and rule-based: prioritize T+1 legality, trailing-stop/profile rules, EOD discipline, position/account consistency, and whether any strong-hold exception is truly limit-up/leader-like. Do not preserve a weak position into the close merely because the morning thesis sounded good.

When `--execute-sells` is used, simulated sell execution must honor liquidity constraints. If a triggered sell is limit-down with no bid liquidity, record/report `SELL_BLOCKED` with `LIMIT_DOWN_NO_BID`, keep the position open, and do not update cash, realized PnL, or trades as if the sell executed.

EOD automation workflow:

```bash
bash scripts/auto_daily.sh eod
```

After it finishes, inspect the current date's EOD log plus the live outputs that exist:

- `output/live/auto/<date>_eod.log`
- `output/live/eod_features.jsonl`
- `output/live/training_rows.parquet`
- `output/live/paper_account.json`
- `output/live/paper_holdings.json`
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- live monitor output from the EOD script
- `output/live/decision_journal.jsonl` (structured per-run decisions; or `python3 scripts/show_journal.py --date today`)

EOD first runs `scripts/data_doctor.py`; a CRITICAL finding (e.g. duplicate snapshots) **gates the learning half** — `forward_eval` and the capability-flywheel record are skipped so the system never learns from dirty data (the capital half still runs). It then pushes the situational-awareness digest to Feishu (`scripts/status.py --push-feishu`; needs `XIAOCAO_FEISHU_WEBHOOK`). The capability flywheel (`scripts/continuous_optimize.py`) runs a health check every eod and, **on Fridays, automatically records a dated verdict** to `kronos_screen/HYPOTHESES.jsonl` from within the same eod run — no separate scheduler is needed (`bash scripts/auto_daily.sh optimize` is only for on-demand/back-fill recording). Surface a REJECTED pipeline verdict only as evidence, not alarm: the secondary screen is a defensive overlay under forward test, expected to be marginal.

Reply in Chinese with a concise A/B battle report for take-all vs ★ vs ★B (including the **A/B contrast frequency** line — if B never differed from A the verdict is uninformative), the **book A vs book B** comparison from `settle_book_a.py` (validated next-close policy vs live stop policy), and the **PnL attribution** from `decompose_pnl.py` (`pick_alpha / entry_slippage / exit_timing` — entry_slippage should stay near zero under the VWAP fill model; flag it if it grows). Also report current cash/equity/open positions and any executed sells. Highlight only real anomalies: script failure, missing expected output, NONE/no usable result, HARD_STOP trigger, attribution reconciliation MISMATCH, or clearly unusual A/B behavior.

EOD reporting is a post-trade audit, not a fresh bullish/bearish call. Emphasize realized/simulated execution discipline, A/B evidence, data capture health, account/holding consistency, and any blocked sells or unresolved risk that must carry into the next session.

## Kronos Secondary Screen & Continuous Optimization

A Kronos-based secondary screen + forward-signal capture lives under `kronos_screen/` in the full project checkout. It re-ranks the day's primary candidates and accumulates training data over time.

Pipeline (honest framing — it is a **defensive overlay hypothesis still under forward test**, NOT a proven return engine; the first 8 clean live days showed K→P -1.02%/day vs take-all +0.58%/day, n too small to conclude):

- **K (Kronos)** — frozen Kronos-base embedding of each candidate's daily K-line → drops the worst ~50% of the day's candidates.
- **P (prior-day intraday)** — GBDT on yesterday's minute microstructure (尾盘强度 / 收盘位置 / 三段动量 / 主力净流入) → ranks the survivors; top-N are the ★ picks.
- **Auction forced-contrast (live only)** — today's 9:25 call-auction quality (`q = rank(残余买盘/撮合量)/2 + rank(竞价涨幅)/2`) may swap out the auction-worst ★ pick for the best non-★ survivor → the `★B` live trade set (`vb_swap` marks swap days; guarantees the A/B forward test has contrast).

Requirements (full checkout only; the lightweight bundled runtime omits these): `kronos_screen/model/{K_kronos,P_priorday}.joblib`, a clone of Kronos (`github.com/shiyu-coder/Kronos`; point to it with `KRONOS_REPO=/path/to/Kronos`), and Python deps `torch`, `scikit-learn`, `joblib`, `pandas`, `huggingface_hub` (Kronos-base weights auto-download on first use). Without these, `live_recommend.py` runs the baseline and prints a skip note.

Daily continuous-optimization loop:

```bash
# 1) 9:25 — morning recommendation auto-runs K→P + captures the auction snapshot
PYTHONPATH=src python3 scripts/live_recommend.py
# 2) after 15:00 — capture today's TICK order-flow (each_trade buy/sell) + minute path
PYTHONPATH=src python3 kronos_screen/scripts/eod_capture.py            # add --save-raw to keep raw ticks
# 3) after the T+1 close is available — join realized returns: A/B verdict + accumulate training rows
PYTHONPATH=src python3 kronos_screen/scripts/forward_eval.py --live-only
# 4) settle book A (validated open->next-close reference) + A-vs-B comparison
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_a.py
# 5) per-trade PnL attribution vs the validated counterfactual (reconciles to the account)
PYTHONPATH=src python3 kronos_screen/scripts/decompose_pnl.py
# 6) capability flywheel (weekly) — judge the accumulated pipeline under the discipline guards + record a verdict
PYTHONPATH=src python3 scripts/continuous_optimize.py --record
```

The capability flywheel (`scripts/continuous_optimize.py`) closes the loop: it reads `training_rows.parquet`, builds per-trade results (each pick vs that day's take-all mean), runs them through `src/xiaocao/research/guards.py` (cache-only, walk-forward train+test, **per-trade not day-weighted**, multiple-comparison significance), and appends the verdict to the `kronos_screen/HYPOTHESES.jsonl` knowledge ledger — the executable successor to STATE.md's hand-written log. It will honestly REJECT a marginal/over-fit edge; treat a REJECTED verdict as evidence the overlay is not (yet) validated, not as a failure. `ledger.already_refuted(id)` lets you skip re-running a dead direction. To judge any other hypothesis, produce a `{day, strat_ret, base_ret}` jsonl from cache and run `scripts/research_run.py`.

Accumulated artifacts:

- `output/live/signal_snapshots.jsonl` — per-candidate daily: K/P scores, ★/★B tiers + `vb_swap`, auction features (`is_live` flags real same-day captures; re-running a day replaces that day's rows — idempotent).
- `output/live/eod_features.jsonl` — per-candidate tick order-flow features (净主买 / 大单净额 / 尾盘净主买).
- `output/live/training_rows.parquet` — snapshots joined to realized next-close returns; the growing labeled set.
- `output/live/paper_account_A.json` + `book="A"` rows in `positions.jsonl` — the validated-policy virtual book (kill-switch sensor).
- `output/live/pnl_decompose.csv` — per-trade `pick_alpha / entry_slippage / exit_timing` attribution.
- `output/live/paper_skips.jsonl` — picks whose paper limit was never reached (audit, no silent drops).

Exit-layer validation tooling (run on demand, not daily): `kronos_screen/scripts/backtest_intraday_stop.py` replays stop policies (`next_close / sparse2 / sparse4 / hard8 / eod_only / atr`) on historical minute prints across the full candidate history; `kronos_screen/scripts/backtest_deploy_gate.py` tests deploy gates (all index/regime gates FAILED train+test consistency — the performance kill-switch is the only deploy control).

`forward_eval.py --live-only` reports take-all vs ★(K→P) vs ★B(K→P+auction) with a paired significance test, so the auction tiebreak and any new signal are validated forward (call-auction and ticks are latest-only on the API → not backtestable; only live captures count). Periodically retrain P and re-fit the screen on the accumulated `training_rows.parquet`, then refresh `kronos_screen/model/*.joblib`. Background and full evaluation history are in `kronos_screen/STATE.md`.

## Market Data

Use this section for broad market, index, stock, minute line, K-line, call auction, market environment, and tick-level queries.

Market overview and environment:

```bash
PYTHONPATH=src python3 -m xiaocao market overview --format json
PYTHONPATH=src python3 -m xiaocao market environment --date latest --format table
PYTHONPATH=src python3 -m xiaocao market week-stats --format json
PYTHONPATH=src python3 -m xiaocao market env-selection --date latest --format json
PYTHONPATH=src python3 -m xiaocao market env-minute --code 9A0001.XCHJZS --date latest --format json
```

Realtime quotes:

```bash
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 000001.XSHG,399001.XSHE,399006.XSHE --format table
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 300750.XSHE --format table
PYTHONPATH=src python3 -m xiaocao quote realtime --codes 000001.XSHG,399001.XSHE --raw-line --format json
```

Minute line, K-line, call auction, and trades:

```bash
PYTHONPATH=src python3 -m xiaocao quote minute --code 300750.XSHE --freq 1min --adj bfq --format json
PYTHONPATH=src python3 -m xiaocao quote minute --code 300750.XSHE --freq 1min --adj bfq --trade-date 2026-04-28 --count 241 --format json
PYTHONPATH=src python3 -m xiaocao quote history --code 300750.XSHE --count 120 --freq D --adj qfq --format table
PYTHONPATH=src python3 -m xiaocao quote history --codes 300750.XSHE,000001.XSHG --count 20 --freq D --adj qfq --format csv --output output/batch_kline.csv
PYTHONPATH=src python3 -m xiaocao quote auction --code 300750.XSHE --date latest --format json
PYTHONPATH=src python3 -m xiaocao market each-trade --code 300750.XSHE --count 20 --format table
```

Use `quote` for ordinary stock/index data. Use `market` compatibility commands only when the user asks for lower-level API behavior or endpoints not exposed by `quote`.

## Pools And Sectors

Use this section for Xiaocao pools, sorting, stock Xiaocao index, dynamic index, block rank, category rank, sector constituents, and technical indicators.

Stock pools:

```bash
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group dixi --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group jieli --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group qibao --format table
PYTHONPATH=src python3 -m xiaocao data pool --date latest --group jingwang --format table
```

Pool groups:

- `dixi`: 低吸.
- `jieli` / `lianban`: 接力.
- `qibao` / `hpqb`: 红盘起爆.
- `jingwang`: 竞王.

Sorting:

```bash
PYTHONPATH=src python3 -m xiaocao data sort --date latest --from-pool dixi --sort-key xiaocaoCJS --format table
PYTHONPATH=src python3 -m xiaocao data sort --date latest --from-pool dixi --sort-key directionCjs --sort desc --format table
PYTHONPATH=src python3 -m xiaocao catalog sort-keys --format table
```

Block and sector data:

```bash
PYTHONPATH=src python3 -m xiaocao block rank --date latest --rank-model focus --format table
PYTHONPATH=src python3 -m xiaocao block category-rank --date latest --rank-model full --format table
PYTHONPATH=src python3 -m xiaocao block score --date latest --format json
PYTHONPATH=src python3 -m xiaocao block stocks --date latest --block-code 980338.ZHBK --format json
PYTHONPATH=src python3 -m xiaocao block stocks --date latest --category-code 000031.BKDL --format json
PYTHONPATH=src python3 -m xiaocao block detail --date latest --code T08.ZHBK --format json
PYTHONPATH=src python3 -m xiaocao block kline --code T08.ZHBK --count 60 --format table
```

Use `rank-model focus` for strategy-like short-term focus and `rank-model full` for report-style broader display.

Xiaocao index and dynamic index:

```bash
PYTHONPATH=src python3 -m xiaocao index stock --date latest --codes 300750.XSHE --format json
PYTHONPATH=src python3 -m xiaocao index stock --date latest --from-pool dixi --format table
PYTHONPATH=src python3 -m xiaocao index dynamic --date latest --index-name jinglong --format table
PYTHONPATH=src python3 -m xiaocao index industry-dynamic --date latest --index-name jinglong --format table
```

Technical indicators:

```bash
PYTHONPATH=src python3 -m xiaocao indicator smallgrass current --code 300750.XSHE --format json
PYTHONPATH=src python3 -m xiaocao indicator smallgrass current --codes 300750.XSHE,000001.XSHG --format json
PYTHONPATH=src python3 -m xiaocao indicator smallgrass history --code 300750.XSHE --freq D --count 120 --format json
PYTHONPATH=src python3 -m xiaocao indicator query current --code 300750.XSHE --indicator macd --format json
PYTHONPATH=src python3 -m xiaocao indicator query history --code 300750.XSHE --indicator boll --freq D --format json
```

Backend indicator values: `smallGrass`, `vol`, `amt`, `macd`, `rsi`, `kdj`, `boll`.

## Reports And Strategy

Use this section for premarket reports, after-close reviews, daily reports, strategy runs, explanation reports, local replay, backtests, and cross-window validation.

Reports:

```bash
PYTHONPATH=src python3 -m xiaocao report premarket --date latest --source api --output reports/premarket/latest.md
PYTHONPATH=src python3 -m xiaocao report afterclose --date latest --source api --output reports/afterclose/latest.md
PYTHONPATH=src python3 -m xiaocao report afterclose --date latest --source api --format json --output output/afterclose.json
PYTHONPATH=src python3 -m xiaocao report daily --date latest --source api --output reports/latest.md
PYTHONPATH=src python3 -m xiaocao report daily --source local --date 2024-10-25 --output output/daily_2024-10-25.md
```

Strategy runs:

```bash
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --source api --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --source api --profile validated_v5 --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --modes dixi --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --modes direction --direction-sort-key directionCjs --max-per-direction 5 --format table
PYTHONPATH=src python3 -m xiaocao strategy run --date latest --explain --format markdown
PYTHONPATH=src python3 -m xiaocao strategy run --source local --date 2024-10-25 --format table
```

Use local-source commands only when `XIAOCAO_ROOT/results/` contains the relevant `YYYY-MM-DD_detail.csv` files. The bundled runtime is API-first and does not ship historical local CSV data.

Backtests:

```bash
PYTHONPATH=src python3 -m xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --profile validated_v5 --workers 6
PYTHONPATH=src python3 -m xiaocao backtest run --start 2026-03-01 --end 2026-04-24 --exclude-modes 接力低弱转2 --output output/xiaocao_backtest_no_jslrz2
PYTHONPATH=src python3 -m xiaocao backtest validate --windows 2026-03-01:2026-03-31,2026-04-01:2026-04-24 --variant '--profile validated_v5' --workers 4
```

Backtest outputs include daily `signals_YYYY-MM-DD.json`, `trades.csv`, and `summary.json`.

## Utilities

Calendar and config:

```bash
PYTHONPATH=src python3 -m xiaocao calendar latest --date today
PYTHONPATH=src python3 -m xiaocao calendar trade-days --start 2026-04-01 --end 2026-04-30 --format json
PYTHONPATH=src python3 -m xiaocao calendar next --date 2026-04-24
PYTHONPATH=src python3 -m xiaocao config show --format json
```

Catalog:

```bash
PYTHONPATH=src python3 -m xiaocao catalog list --format table
PYTHONPATH=src python3 -m xiaocao catalog groups --format table
PYTHONPATH=src python3 -m xiaocao catalog rank-models --format table
PYTHONPATH=src python3 -m xiaocao catalog freqs --format table
PYTHONPATH=src python3 -m xiaocao catalog adjs --format table
PYTHONPATH=src python3 -m xiaocao catalog indicators --format table
```

Live API health check:

```bash
PYTHONPATH=src python3 -m pytest tests/e2e -q
```

## Response Style

Report the command outcome, the relevant file paths, and the key rows or counts. When the user asks for data, summarize the returned facts and mention the actual query date used.
