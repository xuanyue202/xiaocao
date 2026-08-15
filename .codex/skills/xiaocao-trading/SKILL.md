---
name: xiaocao-trading
description: Use for Xiaocao repository work: live morning, intraday, EOD, weekly and scheduling automations; A-share quotes, market, pools and indicators; reports, strategies, backtests, paper accounts and research flywheels.
metadata:
  short-description: Run Xiaocao trading and market-data workflows
---

# Xiaocao Trading

This file is the router. Load one task branch, not the whole operating manual.

## Start

1. Set `SKILL_DIR` to this skill directory.
2. Select `XIAOCAO_ROOT`:
   - Use the current checkout when it contains `pyproject.toml` and `src/xiaocao/`.
   - Otherwise use `$SKILL_DIR/assets/xiaocao-runtime`.
3. Run from `XIAOCAO_ROOT`. Prefer `.venv/bin/python` for scripts when present; otherwise use `PYTHONPATH=src python3`.
4. Read only the matching branch below before acting. If the request crosses branches, read each matching file. Do not preload sibling branches.

Completion means the requested command reached a terminal state and the branch-specific evidence was checked. A command start, intermediate log line, or UI toast is not completion.

## Non-negotiable boundaries

- `docs/OPERATING_CONTRACT.md` is the SSOT for Book A/B/T, ★E authority, fills, exits, allocation, kill-switch, account identity and capital safety. Read it completely before changing or adjudicating those semantics; do not duplicate them here.
- The deterministic spine owns data, fills, stops, accounting and safety. Never hand-compute a fill, edit an account/ledger, fabricate a trade, or authorize a real order.
- Xiaocao is paper-only unless both live-capital keys pass `src/xiaocao/live/safety.py`. An automation never creates either key.
- Judgment artifacts (`XIAOCAO_PLAYBOOK`, posture timeline, candidate hypotheses) are priors only. They cannot filter deterministic picks, tune parameters or validate a strategy. For posture/exit judgment, start at `reference/experience/README.md` and follow only its relevant pointer.
- Keep Books A, B and T separate. Same-code overlap is valid. For current truth, prefer `positions.jsonl`, `paper_trades.jsonl` and matching account files over stale holdings snapshots.
- Book-B phase-one broker seam is manual/read-only and non-runtime: it must never
  replace the canonical `paper_record.py` writer or invent a fill. It requires
  ★E/allocation proof for BUY, monitor-authorized owned-lot evidence for SELL,
  account-level writer fencing and durable takeover/reconcile evidence; no real
  submit is permitted while the Founder template reports `submit_capability=false`.
- Before trusting A/B or repaired ledger state, run `scripts/data_doctor.py`. Raw cumulative A-B PnL is accounting information; exit comparison requires the identical-entry paired cohort.
- Cache first and rate-limit Xiaocao API calls. The market-data branch contains endpoint-specific traps.

## Route by consumer task

| Request branch | Read completely before acting |
|---|---|
| Morning automation, 9:25 recommendation, frozen evidence review, ★E paper buys | [`references/automation-morning.md`](references/automation-morning.md) |
| Opening/sparse monitor, 14:25 precheck, 14:55 discipline, sell or holding audit | [`references/automation-intraday.md`](references/automation-intraday.md) |
| Daily EOD capture, evaluation, A/B/T settlement and audit | [`references/automation-eod.md`](references/automation-eod.md) |
| Friday weekly deep review and evidence-gated auto-iteration | [`references/automation-weekly.md`](references/automation-weekly.md) |
| Automation cadence, RRULE or Codex schedule changes | [`references/scheduling.md`](references/scheduling.md) |
| Quotes, environment, minute/K-line, pools, sectors, indices or indicators | [`references/market-data.md`](references/market-data.md) |
| Reports, strategy runs, backtests, cohorts or paper-vs-market research | [`references/strategy-and-backtests.md`](references/strategy-and-backtests.md) |
| Kronos variants, training rows, research guards, verdict ledger or flywheel states | [`references/research-flywheels.md`](references/research-flywheels.md) |
| Founder Securities Web/OpenCLI read-only probe, prepare, reconcile or recover | [`references/foundersc-opencli.md`](references/foundersc-opencli.md) |
| Book-B phase-one execution seam, ownership evidence or allocation proof | [`references/automation-morning.md`](references/automation-morning.md), [`references/automation-intraday.md`](references/automation-intraday.md), [`references/foundersc-opencli.md`](references/foundersc-opencli.md) |
| “What should the trading system do?” or a behavior change | `docs/OPERATING_CONTRACT.md`, then the owning code/tests |
| Posture, discretionary exit triage or distilled 小草 knowledge | `reference/experience/README.md`, then only the routed playbook/timeline artifact |

## Shared evidence tools

- `python3 scripts/show_journal.py --date today`: same-day cross-run chronology; read first for intraday/EOD.
- `python3 scripts/status.py --json`: Book A/B paired comparison, Book T valuation, cash/equity, decisions and open holdings.
- `python3 scripts/data_doctor.py`: ledger/snapshot integrity gate.
- `python3 scripts/flywheel_selfcheck.py`: capital/capability/strategy-loop health.
- `python3 scripts/research_run.py --trades <file> --n-tried N`: guarded cache-built research verdict.

## Response contract

- For automations, reply in concise Chinese and lead with execution/account outcome, not market storytelling.
- State the actual market/query date. Link the decisive local artifacts and report key rows/counts.
- Separate deterministic success from supporting-layer degradation such as stale posture, missing reviews or a heavier knowledge backlog.
- Report `候选股: NONE`, non-trading-day skip, `T+1_blocked` or an unchanged REJECTED research verdict as their actual bounded states, not generic failures.
- Escalate only branch-defined anomalies; never turn warnings into trades or parameter changes.
