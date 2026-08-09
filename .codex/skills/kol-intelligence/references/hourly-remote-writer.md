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

Each run is one sweep; a sweep with no concrete item is silent. Every concrete
item remains reportable while waiting, unchanged, exceptional, handoff-completed,
or fully completed; distinguish handoff from downstream completion. Retryable
failures expose only credential-safe `category`, `code`, and `stage`; a started
task owns repair and exact continuation, so do not defer obtainable work.

Obey seven-state `writer_progress.next_action`; bind input and readback
receipts; retryability never changes owner.

`repair_required` is work for the current Agent, not a user blocker: reconcile
claims/receipts, patch/test/commit/push without user WIP, and continue on the
same stdin. If it exited, never run `run` twice for one slot; use
`resume-mailbox` only for the repaired message. After matching repair closure,
run only `narrow_resume_surface`.

Every source result carries seven-state `writer_progress`. A raw `waiting` result
without an immutable provider `next_poll_not_before` is an internal contract
failure and becomes `repair_required`; diagnostic exceptions never manufacture
an hourly `wait_until` or user blocker. Provider deadlines, auth/CAPTCHA, and
uncertain external effects retain their legal progress states.

This machine is the only KOL writer. It consumes Xiaocao `scope=post_handoff`
and URL-only `wechat_official_article` capsules from LiangHuiMCP; each capsule
is discovery metadata, not the full article. It never scans the local
WeChat contact, never reads or downloads source-video bytes, activates a player,
or uses Computer Use. Manual import/process commands are reconciliation surfaces;
normal delivery is the mailbox drain at `run` start.

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
and current working directory. The desktop `codex_app__list_threads` wrapper is
not transport: it has stalled before delivery. Use the repository helper and
exclude that current task (`CODEX_THREAD_ID`):

```bash
CODEX_HOME=/Users/xuanyue202/.codex \
CODEX_AUTOMATION_ID=xiaocao-kol-hourly-low-bandwidth-operation \
CODEX_REMOTE_HOST=MacBook-Pro-6.local \
node scripts/codex_peer_gate.js
```

The helper starts `codex app-server --stdio`, performs `initialize`/`initialized`,
then serially calls `thread/list` with `{"limit":20}`, exact `cwd`, supported
`sourceKinds`, and `useStateDbOnly=true`, followed by `thread/read` for matching
same-cwd prompts. It verifies host/cwd/Automation identity and reads rollout
events only for the latest `task_complete`. A candidate without that terminal
event is an authoritative active peer: return `no_op` before mailbox access.
All-terminal candidates return `pass`; the helper emits only `pass`, `no_op`, or
`repair_required`, with at most two sequential attempts.

The official protocol does not expose the desktop project UUID; the binding is
the current app-server host identity (`remoteControl/status/changed.serverName`)
plus the exact canonical cwd. Do not substitute a stale project/host cache.
`codex app-server` is documented as experimental/unsupported for production,
so a helper error remains `repair_required` and blocks business effects; never
silently fall back to the hanging wrapper or infer a successful no-op.

Serial gate rule: invoke it with local permissions for the Codex state runtime;
never overlap attempts/requests/readbacks or reuse a stale host. A state-runtime
permission/init or identity/readback failure is control-plane `repair_required`:
it blocks business effects, not repair. Apply 5 Why in this task and never defer
to the next Automation. Do not add a Python global lock, lease, heartbeat,
fencing token, or stale takeover.

If there is no active peer, run `scripts/kol_daily.py run` exactly once. For
each `daily_lianghui_mailbox_input_required`, call the exact operation and
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

`validate-repair` runs the repo test, verifies commit lineage/branch readback,
and persists `RepairValidationReceipt`. `resume-mailbox` defaults to `HEAD`,
requires that receipt for code/contract repairs, and performs exactly one
`get_mailbox_message(message_id, expected_content_sha256)`—never a list.
Missing/changed/acked/unavailable targets fail closed; provider waits reuse a
revision only after their durable TZ-aware deadline is due, with uncertain
effects reconciled before retry.

