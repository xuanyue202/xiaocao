---
name: kol-intelligence
description: Capture, resume, enrich, analyze, route, and distill high-density KOL investment content for Xiaocao. Use for WeChat/Xiaoetong capture, Baidu Netdisk transcript recovery, text/image/transcript processing, timely market and portfolio decisions, household WeChat advice, paper-only Book KOL-US actions, or durable multi-author investment-knowledge distillation. One invocation evaluates both the current-decision and reusable-knowledge branches; either branch may explicitly produce no output when the source does not support it.
---

# KOL Intelligence

Keep every run resumable. Prefer deterministic local APIs, CLIs, and logged-in browser DOM automation. Computer Use is not a default or fallback implementation: the Baidu desktop experiment showed it is too slow and unreliable for this workflow. Consider it only through a separately reviewed exception after API, CLI, and browser-DOM approaches have all been concretely disproved.

## One input, two conditional branches

Process each high-density item once. After normalization, reopen the latest evidence file from disk and bind the reading to its current SHA-256; never distill or decide from a cached chat summary or a stale context copy. Preserve one shared source/author/evidence identity, then evaluate these branches independently:

1. **Current decision:** extract timely market-wide, sector, asset, and company signals; validate them against current facts; produce household advice and a Book KOL-US paper action. Use exactly `decision_status=actionable_signal` when supported or `decision_status=no_actionable_signal` with a concrete reason. For every no-action result, also set `reader_insight.status=useful` with a short evidence-bound `summary` and explicit `boundary`, or `reader_insight.status=none` with a concrete reason. Low confidence is not a reason to hide a relevant mention; do not invent a trade.
2. **Durable knowledge:** extract reusable causal reasoning, decision heuristics, exit lessons, and falsifiable candidate hypotheses from any author. Use exactly `knowledge_status=reusable_knowledge` when supported or `knowledge_status=no_reusable_knowledge` with a concrete reason. Do not create an empty distillation.

Both branches may complete, either branch may complete alone, or both may explicitly no-op. Do not make the user invoke another skill. Before writing knowledge, read [durable-knowledge.md](references/durable-knowledge.md) completely and follow its authority, provenance, schema, and author-specific posture rules.

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

## Xiaocao capture

1. Start the existing sniffer from `/Users/bytedance/coding/wx_channels_download`:
   `./wx_video_download_macos_arm64`.
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
invocations never read or download the large source video. After decisions,
`audit` derives its acceptance receipt from the capture, Netdisk, notification,
and paper ledgers. It must prove each external side effect exactly once and
return zero new external side effects on rerun before user confirmation.

## Enrichment boundary

