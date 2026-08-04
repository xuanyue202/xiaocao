# Hourly Low-Bandwidth Operation

Use this for Ticket 07 preflight, lifecycle, and silent paths. Do not read
`full-contract.md` unless the runner requests semantic input.

## Runner

Run exactly one command in the Xiaocao repository and keep that process alive:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py run
```

Inspection surfaces are:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py status
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py audit
```

One sweep per run; a 07:00 run drains overnight backlog by decision priority.
No-update/healthy waits are silent. Retryable failures persist credential-safe
`category`/`code`/`stage` only. No runs from 23:01 to 06:59.

Read only lightweight evidence/receipts; never reads or downloads source-video
bytes, and never uses Computer Use.

For the latest Lv video, discovery is not completion. `latest_lv_video_goal`
succeeds only when its exact identity/version has a completed terminal and a
灰常亮 report with durable receipt plus stable URL; earlier stages stay pending.

Unfinished video ledger rows retain identity/version/stage, trigger attempt,
reconciliation, and `next_poll_not_before`. Retry cloud-save once only after a
settled exact zero-match; two failures become
`lv-cloud-transfer-not-materialized`. The final share `确定` must be an OpenCLI
native semantic click; claim it first and reconcile ambiguity before retry.

## Semantic loading gate

When the still-running process emits `daily_analysis_input_required`:

1. Read the analysis request from disk to locate its evidence and bindings.
2. Read `full-contract.md` completely before analysis.
3. Reopen the referenced immutable evidence, verify its current SHA-256 against
   the request, and use that one bound reading for analysis.
4. If reusable knowledge will be written, also read `durable-knowledge.md`
   completely.
5. Create the complete evidence-bound Ticket 01 JSON beside the runtime
   artifacts.
6. Write exactly `{"bundle_path":"<absolute-json-path>"}` followed by a newline
   to the same process.

Keep stdin open. EOF persists `waiting_semantic_input`, preserving the original
request, evidence SHA, and item claim. The next sweep reuses that exact
request/evidence, skips completed acquisition/transcript work, and never
replays publication, notification, or Book effects. Stop that adapter before
later backlog items.

Small downloads are unattended: never edit ordinary Chrome or a global
extension. Try `Page.setDownloadBehavior` with controlled inbox readback;
otherwise bind one memory-only PDF/UTF-8 link to exact provider
id/name/size/identity/version and validate HTTPS/type/bytes/SHA. Never use it
for video or persist secrets. Save prompts are internal—no user blocker or
WeChat. Only auth, SMS, CAPTCHA or consent may ask; no second UI trigger.

Every item includes `content_value.status=low_density|promoted`. Promoted items
also include `content_value.tier=report_only|alert_eligible`. An alert-eligible
event supplies one or more accepted `alert_basis` values: current market
posture, buy, sell, hold, position boundary, direction, or actionable trigger.
Promoted items include reviewed natural-Chinese `publication.summary`,
`publication.report_body`, and `publication.remaining_summary`.

A low-density item uses a paper-only KOL-US no-trade reason and creates neither
a 灰常亮 report nor a reminder. A promoted event obtains its durable 灰常亮
receipt and stable URL before Book KOL-US or reminder effects. Report-only
content records a legal no-alert reason. An alert-eligible event sends one
all-recipient reminder with the key insight, compact synthesis, and exactly one
stable report link.

## Scheduling and recovery

Codex Automation is the only scheduling authority. Keep exactly one active
task with
`RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0`.
Express Beijing wall-clock time directly and omit `DTSTART` and `TZID`. Reopen
the Automation after every change and verify the next run and that no duplicate
task exists.

The runner reuses the configured Lv Xiaotong share URL/code, watches
lightweight metadata under `/课程/路西法全套`, and consumes only Xiaocao
broadband handoffs plus cloud/transcript receipts. Lv discovery recursively
reads the share tree and must not infer child-tree freshness from a
parent-directory modification time.

One sweep obtains at most one complete recursive Lv `/share/list` snapshot and
reuses it for both the small-item and video adapters in the same process,
session, and profile. Every item still validates exact provider identity,
version, path, name, size, and target. A cursor advances only after a complete
scan. The words `已失效` elsewhere in a valid page are not an expiration proof:
only an exact visible terminal state or an explicit provider failure response
may classify `share_expired`; successful share metadata and a complete list
take precedence.

Discovery-only OpenCLI failures (`wrong_share`, `wrong_origin`, `about:blank`,
timeout, invalid JSON, and incomplete `/share/list`) may reopen the configured
share, wait briefly, and retry the full read exactly once in the same sweep.
Preserve the original and final credential-safe `category/code/stage`; never
collapse them into a generic source error. This recovery authority ends before
any download, cloud-transfer, publication, notification, or Book side effect.
Those actions reconcile claims and receipts and are never retried blindly.

After a scan, ledger and isolate item failures; prioritize latest Lv,
and reconcile uncertain claims without replay.

Small-PDF precedence is complete video transcript, independent report, then
video summary. Directory/title-date/mtime/version plus a verified transcript
may prove `companion_suppressed` before claim; filename alone cannot. Ambiguous
or incomplete cases use one claimed local PDF download, immutable SHA-256,
`pypdf`/`pdfplumber`, and rendered visual/OCR coverage; unsafe PDFs fail closed.

Route Lv claims, not media types. `会员直播` uses current-fact/event/eligible
alert/paper-Book semantics. Reusable `底层逻辑` normally uses no actionable
signal, useful insight, reusable knowledge, report-only, no alert, and reasoned
no-trade; it distills under `reference/experience/distilled/` at `authority=0`.
It cannot change posture/timeline/parameters without research plus human gate.
Mixed claims stay one report; only the current branch authorizes alert/Book,
and valuable methodology is not low-density merely for lacking a trade call.

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
