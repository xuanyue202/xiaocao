# Hourly Remote Writer

Use only on Ticket 07's remote sole-writer node. Local WeChat follows
[hourly-local-capture.md](hourly-local-capture.md). Do not read
`full-contract.md` unless the semantic or post-handoff work is ready.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py run
```

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py status
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py audit
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py convergence-report
```

Each run is one sweep. A sweep with no concrete item is silent.
Every concrete item remains reportable while waiting, unchanged, exceptional,
handoff-completed, or fully completed; never imply that handoff completion is
downstream completion. Retryable failures expose only credential-safe
`category`, `code`, and `stage`. A started task owns recoverable items through
repair and exact continuation; do not defer obtainable work.

Obey seven-state `writer_progress.next_action`; bind input and readback
receipts; retryability never changes owner.

`repair_required` is work for the current Agent, not a user blocker: reconcile
claims/receipts, patch regressions, validate, commit, and push without user WIP. Continue on
the same stdin when possible. If it exited, never run `run` twice for one slot;
recheck peers/receipts and use `resume-mailbox` for only the repaired message.
After matching repair closure, run only `narrow_resume_surface`.

Every source result must carry the seven-state `writer_progress` object. A raw
`waiting` result without an immutable provider `next_poll_not_before` is an
internal contract failure and becomes `repair_required`; known diagnostic
exceptions never manufacture an hourly `wait_until` or a user blocker. Provider
deadlines, authentication/CAPTCHA, and uncertain external effects retain their
own legal progress states.

This machine is the only KOL writer. It consumes Xiaocao `scope=post_handoff`
capsules and URL-only `wechat_official_article` capsules from LiangHuiMCP. The
capsule is discovery metadata, not the full article. It never scans the local
WeChat contact and never reads or downloads source-video bytes, activates a
player, or uses Computer Use. The manual `import-wechat-official`,
`process-wechat-official`, and `process-xiaocao-handoff` commands remain
reconciliation surfaces only; normal hourly delivery is the mailbox drain at
the start of `run`.

When reconciling an already imported official-account capsule outside the
normal hourly path, process only that inbox with `PYTHONPATH=src
.venv/bin/python scripts/kol_daily.py process-wechat-official`. Run it exactly
once and keep the same process alive for image/semantic input; do not rerun the
full `run` command merely to pick up the handoff.

For a late Xiaocao video capsule, process only imported post-handoff state with
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py process-xiaocao-handoff`.
Run once and keep it alive for input; do not rerun the full `run` command.

## Active-peer gate and LiangHuiMCP drain

A **peer task** is another Codex task with the same Automation ID, current host,
and current working directory. Before Python, call standalone `list_threads`
with `{"limit":20}`. Read active same-host/cwd candidates using `read_thread`
with `{"threadId":"<candidate-id>","hostId":"<current-host>",
"turnLimit":3,"includeOutputs":false}` until the in-progress turn matches this
run's Automation ID and prompt metadata. Ignore titles and exclude that current
task. An active/needs-attention peer owns continuation: exit successfully
without mailbox access.

Bind each list to `hostId`/`projectId`/`cwd`; never reuse `hostId` from
memory/earlier slots. If a task's tuple changes, discard
candidates and retry once with the fresh binding; old-host readback fails. Apply
5 Why; task-list failure handling blocks business effects, not repair. Use two
lists (initial + fresh retry); both fail => `repair_required`, no third duplicate.
Never defer to the next Automation.
Do not add a Python global lock, lease, heartbeat, fencing token, or stale takeover.

If there is no active peer, run `scripts/kol_daily.py run` exactly once. For
each `daily_lianghui_mailbox_input_required`, call the exact operation and
arguments, then return one compact JSON line to the same process:

- `list_mailbox_messages`: return `{"operation":"list_mailbox_messages",
  "page":<exact structuredContent>}`. The runner asks for pending messages,
  oldest first, up to 50 per page, and follows every cursor.
- `ack_mailbox_message`: return `{"operation":"ack_mailbox_message",
  "outcome":<tool outcome>,"receipt":<exact receipt>}`.

The runner validates mailbox `kol.handoff`, message type
`xiaocao.kol_handoff`, schema version `1`, exact family/message/content-hash
bindings, then imports and processes each message through its existing
post-handoff business pipeline. It maintains this run's
`attempted_message_ids`. After a batch, query again and process only new
eligible messages. Do not repeat an unchanged wait inside one drain. If the
process exits, call `resume-mailbox` for that message when due in this task. Call
`ack_mailbox_message` only after that exact message has completed every
downstream business effect and durable receipt. Authoritative `acked` or
`already_acked` is reported as `全部完成`; handoff creation alone is never
reported as downstream completion.

### Narrow repair resume

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py validate-repair --mailbox-message-id <exact-64-hex-message-id>
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py resume-mailbox \
  --mailbox-message-id <exact-64-hex-message-id> [--repair-revision <exact-40-hex-commit>]
```

