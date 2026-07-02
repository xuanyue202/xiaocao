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

The bundled runtime includes the Xiaocao CLI/package source, live scripts, docs,
`reference/experience` knowledge artifacts, `stocks.json`, and `xiaocao.yaml.example`.
It intentionally does not include local historical `results/`, large `output/` caches, or
private `xiaocao.yaml`.

Python dependencies are declared in `pyproject.toml` (`requests`, `PyYAML`; `pytest` for e2e checks). If a command fails with a missing dependency, install from `XIAOCAO_ROOT`:

```bash
python3 -m pip install -e .
```

Use `table` for human-readable checks, `json` for follow-up analysis, and `csv` when the user wants a spreadsheet/export.

## Operating Contract & Capital Safety (read first)

`docs/OPERATING_CONTRACT.md` is the single source of truth (SSOT) for the trading口径: book A/B/T exit policy, the staged-exit rule, fill model, quality governor, kill-switch, trend-book separation, and the capital-safety boundary. When a question is about *what the system should do*, follow the contract, not ad-hoc reasoning.

Architecture principle — **the deterministic spine runs without an LLM** (data, fills, stops, accounting, safety are code in `src/xiaocao/live/`); the agent is for **judgment** (posture, anomaly triage, hold exceptions) and **research**. Do not hand-compute fills, edit account balances, or decide to place a real order — the scripts do that.

Capital safety (two-key): xiaocao is paper-only. A real-capital order is structurally impossible without BOTH `XIAOCAO_LIVE_TRADING_ENABLED=true` AND a human-signed `output/live/live_authorization.json` (minted only by `scripts/authorize_live.py`). An automation can never self-authorize live trading. See `src/xiaocao/live/safety.py`.

Agent-facing tools (prefer these over re-scraping files):

- `python3 scripts/show_journal.py --date today` — what earlier runs concluded today (cross-context continuity). Read this at the start of an intraday/EOD run instead of re-deriving the day from scattered files.
- `python3 scripts/status.py` (`--json`, `--push-wecom`) — the situational-awareness digest: book A vs book B realized spread, Book T trend account, equity/cash, today's decisions, open holdings; `--push-wecom` posts through the OpenClaw WeCom relay when `XIAOCAO_WECOM_*` is configured.
- `python3 scripts/research_run.py --trades <file> --n-tried N` — judge a cache-built results file under the discipline guards (cache-only, walk-forward, per-trade-not-day-weighted, multiple-comparison significance); it refuses to call a day-weighting artifact "validated".
- `python3 scripts/data_doctor.py` — dirty-data doctor. **Run it before trusting any A/B verdict**: it catches duplicate (date,code,is_live,book) snapshots (the 06-01 bug that made an A/B result meaningless), book A/B/T account drift, and stale positions. Exits non-zero on a critical finding.
- `python3 scripts/flywheel_selfcheck.py` — are the three coupled flywheels healthy? ① capital + ② capability auto-turn (spinning); ③ strategy is an intentional human gate, reported open/blocked/closed (🔴 only if a PASS verdict is pending with no actuator). Also flags a stalled loop.
- MCP read tools (optional): `python3 -m xiaocao.mcp.server` exposes the same read-only surface to an MCP client — `live_status`, `data_health_report`, `recent_decisions`, `ledger_verdicts`, `judge_hypothesis`, `operating_contract`, `flywheel_status` (never live trading).

## Xiaocao Judgment Playbook (posture & exit priors)

Use this section when an automation (morning / intraday / eod) needs the **discretionary judgment priors** distilled from the 小草大师班 live commentary — never for a deterministic action. These priors live in human-readable artifacts and are **agent context only**:

- `docs/XIAOCAO_PLAYBOOK.md` — the 道-法-术-纪律 playbook + a **「实时盘面判断模型」** table (观察→推断→底层逻辑→动作, across 盘前/集合竞价/9:31-9:35/盘中). Every line is tagged `[已编码]` (the spine already implements it), `[先验]` (agent judgment only), or `[待验]` (a hypothesis that must clear the flywheel). Distilled from `reference/experience/distilled/*_{morning,review}.json`.
- `reference/experience/REGIME_TIMELINE.md` — the dated **posture timeline**: one row per session with `regime` / `dominant_style` / risk stance / leaders / `valid_until` / `证伪条件`. The **现行 posture** section at the bottom is the current macro prior.
- `reference/experience/xiaocao_hypotheses.jsonl` — the **candidate** hypothesis backlog (see flywheel hookup below). Candidates are NOT verdicts.

