# 02 — 百度网盘真实视频确定性富化到双输出闭环

**What to build:** Use the logged-in OpenCLI bridge on the real Baidu Netdisk consumer page to take a runtime-named `-compressed.mp4` through exact upload-or-existing-file reconciliation, real `文稿` generation, direct complete-transcript DOM capture, content verification, and ticket 01's household-advice and Book KOL-US outputs. Submit separate `tpl_no=1` `文稿笔记` generation, record submission, and continue without polling its asynchronous completion. AI-note content can never replace, shorten, reorder, or overwrite the complete transcript used for decisions. Repeat the completed behaviour on a second real video. Do not implement `.doc` export/download, live capture, subscriptions, batch processing, or scheduling in this ticket.

**Blocked by:** Nothing. The Codex browser denial remains recorded as a surface-specific capability failure. The logged-in OpenCLI extension/daemon provides the permitted DOM route; no direct/raw CDP client, Computer Use, absolute coordinates, token extraction, or desktop workaround was used. OpenCLI's own official `browser upload` command uses its extension/CDP bridge internally and is recorded as `upload_transport=opencli_cdp`.

**Status:** completed

**Progress:** Ticket 01 is already completed. Ticket 02 now has both its original 6/28 + 7/19 acceptance and a fresh 7/20 two-video confirmation. The current upload implementation uses only OpenCLI's official browser `upload` command; the loopback DOM-blob fallback was deleted after the OpenCLI extension's `Allow access to file URLs` permission was enabled. A 536,259,685-byte original video then uploaded through `opencli_cdp`, reached real `文稿`, submitted `tpl_no=1`, exposed its complete initial DOM transcript, passed opening/middle/ending verification, delivered a household reminder, and recorded a Book KOL-US result. A distinct 7/20 morning video completed the same transcript-to-decisions seam. `.doc` export/download is not part of the implementation or acceptance path.

**2026-07-21 implementation closeout:** Commit `d43e724` removes the nonstandard loopback/blob route, passes the persistent source path to OpenCLI's official file-input upload, gives only long browser uploads the extended command timeout, and records sanitized `opencli_cdp` permission or command failures. The live route proved that neither the 536 MB source nor a smaller derivative was required to be compressed again.

## Acceptance

- [x] Runtime-named `-compressed.mp4` inputs are hashed and probed without a hard-coded dated implementation; an existing cloud copy is reused only after exact basename binding.
- [x] The mandatory provider remains `baidu_consumer_page`; it never silently switches to AASR, raw CDP, Computer Use, absolute coordinates, or an unbound API result.
- [x] Every actual browser side effect has a durable pre-action claim. Upload, transcript generation, and `tpl_no=1` AI-note submission are separate checkpoints; AI-note completion is non-gating and is not polled.
- [x] The fresh 6/28 derivative was uploaded when absent, reached real `文稿` ready, then reached direct DOM capture without export or download.
- [x] DOM capture opens the exact player, handles only semantically identified ad overlays, never refreshes, and proves a unique complete initial transcript: `scrollTop=0`, nontrivial counts, final sentence already present below the viewport, no virtual/loading/load-more markers, and immutable text hash.
- [x] Content verification checks opening, middle, and ending excerpts and binds the audit to both video and transcript SHA-256.
- [x] Each accepted real transcript reaches ticket 01's source-neutral contract, a real household WeChat receipt, and `book=KOL-US`, `paper_only=true`, with either a fill or explicit nonempty `no_trade.reason`.
- [x] The second-video path has distinct real video, DOM capture, transcript, audit, decision, household, and Book KOL-US evidence.
- [x] Browser/API failures append explicitly without persisting cookies, tokens, page query strings, transcript text, or household positions in the Netdisk ledger.
- [x] No live capture, subscription access, batch ingestion, or scheduling was implemented, and tickets 03–07 were not modified by this ticket.
- [x] Focused tests, full suite, two-axis review, and the implementation commit are recorded in the completion handoff.

## Verification evidence

### Current 7/20 two-video confirmation — official OpenCLI upload and direct DOM decisions

