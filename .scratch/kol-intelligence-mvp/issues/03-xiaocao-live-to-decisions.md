# 03 — 新小草直播捕获到双输出闭环

**What to build:** On the user-present broadband media worker, begin before a new Xiaocao live exists: verify the capture service, arm a baseline-aware job, tell the user when to play the enterprise-WeChat card, and capture only the new live directly into a compressed artifact. After the large-video upload or cloud handoff, the 7×24 coordinator takes over deterministic enrichment, household WeChat, and Book KOL-US. The exploratory capture client is reusable implementation material, not a separate deliverable.

**Blocked by:** 02 — 百度网盘真实视频确定性富化到双输出闭环.

**Status:** completed

- [x] Readiness is verified and a fresh persisted baseline exists before the user is asked to play anything.
- [x] One unambiguous prompt was delivered; opening the target player produced exactly one new `live_id`, with no fixed playback wait required.
- [x] Old candidates cannot be mistaken for the new live; source identity and time remain linked through every artifact/output.
- [x] The normal save path is restricted to `live_capture` plus `compress=true` and cannot select the raw-save path.
- [x] Failed/interrupted download resumes from the capture ledger and rehydrates a signed candidate only in memory.
- [x] The same captured evidence reaches deterministic enrichment, household WeChat, and a Book KOL-US action/no-trade result.
- [x] Large local capture/upload remains on the broadband media worker; the 7×24 coordinator resumes from a metadata-only handoff and does not download the source video.
- [x] Status/recovery claims every external mutation before action and resumes from the existing capture/Netdisk/decision ledgers.
- [x] Passwords, credentials, and signed media URL queries cannot enter source or job state; the legacy capture ledger has been atomically sanitized.
- [x] The user confirms the message corresponds to this live and normal active interaction stays within about five minutes.

## Evidence

- The July 21 capture `kol-b15453277907` proves the real adapter contract,
  inline-compressed artifact, interruption recovery, immutable full transcript,
  AI-note submission, household delivery, and Book KOL-US no-trade receipt.
  It is not reused as final Ticket 03 acceptance because the browser upload
  claim at `2026-07-21T21:38:04+08:00` preceded deterministic sniffer/proxy
  cleanup proof at `2026-07-21T21:41:43+08:00`.
- The Ticket 03 runner now rejects that ordering and will not prepare or
  advance Netdisk until the exact process is gone, ports 2022/2023 have no
  listener, `/api/status` is unavailable, and all four system proxy flags are
  zero.
- Fresh acceptance job `kol-d141475ad2a9` was armed at
  `2026-07-25T18:40:25+08:00` after the exact binary became healthy. Its
  persisted baseline has 37 unique historical candidate keys. One playback
  prompt was emitted after that write. Across three consecutive Goal turns no
  new candidate appeared, so the listener was safely paused without changing
  the baseline or replaying the prompt. The exact process and listeners are
  gone, `/api/status` is unavailable, and all four system proxy flags are zero.
- The resumed listener claimed only new `live_id`
  `l_6a632acee4b0694c352f25ba` and produced
  `20260724 大师班专场(晚18：30开播)-compressed.mp4` directly. The artifact is
  208,016,619 bytes, 2,989.109589 seconds, and has SHA-256
  `ac3939f5f949cf47e05b90680bca91393fd7e249e62f69f6dfbec7735f9815b2`;
  no raw sibling exists and the final 30 seconds decode successfully.
- Deterministic cleanup completed at `2026-07-25T19:29:02+08:00`; Netdisk
  upload started later at `2026-07-25T19:29:16.255070+08:00`. The exact cloud
  target was reconciled once, then a metadata-only handoff was published with
  `coordinator_large_payload_local_bytes=0`.
- A real Baidu folder-page `.nd-operate-guidance` operation-ad overlay was
  semantically identified and closed through its unique
  `img[alt="close"]` control. The visible overlay count changed from one to
  zero while the exact folder binding remained true. The same non-coordinate
  handling now runs before every folder inspection/reconciliation.
- The exact video produced a 12,934-character complete transcript with SHA-256
  `ff0556df3d35414bf33b18fa6ef1543ed210d901bda2c77c420990526092d75b`.
  Its seven-row market/next-session/multi-session/style/sector/risk/asset
  matrix passed content audit, and the current-market check used the latest
  available July 24 close.
- The initial household rendering was delivered but rejected by the user
  because it mixed too much system prose with the source. The authorized
  correction keeps raw ASR only in audit evidence and sends four explicit
  sections: context-corrected KOL viewpoints, system logic decomposition,
  current-fact check, and system conclusion.
- The first corrected notification was 2,221 UTF-8 bytes and exposed a real
  boundary bug: Xiaocao uses the relay REST `/send` endpoint, which bypasses
  the wecom-app extension's existing long-text splitter. WeCom therefore
  truncated the successful API call at exactly 2,048 bytes, after the first
  character of `信息来源`. The Xiaocao notifier now losslessly splits title plus
  body at semantic boundaries into at-most-2,048-byte chunks and requires all
  chunks for all recipients before returning `ok`. The real corrected payload
  was proven as two lossless chunks of 2,045 and 176 bytes and delivered to
  both configured recipients under notification key
  `fd699f29e34da5fe3fc3c8d4a08dcbf1cf7c34d27aa9018a6e31eef322310aeb`.
  The unchanged Book KOL-US no-trade receipt retained key
  `6cd34b6a7d687f61b3ffd3195bf492ed0c7b772a123d6f3a1d608eb3fdd40885`
  and was not written again.
- Acceptance evidence
  `output/live/kol_xiaocao_live/acceptance/kol-d141475ad2a9.d751ce6da86cbdd9.json`
  proves one capture, one upload, one transcript request, one AI-note request,
  one corrected notification claim/receipt, and one Book KOL-US row. A second
  runner invocation returned `idempotent_replay=true` with zero new external
  side effects.
- At `2026-07-25T20:44:47+08:00` the user confirmed the corrected, chunked
  message corresponds to the target live and has decision value. The runner
  persisted `xiaocao_live_completed` with
  `user_confirmation=target_live_and_decision_value_confirmed` and zero new
  external side effects.
- The committable, sanitized acceptance summary is
  `.scratch/kol-intelligence-mvp/evidence/03-xiaocao-live-acceptance.json`. It
  contains only identities, hashes, counts, safety assertions, and the user's
  confirmation; it excludes credentials, signed media URLs, receipt endpoints,
  and transcript text.
- Focused capture/runner/Netdisk/skill/rendering/notifier tests: `97 passed`. The broader decision
  fixture file currently has stale July 19 processing-time timestamps and is
  reported separately rather than treated as a Ticket 03 regression.
