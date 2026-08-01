# Hourly Low-Bandwidth Operation

Use this contract for Ticket 07's deterministic preflight, runner lifecycle,
and silent no-update/retryable paths. Do not read `full-contract.md` unless the
runner emits a semantic input request.

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

Every run exits after one sweep. A 07:00 run drains overnight backlog in
decision-priority order. A completed scan with no new content and healthy
asynchronous waiting print nothing. A retryable source failure prints one
credential-safe diagnostic containing `category`, `code`, and `stage`; this is
local operational evidence, not an externally visible event. There is no
invocation from 23:01 through 06:59.

The coordinator may read only lightweight metadata, transcripts, images,
handoff JSON, and durable receipts. It never reads or downloads source-video
bytes and never uses Computer Use.

Discovery is not completion for the latest Lv Xiaotong video. `status` and
`audit` expose `latest_lv_video_goal`; it is successful only when the exact
latest observed identity and version have a completed analysis terminal plus a
published 灰常亮 report with both a durable receipt and stable detail URL.
Download, cloud enrichment, transcript readiness, or analysis alone remain
pending/incomplete states and must not be reported as success.

An unfinished subscription-video result must retain its item identity,
version, concrete stage, trigger attempt, reconciliation result, and
`next_poll_not_before` in the coordinator ledger. A cloud-save claim gets one
recovery attempt only after a settled exact zero-match proof; two failed
materializations become the changed structured blocker
`lv-cloud-transfer-not-materialized`, not another generic waiting state.
The share dialog's final `确定` action is an OpenCLI native semantic click on
the uniquely marked control, never a JavaScript `element.click()`. Claim the
native click first; if its result is ambiguous, reconcile the exact private
copy before any second attempt.

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
