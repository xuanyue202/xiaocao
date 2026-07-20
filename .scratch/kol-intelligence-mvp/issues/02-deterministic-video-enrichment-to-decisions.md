# 02 — 百度网盘真实视频确定性富化到双输出闭环

**What to build:** Use the logged-in OpenCLI browser bridge on the real Baidu Netdisk consumer page to take a runtime-named `-compressed.mp4` through upload-or-existing-file reconciliation, complete transcript readiness, deterministic complete-DOM capture, local verification, and ticket 01's household-advice and Book KOL-US outputs. Browser side effects and their asynchronous results are separate durable states. When the initial `文稿` DOM is proven complete, direct DOM capture is the primary path; explicit export/download remains a compatibility path for pages that cannot prove complete initial rendering. An already-present AI note may be reconciled as an optional sibling but can never gate, replace, shorten, reorder, or overwrite the transcript. Repeat the completed behaviour on a second real video. In the target deployment, Netdisk reconciliation, cloud AI work, small-document retrieval, analysis, notification, and paper execution belong to the 7×24 coordinator; any unavoidable large local upload belongs to the broadband media worker and crosses the boundary only through durable job/artifact references.

**Blocked by:** Nothing. The Codex browser denial remains recorded as a surface-specific capability failure. The logged-in OpenCLI extension/daemon provides the permitted DOM route; no raw CDP, Computer Use, absolute coordinates, token extraction, or desktop workaround was used.

**Status:** completed

**Progress:** Ticket 01 is completed in commits `f892c86`, `a49462b`, and `8e92126`. Ticket 02 now has two real `baidu_consumer_page` jobs in `decided`: the requested 717 video and the corrected 719 video. OpenCLI 1.8.6 reads the already logged-in page, proves exact target URLs, reconciles the existing transcripts without regeneration, observes the existing AI notes as optional siblings, rejects virtualized/partial transcript DOM, writes immutable hash-bound text, validates opening/middle/ending excerpts, reads fresh market and household context, sends a real household message, and records a paper-only Book KOL-US fill or no-trade. Three-attempt bounded retry handles transient read-only OpenCLI timeouts; failures are appended and later success clears transient error fields. The export/download state machine remains tested for compatibility but is not invoked after successful complete-DOM proof. No Computer Use or ticket 03–07 work was performed.

## Acceptance

- [x] Runtime-named `-compressed.mp4` inputs are hashed and probed without a hard-coded dated implementation; existing Netdisk copies are reused only after exact target binding.
- [x] The provider remains `baidu_consumer_page`; it never silently switches to AASR, raw CDP, Computer Use, absolute coordinates, or an unbound API result.
- [x] Every actual browser side effect requires a durable pre-action claim. These two jobs reconciled already-ready transcripts and merely observed existing AI notes, so no generation/export click was repeated.
- [x] Completed page transitions record exact basename, canonical state, observation time, sanitized path, and snapshot SHA-256; exact player query basenames are validated before query stripping.
- [x] Both real pages visibly reached complete transcript ready; their already-present AI notes remained optional sibling evidence and did not gate transcript capture.
- [x] Direct capture proves the transcript is initially fully rendered: unique list, `scrollTop=0`, nontrivial counts, below-viewport last sentence already in DOM, no virtual/loading/load-more markers, exact immutable text hash. Legacy export/download remains a fail-closed compatibility path.
- [x] Content verification proves opening, middle, and ending excerpts and binds the audit to both video and transcript SHA-256.
- [x] Each verified transcript reached ticket 01's source-neutral contract, a real household WeChat receipt, and a `book=KOL-US`, `paper_only=true` explicit no-trade outcome.
- [x] The second real video has distinct video, DOM-capture, transcript, audit, decision-bundle, household, and Book KOL-US evidence.
- [x] Browser/API/interface failures append explicitly without secrets, cookies, query strings, household positions, or transcript content entering the Netdisk ledger.
- [x] The coordinator can resume from cloud video plus lightweight job/artifact references; large local upload remains assigned to the broadband media worker when needed.
- [x] No live capture, subscription access, batch ingestion, or scheduling was implemented; no files under tickets 03–07 were modified.
- [x] Focused tests, full suite, two-axis review, requirement evidence, and implementation commit are recorded below.

## Verification evidence

### Real video 717

- Source: `/Users/bytedance/Downloads/鹅直播视频/20260717 盘前大师班直播(7月17日)-compressed.mp4`; job `kol-netdisk-a3c24ce8f0841ed4`.
- Video: SHA-256 `a3c24ce8f0841ed44eb46593b599ca576556617b79497cde9eccce14c1f45e81`; 2,192.547945 seconds; 86,388,665 bytes.
- Existing cloud children were reused without regeneration. OpenCLI complete-render proof: 3,849 characters, 32 paragraphs, 468 sentences, `scrollTop=0`, last sentence present below the initial viewport, and no virtual/loading/load-more marker.
- Transcript SHA-256 `790eaede3d920f31e9842b83e31f56ba28d98d7a0e685690258fd4ba89522d2e`; DOM-capture SHA-256 `192bb4fb2ce77c637c2f02ade5102819d655f7a25252eaa458b1d00151fc5f38`; three-position audit SHA-256 `6183b743f560d69a774508a3a6e75504d0fc811e440617003f630a6667d96e22`.
- Household receipt: `wecom-relay://ok/93e48db878dbf512e6c5cb973bad99aead17d7afa8661a9aa342bb0a316c4766/c34827dca68a2087`.
- Book outcome: `book=KOL-US`, `paper_only=true`, `decision=no_trade`, idempotency key `97cc…`; reason: the source described only an A-share repair/small-position setup and supplied no unambiguous US-listed target, price, or trigger.
- Final state `decided`; a sequential rerun returned `idempotent_replay=true`.