`validate-repair` runs the repo test, verifies commit
lineage/branch readback, and persists `RepairValidationReceipt`.
`resume-mailbox` defaults to `HEAD`, requires that receipt for code or
contract repairs, and performs exactly one
`get_mailbox_message(message_id, expected_content_sha256)`—never a list.
Missing/changed/acked/unavailable targets fail closed pre-processor.
Provider waits may reuse a revision only after their durable TZ-aware
poll deadline is due; reconcile uncertain effects before retry.

`convergence-report` is the credential-safe daily report. It aggregates stable
failure codes, repair required/closed and same-root recurrence, generic waits,
internal user dependency, peer-gate attempts/latency, runner starts,
side-effect reconciliation, duplicate-effect audits, scheduled/clean/business
slots, and explicit exclusions. It reads append-only ledgers and never deletes
or rewrites a failed slot. A first rollout may be recorded only after the
authoritative single-writer readback proves one writer, the target revision,
protected WIP, dependencies/private config/restored state, and Automation
ownership:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py rollout-readback
```

The command consumes one credential-safe JSON line on stdin and starts the
seven-day/50-scheduled-slot stability window only after that readback is
accepted; it never backfills historical business slots.

At provider steps, use installed OpenCLI once and bind exact identity/version,
bytes, hashes, and receipts. The no-MCP capture rule permits the
repository-designated LiangHui client only after read-only exact-receipt
reconciliation; CAPTCHA/auth/consent or materially incompatible business
outcomes may ask. Reconcile the exact handoff/media SHA before advancing;
latest content is incomplete until analysis, 灰常亮 receipt, and stable URL.

## Semantic loading gate

For `daily_analysis_input_required` in the same process:

1. Read the request and locate its evidence and bindings.
2. Read `full-contract.md` completely before analysis.
3. Reopen immutable evidence and verify its current SHA-256 against the request.
4. If reusable knowledge will be written, also read `durable-knowledge.md`
   completely.
5. Create complete evidence-bound Ticket 01 JSON beside runtime artifacts.
6. Write exactly `{"bundle_path":"<absolute-json-path>"}` followed by a
   newline to the same process.

For `daily_official_article_image_input_required`, inspect every image once and
write UTF-8 Markdown headed `# 图片信息转写` with each index/SHA,
information/decorative status, relevant text/chart/table content, and
uncertainty. Do not copy the body or serialize note content as JSON. Then write
exactly `{"image_notes_path":"<absolute-md-path>"}` followed by a newline to
the same process. The runner appends notes to full Markdown before analysis.

Keep stdin open. EOF persists `waiting_semantic_input`, preserving the original
request, evidence SHA, and item claim. The next sweep reuses that exact
request/evidence, skips completed acquisition/transcript work, and never
replays publication, notification, or Book effects. Stop that adapter before
later backlog items.

Small downloads are unattended: use `Page.setDownloadBehavior` with a
controlled inbox or bind one memory-only link to the exact provider identity.
A Save prompt is not a user blocker. Only auth, SMS, CAPTCHA, or consent may
ask; never edit ordinary Chrome/a global extension or issue a second trigger.

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`, and
reviewed natural-Chinese publication fields. Every promoted item also decides
`longitudinal_projection`: `promoted` carries evidence-bound viewpoints and an
initial `current|expired|invalidated|uncertain` evaluation; `none` carries an
empty list and a concrete reason. Missing this decision fails closed rather
than defaulting to an empty viewpoint list.

Low-density creates neither report nor reminder. A promoted event gets its
durable 灰常亮 receipt and stable URL before Book KOL-US or reminder effects;
report-only records a no-alert reason, while alert-eligible sends one reminder.
Missing independent verification, no uniquely mapped instrument, low
confidence, or Book KOL-US `no_trade` do not justify report-only when current
market posture or direction is present; retain those limits in the reminder.

## Remote schedule

Codex Automation schedules exactly one remote writer with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=30
```

Use Beijing wall time; omit `DTSTART` and `TZID`. After changes, reopen the
existing Automation and verify its next run and that no duplicate exists. Do
not create, edit, or assume ownership of the local capture Automation here.

## Discovery and recovery

Reuse the configured Lv share, `/课程/路西法全套`, handoffs, and receipts. One
sweep reuses one complete recursive listing and validates identity/version/
path/name/size/target before advancing. Preserve safe diagnostics, reconcile
claims without replay, and fail closed on ambiguous evidence. Maintenance uses
new-publication, due-horizon, material fact, or user currentness CAS triggers
under `output/live/kol_daily/viewpoint_triggers/`; run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py viewpoints` only for those
triggers, preserving the stable report URL/manifest with no reminder or Book
action.

The append-only ledger resumes without resending. Report every concrete item,
including waits and retryable exceptions; distinguish handoff from downstream
completion. Report an unchanged blocker only once.
Repeated source/stage/code or acquisition stalls append one
exhausted audit with `repair_required=true`; repetition does not make them
`user_action_required`. Reserve that status for authentication, SMS, CAPTCHA,
consent, a fact only the user can provide, or an external side effect whose
outcome cannot be reconciled. A timeout, selector drift, schema mismatch,
missing internal UI path, or repository defect is never by itself
`user_action_required`.
