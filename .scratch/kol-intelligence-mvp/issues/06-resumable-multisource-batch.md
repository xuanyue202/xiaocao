# 06 — 可恢复的多来源批处理闭环

**What to build:** On the 7×24 coordinator, process at least two real video
jobs and one real text/image job in one operational window without serially
blocking on cloud enrichment. Consume Xiaocao broadband-worker handoffs
alongside automatically polled subscription updates, recover after process
interruption, and carry every item independently to a household terminal and
an idempotent Book KOL-US paper terminal without locally downloading source
videos.

**Blocked by:** 03 — 新小草直播捕获到双输出闭环; 04 — 吕晓彤文字与图片订阅到双输出闭环; 05 — 吕晓彤与路西法订阅视频到双输出闭环.

**Status:** completed — scheduler interruption/recovery, the shared coverage
gate, event-specific 灰常亮 reports, historical longitudinal initialization,
production read-back, Agent-ordered current/history projection, zero-side-effect
replay, and the scoped Ticket 06 commit all passed.

- [x] Two real videos plus one real text/image item each reach their own household and Book KOL-US terminal result.
- [x] The batch combines at least one broadband-worker handoff with at least one automatically discovered subscription item.
- [x] One waiting child does not block other ready work.
- [x] First async polling starts no earlier than five minutes and later retries use explicit backoff.
- [x] Restart reconstructs state from append-only evidence without replaying completed children.
- [x] Stable identities and durable receipts prevent duplicate upload, generation, notification, or paper actions.
- [x] Time-sensitive signals are prioritized while aging prevents lower-priority high-density work from starving.
- [x] Low-density, duplicate, unauthorized, missing-evidence, and missing-market-data items retain explicit pause/terminal reasons.
- [x] Network accounting proves the coordinator reads zero source-video bytes.
- [x] A multi-part publication is one logical child with every component identity and version preserved.
- [x] Historical fragment receipts are reconciled read-only and never auto-replayed as a consolidated publication.
- [x] A complete source signal cannot be hidden by Book eligibility or historical receipt reconciliation.
- [x] Every reviewed real publication event has its own complete 灰常亮 report; a batch does not merge reports, reminders, or Book terminals.
- [x] Historical initialization creates no new Enterprise WeChat reminder or Book replay.
- [x] The user approved the complete-report quality and concise-reminder shape.
- [x] Revalidate the Agent-ordered per-KOL current/history reader projection and true history total in production.
- [x] Create the scoped Ticket 06 commit.
- [x] No 7×24 schedule was created; deployment remains Ticket 07.

## Dependency handoff

- Ticket 03 was committed first as independent commit `968b05d`
  (`Complete Ticket 03 Xiaocao live loop`), after the Ticket 04/05 commits.
- Ticket 06 remains an orchestration layer. It consumes the existing Ticket
  03 metadata handoff, Ticket 04 text/image result, and Ticket 05 cloud-video
  acceptance receipt. It does not reimplement capture, OCR, Baidu discovery,
  cloud transfer, enrichment, decision, notification, or Book logic.
- The public surface is one runner plus `status` and `audit`. Each child keeps
  stable source/version identity, priority, status, `next_poll_not_before`,
  retry count, failure reason, payload accounting, and a terminal receipt.
  State is reconstructed from one append-only JSONL ledger.

## Final reader-publication contract

The batch is an operational ledger, not a reader publication identity. One
real KOL publication event produces one complete safe-Markdown report in
灰常亮. Multipart files from the same event remain ordered `source_parts` of
that one report; independent events remain independent reports even when one
coordinator window processes them together.

For a newly eligible event, Enterprise WeChat may send at most one concise
event-specific reminder after the durable 灰常亮 publication receipt. The
message leads with the most decision-important insight, follows with a
coherent compact synthesis of the other important information, and ends with
exactly one stable report link. It is neither a naked link nor the full report.
Different events never merge into one batch message. Historical imports and
report corrections publish/reconcile the report but create no reminder or
Book replay.

## Corrected logical-episode review

The earlier Ticket 05 sample and Ticket 06 v2 insight covered only
`7月5日（二）.mp4`. That was incomplete: the real 路西法 7 月 5 日 publication is
three videos and must be treated as one episode.

The corrected source identity is:

- aggregate identity
  `9fc5ed7f825ff6a3dea9ccff39ae382e521a0d777a673e6fad5a45a1c7da2b73`;
- aggregate version
  `c4ea2e58009b9d3fc193006b7fdffd8b0bb914ac7da64bb3d82dc1c8f8be265e`;
- three immutable source part identities/versions and sizes, totaling
  2,082,952,559 metadata bytes;
- three authenticated small-document transcript hashes;
- one merged evidence hash
  `829a207063ec2469ae854367d18dfa4de7b56357b9c0c796bbbf9def895dab84`;
- one superseded review-only decision-result hash
  `97cb686050d95f9e3343e6e22c44fb6b7a61addc446cd07557d8164876b7d820`.