- Require a completed runtime-named `-compressed.mp4`; do not retain or process the raw stream in the normal workflow. Text, images, web posts, and already-transcribed material bypass video enrichment and enter normalization directly.
- The required decision evidence is the complete `文稿` transcript read directly from the logged-in player DOM and persisted as immutable text. Ticket 02 also requires submitting `文稿笔记` generation, but its asynchronous completion is explicitly non-gating and is never polled as an acceptance condition. The AI note must never replace, shorten, reorder, or overwrite the transcript.
- Ticket 02's mandatory provider is `baidu_consumer_page`, orchestrated through the logged-in OpenCLI browser bridge and `scripts/kol_netdisk_video.py`:
  1. Run `prepare --video <runtime-named-compressed.mp4>`. It hashes and probes the exact local source and returns the stable job ID required by every later command; this local preparation has no browser side effect.
  2. Before asking the user for anything, run the OpenCLI doctor/profile checks and inspect the exact cloud folder through the logged-in page. A manually clickable tab or an empty session list is not proof. Do not use raw CDP, Computer Use, or absolute coordinates.
  3. Repeatedly run `advance-opencli --job-id <id> --opencli-session <stable-name> [--opencli-profile <profile>]`. Each invocation advances at most one durable external checkpoint or observes one asynchronous completion; it is a manual resumable stepper, not a batcher or scheduler. While transcript generation is pending, honor `next_poll_not_before` and use the runtime's fixed one-minute polling interval. Do not poll AI-note completion.
  4. The stepper scans every logged-in folder-API page and reconciles the exact basename only after a complete scan. If absent, it claims upload before mutation, opens the prepared source once, verifies size and SHA-256, and copies those bytes to a private temporary immutable snapshot with the exact target basename. Both direct OpenCLI and any fallback read that same verified snapshot, so the contract works through either a direct binary or an `npx` runtime. After the snapshot is complete, revalidate the real folder hash-route, mark only the current folder's file input with an unguessable one-shot selector, and install capture-phase route guards that block both input and change events if navigation occurs. Only when Chrome returns the specific `Not allowed` failure may it serve the snapshot from an unguessable `127.0.0.1` route; that one DOM action revalidates the folder both before and after fetching the snapshot, constructs a native DOM `File`, verifies its browser-reported size, and dispatches the file-input events. The marker, temporary path, and loopback URL are never persisted, and readiness still requires a later exact cloud-file proof.
  5. Before any player DOM mutation, validate the real `location.href` against the complete `/课程/自己的课/小草/<target-basename>` path, not just the basename. The stepper then activates `文稿`, waits for the semantic active-tab state, claims generation before the triggering interaction, and records requested/ready separately. An already-ready transcript is reconciled without regenerating it.
  6. The stepper then activates `笔记`, waits for the semantic active-tab state, and opens template `tpl_no=1` (`文稿笔记`) under an independent claim when needed. It must enter the `#tplModal` iframe, uniquely locate and click the visible `生成该笔记` button, and then prove that the template modal is no longer visible and the note iframe has entered `generating` or `ready`. A direct `genNoteByTpl` postMessage, a click-dispatched return value, or a synthetic "已提交" snapshot is not submission proof. Only the confirmed UI transition records `ai_note_requested`; do not wait for, poll, or require later AI-note completion.
  7. On the Netdisk folder page, semantically dismiss the known `.nd-operate-guidance` operation-ad overlay through its unique `img[alt="close"]` control before upload inspection or reconciliation; never use click coordinates. As soon as the complete `文稿` is ready and AI-note submission has been recorded, the stepper opens the exact player and performs one atomic OpenCLI DOM action. It first closes a semantically identified advertisement dialog; if that exact ad overlay cannot be closed, it hides only that identified overlay. It then activates `文稿`, waits for content, and captures the unique initial `.ai-draft__wrap-list` as immutable UTF-8 text. Never refresh as an ad workaround.
  8. DOM capture is valid only when it proves `scrollTop=0`, nontrivial paragraph/sentence counts, the last sentence is already in DOM and below the initial viewport when content overflows, and there are no virtual/loading/load-more markers. Run `verify --audit-file <json>` with excerpts from the opening, middle, and ending thirds, bound to both source-video and transcript hashes.
  9. Create one ticket-01 source-neutral bundle whose `evidence_path` is that verified transcript, then run `decide --bundle <json>`. KOL delivery must call the notifier with `audience="kol"` and fan out once to the distinct `XIAOCAO_KOL_WECOM_USER_IDS` set (currently `Chen,FeiFei`). The relay REST `/send` path does not inherit the wecom-app extension's long-text chunking, so the notifier must losslessly split the complete title plus body at semantic boundaries into UTF-8 chunks of at most 2,048 bytes, preserve order, and require every chunk for every recipient to return `ok` before writing one aggregate delivery receipt. One successful recipient or chunk is not completion. Before any makeup send, compare the recipient configuration time with the original send time and send only to a proven-missing recipient—never replay the full decision pipeline or duplicate a recipient that already succeeded. Completion requires the all-recipient household WeChat receipt and a result with `book=KOL-US`, `paper_only=true`, plus a fill or an explicit nonempty `no_trade.reason`.
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
  cursor. It ignores video payloads, persists a source-version claim before
  each small text/image browser download, snapshots only the completed browser
  receipt, bypasses OCR for native UTF-8 text, and runs macOS Vision OCR once
  for images. A replayed/uncertain download claim may only reconcile the prior
  download event; it must never retrigger it.
