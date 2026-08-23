# 04 — 吕晓彤文字与图片订阅到双输出闭环

**What to build:** On the 7×24 coordinator, poll the currently bound Lv Xiaotong Baidu subscription share URL directly for irregular file-list changes, detect one unseen text item and one unseen image without recurring user prompting, and carry each through the common intelligence path. Text bypasses video enrichment; the image uses OCR while preserving original evidence. Each item independently reaches household WeChat and a Book KOL-US action or explicit no-trade reason.

**Blocked by:** 02 — 百度网盘真实视频确定性富化到双输出闭环. Ticket 01's downstream contract is already complete; ticket 02 must first establish deterministic Netdisk control that this subscription poller reuses.

**Status:** completed — user accepted the real source's image-only text
contract on 2026-07-25

- [x] The user stores/authorizes the current subscription share URL and code once in ignored local config; recurring update discovery is automated by the resumable poller.
- [x] Direct share metadata polling is low-bandwidth, records a durable manifest cursor/identity, and detects a real irregular update without asking the user to check manually.
- [x] Text bypasses Baidu video enrichment and enters the common contract directly in focused tests; the real share currently contains no native text sample.
- [x] OCR retains the original image as evidence and surfaces ambiguous fields rather than guessing.
- [x] Source, author, publication/capture time, media type, and evidence location remain traceable.
- [x] Every text-bearing form that exists in the real source reaches the two outputs: the real source uses image text, so the real image completed OCR, household WeChat, and Book KOL-US no-trade. The native-text bypass remains covered by focused tests without fabricating a source sample.
- [x] Duplicate/repeated subscription items cannot duplicate notification or paper action.
- [x] A no-update poll is quiet and does not consume or download unrelated large media.
- [x] The user accepted the real image-only source contract and the corrected weak-signal advice boundary; low-confidence asset mentions remain visible without being upgraded into attributed Lv Xiaotong trades.

## Real source contract confirmed 2026-07-25

- The only discovery surface is the currently configured authorized share root. Do not implement `订阅分享管理` message parsing or a second discovery adapter.
- Subscription identity shown by the real update cards: `彤商学院防断更新zk7897897`.
- The current URL and code are stored only under `kol_intelligence.lv_xiaotong` in ignored local `xiaocao.yaml`; neither value enters the ticket, source, or job state.
- The current private URL passes the fail-closed provider/path check after
  allowing only Baidu's observed root hash-route form; arbitrary fragments,
  query strings, hosts, and non-`/s/` paths remain rejected.
- The real screenshot shows that the share receives heterogeneous files: `7月20日.mp4`, plus image groups containing `12.png`, `10.png`, `9.png`, `17.png`, `16.png`, and `15.png`. The direct share poller enumerates every file independently; it does not need to reconstruct the original reminder envelope.
- The first implementation reads the share's file list and latest modification time, persists the observed file identities, and treats later unseen/changed identities as updates. Do not add cross-link migration logic, multiple fallback surfaces, or speculative abstractions before a concrete failure requires them.
- If the share rotates, the user replaces the two local config values. Exact duplicate suppression may reuse an already available stable file identity; do not build a separate cross-root subsystem for a hypothetical problem.
- The screenshot establishes source semantics, not implementation acceptance. Ticket implementation selects one deterministic direct-share listing method, proves it on the real link, and stops exploring once it works.

## Implementation and real acceptance 2026-07-25

- Ticket-only implementation is isolated in `src/xiaocao/kol/lv_subscription.py`,
  `scripts/kol_lv_subscription.py`, `scripts/kol_vision_ocr.swift`, and
  `tests/test_kol_lv_subscription.py`.
- The matching agent operation contract is an isolated Ticket 04 section in
  `.codex/skills/kol-intelligence/SKILL.md`; pre-existing unrelated edits in
  that already-dirty skill file remain outside this ticket's eventual staged
  hunk.
- The browser protocol scans the configured share root and every subdirectory
  through the page's `/share/list` protocol, persists provider-file identity,
  source modification time, version identity, first observation time, cursor,
  and presence without persisting the URL or share code.
- A source-version claim is persisted before the browser download action; only
  its completed immutable receipt may enter text extraction or OCR, so a loose
  same-name local file is not an ingestion path.
- The shortest bootstrap-to-output operation is one resumable process:
  `PYTHONPATH=src python3 scripts/kol_lv_subscription.py run --bootstrap-bind --opencli-session xiaocao-lv-subscription --opencli-profile <connected-profile>`.
  It binds the active authorized Microsoft Edge tab once through the OpenCLI
  Browser Bridge, polls, claims and downloads
  every pending small text/image, extracts evidence, persists
  `analysis_request.json`, accepts the evidence-bound bundle path on the same
  process stdin, then completes household delivery and Book KOL-US. Later runs
  omit `--bootstrap-bind`; no manual subcommand chain is required.
- Local contract tests cover quiet repeated polls, disappearance/reappearance,
  changed versions, OCR-once concurrency, native text bypass, OCR ambiguity,
  evidence/result integrity, complete trade-information coverage, paper-only
  fail-closed behavior, pre-trigger retry versus uncertain-trigger
  reconciliation, and exactly-once household/paper outcomes.
- Codex browser capability evidence remains surface-specific and sanitized:
  the built-in browser and the separately installed Codex connector in
  Microsoft Edge can enumerate the private-share tab, but DOM reads against the
  real `/s/...` page are rejected as `browser_security_policy_denied`. Neither
  the real URL nor extraction code is recorded, and those surfaces are not
  retried or treated as the product adapter.
