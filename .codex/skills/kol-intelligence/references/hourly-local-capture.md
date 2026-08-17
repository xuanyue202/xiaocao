# Hourly Local Capture Node

Local node: WeChat capture, publisher discovery, upload, and credential-free
handoff. Remote work: [hourly-remote-writer.md](hourly-remote-writer.md).

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser/MCP JSON.
The normal handoff path does not inject a Codex task message or remote-import.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes, or writes
Book. Do not substitute the remote coordinator.

Each sweep reports every item (waits, exceptions, completions), not downstream
completion; expose only safe failure `category`, `code`, and `stage`. Never
duplicate armed captures.

Prefer newest browser-critical, then newest `playback_activated`, then oldest
`handoff_ready`; all stay resumable.

An `upload_claimed`/`cloud_handoff` wait is nonterminal. The same `capture-local` process must
reconcile the exact identity, capture/Netdisk job, and claim through
`cloud_handoff_published` plus authoritative LiangHuiMCP
`created|already_present` (`Handoff完成`). This wait must not end the task,
rescan, defer to the next hour, or create another claim.

A retryable `source_temporarily_unavailable` after an `awaiting_playback` wait
reuses the same capture/job and next-hour deadline; binding, ledger, or receipt
failures alone enter source repair.

If an older process died after `cloud_handoff_published`, do not rerun the full
sweep. Run this read-only exchange exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-handoff
```

It syncs `handoff_ready` from the item ledger and dispatches only that capsule;
its lock prevents duplicates and never scans, advances, or re-uploads.

If official handoffs lack creation readback, reconcile the same mailbox message,
then run this official-only response exchange once, without a full sweep:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-wechat-official
```

Never schedule it hourly or use it before remote ambiguity is resolved.

Use Browser, not Computer Use; `wx_channels_download` alone owns video bytes,
and other nodes receive metadata and receipts.

Before any media upload, read
[opencli-baidu-netdisk-upload.md](opencli-baidu-netdisk-upload.md) completely.

## WeChat and Xiaoetong gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` via local `wechat-cli`;
baseline older links, arm only the newest, reuse the singleton sniffer, preserve
armed jobs, and supersede older unarmed previews.

In the same sweep, use the stateless local command
`subscription-updates --within 48h` to scan exactly these registered KOL
publishers:

- `刘少狙击营` (`kol-liushao-jujiying`)
- `A也叫艾利克斯` (`kol-a-alex`)

Repeat `--publisher` for both and require `failures=[]`; baseline older articles,
then use unseen stable IDs. Persist identity, publisher/title, times, normalized
URL, and hashes only. Never fetch articles locally or drive WeChat GUI.

For `daily_browser_input_required`, keep the same process alive and use
`browser`, never Computer Use:

1. `resolve_xiaoetong_page`: open the supplied `source_url`; return the current
   URL and page state. Accept only a bound H5 live page
   (`/vN/course/alive/l_*`) or recorded-video page
   (`/p/course/video/v_*`). For a recorded-video page, also return the numeric
   `media_file_id` bound to the visible video element; the capture layer accepts
   only a new trusted media candidate whose URL path binds that exact file ID.
   Convert an MP wrapper to H5 only after validating its embedded app/resource
   identity; strip share parameters.
2. Let the runner arm that exact H5 source job.
3. `activate_xiaoetong_playback`: refresh; enter `666` only at a visible
   course-password gate. If waiting/live-only/generating, return `activated=false`.
   Once `<video>` exists, set/read `muted=true`, `volume=0` via page control
   before playback; hidden controls use tab `cdp`/`Runtime.evaluate`. Reapply
   after refresh/rebuild, prove two advancing `currentTime` samples, then
   return `activated=true` and bound URL/password state. An app/resource
   redirect to `<app_id>.block.xiaoeeye.com` is
   `source_temporarily_unavailable` with both booleans false; return its URL for
   retry. If the same page first lands on a generic Xiaoetong unavailable or
   personal-center shell, derive that exact app/resource block URL by replacing
   the `.h5.xiaoeknow.com` host suffix with `.block.xiaoeeye.com`, navigate the
   same tab to it, and return the resulting bound block URL. Never report the
   state for an unrelated URL or use it for another identity.
4. For a recorded-video download, `resolve_xiaoetong_media_url` returns only
   the currently observed signed HTTPS m3u8 URL whose host and path bind the
   supplied `media_file_id`. The runner uses this short-lived value in memory
   for the exact download call; never return cookies or DRM keys, and never
   persist the signature in Xiaocao manifests or append-only ledgers.

Login: keep tab; report account_login_required with activated/password_used=false;
never enter 666. See [SOP](xiaoetong-sms-login.md).

`密码666` text is not a visible gate. Do not inspect cookies, storage, or
credentials. An `awaiting_playback` job keeps the same identities and rechecks
the bound page next hour until playable; never wait inside one sweep or create a
replacement job. Later capture, cleanup, upload, and handoff reconcile without
Browser.

## LiangHuiMCP handoff

On `daily_lianghui_mailbox_input_required`, keep the process alive and call the
named LiangHuiMCP operation with exact `arguments`:

- `send_mailbox_message`: one compact JSON line with `operation`, `outcome`,
  and authoritative `receipt`.
- `get_mailbox_message`: one compact JSON line with `operation` and the exact
  structured message as `message`.

Never reinterpret or reconstruct receipts; mailbox errors fail closed. Send only
credential-free capsule fields, never local paths or media bytes. Official
articles contain normalized public URL plus identity metadata; video capsules
contain post-handoff metadata and hashes only.

`send_mailbox_message` uses mailbox `kol.handoff`, type `xiaocao.kol_handoff`,
schema `1`, and the same `handoff_id` as message and correlation IDs. Only
authoritative `created|already_present` with the exact hash is `Handoff完成`;
no remote task discovery, task selection, or `send_message_to_thread` participates.

Mailbox `subject` identifies the item: video `[视频] <media_basename stem>`;
article `[文章] <exact article title>`. Generic `[视频] 小草直播` fails the
pre-send gate. Never rewrite MCP arguments. Repair sender/tests before first
send and resume the same job; after creation, keep the immutable message and
apply repairs only to future handoffs.

Next sweep, use `get_mailbox_message` to reconcile each locally receipted but
unobserved handoff by exact mailbox ID and the same
`handoff_id`. `pending` remains `Handoff完成`. A bound `acked` message with its
authoritative ack receipt becomes `全部完成`. A timeout or ambiguous response
never authorizes another message ID or changed content; retry only the same
idempotency key after reconciling its exact readback.

## Local schedule

Codex Automation schedules exactly one local capture task with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0
```

Use Beijing wall time; omit `DTSTART`/`TZID`; do not run 23:01–06:59. Reopen a
changed Automation, verify next run/no duplicate, and never alter the remote writer.

The append-only local ledger resumes only unfinished capture/upload/handoff
work. A restart or replay reconciles existing claims and never repeats a cloud
upload with an uncertain side effect.
