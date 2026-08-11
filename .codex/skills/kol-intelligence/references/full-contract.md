# Full KOL Intelligence Contract

Read this file completely before any semantic extraction, KOL source workflow,
publication, viewpoint maintenance, household recommendation, or Book KOL-US
decision. For the hourly coordinator's deterministic preflight and no-update
path, read `hourly-remote-writer.md` instead and load this file only if the
runner emits a semantic input request.

## Contents

- [One input, two conditional branches](#one-input-two-conditional-branches)
- [Deployment boundary](#deployment-boundary)
- [灰常亮 report and viewpoint publication](#灰常亮-report-and-viewpoint-publication)
- [Xiaocao capture](#xiaocao-capture)
- [Enrichment boundary](#enrichment-boundary)
- [Lv Xiaotong direct subscription](#lv-xiaotong-direct-subscription)
- [Lv Xiaotong and Lucifer cloud videos](#lv-xiaotong-and-lucifer-cloud-videos)
- [Resumable multi-source batches](#resumable-multi-source-batches)
- [Source-agnostic investment-claim coverage gate](#source-agnostic-investment-claim-coverage-gate)
- [Judgment contract](#judgment-contract)
- [Output contract](#output-contract)

Keep every run resumable. Prefer deterministic local APIs, CLIs, and logged-in browser DOM automation. Computer Use is not a default or fallback implementation: the Baidu desktop experiment showed it is too slow and unreliable for this workflow. Consider it only through a separately reviewed exception after API, CLI, and browser-DOM approaches have all been concretely disproved.

## Agent-owned self-repair

First principle: minimize dependence on the user. Apply 5 Why and
first-principles diagnosis to every recoverable code, environment, tool,
provider, schema, rendering, or control-plane failure in the current task.
Bind the exact item, stage, evidence, claims, receipts, and uncertain effects;
reproduce read-only, fix the root cause, add a regression, validate, and resume
the same durable job without replay. Fail-closed blocks unsafe effects, not
repair. Retrieve/process evidence when safely obtainable instead of deferring
to the user or a later run. Commit and normally push the scoped repair after
reconciling `main`, preserving unrelated WIP.

Use `repair_required` for timeouts, selector or provider-contract drift, schema
and rendering mismatches, missing internal controls, broken recovery paths,
and other repository defects the Agent can investigate. These failures may
degrade a sweep but must not send a user-action notification. Reserve
`user_action_required` for authentication, SMS, CAPTCHA, consent, a material
fact only the user can supply, or an uncertain external side effect that exact
readback cannot reconcile. Never self-repair by weakening evidence gates,
changing investment meaning, recipients, schedules, real-capital authority,
or an explicit human review boundary. If the exact-once process has exited,
preserve the original job and repair the next authorized resume path rather
than rerunning the same slot.

## One input, two conditional branches

Process each captured source item once. After normalization, reopen the latest evidence file from disk and bind the reading to its current SHA-256; never distill or decide from a cached chat summary or a stale context copy. Preserve one shared source/author/evidence identity, evaluate the investment-content gate, then evaluate these branches independently when supported:

1. **Current decision:** extract timely market-wide, sector, asset, and company signals; validate them against current facts; produce household advice and a Book KOL-US paper action. Use exactly `decision_status=actionable_signal` when supported or `decision_status=no_actionable_signal` with a concrete reason. For every no-action result, also set `reader_insight.status=useful` with a short evidence-bound `summary` and explicit `boundary`, or `reader_insight.status=none` with a concrete reason. `reader_insight.status=none` is the pre-publication `low_density` terminal and must not create a 灰常亮 report or reminder. Low confidence is not a reason to hide a relevant mention; do not invent a trade.
2. **Durable knowledge:** extract reusable causal reasoning, decision heuristics, exit lessons, and falsifiable candidate hypotheses from any author. Use exactly `knowledge_status=reusable_knowledge` when supported or `knowledge_status=no_reusable_knowledge` with a concrete reason. Do not create an empty distillation.

Both branches may complete, either branch may complete alone, or both may explicitly no-op. Do not make the user invoke another skill. Before writing knowledge, read [durable-knowledge.md](durable-knowledge.md) completely and follow its authority, provenance, schema, and author-specific posture rules.

Keep the layers separate:

- KOL claims are attributed source evidence.
- Current-market validation and recommendations are system judgment.
- Durable knowledge is an `authority=0` prior or candidate, never a deterministic rule.
- Household advice is advisory; Book KOL-US is paper-only; neither authorizes real-capital execution.

## Deployment boundary

- The always-on coordinator owns every 7x24 activity that is not bandwidth-heavy: Netdisk subscription/folder polling, metadata deduplication, cloud-to-cloud transfer, AI-job submission and polling, small transcript/image retrieval, OCR, market validation, household notification, and Book KOL-US paper execution.
- The broadband media worker owns only user-present triggers or unavoidable large local transfers: Xiaocao WeChat/Xiaoetong playback, livestream capture/compression, and any required local upload of a large video.
- Xiaocao's current manual trigger belongs on the broadband media worker. After it publishes a cloud video or lightweight artifact reference, the always-on coordinator resumes the job.
- Lv Xiaotong's irregular Baidu subscription updates must be polled automatically by the always-on coordinator. The user may help once with login, authorization, or page semantics, but must not be the recurring update detector.
- Prefer Netdisk-side transfer and enrichment. If a provider step truly requires moving a large file through a local machine, persist an explicit broadband handoff instead of silently pulling it through the always-on node.
- Development may colocate both roles on one Mac, but code and job state must preserve this placement boundary.
- The local WeChat node may discover registered official-account publications
  by exact publisher through stateless `wechat-cli` windows. It hands the sole
  writer only a self-hashed public URL plus identity metadata, with no article
  body, summary evidence, credentials, or large bytes. The writer uses the
  installed OpenCLI browser path to materialize immutable full-article
  Markdown and images. Every image is inspected once and its information is
  written as Markdown before the shared semantic gate; a CAPTCHA stops for
  same-session user verification and never triggers an HTTP/MCP retry loop.

## 灰常亮 report and viewpoint publication

- Use `灰常亮` as the canonical Chinese product name. `LiangHui` and `亮灰`
  are aliases for the same family Web App: 亮仔 is 垚亮 and 灰仔 is 菲菲.
  Never transliterate `LiangHui` as `梁辉`.
- One complete reader report represents one real KOL publication event. A
  multipart livestream is one report with ordered `source_parts`; two
  independent events remain two reports even when one batch processes them.
  A small PDF may join a video only when provider identity/version metadata and
  content evidence explicitly prove that both are parts of the same event.
  Filename similarity is never sufficient. A confirmed mixed-media episode
  has one source-neutral identity/version and ordered PDF/video `source_parts`;
  an independent report PDF remains its own publication event.
  Never derive report identity from a batch, filename, display author, ticker,
  or local thesis id.
- Before assigning publication-event identity, complete coverage review must
  find at least one attributable investment-decision claim. If it finds none,
  persist a durable `low_density` intake terminal with the audit and no-trade
  reason; create neither a 灰常亮 report nor a reminder claim. Media length alone
  never decides this gate.
- Publish every promoted event report that passes the Xiaocao completeness and
  safety gate to 灰常亮 through the existing family-authenticated MCP. The
  complete safe Markdown `report_body` is the authoritative reader content. A
  report may publish without longitudinal viewpoints; never manufacture
  viewpoints to fill the schema.
- `reader_insight` describes a promoted event's content value, while
  `alert_eligible` independently authorizes a new reminder. Information-rich
  live sessions use a permissive alert gate: current market posture,
  buy/sell/hold action, position boundary, direction choice, or actionable
  trigger is sufficient and need not reverse the previous session. Historical
  initialization, expired intraday commentary, report correction,
  methodology-only material, or pure confirmation may publish with
  `alert_eligible=false` and must not replay an earlier household notification
  or Book KOL-US action. Missing independent verification, no uniquely mapped
  instrument, low confidence, or a Book KOL-US `no_trade` result are not
  no-alert reasons when the source still contains current market posture or a
  current direction choice; keep those execution limits in the reminder
  boundary instead of demoting the event to `report_only`.
- Longitudinal `viewpoint`, `viewpoint_evaluation`, and `viewpoint_relation`
  records are optional Agent judgments. Keep every historical viewpoint,
  append later viewpoints with `replaces`, `refines`, or `coexists`, and make
  currentness explicit with an as-of evaluation. Lack of a counterexample
  never makes an old viewpoint current. 灰常亮 stores and displays these
  records; it does not create a second analysis layer or expire them itself.
- Every field shown directly to a family reader must be edited as coherent
  natural Chinese, regardless of KOL or source adapter. Report titles and
  summaries, viewpoint subjects and stances, evaluation bases, relation
  reasons, and explanatory lists must never expose internal enums,
  snake/kebab/camel tags, serialized arrays, raw ASR fragments, database
  identifiers, or English action labels. English is reserved for an official
  company/product name or a stock/ETF ticker such as `SpaceX` or `AAPL`.
  A viewpoint subject says clearly what the view concerns; its stance is a
  complete sentence that preserves the direction, condition, horizon, and
  material boundary supported by the source. This is a publication gate for
  every KOL path, not a cleanup rule tied to one author or keyword.
- Before publication, compare every reader-facing date, session label, and
  episode label against the immutable source identity, provider metadata, and
  transcript self-identification. A filename may contain transport decoration,
  but the Agent must not silently change an attributable label such as
  `盘前` into `盘中`. When those sources disagree or the transcript does not
  resolve the label, use neutral wording such as the date plus `直播` or
  `大师班`; never invent a more specific session identity. Re-run this check on
  the authoritative report readback before notification. A mismatch requires a
  same-report content-and-manifest CAS correction and never replays the prior
  reminder or Book action. Every new or corrected record `created_at` must be
  a real UTC ISO-8601 timestamp ending in `Z`; a local offset or a fabricated
  conversion is rejected before any 灰常亮 mutation.
- Author identity is reviewed data, never a name-based inference. The current
  recurring authors 吕晓彤, 路西法, and 小草 are male; refer to each author with
  `他/他的`, never `她/她的`. Semantic requests must carry the repository author
  profile, and report publication must fail closed on conflicting pronouns.
- Maintain each stable KOL as one Agent-owned projection of current complete
  viewpoints plus an archived history timeline. Re-evaluate on every new real
  publication event, when an explicit horizon/trigger/falsifier becomes due,
  when material market or fundamental evidence changes, or when the user asks
  for a refresh. Append a new evaluation rather than editing history; publish
  the complete prior manifest plus additions under content-and-manifest CAS.
  A KOL projection is not a synthetic publication report and never creates a
  reminder or Book action by itself. Periodic scheduling belongs to Ticket 07;
  Ticket 06 creates no recurring task.
- Every promoted semantic item must include one explicit
  `longitudinal_projection` decision. Use `status=promoted` only for
  attributable, decision-relevant claims whose subject, direction, horizon,
  conditions, evidence, and future evaluation boundary are all preserved;
  include one or more viewpoints plus an initial as-of evaluation using exactly
  `current|expired|invalidated|uncertain`. Use `status=none`, an empty
  viewpoint list, and a concrete reason for news fragments, quotations,
  examples, advertisements, unsupported inferences, or claims that cannot be
  evaluated later. A report-only event may still contain valid longitudinal
  viewpoints; alert eligibility never decides viewpoint visibility.
- Keep the authoritative article evidence and reader report as Markdown. The
  narrow `longitudinal_projection` object is a schema-validated internal
  sidecar for stable 灰常亮 records; never serialize it into reader Markdown.
  Each viewpoint evidence reference must resolve to the complete source claim
  inventory, and every initial viewpoint must publish atomically with one
  explicit currentness evaluation. Missing projection judgment fails closed;
  it never silently becomes an empty `viewpoint_ids` list.
- Before each `put_kol_record` and `publish_kol_report`, persist the exact
  request under a durable claim. An uncertain response must first use
  `get_kol_write_status`; a conflict must read `get_kol_record` and rebuild.
  Publish only the exact manifest. Persist the publication receipt and stable
  detail URL before a reminder can be claimed.
- A newly eligible publication event may create at most one concise,
  independently retryable Enterprise WeChat reminder. It leads with the most
  decision-important insight, follows with a coherent compact synthesis of the
  remaining important information, and ends with exactly one stable 灰常亮
  report link. It must be useful before the user opens the link, but it never
  duplicates the full report. Different events never merge reminders because
  a batch completed. A report correction uses the same stable URL and
  compare-and-swap hashes, and never replays an earlier reminder or Book
  action.

## Xiaocao capture

1. Start the existing sniffer from the `wx_channels_download` repository beside
   the active Xiaocao checkout (for example
   `/Users/bytedance/coding/wx_channels_download` on the capture node):
   `./wx_video_download_macos_arm64`. Never bind this workflow to another
   machine's absolute checkout path.
2. Verify `http://127.0.0.1:2022/api/status` before asking the user to play anything.
3. Arm a fresh Xiaocao job (source and author are fixed by this adapter):
   `PYTHONPATH=src python3 scripts/kol_capture.py arm`.
4. Ask the user to open the enterprise-WeChat card. For a protected evening replay, the user enters the password; once the target player appears, no continued playback or fixed wait is required. Never store the password in source or job state.
5. Poll with the returned job id and start the download. This must reproduce the `/download/live` **保存** action (`type=live_capture`, `compress=true`), never the raw `仅保存原片` path:
   `PYTHONPATH=src python3 scripts/kol_capture.py poll --job-id <id> --download`.
6. After `poll` records `status=downloaded`, verify the runtime-named `-compressed.mp4` exists and has nonzero size and duration. Then stop the exact `wx_video_download_macos_arm64` session gracefully with `Ctrl-C` so it restores the system proxy. Before any Netdisk/OpenCLI action, confirm the process is gone, ports 2022/2023 have no listener, `/api/status` is unavailable, and `scutil --proxy` reports `HTTPEnable`, `HTTPSEnable`, `ProxyAutoConfigEnable`, and `SOCKSEnable` all `0`. Treat cleanup failure as a hard block to enrichment/upload; do not kill unrelated applications merely because they retain `CLOSE_WAIT` or `CLOSED` sockets.
7. Re-run `poll` or `status` rather than starting over after interruption. The append-only ledger is `output/live/kol_capture_jobs.jsonl`.

Do not modify the dirty `wx_channels_download` repository. Treat its local API as an adapter.

For Ticket 03, prefer the resumable top-level surface over manually chaining
the steps above:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py run
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py run \
  --capture-job-id <id> \
  --opencli-session <stable-name> \
  --opencli-profile <connected-profile>
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py status
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py audit \
  --capture-job-id <id>
```

The first command emits the only playback prompt, and only after it has proven
the exact sniffer process healthy and persisted the candidate baseline. Later
invocations resume from the capture and enrichment ledgers. They must finish
compressed-media validation plus deterministic process/port/API/proxy cleanup
before preparing or advancing Netdisk. The broadband invocation owns the
large upload and then publishes a metadata-only cloud handoff; coordinator
invocations never read or download the large source video. Acceptance is
explicitly scoped by ownership. On the capture node, `audit` may derive a full
receipt from the capture, cleanup, upload, handoff, notification, and paper
ledgers when those ledgers are colocated. On the remote sole writer, importing
the self-hashed capsule persists one immutable `cloud_handoff_imported` receipt;
`run` and `audit` then use `scope=post_handoff`, treat the capsule as the
upstream boundary, and validate only remote-owned transcript, AI-note request,
decision, publication, exact-recipient reminder, and Book effects. The remote
audit must never reopen the local capture ledger, local cleanup receipt, or
source-video bytes. Each scope proves its owned external effects exactly once
and returns zero new external effects on rerun; end-to-end acceptance composes
the two receipts by handoff id and media SHA-256. Once those deterministic
receipts prove the reader-facing publication, the eligible reminder or legal
no-alert terminal, and the paper-only Book KOL-US terminal, a routine Ticket 03
run is `completed` with `next=none`. It must not enter
`awaiting_user_confirmation` merely because the report or acquisition adapter
changed. Human review is allowed only for an explicit evidence ambiguity, a
requested editorial correction, or a separately specified historical
aggregation gate. The `confirm` surface remains available solely to migrate an
already-persisted legacy `awaiting_user_confirmation` state; it never gates new
work and never authorizes replaying publication, reminder, or Book side effects.

## Enrichment boundary

- Require a completed runtime-named `-compressed.mp4`; do not retain or process the raw stream in the normal workflow. Text, images, web posts, and already-transcribed material bypass video enrichment and enter normalization directly.
- The required decision evidence is the complete `文稿` transcript read directly from the logged-in player DOM and persisted as immutable text. Ticket 02 also requires submitting `文稿笔记` generation, but its asynchronous completion is explicitly non-gating and is never polled as an acceptance condition. The AI note must never replace, shorten, reorder, or overwrite the transcript.
- Ticket 02's mandatory provider is `baidu_consumer_page`, orchestrated through the logged-in OpenCLI browser bridge and `scripts/kol_netdisk_video.py`:
  1. Run `prepare --video <runtime-named-compressed.mp4>`. It hashes and probes the exact local source and returns the stable job ID required by every later command; this local preparation has no browser side effect.
  2. Before asking the user for anything, run the OpenCLI doctor/profile checks and inspect the exact cloud folder through the logged-in page. A manually clickable tab or an empty session list is not proof. Do not use raw CDP, Computer Use, or absolute coordinates.
  3. Repeatedly run `advance-opencli --job-id <id> --opencli-session <stable-name> [--opencli-profile <profile>]`. Each invocation advances at most one durable external checkpoint or observes one asynchronous completion; it is a manual resumable stepper, not a batcher or scheduler. While transcript generation is pending, honor `next_poll_not_before` and use the runtime's fixed one-minute polling interval. Do not poll AI-note completion.
  4. The stepper scans every logged-in folder-API page and reconciles the exact basename only after a complete scan. If absent, it claims upload before mutation, opens the prepared source once, verifies size and SHA-256, and copies those bytes to a private temporary immutable snapshot with the exact target basename. Both direct OpenCLI and any fallback read that same verified snapshot, so the contract works through either a direct binary or an `npx` runtime. After the snapshot is complete, revalidate the real folder hash-route, mark only the current folder's file input with an unguessable one-shot selector, and install capture-phase route guards that block both input and change events if navigation occurs. Only when Chrome returns the specific `Not allowed` failure may it serve the snapshot from an unguessable `127.0.0.1` route; that one DOM action revalidates the folder both before and after fetching the snapshot, constructs a native DOM `File`, verifies its browser-reported size, and dispatches the file-input events. The marker, temporary path, and loopback URL are never persisted, and readiness still requires a later exact cloud-file proof.
  5. Before any player DOM mutation, validate the real `location.href` against the complete `/课程/自己的课/小草/<target-basename>` path, not just the basename. The stepper then activates `文稿`, waits for the semantic active-tab state, claims generation before the triggering interaction, and records requested/ready separately. An already-ready transcript is reconciled without regenerating it.
  6. The stepper then activates `笔记`, waits for the semantic active-tab state, and opens template `tpl_no=1` (`文稿笔记`) under an independent claim when needed. It must enter the `#tplModal` iframe, uniquely locate and click the visible `生成该笔记` button. The exact target/template/button-bound click dispatch records `ai_note_requested`; modal closure, `generating`, `ready`, note length, and note content are neither read nor required afterward. Do not wait for, poll, or require AI-note completion.
     Render transcript and AI-note DOM actions only from the versioned repository-owned Baidu Netdisk OpenCLI templates and require the returned template name/version to match before accepting their proof. The early `#tplModal` shell and visible submit button are not readiness: wait until exactly one `文稿笔记` row exists, that row carries the provider's selected marker, and exactly one enabled `生成该笔记` button is visible. Recheck all three conditions immediately before the one final click.
     If the provider action returns the exact pretrigger failure `Netdisk AI-note template submission failed`, the implementation has proved that no click was dispatched. Persist `ai_note_pretrigger_failed` before returning the error and permit at most one fresh claim and one later submission attempt. A legacy claim may enter that state only through `reconcile-ai-note-pretrigger` with the exact captured CLI command, exit code, error, claim timestamp, and remote task/turn identity. A dispatched click, missing original error, different evidence, or a second pretrigger failure remains fail-closed and can never use this recovery path.
     A replayed `ai_note_claimed` state never clicks again and never probes the
     AI-note body or completion state. Preserve the claim as the at-most-once
     trigger boundary and proceed directly to complete transcript capture; an
     AI-note outcome is not report evidence and cannot block analysis.
  7. On the Netdisk folder page, semantically dismiss the known `.nd-operate-guidance` operation-ad overlay through its unique `img[alt="close"]` control before upload inspection or reconciliation; never use click coordinates. As soon as the complete `文稿` is ready and AI-note submission has been recorded, the stepper opens the exact player and performs one atomic OpenCLI DOM action. It first closes a semantically identified advertisement dialog; if that exact ad overlay cannot be closed, it hides only that identified overlay. It then activates `文稿`, waits for content, and captures the unique initial `.ai-draft__wrap-list` as immutable UTF-8 text. Never refresh as an ad workaround.
  8. DOM capture is valid only when it proves `scrollTop=0`, nontrivial paragraph/sentence counts, the last sentence is already in DOM and below the initial viewport when content overflows, and there are no virtual/loading/load-more markers. Run `verify --audit-file <json>` with excerpts from the opening, middle, and ending thirds, bound to both source-video and transcript hashes.
  9. Build one canonical Ticket-01 source-neutral bundle from the emitted `analysis_request.json`, a judgment-only semantic draft, and a separate current market-evidence JSON by running `PYTHONPATH=src .venv/bin/python scripts/kol_semantic_bundle.py --analysis-request <path> --semantic-draft <path> --market-evidence <path>`. Only its validated `bundle_path` may return to the still-running writer; a hand-built or legacy-validated bundle is not a new-event builder. The persisted `ValidatedBundleReceipt` must exist before `decide` prepares any business effect. Publish the complete event report to 灰常亮 first. Only after its durable publication receipt may a newly eligible event fan out one concise reminder to the distinct `XIAOCAO_KOL_WECOM_USER_IDS` set (currently `Chen,FeiFei`): lead with the key insight, add the coherent compact synthesis, and end with exactly one stable report link, all within the 2,048-byte safe-send limit. Do not split the complete report across messages. The legacy chunked notifier is reconciliation-only for already-claimed historical sends. Before any makeup send, compare the recipient configuration time with the original send time and send only to a proven-missing recipient—never replay the full decision pipeline or duplicate a recipient that already succeeded. Completion requires the 灰常亮 receipt, the eligible event's all-recipient short-reminder receipt or a legal no-alert reason, and a result with `book=KOL-US`, `paper_only=true`, plus a fill or an explicit nonempty `no_trade.reason`.
     The delivery claim must hash the exact title/body bytes passed to the Relay.
     `reader_title` is the full report title. When the WeChat entry needs shorter
     copy, put its natural-language `title` and `summary` in `reader_reminder`;
     those fields participate in notification identity and cannot change the
     report identity.
     A publication wrapper must provide those bytes to the delivery ledger as an
     explicit message builder; it must never hash a generic delegate message and
     then silently substitute a different report reminder inside the sender.
     Sender exceptions append `notification_send_uncertain` before stopping. If
     an older validated all-recipient transport receipt contains byte-identical
     reader copy and the same stable report URL, a revised notification identity
     may consume that delivery through one content-alias receipt without calling
     the sender; a second or nonidentical match fails closed.
     Once the publication ledger already has a completed stable receipt, a
     coordinator resume reads that receipt before rebuilding any candidate and
     never republishes merely because a later decision bundle has reader-copy
     edits. The final reminder is still validated independently and must use
     natural reader copy. Ticket 03 acceptance treats one validated content
     alias as a valid notification authorization, with exactly one delivered
     receipt and zero new Relay calls.
     When the sole writer cannot reach the public Relay but the capture node can,
     keep the notification claim and final ledger on the sole writer. A local
     transport fallback is allowed only from a self-hashed, credential-free
     request that binds the source task, notification identity, final report,
     exact title/body/content hash, exact recipients, original failure, and an
     explicit missing-recipient confirmation. Run
     `scripts/kol_notification_transport.py <request.json>` on the configured
     transport node. It claims and receipts each recipient independently;
     successful recipients are never replayed, provably pre-connect failures
     may resume only for the missing recipient, and any uncertain result stops.
     Return the original self-hashed request together with the self-hashed
     all-recipient receipt to the sole writer. Record them with
     `scripts/kol_decisions.py --transport-request <request.json>
     --record-transport-receipt <receipt.json>`. The writer must validate both
     self-hashes, exact request/receipt bindings, the configured recipient set,
     and one matching prior `notification_send_claimed` plus
     `notification_send_uncertain` state before recording the existing
     notification identity as delivered
     before Ticket 03 may continue. A task message is the control plane; Git is
     only the code/contract transport and never carries runtime request files.
     Therefore the writer's task message must carry the complete
     credential-free request JSON, its file SHA-256, and its canonical
     self-hash, not only a remote filesystem path. The transport node must
     return the complete receipt JSON with its file SHA-256 and canonical
     self-hash. Repeated task messages with the same handoff id and hash are
     reconciliation requests owned by one control-plane coordinator; they
     never authorize a second Relay call, publication, or Book action.
     If reader-copy correction changes title/body after the original claim, a
     first-time request must include a self-hashed `content_revision` that binds
     the prior 16-character claim hash, replacement full content hash, current
     report content hash, and correction reference. Without that proof, changed
     content fails closed. A historical pair recorded before this field existed
     may replay only when one existing validated-transport event and one
     delivered event already bind the exact request handoff id and receipt hash;
     that migration replay writes nothing.
     Every code-sync task must copy the exact 40-character value produced by
     `git rev-parse HEAD`; never expand a short SHA manually. The receiver must reject a mismatch
     against the fetched branch before checkout, tests, or business recovery.
     Each cross-node progress message must also include one machine-readable
     stage capsule with `item_id`, `prerequisite_sha`, `completed_gate`, and
     `next_gate`. A later summary cannot skip an unresolved prerequisite, and
     a task-list/readback handler error never authorizes redispatch of the same
     business mutation.
- `capture-dom --opencli-session <session> [--opencli-profile <profile>]` invokes the same exact-player DOM contract directly. There is no `.doc` export, cloud-document, browser-download, or local Word-import path in Ticket 02.
- Each completed transition needs exact-target, timezone-aware, hash-bound evidence. Player query parameters are validated for basename binding and stripped before ledger storage. The append-only ledger stores no snapshot text, transcript content, query string, cookie, token, household position, or credential.
- Every external browser side effect has a durable pre-action claim. A new claim requires a fresh, at-most-30-minute persisted liveness/page proof; a capability failure blocks later claims until a new valid liveness record. A replayed or uncertain claim is read-only: inspect the real page and reconcile it, but never repeat upload, transcript generation, or AI-note submission blindly. Sequential reruns return the latest state and cannot regress a verified or decided job to prepared.
- `--reconcile-existing` is fail-closed and is valid only for stable generated content such as `transcript_ready` (and a separately observed already-ready AI note). It never records a requested state and never authorizes a click. User reports can tell the agent where to inspect, but only a fresh exact-target DOM snapshot can support reconciliation.
- If Codex browser policy rejects a fresh Netdisk DOM snapshot, record `capability-failure --surface <exact-surface> --reason browser_security_policy_denied`, then prefer the documented logged-in OpenCLI bridge. Do not use raw CDP, Computer Use, absolute coordinates, or a secret-bearing workaround.
- `scripts/kol_enrich_video.py` is an explicit `baidu_aasr` fallback for a separately authorized run. It never silently replaces a Netdisk job and cannot satisfy Ticket 02's mandatory Netdisk acceptance. Its transcript remains complete provider-order ASR with `pid=80006`, `smooth_text=0`, `filter_sensitive=0`, immutable raw results, and audio spot checks.
- If a deterministic provider or interface differs from its recorded contract, persist the failure and stop. Ask for only the smallest current login, authorization, CAPTCHA, or real-page clarification action; do not improvise or ask the user to repeat already-verified preparation.

## Lv Xiaotong direct subscription

- Ticket 04 has exactly one discovery/download provider: the ignored
  `xiaocao.yaml` values under `kol_intelligence.lv_xiaotong`, opened through the
  logged-in OpenCLI Browser Bridge in Google Chrome. The separately installed
  Codex browser connector may be hosted in Microsoft Edge; it is not the
  Ticket 04 OpenCLI session. Do not add subscription-message parsing,
  another link source, a raw HTTP client, Computer Use, or a second long-lived
  adapter.
- Codex's built-in browser can enumerate an already-open private-share tab but
  policy rejects DOM reads against the real `/s/...` page. Record this only as
  `browser_security_policy_denied`; never log the real URL/code, retry the same
  IAB read, ask for an IAB tab attachment, or switch browser-control mechanisms
  to evade the policy.
- The one-time bootstrap action is: the user opens the configured link in
  Google Chrome with the OpenCLI Browser Bridge installed, verifies that the
  file list is visible, and leaves that tab active. Then start the single
  resumable runner:
  `PYTHONPATH=src python3 scripts/kol_lv_subscription.py run --bootstrap-bind --opencli-session xiaocao-lv-subscription`.
  Later runs omit `--bootstrap-bind` and reuse the stable OpenCLI session.
- The runner completes a full recursive `/share/list` scan before updating the
  cursor. Parent-directory modification times are never a pruning gate because
  Baidu may leave a parent timestamp stale when a deeper child changes. Scan
  child directories in small bounded concurrent batches with a per-request
  timeout, then reuse that one complete in-memory listing within the same
  process, session, and profile for all pending small items instead of
  rescanning the share per item; the snapshot never crosses a runner boundary,
  and every item still validates its exact identity, version, name, size, and
  browser target plus its exact path. Ticket 04 and Ticket 05 reuse this same in-process
  snapshot; neither performs a second recursive Lv scan in the same sweep. It
  ignores video payloads, persists a source-version claim before each small
  text/image/PDF browser download, snapshots only the completed browser
  receipt, bypasses OCR for native UTF-8 text, and runs macOS Vision OCR once
  for images. The words `已失效` elsewhere in a valid page are not evidence of
  expiration: require an exact visible terminal UI or explicit provider error,
  and prefer successful share metadata plus complete `/share/list` evidence.
  A replayed/uncertain download claim may only reconcile the prior download
  event; it must never retrigger it.
- Small-file acquisition is unattended. Do not change the ordinary Chrome
  profile, its `prompt_for_download` preference, or global extensions. First
  apply target-scoped `Page.setDownloadBehavior` to the exact bound OpenCLI
  session and runtime-controlled inbox, and persist a credential-free command
  acknowledgement/readback. If OpenCLI explicitly rejects that CDP method,
  only claimed PDF and small UTF-8 text items may use the authenticated share
  page to request one signed link for their exact provider file id, name, path,
  size, identity, and version. Keep the signed URL/cookies/tokens in memory,
  stream only to the controlled inbox, and validate provider HTTPS host/path,
  content type, exact bytes, and SHA-256 before completing the original claim.
  This direct path never handles images or video. A native Save dialog or
  download prompt is internal recovery, never a user-action blocker or WeChat
  event; only login/authentication, SMS, CAPTCHA, or explicit authorization
  consent may ask the user. A claimed replay never performs another UI
  trigger.
- Before any small-item claim, discovery-only `wrong_share`, `wrong_origin`,
  `about:blank`, OpenCLI timeout/invalid JSON, or incomplete `/share/list` may
  reopen the configured page, back off, and retry the full read exactly once.
  Preserve the original and final credential-safe category/code/stage. This
  bounded authority never extends to download, transfer, publication,
  notification, or Book actions; uncertain side effects reconcile receipts.
- A `.pdf` is eligible only inside the configured small-file and page-count
  boundaries. Do not download it unconditionally. If provider directory,
  title date and summary semantics, mtime/version relation, and a verified
  complete video transcript jointly prove one companion, persist an exact
  `companion_suppressed` relationship receipt before acquisition and create no
  PDF claim, download, extraction, analysis, report, reminder, or Book effect.
  Otherwise preserve the claimed original PDF and SHA-256, extract text locally
  with `pypdf` and, when available, `pdfplumber`, and render every page with
  visual resources or insufficient native-text coverage using Poppler while
  recording page-level render/OCR hashes. A rendered page with insufficient OCR
  remains `visual_review_required` until the semantic bundle covers it.
  Malformed, encrypted, uncovered, unknown, or oversized PDFs fail closed.
  Replay reuses every relationship/download/extraction/semantic/publication/
  notification/Book receipt and creates no second effect.
- If a claimed small PDF reaches `provider_web_download_client_only` or the
  signed-link interceptor cannot recover it, keep the same acquisition claim
  and use owner-cloud fallback. Create or reuse only
  `/xiaocao/lv_subscription/<version>/`: zero exact owner matches permits one
  transfer, one exact name/size match resumes idempotently, and multiple
  matches fail closed. Success is the owner fsid/path/size readback, never a UI
  toast. Obtain the owner dlink and the same OpenCLI target's HttpOnly cookies
  in process memory only, stream HTTPS to the version inbox, and require HTTP
  200, exact size, PDF magic, and SHA-256. Signed URLs, cookies, and tokens must
  never enter argv, stdout, ledgers, or receipts. Video and oversized files are
  ineligible. A normal Save prompt or client-only response is internally
  recoverable; only auth, SMS, CAPTCHA, consent, or missing system permission
  may become a user-action blocker.
- A PDF analysis request lists only provider-metadata relation candidates. The
  semantic bundle must resolve `independent|companion` with content quotes and
  exact provider identity/version evidence. A companion also binds the related
  evidence SHA-256; publication then uses one source-neutral event and ordered
  mixed-media `source_parts`. Do not publish both a companion PDF and its video
  independently. Unresolved relation evidence remains pending, not guessed.
- Route Lv claims by product semantics, never by PDF/video type alone. The
  `会员直播` product is time-sensitive current decision evidence and follows the
  complete transcript -> current-fact validation -> one event report ->
  eligible reminder -> paper-only Book path. The `底层逻辑` product is case
  analysis, causal framework, and methodology. When it contains reusable
  reasoning but no current action, use `decision_status=no_actionable_signal`,
  `reader_insight.status=useful`, `knowledge_status=reusable_knowledge`, one
  report-only `底层逻辑` knowledge entry, no alert, and KOL-US
  `decision=not_applicable` with a reason. This durable-only route creates no
  Book row; lack of a direct buy/sell instruction is not `low_density`.

### 吕晓彤“马车”周期推荐池

- Treat an authoritative 吕晓彤 source title or reader-visible heading that
  identifies the product as `马车` as his **current-cycle core recommendation
  pool**. This is a stable user-provided author/product fact: apply it on later
  runs without asking again. Every ETF, stock, or theme listed in that `马车`
  is a current primary recommendation and a `must_surface` claim. Preserve the
  complete set and use role `primary_recommendation`; absence of a code,
  weight, entry, position size, or exit rule does not demote it to a generic
  watchlist.
- Keep product meaning and execution authority separate. Bind every listed
  member to the exact image/text evidence and named-asset inventory, and group
  them as one basket thesis only when their direction, horizon, and conditions
  agree. The report title, summary, and opening identify `马车` as the current
  cycle's core recommendation pool and name every member. Preserve an
  unspecified order and weight as unspecified; never invent a product code,
  internal ranking, allocation, entry, stop, or exit. The household conclusion
  treats the set as the priority research and screening universe, while a buy
  or allocation recommendation still requires its own evidence-bound execution
  conditions.
- Use `longitudinal_projection.status=promoted` for every complete current
  `马车` snapshot. The viewpoint subject is 吕晓彤's current-cycle core
  recommendation pool; its horizon ends when he publishes the next complete
  `马车` or explicitly changes the set. Compare the full member set with the
  latest current `马车` viewpoint. A new complete snapshot appends one new
  `current` viewpoint, appends an `expired` evaluation to the prior snapshot,
  and links the new viewpoint to the prior one with `replaces`. An explicit
  partial add/remove amendment uses `refines`. Keep the prior report,
  viewpoint, evaluations, and relations in history; the set diff must state
  additions, removals, and unchanged members.
- A newly observed current `马车` snapshot is a current direction choice and
  is `alert_eligible` when it is a new publication event. Its concise reminder
  leads with the core pool and any set diff, then states the missing execution
  conditions. A historical initialization, report correction, maintenance
  evaluation, or replay retains the stable report URL and creates no reminder
  or Book replay. Book KOL-US remains paper-only and acts only when a supported
  US-listed instrument and execution conditions exist; otherwise record the
  complete source signal and an explicit `no_trade` reason.

- Preserve the original underlying-logic evidence and normalized text with
  SHA-256, distill reusable material under `reference/experience/distilled/`,
  and route candidate hypotheses to the backlog with `authority=0`. Lv is an
  other author: this path cannot mutate Xiaocao `posture_current`,
  `REGIME_TIMELINE`, or deterministic strategy/parameters. Authority promotion
  requires the research harness and human gate. When one real event contains
  both current-decision and durable-knowledge claims, publish one report and
  route the claims into both branches; only current-decision claims may
  authorize an alert or Book action. Pure promotion, repetition, or evidence
  with no reusable reasoning may legally use `no_reusable_knowledge`.
- When the still-running command emits
  `subscription_analysis_input_required`, reopen the referenced immutable
  evidence and `analysis_request.json`, validate current market and household
  facts, and write the complete coverage matrix and decision judgment to a
  semantic draft while keeping current market facts in a separate market-
  evidence JSON. Run `scripts/kol_semantic_bundle.py` with all three files and
  write exactly its validated `{"bundle_path":"<absolute-json-path>"}` followed
  by a newline to that same process. Do not hand-build a new-event bundle, or
  exit and manually chain `poll`, `claim-download`, `ingest`, and `decide`.
- Completion requires a durable household notification outcome plus a
  paper-only Book KOL-US result for every processed item, except a pure
  durable-only `底层逻辑` report may complete with a reasoned `not_created`
  Book terminal. The notification
  outcome is delivered for a useful reader insight and suppressed with a
  reason only when there is no accurately relayable insight. A no-update run
  with no unfinished item prints nothing. After any interruption, rerun the
  same command: the durable manifest, download receipt, OCR result, analysis
  request, notification outcome, and paper decision resume without duplicate
  OCR, notification, or paper action.

## Lv Xiaotong and Lucifer cloud videos

- Ticket 05 has exactly two metadata entry points on the same logged-in Google
  Chrome OpenCLI Browser Bridge: the Ticket 04 configured Lv Xiaotong share
  and the private directory `/课程/路西法全套`. Do not use the Codex built-in
  browser, another share, raw CDP, Computer Use, coordinates, a direct HTTP
  client, marketplace search, or an automated purchase.
- Within one Ticket 07 sweep, Ticket 05 consumes Ticket 04's already-complete
  Lv snapshot rather than recursively scanning the same share again. A shared
  snapshot never bypasses exact per-item identity/version/name/size/target
  validation and never crosses a process boundary.
- Run one resumable coordinator command:
  `PYTHONPATH=src python3 scripts/kol_subscription_videos.py run --opencli-profile <connected-profile>`.
  Its default Lv, private-folder, and enrichment session is the already-bound
  `xiaocao-lv-subscription` session. Override a session only after explicitly
  binding and proving that exact Google Chrome OpenCLI session.
- A publication may consist of any number of source videos. Treat it as one
  logical episode, not one decision per file. Prefer explicit source metadata
  (`episode_id`, title, `part_index`, and optional declared count). Otherwise
  conservatively recognize common filename suffixes such as Chinese numerals,
  Arabic numbers, `Part`/`Segment`, `上/中/下`, or `A/B`. Automatic groups with
  an unknown final count must remain quiescent for at least five minutes before
  component work begins. Missing, duplicate, mixed-directory, or ambiguous
  part order is a surfaced pause; never guess or silently process one fragment.
  For arbitrary filenames, pass a small reviewed JSON manifest with
  `--episode-spec <path>` rather than renaming evidence or adding a source.
- Preserve every component provider identity, source path, version, size,
  order, transcript path, and transcript SHA-256. Assemble the verified
  component transcripts in source order into one immutable episode evidence
  file. Analyze that evidence once, publish one complete 灰常亮 event report,
  send at most one eligible short-link reminder, and write at most one Book
  KOL-US paper terminal for the episode. A new or
  changed component creates a new aggregate version; unchanged components and
  completed episode receipts cannot be replayed. If a legacy run already
  completed one or more fragments independently, pause the aggregate as
  `historical_component_receipts_require_reconciliation`; never auto-send a
  consolidated historical message or paper action. Historical component
  receipts prove that blind replay is forbidden; they do not prove that the
  complete aggregate has no new reader insight. A reviewed legacy episode may
  bind authenticated small component transcripts into one aggregate result.
  If that result contains an actionable signal or useful reader insight, it
  must stop at `awaiting_user_review` with no household or Book side effect;
  it may not use `suppressed` as a terminal. After explicit approval, use the
  normal event-publication path to create one aggregate-scoped 灰常亮 receipt,
  eligible short reminder, and Book terminal. `suppressed` is legal only when
  the complete aggregate has no accurately relayable insight. Historical
  review approval publishes the report with a legal no-alert reason and
  reconciles the existing Book result; it never replays either side effect.
  On replay, the durable review gate or receipt may repair missing derived
  manifest fields without changing a household or Book ledger. The legacy
  `approve-episode-review` command is retained only for reconciling an already
  claimed historical aggregate and must not be used as a new full-message
  delivery surface.
- For the latest Lv Xiaotong video goal, discovery, cloud transfer, transcript
  readiness, and analysis are checkpoints rather than success. Bind the
  terminal to the exact source identity and publication version. Mark the goal
  successful only after a complete 灰常亮 report has both its durable publication
  receipt and stable detail URL; surface that proof through Ticket 07
  `status`/`audit`.
- The first scan recursively baselines all history but makes only the latest
  real logical content unit from each source work-eligible. Later scans process
  only a new or changed standalone video or aggregate episode version.
  A no-update run prints nothing.
- Lv Xiaotong video handling is cloud-to-cloud. Persist a pre-action claim,
  reconcile an exact existing private copy by provider identity/path/size, or
  trigger one share-side save and persist its exact private receipt. Never
  download the source video locally. Lucifer videos are already private and
  enter enrichment in place. If either provider truly requires large local
  bytes, persist a broadband-worker handoff and stop.
- For the Lv share-side save, DOM evaluation may select the exact source and
  destination and mark the one visible `确定` control with a unique selector,
  but the final provider confirmation must use OpenCLI's native
  `browser <session> click <selector>` command. Persist the click claim before
  that command. Never use `element.click()` as confirmation proof; a timeout
  or ambiguous native-click result is side-effect-uncertain and must enter
  exact private-copy reconciliation before any retry.
- A triggered Lv save is unfinished until an exact private copy is observed.
  Reconcile the intended directory first, then a settled provider search by
  exact filename and byte size; fuzzy search rows with no exact match are a
  valid zero-match terminal, not a search timeout. After 30 minutes and a fresh
  exact zero-match proof, one recovery claim may repeat the same target save.
  Two reconciled trigger attempts without a copy become the structured
  `lv-cloud-transfer-not-materialized` user-action blocker. Never wait or
  retrigger indefinitely.
- When the hourly writer persists a cloud-transfer `wait_until`, resume it only
  at or after the bound deadline with the emitted `kol_daily.py
  resume-source-wait --source-adapter subscription_video --source-identity
  <exact-identity>` command. That command consumes only the exact item's narrow
  source surface; it does not drain the mailbox, discover another item, or
  start another hourly sweep.
- If an exact continuation reaches `structured_input` after the original stdin
  closes, run `kol_daily.py resume-source-input --source-adapter
  subscription_video --source-identity <exact-identity>` and return the
  validated bundle to that same process. The command rebuilds only the
  persisted request bindings and records the structured-input receipt; it does
  not run source discovery or a new sweep.
- If that process proves the exact decision, gray-report receipt, and Book
  terminal but fails while projecting the daily terminal, use
  `reconcile-source-terminal` for the exact identity. It performs readback
  only and records `external_business_effects_replayed=false`.
- Both sources use Ticket 02's exact-player transcript and `tpl_no=1` note
  contract. Register the cloud metadata version without inventing a payload
  hash, bind the player to the complete path, preserve the complete transcript
  as immutable evidence, and record `large_payload_local_bytes=0`.
- When the runner emits `subscription_video_analysis_input_required`, reopen
  the referenced transcript and SHA-256, build all seven coverage rows and the
  full entity inventory in a judgment-only semantic draft, write current market
  facts separately, and run `scripts/kol_semantic_bundle.py` against those two
  files plus the emitted request. Write only its validated
  `{"bundle_path":"<absolute-json-path>"}` followed by a newline to the same
  process. The bundle must use exactly
  `decision_status=actionable_signal|no_actionable_signal` and
  `knowledge_status=reusable_knowledge|no_reusable_knowledge`, include an
  explicit Xiaocao consensus/conflict/unrelated assessment, and state that the
  comparison cannot duplicate delivery or Book side effects.
- A semantically identical, same-author, same-title transcript may reuse prior
  household and paper receipts only after exact normalized-content proof and
  receipt reconciliation. It still gets a current coverage matrix and market
  validation; it must not resend or write another paper action.

## Resumable multi-source batches

Ticket 06 adds one coordination surface over the already verified Ticket
03/04/05 runners; it is not another source adapter:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_batch.py run \
  --spec <batch-spec.json> \
  --output-dir output/live/kol_batch
PYTHONPATH=src .venv/bin/python scripts/kol_batch.py status \
  --batch-id <stable-batch-id> \
  --output-dir output/live/kol_batch
PYTHONPATH=src .venv/bin/python scripts/kol_batch.py audit \
  --batch-id <stable-batch-id> \
  --output-dir output/live/kol_batch
PYTHONPATH=src .venv/bin/python scripts/kol_batch.py deliver-insight \
  --batch-id <stable-batch-id> \
  --insight <reviewed-insight.json> \
  --output-dir output/live/kol_batch
```

- A live batch spec includes one small `insight_path` JSON after the existing
  decision runners have produced the cross-source synthesis. It binds every
  child adapter to the immutable evidence and decision-result SHA-256, and
  contains the decision-priority conclusion, KOL consensus/conflict, system
  judgment, household action and Book KOL-US result. The coordinator validates
  those bindings; it never invents or recomputes source decisions.
- Batch synthesis may enrich each child report's analysis, but the batch is not
  a reader publication identity and cannot merge child reports, notification
  claims, or Book terminals. The legacy `deliver-insight` surface is retained
  only to reconcile already-claimed historical batch delivery; do not use it
  for a new delivery. New work publishes each real event independently to
  灰常亮 and, only after that event's publication receipt, may send its one short
  link reminder. A replay publishes and sends zero new side effects.
- Batch children retain the stable Ticket 03 capture/handoff identity, Ticket
  04 source/version identity, or Ticket 05 source/version identity. The
  append-only batch ledger stores priority, status, `next_poll_not_before`,
  retry count, failure reason and terminal receipt for each child; restart
  rebuilds only from that evidence.
- A Ticket 05 logical episode is still exactly one batch child. Its aggregate
  identity/version is immutable and its ordered `source_parts` preserves every
  component identity, version, source path, size, label, and index. Receipt
  reconciliation must prove the same complete part set was analyzed once,
  reached exactly one household terminal (`delivered` or legal `suppressed`),
  and reached exactly one Book terminal. The coordinator never expands the
  parts into duplicate notification or Book children; it never reads their video bytes.
- Never wait serially for one video. Each sweep advances at most one checkpoint
  per due child, so a ready image, text item or other video continues while an
  asynchronous child waits. Time-sensitive work starts at higher priority;
  five-minute aging raises older work until it becomes visible, preventing
  starvation.
- A transcript/AI child uses `wait_for_async_receipt=true`; registration writes
  the coordinator-owned durable checkpoint and `next_poll_not_before` into the
  append-only ledger. Never accept a caller-supplied request timestamp. The
  first poll occurs only after at least five minutes from that checkpoint. A
  still-pending child uses explicit exponential backoff; only that failed or
  due child is retried.
- Treat `low_density` and `duplicate` as explicit terminal dispositions.
  Treat `unauthorized`, `missing_evidence`, and `missing_market_data` as
  explicit paused dispositions. Do not hide any of them under a generic
  failure or retry an uncertain external claim.
- The coordinator may read only metadata, receipt JSON, images/small documents,
  complete transcripts and result payloads. Every child records
  `large_payload_local_bytes=0`, and the audit must prove coordinator source
  video bytes are zero. Xiaocao media remains behind its broadband handoff and
  subscription videos remain cloud-side.
- Receipt reconciliation is read-only. A completed Ticket 03/04/05 household
  or Book KOL-US receipt is imported under a durable reconciliation claim and
  cannot be replayed. A Book `filled` terminal is fail-closed unless it carries
  the existing runner's KOL-US identity, paper-only flag, idempotency key,
  ticker, side, price and quantity, bound to the immutable decision-result hash
  and watched Book ledger. Do not invent a second fill schema in the
  coordinator.
- Before accepting a batch, declare `watched_artifacts` with explicit roles for
  `cloud_transfer_claim`, `cloud_transfer_receipt`,
  `transcript_generation`, `ai_note_submission`,
  `household_notification`, and `book_kol_us_action`. The coordinator
  snapshots only small JSON/JSONL payloads and requires the complete role set,
  paths, sizes, line counts and hashes to remain unchanged across run,
  interruption, restart and replay. An empty or changed watcher set cannot
  pass audit.
- For a live acceptance, terminate the real runner while at least one child is
  unfinished, restart the exact same command, and require `audit` to show two
  runner starts, an interruption, one terminal receipt per child, no terminal
  regression, unchanged side-effect ledgers and zero new external effects.
- Ticket 06 creates no recurring Automation or 7x24 schedule. Deployment and
  scheduling belong to Ticket 07.

## Source-agnostic investment-claim coverage gate

This gate applies to every KOL source and every single-item or batch runner.
Source adapters may differ only in how they acquire and bind immutable
evidence. They must all call the same semantic extraction and coverage
contract before notification or Book effects.

First, build a complete **investment-thesis inventory** from the full
evidence. A thesis is `must_surface` if any one of these bases applies:

- the KOL makes a concrete investment recommendation;
- the passage could change portfolio exposure or risk control;
- it contains a market or sector view that could change a decision;
- it gives a thesis whose consequences could materially affect an asset,
  industry, market, or the user's capital.

These bases are an OR condition. Never require a named object, direction,
timing, position size, and risk boundary to appear together. Conditional,
low-confidence, unverified, or system-conflicting theses still surface with
their uncertainty attached. User holdings affect priority and linkage only;
they never restrict extraction.

Classify every investment-relevant mention as a primary recommendation,
alternative instrument, risk warning, supporting rationale, historical
example, analogy, quoted view, or unrelated mention. Pure advertisements and
promotions are excluded. Historical, analogy, quoted, and unrelated mentions
remain audit-visible but do not enter the reader briefing unless they also
carry an independent must-surface thesis. When a material role remains
ambiguous, surface it as uncertain instead of deleting it.

Group fragments into one **investment-thesis unit** only when subject,
direction, horizon, and conditions agree. Preserve different directions,
horizons, or conditions as separate units even when they concern the same
asset. Preserve conflicts and explicit revisions; never let a newer statement
silently erase an older conflicting one.

Second, after the inventory is complete, perform an independent semantic
reread of stable segments covering the entire immutable evidence. Every
segment is reviewed exactly once and classified as investment content,
non-investment content, or advertisement. Every investment segment must link
to one or more thesis units, and every thesis unit must link back to exact
quotes in its segments. Missing-thesis, incorrect-merge, and role-error
findings must be empty before the audit can pass. Keyword searches, asset-name
lists, action-word regexes, and the first summary are diagnostic warnings
only; they never decide importance and never prove completeness.

Rank the must-surface units by urgency, potential impact, specificity, and
user relevance. The ranking is decision-driven rather than structurally
market-first: a specific, time-sensitive recommendation may lead; a broad
market view may lead when it has greater decision impact. Low-priority,
high-density material must still be processed and cannot starve.

Before creating the decision bundle, build a private **trade-information coverage matrix** against the immutable transcript. This is an extraction-completeness checklist, not a keyword score. Bind every supported row to an exact evidence excerpt, its corrected reader-facing meaning, the applicable horizon, and any trigger or falsifier. Explicitly mark unsupported rows as absent instead of silently omitting them:

- **today's market diagnosis**: what happened in the current session, the present market phase, breadth/liquidity/risk appetite, and whether the author sees a tradable regime;
- **next-session playbook**: what to watch or do tomorrow, including opening/confirmation conditions, leadership tests, pullback requirements, chase prohibitions, and cancellation conditions;
- **next-several-session base case**: the expected path over the following days or weeks, likely continuation/divergence/rotation, and the observations that would overturn it;
- style and market-cap regime: trend versus short-term emotion, large versus small capitalization, and which style is not ready;
- market/board/sector hierarchy: broad market, board/theme leadership, and named instruments, without imposing reader order;
- position and risk budget: recommended exposure ranges, pacing, funding source, and risk-control limits;
- named-asset inventory: every materially discussed company, fund, index, commodity, or currency, including whether it is a primary candidate, alternative/ETF, comparison, negative example, historical example, or unrelated demonstration/promotion.

Apply the layers in this order: (1) preserve the KOL signal, (2) validate
current facts and market state, (3) assess household relevance, (4) map Book
KOL-US execution authority. A non-US asset, unavailable order type, stale
entry, low confidence, or `no_trade` outcome may change only layers 2-4. It
must never erase or demote a complete source signal from layer 1.

Build an **entity-resolution inventory** for every named or phonetic company, fund, index, and code before judgment:

- retain the raw ASR surface form privately for audit, but resolve the official current name, six-digit code, and exchange from authoritative current sources;
- if the mapping remains ambiguous, mark it unresolved and exclude it from actionable recommendations;
- keep the exact transcript `quote` for evidence validation; when it contains ASR name/code errors, also populate `reader_quote` with a faithful corrected transcription and never silently change the underlying claim;
- never expose Chinese-digit codes, garbled ASR names, bare internal symbols such as `688347.XSHG`, internal metric keys, or unverified name-code pairs in a household message;
- require a plain-language `reader_text` for every market fact that may be shown to the user.

If the source contains market, style, timing, or position statements,
`market_outlook` is mandatory and a single-stock signal cannot substitute for
it. Order the reader briefing by the decision-priority ranking. Surface every
primary candidate and meaningful alternative, or explicitly record its
non-actionable role and exclusion reason; do not let one executable instrument
erase the rest of the author's decision hierarchy.

## Judgment contract

- Preserve the KOL's claim, reasoning, horizon, asset scope, and falsifiers. A thesis does not expire merely because a day passed.
- Re-evaluate the thesis against current market facts at processing time; do not replay an old order blindly.
- Current-fact validation must distinguish external confirmation from source
  consistency. Record the authoritative source and as-of time for every fact
  presented as independently verified. If current data is unavailable, keep
  the KOL claim attributable, state the missing validation explicitly, and do
  not turn internal transcript consistency into a fact check. A source-only
  report may still publish when it has useful reader insight and makes no
  unsupported actionable recommendation, but its final quality review must
  mark the fact-validation depth as limited.
- When the sole writer lacks authoritative current market data and a material
  current-session claim needs verification, it must stop before publication
  and send one credential-free, self-hashed market-validation request to the
  capable node. The response must bind the request hash and record endpoint,
  parameters, trade date, selected rows, as-of time, and limitations. The
  writer validates that receipt and classifies each claim as supported,
  conflicting, or unresolved before publication; source consistency never
  substitutes for this handoff. A duplicate request with the same identity is
  read-only reconciliation and cannot cause duplicate API calls or later
  external side effects.
- Prioritize concrete, time-sensitive implications: the market phase and overall strategy, sectors to add/reduce/exit, specific opportunities, the causal chain, validity window, trigger, and falsifier. Generic textbook framing belongs only in the durable-knowledge branch.
- Treat holdings as context, not a search boundary. Surface strong opportunities outside current holdings and explain the funding or switching logic when relevant.
- In human-facing messages, name both the verified company/fund and its code, explain the source signal and causal chain in plain language, show the author and source date/type, and omit internal gates, enums, hashes, local filenames, serialized pipeline state, and raw ASR artifacts. Populate `reader_title` when the source title needs editorial cleanup; otherwise the renderer must remove transport-only date prefixes, extensions, and compression suffixes. Use coherent natural-language paragraphs, never tables. The KOL's valuable information must dominate; the system adds only material fact, background, conflict, or uncertainty notes. For `no_actionable_signal`, send a compact weak-signal card when `reader_insight.status=useful`: state the insight, link only genuinely relevant current household positions, and make the evidence boundary explicit. Do not expand it into unrelated market or portfolio analysis, and do not decide for the user whether to act.
- For dense spoken-video transcripts, keep the raw exact `quote` only in audit evidence and give every reader-visible claim a faithful `reader_quote` corrected from the surrounding context. Remove ASR misspellings, broken names, filler, repetition, and incomplete oral syntax without inventing a new thesis. The household message must lead with `KOL观点｜按逐字稿上下文校正`, then separately label `系统拆解｜对KOL逻辑的分析`, `系统核对｜仅补事实`, and `系统结论`. Never mix a system inference into the KOL section, never expose the dirty raw transcript as a substitute for faithful correction, and do not let a generic market-analysis scaffold bury the source's actual recommendation logic.
- Extract all relevant asset classes, but Book KOL-US may transact only US-listed equities and ETFs.
- Book KOL-US is paper-only. No margin, options, futures, short selling, or negative cash. Leveraged and inverse ETFs are allowed as cash instruments when the opportunity warrants them.
- Do not suppress good paper opportunities with arbitrary fixed sizing thresholds. Make sizing opportunity-dependent and explain concentration risk.
- Household recommendations are advisory only: state buy/add/hold/reduce/sell/wait, evidence, confidence, horizon, and falsifier. Never execute real-capital trades.

## Output contract

For every processed source item, first produce a durable content-value result.
For every promoted publication event, produce:

- source, author, title, publication/capture time, and evidence location;
- KOL claims separated from system synthesis;
- current-market validation and conflicts;
- market-wide outlook and overall strategy when the source supports them,
  ordered with all other theses by decision priority;
- household action recommendation and what would change it;
- Book KOL-US action or an explicit no-trade reason;
- `decision_status` and `knowledge_status`, including explicit no-op reasons;
- durable distillation path and routed hypothesis ids when knowledge was written;
- processing state and next asynchronous checkpoint.
- an explicit longitudinal projection decision, including evidence-bound
  viewpoints and initial evaluations when supported, or a concrete no-viewpoint
  reason when not supported.

Do not publish a `low_density` source item to 灰常亮. Publish every complete
promoted event to 灰常亮 after the coverage and safety gate. For a new event with
`reader_insight.status=useful` and explicit alert eligibility, send only one
concise de-duplicated reminder per real publication event and fan it out to
both currently configured household recipients (`Chen` and `FeiFei`). Lead
with the key insight, add a compact synthesis of the other important
information, and end with the stable 灰常亮 report link. Confidence and Book
KOL-US trade eligibility do not decide content visibility. If the promoted
event is informative but not currently alert-eligible, or is
historical/reconciled, persist the report and legal no-alert reason but create
no reminder claim.

The final reader briefing is created only after the coverage audit passes.
Each must-surface thesis appears exactly once in its ranked KOL prose. System
paragraphs cannot replace or hide KOL theses. If the UTF-8 payload exceeds
2,048 bytes, keep the full lossless briefing in 灰常亮 instead of splitting it
across Enterprise WeChat. Compress the reminder to its key insight, compact
synthesis and report link; never truncate or weaken the full report to fit the
transport limit.