- The product adapter is the same route proven by Ticket 02: the OpenCLI Browser Bridge
  in Microsoft Edge. The operator opened the configured link there,
  completed extraction, and left the visible file list active. OpenCLI doctor
  then proved the extension/daemon profile connected before the one-time bind.
- The real page exposed two `/share/list` shapes: a root request carrying
  page-generated `root + shorturl` state and a directory request carrying
  page-generated `sekey + dir` state. The implementation reuses those observed
  request templates inside the page and changes only page number and directory;
  secret-bearing parameters never leave the browser or enter durable state.
- The complete real scan persisted one cursor over **515 provider identities**:
  46 directories, 43 images, and 426 excluded non-image/non-text files. Every
  entry retained provider modification time; the observed range was
  `1758202204..1784821267`. No native `.txt` or `.md` item existed.
- Initial bootstrap baselined 42 historical images and made only the latest real
  image, `17.png`, work-eligible. This prevents a first deployment from
  replaying 42 historical notifications. Later new or changed versions remain
  eligible normally.
- A durable claim preceded the exact UI download. The page's default 16-item
  selection was cleared, exactly `17.png` was selected, and the unique
  `普通下载` confirmation completed one 1,377,484-byte browser download. The
  immutable original SHA-256 is
  `dd76d6bdacb792933897112ae1426fb20349e1c575f17045792612df0b232846`.
- macOS Vision OCR ran once. Evidence SHA-256 is
  `10bf2839cb777d3f507b15db9d9b3eac9f9f17fa12e93dcd82fca11841d49f79`;
  all 16 low-confidence lines received explicit non-actionable assessments.
  The screenshot was a member-group chat fragment, so no remark was silently
  attributed to Lv Xiaotong.
- The evidence-bound bundle contains all seven trade-information coverage rows
  and resolves every named asset: Intel/`INTC`, Tesla/`TSLA`,
  Alphabet/`GOOGL`, and the A-share market. Current validation used the latest
  completed A-share EOD snapshot and latest US session. The result is
  `decision_status=no_actionable_signal`: household advice is `wait`, while
  Book KOL-US is `paper_only=true, status=no_trade` because ticker mapping alone
  cannot replace author attribution, thesis, trigger, position, horizon, and
  falsifier.
- Household WeChat delivery completed with one durable receipt. User review
  found that the first rendered card was too verbose: it expanded a weak group
  fragment into unrelated market-wide prose. That already delivered card was
  not resent. The corrected contract retains the private coverage matrix but
  sends only a compact reader insight. For this real sample the useful insight
  is that group participants were discussing weakness in named US technology
  assets; because the household actually holds `TSLA`, the card links only that
  real position, labels the signal weak and non-attributable to Lv Xiaotong,
  and leaves the buy/sell judgment to the user.
- Low confidence no longer suppresses a relevant mention. Every
  `decision_status=no_actionable_signal` must declare
  `reader_insight.status=useful` with a concise summary and evidence boundary,
  or `reader_insight.status=none` with a reason. Only the latter is audited and
  suppressed from household delivery; it still reaches Book KOL-US as a
  paper-only result. Focused regression tests prove both paths and their replay
  idempotency.
- The original household WeChat delivery completed with one durable receipt. The exact
  household idempotency key occurs once in the outbox; the exact Book KOL-US
  idempotency key occurs once in the paper ledger. Decision result SHA-256 is
  `52dfaaed8b6114a7ee297b7dbb39e7fc870609388c5f71edb4ddec395ed425bb`.
- Re-running the same runner returned zero stdout. Durable state then showed
  zero pending items, one download receipt, one OCR artifact, one decision
  state, one matching household row, and one matching paper row: no second
  download, OCR, notification, or paper action.

## Reader-output correction and focused validation 2026-07-25

- Real-result preview after user review is five lines: one weak-signal insight,
  the genuine household `TSLA` relationship, the provenance/confidence
  boundary, and the source. It does not expose INTC/GOOGL/A-share boilerplate,
  unrelated portfolio commentary, or a system-made buy/sell decision.
- A weak but accurate mention is still sent even when it cannot support a
  trade. The renderer title is `弱信号提醒`, not `不行动`; the user retains the
  decision.
- A source item with no accurately relayable insight is persisted with
  `notification.status=suppressed` and a reason. The sender is not called, the
  paper-only no-trade audit still completes, and replay adds neither a second
  outbox row nor a second paper decision.
- Passing focused commands:
  - `PYTHONPATH=src python3 -m pytest -q tests/test_kol_lv_subscription.py tests/test_kol_skill_structure.py tests/test_kol_netdisk_enrichment.py`
    — 77 passed in the clean Ticket 04 staged tree.
  - `PYTHONPATH=src python3 -m pytest -q tests/test_kol_decisions.py -k 'no_actionable_reader_message or no_reader_insight or reader_message_surfaces_market_outlook'`
    — 4 passed in the clean Ticket 04 staged tree.
  - `python3 -m py_compile` over the modified KOL modules and runner succeeded.
- A broader run of `tests/test_kol_decisions.py` also exposed 31 unrelated
  pre-existing failures: that file's shared fixture hard-codes a market
  `checked_at` of 2026-07-19, which now correctly fails the production
  24-hour-currentness gate. Ticket 04 does not weaken that safety gate; its
  current-time Ticket 04 and reader-policy tests pass.

## Source-limited acceptance decision

Accepted by the user on 2026-07-25. The configured real share contains image
text and excluded video/other files, not native text. No sample was fabricated.
The real-image end-to-end run plus the focused native-text bypass test is the
final Ticket 04 evidence contract; a future `.txt` or `.md` item is not required
for completion.