The complete episode is ordered by decision priority and has a defensive
portfolio posture:

- latest available 2026-07-24 A-share evidence is still `bear`, with 555
  rising and 4,939 falling;
- 北特科技 closed 38.99 (-5.48%), so the author's roughly 40-yuan price
  condition is met but market breadth repair and stock stabilization are not;
- 三花智控 closed 35.05 (-5.75%), and the stated governance concern remains
  unresolved;
- long-term physical-AI, robotics, energy, storage, and ETF preferences remain
  the author's view, not a current trade override;
- political, war, dollar, precious-metal, golden-pit, financing, and technical
  ranking claims were not independently verified by local evidence and were
  not converted into actions;
- the prior `suppressed` terminal is invalid because the aggregate contains a
  material new signal: after 7 July, approximately 5% or less, short SpaceX,
  never use leverage;
- current facts correct SpaceX to listed ticker `SPCX` and confirm its 7 July
  Nasdaq-100 inclusion;
- the corrected household state is `review_required`, not a terminal, and
  proposed Book KOL-US remains paper-only `no_trade` because direct shorting
  is outside Book authority while daily -200% `SPCG` conflicts with the
  source's no-leverage boundary.

The corrected review artifact hash is
`533747efe1ffc10a0ce1e5e133e0410734c987ddd4aae012a0fef6b7e2b0a6ed`.
Its creation changed no household, notification, or Book ledger and read zero
source-video bytes.

## Real interrupted batch acceptance

The corrected real batch is `ticket06-real-20260726-v3` and contains four
children in the same ledger:

1. Xiaocao broadband metadata handoff video, priority 100;
2. Lv Xiaotong automatic subscription video, priority 90 and async;
3. Lucifer three-part logical video episode, priority 80;
4. Lv Xiaotong real image, priority 40.

At `07:44:02.771704+08:00` the coordinator wrote the async checkpoint for the
Lv video and set the first poll no earlier than
`07:49:02.771704+08:00`. Xiaocao, Lucifer, and the low-priority image all
reached terminal receipts by `07:44:03+08:00` while the Lv video was still
waiting.

The first runner received real `SIGTERM` at `07:44:14+08:00` with one
unfinished child and exited 143. The same runner restarted at
`07:44:29+08:00`, preserved the three existing receipt hashes, and polled only
the due Lv child at `07:49:02.901621+08:00`. The observed first-poll delay was
300.129917 seconds. The batch completed at `07:49:03+08:00`.

The v3 runner-local terminals were:

- Xiaocao video: household `delivered`, Book `no_trade`;
- Lv video: household `delivered`, Book `no_trade`;
- Lucifer episode: household `suppressed`, Book `no_trade` — invalidated by
  user review and retained only as superseded historical evidence;
- Lv image: household `delivered`, Book `no_trade`.

All four have `large_payload_local_bytes=0` and
`coordinator_source_video_bytes=0`.

A full rerun added only runner start/completion events. The child-terminal
event count stayed four, the async-poll claim count stayed one, and all watched
source/transfer/enrichment/household/Book hashes remained unchanged. The audit
reports `accepted`, one interruption, four terminal receipts, zero retries,
zero source-video bytes, and zero new external side effects. This proves the
coordinator mechanics. Semantic publication was completed later through the
event-specific 灰常亮 report contract: the corrected Lucifer report is
published with a legal historical no-alert reason, while the existing
paper-only `no_trade` is reconciled without replay.

## Real source rescan and pause noise

The private source was rescanned only through the logged-in Microsoft Edge OpenCLI
Browser Bridge. No raw HTTP, Computer Use, source-video open, or download was
used. A transient private-directory timeout failed before manifest write; one
safe read-only retry completed.

- weak one-file numeric/bracket suffix pauses: 0;
- remaining explicit episode pauses: 4;
- reasons: two `episode_waiting_for_companions`, two `incomplete_episode`;
- the former Lucifer terminal stayed immutable but is now marked superseded;
- the aggregate was paused at `awaiting_user_review` before the corrected
  event report was reviewed and published to 灰常亮;
- coordinator/source event video-byte accounting stayed 0.

## Superseded batch insight and corrected event report

The old v2 insight was delivered but omitted Lucifer and is superseded; it is
not authorized for replay. The v3 preview was not published, but user review
also rejected it because it omitted the primary SPCX short signal and repeated
the false unlisted classification. It is not a valid corrected preview.

The first replacement Lucifer review, now superseded by the complete gold
review below:

- leads with the 7 July, 5%-or-less, no-leverage SPCX short signal;
- separates KOL view, system analysis, fact check and system conclusion;
- corrects SpaceX to listed `SPCX` and records the 7 July entry-price boundary;
- proposes Book KOL-US `no_trade` without hiding the source signal;
- is 1,481 UTF-8 bytes and has no publication claim or recipient send.

No replacement batch message is built or delivered. The corrected content is
published as the Lucifer event's complete 灰常亮 report. Any future eligible new
event uses its own short reminder and stable report link.