- When the still-running command emits
  `subscription_analysis_input_required`, reopen the referenced immutable
  evidence and `analysis_request.json`, validate current market and household
  facts, build the complete coverage matrix and source-neutral decision bundle,
  then write exactly `{"bundle_path":"<absolute-json-path>"}` followed by a
  newline to that same process. Do not exit and manually chain `poll`,
  `claim-download`, `ingest`, and `decide`.
- Completion requires a durable household notification outcome plus a
  paper-only Book KOL-US result for every processed item. The notification
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
- Run one resumable coordinator command:
  `PYTHONPATH=src python3 scripts/kol_subscription_videos.py run --opencli-profile <connected-profile>`.
  Its default Lv, private-folder, and enrichment session is the already-bound
  `xiaocao-lv-subscription` session. Override a session only after explicitly
  binding and proving that exact Google Chrome OpenCLI session.
- The first scan recursively baselines all history but makes only the latest
  real video from each source work-eligible. Later scans process only a new or
  changed provider identity/version. A no-update run prints nothing.
- Lv Xiaotong video handling is cloud-to-cloud. Persist a pre-action claim,
  reconcile an exact existing private copy by provider identity/path/size, or
  trigger one share-side save and persist its exact private receipt. Never
  download the source video locally. Lucifer videos are already private and
  enter enrichment in place. If either provider truly requires large local
  bytes, persist a broadband-worker handoff and stop.
- Both sources use Ticket 02's exact-player transcript and `tpl_no=1` note
  contract. Register the cloud metadata version without inventing a payload
  hash, bind the player to the complete path, preserve the complete transcript
  as immutable evidence, and record `large_payload_local_bytes=0`.
- When the runner emits `subscription_video_analysis_input_required`, reopen
  the referenced transcript and SHA-256, build all seven coverage rows and the
  full entity inventory, then write `{"bundle_path":"<absolute-json-path>"}`
  followed by a newline to the same process. The bundle must use exactly
  `decision_status=actionable_signal|no_actionable_signal` and
  `knowledge_status=reusable_knowledge|no_reusable_knowledge`, include an
  explicit Xiaocao consensus/conflict/unrelated assessment, and state that the
  comparison cannot duplicate delivery or Book side effects.
- A semantically identical, same-author, same-title transcript may reuse prior
  household and paper receipts only after exact normalized-content proof and
  receipt reconciliation. It still gets a current coverage matrix and market
  validation; it must not resend or write another paper action.

## Trade-information coverage gate

Before creating the decision bundle, build a private **trade-information coverage matrix** against the immutable transcript. This is an extraction-completeness checklist, not a keyword score. Bind every supported row to an exact evidence excerpt, its corrected reader-facing meaning, the applicable horizon, and any trigger or falsifier. Explicitly mark unsupported rows as absent instead of silently omitting them:

- **today's market diagnosis**: what happened in the current session, the present market phase, breadth/liquidity/risk appetite, and whether the author sees a tradable regime;
- **next-session playbook**: what to watch or do tomorrow, including opening/confirmation conditions, leadership tests, pullback requirements, chase prohibitions, and cancellation conditions;
- **next-several-session base case**: the expected path over the following days or weeks, likely continuation/divergence/rotation, and the observations that would overturn it;
- style and market-cap regime: trend versus short-term emotion, large versus small capitalization, and which style is not ready;
- market/board/sector hierarchy: broad market first, then board/theme leadership, then named instruments;
- position and risk budget: recommended exposure ranges, pacing, funding source, and risk-control limits;
- named-asset inventory: every materially discussed company, fund, index, commodity, or currency, including whether it is a primary candidate, alternative/ETF, comparison, negative example, historical example, or unrelated demonstration/promotion.

Build an **entity-resolution inventory** for every named or phonetic company, fund, index, and code before judgment:

- retain the raw ASR surface form privately for audit, but resolve the official current name, six-digit code, and exchange from authoritative current sources;
- if the mapping remains ambiguous, mark it unresolved and exclude it from actionable recommendations;
- keep the exact transcript `quote` for evidence validation; when it contains ASR name/code errors, also populate `reader_quote` with a faithful corrected transcription and never silently change the underlying claim;
- never expose Chinese-digit codes, garbled ASR names, bare internal symbols such as `688347.XSHG`, internal metric keys, or unverified name-code pairs in a household message;
- require a plain-language `reader_text` for every market fact that may be shown to the user.

