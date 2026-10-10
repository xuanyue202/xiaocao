# Morning automation

Read this file only for the daily morning recommendation/paper-book branch.

## Execute

Scheduler wakes are preparation only: producer and paper wake at 09:18; APP
wakes at 08:53. Start the original entrypoint promptly. Python waits until
09:25:01 before capture/paper consumption, and until 09:00 before fresh APP
preflight notices and its 2100-second preparation budget. Continuations retain
their exact prior absolute deadline. Required data and every active candidate's
dated entry price must be ready together; the original producer retries every
two seconds until ready. Paper waits for that same original bundle every two
seconds. Review support retains its separate bounded budget and is bound to
the consumer's checkpoint. Failed-run context packs read existing queues.

Recover saved credentials within the current owner. A pre-secret APP receipt
with both action flags false is not a consumed password attempt. The helper
may dismiss the uniquely proven old error sheet, reprove the same account and
window, then use Keychain once. True confirmations and uncertain transports
retain their fence. Proven no-action dependency failures recheck every two
seconds within the original budget. Missing credentials, locked accounts and
explicit human-only authentication remain distinct blockers.

For producer or consumer handoff faults, apply Operating Contract §1c and
[book-b-live-repair.md](book-b-live-repair.md). The original 09:25:01 capture commits
one execution bundle before optional news/report work. Both consumers verify
its exact checkpoint and consume the proved original or recovered copy.
Read `morning_bundle_repair_required.request_path`, repair the local dependency,
then run `morning_bundle_recovery.py --request <exact-path>` once; accept only
the revalidated original batch. Keep the original wait/budget alive. A missing
original remains unproved, with failure notification and bounded owner repair.
Formal paper passes the dated immutable snapshot and consumer receipt; its
legacy mutable experiment flag is forbidden in Automation. Explicit intelligence
`on` also requires the completed same-batch support artifact and current veto.
An orphan checkpoint before the commit is a request for the exact original
producer owner; only that runtime identity can finish its interrupted commit.
Consumers cannot create a commitment. A zero-row proven capture needs no support
artifact. Missing shadow support/review queue is explicit degradation. Empty
new support cannot withdraw an earlier valid event; the typed policy owns expiry.
After a proved bundle commit, a conflicting compatibility freeze is preserved
and reported as supporting degradation; it does not abort derived support work.

For the bounded KOL overlay, also read
[kol-trading-judgment.md](kol-trading-judgment.md). Keep the original runner and
model. The remote writer owns full reading and independent source-level review
of every new/changed report. The same semantic publication writes LiangHui
viewpoints, evaluations and relations atomically. Morning live and paper tasks
consume the compact hash-bound projection and perform only their separate
current-applicability adaptation and review. They do not reread unchanged
report bodies or create a second source draft. Only a
source-verified published decision is consumable. Account-risk and KOL
caps are separate from frozen qualification and the allocation capsule; a late
review never rewrites the freeze, old intent or an earlier fill.

Scheduled delivery is split across two Automations because the recommendation
is ready before opening-window execution can finish:

```bash
# 09:25:01 task: commit execution bundle, then deliver derived report/review queue
CODEX_AUTOMATION_ID=xiaocao-daily-morning bash scripts/auto_daily.sh morning-prerecommend

# 09:25 task: wait for those frozen artifacts, review, and paper-record
CODEX_AUTOMATION_ID=xiaocao-daily-morning-execution bash scripts/auto_daily.sh morning-execute
```

Book-B real-capital execution is a third, deliberately independent
09:00 Automation and process:

```bash
CODEX_AUTOMATION_ID=xiaocao-book-b-live-morning PYTHONPATH=src .venv/bin/python scripts/book_b_live_morning.py --date today --route native-app
```

