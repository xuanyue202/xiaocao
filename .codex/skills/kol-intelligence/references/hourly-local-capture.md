# Hourly Local Capture Node

Local WeChat/broadband node only: capture, exact-publisher discovery, upload,
and credential-free handoff. Remote work follows
[hourly-remote-writer.md](hourly-remote-writer.md).

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser and
LiangHuiMCP request/response JSON. The normal handoff path does not inject a
Codex task message and does not invoke the remote capsule importer directly.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes, notifies,
or writes Book. Do not substitute the remote coordinator here.

Each invocation performs one discovery sweep. A sweep with no concrete article
or video item is silent. Every concrete item remains reportable while waiting,
unchanged, exceptional, handoff-completed, or fully completed. Handoff is not
downstream completion. Retryable failures expose only credential-safe
`category`, `code`, and `stage`. Reconcile armed captures; never duplicate them.

Within one sweep, prefer the newest browser-critical item, then the newest
`playback_activated` capture, then the oldest `handoff_ready`; all stay
resumable.

An `upload_claimed` or other `cloud_handoff` wait is nonterminal. After the full
discovery sweep, the same `capture-local` process must keep reconciling that
exact identity, capture job, Netdisk job, and upload claim until it receives
`cloud_handoff_published` and authoritative LiangHuiMCP
`created|already_present` readback. That creation receipt is `Handoff完成`.
Waiting for a cloud receipt must not end the task, rely on the next
hourly run, rescan WeChat, or create another upload/handoff claim.

If an older process died after publishing `cloud_handoff_published`, do not
rerun the full sweep. Run this read-only response exchange exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-handoff
```

It reads the item ledger, syncs `handoff_ready`, and dispatches only that
published capsule. A dispatch lock prevents duplicates; it does not scan
WeChat, use Browser, advance capture, or re-upload.

If the live source stops before official handoffs receive creation readback,
do not rerun the full sweep. Reconcile the same mailbox message, then run this
official-only response exchange exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-wechat-official
```

Never schedule this as another hourly runner or use it before remote ambiguity
is resolved.

The local adapter may use Browser, never Computer Use, to activate the bound
player. `wx_channels_download` alone owns video bytes and inline compression.
The coordinator and remote control plane receive only metadata, receipts, and
the self-hashed handoff capsule.

Before any media upload, read
[opencli-baidu-netdisk-upload.md](opencli-baidu-netdisk-upload.md) completely.

## WeChat and Xiaoetong gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` through local
`wechat-cli`. First scan baselines older links and arms only the newest; later
scans add unseen links. A newer preview may use the existing singleton sniffer;
keep armed jobs resumable and supersede only older unarmed previews. Never
replace an armed job or duplicate a preview identity.

In the same sweep, use the stateless local command
`subscription-updates --within 48h` to scan exactly these registered KOL
publishers:

- `刘少狙击营` (`kol-liushao-jujiying`)
- `A也叫艾利克斯` (`kol-a-alex`)

Repeat `--publisher` for both exact names and require `failures=[]`. Baseline
older articles once; later use unseen stable IDs. Persist only identity,
publisher/title, times, normalized public URL, and hashes. Summary metadata is
not article evidence. Never fetch the article locally or drive WeChat GUI.

For `daily_browser_input_required`, keep the same process alive and use
`browser`, never Computer Use:

1. `resolve_xiaoetong_page`: open the supplied `source_url`; return the current
   URL and page state. Convert an MP wrapper to H5 only after validating its
   embedded app/resource identity; strip share parameters.
2. Let the runner arm that exact H5 source job.
3. `activate_xiaoetong_playback`: refresh; enter `666` only at a visible
   password gate. If waiting/live-only/generating, return its visible state with
   `activated=false`. If playable, set and read back `muted=true`, `volume=0`
   (reapply after refresh/navigation), start it, and prove advancing media time.
   Only then return `activated=true`, bound URL, and password-use state.

Message text such as “密码666” is not evidence; visible page state is. Never
read cookies, storage, or credentials. An `awaiting_playback` source job keeps
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

At the start of the next local sweep, use `get_mailbox_message` to reconcile
every locally receipted but unobserved handoff by exact mailbox ID and the same
`handoff_id`. `pending` remains `Handoff完成`. A bound `acked` message with its
authoritative ack receipt becomes `全部完成`. A timeout or ambiguous response
never authorizes another message ID or changed content; retry only the same
idempotency key after reconciling its exact readback.

## Local schedule

Codex Automation schedules exactly one local capture task with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0
```

Use Beijing wall time; omit `DTSTART` and `TZID`. Do not run 23:01–06:59. After
any change, reopen the existing Automation and verify its next run and that no
duplicate exists. Do not create, edit, or assume ownership of the remote writer
Automation from this node.

The append-only local ledger resumes only unfinished capture/upload/handoff
work. A restart or replay reconciles existing claims and never repeats a cloud
upload with an uncertain side effect.
