# Hourly Remote Writer

Use only on Ticket 07's remote sole-writer node. Local WeChat follows
[hourly-local-capture.md](hourly-local-capture.md). Do not read
`full-contract.md` unless the semantic or post-handoff work is ready.

## Runner and boundary

Start through the task/hour launcher below and retain the original process
for input requests. An already-bound exact continuation replaces `run`.

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py status
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py audit
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py convergence-report
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py stability-acceptance
```

Each run is one sweep; no concrete item is silent. Report concrete waits and exceptions,
plus credential-safe failures, in `对象 | 状态 | 说明`, prefixing each object
with `[视频]` or `[文章]`; never label `Handoff完成` as `全部完成`.
The started task owns repair; do not defer obtainable work.

Obey seven-state `writer_progress.next_action`; bind input and readback
receipts; retryability never changes owner.

`repair_required` is work for the current Agent, not a user blocker: reconcile,
patch/test/commit/push without user WIP, then continue on the same stdin. Never
run `run` twice for one slot; after matching repair closure use `resume-mailbox`
for that message and run only `narrow_resume_surface`.

A raw `waiting` result without an immutable provider `next_poll_not_before`
becomes `repair_required`; diagnostics never manufacture `wait_until` or a user
blocker. Provider deadlines, auth/CAPTCHA, and uncertain effects retain their
seven-state `writer_progress` states.

This sole writer consumes Xiaocao `scope=post_handoff` and URL-only
`wechat_official_article` LiangHuiMCP capsules as discovery metadata, not full
articles: each is not the full article. It never scans the local
WeChat contact and never reads or downloads
source-video bytes, starts playback, or uses Computer Use. Player DOM binding
requires `video-player-safety.md`; normal delivery is the mailbox drain.

For an already imported official-account capsule use only `PYTHONPATH=src
.venv/bin/python scripts/kol_daily.py process-wechat-official`; for a late
Xiaocao video capsule use only `PYTHONPATH=src .venv/bin/python
scripts/kol_daily.py process-xiaocao-handoff`. Run once, keep that process alive
for input, and do not rerun the full `run` command.

## Task/hour lock and LiangHuiMCP drain

Use the existing non-blocking hour lock, keyed by exact Automation ID and the
current Beijing date/hour. Start once in a retained interactive PTY:

```bash
CODEX_AUTOMATION_ID=xiaocao-kol-hourly-low-bandwidth-operation \
PYTHONPATH=src .venv/bin/python scripts/kol_automation_slot_gate.py \
  --automation-id xiaocao-kol-hourly-low-bandwidth-operation \
  --lock-dir output/live/kol_automation_hour_locks \
  -- .venv/bin/python scripts/kol_daily.py run
```

`hour_busy` ends this invocation before projection, mailbox or business work.
`hour_acquired` permits work; retain this same process/stdin until its command
terminates. The exec'd runner holds the lock through input waits and releases
it on exit. Different Automation IDs, dates and hours use independent keys;
a previous hour may still be running. Reacquisition after exit is allowed,
with existing source/object claims, receipts and resource locks preventing
repeated effects. Codex peer-session completion is no longer an execution gate.

After `hour_acquired`, build the cache-only trading projection and handle its
exact classification-backfill IDs while the original runner waits for input.
For an already-bound exact continuation, replace the final `run` command with
that continuation and its exact arguments in the same launcher. Further narrow
commands use this launcher too; never start a second full sweep for this run.
Retain the runtime `CODEX_THREAD_ID` and verify the initial scheduler's exact
Automation ID before launching. Identity mismatch stops before effects.

For each `daily_lianghui_mailbox_input_required`, call the exact operation and
arguments, then return one compact JSON line to the same process:

- `list_mailbox_messages`: return `{"operation":"list_mailbox_messages",
  "page":<exact structuredContent>}`. The runner asks for pending messages,
  oldest first, up to 50 per page, and follows every cursor.
- `ack_mailbox_message`: return `{"operation":"ack_mailbox_message",
  "outcome":<tool outcome>,"receipt":<exact receipt>}`.

The runner validates mailbox `kol.handoff`, type `xiaocao.kol_handoff`, schema
`1`, and exact family/message/content-hash bindings before its post-handoff
pipeline. It maintains `attempted_message_ids`; after each batch query only new
eligible messages, keep unchanged waits once, and use `resume-mailbox` when due
if the process exits. Ack only after every downstream effect and durable
receipt; `acked|already_acked` is `全部完成`, never handoff creation alone.

### Narrow repair resume

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py validate-repair --mailbox-message-id <exact-64-hex-message-id>
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py resume-mailbox \
  --mailbox-message-id <exact-64-hex-message-id> [--repair-revision <exact-40-hex-commit>]
```