It may start before the dated freeze exists and wait only for that freeze. It
retains its original process on a recoverable preflight dependency failure;
handle `dependency_recovery_wait` through [book-b-live-repair.md](book-b-live-repair.md)
and Operating Contract §1b before classifying a terminal result.
must never run or await `morning-execute`, read a paper fill, or write
`positions.jsonl`, `paper_trades.jsonl`, `paper_account.json`, or
`paper_account_T.json`. Its state lives only under
`output/live/book_b_live_execution/`. Before waiting, it verifies the native session once. It then leaves the App untouched until 09:24 China time, when the same runner rechecks/recovers the session and resumes 30-second heartbeats until the freeze. The quiet wait performs no repeated freeze polling; bounded sleeps recheck the clock and original timeout. A late start resumes checks immediately. Once a non-empty
freeze exists, the normal new-BUY path reads available cash and Book-B owned
position marks from the account-bound positions capture. It atomically produces
`book_b_live_allocation_facts_<date>.json` with a scoped buying-power receipt;
full mixed-account order/trade/equation reconciliation follows submission. OpenCLI trading/view is sunset: this
live entrypoint does not import, initialize, authenticate or query it. A
non-empty dated freeze is valid for this
consumer only when the queue producer manifest already binds its actual
same-day snapshot rows, report, strategy run id, producer strategy Git SHA,
hash and count. Before any agent review can enrich the canonical snapshots,
the producer atomically writes those exact rows to
`output/live/book_b_live_freeze_<date>.jsonl`; an existing different artifact
must never be overwritten. The live consumer reads and recomputes only that
immutable dated copy rather than defining a new digest from later-reviewed
`signal_snapshots.jsonl`. Broker total assets and total securities market value
are evidence only, never the mixed-account Book-B basis. Apply Contract §6's
approved dynamic APP capital policy on logical account `primary`; the allocation
capsule cites its exact capital-flow head. Routine tasks never migrate or mint
authorization. Any submitted, acknowledged, partial, filled,
unknown or reconciling execution evidence (including a fill followed by an
ownership-ledger write failure) blocks reuse of the first-batch basis until a
hash-bound EOD settled-NAV receipt exists. A settlement is reusable only when
its ownership-chain head still equals the current broker-proved ownership
ledger. If the head changed after a proved fill, replay the hash-bound owned
fills and mark the current owned lots from today's account-bound APP positions;
use the current proved dynamic strategy NAV and owned exposure under §6.
Capital allocation movements preserve unitized risk history.
The returned `account.accounting` is the Contract §6 financial view; retain its
observation/journal hashes and distinguish marked NAV from exit-fee NAV. Cash
classification and statement work reads `docs/BOOK_B_ACCOUNTING.md` after the
time-critical runner start. Routine tasks consume proved facts without classifying
balance differences as capital.
An old zero-fill SELL with exact fresh order/trade/holding proof may remain
reconcile-only while other codes proceed; block a new BUY in that SELL's code.
The
complete allocation capsule binds its capital
basis source, NAV, cash, exposure and broker summary under one canonical hash,
and broker-summary cash must equal top-level available cash. Because the native
App has no mock/live data namespace, every exit must record the explicit
`native_environment_restore_not_applicable` receipt and must not claim a fake
mock restoration.
At 09:00-09:30 the later `forward_eval` field `executable_fillable` may be
absent. Absence is not false and must be deferred to the current submit-time
market guard; an explicitly false value remains ineligible.
During 09:25–09:30, urgent code repair and exact missing-source retrieval take
priority. Follow Operating Contract §1b. Do not add countdown warnings or an
opening preparation cutoff. The APP accepts queued BUY orders from 09:25; aim for the entire batch before 09:28 and require acceptance before 09:30 as the service target. Record lateness honestly; the original plan
may continue within its existing session, recovery deadline and market guards.
Before materializing any new live intent, refresh the proprietary same-day
trade status, current price, authoritative down price and timestamp with no
cache; bind those facts into the durable plan. Lunch, the closing auction and
post-close remain blocked. This changes no frozen selection, allocation,
initial limit, capital scope or exact-once rule, and an existing intent is
always reconciled rather than regenerated or resubmitted. One narrow
pre-submit exception exists for a local/read-only repair: when the original
guard was valid at binding time but has aged out, no submit claim, broker order
id or chain uncertainty exists, and the read-only prepare again proves no
write, the same plan may bind exactly one immutable no-cache guard sidecar.
That sidecar may change only current trade status, price, authoritative down
price and observation time; it keeps the original plan hash, code, side,
shares, limit, basket and allocation proof, is reused rather than overwritten,
and must still stop at limit-down, unavailable data, an expired session or
`REALTIME_ABOVE_BASKET`. It never revives a terminal plan and never authorizes
a second refresh or submit.
The live-plan consumer binds proprietary `HH:MM:SS:millisecond` clocks to the
dated China session and accepts only the documented continuous-auction `T`
status family (`T` or `T` plus digits). Numeric BUY limits are floored, never
rounded up, to the 0.01-yuan stock tick before broker readback.
Apply `docs/OPERATING_CONTRACT.md` section 9 for the capital-gate semantics.
Unless the Founder adapter proves the account-bound `native-app` route, the
required helper capability (v11 for scoped new-BUY parsing), exact prepare/submit
capability, native reconcile capability and broker buying-power facts, the task
reports the exact fail-closed reason and produces no real order. Persist the
sanitized preflight receipt with `website_authentication.status=not_used` and
separate native PassGuard evidence; never infer one capability from another.
Before prepare, the adapter requires zero existing exact
`code+side+price+quantity` orders and snapshots all visible order ids. The
single claimed submit must map to exactly one new numeric order id with that
tuple (or the bounded counter-success notice proof below), then bind any fills by `order_id+code+side`; otherwise it becomes
UNKNOWN/reconcile-only with no click retry. OCR names are non-authoritative;
critical numbers must be exact, locale-normalized by field (`17,3900` is a
decimal price; `54,528.94` uses a grouping comma), and invariant-checked. Keep
the validated success-popup order id and native action/result evidence while a
grid refresh is pending. Immediate self-heal may retry only native reads and
exact reconciliation for the same durable claim. A transient structural,
freshness-evidence, asset-equation, or cross-table failure triggers a bounded
whole-snapshot reread with strict invariants unchanged; the receipt records
read-only actions, attempts, failure codes, and exhaustion. It must never
repeat Return, confirmation or submit. Any
prepare/submit/reconcile chain uncertainty permanently disables automatic
replacement. Exact-order cancellation is available only after unique mapped
order-id readback; it selects and confirms once, then reconciles that same id.
Automatic replacement remains disabled. A five-minute trade lock has one Keychain-backed recovery; a client
restart/CAPTCHA remains a separate bounded slow path.