How each agent consults them:

- **Morning agent** — read the **现行 posture** of `REGIME_TIMELINE.md` (regime / risk / `证伪条件`) as today's macro prior, plus the 术/纪律 of `XIAOCAO_PLAYBOOK.md`, to frame the day's narrative (optimistic / neutral / defensive; which 方向 lead vs lag; whether the deterministic `★B` picks sit *with* or *against* the posture). It is a **lens for the Chinese summary**, never a filter on the picks. If the latest timeline row is several sessions stale, say "no current posture prior" and proceed on live data only.
- **EOD agent** — use the 纪律 (出场) section of `XIAOCAO_PLAYBOOK.md` for **anomaly triage only**: when a position was held through a deferred trailing/composite signal or a strong-hold exception, judge whether that looks like a *defensible discretionary exception* or a *discipline gap worth flagging*. One line of triage in the A/B report — it changes no fill, stop, or account row. The **exit-calibration sensor** (`output/live/exit_calibration.jsonl`, refreshed every eod, see the EOD workflow below) is the falsifiable companion to this triage: once an exit rule clears the min-n floor it shows, on realized forward paths, whether holding-through / selling actually *paid* — so the triage line can cite data instead of vibe. Still a prior, never an auto action.

**红线 (MUST NOT)** — consistent with `docs/OPERATING_CONTRACT.md` §2 (LLM 不进确定性回路):

- MUST NOT enter the deterministic spine (data / fill / stop / book A·B accounting / safety). No script reads these files.
- MUST NOT auto-tune any param / threshold / profile / model from a playbook claim. `src/xiaocao/strategy/params.py` stays frozen-guarded; the only edit path is the §10 human gate.
- MUST NOT be cited as evidence a strategy is "validated". A live-commentary claim is a **prior/hypothesis**, not a verified edge.

**Hypotheses go through the flywheel, not the playbook.** Every falsifiable claim is harvested into `reference/experience/xiaocao_hypotheses.jsonl` as a **candidate** (`status:"candidate"`). It only becomes a usable edge by passing the capability flywheel (`scripts/research_run.py` discipline guards → `kronos_screen/HYPOTHESES.jsonl` verdict ledger). In the current rapid-exploration phase, a PASS with complete mapping / attribution / overfit / rollback evidence may be applied to paper/simulation/research/tooling by weekly deep review; real-capital, account history, safety logic, and core deterministic truth sources still require the explicit human gate. An un-operationalized candidate carries **zero** authority over the spine.

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

Signal stability: for a same-day live run, the Xiaocao signal set produced after the
09:25 call-auction snapshot is the day's fixed morning signal. Use it as trusted evidence
for later review/audit; do not reclassify it as unstable just because the review happens
after the close. Intraday prices and fills can change, but the 09:25 emitted/recommended
set is the reference signal set.

Intermediate cohorts: `scripts/cohort_snapshot.py --date <date>` captures benchmark/watchlist
research cohorts such as raw-qibao high-open or limit-like strong-attack samples into
`output/cohorts/cohort_snapshots.jsonl`. These rows have `authority=0`: use them for
review, watchlists, and `research_run.py` artifacts, not as automatic paper-buy inputs.
When reviewing whether those watchlist samples are actually tradable, use the fill-aware
research path: `scripts/backfill_qibao_cohort_minutes.py` to cache only missing cohort
minute-line code-days at a low request rate, then `scripts/research_qibao_cohort_execution.py`
to generate `output/research/qibao_cohort_execution_*.jsonl`, then judge with
`scripts/research_run.py`. The benchmark base must remain the full same-day qibao pool daily
return; a partially backfilled minute subset is not a valid base. The script scales daily open
into the minute bar price axis before applying the `open*1.005` limit; do not anchor the touch
test on the first cached minute. Even a PASS here remains
authority=0 until the §10 human gate promotes it.

