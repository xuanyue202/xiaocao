# Hourly Local Capture Node

Use this contract only on the local WeChat/broadband node. Its entire hourly
scope is Xiaocao live discovery/capture plus exact-publisher WeChat official-
account discovery, cloud upload where media exists, and credential-free
handoffs. The remote writer follows
[hourly-remote-writer.md](hourly-remote-writer.md); do not perform its work here.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

`capture-local` runs only `xiaocao_wechat_live` and
`wechat_official_accounts`. It never scans Lv, consumes a remote handoff,
analyzes, publishes, notifies, or writes Book. Do not substitute the remote
coordinator command on this machine.

Each invocation performs one sweep. Normal no-update and healthy waiting are
silent. Retryable failures expose only credential-safe `category`, `code`, and
`stage`. Reconcile an unfinished capture before creating another one, and never
start two sniffers.

The local adapter may use Browser, never Computer Use, to activate the bound
player. `wx_channels_download` alone owns video bytes and inline compression.
The coordinator and remote control plane receive only metadata, receipts, and
the self-hashed handoff capsule.

## WeChat and Xiaoetong gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` through local
`wechat-cli`. First scan baselines older links and arms only the newest; later
scans add unseen links. Never replace an unfinished capture.

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
3. `activate_xiaoetong_playback`: refresh and play. Enter default `666` only
   when the page visibly presents a password gate. After media requests begin,
   return the bound URL, `activated=true`, and whether the password was used.

Message text such as “密码666” is not evidence; visible page state is. Never
read cookies, storage, or credentials. Later sweeps reconcile the exact task,
artifact, proxy cleanup, upload, and handoff without Browser.

## Remote handoff

For `daily_remote_handoff_input_required`, validate the small capsule and
resolve the newest remote writer Automation task for the current hourly window
on `MacBook-Pro-6.local`. Never route new work to a stale long-lived task, a
task from an older window, or a task waiting on approval. Send capsule fields
only, never local paths or video bytes. A `wechat_official_article` capsule
embeds only a credential-free public URL plus identity metadata. Import it
idempotently with `scripts/kol_daily.py import-wechat-official` over a plain
non-TTY stdin pipe (`tty=false`), writing the exact compact JSON as one line
exactly once; it contains no article body, Markdown, summary evidence, or local
path. After an accepted import, the same current-window remote task runs
`scripts/kol_daily.py process-wechat-official` exactly once and keeps that
process alive for image/semantic input; it does not rerun the full multi-source
hourly coordinator. Xiaocao video capsules still import with
`scope=post_handoff`. The remote task reads
[hourly-remote-writer.md](hourly-remote-writer.md) and reconciles the exact
`handoff_id`.

Return acceptance to the same local process only after an accepted or
already-present readback. Reconcile ambiguity before retrying, and persist the
host, current-window task, handoff ID, and acceptance. Never create a second
handoff merely because readback was delayed.

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
upload with an uncertain side effect. Report only a structured user-action
blocker or an externally visible completed handoff; preserve retryable details
in local status and audit surfaces without presenting them as business events.