`convergence-report` is the credential-safe daily report: stable failure codes,
repair required/closed and same-root recurrence, generic waits, internal user
dependency, peer-gate attempts/latency, runner starts, side-effect
reconciliation, duplicate-effect audits, scheduled/clean/business slots, and
exclusions. It reads append-only ledgers and never rewrites failed slots. A
first rollout requires authoritative single-writer readback of one writer,
target revision, protected WIP, dependencies/private config/restored state, and
Automation ownership:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py rollout-readback
```

Use exact self-hashed Automation-interface evidence. Local facts are re-read
and a peer-gate pass from the prior ten minutes is required. Only acceptance
starts the seven-day/50-scheduled-slot window; never backfill business slots.

At provider steps, use installed OpenCLI once with exact identity/version,
bytes, hashes, and receipts. The no-MCP capture rule permits the
repository-designated LiangHui client only after read-only exact-receipt
reconciliation; auth/CAPTCHA/consent or materially incompatible business
outcomes may ask. Reconcile the
handoff/media SHA; latest content is incomplete until analysis, 灰常亮 receipt,
and stable URL.

## Semantic loading gate

For `daily_analysis_input_required`, Read `full-contract.md` completely before
analysis and verify its current SHA-256 against the request. Run
`scripts/kol_semantic_bundle.py` with that request, a judgment-only draft, and
separate market evidence. Return only its validated absolute `bundle_path`;
hand-built/legacy new-event bundles cannot pass the persisted receipt.

For `daily_official_article_image_input_required`, inspect every image once and
write UTF-8 Markdown headed `# 图片信息转写` with index/SHA,
information/decorative status, relevant text/chart/table content, and
uncertainty. Do not copy the body or serialize notes as JSON; write exactly
`{"image_notes_path":"<absolute-md-path>"}` plus a newline. The runner appends
notes to full Markdown before analysis.

Keep stdin open. EOF persists `waiting_semantic_input`, preserving the original
request, evidence SHA, and item claim. The next sweep reuses that exact
request/evidence, skips completed acquisition/transcript work, never replays
publication, notification, or Book effects. Stop that adapter before later
backlog items.

Small downloads are unattended: use `Page.setDownloadBehavior` with a
controlled inbox or one memory-only link bound to the exact provider identity.
A Save prompt is not a user blocker. Only auth, SMS, CAPTCHA, or consent may
ask; never edit ordinary Chrome or a global extension, or issue a second
trigger.

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`,
reviewed publication fields, and a `longitudinal_projection`: `promoted` carries
evidence-bound viewpoints with an initial `current|expired|invalidated|uncertain`
evaluation; `none` carries an empty list and concrete reason. Missing this
decision fails closed rather than defaulting to an empty viewpoint list.

Low-density creates neither report nor reminder. A promoted event gets its
durable 灰常亮 receipt and stable URL before Book KOL-US or reminder effects;
report-only records a no-alert reason, while alert-eligible sends one reminder.
Missing independent verification, no uniquely mapped instrument, low confidence,
or Book KOL-US `no_trade` do not justify report-only when current market
posture/direction is present; retain those limits in the reminder.

## Remote schedule

Codex Automation schedules exactly one remote writer with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=30
```

Use Beijing wall time; omit `DTSTART` and `TZID`. After changes, reopen the
existing Automation and verify its next run and that no duplicate exists. Do
not create, edit, or assume ownership of the local capture Automation here.

## Discovery and recovery

Reuse the configured Lv share `/课程/路西法全套`, handoffs, and receipts. One
sweep reuses one recursive listing, validates identity/version/path/name/size/
target, reconciles claims without replay, and fails closed on ambiguity.
Maintenance uses new-publication, due-horizon, material fact, or user-currentness
CAS triggers under `output/live/kol_daily/viewpoint_triggers/`; run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py viewpoints` only for
those triggers, preserving the stable report URL/manifest without reminder or
Book action.

The append-only ledger resumes without resending. Report every concrete item,
including waits and retryable exceptions; distinguish handoff from downstream
completion and report an unchanged blocker once. Repeated source/stage/code or
acquisition stalls append one exhausted audit with `repair_required=true`;
repetition does not make them `user_action_required`. Reserve that status for
authentication, SMS, CAPTCHA, consent, a user-only fact, or an external effect
whose outcome cannot be reconciled. Timeout, selector drift, schema mismatch,
missing UI path, or repository defect is never by itself `user_action_required`.