`validate-repair` persists `RepairValidationReceipt` for tested pushed lineage;
`resume-mailbox` calls one exact `get_mailbox_message`, never list. Targets
fail closed on mismatch; provider waits honor their deadline and reconcile
uncertain effects. Source repairs use `validate-source-repair` then
`resume-source-repair` with exact adapter/fingerprint; resume consumes only
`narrow_resume_surface` and reads neither mailbox nor another source.

`convergence-report` reads append-only ledgers for repairs, generic waits,
gate/runner timing, effects, duplicate-effect audits, slots, and exclusions; it never
rewrites failures. First rollout requires authoritative one-writer, revision,
WIP, dependency/config/state, and Automation-ownership readback:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py rollout-readback
```

Use self-hashed Automation evidence and the existing runtime/state checks.
Historical peer-gate metrics remain diagnostics with status `retired`; they
are not rollout or stability prerequisites.
Acceptance starts seven-day/50-scheduled-slot observation; never backfill.
`stability-acceptance` is read-only: pending until gates, passed if all pass.
Run it with `--period-end <as_of>` only when acceptance is due.
`pending_observation` is not completion; only `passed` closes Issue 06. A failed
acceptance requires an explicit new rollout, never historical backfill or a
second hourly writer.

Resumes skip mailbox/sweep; mismatch is repair. Use
`resume-source-wait` after its deadline, `resume-source-input` for persisted
input, or `resume-source-user-action` after authentication, with
`--source-adapter subscription_video --source-identity <identity>`. Auth uses
identity `subscription_video:source`; clear after `user_action_required`.

After exact cloud-transfer reconciliation proves a completed private copy,
continue the unfinished item with `resume-source-user-action` and that item's
exact identity. The coordinator binds the historical blocked identity/version
to the durable reconciliation claim and receipt, even when source-level
readback projected `no_update`. Transfer completion closes only that effect;
the exact-item terminal receipt closes analysis/publication. Keep source
discovery disabled on this continuation.

Before binding or switching to a Baidu player, read
[video-player-safety.md](video-player-safety.md) completely. At provider steps,
use only the installed OpenCLI provider; keep every effect at-most-once with
exact identity/version,
bytes, hashes, and receipts. The no-MCP capture rule permits the
repository-designated LiangHui client only after read-only exact-receipt
reconciliation; auth/CAPTCHA/consent or materially incompatible business
outcomes may ask. Reconcile the
handoff/media SHA; latest content is incomplete until analysis, 灰常亮 receipt,
and stable URL.

Baidu player work requires a pause guard, paused readback, transcript integrity,
and exact-tab-close receipts; a missing receipt is `repair_required`.

### Cloud discovery coverage

Cloud scans and absence claims first read
[cloud-discovery-coverage.md](cloud-discovery-coverage.md) completely.

## Semantic loading gate

For Xiaocao transcript semantic input (`daily_analysis_input_required` and
subscriptions), read
[semantic-model-routing.md](semantic-model-routing.md) completely. Other authors
retain the canonical-bundle route. Read `full-contract.md` completely before
acceptance; its current hash must match the request if pinned. Return only
`{"bundle_path":"<validated-absolute-json-path>"}` plus a newline; no legacy bypass.

For `daily_official_article_image_input_required`, inspect every image once and
write UTF-8 Markdown headed `# 图片信息转写` with index/SHA,
information/decorative status, relevant text/chart/table content, and
uncertainty. Do not copy the body or serialize notes as JSON; write exactly
`{"image_notes_path":"<absolute-md-path>"}` plus a newline. The runner appends
notes to full Markdown before analysis.

For `daily_xiaocao_audit_input_required`, use `audit_contract.audit_template`:
retain the exact video/transcript hashes and fill its three `checks` with
`position`, an exact `excerpt` starting in that third, and `passed=true` only
after checking the persisted transcript. Return `{"audit_path":"<absolute-json-path>"}`
to the same stdin. The template starts with empty excerpts and false checks;
it is not proof until reviewed. Do not use an `excerpts`/`quote` envelope.

