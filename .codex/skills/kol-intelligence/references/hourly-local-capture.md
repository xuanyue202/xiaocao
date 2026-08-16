# Hourly Local Capture Node

Local node: WeChat capture, publisher discovery, upload, and credential-free
handoff. Remote work follows
[hourly-remote-writer.md](hourly-remote-writer.md).

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser/MCP JSON.
The normal handoff path does not inject a Codex task message or call the remote importer.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes or writes
Book. Do not substitute the remote coordinator.

Each invocation performs one sweep. Report every concrete item, including waits,
exceptions and completions; handoff is not downstream completion. Expose only
safe failure `category`, `code`, and `stage`. Never duplicate armed captures.

Prefer the newest browser-critical item, then newest `playback_activated`, then
oldest `handoff_ready`; all stay resumable.

An `upload_claimed`/`cloud_handoff` wait is nonterminal. The same `capture-local` process must
reconcile the exact identity, capture/Netdisk job and claim through
`cloud_handoff_published` and authoritative LiangHuiMCP
`created|already_present` (`Handoff完成`). This wait must not end the task, rescan,
defer to the next hour, or create another upload/handoff claim.

If an older process died after publishing `cloud_handoff_published`, do not
rerun the full sweep. Run this read-only response exchange exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-handoff
```

It syncs `handoff_ready` from the item ledger and dispatches only that capsule.
Its lock prevents duplicates; it never scans, advances capture, or re-uploads.

If official handoffs lack creation readback, reconcile the same mailbox message,
then run this official-only response exchange once, without a full sweep:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-wechat-official
```

Never schedule it hourly or use it before remote ambiguity is resolved.

Use Browser, not Computer Use. `wx_channels_download` alone owns video bytes;
other nodes receive metadata and receipts.

Before any media upload, read
[opencli-baidu-netdisk-upload.md](opencli-baidu-netdisk-upload.md) completely.

## WeChat and Xiaoetong gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` via local `wechat-cli`.
Baseline older links and arm only the newest; later add unseen links. Reuse the
singleton sniffer, preserve armed jobs, and supersede only older unarmed previews.

In the same sweep, use the stateless local command
`subscription-updates --within 48h` to scan exactly these registered KOL
publishers:

- `刘少狙击营` (`kol-liushao-jujiying`)
- `A也叫艾利克斯` (`kol-a-alex`)

Repeat `--publisher` for both and require `failures=[]`. Baseline older articles;
later use unseen stable IDs. Persist identity, publisher/title, times, normalized
public URL and hashes only. Never fetch articles locally or drive WeChat GUI.

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
credentials. An `awaiting_playback` source job keeps
the same capture/source identities and rechecks the same bound page on the next
hourly sweep until it becomes playable; never wait inside one sweep or create a
replacement job. Later capture, artifact, proxy cleanup, upload, and handoff
stages reconcile without Browser.

## LiangHuiMCP handoff

The runner emits `daily_lianghui_mailbox_input_required`. Keep the same process
alive and call the named LiangHuiMCP operation with its exact `arguments`:

- `send_mailbox_message`: return one compact JSON line containing
  `operation`, `outcome`, and the authoritative `receipt`.
- `get_mailbox_message`: return one compact JSON line containing `operation`
  and the tool's exact structured message as `message`.

Do not reinterpret, trim, or reconstruct a tool receipt. A mailbox operation
error fails closed. Send only the credential-free capsule fields, never local
paths or media bytes. A `wechat_official_article` contains only a normalized
public URL plus identity metadata. Xiaocao video capsules contain post-handoff
metadata and hashes only.

`send_mailbox_message` uses mailbox `kol.handoff`, message type
`xiaocao.kol_handoff`, schema version `1`, and the same `handoff_id` as both
message ID and correlation ID. Only authoritative `created|already_present`
with the exact content hash is `Handoff完成`; no remote task discovery, task
selection, or `send_message_to_thread` participates in this terminal.

Mailbox `subject` must identify the item: video uses
`[视频] <media_basename stem>` (for example,
`[视频] 20260807 大师班专场(晚18:00开播)-compressed`); article uses
`[文章] <exact article title>`. Generic `[视频] 小草直播` fails the pre-send gate.
Never rewrite emitted MCP arguments. Before first send, repair the sender plus
tests and resume the same job; after a creation receipt, keep the immutable
message and apply the repair only to future handoffs.

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

Use Beijing wall time; omit `DTSTART`/`TZID`. Do not run 23:01–06:59. Reopen a
changed Automation, verify its next run/no duplicate, and never alter the remote
writer Automation here.

The append-only local ledger resumes only unfinished capture/upload/handoff
work. A restart or replay reconciles existing claims and never repeats a cloud
upload with an uncertain side effect.