After any non-normal live-morning result, follow
[`book-b-live-repair.md`](book-b-live-repair.md). The started Automation owns
urgent AX/code repair, minimum necessary validation, exact narrow resume and
terminal readback first; root-cause repair, affected-behavior verification and concise cause/fix/verification follow
the terminal outcome. Do not delay continuation for commit/push or defer a
locally repairable failure to the next schedule. Apply Operating Contract §1a
for local versus APP-server simulation; preserve execution discipline.

The review request keeps the original frozen evidence hash. Legacy missing
`k_score` / `p_score` NaN values become null only in the review copy, with an
explicit `candidate_missing_values` audit. This never edits the frozen rows or
normalizes execution fields or infinities. A process that died before opening
its review window must not be restarted to obtain a late semantic decision.

The execution stage must never rerun `live_recommend.py`. Keep its shell alive
through the agent-review rendezvous and paper recording. Do not restart it while
it is waiting for the opening window. For an explicit manual one-shell recovery,
`bash scripts/auto_daily.sh morning` remains available.

Keep prerecommendation preflight bounded to this skill, the named automation
memory and current-day artifacts. If `CODEX_HOME` is unset, resolve it as
`$HOME/.codex`; do not scan old rollout recovery notes before starting the shell.

The orchestration must reach these stages:

1. The prerecommendation stage runs `live_recommend.py`, freezes the usable 9:25 signal/evidence set, and writes `output/live/recommend_<date>.md` plus ★/★B/★M/★E snapshots. K/P is an optional ranking overlay: a missing model/cache must fall back to neutral K/P ranks and must not skip deterministic snapshot capture or ★E selection. Snapshot-capture failure is fatal and must never be reported as a genuine `★E NONE`.
2. The same stage runs `build_intelligence_review_queue.py` to create the zero-fetch, zero-score review queue, then terminates so its final/inbox result is user-visible. Priority is open Book-B positions, then ★E, ★B and ★.
3. The execution stage uses `wait_for_morning_freeze.py` to require the matching dated report and queue. Missing, malformed or wrong-date evidence fails closed; it never regenerates the signal set.
4. `wait_for_agent_reviews.py` opens a bounded rendezvous. A missing derived queue waits within that same budget; its later arrival never resets the deadline. Invalid or wrong-date queues remain explicit degradation. While the execution shell waits, read the dated queue and frozen evidence, then write structured reviews with `scripts/agent_intelligence_review.py`. Supply each queue item's exact `evidence_freeze_ref` using `--evidence-freeze-ref`; an absent or different reference is rejected before writing. Never substitute keyword scoring. For this local paper branch, if time expires, let base picks continue and report supporting-layer fallback. The independent APP opening runner follows §1b instead.
5. `paper_record.py --pick mode_exec_star --intelligence-trade shadow` records only executable ★E Book-B fills plus the matching Book-A reference rows. K/P, auxiliary indicators, intelligence and manual notional cannot restore a failed mode gate.
6. Book T runs independently after the Book-B attempt, including a missing Book-B freeze or failed Book-B paper record. The original shell preserves the Book-B failure exit status after finishing Book T; it skips B review/buy when B evidence is missing. A Book-T error remains deterministic failure and prevents its optional shadow consumer. Shared ledger recovery/locking and Book-T market gates still apply. Report each book as checked, failed, or not started from its own receipt.
7. `paper_record.py --trend-only` first checks whether Book T has an empty slot or a sellable switch candidate. A full aligned book returns immediately; otherwise it waits for the opening window and fills or performs a paired switch. No candidate or an unfilled replacement is normal.

The current formal Book T consumer remains the v1 control path until Issue 06's
research-consumption and human gates pass. `scripts/book_t_shadow.py
--runtime-check` is a read-only next-run preflight. If a dated,
hash-bound `output/live/book_t_v2_shadow_input_<date>.json` exists,
`auto_daily.sh morning-execute` may consume it after the v1 paper record; the
result is written only under `output/research/book_t_v2_shadow/<run-id>/` and
must never touch `positions.jsonl`, `paper_account_T.json`, or
`paper_trades.jsonl`. The consumer replays and accumulates prior isolated
frozen inputs so the 20/60/50 research floors cannot be reset by a daily
process restart.
A dated producer/input missing from a scheduled run is a supporting-layer
failure and must be reported as such. Only an intact, consumed real-day input
whose cumulative sample is still below the 20/60/50 floors is the normal
`pending_observation` state.
Run `scripts/book_t_v2_soak.py --gate daily-stability --required-days 5` for
the separate stage-3 five-real-trading-day acceptance. Stage 4 remains
`--gate engineering-burn-in --required-days 20`; the five-day verdict cannot
lower or substitute for that formal burn-in.
A consumed input must carry the v1 T receipt and raw SHA-256 hashes for the
positions, account, and trades artifacts; the CLI verifies those hashes before
research evaluation.
`paper_record.py --trend-only` emits the dated receipt after its formal T
result; receipt-write failure is supporting degradation and never rewrites the
successful v1 account result.
If the optional shadow input is malformed or its research write fails, the
automation records supporting-layer degradation and preserves the successful
v1 control result. A real Book T `paper_record.py --trend-only` error is
deterministic failure and must not be hidden by a blanket `|| true`.

Book T ETF candidates are admitted only with the explicit instrument contract and
validated proprietary realtime/minute/daily/liquidity facts described in the
Operating Contract. Missing metadata or current execution facts is a bounded
skip, never a stock-shaped 100-share fallback.

The 9:25 emitted set is the day’s stable recommendation reference. Later prices/fills may change; do not relabel the frozen signal set as unstable after close.

The checked-in `scripts/book_b_execute.py` is the lower-level phase-one
execution seam, not another paper writer. `auto_daily.sh` remains unchanged
and continues to call the canonical `paper_record.py` path. If the seam is
used for a dry run, BUY rows must carry an allocation proof produced by the
shared `strategy.mode_switch.plan_board_lot_orders` allocator, using rolling
broker-reconciled strategy NAV under Contract §6. Missing or
inconsistent proof, cash, batch, exposure, slot, or board-lot facts fail closed.
Its market guard records `LIMIT_DOWN_BUY_BLOCKED` or
`LIMIT_DOWN_CHECK_UNAVAILABLE`; neither is a fill.