Current human-gated paper-only promotions (2026-06-30): raw-qibao top10 +
electronic/20cm `high_open_watch` **only for open 6%-10%** is emitted as
`高开标杆起爆`, and `limitlike_watch` is emitted as `强攻标杆起爆`. These are
Book-B/paper simulation rules only; they do not authorize real capital and must
keep `qibaoRankScore` as the primary score. Generic high-open signals outside
these promoted qibao benchmark modes remain shadowed by the normal
`openPctChange >= 6` guard.

When the user asks whether the live short-line strategy is effective, compare
Book B against A-share benchmarks with:

```bash
PYTHONPATH=src python3 scripts/research_paper_vs_market.py --start 2026-06-01 --output output/research/paper_vs_market_2026-06-01_latest.md
```

Use 上证 as a broad large-cap reference, but also compare 深成指 / 创业板指 /
中证1000 because the current book trades small/mid growth and 20cm names.
The EOD automation now writes the same comparison daily to
`output/research/paper_vs_market_<start>_<date>.md` (default start
`2026-06-01`; override with `PAPER_VS_MARKET_START`).

When the user asks for a fast stage on trend/Book-T participation, start with the
concrete leader-basket counterfactual before wider trend-book research:

```bash
PYTHONPATH=src python3 scripts/research_trend_leader_basket.py --entry-date 2026-06-01 --checkpoints 2026-06-08,2026-06-19 --output output/research/trend_leader_basket_2026-06-01.md
```

This script is cache-first and uses `/stock/minute_line` `trade` as the price
axis; default entry is entry-day close. Use `--allow-api` only to fill missing
minute bars, rate-limited.

Mode recent confidence / mode rotation is sourced from **live all-hit forward
labels** first: `output/live/training_rows.parquet`, produced by
`signal_snapshots.jsonl -> forward_eval.py --live-only`, contains every live
morning hit including bought, unbought, KP-dropped, and shadow rows. `live_recommend.py`
must rank modes by those recent 5/10/20-day `net_realized_ret` windows before
falling back to SQLite `mode_history`. If every mode confidence is 50, treat it
as a wiring/data issue: check that EOD `forward_eval` has refreshed
`training_rows.parquet`, that `capture_signals.py` is recording
`mode_confidence_source/reason`, and only then fall back to stale
`mode_history`.

For qibao benchmark work, `capture_signals.py` must preserve `rawQibaoRank`,
`qibaoRankScore`, `qibaoBenchmarkKind`, and `qibaoBenchmarkLayer` into
`signal_snapshots.jsonl`; `forward_eval.py` materializes
`qibao_benchmark_star` and reports it as variant D. If qibao benchmark winners
look absent from `training_rows.parquet`, treat that as a data wiring break first,
not as a strategy conclusion.

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

Book T trend paper book:

```bash
PYTHONPATH=src python3 kronos_screen/scripts/paper_record.py --date YYYY-MM-DD --trend-only
PYTHONPATH=src python3 scripts/live_monitor.py --book T --execute-sells
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_t.py
```

Book T writes `book:"T"` rows to the same `output/live/positions.jsonl`, uses
`output/live/paper_account_T.json`, and keeps `output/live/paper_holdings_T.json`.
It is paper-only and independent from Book B: same-code B/T overlap is allowed,
T exits use `TREND_TRAIL_DD` / `TREND_REBALANCE_R`, and T must not consume Book-B
strong-hold/composite logic. Trend evaluation stays out of
`continuous_optimize.py`; use `trend_guards` / `trend_optimize` for compounded
return, drawdown, turnover, and beta comparison.
Run `PYTHONPATH=src python3 scripts/trend_optimize.py` for the trend health
check, and add `--record` only from the weekly/explicit optimize path.

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
2. `kronos_screen/scripts/paper_record.py` confirms the Book-B paper buy after the opening execution window. Treat `basket` as the **abandon bound only, never the fill assumption**. The fill model is a realistic paper limit order: `L = min(open × (1 + 0.5%), basket_price)`; after the 9:30-9:31 window settles, if the window trades through `L`, fill at `min(window VWAP, L)`. If the initial low limit is not filled or would be rejected as too far from the tape, check the latest opening-window price as the real-time retry proxy; when that price is still `<= basket_price`, fill at that real-time price and audit `retry_realtime_after_limit_reject`. If the retry price is above `basket` or unavailable, the pick is **skipped** and audited in `output/live/paper_skips.jsonl` (`SKIPPED / LIMIT_NOT_REACHED`). If minute data is unavailable it falls back to `L` and marks `fill_fallback`. It also records **book A** — the validated reference policy (same final entry fill as Book B, sell at next close, no stop) — as a parallel virtual book, and applies a **kill-switch**: if book A's last 5 exit-days cum return < -3% it halves book B's deploy, < -5% it pauses Book-B buys entirely (book A and data capture always continue).
3. The morning orchestration then runs `paper_record.py --trend-only` for Book T. This records only new trend slots into `paper_account_T.json`; no Book-T candidate, an already-full T book, or a skipped T fill is normal paper state and not a Book-B anomaly.