### Real video 719

- Source: `/Users/bytedance/Downloads/鹅直播视频/20260719 大师班专场(晚18：00开播)-compressed.mp4`; job `kol-netdisk-be3e15d292b984e0`.
- Video: SHA-256 `be3e15d292b984e0d71b1ba9adc25b293de4e1152cdfe24d9870a1ba5078e79b`; 6,315.42268 seconds; 516,505,681 bytes. The cloud player showed 01:45:16 and the existing transcript/AI note were reused without regeneration.
- OpenCLI complete-render proof: 33,160 characters, 225 paragraphs, 3,363 sentences, `scrollTop=0`, last sentence present below the initial viewport, and no virtual/loading/load-more marker.
- Transcript SHA-256 `4ac93b6aa5c60e3fded7f103e89d58b4c8e7caa2516210d238d38d4f9fc37c76`; DOM-capture SHA-256 `f8f620919ae0e0c5c924502cba8e8da8f80792d1d595b77eef6767e5b4c1e5b5`; three-position audit SHA-256 `38ee9816d2f82538d704140cc2cfe7723cb72e2c2fa8c084f2a8d752356289d8`.
- Household receipt: `wecom-relay://ok/0c7d254a58fbfd41e57c3ad086f739997204b8b76cde47ac08f9dadbeed9e2de/a994892fe0ca1f0e`.
- Book outcome: `book=KOL-US`, `paper_only=true`, `decision=no_trade`, idempotency key `6b32…`; reason: the A-share small-cap-technology thesis had not completed its trigger and supplied no unambiguous US-listed target/price pair.
- Final state `decided`; a sequential rerun returned `idempotent_replay=true`.

### Shared validation

- Fresh market snapshot at `2026-07-20T10:38:36+08:00`: advancing 2,846, declining 2,575, positive/negative level-seven counts both zero. The two recommendations therefore treated the tape as limited repair, not a confirmed strong trend.
- Both decision bundles passed source-neutral preflight with a fresh LiangHui MCP household-context read. The committed acceptance inputs are `reference/experience/acceptance/kol_netdisk_717_decision_2026-07-20.json`, `reference/experience/acceptance/kol_netdisk_719_decision_2026-07-20.json`, and `reference/experience/acceptance/kol_netdisk_market_2026-07-20T1038.json`.
- Ledger audit found no access/refresh token, cookie, `BDUSS`, `STOKEN`, auth material, household context/positions, transcript quote, or page query string. Only sanitized paths, hashes, states, and delivery/book summaries are durable.
- Decision branch: both sources were actionable for current household posture. Knowledge branch: `knowledge_status=no_reusable_knowledge` for both because the small-position/wait-for-mainline lessons duplicate existing Xiaocao priors and add no novel falsifiable hypothesis; no knowledge file was changed.
- Exact staged-index snapshot (`git checkout-index --all --prefix=<fresh-temp>/`): `tests/test_kol_enrichment.py tests/test_kol_netdisk_enrichment.py` -> `63 passed` in 1.45 seconds; full `tests/` -> `734 passed` in 15.61 seconds; `git diff --cached --check` -> clean.
- Final Spec review: no remaining actionable findings. It confirmed optional/non-gating AI notes, one atomic OpenCLI URL/tab/text/render read, consistent policy documentation, corrected 717/719 evidence, both required outputs, and no Ticket 03–07, subscription, batch, scheduling, raw-CDP, or Computer Use implementation.
- Final Standards review: all three P1 findings were fixed. No blocking finding remained; the only P2 judgement call is future maintainability work around the broad Netdisk service and repeated provider decision-finalization logic, intentionally not expanded inside Ticket 02. It also confirmed no staged scope leak or sensitive evidence.
- Implementation commit: `ff64705` (`Implement deterministic Netdisk video enrichment`).

## Comments

- 2026-07-19: Research established that Netdisk “文稿笔记” may be structured/summary content, so the downloaded complete transcript and the AI note are validated as separate children. Historical `20260628` Word material is reference-only and cannot substitute for this fresh browser run.
- 2026-07-19: Browser security policy denial is a real execution blocker. The implementation records it and stops rather than using Computer Use or another browser surface as a covert fallback.
- 2026-07-20: OpenCLI was installed and connected after the Codex-surface denial. It read the logged-in consumer-page DOM without extracting credentials and proved that both target transcript lists were fully present in the initial DOM, so direct capture replaced unnecessary export/download work for these jobs.
- 2026-07-20: The 719 correction supersedes the earlier prepared 628 candidate; no 628 artifact is used as Ticket 02 acceptance evidence.
