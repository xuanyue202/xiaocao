# Repository Guidelines

Xiaocao is a Python CLI and automation toolkit for A-share data, strategy screening, reports, Kronos recommendations, and paper-trading surveillance.

当前研究部署按用户 2026-09-12 的明确说明分为**本地数字模拟**与 **APP 服务端仿真**。当前 APP 即使界面、代码或历史记录称为“实盘/live”，连接的仍是无法影响真实券商账户的仿真服务。所有本项目任务应同时理解：在既有任务范围内通过项目代码推进仿真买卖、撤单和对账；按正式交易标准保持策略、仓位、时效、成交确认与账本准确性，不因知道是模拟而降低执行积极性或实验严谨性。完整定义及当前部署范围见 `docs/OPERATING_CONTRACT.md` §1a；旧的实盘措辞按该节解释。

For trading faults, follow `.codex/skills/xiaocao-trading/references/book-b-live-repair.md`: urgent AX/code repair and minimum necessary validation precede same-plan continuation; root-cause analysis and affected-behavior verification follow the terminal outcome.

Every repository change must receive a post-change `code-review` using independent Standards and Spec reviews of an explicit baseline and scoped diff. In the 09:25–09:30 golden window and other legal urgent trading windows, first repair the necessary dependency, validate order correctness and continue the original trade; perform code review after terminal or exact unresolved-order readback, before declaring the change complete. The implementing agent owns the quality loop: assess each finding from first principles, fix demonstrated problems, re-review the affected diff and record findings and validation limits. Do not hand an actionable review backlog back to the user; escalate only an irreducible permission, external-evidence gap or user decision. Deferred APP tests remain deferred under the test-window rules; a review does not substitute for them.

## Xiaocao Knowledge Base (read when working on strategy/posture/exit judgment)

`reference/experience/README.md` is the single entry point to the distilled 小草 knowledge: the judgment playbook (`docs/XIAOCAO_PLAYBOOK.md`), the dated posture timeline (`reference/experience/REGIME_TIMELINE.md`), the falsifiable hypothesis backlog (`reference/experience/xiaocao_hypotheses.jsonl`), the verdict ledger (`kronos_screen/HYPOTHESES.jsonl`), and the **flywheel findings log**. One command for current state: `PYTHONPATH=src python3 scripts/xiaocao_knowledge.py`.

These are **judgment priors / candidate hypotheses** — raw claims have authority=0 and MUST NOT auto-tune parameters. Permanent strategy/parameter promotion requires `scripts/research_run.py` and the §10 human gate. The separately user-authorized bounded current KOL decision interface is governed by `docs/OPERATING_CONTRACT.md` §2a and the trading skill's `references/kol-trading-judgment.md`; it requires source verification, current applicability and independent review, and never widens capital/execution authority. Same SSOT discipline as everything else here.

## Project Structure & Module Organization

Python uses a `src/` layout. Core code lives in `src/xiaocao/`; CLI entrypoints are `cli.py` and `__main__.py`. Strategy logic is under `strategy/`, API under `api/`, sources under `datasource/`, and live safety gates under `live/`.

Operational scripts live in `scripts/`; live automation centers on `auto_daily.sh`, `live_recommend.py`, and `live_monitor.py`. Kronos tooling lives in `kronos_screen/`. Tests are in `tests/`, with API e2e tests in `tests/e2e/`. Codex config is in `.codex/`; generated bundles and `output/` artifacts are not source.

## Build, Test, and Development Commands

- `PYTHONPATH=src python3 -m xiaocao --help`: run the CLI from source.
- `python3 -m pip install -e .`: install the package and `xiaocao` console script.
- `PYTHONPATH=src python3 -m pytest -q`: run the standard test suite.
- `PYTHONPATH=src .venv/bin/python -m pytest -q -m 'not e2e' -n 2 --dist loadfile`: full offline regression, grouped by file on two workers. See `docs/TESTING.md` for scope, isolation and test-value criteria. Keep focused tests and coverage runs serial.
- `PYTHONPATH=src python3 -m pytest tests/e2e -q`: run live API tests.
- `bash -n scripts/auto_daily.sh`: syntax-check automation shell.
- `python3 scripts/package_xiaocao_skill.py`: refresh the Codex skill runtime and symlink install.

