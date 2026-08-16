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
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py stability-acceptance
```

Each run is one sweep; no concrete item is silent. Report concrete waits and
exceptions, distinguishing handoff from completion. Expose only credential-safe
failures. The started task owns repair; do not defer obtainable work.

Report concrete items in a compact Markdown table `对象 | 状态 | 说明`. Prefix
each object with `[视频]` or `[文章]`; never label `Handoff完成` as `全部完成`.

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
WeChat contact, never reads or downloads source-video bytes, starts playback,
or uses Computer Use. It may bind the exact paused player DOM only under
`video-player-safety.md`. Manual import/process commands are reconciliation
surfaces; normal delivery is the mailbox drain at `run` start.

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
and current working directory. The Automation runtime supplies
`CODEX_THREAD_ID`; never synthesize it. The desktop `codex_app__list_threads`
wrapper is not transport: it has stalled before delivery. Use the repository
helper and exclude the current task:

```bash
CODEX_HOME=/Users/xuanyue202/.codex \
CODEX_AUTOMATION_ID=xiaocao-kol-hourly-low-bandwidth-operation \
CODEX_REMOTE_HOST=MacBook-Pro-6.local \
node scripts/codex_peer_gate.js
```

The helper owns app-server, exhausts every `thread/list` cursor, serially reads
matches, verifies host/cwd/Automation/current-task identity, and reads rollout
`task_complete`. Active peer returns `no_op`; complete all-terminal pagination
returns `pass`; incomplete identity/page/response/readback is `repair_required`.

Bind the experimental app-server protocol to its current host identity
(`remoteControl/status/changed.serverName`) and exact canonical cwd, never a
stale project cache. Any helper error is `repair_required` and blocks effects;
never fall back to the hanging wrapper or infer a successful no-op.

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

Use self-hashed Automation evidence; require recent peer-gate readback.
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

For `daily_analysis_input_required`, Read `full-contract.md` completely before
analysis and verify its current SHA-256 against the request. Run
`scripts/kol_semantic_bundle.py` with that request, a judgment-only draft, and
separate market evidence. Return exactly one compact JSON line
`{"bundle_path":"<validated-absolute-json-path>"}`; hand-built or legacy
new-event bundles cannot pass the persisted receipt.

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