Use a two-stage reply for the morning automation. Keep the single orchestrated `auto_daily.sh morning` process running so the 9:35 opening-dense monitor sees confirmed positions, but as soon as the log shows `wrote .../recommend_<date>.md` or that recommendation file exists, inspect it and immediately send an interim Chinese update with today's ★B table and whether ★B differs from ★. The interim table must include `basket`, `basket_rule`, and the produced one-sentence stock sentiment/news summary; mark `paper_buy` as pending/`待模拟成交` and do not call the morning automation finished yet. Then continue waiting for `paper_record.py`; after the paper-buy phase completes, send the complete morning summary with fills, fees, account cash, posture, and anomalies.

If the recommendation output is `候选股: NONE` or no ★B result is present, report that interim state immediately and continue only if the orchestration is still doing useful paper-record/data-capture work. If the user asks for visibility while the paper phase is waiting, provide the interim recommendation from `recommend_<date>.md` rather than waiting for the final fill report.

After it finishes, inspect the current date's morning log plus the live outputs that exist:

- `output/live/auto/<date>_morning.log`
- `output/live/recommend_<date>.md`
- `output/live/signal_snapshots.jsonl`
- `output/live/positions.jsonl`
- `output/live/paper_account.json`
- `output/live/paper_account_T.json`
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
| `paper_buy` | Fee, fill basis, fill limit, window VWAP/high/low/last, retry/fallback/skip status when positions were recorded |

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
Book T positions are monitored only by `scripts/live_monitor.py --book T`; they use wide trend exits and should not be mixed into the default Book-B monitor summary.

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
- `output/live/paper_account_T.json`
- `output/live/paper_holdings.json`
- `output/live/paper_holdings_T.json`
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- live monitor output from the EOD script
- Book T monitor / `settle_book_t.py` output when present
- `output/live/decision_journal.jsonl` (structured per-run decisions; or `python3 scripts/show_journal.py --date today`)
- `output/research/paper_vs_market_<start>_<date>.md` (Book B vs 上证/深成指/创业板指/中证1000)

EOD first runs `scripts/data_doctor.py`; a CRITICAL finding (e.g. duplicate snapshots) **gates the learning half** — `forward_eval` and the capability-flywheel record are skipped so the system never learns from dirty data (the capital half still runs). The EOD capital half monitors Book B, monitors Book T with `scripts/live_monitor.py --book T --execute-sells`, settles Book A, then settles Book T with `settle_book_t.py`. It then pushes the situational-awareness digest to WeCom via OpenClaw relay (`scripts/status.py --push-wecom`; needs `XIAOCAO_WECOM_RELAY_URL`, `XIAOCAO_WECOM_RELAY_TOKEN`, `XIAOCAO_WECOM_USER_ID`; optional `XIAOCAO_WECOM_ACCOUNT_ID=default`, `XIAOCAO_WECOM_INSECURE=true`). For Codex cron, put these vars in local untracked `output/live/notify.env` (or point `XIAOCAO_NOTIFY_ENV_FILE` elsewhere) so fresh automation contexts inherit the relay config without editing each automation. The capability flywheels run health checks every eod: `continuous_optimize.py` for short-line A/B/C/D and `trend_optimize.py` for Book T's compounded/dd/turnover instrument. On Fridays both automatically record changed verdicts to `kronos_screen/HYPOTHESES.jsonl`; `bash scripts/auto_daily.sh optimize` is the on-demand/back-fill recording path. Surface a REJECTED pipeline verdict only as evidence, not alarm: the secondary screen and Book T trend edge are forward/research evidence until §10 says otherwise.

