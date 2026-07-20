# KOL Intelligence Decision Slice

Ticket 01 begins with already-transcribed material. Ticket 02 adds a real,
single-video Baidu Netdisk consumer-page state machine. Its primary evidence
route is the complete, initially rendered transcript DOM read through the
logged-in OpenCLI browser bridge. Baidu AASR remains an explicit fallback that
does not satisfy the mandatory Netdisk acceptance. Ticket 02 excludes Computer
Use, live capture, subscriptions, batch ingestion, and scheduling.

## Baidu Netdisk browser enrichment

Prepare the runtime-named source before touching the page:

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py prepare \
  --video '/absolute/path/runtime-title-compressed.mp4'
```

The browser provider is `baidu_consumer_page`. First inspect the local source,
current login, existing cloud video, transcript, and any existing AI note. Use the logged-in
OpenCLI bridge to prove fresh DOM control; a manually clickable tab, ambient
URL, or tab listing alone is not sufficient. Persist liveness, derive locators
from the real DOM, and reconcile the exact basename before asking the user to
prepare anything. Use `source_mode=existing` when the cloud copy is present and
upload only when it is absent. Persist a claim before each external browser
side effect; read-only DOM capture itself does not need a side-effect claim:

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py liveness \
  --job-id <job-id> --surface opencli \
  --evidence-file /absolute/path/liveness-evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py claim \
  --job-id <job-id> --action upload
PYTHONPATH=src python3 scripts/kol_netdisk_video.py claim \
  --job-id <job-id> --action transcript
```

Liveness evidence uses the same fresh, timezone-aware snapshot/hash discipline,
but stores only its sanitized Netdisk path, observation time, and SHA-256. A
durable capability failure invalidates prior liveness until a later fresh DOM
snapshot is explicitly recorded; side-effect claims fail closed meanwhile.
Only the exact `/disk/main` and `/pfile/video` paths are accepted, and a proof
older than 30 minutes cannot authorize a new claim. Recovery evidence must
strictly post-date the latest capability failure; a still-fresh snapshot taken
before the denial cannot clear it.

After the real page visibly changes, save a small evidence JSON object and
record the corresponding state. `visible_state` is a canonical marker, not free
text. `snapshot_text` is the transient fresh DOM snapshot used to prove the
target and step semantics; its SHA-256 must match. The service discards that
text and writes only the safe marker and hash to the append-only ledger:

```json
{
  "page_url": "https://pan.baidu.com/pfile/video",
  "target_name": "runtime-title-compressed.mp4",
  "visible_state": "transcript_ready",
  "snapshot_text": "...runtime-title-compressed.mp4...文稿 已生成...",
  "target_region_text": "runtime-title-compressed.mp4...文稿 已生成",
  "snapshot_sha256": "<64 lowercase hex characters>",
  "observed_at": "2026-07-20T09:00:00+08:00"
}
```

Canonical markers are `video_present`, `transcript_generating`,
`transcript_ready`, `ai_note_generating`, `ai_note_ready`,
`transcript_exported`, `cloud_document_present`, and `download_started` for the
corresponding record steps in order.

`video_ready` may be proven either by the exact `/disk/main` row or by an exact
`/pfile/video?path=.../<target-basename>` player binding. Transcript, AI-note,
and DOM-capture evidence comes from `/pfile/video`; legacy export/download
states remain restricted to their appropriate player or file-list views. Query
strings are validated for target binding and stripped before ledger storage.
Normal side-effect transitions must occur at or after their claim or
predecessor evidence.

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step video_ready --source-mode existing \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step transcript_requested \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step transcript_ready \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step ai_note_requested \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step ai_note_ready \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step export_ready \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step cloud_document_ready \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step download_requested \
  --evidence-file /absolute/path/evidence.json
