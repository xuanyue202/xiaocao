# Weekly deep review automation

Read this file only for the Friday weekly flywheel-consumer branch.

## Execute

```bash
bash scripts/auto_daily.sh weekly
```

This is a research/iteration workflow, not a trading workflow. It may run on a non-trading Friday and reviews the latest trading week.

Before applying any change, read `docs/OPERATING_CONTRACT.md` completely, especially §10, plus `docs/STRATEGY_EVOLUTION_PROTOCOL.md` and `reference/experience/research_protocols.yaml`. Record pre-run `git status --porcelain`; never auto-edit a file that was already dirty.

The first phase must produce `output/live/weekly_plan_<date>.json`. Inspect its fixed-input evidence before choosing exactly one route:

- `AUTO_APPLIED`: paper/simulation/research/tooling only, with a complete evidence bundle. Strategy-return changes additionally require `change_type`, `protocol_id` and a passing `research_manifest` with diagnostics. Implement, test and provide rollback.
- `PROPOSAL_ONLY`: evidence outside the fixed list, incomplete attribution/overfit/rollback mapping, real-capital/account/safety/core-truth changes, or a dirty target. Create the dated `.scratch/weekly-deep-review/...md` proposal.
- `NO_ACTION_REQUIRED`: no qualified auto-apply candidate and no proposal.

Read-only instrumentation/report-quality gaps may be AUTO_APPLIED with focused validation when they do not alter strategy, fills, accounts or safety.

## Human-facing first screen

The Chinese first screen answers, in order:

1. What the week’s transcripts/evidence taught.
2. Where that learning was applied or distilled.
3. What the user must review/confirm and why it cannot auto-land.

Keep raw machine states and full dirty-file details in the audit section. Do not use English machine headings as the first-screen narrative.

## Finalize

```bash
PYTHONPATH=src python3 scripts/weekly_deep_review.py \
  --finalize output/live/weekly_plan_YYYY-MM-DD.json \
  --mode AUTO_APPLIED \
  --auto-apply-candidate output/live/weekly_auto_apply_candidate_YYYY-MM-DD.json \
  --validation "bash -n scripts/auto_daily.sh: PASS" \
  --validation "PYTHONPATH=src python3 -m pytest ...: PASS"
```

Use `--mode PROPOSAL_ONLY` when appropriate. Never label failed/unrun validation as AUTO_APPLIED.

Finalize must write `output/live/weekly_review_<date>.md`, append `output/live/flywheel_change_ledger.jsonl`, stage only the allowlist and commit to the current branch. Do not use `git add -A`.

Completion requires a terminal weekly command, inspected plan, implemented-or-proposed route, passing declared validations, final report/ledger and the expected scoped commit. A plan file alone is not completion.