## Codex Skill, CLI & Automation Flow

Treat repo code as the behavioral source and `.codex/skills/xiaocao-trading/SKILL.md` as agent instructions. **Codex Automation is the runtime scheduling authority**: create or update active tasks through the Codex Automation tool/API, then view them again through that interface. `.codex/automations/*/automation.toml` and `~/.codex/automations/*/automation.toml` are reviewable mirrors/implementation state; editing either file alone does not activate or verify a schedule.

All China-market schedules must express the intended China wall-clock time directly in an RRULE with `BYHOUR` and `BYMINUTE`, interpreted in the user's locale. For ordinary recurring Codex cron automations, **omit `DTSTART` and `TZID` entirely** and never manually convert China time to UTC. The current Codex Automation contract reserves DTSTART/timezone-specific schedules for a separate reviewed path, and Codex Desktop has shown an eight-hour next-run preview error when a TZID-bearing DTSTART is used here. Preserve unrelated working schedules when changing one task. After any schedule change, update the existing Automation (do not create a duplicate), re-open it through the Automation interface, and verify the displayed next-run cadence against the current local clock.

End-to-end path: Codex Automation schedule -> automation prompt -> `xiaocao-trading` skill -> runtime bundle -> CLI/scripts -> `output/live/*` artifacts -> summary. CLI output, live behavior, account files, or Kronos fields require matching skill and automation updates.

### Local KOL browser recovery

For an OpenCLI timeout, unresponsive/absent Edge window or upload continuation,
read [local capture recovery](docs/agents/local-capture-recovery.md) before acting.
Keep the exact capture/job/upload claim; restore the existing session locally.
Why: a closed browser is an owned recoverable dependency, not proof of a user blocker.

## Codex Remote collaboration

For remote connectivity, task discovery, deployment or writer cutover, read
[remote collaboration](docs/agents/remote-collaboration.md) before diagnosing or
changing ownership. Reuse Codex Remote and the registered project/task.
Why: connected device, discoverable task and business-ready runtime prove different
things; keep their evidence and single-writer authority separate.

## Coding Style & Naming Conventions

Use 4-space indentation and type hints where they clarify interfaces. Prefer small, testable functions and explicit normalization. Modules and tests use `snake_case`; CLI subcommands should stay descriptive. Keep runtime state and generated reports under `output/`.

## Testing Guidelines

方正 APP 相关模拟测试（含自动化离线回归、APP 端到端及手动压力/试单脚本）仅在北京时间周六日，或工作日 09:00 前、11:30（含）–13:00（不含）、15:00 起运行；工作日 09:00–11:30、13:00–15:00 禁止。新测试使用 `app_simulation` pytest 标记；临时通过原生 CLI 做测试时设置 `XIAOCAO_APP_SIMULATION_TEST=1`，禁止用正式交易入口绕过测试时段。具体入口、到点停止及同批次收尾见 `docs/FOUNDER_NATIVE_AX.md` 的测试时段说明。正式交易、生产对账及必要故障修复不属于工程模拟测试。

Pytest uses `pytest.ini`, `tests` as the default path, and `e2e` as the live API marker. Name tests `test_*.py`. For live trading changes, cover normal flow and fail-closed safety, especially paper vs real-capital paths.

Choose checks by the failure they can detect. Preserve behavioral tests for order identity, duplicate effects, amounts and accounting, plus deployment wiring and broken-link checks. Do not lock prose, document versions, model preferences, line counts or internal implementation spelling into tests. Documentation-only edits need a diff/link/config check, not a full trading suite. Follow the urgent-repair reference for minimum pre-resume validation; expand regression only for the affected behavior after the terminal outcome.

## Commit & Pull Request Guidelines

Recent commits use concise imperative summaries, sometimes with a priority prefix such as `P0:`. Examples: `Add live trading automation migration support`, `Improve paper trading execution controls`. PRs should describe changes, list validation, call out live/API impact, and mention excluded artifacts.

Once the user authorizes a coherent KOL or knowledge-base change set and it has passed its scoped validation, commit and normally push it promptly so the local and remote writers do not drift into a later conflict. Preserve unrelated WIP and exclude runtime `output/`, credentials, caches, binaries, account state, and other generated artifacts. Fetch and reconcile the remote branch before pushing; never force-push over another writer.

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