EOD also runs `scripts/research_paper_vs_market.py` and writes the dated report
under `output/research/`. Include a one-line "Book B vs index avg" result in the
Chinese EOD reply; this is the daily sanity check that the simulated strategy is
at least beating a passive A-share reference over the same window.

EOD then runs `scripts/flywheel_selfcheck.py --notify-blocked` — the three-flywheel health check. **Read its `③ strategy flywheel` status and act per the runbook below.** ① capital and ② capability auto-turning is the normal steady state; the only line that needs a decision is ③.

EOD also runs `scripts/exit_calibration.py --ingest --score --distill` (and `posture_calibration.py --score --distill`) — the **calibration loops** for the 卖出逻辑 and the posture layer. The exit sensor reads today's Book-B exit DECISIONS from `alerts.jsonl`, collapses each position-day to its net realized stance (`sell` = `SELL_TRIGGERED`; `hold` = a strong-hold-suppressed or deferred-and-not-sold position — the staged-exit defer→14:55-execute path counts once, as the sell), and scores any decision whose H-day forward window has closed against the position's realized forward path (split-safe `date_kline` returns, lookahead-safe by construction). It is **sensor-only** — it never changes a fill, stop, account row, or `exit_policy.py` param; it has zero authority over the deterministic spine. In the report, surface its **by-exit-rule hit-rate** only when a rule clears the min-n floor (it tags `n<5` results as not-yet-meaningful): a rule reading **<45% over n≥8–10** is a *distillation target*. A `hold` rule that calibrates well means we correctly held through a dip; a `sell` rule reading low means that exit tends to cut bounces (the position-level analog of 小草's "别对回调空仓"). Early on it scores few decisions (the daily cache lags the live decisions and many low-suck small-caps aren't cached); a thin coverage count is the honest state, not an anomaly.

The **`--distill`** step closes the loop into the flywheel: a flagged rule is staged as a falsifiable CANDIDATE in `output/live/calibration_candidates.jsonl` (runtime, gitignored) — it does NOT auto-edit the tracked candidate backlog or the spine. `flywheel_selfcheck.py` now reports these loops as the **②b calibration leg** (posture/exit scored + recorded counts, distill wired, candidates staged), so a silently-broken sensor surfaces as a `CALIBRATION` warning instead of rotting unnoticed. A staged candidate is human-gate work: promote it into `reference/experience/xiaocao_hypotheses.jsonl`, validate via `research_exit_priors.py` / `research_run.py`, then §10 — **never** an auto-tune. If `candidates staged > 0`, surface it as a to-do for the human, not an anomaly.

EOD also runs `scripts/flywheel_sweep.py` — the candidate-backlog **CONSUMER** (the thing that keeps ② getting *smarter*, not just *heavier*). It first **reconciles** the research verdict ledger back into `reference/experience/xiaocao_hypotheses.jsonl`: a REJECTED candidate is **retired** (structured `retired_on` + `last_verdict`, so it stops reappearing as live work) and a PASS is tagged as §10 evidence. Sweep itself does not edit strategy; the weekly deep review consumes PASS evidence only when the fixed input bundle contains a concrete paper/simulation mapping, attribution, overfit check, validation, and rollback. It then prints the **test-priority queue**: untested candidates ranked by recurrence↓ (how many distinct transcripts repeat the claim = `len(source_dates)`) then age↑, flagged cache-expressible. `flywheel_selfcheck.py` prints a **knowledge scoreboard** — `transcripts / candidate→tested / tested→PASS / retired / median recurrence / oldest-untested` plus a 🟢 smarter / 🟡 heavier gauge. In the report: if the scoreboard reads 🟡 **heavier** or a `KNOWLEDGE` warning fires (grading falling behind ingest, or a stale oldest-untested tail), surface the **top 1–3 cache-expressible candidates from the sweep queue** as the §10 research to-do — the human picks one, confirms its operationalization, runs `research_run.py` / `research_exit_priors.py` under the train+test guard. Retirements, scoreboard ratios, and the queue are **informational** (the standing 判断层 backlog state), not anomalies — surface them as a one-line "知识飞轮" status + the to-do when grading is behind, not an alarm.

