---
name: kol-intelligence
description: Capture, resume, enrich, analyze, route, and distill high-density KOL investment content for Xiaocao. Use for WeChat/Xiaoetong capture, Baidu Netdisk transcript recovery, text/image/transcript processing, timely market and portfolio decisions, household WeChat advice, paper-only Book KOL-US actions, or durable multi-author investment-knowledge distillation. One invocation evaluates both the current-decision and reusable-knowledge branches; either branch may explicitly produce no output when the source does not support it.
---

# KOL Intelligence

Keep every run resumable. Prefer deterministic local APIs, CLIs, and logged-in browser DOM automation. Computer Use is not a default or fallback implementation: the Baidu desktop experiment showed it is too slow and unreliable for this workflow. Consider it only through a separately reviewed exception after API, CLI, and browser-DOM approaches have all been concretely disproved.

## One input, two conditional branches

Process each high-density item once. After normalization, reopen the latest evidence file from disk and bind the reading to its current SHA-256; never distill or decide from a cached chat summary or a stale context copy. Preserve one shared source/author/evidence identity, then evaluate these branches independently:

1. **Current decision:** extract timely market-wide, sector, asset, and company signals; validate them against current facts; produce household advice and a Book KOL-US paper action. Use exactly `decision_status=actionable_signal` when supported or `decision_status=no_actionable_signal` with a concrete reason. Do not invent a trade.
2. **Durable knowledge:** extract reusable causal reasoning, decision heuristics, exit lessons, and falsifiable candidate hypotheses from any author. Use exactly `knowledge_status=reusable_knowledge` when supported or `knowledge_status=no_reusable_knowledge` with a concrete reason. Do not create an empty distillation.

Both branches may complete, either branch may complete alone, or both may explicitly no-op. Do not make the user invoke another skill. Before writing knowledge, read [durable-knowledge.md](references/durable-knowledge.md) completely and follow its authority, provenance, schema, and author-specific posture rules.

Keep the layers separate:

- KOL claims are attributed source evidence.
- Current-market validation and recommendations are system judgment.
- Durable knowledge is an `authority=0` prior or candidate, never a deterministic rule.
- Household advice is advisory; Book KOL-US is paper-only; neither authorizes real-capital execution.

## Deployment boundary

- The always-on coordinator owns every 7x24 activity that is not bandwidth-heavy: Netdisk subscription/folder polling, metadata deduplication, cloud-to-cloud transfer, AI-job submission and polling, small transcript/image retrieval, OCR, market validation, household notification, and Book KOL-US paper execution.
- The broadband media worker owns only user-present triggers or unavoidable large local transfers: Xiaocao WeChat/Xiaoetong playback, livestream capture/compression, and any required local upload/download of a large video.
- Xiaocao's current manual trigger belongs on the broadband media worker. After it publishes a cloud video or lightweight artifact reference, the always-on coordinator resumes the job.
- Lv Xiaotong's irregular Baidu subscription updates must be polled automatically by the always-on coordinator. The user may help once with login, authorization, or page semantics, but must not be the recurring update detector.
- Prefer Netdisk-side transfer and enrichment. If a provider step truly requires moving a large file through a local machine, persist an explicit broadband handoff instead of silently pulling it through the always-on node.
- Development may colocate both roles on one Mac, but code and job state must preserve this placement boundary.

## Xiaocao capture

1. Start the existing sniffer from `/Users/bytedance/coding/wx_channels_download`:
   `./wx_video_download_macos_arm64`.
2. Verify `http://127.0.0.1:2022/api/status` before asking the user to play anything.
3. Arm a fresh job:
   `PYTHONPATH=src python3 scripts/kol_capture.py arm --source xiaocao --author 小草`.
4. Ask the user to open the enterprise-WeChat card and play the target stream. For a protected evening replay, the user enters the password; never store it in source or job state.
5. Poll with the returned job id and start the download. This must reproduce the `/download/live` **保存** action (`type=live_capture`, `compress=true`), never the raw `仅保存原片` path:
   `PYTHONPATH=src python3 scripts/kol_capture.py poll --job-id <id> --download`.
6. Re-run `poll` or `status` rather than starting over after interruption. The append-only ledger is `output/live/kol_capture_jobs.jsonl`.

Do not modify the dirty `wx_channels_download` repository. Treat its local API as an adapter.

## Enrichment boundary

