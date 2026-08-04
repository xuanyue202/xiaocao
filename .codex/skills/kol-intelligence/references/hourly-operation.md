# Hourly Low-Bandwidth Operation

Use this contract for Ticket 07's deterministic preflight, runner lifecycle,
and silent no-update/retryable paths. Do not read `full-contract.md` unless the
runner emits a semantic input request.

## Runner

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py run
```

The sole remote writer uses the command above. The local WeChat node uses only:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py capture-local
```

`capture-local` runs only `xiaocao_wechat_live`; it never scans Lv, consumes a
handoff, analyzes, publishes, notifies, or writes Book. Remote `run` is the
only writer.

Inspection surfaces are:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py status
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py audit
```

Each run exits after one sweep; the 07:00 run drains overnight backlog by decision
priority. No-update and healthy waiting are silent. Retryable failures expose
only credential-safe `category`, `code`, and `stage`. Do not run 23:01–06:59.

The coordinator reads only lightweight metadata, transcripts, images, handoff
JSON, and receipts; it never reads or downloads source-video bytes and never
uses Computer Use. The local adapter may use Browser, never Computer Use, to
activate the bound player. `wx_channels_download` alone owns video bytes and
inline compression.

## Xiaocao WeChat live gate

Scan only `福利官小花四-刘丹（执业编号:A0380125080026）` through local
`wechat-cli`. First scan baselines older links and arms only the newest; later
scans add unseen links. Never replace unfinished capture or start two sniffers.

For `daily_browser_input_required`, keep the process alive and use `browser`,
never Computer Use:

1. `resolve_xiaoetong_page`: open `source_url`; return current URL and page
   state. MP wrappers become H5 only after embedded app/resource validation;
   share parameters are stripped.
2. The runner arms that exact H5 source before requesting playback.
3. `activate_xiaoetong_playback`: refresh and play. Enter default `666` only
   for a visible password gate. After media requests begin, return bound URL,
   `activated=true`, and whether the password was used.

Message text such as “密码666” is not evidence; visible page state is. Never
read cookies/storage/credentials. Later sweeps reconcile exact task, artifact,
cleanup, upload, and handoff without Browser.

For `daily_remote_handoff_input_required`, validate the small capsule and reuse
the registered Xiaocao task on `MacBook-Pro-6.local`. Send fields, never paths
or video bytes. Remote reads `full-contract.md`, imports under
`scope=post_handoff`, and reconciles `handoff_id`. Return only after accepted or
already-present readback; reconcile ambiguity before retry. Persist host, task,
ID, and acceptance locally.

Latest Lv is incomplete until its identity/version has analysis plus a 灰常亮
receipt and stable URL. Preserve stage/reconciliation/`next_poll_not_before`;
use bounded cloud-save/native-click recovery from `full-contract.md`.

## Semantic loading gate

For `daily_analysis_input_required` in the same process:

1. Read the request and locate its evidence/bindings.
2. Read `full-contract.md` completely before analysis.
3. Reopen immutable evidence and verify its current SHA-256 against the request.
4. If reusable knowledge will be written, also read `durable-knowledge.md`
   completely.
5. Create complete evidence-bound Ticket 01 JSON beside runtime artifacts.
6. Write exactly `{"bundle_path":"<absolute-json-path>"}` followed by a newline
   to the same process.

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`, and
reviewed natural-Chinese publication fields.

Low-density creates neither report nor reminder. A promoted event gets its
durable 灰常亮 receipt and stable URL before Book KOL-US or reminder effects;
report-only records a no-alert reason, while alert-eligible sends one reminder.

## Scheduling and recovery

Codex Automation alone schedules exactly one remote writer and one local
capture task with
`RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0`.
Use Beijing wall time; omit `DTSTART` and `TZID`. After changes, reopen it and
verify next run and no duplicate.

The runner reuses the configured Lv Xiaotong share URL/code, watches
lightweight metadata under `/课程/路西法全套`, scans the one configured Xiaocao
WeChat contact, and consumes Xiaocao broadband handoffs plus cloud/transcript
receipts. Lv discovery recursively
reads the share tree and must not infer child-tree freshness from a
parent-directory modification time.

One sweep gets one complete recursive Lv `/share/list` snapshot and reuses it
for small-item/video adapters in the same process/session/profile. Each item
still validates provider identity, version, path, name, size, and target;
advance cursor only after the full scan. Incidental `已失效` text is not proof:
only an exact terminal state or provider failure may set `share_expired`;
successful metadata plus complete list wins.

For discovery-only OpenCLI failures (`wrong_share`, `wrong_origin`,
`about:blank`, timeout, invalid JSON, incomplete list), reopen the
share and retry the full read once in the same sweep. Preserve original/final
safe `category/code/stage`; never generalize the error. This authority
ends before download, transfer, publication, notification, or Book; those
reconcile claims/receipts and never retry blindly.

After a scan, ledger and isolate item failures; prioritize latest Lv,
and reconcile uncertain claims without replay.

Small-PDF precedence: complete video transcript, independent report, video
summary. Directory/title-date/mtime/version plus verified transcript may prove
`companion_suppressed` before claim; filename alone cannot. Ambiguous cases use
one claimed PDF download, immutable SHA-256, `pypdf`/`pdfplumber`, and rendered
visual/OCR coverage; unsafe PDFs fail closed.

Route Lv claims, not media types. `会员直播` uses current-fact/event/eligible
alert/paper-Book semantics. Reusable `底层逻辑` normally means no actionable
signal, useful insight, reusable knowledge, report-only/no-alert/reasoned
no-trade, distilled at `authority=0`; it cannot change posture or parameters
without research plus human gate. Mixed claims stay one report; only current
claims authorize alert/Book. Valuable methodology is not automatically low-density.

Put targeted currentness requests in
`output/live/kol_daily/viewpoint_triggers/*.json`. Supported triggers are a new
same-KOL publication, due horizon/trigger/falsifier, material fact change, and
explicit user request. Maintenance appends an evaluation under
content-and-manifest CAS and creates no reminder or Book action.

The append-only ledger resumes only unfinished sources within an hour.
Historical initialization, correction, evaluation maintenance, restart, and
replay reconcile existing receipts and never resend an earlier reminder or
paper action. Report only a structured user-action blocker or a completed
externally visible event. Do not surface a retryable diagnostic as an external
event, but preserve it in `status`, `audit`, and the append-only ledger. The same
blocker stays silent until it changes or clears.

A first exhausted transient discovery recovery may remain an internal degraded
state. The same source/stage/code in consecutive hourly slots, or a newly
observed identity/version that stays at `source_acquisition` across two slots,
must append a recovery-exhausted/stalled audit record in that sweep. The runner
must record that deterministic recovery was attempted and that no business
effect was replayed. If receipts do not permit a safe deterministic repair,
emit one deduplicated structured operational blocker; never remain silently
degraded forever.