Keep stdin open. EOF persists `waiting_semantic_input`, preserving the original
request, evidence SHA, and item claim. The next sweep reuses that exact
request/evidence, skips completed acquisition/transcript work, never replays
publication, notification, or Book effects. Stop that adapter before later
backlog items.

Small downloads are unattended: use `Page.setDownloadBehavior` with a
controlled inbox or one memory-only link bound to the exact provider identity.
A Save prompt is not a user blocker. Only auth, SMS, CAPTCHA, or consent may
ask; never edit the ordinary Microsoft Edge profile or a global extension, or
issue a second trigger.

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`,
reviewed publication fields, and a `longitudinal_projection`: `promoted` carries
evidence-bound viewpoints with an initial `current|expired|invalidated|uncertain`
evaluation. Every evaluation also carries the typed `trading_applicability`
defined by `semantic-model-routing.md`; non-short-horizon viewpoints must be
explicitly classified rather than omitted. `none` carries an empty list and concrete reason. Missing this
decision fails closed rather than defaulting to an empty viewpoint list.

Low-density creates neither report nor reminder. A promoted event gets its
durable 灰常亮 receipt and stable URL before Book KOL-US or reminder effects;
report-only records a no-alert reason, while alert-eligible sends one reminder.
Before reusing a completed publication, verify that its report binds the accepted
source version and evidence hash and its manifest contains every accepted
viewpoint and initial evaluation. A stale local receipt is not completion proof.
Repair a mismatch through an exact-object publication correction with authoritative
hash/manifest readback; retain prior receipts and do not replay Book or reminders.
Missing independent verification, no uniquely mapped instrument, low confidence,
or Book KOL-US `no_trade` do not justify report-only when current market
posture/direction is present; retain those limits in the reminder.

## Discovery and recovery

Reuse the configured Lv share `/课程/路西法全套`, handoffs, and receipts;
validate exact identity/version/path/name/size/target and reconcile claims.
Maintenance uses new-publication, due-horizon, material fact, or user-currentness
CAS triggers under `output/live/kol_daily/viewpoint_triggers/`; run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py viewpoints` only for
those triggers, preserving the stable report URL/manifest without reminder or
Book action.

The append-only ledger resumes without resending. Report waits and exceptions;
distinguish handoff from completion and report an unchanged blocker once.
Repeated source/stage/code or
acquisition stalls append one exhausted audit with `repair_required=true`;
repetition does not make them `user_action_required`. Reserve that status for
authentication, SMS, CAPTCHA, consent, a user-only fact, or an external effect
whose outcome cannot be reconciled. Timeout, selector drift, schema mismatch,
missing UI path, or repository defect is never by itself `user_action_required`.
User-directed bounded cloud-transfer repair is Agent-owned: bind the claim,
prove target absence, persist `operator_authorized_recovery`, make one third
native click and stop. Never ask user to save or add it to hourly.

## Trading semantic completion at publication

The validated semantic bundle is the only source-analysis pass. Before accepting
publication, require every decision-relevant thesis to carry evidence, horizon,
conditions/triggers, falsifiers, uncertainties and an explicit currentness
evaluation plus typed short-term applicability. The same publication atomically writes the report, viewpoints and
initial evaluations; maintenance appends evaluations/relations. Do not pause for
`daily_trading_source_preparation_input_required` or create a second notes packet.
Trading tasks compose their rebuildable compact projection from these published
records. Empty/unchanged sweeps remain silent and do not refresh history.

When that projection reports a content-hash-bound `classification_backfill`
manifest, the remote writer owns the exact listed viewpoint IDs. Reuse the
already-published viewpoint, evaluation and cited evidence; do not reread every
report body merely to classify time horizon. Append one validated evaluation per
viewpoint with explicit `trading_applicability`. If a genuinely short-term legacy
view lacks triggers, falsifiers or uncertainties, publish a source-bound refined
replacement/superseding viewpoint rather than mutating history or letting the
trading consumer infer the missing fields. Process the exact manifest one
viewpoint at a time under per-object durable receipts and the normal Automation
time budget; unprocessed IDs remain for later exact continuation rather than
being dropped by a count limit. Leave morning and intraday consumers on their
deterministic baseline until the next clean projection.