- Require a completed runtime-named `-compressed.mp4`; do not retain or process the raw stream in the normal workflow. Text, images, web posts, and already-transcribed material bypass video enrichment and enter normalization directly.
- The required enrichment child is a complete transcript. An already-present AI note may be retained as optional sibling evidence, but it must never gate, replace, shorten, reorder, or overwrite the transcript.
- Ticket 02's mandatory provider is `baidu_consumer_page`, orchestrated through the logged-in OpenCLI browser bridge and `scripts/kol_netdisk_video.py`:
  1. Run `prepare --video <runtime-named-compressed.mp4>`. It hashes and probes the exact local source and returns the stable job ID required by every later command; this local preparation has no browser side effect.
  2. Before any browser side effect, inspect the existing login, cloud video, transcript, and AI note. Prove DOM control and persist `liveness --surface opencli`; a manually clickable tab or tab list alone is not enough. Record a surface-specific policy denial before switching to the documented OpenCLI route. Do not use raw CDP, Computer Use, or absolute coordinates.
  3. Reconcile the exact basename from a fresh `/disk/main` row or an exact `/pfile/video?path=.../<target-basename>` player binding. If present, record `video_ready --source-mode existing`; if absent, persist `claim --action upload`, upload with the browser file chooser, visibly verify the exact row, then record `video_ready --source-mode uploaded`. Never create a duplicate before checking.
  4. If a fresh `/pfile/video` DOM snapshot already proves the exact target's complete transcript is ready, record `transcript_ready --reconcile-existing` directly from `video_ready`; do not claim or click transcript generation. Otherwise persist `claim --action transcript` immediately before clicking the one visible control that starts complete `文稿`/subtitle generation. Record `transcript_requested` only after the player visibly shows the request/processing state, and `transcript_ready` only after the same target visibly shows completion.
  5. Activate `文稿` and run `capture-dom --opencli-session <session>`. Accept only one complete `.ai-draft__wrap-list` with `scrollTop=0`, a nontrivial paragraph/sentence count, the last sentence already present below the initial viewport, and no virtual/loading/load-more markers. The command binds the exact player URL, immutable transcript text, render proof, source video, and SHA-256. A partial or virtualized transcript fails closed.
  6. Run `verify --audit-file <json>` with excerpts from the opening, middle, and ending thirds of the captured transcript, bound to both source-video and transcript hashes.
  7. Create one ticket-01 source-neutral bundle whose `evidence_path` is that verified transcript, then run `decide --bundle <json>`. Completion requires an actual household WeChat receipt and a result with `book=KOL-US`, `paper_only=true`, plus a fill or an explicit nonempty `no_trade.reason`.
- If an AI note is already present, fresh target-scoped DOM proof may record `ai_note_ready --reconcile-existing` as optional sibling evidence. Do not generate it merely to unblock capture; transcript readiness is sufficient.
- The older export → exact cloud `.doc` → download → `import-download` chain remains a compatibility path when initial full-DOM rendering cannot be proven. It is not required after successful `capture-dom`; the AI note still cannot replace the transcript.
- Each completed transition needs exact-target, timezone-aware, hash-bound evidence. Player query parameters are validated for basename binding and stripped before ledger storage. The append-only ledger stores no snapshot text, transcript content, query string, cookie, token, household position, or credential.
- Every external browser side effect has a durable pre-action claim. A new claim requires a fresh, at-most-30-minute persisted liveness/page proof; a capability failure blocks later claims until a new valid liveness record. If a call is interrupted after the claim, inspect the real page and reconcile it; do not repeat the click blindly. Sequential reruns return the latest state and cannot regress a verified or decided job to prepared.
- `--reconcile-existing` is fail-closed and is valid only for the stable generated children `transcript_ready` and `ai_note_ready`. It never records requested/generating, export, cloud-document, or download states, and never authorizes a click. User reports can tell the agent where to inspect, but only a fresh exact-target DOM snapshot can support reconciliation.
- If Codex browser policy rejects a fresh Netdisk DOM snapshot, record `capability-failure --surface <exact-surface> --reason browser_security_policy_denied`, then prefer the documented logged-in OpenCLI bridge. Do not use raw CDP, Computer Use, absolute coordinates, or a secret-bearing workaround.
- `scripts/kol_enrich_video.py` is an explicit `baidu_aasr` fallback for a separately authorized run. It never silently replaces a Netdisk job and cannot satisfy Ticket 02's mandatory Netdisk acceptance. Its transcript remains complete provider-order ASR with `pid=80006`, `smooth_text=0`, `filter_sensitive=0`, immutable raw results, and audio spot checks.
- If a deterministic provider or interface differs from its recorded contract, persist the failure and stop. Ask for only the smallest current login, authorization, CAPTCHA, or real-page clarification action; do not improvise or ask the user to repeat already-verified preparation.

## Judgment contract

- Preserve the KOL's claim, reasoning, horizon, asset scope, and falsifiers. A thesis does not expire merely because a day passed.
- Re-evaluate the thesis against current market facts at processing time; do not replay an old order blindly.
- Prioritize concrete, time-sensitive implications: the market phase and overall strategy, sectors to add/reduce/exit, specific opportunities, the causal chain, validity window, trigger, and falsifier. Generic textbook framing belongs only in the durable-knowledge branch.
- Treat holdings as context, not a search boundary. Surface strong opportunities outside current holdings and explain the funding or switching logic when relevant.
- In human-facing messages, name both the company/fund and its code, explain the source signal and causal chain in plain language, and omit internal gates, enums, hashes, and serialized pipeline state.
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

Notify on every processed high-density item, not only when Book KOL-US trades.
