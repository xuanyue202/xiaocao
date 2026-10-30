---
name: xiaocao-trading
description: Use for Xiaocao repository work: scheduled morning/intraday/EOD/weekly flows; A-share data, strategy, reports, paper/APP simulation and research.
metadata:
  short-description: Xiaocao role/phase router
---

# Xiaocao Trading

Choose the actual consumer before loading its instructions. Work from the current
checkout if it has pyproject.toml and src/xiaocao; otherwise use this skill's
assets/xiaocao-runtime. Prefer PYTHONPATH=src .venv/bin/python where available.
Keep current role/Automation/Thread, original process, budget and exact inputs.

## Scheduled task: start, then load the owned phase

The scheduler prompt gives the exact first action. Verify its initial header and
actual runtime identity, then start that action with short yield; read the role
guide while the original process waits. Closing's first shell call is its startup
launcher; sparse/hour locks may require immediate quiet stop before any other work.
Why: context preparation must not consume an irreversible trading window.

| Actual consumer | Role guide |
|---|---|
| APP Book B morning | [morning-app](references/tasks/morning-app.md) |
| Original recommendation producer | [morning-producer](references/tasks/morning-producer.md) |
| Original Paper B/T supervisor | [morning-paper](references/tasks/morning-paper.md) |
| Opening protection /14:25 precheck /14:45 close | [protective monitor](references/tasks/monitor-protective.md) |
|10:25/10:55/13:25/13:55 claim owner | [sparse monitor](references/tasks/monitor-sparse.md) |
| EOD post-close business/feedback | [EOD owner](references/tasks/eod.md) |
| Weekly frozen-plan/repair/research | [weekly owner](references/tasks/weekly.md) |

Read the role's current phase, then only references triggered by an emitted event.
[Shared automation contract](references/automation-context.md) defines identity,
owned recovery, evidence, financial/notification boundaries. Long automation
references are detailed lookup contracts, not an instruction to preload every
consumer or all historical incident narratives. A duplicate/no-op gate stops
before supporting work; preserve the actual returned branch.

## Repository, strategy and research work

| Need | Entry |
|---|---|
| Strategy consumer/parameter/authority map | docs/STRATEGY_CONSUMPTION.md, then relevant source modules |
| Change or adjudicate business semantics | Read docs/OPERATING_CONTRACT.md completely before changing them |
| Market data/auth/history/source issues | [market-data](references/market-data.md) |
| Backtest/report/current research evidence | [strategy-and-backtests](references/strategy-and-backtests.md) |
| Hypothesis/verdict/research-promotion loop | [research-flywheels](references/research-flywheels.md) |
| Posture/exit judgment priors | reference/experience/README.md, then only its relevant artifact |
| Current KOL applicability/policy | [kol-trading-judgment](references/kol-trading-judgment.md) |
| Native APP diagnostic/action/recovery | [foundersc-native-ax](references/foundersc-native-ax.md), exact current guidance |
| Failed or overbroad execution dependency | [book-b-live-repair](references/book-b-live-repair.md) |
| Create/update/audit scheduling | [scheduling](references/scheduling.md) |
| Exact historical OpenCLI evidence only | [legacy OpenCLI](references/foundersc-opencli.md); never use inside native-app |

## Authority and completion

Operating Contract is business SSOT; code implements behavior; artifact receipts
prove outcomes. A mismatch is a repair issue. Apply §1a: local digital simulation
and APP-server simulation are distinct; APP legacy live labels do not establish
real brokerage effects. Preserve formal order/claim/accounting rigor because
false fills or erased failures invalidate the experiment.

Paper A/B/T, APP and independent funded research retain their own writers/fills.
Published LiangHui meanings are semantic SSOT; trading workers adapt current
conditions, not re-extract sources. Judgment priors have authority0; only the
existing reviewed §2a interface may influence current decisions. Parameter/strategy
promotion uses research_run and §10, not a coherent story or a model result.

Completion requires the owned branch's actual outcomes and evidence, plus any
remaining authorized local recovery. A recoverable early blocked process is not
task completion. Use §1e scope/repair; never replay unknown effects, replace an
active owner, reset a claim or extend the original budget. Genuine current missing
proof pauses affected new BUY; independent protective exits use their own guards.

For source changes follow AGENTS.md: preserve WIP, minimum urgent validation then
original continuation, independent Standards/Spec review and affected regression.
APP engineering tests require the legal test-window gate. Instruction changes
with hash-bound packets must preserve old exact readback and package closure;
see docs/CONTEXT_ENGINEERING.md. Do not label instructions or tests as natural
execution acceptance. Final Chinese output separates deterministic business,
support degradation, actual orders/fills and delivery. Keep payloads in artifacts.
