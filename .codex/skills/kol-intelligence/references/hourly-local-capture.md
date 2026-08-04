# Hourly Local Capture Node

Use this contract only on the local WeChat/broadband node. Its entire hourly
scope is discovery, Xiaoetong playback activation, inline-compressed capture,
cloud upload, and a credential-free handoff. The remote writer follows
[hourly-remote-writer.md](hourly-remote-writer.md); do not perform its work here.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

`capture-local` runs only `xiaocao_wechat_live`. It never scans Lv, consumes a
handoff, reads a transcript, analyzes, publishes, notifies, or writes Book. Do
not substitute the remote coordinator command on this machine.

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

For `daily_remote_handoff_input_required`, validate the small capsule and reuse
the registered Xiaocao task on `MacBook-Pro-6.local`. Send capsule fields only,
never local paths or video bytes. The remote task reads
[hourly-remote-writer.md](hourly-remote-writer.md), imports with
`scope=post_handoff`, and reconciles the exact `handoff_id`.

Return acceptance to the same local process only after an accepted or
already-present readback. Reconcile ambiguity before retrying, and persist the
host, task, handoff ID, and acceptance. Never create a second remote task or
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
