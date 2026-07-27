# 07 — 7×24 节点的小时级低流量日常运行闭环

**What to build:** Deploy the accepted Ticket 06 control plane as one
short-lived hourly operation on the always-on coordinator. From 07:00 through
23:00 Beijing time it discovers low-bandwidth source changes, resumes due cloud
enrichment, consumes Xiaocao broadband-worker handoffs, applies the
investment-content gate, publishes complete event reports and longitudinal
updates to 灰常亮, sends eligible event-specific Enterprise WeChat reminders,
and reaches an independent Book KOL-US paper terminal. It is silent overnight;
the 07:00 run drains the backlog. Normal operation needs no daily user action
and reads zero source-video bytes.

**Blocked by:** 06 — 可恢复的多来源批处理闭环（completed）.

**Status:** ready-for-agent

## Reader and decision contract

- [ ] Every covered source item first reaches exactly one content-value result:
  `low_density` or a promoted publication event.
- [ ] A `low_density` item has no attributable investment-decision claim,
  retains a durable local audit/no-trade reason, and creates neither a 灰常亮
  report nor an Enterprise WeChat reminder.
- [ ] Every promoted publication event independently reaches all three
  terminals: a durable complete 灰常亮 report, an alert result of delivered or
  legally not eligible, and a Book KOL-US paper action or explicit no-trade
  reason.
- [ ] The reminder gate is intentionally permissive for information-rich live
  sessions: current market posture, buy/sell/hold action, position boundary,
  direction choice, or actionable trigger is sufficient. A view need not
  reverse the previous session to be useful.
- [ ] Informative but expired, historical, corrective, methodology-only, or
  pure-confirmation events may publish a report with a legal no-alert reason.
- [ ] A reminder is sent only after the report receipt, leads with the most
  decision-important insight, coherently covers the remaining important
  information, and ends with exactly one stable 灰常亮 link.
- [ ] Independent events never merge reports, reminders, or Book terminals.
  Overnight backlog is processed in decision-priority order; each eligible
  event may send its own reminder instead of being folded into a digest.
- [ ] New same-KOL publications, due horizons/triggers/falsifiers, material
  fact changes, and user requests trigger targeted viewpoint-currentness
  evaluation. Evaluation-only maintenance appends to the existing 灰常亮
  projection and creates no synthetic event report, reminder, or Book action.
- [ ] Historical initialization, corrections, evaluation maintenance, restart,
  and idempotent replay never resend an earlier reminder or paper action.

## Runtime and placement contract

- [ ] Exactly one Codex Automation invokes the coordinator hourly from 07:00
  through 23:00 Beijing time. It uses an RRULE with direct local `BYHOUR` and
  `BYMINUTE`, omits `DTSTART` and `TZID`, and has no overnight invocation.
- [ ] The Automation is created or updated through the scheduling authority,
  then reopened there to verify its displayed next-run cadence and absence of
  duplicates.
- [ ] Each invocation is short-lived and reconstructs due work from the
  append-only ledger. One waiting child cannot keep the process resident or
  block other ready work.
- [ ] Lv Xiaotong is discovered through the single accepted private-config
  Baidu share URL/code path; normal metadata polling, media dispatch, cloud
  transfer/enrichment, OCR, analysis, and output require no user polling.
- [ ] Lucifer discovery watches lightweight metadata under
  `/课程/路西法全套`. The user remains responsible only for legally purchasing
  and synchronizing new material into that directory.
- [ ] Xiaocao remains the exceptional user-present broadband path. The
  broadband worker captures/compresses or uploads unavoidable large media and
  hands the coordinator only lightweight state and artifact references.
- [ ] The coordinator reads zero source-video bytes and does not use Computer
  Use. Provider API/CLI or semantic browser interfaces are the only accepted
  recurring paths.
- [ ] Normal no-update runs and self-recoverable transient failures are silent.
  A blocker that truly requires user action creates one concise operational
  reminder with the exact required action; the same blocker is not repeated
  until its state changes.
- [ ] One runner provides `run`, `status`, and `audit`; no source-specific
  dashboard, fallback adapter chain, or additional manual control plane is
  introduced.

## End-to-end acceptance

- [ ] One real automatically discovered Lv Xiaotong or Lucifer update reaches
  its content-value result and, when promoted, all three event terminals
  without a user discovery step.
- [ ] One real Xiaocao broadband handoff reaches the same promoted-event
  terminals without moving the source video through the coordinator.
- [ ] One real or reviewed short text/image sample with zero attributable
  investment claims proves `low_density`: local audited terminal, no 灰常亮
  report, no reminder, and no Book trade.
- [ ] Acceptance includes a report-only event and an alert-eligible event; the
  latter proves report-first publication and one all-recipient reminder with
  the stable report link.
- [ ] A targeted due/fact-change viewpoint reevaluation appends a new
  evaluation, preserves history/current projection order, and produces zero
  reminder and Book side effects.
- [ ] A forced interruption between discovery, report publication, reminder,
  Book, and viewpoint maintenance resumes only unfinished work. A full replay
  leaves every external receipt and paper fill unchanged.
- [ ] Payload accounting proves zero coordinator source-video bytes and records
  only lightweight metadata, transcripts, images, reports, and receipts.
- [ ] A user-action blocker produces one operational reminder; repeated hourly
  runs remain silent until the blocker changes or clears.
- [ ] The live Automation view proves the intended daytime hourly cadence, no
  duplicate task, and a next run consistent with the current Beijing clock.
- [ ] Live acceptance records discovery latency, processing latency, reminder
  count, no-update silence, low-density suppression, report URL, Book result,
  viewpoint-maintenance result, traffic accounting, and replay hashes in one
  durable artifact.
- [ ] Update the runtime bundle and `kol-intelligence` Skill to match the
  accepted behavior, run focused plus full KOL tests, and create the scoped
  Ticket 07 commit.

## Non-goals

- Full unattended Enterprise WeChat/Xiaoetong playback or password entry.
- Local source-video download on the always-on coordinator.
- Automatic purchase or acquisition of Lucifer material.
- A second Baidu discovery route, preventive fallback adapter, Computer Use
  workflow, batch digest, or new 灰常亮 analysis engine.
- Any real-capital trade.
