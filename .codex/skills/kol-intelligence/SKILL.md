---
name: kol-intelligence
description: Capture, resume, enrich, analyze, route, and distill high-density KOL investment content for Xiaocao. Use for hourly KOL coordination, WeChat/Xiaoetong capture, Baidu Netdisk transcript recovery, text/image/transcript processing, current market and portfolio decisions, 灰常亮 publication and viewpoint maintenance, household advice, paper-only Book KOL-US actions, or durable multi-author investment-knowledge distillation.
---

# KOL Intelligence

Keep every run resumable and evidence-bound. Prefer deterministic local APIs,
CLIs, and logged-in browser DOM automation. Do not use Computer Use unless a
separately reviewed exception explicitly authorizes it. Never execute
real-capital trades.

## Load only the contract required now

- For `scripts/kol_daily.py run|status|audit`, the hourly Automation, or a
  normal no-update/retryable sweep, read
  [hourly-operation.md](references/hourly-operation.md) completely. Do not
  read the full contract before starting the runner.
- If the hourly runner emits `daily_analysis_input_required`, keep that same
  process alive, then read
  [full-contract.md](references/full-contract.md) completely before reading
  the immutable evidence and creating the requested bundle.
- For direct capture, enrichment, subscription, batch, semantic analysis,
  publication, viewpoint, notification, or Book KOL-US work, read
  [full-contract.md](references/full-contract.md) completely before acting.
- Before writing reusable knowledge, also read
  [durable-knowledge.md](references/durable-knowledge.md) completely.

Do not load unrelated references. Do not make the user invoke another skill
to complete the current-decision and reusable-knowledge branches.

## Non-negotiable semantic boundaries

- Reopen immutable evidence from disk and bind it to its current SHA-256;
  never decide from a cached chat summary.
- Preserve KOL claims separately from system validation, household advice,
  paper-only Book KOL-US judgment, and `authority=0` reusable knowledge.
- Use exactly `decision_status=actionable_signal` or
  `decision_status=no_actionable_signal`, and
  `knowledge_status=reusable_knowledge` or
  `knowledge_status=no_reusable_knowledge`, when the semantic contract applies.
- Treat holdings as context, not a search boundary. Never use keywords,
  asset-name lists, or a prior summary as an importance or completeness gate.
- Publish a promoted event to 灰常亮 before any eligible reminder or Book
  effect. A `low_density` item creates neither a report nor a reminder.
- For the latest Lv Xiaotong video, discovery, cloud transfer, transcript
  readiness, and completed analysis are checkpoints, not success. Keep the
  exact identity/version eligible across hourly sweeps until `status` proves a
  complete 灰常亮 publication receipt and stable detail URL. Every unfinished
  state must expose its concrete stage, retry boundary, and safe next action;
  a generic `waiting_count` is not an acceptable terminal explanation.
- Reconcile every external claim and receipt before retry. Corrections,
  maintenance, restarts, and replays never resend a prior reminder or paper
  action.
