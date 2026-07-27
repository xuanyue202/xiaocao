# Repository Guidelines

Xiaocao is a Python CLI and automation toolkit for A-share data, strategy screening, reports, Kronos recommendations, and paper-trading surveillance.

## Xiaocao Knowledge Base (read when working on strategy/posture/exit judgment)

`reference/experience/README.md` is the single entry point to the distilled 小草 knowledge: the judgment playbook (`docs/XIAOCAO_PLAYBOOK.md`), the dated posture timeline (`reference/experience/REGIME_TIMELINE.md`), the falsifiable hypothesis backlog (`reference/experience/xiaocao_hypotheses.jsonl`), the verdict ledger (`kronos_screen/HYPOTHESES.jsonl`), and the **flywheel findings log**. One command for current state: `PYTHONPATH=src python3 scripts/xiaocao_knowledge.py`.

These are **judgment priors / candidate hypotheses** — agent-cortex and flywheel inputs only. They MUST NOT enter the deterministic spine or auto-tune any param; a claim has zero authority over strategy until it passes `scripts/research_run.py` and the §10 human gate (see `docs/OPERATING_CONTRACT.md` §2). Same SSOT discipline as everything else here.

## Project Structure & Module Organization

Python uses a `src/` layout. Core code lives in `src/xiaocao/`; CLI entrypoints are `cli.py` and `__main__.py`. Strategy logic is under `strategy/`, API under `api/`, sources under `datasource/`, and live safety gates under `live/`.

Operational scripts live in `scripts/`; live automation centers on `auto_daily.sh`, `live_recommend.py`, and `live_monitor.py`. Kronos tooling lives in `kronos_screen/`. Tests are in `tests/`, with API e2e tests in `tests/e2e/`. Codex config is in `.codex/`; generated bundles and `output/` artifacts are not source.

## Build, Test, and Development Commands

- `PYTHONPATH=src python3 -m xiaocao --help`: run the CLI from source.
- `python3 -m pip install -e .`: install the package and `xiaocao` console script.
- `PYTHONPATH=src python3 -m pytest -q`: run the standard test suite.
- `PYTHONPATH=src python3 -m pytest tests/e2e -q`: run live API tests.
- `bash -n scripts/auto_daily.sh`: syntax-check automation shell.
- `python3 scripts/package_xiaocao_skill.py`: refresh the Codex skill runtime and symlink install.

## Codex Skill, CLI & Automation Flow

Treat repo code as the behavioral source and `.codex/skills/xiaocao-trading/SKILL.md` as agent instructions. **Codex Automation is the runtime scheduling authority**: create or update active tasks through the Codex Automation tool/API, then view them again through that interface. `.codex/automations/*/automation.toml` and `~/.codex/automations/*/automation.toml` are reviewable mirrors/implementation state; editing either file alone does not activate or verify a schedule.

All China-market schedules must express the intended China wall-clock time directly in an RRULE with `BYHOUR` and `BYMINUTE`, interpreted in the user's locale. For ordinary recurring Codex cron automations, **omit `DTSTART` and `TZID` entirely** and never manually convert China time to UTC. The current Codex Automation contract reserves DTSTART/timezone-specific schedules for a separate reviewed path, and Codex Desktop has shown an eight-hour next-run preview error when a TZID-bearing DTSTART is used here. Preserve unrelated working schedules when changing one task. After any schedule change, update the existing Automation (do not create a duplicate), re-open it through the Automation interface, and verify the displayed next-run cadence against the current local clock.

End-to-end path: Codex Automation schedule -> automation prompt -> `xiaocao-trading` skill -> runtime bundle -> CLI/scripts -> `output/live/*` artifacts -> summary. CLI output, live behavior, account files, or Kronos fields require matching skill and automation updates.

## Coding Style & Naming Conventions

Use 4-space indentation and type hints where they clarify interfaces. Prefer small, testable functions and explicit normalization. Modules and tests use `snake_case`; CLI subcommands should stay descriptive. Keep runtime state and generated reports under `output/`.

## Testing Guidelines

Pytest uses `pytest.ini`, `tests` as the default path, and `e2e` as the live API marker. Name tests `test_*.py`. For live trading changes, cover normal flow and fail-closed safety, especially paper vs real-capital paths.

## Commit & Pull Request Guidelines

Recent commits use concise imperative summaries, sometimes with a priority prefix such as `P0:`. Examples: `Add live trading automation migration support`, `Improve paper trading execution controls`. PRs should describe changes, list validation, call out live/API impact, and mention excluded artifacts.

## Calling the xiaocao data API (`p-xcapi.kjap1.cn`)

**Rate-limit every call.** The API throttles on bursts — empirically ~10 sequential calls succeed, but ~60 in quick succession start returning empty `[]`/null (a silent throttle, not an error). When fetching for more than a handful of symbols/dates: batch small, space requests (e.g. sleep ~0.5–1s between calls, ≤~8 concurrent), and **prefer cache-first reads** (`output/.cache/xiaocao.db`) over re-fetching. Never hammer it in a tight loop. Cache results so a retry doesn't re-hit the API.

Gotchas (each cost real debugging time):
- **Codes need the exchange suffix** — `date_kline('600519')` returns empty; `date_kline('600519.XSHG')` works. Always pass `NNNNNN.XSHG/.XSHE/.BJSE`.
- **Minute-line price is in `trade`, not `close`** — `/stock/minute_line` bars have `open/high/low/close = null`; the per-minute price is the `trade` field (+ `vol`/`amt`/`pctChangeRate`). Reconstruct daily OHLC/VWAP from `trade`.
- **`date_kline` (daily OHLCV) can lag weeks** — it froze at 2026-05-29 for ~3 weeks while realtime/minute stayed current. Recent daily bars are reconstructable from `minute_line(code, trade_date=YYYYMMDD, count=241)` (history needs BOTH `trade_date` and `count`). `data_health.stale_market_cache` flags the lag at eod; don't let a swallowed `except: rows=[]` hide it.
- **`date_kline` history is deep, concept-rank history is shallow** — `date_kline(code, count=1300)` serves real prices back to ~2021-02 (incl. the 2022 bear), but `block_category_rank_v3` serves historical *rankings* (`num`/`name`) while the per-concept **return** field `prePctChangeRate` is **0 before ~2024-05-13** (historical concept returns are NOT available). Backtesting trend/concept *returns* on pre-2024-05 ranks silently uses zero-return data (it inflated a cross-cycle alpha to +20~28pp until caught — see `research_trend_crosscycle.py:_real_return_panel`). For cross-cycle returns go STOCK-level via `date_kline`, or reconstruct concept returns from constituent `date_kline`.

## Security & Configuration Tips

Do not commit `xiaocao.yaml`, account state, caches, binaries, or signing secrets. Real-capital paths must go through `src/xiaocao/live/safety.py`; automations should remain paper/sensor safe unless explicitly authorized by the two-key flow.

## Agent skills

### Issue tracker

Issues and PRDs are tracked as local markdown files under `.scratch/<feature-slug>/`; external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The default mattpocock/skills triage vocabulary is used unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain-doc layout: root `CONTEXT.md` plus `docs/adr/` when they exist. See `docs/agents/domain.md`.
