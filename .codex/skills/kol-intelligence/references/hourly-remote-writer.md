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

This machine is the only KOL writer. It consumes Xiaocao `scope=post_handoff`
capsules and URL-only `wechat_official_article` capsules. Import the latter as
one compact JSON line with `scripts/kol_daily.py import-wechat-official` over a
plain non-TTY stdin pipe (`tty=false`). Never use a canonical PTY for the
capsule line, because line buffering can retain or truncate the request before
Python's `readline()` receives it. If the execution backend closes stdin before
receiving any bytes, verify the pre-input failure and missing receipt, create
one validated temporary JSONL line, and invoke the importer once with that file
as plain stdin. Do not count the empty pre-input process as an import attempt
and do not send the capsule twice. XML wrapper text may render URL `&` as
`&amp;`; restore the raw URL, recompute `handoff_sha256`, and require an exact
match before the importer sees it. The capsule is discovery metadata, not the full article.
It never scans the local WeChat contact and never reads or downloads source-video bytes. It does not
activate a capture player or use Computer Use.

When an official-account capsule arrives after this hour's multi-source runner
has already finished, process only that imported inbox with
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py process-wechat-official`.
Run it exactly once and keep the same process alive for image/semantic input;
do not rerun the full `run` command merely to pick up the handoff.

For an official item, run installed OpenCLI once with `weixin download`, image
download, background Chrome, and JSON output. Require success, an item-local
file, exact publisher/title/time, complete UTF-8 body/images, bytes, and hashes.
Combine OpenCLI's verification UI/path/node signals with `请输入验证码`; CAPTCHA
stops for same-session verification without HTTP/MCP retry.

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

For `daily_official_article_image_input_required`, inspect every image once and
write only `# 图片信息转写` Markdown with each index/SHA, information/decorative
status, relevant text/chart/table content, and uncertainty. Do not copy the
body or return JSON. The runner appends notes to full Markdown before analysis.

Keep stdin open. EOF persists `waiting_semantic_input`, preserving the original
request, evidence SHA, and item claim. The next sweep reuses that exact
request/evidence, skips completed acquisition/transcript work, and never
replays publication, notification, or Book effects. Stop that adapter before
later backlog items.

Small downloads are unattended: use `Page.setDownloadBehavior` with a
controlled inbox; otherwise bind one memory-only link to the exact provider
id/name/size/identity/version. There is no user blocker or WeChat for a Save
prompt. Never edit ordinary Chrome or a global extension. Only auth, SMS,
CAPTCHA, or consent may ask; never edit ordinary Chrome or a global extension,
and never issue a second UI trigger.

Every item includes `content_value.status=low_density|promoted`; promoted items
add `content_value.tier=report_only|alert_eligible`, accepted `alert_basis`, and
reviewed natural-Chinese publication fields. Every promoted item also decides
`longitudinal_projection`: `promoted` carries evidence-bound viewpoints and an
initial `current|expired|invalidated|uncertain` evaluation; `none` carries an
empty list and a concrete reason. Missing this decision fails closed rather
than defaulting to an empty viewpoint list.

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

Reuse the configured Lv share, `/课程/路西法全套`, Xiaocao handoffs, and their
receipts. One sweep reuses one complete recursive Lv listing; validate every
identity/version/path/name/size/target and advance the cursor only after the
full scan. Parent mtime or incidental `已失效` text is not proof.

Discovery-only OpenCLI failures may reopen and retry one full read. Preserve
safe `category/code/stage`; authority ends before any side effect. Reconcile
claims and isolate failures without replay. Apply `full-contract.md` PDF
precedence, owner-copy, OCR, and claim-routing rules only when that item reaches
the relevant stage. Unsafe or ambiguous evidence fails closed.

Route Lv claims, not media types: `会员直播` follows current event gates;
reusable `底层逻辑` is normally report-only `authority=0` knowledge with no Book
row. Mixed claims stay one report and only current claims authorize effects.

Put new-publication, due-horizon, material fact, or user currentness requests in
`output/live/kol_daily/viewpoint_triggers/*.json`; maintenance uses CAS and
creates no reminder or Book action.
Use `operation=initial_projection` plus `trigger=user_request` only for a
reviewed report-only history that still has no viewpoints. Run
`PYTHONPATH=src .venv/bin/python scripts/kol_daily.py viewpoints` to process
only these maintenance triggers without scanning sources. It must preserve the
stable report URL and prior manifest, and it never creates a reminder or Book
action.

The append-only ledger resumes unfinished work and reconciles history,
corrections, maintenance, restarts, and replays without resending. Preserve
retryable diagnostics in status/audit; the same blocker stays silent until it
changes. Repeated source/stage/code or acquisition stalls append one exhausted
audit. If receipts forbid deterministic repair, emit one deduplicated blocker.
