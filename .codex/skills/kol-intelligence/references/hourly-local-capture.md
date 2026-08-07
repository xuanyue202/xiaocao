# Hourly Local Capture Node

Use this only on the local WeChat/broadband node: Xiaocao live capture,
exact-publisher official-account discovery, media upload, and credential-free
handoffs. The remote writer follows
[hourly-remote-writer.md](hourly-remote-writer.md); do not perform its work here.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

Use an interactive PTY (`tty=true`) and keep that session alive for Browser and
handoff JSON on the same stdin. Never use non-TTY for `capture-local` or
`capture-wechat-official`; only the remote capsule importer uses `tty=false`.

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`; it never scans Lv, analyzes, publishes, notifies,
or writes Book. Do not substitute the remote coordinator here.

Each invocation performs one sweep. A sweep with no concrete article or video
item is silent. Every concrete item remains reportable while waiting,
unchanged, exceptional, handoff-completed, or fully completed; never imply that
handoff completion is downstream completion. Retryable failures expose only
credential-safe `category`, `code`, and `stage`. Reconcile every already-armed
capture without deleting or duplicating it. The WeChat gate below may arm a
distinct newer preview on the same singleton sniffer so an old wait cannot
starve a live window; never start two sniffers or arm the same preview identity
twice.

Within one sweep, prefer the newest browser-critical item, then the newest
`playback_activated` capture, then the oldest `handoff_ready`; all stay
resumable.

If video upload emits `cloud_handoff_published` after the full sweep has moved
to the official-account source, do not rerun the full sweep. Run this read-only
response exchange exactly once:

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
scans add unseen links. A newly discovered later preview is time-critical and
must not queue behind an older unfinished capture: keep every already-armed
exact job resumable, reuse the one existing sniffer process to arm the newest
exact source job, and mark only older still-unarmed `discovered` previews as
`superseded`. Never replace an armed job, start a second sniffer, or create two
jobs for the same preview identity.

In the same sweep, use the stateless local command
`subscription-updates --within 48h` to scan exactly these registered KOL
publishers:

- `刘少狙击营` (`kol-liushao-jujiying`)
- `A也叫艾利克斯` (`kol-a-alex`)

The combined command repeats `--publisher` for those two exact names and
requires `failures=[]`. Ignore substring matches whose returned publisher is
not exact. On first initialization, baseline older articles and make only the
latest article per publisher eligible; later sweeps add unseen stable article
IDs. Persist only the stable identity, exact publisher/title,
publication/receipt times, normalized public URL, and hashes. The subscription
summary is discovery metadata only and must not cross the handoff or become
article evidence. Do not drive the WeChat GUI or fetch the article locally.

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

Send capsule fields only, never local paths or video bytes. A
`wechat_official_article` capsule
embeds only a credential-free public URL plus identity metadata. Import it
idempotently with `scripts/kol_daily.py import-wechat-official` over a plain
non-TTY stdin pipe (`tty=false`), writing the exact compact JSON as one line
exactly once. If the execution backend closes stdin before any bytes arrive,
first confirm that pre-input failure and absence of a receipt; then create one
validated temporary JSONL line and invoke the importer once with that file as
plain stdin. Never fall back to a PTY. XML wrapper text may display URL `&` as
`&amp;`; restore raw `&` and recompute `handoff_sha256` before import. The
capsule contains no article body, Markdown, summary evidence, or local path.
After an accepted import, the same selected remote task runs
`scripts/kol_daily.py process-wechat-official` exactly once and keeps that
process alive for image/semantic input; it does not rerun the full multi-source
hourly coordinator. Xiaocao video capsules still import with
`scope=post_handoff`. The selected remote task reads
[hourly-remote-writer.md](hourly-remote-writer.md) and reconciles the exact
`handoff_id`.

After `accepted|already_present` import readback, immediately return acceptance
to the local runner, then keep the remote task running downstream. Reconcile
before retry; persist host, task, handoff ID, and acceptance. Delay never
creates a handoff.

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
