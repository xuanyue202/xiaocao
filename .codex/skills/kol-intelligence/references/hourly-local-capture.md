# Hourly Local Capture Node

Local node: WeChat capture, publisher discovery, upload, and credential-free
handoff.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser/MCP JSON.
The normal handoff path does not inject a Codex task message or remote-import.

For one existing item, run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-item
--source-identity <identity>` in one PTY. Never schedule or widen it.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes, or writes
Book. Do not substitute the remote coordinator.

Report `category`/`code`/`stage`; prefer newest browser-critical, then
`playback_activated`, then oldest `handoff_ready`. Never duplicate an arm.

An active `downloading` or `upload_claimed`/`cloud_handoff` wait is nonterminal
and must not end the task. The runner follows these stages in the same PTY;
do not kill it when the initial JSON says `waiting`.
Keep the same `capture-local` process alive until `cloud_handoff_published` plus
LiangHuiMCP `created|already_present` (`Handoff完成`); do not rescan or create
another claim.

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

The only Xiaocao playback route is the native WeChat mini-program. Direct-H5
playback/login code and its SOP were removed; historical evidence remains in
Git and ledgers. H5 must not be used as a download fallback.

Use `--xiaoetong-only`; apply `/proxy.pac` only while the service is healthy.
Keep WeChat login/security domains DIRECT and disable the PAC when stopping.

On `daily_browser_input_required`, keep stdin open in the same process and return
the requested credential-free JSON to that PTY.

Before native launch resolution, `resolve_xiaoetong_page`,
`activate_xiaoetong_mini_program`, or continuation/acceptance of an existing native
capture, read [hourly-local-native-capture.md](hourly-local-native-capture.md)
completely. This stage reference is mandatory for resumed jobs too: it owns
sniffer readiness, verified launch, exact-source media binding, and post-download
cleanup/receipt acceptance. No-update discovery needs only this entry reference.

A user request to prepare but wait for confirmation is an execution gate: keep
the Automation PAUSED and run offline checks only until explicit confirmation.
`Handoff完成` is not remote `全部完成`; report each from its actual bound receipt.

If the native WeChat client visibly says phone login is required, report
`wechat_client_login_required` with `activated=false` and keep the same
identity/job. This is not a Xiaoetong account-login or course-password state.
Send one deduplicated user action even from `resume-source-repair`.

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
