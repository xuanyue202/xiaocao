# Hourly Remote Writer

Use this contract only on the remote sole-writer node for Ticket 07's
deterministic preflight, runner lifecycle, and silent no-update/retryable paths.
The local WeChat/broadband node follows
[hourly-local-capture.md](hourly-local-capture.md); do not perform its capture
work here. Do not read `full-contract.md` unless the runner emits a semantic
input request or post-handoff semantic work is ready.

## Runner and boundary

Run exactly once and keep the process alive for input requests:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py run
```

Inspection surfaces are:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py status
PYTHONPATH=src .venv/bin/python scripts/kol_daily.py audit
```

Each run exits after one sweep; the 07:00 run drains overnight backlog by
decision priority. No-update and healthy waiting are silent. Retryable failures
expose only credential-safe `category`, `code`, and `stage`. Do not run
23:01–06:59.

This machine is the only KOL writer. It consumes imported Xiaocao handoffs with
`scope=post_handoff`; it never scans the local WeChat contact, activates a
browser player, or reads local capture paths. The coordinator reads only
lightweight metadata, transcripts, images, handoff JSON, and receipts; it never
reads or downloads source-video bytes and never uses Computer Use.

For an imported Xiaocao handoff, reconcile the exact `handoff_id` and media
SHA-256 before advancing. Latest Xiaocao or Lv content is incomplete until its
identity/version has analysis plus a 灰常亮 receipt and stable URL. Preserve the
concrete stage, reconciliation result, and `next_poll_not_before`; use bounded
cloud-save/native-click recovery from `full-contract.md` only at the relevant
provider step.

## Semantic loading gate

For `daily_analysis_input_required` in the same process:

1. Read the request and locate its evidence and bindings.
2. Read `full-contract.md` completely before analysis.
3. Reopen immutable evidence and verify its current SHA-256 against the request.
4. If reusable knowledge will be written, also read `durable-knowledge.md`
   completely.
5. Create complete evidence-bound Ticket 01 JSON beside runtime artifacts.
6. Write exactly `{"bundle_path":"<absolute-json-path>"}` followed by a
   newline to the same process.

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

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`, and
reviewed natural-Chinese publication fields.

Low-density creates neither report nor reminder. A promoted event gets its
durable 灰常亮 receipt and stable URL before Book KOL-US or reminder effects;
report-only records a no-alert reason, while alert-eligible sends one reminder.

## Remote schedule

Codex Automation schedules exactly one remote writer with:

```text
RRULE:FREQ=DAILY;BYHOUR=7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23;BYMINUTE=0
```

Use Beijing wall time; omit `DTSTART` and `TZID`. After changes, reopen the
existing Automation and verify its next run and that no duplicate exists. Do
not create, edit, or assume ownership of the local capture Automation here.

## Discovery and recovery

The runner reuses the configured Lv Xiaotong share URL/code, watches lightweight
metadata under `/课程/路西法全套`, and consumes Xiaocao cloud handoffs plus
cloud/transcript receipts. Lv discovery recursively reads the share tree and
must not infer child-tree freshness from a parent-directory modification time.

One sweep gets one complete recursive Lv `/share/list` snapshot and reuses it
for small-item/video adapters in the same process/session/profile. Each item
still validates provider identity, version, path, name, size, and target;
advance cursor only after the full scan. Incidental `已失效` text is not proof:
only an exact terminal state or provider failure may set `share_expired`;
successful metadata plus complete list wins.

For discovery-only OpenCLI failures (`wrong_share`, `wrong_origin`,
`about:blank`, timeout, invalid JSON, incomplete list), reopen the share and
retry the full read once in the same sweep. Preserve original/final safe
`category/code/stage`; never generalize the error. This authority ends before
download, transfer, publication, notification, or Book; those reconcile
claims/receipts and never retry blindly.

After a scan, ledger and isolate item failures; prioritize latest Lv and
reconcile uncertain claims without replay.

Small-PDF precedence: complete video transcript, independent report, video
summary. Directory/title-date/mtime/version plus verified transcript may prove
`companion_suppressed` before claim; filename alone cannot. Ambiguous cases use
one claimed PDF download, immutable SHA-256, `pypdf`/`pdfplumber`, and rendered
visual/OCR coverage; unsafe PDFs fail closed.

For a claimed client-only small PDF, reuse its acquisition claim and one exact
`/xiaocao/lv_subscription/<version>/` owner copy: 0 matches transfers, 1 exact
name/size resumes, and >1 fails closed. Persist only owner fsid/path/size;
owner dlink and same-target HttpOnly cookies stay in memory. Require HTTP 200,
exact size, PDF magic, and SHA. Exclude video/large files; ordinary Save or
client-only states are not user blockers.

Route Lv claims, not media types. `会员直播` uses current-fact/event/eligible
alert/paper-Book semantics. Reusable `底层逻辑` normally means no actionable
signal, useful insight, reusable knowledge, report-only/no-alert/reasoned
`not_applicable` Book intent and no Book row, distilled at `authority=0`; it
cannot change posture or parameters without research plus human gate. Mixed
claims stay one report; only current claims authorize alert/Book. Valuable
methodology is not automatically low-density.

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
event, but preserve it in `status`, `audit`, and the ledger. The same blocker
stays silent until it changes or clears.

A first exhausted transient discovery recovery may remain an internal degraded
state. The same source/stage/code in consecutive hourly slots, or a newly
observed identity/version that stays at `source_acquisition` across two slots,
must append a recovery-exhausted/stalled audit record in that sweep. Record
that deterministic recovery was attempted and no business effect was replayed.
If receipts do not permit a safe deterministic repair, emit one deduplicated
structured operational blocker; never remain silently degraded forever.