## Two-stage reporting

The prerecommendation Automation must return a final/inbox Chinese result as soon
as `recommend_<date>.md` exists, before any agent review. Show one ★E table and
mark execution fields `待模拟成交`. Mention ★B vs ★ only as a retained
forced-contrast line. This is a completed information-delivery stage, not a claim
that paper execution is complete.

After the separate execution Automation ends, send its final ledger update. The table columns are:

`★E | code | name | mode | state | basket | basket_rule | sim_price | shares | notional | position_pct | K/P | open_pct | auc_pct | auc_residual_imb | basis | sentiment/news | paper_buy`

Rules:

- Use `-` for missing values. Never substitute ★B when ★E is empty.
- `state` includes ACTIVE/PROVISIONAL, selected window and pool/market LCB80.
- `position_pct` shows target and actual notional as a percentage of settled NAV.
- `paper_buy` compresses fee, fill basis/limit, window VWAP/high/low/last and retry/fallback/skip state.
- `basket` is an abandon bound, not the assumed fill. Lead the final summary with basket versus actual fill, shares, deployed capital, resulting exposure and cash.
- Treat `auc_residual_imb` as a sign: the post-match residual book is one-sided by construction.

Frame posture only from produced evidence: regime, breadth, limit-up/down counts and actual sentiment/news. The posture is narrative context, never a pick filter.

## Verify

Inspect the dated versions of:

- `output/live/auto/<date>_morning-prerecommend.log`
- `output/live/run_flow_<date>_morning-prerecommend.json`
- `output/live/auto/<date>_morning-execute.log`
- `output/live/run_flow_<date>_morning-execute.json`
- `output/live/recommend_<date>.md`
- `output/live/intelligence_review_queue_<date>.json`
- `output/live/signal_snapshots.jsonl`
- `output/live/positions.jsonl`
- `output/live/paper_account.json`
- `output/live/paper_account_T.json`
- `output/live/paper_trades.jsonl`
- `output/live/paper_skips.jsonl` when present

Candidate truth and booked truth are different. A recommendation is not a buy; prove the buy from positions/trades/accounts.

## Terminal states and anomalies

Prerecommendation completion requires its shell to terminate successfully and the
dated report, queue and required same-run signal capture to exist. A K/P degradation
may be supporting-only; a capture failure is deterministic failure. Execution completion separately requires its shell to
terminate and the final ledger state to be checked. Never conflate the two.

Normal bounded states: no raw candidates, no executable mode, no Book-T slot, review timeout with base-pick fallback, or a documented unfilled limit.

Escalate: script failure/traceback, missing recommendation or paper-record stage, torn/corrupt snapshots, missing mode evidence, AI hard veto, insufficient cash, suspicious fill metadata, ledger inconsistency, or a run-flow/log disagreement.

## Early preparation and urgent continuation

### Invocation ownership

Before any morning business command, query `PYTHONPATH=src .venv/bin/python -m xiaocao calendar latest --date today`. A latest date different from today ends the task as `NON_TRADING_DAY`: no APP/KOL work, freeze wait, historical reconciliation, notification retry or trading alert. An unproved calendar stops before APP work. Weekday scheduling alone is not trading-day evidence. The standalone APP runner independently checks `/stock/trade_cal` before native preflight and notices.

An already terminated, no-effect preflight failure may be continued by its same
dated owner with `--resume-preflight-receipt <exact runs/history receipt>`, under
the receipt-bound once-only and original-budget rules in
[book-b-live-repair.md](book-b-live-repair.md). Preserve the original committed
producer bundle. Never replay a completed/no-action result or use this entry
for existing BUY intents; those require exact-plan recovery. Reuse only fresh
exact zero-fill prior-day SELL proof, retaining UNKNOWN and same-code BUY fences.

The fresh scheduler-created task for today's 09:00 slot owns the runner and
its stdout, review rendezvous, orders, receipts, and notices. A human follow-up
in an older Automation task is a repair/inspection task, even when it has the
same Automation ID and is active at 09:00. It works in an isolated checkout and
returns an exact repair; only an explicit transfer from the user plus readback
of the dated owner changes that role. Do not infer ownership from the clock,
task title, checkout, or shared Automation ID.