If the source contains market, style, timing, or position statements, `market_outlook` is mandatory and a single-stock signal cannot substitute for it. The **market-level conclusion must lead** the notification title and first section, ordered as: today's diagnosis, next-session playbook, next-several-session base case, style/position guidance, and only then sectors and individual instruments. Surface every primary candidate and meaningful alternative, or explicitly record its non-actionable role and exclusion reason; do not let one executable instrument erase the rest of the author's decision hierarchy.

## Judgment contract

- Preserve the KOL's claim, reasoning, horizon, asset scope, and falsifiers. A thesis does not expire merely because a day passed.
- Re-evaluate the thesis against current market facts at processing time; do not replay an old order blindly.
- Prioritize concrete, time-sensitive implications: the market phase and overall strategy, sectors to add/reduce/exit, specific opportunities, the causal chain, validity window, trigger, and falsifier. Generic textbook framing belongs only in the durable-knowledge branch.
- Treat holdings as context, not a search boundary. Surface strong opportunities outside current holdings and explain the funding or switching logic when relevant.
- In human-facing messages, name both the verified company/fund and its code, explain the source signal and causal chain in plain language, show the author and source date/type, and omit internal gates, enums, hashes, local filenames, serialized pipeline state, and raw ASR artifacts. Populate `reader_title` when the source title needs editorial cleanup; otherwise the renderer must remove transport-only date prefixes, extensions, and compression suffixes. For `no_actionable_signal`, send a compact weak-signal card when `reader_insight.status=useful`: state the insight, link only genuinely relevant current household positions, and make the evidence boundary explicit. Do not expand it into unrelated market or portfolio analysis, and do not decide for the user whether to act.
- For dense spoken-video transcripts, keep the raw exact `quote` only in audit evidence and give every reader-visible claim a faithful `reader_quote` corrected from the surrounding context. Remove ASR misspellings, broken names, filler, repetition, and incomplete oral syntax without inventing a new thesis. The household message must lead with `KOL观点｜按逐字稿上下文校正`, then separately label `系统拆解｜对KOL逻辑的分析`, `系统核对｜仅补事实`, and `系统结论`. Never mix a system inference into the KOL section, never expose the dirty raw transcript as a substitute for faithful correction, and do not let a generic market-analysis scaffold bury the source's actual recommendation logic.
- Extract all relevant asset classes, but Book KOL-US may transact only US-listed equities and ETFs.
- Book KOL-US is paper-only. No margin, options, futures, short selling, or negative cash. Leveraged and inverse ETFs are allowed as cash instruments when the opportunity warrants them.
- Do not suppress good paper opportunities with arbitrary fixed sizing thresholds. Make sizing opportunity-dependent and explain concentration risk.
- Household recommendations are advisory only: state buy/add/hold/reduce/sell/wait, evidence, confidence, horizon, and falsifier. Never execute real-capital trades.

## Output contract

For every processed high-density item, produce:

- source, author, title, publication/capture time, and evidence location;
- KOL claims separated from system synthesis;
- current-market validation and conflicts;
- market-wide outlook and overall strategy when the source supports them, before individual sectors or stocks;
- household action recommendation and what would change it;
- Book KOL-US action or an explicit no-trade reason;
- `decision_status` and `knowledge_status`, including explicit no-op reasons;
- durable distillation path and routed hypothesis ids when knowledge was written;
- processing state and next asynchronous checkpoint.

Notify on every processed high-density item that has `reader_insight.status=useful`, regardless of confidence and regardless of whether Book KOL-US trades. A weak but accurately attributable asset mention must not be swallowed: label its confidence and provenance boundary instead. If `reader_insight.status=none`, persist the evidence, no-op reason, and paper result, but suppress the household notification. For a sent KOL message, use one de-duplicated fan-out to both currently configured household recipients (`Chen` and `FeiFei`), with fail-closed all-recipient success.