```

When the fresh target-scoped DOM proves that a cloud child already exists, do
not persist a claim and do not repeat its generating/export side effect. Record
only the stable completed state with explicit reconciliation:

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step transcript_ready --reconcile-existing \
  --evidence-file /absolute/path/evidence.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py record \
  --job-id <job-id> --step ai_note_ready --reconcile-existing \
  --evidence-file /absolute/path/evidence.json
```

Those are the only reconcilable generated states. Requested/generating and
legacy export/download states reject this flag. A user report may guide
inspection but cannot replace fresh exact-target DOM evidence.

The complete transcript is the required child. An already-present AI note may
be reconciled as independent sibling evidence, but it is optional and never
gates or replaces transcript capture. Once the transcript is ready, activate
`文稿` and capture the complete DOM directly:

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py capture-dom \
  --job-id <job-id> --opencli-session <session>
PYTHONPATH=src python3 scripts/kol_netdisk_video.py verify \
  --job-id <job-id> --audit-file /absolute/path/content-audit.json
PYTHONPATH=src python3 scripts/kol_netdisk_video.py decide \
  --job-id <job-id> --bundle /absolute/path/decision-bundle.json
```

`capture-dom` validates the exact player URL and active `文稿` tab, requires one
`.ai-draft__wrap-list`, and rejects partial/virtualized content unless the last
sentence is already in the initial DOM. It records `scrollTop=0`, dimensions,
paragraph/sentence/character counts, the below-viewport last node, and the
absence of virtual/loading/load-more markers. The transcript is written once to
an immutable per-job text artifact and bound to the source video and render
proof by SHA-256. Opening/middle/ending verification and ticket-01 decision
completion then require a real household receipt plus a `book=KOL-US`,
`paper_only=true` fill or nonempty no-trade reason.

The older explicit export → same-name cloud `.doc` → download →
`import-download` chain remains supported as a compatibility path for a page
whose complete transcript cannot be proven in the initial DOM. It is not
required when `capture-dom` succeeds. A partial or virtualized transcript fails
closed; it is never silently accepted or replaced by the AI note.

If a browser surface rejects DOM access, record the exact failed surface without
advancing the job:

```bash
PYTHONPATH=src python3 scripts/kol_netdisk_video.py capability-failure \
  --job-id <job-id> --surface <surface> \
  --reason browser_security_policy_denied
```

Run this once for every newly observed denial, even if the surface and reason
match the preceding failure. Failure recording has no browser side effect, and
each observation refreshes the causal cutoff that later liveness/page evidence
must strictly post-date.

Codex browser policy denial is surface-specific: after recording it, use the
documented logged-in OpenCLI bridge when available. Do not use raw CDP,
Computer Use, absolute coordinates, or a secret-bearing browser workaround.
AASR remains a separate provider and cannot be reported as successful Netdisk
acceptance.

Keep execution layers separate when diagnosing or resuming: user-visible page
access, agent DOM control, cloud transcript readiness, optional AI-note
readiness, complete-render proof, immutable local transcript, and decision
delivery are independent facts. Absence of a local `.doc` never authorizes
regeneration of an already-ready cloud transcript.

## Explicit AASR fallback

The fallback evidence is the complete provider ASR in source order, not an AI
note or cleaned summary. Prepare one completed compressed video with:

```bash
PYTHONPATH=src python3 scripts/kol_enrich_video.py prepare \
  --video '/absolute/path/runtime-title-compressed.mp4'
```

The command records video/audio hashes, duration, and a verified 16 kHz mono
PCM WAV under `output/live/kol_enrichment/artifacts/<job-id>/`. Configure Baidu
AASR credentials only in the environment. Submit either through a private S3
prefix (the CLI uploads, verifies SHA metadata, and keeps the presigned URL only
in memory) or an already-authorized HTTPS WAV URL held in
`KOL_AASR_SPEECH_URL`:

```bash
PYTHONPATH=src python3 scripts/kol_enrich_video.py submit \
  --job-id <job-id> --s3-prefix s3://private-bucket/kol-audio

PYTHONPATH=src python3 scripts/kol_enrich_video.py submit \
  --job-id <job-id> \
  --publication-reference provider://secret-free/object-reference
