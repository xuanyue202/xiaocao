---
name: kol-intelligence
description: Deterministically enrich runtime-named KOL videos through logged-in Baidu Netdisk transcript DOM, verify complete evidence, notify the household portfolio, and update the paper-only Book KOL-US.
---

# KOL Intelligence

Keep every run resumable. Prefer deterministic local APIs, CLIs, and logged-in browser DOM automation. Computer Use is not a default or fallback implementation: the Baidu desktop experiment showed it is too slow and unreliable for this workflow. Consider it only through a separately reviewed exception after API, CLI, and browser-DOM approaches have all been concretely disproved.

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
- Extract all relevant asset classes, but Book KOL-US may transact only US-listed equities and ETFs.
- Book KOL-US is paper-only. No margin, options, futures, short selling, or negative cash. Leveraged and inverse ETFs are allowed as cash instruments when the opportunity warrants them.
- Do not suppress good paper opportunities with arbitrary fixed sizing thresholds. Make sizing opportunity-dependent and explain concentration risk.
- Household recommendations are advisory only: state buy/add/hold/reduce/sell/wait, evidence, confidence, horizon, and falsifier. Never execute real-capital trades.

## Output contract

For every processed high-density item, produce:

- source, author, title, publication/capture time, and evidence location;
- KOL claims separated from system synthesis;
- current-market validation and conflicts;
- household action recommendation and what would change it;
- Book KOL-US action or an explicit no-trade reason;
- processing state and next asynchronous checkpoint.

Notify on every processed high-density item, not only when Book KOL-US trades.
