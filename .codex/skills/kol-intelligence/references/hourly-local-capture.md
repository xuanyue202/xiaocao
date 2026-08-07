# Hourly Local Capture Node

Local WeChat/broadband node only: capture, exact-publisher discovery, upload,
and credential-free handoff. Remote work follows
[hourly-remote-writer.md](hourly-remote-writer.md).

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep stdin alive for Browser and handoff
JSON. Only the remote capsule importer uses a non-TTY stdin pipe (`tty=false`).

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
`cloud_handoff_published` and authoritative remote `accepted|already_present`
readback. Waiting for a cloud receipt must not end the task, rely on the next
hourly run, rescan WeChat, or create another upload/handoff claim.

If an older process died after publishing `cloud_handoff_published`, do not
rerun the full sweep. Run this read-only response exchange exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-xiaocao-handoff
```

It reads the item ledger, syncs `handoff_ready`, and dispatches only that
published capsule. A dispatch lock prevents duplicates; it does not scan
WeChat, use Browser, advance capture, or re-upload.

If the live source stops before imported official handoffs receive readback,
do not rerun the full sweep. Reconcile `accepted|already_present`, then run this
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

## Remote handoff

For `daily_remote_handoff_input_required`, validate the capsule, then read
[remote-writer-lease.md](remote-writer-lease.md) completely. It prefers current
and automatically reuses a verified writer up to twenty-four hours
old. Never use a stale long-lived task or an approval-waiting task.

Send only capsule fields, never paths or bytes. A `wechat_official_article`
contains a public URL plus identity metadata. Import it idempotently with
`scripts/kol_daily.py import-wechat-official` over a non-TTY stdin pipe
(`tty=false`), one compact line once. If stdin closes before bytes, prove no
receipt, then use one validated temporary JSONL line. Never use a PTY. Restore
XML-rendered `&amp;` to `&` and recompute `handoff_sha256` before import.
After acceptance, the selected task runs
`scripts/kol_daily.py process-wechat-official` once and keeps it alive for
inputs; never rerun the coordinator. Xiaocao uses `scope=post_handoff`. Read
[hourly-remote-writer.md](hourly-remote-writer.md) and reconcile `handoff_id`.

After `accepted|already_present` import readback, immediately return acceptance
to the local runner, then keep the remote task running downstream. Reconcile
before retry; persist host, task, handoff ID, and acceptance. Delay never
creates a handoff.

For a Xiaocao video capsule received after the remote hourly sweep, run only:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py process-xiaocao-handoff
```

Do not rerun the remote multi-source coordinator merely to consume it.

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