When a new scheduled task receives `SAME_AUTOMATION_RUNNING`, report the exact
dated lock owner and stop that duplicate task's business path. The current
owner alone completes preflight, KOL projection/review, execution, and notice
readback. A live unified-exec session is scoped to its task, so sending its
session ID to another task is not a handoff. During 09:25–09:30, coordinate
only a concrete `dependency_recovery_wait` or exact failure needing one bounded
repair; the runner owner consumes its own next stage event.

Start at 09:00 with the default 2100-second freeze wait and a short initial
command yield. Runner stage JSON is the event source. Do not model-poll,
repeatedly call `write_stdin`, or emit unchanged status before a stage event or
the 09:24 recovery boundary. While it waits, build the 11:30-horizon capsule:

The runner's duplicate-run lock is scoped to `xiaocao-book-b-live-morning`
and the trading date; it records automation ID, task ID and PID. A remote
writer's task ownership never suppresses this morning task. Resource locks
protect only their actual ledger or native APP operations, not unrelated KOL
work. Diagnose the emitted failure code and actual lock owner before calling
an unlock failure a lock conflict.

The original runner rejects a foreign inherited `CODEX_AUTOMATION_ID` or
`--automation-id` before native preflight. Stage events and immutable terminal
receipts bind the automation ID, actual `CODEX_THREAD_ID`, PID and entrypoint.
A separately authorized exact-plan recovery uses its actual automation ID;
it cannot generate a second morning candidate batch.

The runner records preflight start, APP ready and recoverable dependency problems
locally. Trading WeCom sends one consolidated opening result; an explicit
user-only dependency may notify immediately. Per-order incidents remain durable
locally and are included in the same result. Unchanged same-day recovery results
are deduplicated; `morning_preflight_alert.py --kind book-b --receipt ...` reuses
the runner result claim. Messages explain result, cause and required user action
in plain Chinese, with exact order IDs; hashes, paths and diagnostics stay in Codex. `ready` means native session/account preflight passed, not future
quote/capital permission. A preflight failure reports that opening execution
was not reached. If the original runner is still active at 09:30 without a
terminal receipt, its deterministic notification timer sends an explicit
unproved/pending window result; recovery continues and later sends the actual
terminal result. The timer neither polls the APP nor stops the plan. The
delivery worker is asynchronous during trading; terminal
readback retains recipient delivery times and any pending/uncertain outcome.
Report problems on failure and exact orders/fills on success. Never manufacture
a ready notice or retrospective start. After business work, use
`PYTHONPATH=src .venv/bin/python scripts/morning_trade_notice.py --retry-pending`;
only proven pre-send failures retry automatically. Claimed/uncertain deliveries
require reconciliation and already delivered recipients never resend. Exact
terminal receipts may be notified with `--receipt <path>` without replaying
the trading runner. On macOS the relay uses the native curl TLS stack, keeping
credentials/body on stdin and preserving the configured TLS verification policy.

The single authentication-only market probe runs at this preparation boundary.
Recovery events from the producer and paper freeze wait reach the operator
stream immediately through the daily supervisor, even while detailed output
is logged or the shell waits for its result. On an event, recover the exact
original dependency; read its cited request instead of starting another run.
When the latest bound producer has a failed terminal and no original bundle,
the paper consumer records producer failure and proceeds with independent
Book T once. An active producer or a committed bundle still follows the
original wait/repair path; failed data never becomes NONE.

On `dependency_recovery_wait` with `recovery_kind=app_client_login`, keep the
original runner alive and follow the first-client-login sequence in
`foundersc-native-ax.md` immediately. The authorized morning workflow includes
saved-password fill and visual CAPTCHA completion; routine client login is
agent recovery. Preserve the exact request and signal its recheck only after
same-account native readiness is proved. Missing credentials, macOS permission,
actual credential rejection or uncertain password action retain human-only
handling. Typed Keychain read timeout before helper invocation retries every
two seconds only with durable no-password/no-confirmation evidence.