- Committed compact evidence: `reference/experience/acceptance/kol_netdisk_720_opencli_cdp_e2e_2026-07-21.json`. Runtime market evidence and decision bundles remain under `output/live/kol_intelligence_20260720/`.
- **7/20 morning:** job `kol-netdisk-b80732abb1d9dfc7`; video SHA-256 `b80732abb1d9dfc79a396b9c86ebc89438ee06246302508baaedfd703fded64a`; 85,731,827 bytes; 2,200.561644 seconds. Direct DOM capture produced 3,552 characters, 29 paragraphs, and 433 sentences; transcript SHA-256 `c56a7d94c2d7b3ebfff09241c23b73039f3d45bf914e0fafe54e184a47e2ac01`; DOM-capture SHA-256 `f7c57ff6f3b785051c6f31fe4657e5e9a808e31892efc5bb9279181a2ba0b6eb`; audit SHA-256 `6ff6f485d16cf73fcfcb93376af5f82b07e542d8b606851d23d057a2f1f8f757`.
- The morning decision is `wait`: do not chase a technology gap-up until active leadership, breadth, and earning effect confirm. Household delivery has a real relay receipt; Book KOL-US is paper-only `no_trade` because the source provides no unambiguous US ticker/current-price/trigger. Its sequential rerun returned `idempotent_replay=true`.
- **7/20 review, official upload path:** job `kol-netdisk-ceccb41344432ae8`; original source SHA-256 `ceccb41344432ae840466efc8a87245f4b95b16e664ca32d2dd02b57141d82af`; 536,259,685 bytes; 5,408 seconds. `opencli browser ... upload` attached the persistent original at `11:02:25+08:00`; exact cloud presence was reconciled at `11:03:39`; real `文稿` was ready at `11:14:31`.
- The review DOM capture at `11:14:55` produced 13,984 characters, 101 paragraphs, and 1,514 sentences with `scrollTop=0`, the last node already present below the viewport, and no virtual/loading/load-more marker. Transcript SHA-256 `b677d27e0666e2e081e66a20d44c40db5b1cf76184167f3b1f3ae19b7c3e14a0`; DOM-capture SHA-256 `633b1f68c597130321876647522b0c40897d4f1f86dbf4db1c5790f6b4b6acfc`; audit SHA-256 `2f49e0fdf2ac6b369f41413158fd09e68948aaf921d871bb6bac4a36bb7919b1`.
- The review decision is `wait`: the decline and margin-financing flush are not complete. Household delivery has a distinct real relay receipt; Book KOL-US is paper-only `no_trade` because the signal is A-share-only and supplies no US ticker/current-price/trigger. Its sequential rerun also returned `idempotent_replay=true`.
- Fresh market validation at `2026-07-21T11:07:35+08:00`: 1,932 advancing versus 3,499 declining names; compute chips `-4.31%`, electronics `-5.72%`, communications `-3.38%`, and Huawei technology `-2.97%`. After both replays, the shared decision output contains exactly two household outbox rows and two Book KOL-US decision rows.
- Both knowledge branches explicitly returned `knowledge_status=no_reusable_knowledge`: the two videos reconfirm existing XH-042/XH-044 and current Xiaocao posture rather than adding a duplicate authority-0 hypothesis.

The earlier 6/28 and 7/19 evidence below is retained as historical exact-target upload/reuse coverage. Its loopback upload event describes the runtime used at that time; it is no longer present in the current implementation.

### Fresh real video 628 — upload, real 文稿 DOM, decisions

- Local source: `/private/tmp/20260628 大师班专场-ticket02-final-runtime-v3-20260720-compressed.mp4`; isolated acceptance ledger `output/live/kol_netdisk_enrichment_ticket02_final_v3/events.jsonl`; job `kol-netdisk-ae83a04afdc99894`.
- Video SHA-256 `ae83a04afdc9989467dd754434d5156c00eb5f3a7e3ded012f104e91f9d3d48c`; 624.082474 seconds; 41,539,718 bytes.
- Exact cloud basename was absent before mutation. The prepare-bound source was re-hashed from one descriptor and copied to a private immutable same-basename snapshot used by both the standard OpenCLI attempt and loopback fallback. Loopback DOM-file upload was submitted at `2026-07-20T18:13:00+08:00`; the exact uploaded file was reconciled at `18:13:35` and its already-available real `文稿` was observed at `18:13:58`; `tpl_no=1` AI-note submission was recorded at `18:18:43` and was not polled.
- Complete-render proof at `18:18:59`: 2,014 characters, 17 paragraphs, 247 sentences, `scrollTop=0`, last sentence present below the initial viewport, no virtual/loading/load-more markers. Transcript SHA-256 `42b126d37fcf16b549102b12cfe0c6da50b54e27582a3ce7d2511733921b6b27`; DOM-capture SHA-256 `9a5cd441b538926a5d2fd765345b7db4a9f204f4bce6dbdc438c31738f5c5fe5`.
- Opening/middle/ending audit SHA-256 `f957908501f4f35f00f0b59d85fdb5d8e9427f68ef5bc8a9b70b0273935fb49e`, bound to both source and transcript hashes.
- Household reminder was delivered with receipt `wecom-relay://ok/4ec310…/3153ecceb5c5031a`; Book outcome is `book=KOL-US`, `paper_only=true`, `status=no_trade`, idempotency key `431fb1…`. Reason: the source's A-share storage-chip next-day condition had expired and supplied no unambiguous US ticker, current price, or still-valid trigger.
- Final state is `decided`. The current market check at `2026-07-20T15:05:54+08:00` showed 1,740 advancing and 3,709 declining names; AI, compute-chip, and digital-tech category returns were all negative, so the old conditional-long signal was invalidated rather than replayed.

