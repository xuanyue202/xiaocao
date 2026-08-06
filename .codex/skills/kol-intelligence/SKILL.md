---
name: kol-intelligence
description: Capture, resume, analyze, route, publish, and distill Xiaocao KOL investment content across hourly coordination, WeChat/Xiaoetong, Baidu Netdisk, 灰常亮, household advice, paper-only Book KOL-US, and durable knowledge.
---

# KOL Intelligence

Keep every run resumable and evidence-bound. Prefer deterministic local APIs,
CLIs, and logged-in browser DOM automation. Do not use Computer Use unless a
separately reviewed exception explicitly authorizes it. Never execute
real-capital trades.

## Repair before escalating

Do not stop at a diagnosable repository or provider-contract failure, and do
not relabel it as a user blocker. Reconcile the exact claims and receipts,
identify the root cause from current evidence, patch repository-owned code,
OpenCLI templates, tests, or this contract when intended behavior is already
fixed, run proportionate regressions, and resume the same job/claim/session.
Do this in the current task without waiting for the user to request a
retrospective. Preserve unrelated WIP; stage only the repair, then commit and
normally push it after tests so later Automations inherit the fix.

`repair_required` means the Agent owns diagnosis and repair. Only authentication,
SMS, CAPTCHA, consent, a missing fact only the user can provide, or an uncertain
external side effect that cannot be reconciled may become `user_action_required`.
Do not auto-change investment semantics, recipients, schedules, real-capital
authority, or bypass an explicit human gate. If an exact-once process already
exited, fix the code and preserve its immutable job for the next authorized
resume; never run the same hourly command twice or fake completion.

## Load only the required contract

- For an unambiguous Xiaocao replay capture, read
  [xiaocao-capture-start.md](references/xiaocao-capture-start.md) completely
  and start within 10 seconds. Do not read `full-contract.md` before Ready.
- For the local hourly `scripts/kol_daily.py capture-local` Automation, read
  [hourly-local-capture.md](references/hourly-local-capture.md) completely.
  Do not load the remote-writer or full contract on the capture node.
- For the remote hourly `scripts/kol_daily.py run|status|audit` Automation or a
  normal no-update/retryable sweep, read
  [hourly-remote-writer.md](references/hourly-remote-writer.md) completely. Do
  not read the full contract before starting the runner.
- If the hourly runner emits `daily_analysis_input_required`, keep that same
  process alive, then read
  [full-contract.md](references/full-contract.md) completely before reading
  the immutable evidence and creating the requested bundle.
- For remote post-handoff, enrichment, subscription, batch, semantic analysis,
  publication, viewpoint, notification, or Book KOL-US work, read
  [full-contract.md](references/full-contract.md) completely before acting.
- Before writing reusable knowledge, also read
  [durable-knowledge.md](references/durable-knowledge.md) completely.

Do not load unrelated references. Do not make the user invoke another skill
to complete the current-decision and reusable-knowledge branches.

## Route Xiaocao recap requests before analysis

Treat “小草复盘” in a live/video context as a live-replay capture request first;
let fast-start inspect the current Ticket 03 job and capture ledger before Ready. If no
discoverable
state disambiguates the request, ask only: “录入直播回放，还是复盘已有报告？”
After selection, keep that route fixed through audit; later uses of “复盘” do
not switch the task back to report commentary.
Treat the run as complete only when the reader-facing report has been read back,
the exact recipient set has durable reminder receipts, and the node that owns
each side of the handoff has passed its own acceptance scope. The remote writer
must use `scope=post_handoff`; it must never require local capture ledgers or
video bytes that the handoff contract explicitly forbids transferring. These
deterministic receipts complete a routine Ticket 03 run automatically; do not
pause for report-quality or user confirmation. Human review is reserved for an
explicit evidence ambiguity, requested editorial correction, or a separately
specified historical aggregation gate. The `confirm` command is migration-only
for already-persisted legacy `awaiting_user_confirmation` states.

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
- Use reviewed reader copy for both terminals: `reader_title` may retain the
  report date or session, while optional `reader_reminder.title/summary` keeps
  the WeChat entry concise. Raw filenames, compression suffixes, and internal
  actions such as `wait` or `no_trade` are acceptance failures even when the
  structure is otherwise valid.
- Bind every notification claim to the exact final title/body bytes passed to
  the Relay. A wrapper must not claim generic copy and substitute different
  report copy inside its sender callback.
- For the latest Lv Xiaotong video, discovery, cloud transfer, transcript
  readiness, and completed analysis are checkpoints, not success. Keep the
  exact identity/version eligible across hourly sweeps until `status` proves a
  complete 灰常亮 publication receipt and stable detail URL. Every unfinished
  state must expose its concrete stage, retry boundary, and safe next action;
  a generic `waiting_count` is not an acceptable terminal explanation.
- Reconcile every external claim and receipt before retry. Corrections,
  maintenance, restarts, and replays never resend a prior reminder or paper
  action.