## Source-agnostic completeness review

The accepted extraction policy is now one shared semantic contract for every
single-item and batch KOL runner. It contains no known author, asset, or action
keyword allowlist. A concrete recommendation, portfolio/risk guidance,
market/sector view, or material-impact thesis independently makes a claim
`must_surface`; low confidence, conditionality, missing verification, conflict,
or uncertain attribution can only add a boundary label. Pure advertising is
removed.

The complete 7 July Lucifer evidence was independently reread as 308 stable
segments. The current gold review contains 33 thesis units: 32 must surface and
one unresolved opening holding reference remains audit-only because the ASR
lost its subject. The second pass links 269 investment segments to theses,
classifies 29 as non-investment, and removes 10 advertisement segments. It
preserves the different short- and long-horizon gold views, the SpaceX timing,
size and no-leverage boundary, and all lower-priority capital, sector, company,
commodity, currency, geographic, tax, banking, and macro-information theses.

The reader output is coherent prose rather than a table. Its full 5,954-byte
content belongs in 灰常亮; it must not be split into four Enterprise WeChat
messages. A newly eligible reminder would instead contain the key insight,
compact synthesis, and one stable link. The read-only gold review has SHA-256
`5e141c152ad0ec874aabc7046d531e62ba90d5a636e51dcf747f2d9ce1fa6d9f`,
records zero external side effects and zero coordinator source-video bytes,
and lives at
`output/live/kol_subscription_videos/review/lucifer_20260705_claim_gold_v4.json`.

The same contract passed blind real-evidence checks against the Ticket 03
Xiaocao transcript (10 must-surface plus one audit-only thesis) and the Ticket
04 Lv image (three low-confidence group-member theses plus two audit-only
mentions). The Lv result explicitly does not attribute group-member comments
to Lv Xiaotong, but no longer suppresses the whole image merely because the
author attribution is uncertain. No household notification or Book action was
replayed during this review.

Full KOL validation is `255 passed`. The prior 38 failures were traced to a
test-only 19 July processing-check timestamp; the production 24-hour
currentness gate stayed unchanged, and only the test runtime check timestamp
was refreshed. The production event-report and longitudinal publication is
recorded in the sanitized acceptance evidence below.

## Final 灰常亮 reader acceptance

灰常亮 main commit
`89d859f2f37d81f93972bc48af9a1413b07a5f25` completed CI and Amplify
deployment 162 on 2026-07-26. Authenticated production readback proved:

- Xiaocao shows 8 current and 2 uncertain viewpoints, led by
  `A股整体环境与风格` and `轮动区间交易节奏`; its history title reports the true
  total 203 and expired records stay out of the default current area.
- Lv Xiaotong shows 4 current and 4 uncertain viewpoints plus both reviewed
  `refines` relations from the 20 July event to the 13 July views.
- Lucifer shows 19 current and 13 uncertain viewpoints, led by SpaceX. The
  stable report and KOL page both preserve `7月7日后用总资金5%以下做空，绝不加杠杆`
  and the roughly-40-yuan Beite condition.
- `/finance`, the stable report deep link, and both trailing-slash variants
  return HTTP 200. Logged-out login recovery preserves the exact report id.
- The deployment used only the Agent's ordered report `viewpoint_ids` and a
  service-side `historyTotal`; it added no second analysis rule or
  `display_order` field.
- Production revalidation performed zero KOL writes, zero Enterprise WeChat
  sends, and zero Book actions.

## Validation and evidence

- Sanitized evidence:
  `reference/experience/acceptance/kol_batch_ticket06_2026-07-25.json`.
- Production report/viewpoint acceptance:
  `reference/experience/acceptance/kol_gray_report_and_viewpoint_2026-07-26.json`.
- Runtime ledger:
  `output/live/kol_batch_ticket06_real_v3/state/events.jsonl`.
- Rejected v3 insight preview:
  `output/live/kol_batch_ticket06_real_v3/insight_review.json`.
- Corrected Lucifer review:
  `output/live/kol_subscription_videos/artifacts/c4ea2e58009b9d3fc193006b7fdffd8b0bb914ac7da64bb3d82dc1c8f8be265e/legacy_episode_review_required.26d940916c14d45e.json`.
- Original focused validation:
  `149 passed in 3.84s` across episode grouping, batch scheduling, Ticket
  03/04/05 adapters, source-video boundaries, side-effect claims, SIGTERM
  durability, failure classification, priority aging, insight delivery, and
  receipt-driven manifest repair.
- Post-correction focused validation:
  `150 passed in 3.59s`, including the exact SpaceX salience regression,
  user-visible coverage failure, useful-aggregate review gate, idempotent
  replay, and the existing Ticket 05/06 coordinator suite.
- Current complete KOL validation:
  `255 passed in 7.24s`, including publication CAS/reconcile, all reviewed
  must-surface viewpoints, current/history projection, relation dependency
  ordering, zero-side-effect replay, and the existing source/coordinator suites.
