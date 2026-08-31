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

Report every item with safe `category`/`code`/`stage`. Prefer newest
browser-critical, newest `playback_activated`, then oldest `handoff_ready`;
never duplicate an armed capture.

An `upload_claimed`/`cloud_handoff` wait is nonterminal. The same `capture-local`
process must reconcile its identity, jobs, and claim through
`cloud_handoff_published` plus LiangHuiMCP `created|already_present`
(`Handoff完成`); it must not end the task, rescan, or create another claim.

A retryable `source_temporarily_unavailable` after an `awaiting_playback` wait
reuses the same capture/job and next 20-minute deadline; binding, ledger, or receipt
failures alone enter source repair.

After `cloud_handoff_published` process death, do not rerun the full sweep; run:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-handoff
```

It dispatches only ledger-bound `handoff_ready`; never scan or re-upload.

For an official handoff missing creation readback, reconcile its mailbox message,
then run once without a full sweep:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-wechat-official
```

Never schedule it or run before remote ambiguity clears. Use Browser, not
Computer Use; only `wx_channels_download` owns video bytes. Before upload read
[opencli-baidu-netdisk-upload.md](opencli-baidu-netdisk-upload.md).

## WeChat and Xiaoetong gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` via local `wechat-cli`;
baseline older links, arm only the newest, reuse the singleton sniffer, preserve
armed jobs, and supersede older unarmed previews.

Also run stateless `subscription-updates --within 48h` for exactly:

- `刘少狙击营` (`kol-liushao-jujiying`)
- `A也叫艾利克斯` (`kol-a-alex`)

Repeat `--publisher`, require `failures=[]`, baseline old articles, and persist
only stable identity, metadata, normalized URL, and hashes. Never fetch locally.

For `daily_browser_input_required`, retain the process and use `browser`, never
Computer Use. Claim the logged-in Codex 侧边栏浏览器 Xiaoetong tab; use
Edge/OpenCLI only when durable job state names that existing session.

1. `resolve_xiaoetong_page`: open the supplied `source_url`; return the current
   URL and page state. Accept only a bound H5 live page
   (`/vN/course/alive/l_*`) or recorded-video page
   (`/p/course/video/v_*`). For a recorded-video page, also return the numeric
   `media_file_id` from the visible video. Validate MP wrapper app/resource;
   retain only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs.
   Accept `/v2` to `/v4` rotation only for the same app/resource.
2. Let the runner arm that exact H5 source job.
3. `activate_xiaoetong_playback`: refresh; enter `666` only at a visible
   course-password gate. If waiting/live-only/generating, return `activated=false`.
   Once `<video>` exists, set/read `muted=true`, `volume=0`; hidden controls use
   tab `cdp`/`Runtime.evaluate`. Prove two advancing `currentTime` samples.
   A same-app/resource block redirect is `source_temporarily_unavailable` with
   both booleans false. From a personal-center shell, derive only that bound
   `.block.xiaoeeye.com` path. Never bind an unrelated URL.
4. For a recorded-video download, `resolve_xiaoetong_media_url` returns only
   the current signed HTTPS m3u8 bound to `media_file_id`; keep it in memory and
   never return cookies/DRM keys or persist its signature.

Login: keep the 侧边栏浏览器 tab; report account_login_required with both booleans
false. Send one deduplicated 企业微信 current-video action even from
`resume-source-repair`. See [SOP](xiaoetong-sms-login.md).

`密码666` text is not a visible gate. Do not inspect cookies, storage, or
credentials. `awaiting_playback` keeps identities and rechecks at the next
20 分钟 boundary; never replace the job. Later stages need no Browser.

## LiangHuiMCP handoff

On `daily_lianghui_mailbox_input_required`, keep the process alive and call the
named LiangHuiMCP operation with exact `arguments`:

- `send_mailbox_message`: one compact JSON line with `operation`, `outcome`,
  and authoritative `receipt`.
- `get_mailbox_message`: one compact JSON line with `operation` and the exact
  structured message as `message`.

Never reconstruct receipts. Send credential-free metadata/hashes only, no local
paths or bytes.

`send_mailbox_message` uses mailbox `kol.handoff`, type `xiaocao.kol_handoff`,
schema `1`, and the same `handoff_id` as message and correlation IDs. Only
authoritative `created|already_present` with the exact hash is `Handoff完成`;
no remote task discovery, task selection, or `send_message_to_thread` participates.

Subject is `[视频] <media_basename stem>` or `[文章] <exact article title>`;
generic `[视频] 小草直播` fails. Never rewrite arguments or a created message.

Next sweep, `get_mailbox_message` reconciles exact mailbox ID and same
`handoff_id`: `pending` is `Handoff完成`; bound `acked` is `全部完成`. Ambiguity
authorizes no new ID/content; reconcile then retry the same idempotency key.

## Local schedule

Codex Automation schedules exactly one local capture task with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22;BYMINUTE=0,20,40
```

Use Beijing wall time; omit `DTSTART`/`TZID`; do not run 23:00–06:59. Reopen a
changed Automation, verify next run/no duplicate, and never alter the remote writer.

The append-only local ledger resumes only unfinished capture/upload/handoff
work. A restart or replay reconciles existing claims and never repeats a cloud
upload with an uncertain side effect.