If it reports `MARKET_LOGIN_REQUIRES_USER` or another authentication block,
preserve the original runner's wait. For `MARKET_LOGIN_CAPTCHA_REQUIRED`, the
current client has not submitted the saved password: run the local
`--captcha-from-keychain` command in a PTY with short yield, inspect its
emitted image with `view_image`, and enter one visually verified code into
the waiting process. OCR may assist but cannot be the sole evidence for an
ambiguous character. The recovery lock covers challenge fetch, agent input,
login and token storage. An explicitly rejected/expired CAPTCHA fetches a new
challenge, at most three in this owner; inspect each image before entering its
code. Password/account rejection stops; unknown rejection retains its distinct
category and cooldown rather than claiming the saved password is wrong. After
agent recovery, verify
with one fresh-process probe and consume only a valid immutable producer freeze.

The 09:00 readiness surface is deliberately small:

1. The original runner's initial event/terminal receipt proves native session,
   account binding, capital/ownership and old-intent state. Do not duplicate
   App queries or release an UNKNOWN order to make a green preflight.
2. The one uncached market authentication read proves the stored token; on
   990502 the agent obtains a new token through the single challenge flow,
   then verifies one fresh-process read. Pre-open empty rows are not source
   completeness failure. The 09:25:01 producer validates its actual dated inputs.
3. Run `scripts/morning_preflight_alert.py --date today --kind transport`
   once to prove a trading WeCom recipient and relay configuration exist;
   this is read-only and does not claim delivery. Save the KOL projection and
   its quality separately; degraded coverage uses the deterministic baseline.
4. If authentication remains blocked after repair, run the alert command with
   `--kind market-auth`. If the original runner ends blocked, use `--kind book-b
   --receipt <exact terminal receipt_path>`. A failed original 09:25:01 producer
   uses `--kind producer --receipt <exact run_flow path>`. The alert script
   makes a dated durable incident, sends urgent trading WeCom once for a
   delivered incident, and prints delivery readback; `unproven` or missing
   transport is still a blocker to report, never human acknowledgement.

The 09:24 native session recheck and 09:25 account/quote/market guards remain
fresh action-time checks; a 09:00 green status cannot pre-authorize them.

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_trading_context.py projection \
  --cache-only --history-fresh-through <today>T11:30:00+08:00