```

`poll` fails locally before the persisted five-minute gate and then backs off.
After `Success`, run `render`, create an audio spot-check JSON covering opening,
middle, ending, direction/negation, numbers, and proper names, and run `verify`.
Only a verified transcript may be named as the single decision item's
`evidence_path`:

```json
{
  "video_sha256": "<source-video-sha256>",
  "checks": [
    {
      "position": "opening",
      "timestamp_ms": 12000,
      "transcript_excerpt": "<exact checked text>",
      "heard_text": "<same text after listening>",
      "categories": ["direction_or_negation"],
      "passed": true
    },
    {
      "position": "middle",
      "timestamp_ms": 312000,
      "transcript_excerpt": "<exact checked number>",
      "heard_text": "<same number after listening>",
      "categories": ["number"],
      "passed": true
    },
    {
      "position": "ending",
      "timestamp_ms": 612000,
      "transcript_excerpt": "<exact checked proper name>",
      "heard_text": "<same proper name after listening>",
      "categories": ["proper_name"],
      "passed": true
    }
  ]
}
```

```bash
PYTHONPATH=src python3 scripts/kol_enrich_video.py poll --job-id <job-id>
PYTHONPATH=src python3 scripts/kol_enrich_video.py render --job-id <job-id>
PYTHONPATH=src python3 scripts/kol_enrich_video.py verify \
  --job-id <job-id> --audit-file /absolute/path/content-audit.json
PYTHONPATH=src python3 scripts/kol_enrich_video.py decide \
  --job-id <job-id> --bundle /absolute/path/decision-bundle.json
```

The append-only ledger persists stable paths, hashes, task IDs, timing gates,
and delivery/book summaries. It never persists credentials, tokens, cookies,
presigned URLs, URL query strings, or household positions. The logged-in Chrome
spike on 2026-07-19 was explicitly denied access to the Netdisk consumer page
by a surface-specific policy. That failure is not bypassed with raw CDP,
Computer Use, desktop coordinates, or secret extraction; the documented
OpenCLI bridge is the accepted DOM route.

## Input boundary

Convert the real Word exports with the existing local converter:

```bash
bash /Users/bytedance/Downloads/小草/convert_original_doc_to_markdown.sh \
  /Users/bytedance/Downloads/小草/original_doc \
  /Users/bytedance/Downloads/小草
```

The decision pipeline consumes UTF-8 Markdown or text. A decision bundle is a
JSON object with one source-neutral `items[]` entry per transcript. Each entry
contains source metadata, evidence-anchored KOL claims, concrete
`actionable_signals[]`, a frozen current-market validation, separate system
synthesis, one household advisory action, and one Book KOL-US trade or explicit
no-trade decision. Every actionable signal must name an asset/ticker or explicit
theme, action, horizon, execution, trigger, falsifiers, current validation, and
separate event/fundamental/trading rationales. Framework-only content fails as
`low_density_content`. Cross-source agreements and conflicts link claim IDs
from at least two distinct authors and require a written judgment; counts and
majority votes have no authority. Relevant multi-author conclusions are part of
the reader-facing message, not audit-only plumbing.

The candidate universe is the market, not the current household holdings.
Fresh 亮灰 positions are used to label held/unheld opportunities, size risk, and
state a funding/rotation plan. They must not filter out an opportunity merely
because the family does not already own it.

`household_context_provider` selects the authoritative 亮灰 `lianghui_mcp` source.
Every processing run freshly reads `user://current`,
`get_portfolio_decision_view`, and `get_portfolio_reconciliation_view`. The
resulting family id, timestamp, positions, and decision facts are hashed and
linked to that run's audit/message. They are never reused as the next run's
input. Credentials remain in the 亮灰 project's local `LiangHuiProject` MCP
configuration and are
not copied into this repository or an output ledger.