### Second real video 719 — current implementation rerun

- Source: `/Users/bytedance/Downloads/鹅直播视频/20260719 大师班专场(晚18：00开播)-compressed.mp4`; isolated acceptance ledger `output/live/kol_netdisk_enrichment_ticket02_second_v3/events.jsonl`; job `kol-netdisk-be3e15d292b984e0`.
- The exact existing cloud video was reconciled without upload. Final code observed the complete transcript, recorded a fresh `tpl_no=1` submission at `18:18:13`, and continued directly to DOM capture without polling AI-note completion.
- Complete-render proof at `18:18:28`: 33,160 characters, 225 paragraphs, 3,363 sentences, `scrollTop=0`, final sentence initially below the viewport, no virtual/loading/load-more markers. Transcript SHA-256 `4ac93b6aa5c60e3fded7f103e89d58b4c8e7caa2516210d238d38d4f9fc37c76`; DOM-capture SHA-256 `b1b9e8c580a195a6fd5a1c6ec1e08f960604258ed2ae303e0b1fac2dfe46b260`; audit SHA-256 `38ee9816d2f82538d704140cc2cfe7723cb72e2c2fa8c084f2a8d752356289d8`.
- Household reminder was delivered with receipt `wecom-relay://ok/57f4e7…/e2dedfa7c497fa70`; Book outcome is `book=KOL-US`, `paper_only=true`, `status=no_trade`, idempotency key `b961d7…`. Reason: the A-share small-tech candidate had not triggered and provided no unambiguous US ticker/current-price pair.
- Final state is `decided`; a sequential rerun returned `idempotent_replay=true` without duplicate delivery or Book entry.

### Committed acceptance inputs

- `reference/experience/acceptance/kol_netdisk_628_audit_2026-07-20.json`
- `reference/experience/acceptance/kol_netdisk_628_decision_2026-07-20.json`
- `reference/experience/acceptance/kol_netdisk_719_final_audit_2026-07-20.json`
- `reference/experience/acceptance/kol_netdisk_719_final_decision_2026-07-20.json`
- `reference/experience/acceptance/kol_netdisk_market_2026-07-20T1505.json`

### Validation and review

- Both isolated ledgers contain exactly the required semantic events. Neither contains `.doc`/export/download events, AI-note completion polling, raw snapshot text, page query strings, cookies, tokens, or credentials.
- Claim replay tests prove that an uncertain upload, transcript, or AI-note claim can only reconcile real page state and cannot repeat a side effect. Current upload tests re-hash the prepared source descriptor, reject a source changed before submission, keep the persistent source path available to OpenCLI/Chromium's asynchronous upload, give the 536 MB route a bounded 300-second command timeout, and durably record sanitized `file_access_denied` or `browser_command_failed` evidence without storing the raw diagnostic.
- Full player paths are verified before every DOM mutation; same-basename/wrong-directory tests fail before ad handling or tab activation. Folder inspection walks all pages and rejects an incomplete scan. Official upload is bound to the expected folder and a one-shot marked file input before OpenCLI receives the verified persistent source path; no loopback/blob upload code remains.
- Advertisement handling clicks a semantically identified close control first and hides only the same still-visible identified ad overlay; it never refreshes the player.
- Current focused KOL acceptance (`test_kol_netdisk_enrichment`, enrichment, delivery, household, capture, and skill structure): `80 passed`. Project-venv full suite: `759 passed, 31 failed`; every failure is in the already-completed Ticket 01 `tests/test_kol_decisions.py`, whose fixed `checked_at=2026-07-19T18:00:00+08:00` fixture crossed the production 24-hour freshness gate. `compileall`, `py_compile`, `git diff --check`, targeted credential scan, and both 7/20 real-run idempotency checks passed. Ruff is not installed in either the project or system Python environment, so no Ruff result is claimed for this closeout.
- Initial Spec and Standards reviews found the AI-note bypass, dirty historical acceptance chain, incomplete player-path binding, replayed side effects, mutable upload source, first-page-only inspection, overly broad ad fallback, and upload-route race/failure-ledger gaps. All findings were fixed and regression-tested; the final Spec and Standards reviews reported no actionable findings.

## Scope notes

- The direct DOM transcript is the canonical Ticket 02 path. `.doc` export, cloud-document download, and local Word parsing were removed from code, CLI, tests, skill instructions, and acceptance criteria.
- Knowledge branch result for the fresh 6/28 source: `knowledge_status=no_reusable_knowledge`; its trend-tail, wait-for-confirmation, and exit-on-failure lessons duplicate existing Xiaocao priors, so no authority-0 hypothesis was added.
- Ticket 03–07 work remains untouched and out of scope.