```

Read only its `projection_path`, `projection_sha256`, stable
`source_fingerprint`, counts and quality. Use `source_fingerprint`, not the
audit-time-dependent projection hash, to decide whether source semantics changed. The model body contains every typed, still-valid Book-B short-term `current`
viewpoint that independently passes the published semantic standard, plus only
its necessary relation history; there is no fixed count or latest-N cutoff.
`uncertain`, non-short,
unclassified and inoperable viewpoints remain counts, not context. It contains
no report bodies. Never open a `classification_backfill` manifest in the morning
or infer classifications from keywords, holdings or asset names. Missing or structurally degraded
projection evidence falls back to the deterministic baseline and remains a
remote-writer quality issue. One current-applicability worker receives this
projection plus the exact freeze and runtime facts. The parent independently
reviews the mapping and counterevidence. Reuse a still-valid published decision.

During 09:25–09:30, unexpected AX/code errors or missing KOL material are urgent
work. Patch the smallest failure, validate affected correctness, resume the
same plan and read the terminal result. Keep full tests, packaging, Git and
postmortem work after this flow. There is no 09:28:30 reminder or 09:30 automatic
skip. The final review waits at most 120 seconds and, before opening, only until 09:27; this reserves submission time and retains explicit neutral fallback. The 09:25 BUY floor, actual session/market eligibility,
immutable plan and unknown-submit reconciliation still apply.

Inspect `recommend_source_readiness_<date>.json` alongside the freeze. Empty or
partial responses and stable candidates do not prove source completeness.
Preserve selected observation evidence and final-attempt status; never rerun
the producer after freezing. Stage timings remain in receipts for later
performance diagnosis, not as extra approval gates.

At formal decision publication, load only the exact cited report IDs into a
full hashed context and perform the existing remote readback. This verification
step does not authorize general historical rereading. At 09:00 also run
`market_data_preflight.py --date today --scope authentication`; a successful
empty response proves reachability only. Leave the APP untouched after initial
preflight until the runner's 09:24 recovery event. Source freshness and current
applicability remain independent.

### Submit the batch before waiting for fills

The runner supplies hash-bound account/allocation facts and account-risk receipt
before final review. Use that exact request; do not duplicate the account read.
Send only a changed `source_fingerprint` and current applicability facts. Never invent
an opening fact or publish an authority=0 projection as a current decision.

The runner holds one account fence across full-batch allocation and serialized submissions. A fully mapped, chain-certain ACK/PARTIAL allows the next reserved order; UNKNOWN or incomplete identity stops new writes. Fill polling starts after the submission pass. Inspect submission_observations for actual counter-acceptance proof and deadline performance; prepare completion is not submission. Preserve APP raw order states: queued is not exchange-accepted and neither is a fill. If orders remain open, the original task owns exact-plan reconciliation until terminal or an explicit recorded checkpoint handoff; never leave a bare unresolved receipt without naming the pending orders and next owner.


### Bounded counter-submission hot path

For an entirely new BUY batch, the production CLI and rehearsal share
`submission_batch`: hold the account writer fence and native App session,
validate positions/orders/trades/funds and cancellation capability once, reserve
the whole immutable batch notional within available cash, and expire the local
observations after 60 seconds. At most five engineering plans are supported;
production selection remains at most three seats. Current account/form identity,
KOL restrictions, market guards and capital authorization still apply per order.
No full-grid query belongs between successful counter acknowledgements.

An exact native confirmed action plus the account-bound prepared tuple and unique
`委托已提交` success-notice contract number outside the baseline/earlier batch IDs
may prove ACK. Persist action/result and the claim binding. This is counter
acceptance only: `fill_observation_pending=true`; zero observed fill does not
prove zero actual fill. Full order/trade reconciliation starts after the submission
pass and remains mandatory. Missing/suspect success notices take the existing
exact table path, invalidate batch reuse and stop further fast-path submissions.
Existing claims/recovery, SELL and cancellation retain current-table checks.
Clear batch observations before reconciliation and on every context exit.

Report preflight duration, first-to-last counter acknowledgement duration and
their total separately, plus terminal cleanup. After the September 16 change,
offline behavior is verified; the new APP speed requires fresh 2/3/5-order
acceptance. Earlier 70.366/105.654-second runs used the old orchestration and are
not performance evidence for this path.


## New-BUY critical path and operator context

Operating Contract §1c/§4 governs the scoped buying-power route. The normal
native morning uses one account-bound positions capture for available cash and
owned-lot risk, sharing it for up to 60 seconds while the ownership head is
unchanged. At batch entry read positions and order identities/related tuples;
unrelated statuses, fills, valuations and cancel readiness cannot block the
new BUY. Complete native structure and relevant cell confidence remain required.
The execution port performs the one real form preparation and readback just
before claim/submit; the separate clear-after-readback rehearsal is omitted for
new morning orders. Recovery keeps its established prepare/reconcile route.
Full order/trade/account reconciliation follows the submission pass.

Before 09:20 retain the immutable viewpoint projection path/hash and its quality
summary; no source notes or conditional opening draft exists. After 09:24 react
to runner stage events. Read `brief_path` first, fetch missing fields from
`request_path` only as needed, and select fields from the terminal artifact.
Never print full candidate arrays, account tables, report-id arrays or source
caches into the operator stream. Full detail stays in immutable artifacts.


## Book T budget and historical corrections

Operating Contract §4b/§6 governs the independent T sleeve. The production
producer freezes the original T capital, exposure cap, held cost and cash.
Never apply the total-capital 30% allocation a second time to T equity, resize
a canonical control fill or reuse a post-control held lot as a new shadow fill.

The shadow consumer resolves registered corrections under
`output/research/book_t_v2_budget_repairs` and verifies source and derived hashes.
Keep original freezes, v1 receipts and global lifecycle evidence unchanged.
Historical correction inputs are research rehearsals and are excluded from
both 5/20-day natural acceptance and strategy promotion; report their count
separately. Missing/corrupt registration is a binding failure. Do not regenerate
history from current market facts or rerun the formal T writer to repair it.