Claims must contain an exact excerpt from the referenced transcript. Market
validation must use one of `support`, `qualify`, `conflict`, or `invalidate` and
must include timestamped facts with evidence references. Age alone is not an
invalidation rule.

Run a bundle with:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py path/to/bundle.json
```

To process with a fresh 亮灰 portfolio read and deliver each still-pending item
to the recipient already configured in `output/live/notify.env`, use:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py path/to/bundle.json --send-wechat
```

The sender reuses `src/xiaocao/live/notify.py`. A relay `ok` is persisted as a
per-item receipt immediately. Notification idempotency includes the market
outlook, advisory, relevant cross-source judgment, and revision, so a material
change from defense to trial positioning creates a new reader notification.
Book KOL-US keys on evidence plus
the material paper intent: replaying the same decision is idempotent, while a
later `no_trade -> trade` or target change can be recorded after new market
facts. Legacy evidence-only decisions remain replay-compatible. A process lock and a
durable pre-send claim prevent concurrent duplicate sends; an interrupted relay
call fails closed as uncertain until reconciled.

## Two output layers

Phone messages are written for a human reader, not as serialized pipeline state.
When the source contains a market-wide or portfolio-wide judgment, the normalized
item carries an evidence-linked `market_outlook` with the current phase, base
case, overall strategy, turning points, horizon, confidence, falsifiers, and its
own scope-matched current-market validation. The message renders this as a
standalone `大盘与整体策略` section before individual stocks or themes. It shows
the linked KOL quotes first, then labels current-market validation and every
forward path/strategy statement as system judgment, including validation time
and whether facts support, qualify, conflict with, or invalidate the view. Key
facts are rendered in reader language with their observation time; raw evidence
references remain in the audit output instead of cluttering the phone message. It
must not be inferred from holdings or invented when the source has no such view.
Each subsequent signal names the company and code,
explains what happened, connects the causal chain to the likely market impact,
says what it means for this household or a new opportunity, and gives
plain-language timing and reconsideration conditions.
Book KOL-US fills, gate/status enums, bucket labels, and hashes remain in the
audit result and are never included in WeChat copy. Relevant cross-author
agreement or tension is rendered in plain language.

The single `kol-intelligence` invocation also evaluates a conditional durable-knowledge
branch. Reusable reasoning from every author is distilled through the same governance
into `reference/experience/distilled/`; a source with no reusable logic records
`knowledge_status=no_reusable_knowledge` instead of creating an empty artifact. New
multi-author files include `author`, `source`, and evidence path/SHA provenance;
the common candidate backlog preserves authors and source references. This
issue does not rewrite the global current A-share posture; all three authors'
notes enrich hypotheses and reusable judgment with `authority=0` until the
existing research and human gates pass.

Committed acceptance bundles contain transcript claims, market evidence, and
redacted routing intent only. The actual family holdings and personalized
held/unheld assessment stay under ignored `output/live/kol_intelligence/`.

Use `--preflight` to validate all transcript quotes, market facts, cross-source
links, and Book KOL-US intents without writing any notification or trade. Once
an external WeChat send is confirmed, record its receipt idempotently:

```bash
PYTHONPATH=src python3 scripts/kol_decisions.py \
  --output-dir output/live/kol_intelligence \
  --mark-delivered <IDEMPOTENCY_KEY> --receipt <WECHAT_RECEIPT>
```

Outputs live under `output/live/kol_intelligence/` by default:

- `latest_result.json` and `events.jsonl`: auditable analysis results;
- `latest_household_message.md` and `household_outbox.jsonl`: deterministic
  WeChat-ready advisory messages, pending until an agreed delivery adapter
  records an external receipt;
- `book_kol_us/account.json`, `decisions.jsonl`, and `trades.jsonl`: an isolated,
  paper-only, cash-only US equity/ETF book.

The pipeline fails visibly before side effects when household context or market
facts are missing, a ticker is ambiguous, content is low-density, evidence does
not contain the quoted claim, or a proposed paper instrument breaches the book
rules. It never imports or calls a real-capital execution interface.
