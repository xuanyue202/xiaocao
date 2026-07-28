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
decision-priority order. No-update and self-recoverable waiting states print
nothing. There is no invocation from 23:01 through 06:59.

The coordinator may read only lightweight metadata, transcripts, images,
handoff JSON, and durable receipts. It never reads or downloads source-video
bytes and never uses Computer Use.

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
broadband handoffs plus cloud/transcript receipts.

Put targeted currentness requests in
`output/live/kol_daily/viewpoint_triggers/*.json`. Supported triggers are a new
same-KOL publication, due horizon/trigger/falsifier, material fact change, and
explicit user request. Maintenance appends an evaluation under
content-and-manifest CAS and creates no reminder or Book action.

The append-only ledger resumes only unfinished sources within an hour.
Historical initialization, correction, evaluation maintenance, restart, and
replay reconcile existing receipts and never resend an earlier reminder or
paper action. Report only a structured user-action blocker or a completed
externally visible event. The same blocker stays silent until it changes or
clears.
