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

A task-list/readback failure blocks business effects, not repair. Apply 5 Why,
fix arguments, and retry standalone now. If still unavailable, keep diagnosing
as `repair_required`; never defer to the next Automation or ask the user. Do
not add a Python global lock, lease, heartbeat, fencing token, or stale takeover.

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

After fixing, testing, committing, and pushing a repository failure, continue
the same item in the current Agent task with:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py resume-mailbox \
  --mailbox-message-id <exact-64-hex-message-id> \
  --repair-revision <exact-40-hex-commit>
```

Reapply the peer gate and keep stdin open. The first repaired continuation
requires the prior wait, same content hash, and a new repair revision; it
processes no other message. A contract/error wait may not reuse that revision.
An async provider wait may reuse it only when the durable wait includes an
explicit timezone-aware `next_poll_not_before` and that deadline is due.
Missing/acked/changed targets fail closed. Reconcile `uncertain` effects before
retry. Resume a due provider wait now.

For an official item, run installed OpenCLI once: `weixin download`, images,
background Chrome, and JSON. Require an item-local file, exact
publisher/title/time, complete UTF-8 body/images, bytes, and hashes.
Combine OpenCLI's verification UI/path/node signals with `请输入验证码`; CAPTCHA
stops for same-session verification without HTTP/MCP retry.

The no-MCP capture rule bans capture retrieval beyond OpenCLI. After read-only
exact-receipt reconciliation, the repository-designated LiangHui client is
allowed only for authorized context, publication, reminders, and receipts.
Resolve conflicts from business invariants; ask only for auth/consent/CAPTCHA,
new authority, or materially incompatible business outcomes.

For an imported Xiaocao handoff, reconcile the exact `handoff_id` and media
SHA-256 before advancing. Latest Xiaocao or Lv content is incomplete until its
identity/version has analysis plus a 灰常亮 receipt and stable URL. Preserve the
concrete stage, reconciliation result, and `next_poll_not_before`; use bounded
cloud-save/native-click recovery from `full-contract.md` only at the relevant
provider step.

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

Reuse the configured Lv share, `/课程/路西法全套`, Xiaocao handoffs, and their
receipts. One sweep reuses one complete recursive Lv listing; validate every
identity/version/path/name/size/target and advance the cursor only after the
full scan. Parent mtime or incidental `已失效` text is not proof.

Discovery-only OpenCLI failures may reopen and retry one full read. Preserve
safe `category/code/stage`; authority ends before any side effect. Reconcile
claims and isolate failures without replay. Apply `full-contract.md` PDF
precedence, owner-copy, OCR, and claim-routing rules only when that item reaches
the relevant stage. Unsafe or ambiguous evidence fails closed.

Route Lv claims, not media types: `会员直播` follows current event gates;
reusable `底层逻辑` is normally report-only `authority=0` knowledge with no Book
row. Mixed claims stay one report and only current claims authorize effects.

Put new-publication, due-horizon, material fact, or user currentness requests in
`output/live/kol_daily/viewpoint_triggers/*.json`; maintenance uses CAS and
creates no reminder or Book action.
Use `operation=initial_projection` plus `trigger=user_request` only for a
reviewed report-only history that still has no viewpoints. Run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py viewpoints` to process
only these maintenance triggers without scanning sources. It must preserve the
stable report URL and prior manifest, and it never creates a reminder or Book
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
