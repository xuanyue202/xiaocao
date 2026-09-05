# Hourly Local Capture Node

Local node: WeChat capture, publisher discovery, upload, and credential-free
handoff.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser/MCP JSON.
Do not inject a Codex task message or remote-import.

For one existing item, run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-item
--source-identity <identity>` in one PTY. Never schedule or widen it.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes, or writes
Book. Do not substitute the remote coordinator.

Report `category`/`code`/`stage`; prefer newest browser-critical, then
`playback_activated`, then oldest `handoff_ready`. Never duplicate an arm.

An `upload_claimed`/`cloud_handoff` wait is nonterminal. The same process must
reach `cloud_handoff_published` plus LiangHuiMCP `created|already_present`
(`Handoff完成`); do not rescan or create another claim.

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

The default Xiaocao playback route is now the native WeChat mini-program. The
old direct-H5 playback route is archived: its code and historical evidence stay
available for compatibility/readback, but it must not be used as a download
fallback.

Use `--xiaoetong-only`; apply `/proxy.pac` only while the service is healthy.
Keep WeChat login/security domains DIRECT and disable the PAC when stopping.
For `#小程序://鹅直播/<token>`, retain contact/time/token, arm the candidate
baseline, then open the original message once. Skip H5 resolution. Bind the
observed candidate ID, app ID, live ID and post-arm time before downloading.
For H5 entries, retain the process for credential-free identity resolution;
H5 is not playback proof.

For an HTTPS share entry, the default launch route is now the verified merchant
Web Link, not chat-window screenshots. Run the emitted `launch_resolver_command`
with `PYTHONPATH=src`. The read-only `scripts/kol_xiaoetong_launch.py` follows the
first-party share redirect, validates the app/live anchor, obtains the provider's
public Web Link representation, ignores the page's mock branch and verifies that
the real `weixin://dl/business/?t=...` ticket embeds that exact replay. The mobile
User-Agent requests the provider's link representation instead of its desktop QR;
it is not login or entitlement. Do not invent tickets, app IDs or page paths.

Use the returned page URL for identity resolution only. After the same task is
armed and `/proxy.pac` is healthy and applied, execute `launch_command` once via
normal macOS URL handling. If the target mini-program is already open, reuse it.
Regenerate tickets at activation; never reuse an old ticket from a report. Read
the Goose Live window, not the unshareable main chat window. Inspect the visible
course-password gate, enter `666` once if present, and observe the exact finite
replay request. Password acceptance may itself start media loading; do not add a
redundant Play click. No hooks, WeChat re-signing, hidden debugging or protection
changes are allowed. Use visible player mute/pause controls when available; the
H5-only DOM mute instruction does not authorize attaching a debugger to WeChat.
If the resolver cannot prove a ticket, use the original visible message entry.
Native `#小程序://...` tokens still use that original-message fallback, not guessed
URL conversion. A launch plan is not playback, download or upload acceptance.

The capture candidate API uses `view=capture`: fresh observed IDs/times only,
without historical title enrichment or remote metadata requests. General display
lists enrich asynchronously with an incremental cache; they cannot bind a source.

1. `resolve_xiaoetong_page`: open the supplied `source_url` only to obtain and
   validate the bound Xiaoetong app/resource anchor. Accept only a bound H5 live
   page (`/vN/course/alive/l_*`) or recorded-video page
   (`/p/course/video/v_*`). For a recorded-video page, also return the numeric
   `media_file_id` from the visible video. Validate MP wrapper app/resource;
   retain only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs.
   Accept `/v2` to `/v4` rotation only for the same app/resource. A bound
   `source_temporarily_unavailable` result is an expected H5 observation here.
2. Let the runner arm the exact source job using that stable identity. Do not
   arm another job when switching from the archived H5 route.
3. `activate_xiaoetong_mini_program`: the Agent owns the native WeChat UI
   action; never ask the user to open or select the replay. Use the reviewed
   Computer Use exception (`cua_repl`) against visible WeChat,
   inspect fresh state, keep one foreground session, one action at a time, and
   read state back after each. Do
   not use hooks, injection, webhooks, storage/cookie reads,
   credential extraction, clipboard loops, or rapid/global-shortcut
   retries. There is no evidence for a magic safe interval: wait only for a
   visible state/sniffer event, and make at most one
   activation attempt per scheduled boundary. If the app requires login,
   SMS/OTP, CAPTCHA, consent, or shows an explicit protection screen, return
   `account_login_required`/the corresponding blocked state and stop; that is
   the only user-action boundary. Enter `666` only at a visible
   course-password gate. Let the target start a media request; no continuous
   playback or fixed wait is required. Return
   `playback_surface=wechat_mini_program`, the exact `source_identity` and
   `live_id`, plus `media_request_observed=true` only when the singleton
   `wx_channels_download` sniffer saw the target request. A current-live
   `liveplay` request alone is not a finite replay; prefer the matching VOD
   `playlist_eof.m3u8` from the mini-program lookback path. Never return signed
   URLs, cookies, keys, or request headers.
4. The source job accepts only the newly observed candidate bound to the exact
   `live_id` and finite playlist. The runner then starts the same
   `type=live_capture`, `compress=true` task and validates the resulting
   `-compressed.mp4`. H5 block-page status must never be reported as download
   success.

If the native mini-program needs login, report `account_login_required` with
`activated=false` and keep the same identity/job. Send one deduplicated user
action even from `resume-source-repair`. See [SOP](xiaoetong-sms-login.md).

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