Reply in Chinese with a concise A/B/C/D battle report for take-all vs ★ vs ★B vs ★M vs qibao-benchmark (including the **A/B contrast frequency** line — if B never differed from A the verdict is uninformative), the **book A vs book B** comparison from `settle_book_a.py` (validated next-close policy vs live stop policy), the **Book B vs index avg** line from `paper_vs_market`, the **Book T trend paper account** line when present (cash/equity/open, executed trend exits, no short-line verdict), and the **PnL attribution** from `decompose_pnl.py` (`pick_alpha / entry_slippage / exit_timing` — entry_slippage should stay near zero under the VWAP fill model; flag it if it grows). Also report current cash/equity/open positions and any executed sells, separating Book B and Book T. Include the **exit-calibration** line only when an exit rule cleared the min-n floor (a `<45%` rule is a distillation flag for the human gate, not an anomaly; a tagged small-n or thin-coverage result is informational and need not be surfaced). Add a one-line **知识飞轮** status from the knowledge scoreboard (e.g. `候选 30 / 已测 30% / 已退役 5 / 最老未测 21d`) and, **only when** it reads 🟡 heavier or a `KNOWLEDGE` warning fired, the §10 to-do naming the top 1–3 cache-expressible candidates from the sweep queue. Highlight only real anomalies: script failure, missing expected output, NONE/no usable result, HARD_STOP trigger, attribution reconciliation MISMATCH, Book T account/holding drift, or clearly unusual A/B behavior.

EOD reporting is a post-trade audit, not a fresh bullish/bearish call. Emphasize realized/simulated execution discipline, A/B evidence, data capture health, account/holding consistency, and any blocked sells or unresolved risk that must carry into the next session.

Weekly deep review automation workflow:

```bash
bash scripts/auto_daily.sh weekly
```

This is a Friday-evening **flywheel consumer / auto-iteration** workflow, not a trading
workflow. It still runs on non-trading Fridays and reviews the most recent trading week.
`auto_daily.sh weekly` records short-line + Book-T verdicts, reconciles/ranks the backlog,
refreshes `reference/experience/distill_action_log.jsonl`, and writes:

```text
output/live/weekly_plan_YYYY-MM-DD.json
```

After the plan exists, the Codex agent must inspect it and then act by evidence level:

- `AUTO_APPLIED`: allowed for paper/simulation/research/tooling strategy changes **only**
  when the plan contains a complete `evidence_bundle` from the fixed input list
  (`flywheel_selfcheck`, `flywheel_sweep --json`, `distill_action_log`, verdict ledger,
  research outputs, PnL attribution, paper-vs-market, posture/exit calibration, git status).
  Implement the change, update tests/docs as needed, and run validation before finalizing.
- Read-only instrumentation / projection / report-quality gaps from `distill_action_log`
  should be treated as `AUTO_APPLIED` candidates by default: implement them directly when
  they do not alter strategy behavior, params, fills, accounts, or capital safety. Do not
  ask the user for confirmation just to add observability. The expected downsides are only
  maintenance cost / report noise; keep them contained with focused tests and compact output.
- `PROPOSAL_ONLY`: required for anything outside the fixed input list, any weak/unclear
  evidence, any dirty-file target, or any strategy mapping that is not concrete enough to
  implement. The weekly report must surface the proposal in the first screen and create a
  `.scratch/weekly-deep-review/<date>/...md` issue. Do not silently bury it in the backlog.
- `NO_ACTION_REQUIRED`: only when the plan has no auto-apply candidate and no proposal.

Dirty-file boundary: record the pre-run `git status --porcelain`; do not auto-edit a file
that was already dirty before the weekly run. If evidence points to such a file, write
`NEEDS_HUMAN_CONFIRMATION` in the report/proposal and stop at a recommendation.

Weekly report readability is part of the contract. The first screen must be Chinese and
decision-oriented, not an internal state dump. It must answer, in this order:

1. 这批转录/证据具体给了什么启发（尤其是 posture、playbook、hypothesis、audit）。
2. 已经改进或沉淀到了哪里（例如 posture_current、XIAOCAO_PLAYBOOK、候选假设、命中审计、工具提案）。
3. 需要用户看/确认什么，以及为什么不能自动落地。

Do not use raw headings such as `Human Attention`, `NEEDS_CONFIRMATION`, or
`BLOCKED_BY_DIRTY_FILE` in the human-facing first screen. A pre-existing dirty file list is
only a local-worktree reminder, not a strategy decision; summarize the count and a few sample
paths in Chinese, and keep the full machine details in the audit section.

Finalize with the weekly harness after implementation/proposal routing:

```bash
PYTHONPATH=src python3 scripts/weekly_deep_review.py \
  --finalize output/live/weekly_plan_YYYY-MM-DD.json \
  --mode AUTO_APPLIED \
  --auto-apply-candidate output/live/weekly_auto_apply_candidate_YYYY-MM-DD.json \
  --validation "bash -n scripts/auto_daily.sh: PASS" \
  --validation "PYTHONPATH=src python3 -m pytest ...: PASS"
```

Use `--mode PROPOSAL_ONLY` when no code was auto-applied. Finalize writes
`output/live/weekly_review_YYYY-MM-DD.md`, appends
`output/live/flywheel_change_ledger.jsonl`, stages only the weekly allowlist, and commits to
the current branch. If validation fails, fix and rerun validation, or finalize as
`PROPOSAL_ONLY`; do not label a failed or unvalidated strategy change `AUTO_APPLIED`.
An `AUTO_APPLIED` finalize must include at least one auto-apply candidate with required
fields `id`, `title`, `source`, `recommended_change`, and a complete `evidence_bundle`
(`problem_observed`, `attribution`, `evidence_artifact`, `baseline_vs_variant`,
`overfit_check`, `change_scope`, `rollback`). The candidate `source` must be from the
fixed input list; otherwise it is a proposal requiring user confirmation.

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
# 3) after the T+1 close is available — join realized returns: A/B/C/D verdict + accumulate training rows
PYTHONPATH=src python3 kronos_screen/scripts/forward_eval.py --live-only
# 4) settle book A (validated open->next-close reference) + A-vs-B comparison
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_a.py
# 5) monitor and settle Book T with its trend exit profile
PYTHONPATH=src python3 scripts/live_monitor.py --book T --execute-sells
PYTHONPATH=src python3 kronos_screen/scripts/settle_book_t.py
# 6) per-trade PnL attribution vs the validated counterfactual (reconciles to the account)
PYTHONPATH=src python3 kronos_screen/scripts/decompose_pnl.py
# 7) capability flywheel (weekly) — judge the accumulated pipeline under the discipline guards + record a verdict
PYTHONPATH=src python3 scripts/continuous_optimize.py --record
# 8) trend capability flywheel (weekly) — judge Book T with compounded/dd/turnover guards + record changed verdicts
PYTHONPATH=src python3 scripts/trend_optimize.py --record
```

The capability flywheel (`scripts/continuous_optimize.py`) closes the loop: it reads `training_rows.parquet`, builds per-trade results (each pick vs that day's take-all mean), runs them through `src/xiaocao/research/guards.py` (cache-only, walk-forward train+test, **per-trade not day-weighted**, multiple-comparison significance), and appends the verdict to the `kronos_screen/HYPOTHESES.jsonl` knowledge ledger — the executable successor to STATE.md's hand-written log. It will honestly REJECT a marginal/over-fit edge; treat a REJECTED verdict as evidence the overlay is not (yet) validated, not as a failure. Each run re-evaluates every tracked variant (A `kp_star`, B `vb_star`, C `mode_star`, D `qibao_benchmark_star`; more data may flip a verdict) but only re-records the ledger when the verdict CHANGED, consulting `ledger.already_refuted(id)` — so a settled, unchanged verdict is not re-litigated. To judge any other hypothesis, produce a `{day, strat_ret, base_ret}` jsonl from cache and run `scripts/research_run.py`.

The trend capability flywheel (`scripts/trend_optimize.py`) is parallel, not a
variant of the above: it builds non-overlapping Book-T-style holds from the
cached concept panel and judges them with `src/xiaocao/research/trend_guards.py`
on compounded alpha, max drawdown, turnover, walk-forward retention,
per-hold significance, and non-bull survival. Its `--record` path writes changed
trend verdicts into the same ledger with trend-specific metrics; it still has
zero authority to change `TREND_*` params without §10.

### The three flywheels & what to do at each ③ state

`scripts/flywheel_selfcheck.py` reports three coupled flywheels: **① capital** (钱滚钱), **② capability** (经验滚经验), **③ strategy** (本事变强). ① and ② turn automatically every day — if either is not `spinning`/`wired`, it's a wiring/data break to fix (the self-check exit code and warnings tell you). ③ is the **actuator leg**; act by its `status`:

- **`open` (🟡) — the normal state today.** No unconsumed PASS is waiting. There may be applied PASS evidence recorded in `reference/experience/applied_verdicts.jsonl`; no new action is required.
- **`blocked` (🔴) — a real anomaly, escalate or propose.** A hypothesis has PASSed the discipline guards but has not been consumed. If the fixed weekly input bundle includes concrete mapping, attribution, overfit check, validation, and rollback for a paper/simulation/research/tooling change, apply it through weekly deep review and record the consumption. If that mapping is missing or points at real-capital/account/safety/core truth-source changes, write a proposal for the human instead.
- **`closed` (🟢) — future.** Once a dedicated actuator can convert qualified PASS evidence into audited changes without agent hand work, the ②→③→① ring closes. Until then, `rings.fully_closed=False` is the honest state, not a bug.

Accumulated artifacts:

- `output/live/signal_snapshots.jsonl` — per-candidate daily, keyed by `(date, code, is_live, book)`: K/P scores, ★/★B/★M tiers (`kp_star` / `vb_star` / `mode_star`) + `vb_swap`, raw-qibao benchmark fields, auction features, and trend context fields when capture has them (`is_live` flags real same-day captures; re-running a day replaces that day's rows for the same book — idempotent). ★M is K survivors re-ranked by live all-hit mode-rotation `rank_score`; it is shadow forward-test only unless the research guard and §10 human gate promote it.
- `output/live/eod_features.jsonl` — per-candidate tick order-flow features (净主买 / 大单净额 / 尾盘净主买).
- `output/live/training_rows.parquet` — Book-B snapshots joined to realized next-close returns; the growing short-line labeled set, including `qibao_benchmark_star` for the independent qibao benchmark D variant. Book T is excluded from this per-trade continuous-optimization path.
- `output/live/paper_account_A.json` + `book="A"` rows in `positions.jsonl` — the validated-policy virtual book (kill-switch sensor).
- `output/live/paper_account_T.json` + `book="T"` rows in `positions.jsonl` — the trend paper book; monitor via `scripts/live_monitor.py --book T` and settle via `settle_book_t.py`.
- `output/live/pnl_decompose.csv` — per-trade `pick_alpha / entry_slippage / exit_timing` attribution.
- `output/live/paper_skips.jsonl` — picks whose paper limit was never reached (audit, no silent drops).

Exit-layer validation tooling (run on demand, not daily): `kronos_screen/scripts/backtest_intraday_stop.py` replays stop policies (`next_close / sparse2 / sparse4 / hard8 / eod_only / atr`) on historical minute prints across the full candidate history; `kronos_screen/scripts/backtest_deploy_gate.py` tests deploy gates (all index/regime gates FAILED train+test consistency — the performance kill-switch is the only deploy control).

`forward_eval.py --live-only` reports take-all vs ★(K→P) vs ★B(K→P+auction) vs ★M(K survivors + mode-rotation rank) vs qibao-benchmark D with a paired significance test, so the auction tiebreak and any new signal are validated forward (call-auction and ticks are latest-only on the API → not backtestable; only live captures count). Periodically retrain P and re-fit the screen on the accumulated `training_rows.parquet`, then refresh `kronos_screen/model/*.joblib`. Background and full evaluation history are in `kronos_screen/STATE.md`.

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
