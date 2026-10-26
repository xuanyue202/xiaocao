# EOD automation

## Unified APP B lifecycle reporting (2026-10-22)

After the original paper EOD, APP EOD and statement readback finish, run the original `scripts/research_book_b_forward.py --phase eod` once through `scripts/eod_post_business.py --step research` with the same identity. This advances independent funded controls and refreshes their reports and the read-only APP lifecycle join. The paper shell does not run research acquisition before APP reconciliation; do not duplicate it with a second report call. Read [BOOK_B_WORKFLOW.md](../../../../docs/BOOK_B_WORKFLOW.md): model net returns, APP marked NAV, estimated profit and confirmed profit are distinct. Missing actual fees or unclassified cash keep confirmed profit unknown. A report never closes an order or grants settlement authority.


Read this file only for the daily post-close capture/evaluation branch.

APP Book B cash/NAV and performance use Operating Contract §6's dynamic
SQLite financial journal. Consume `account.accounting` and cite its observation,
journal and funding heads. Apply `docs/BOOK_B_ACCOUNTING.md` for profit/cost,
unclassified cash and actual fee finality. Missing itemized native fees keep net
profit unknown and block formal settlement even when cash happens to match;
report pending exact order identities. Accepted actual fee receipts append
differences to the shared journal; never classify a balance gap as a fee or
replace historical postings. Budget/exit-fee estimates retain their existing
scope. Paper A/B/T and historical settlements stay independent.

## Execute

After the original paper and APP processes terminate, execute each prescribed statement/research/feedback child once through `scripts/eod_post_business.py --step <statement|research|feedback>` with the same identity. This captures its actual exit and separate stdout; do not also invoke the child directly. A persistent claim forbids replacement after failure/interruption.

For post-business closeout, read [EOD_WEEKLY_FEEDBACK.md](../../../../docs/EOD_WEEKLY_FEEDBACK.md).
The paper shell defers its final WeCom digest. After both original processes,
the original statement/research/feedback and execution review are terminal,
read `scripts/eod_closeout.py --context --date <date>`, follow up prior Weekly
responses, and prepare the structured reviewed handoff described there.
Run the identity-bound `scripts/eod_closeout.py --review <dated-review.json>
--push-wecom` once. It verifies original ownership/terminal/hash/accounting
bindings, freezes daily issues, experiments and registered design acceptance,
then sends through the existing durable claim. Do not add business or report
replays. Leave missing terminal/source proof explicit and do not manufacture
a successful closeout. Verify delivery separately. An uncertain send is never
recovered by invoking closeout or status again; use the exact durable claim.
Weekly owns cross-day synthesis; EOD does receipt/hash audit only for KOL.

The scheduler wakes at 15:03. Enter the retained command promptly; both paper
and APP EOD entrypoints wait until 15:10 before their slot claims or business
effects. Each sleep is at most 60 seconds and rereads China wall time.

Before applying the command prefix, require this task's initial scheduler header
to say exactly `Automation ID: xiaocao-daily-eod`. If an inherited
`CODEX_AUTOMATION_ID` is nonempty and different, stop rather than replacing it.
Bind an absent ID only from that verified header; retain the actual runtime
`CODEX_THREAD_ID`. Environment fields are task binding evidence, not scheduler
authentication (the scheduler run-token gap remains in Contract §1c).
Read same-day chronology first:

```bash
python3 scripts/show_journal.py --date today
CODEX_AUTOMATION_ID=xiaocao-daily-eod bash scripts/auto_daily.sh eod
```

Retain the runtime `CODEX_THREAD_ID` and verify it against this task's initial
scheduler header before entry. Both EOD entrypoints require the exact Automation
ID and a nonempty thread identity. Each claims its separate paper/APP date slot
under `output/live/eod_task_slots/xiaocao-daily-eod/` before business work. Claims
survive success, failure and process exit; another task or top-level retry stops
without overwriting the original daily pointer. A failed slot permits only the
existing narrow recovery path, never deleting the claim or rerunning EOD.
These task claims do not replace account, order or paper-ledger resource guards.

Keep the shell alive until it exits. `forward_eval` can be quiet for several minutes because API/cache fills are rate-limited; do not restart it or launch a duplicate writer.

After the paper EOD shell exits, run the independent real-capital Book-B
settlement exactly once:

```bash
CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase eod
```

The live EOD entry point rejects calls before 15:00 China time or on a date
other than the declared trade date. The oldest observed time across the three
broker row tables must also be at or after 15:00. This prevents a premature or
cached run from making an intraday NAV immutable.

This is read/reconcile/settle only: it creates no new SELL decision or order.
It first reads fresh account-bound positions/orders/trades plus the positions
funds summary, then classifies historical SELL tasks under Operating Contract §4.
An independently disposed lot with validated chains, zero current same-code
account holdings and no contradictory current order/trade evidence becomes
`economically_closed` for EOD only; its original UNKNOWN, no-replay claim and
same-code BUY fence remain. Record the exact disposal/snapshot hashes in
`eod_review`; skip redundant old-history queries for that proved closure.
Every new EOD snapshot reevaluates the proof and reopens changed economic facts.
Current/unknown BUY, unproved disposal, residual holdings and new contradictory
fills remain active blockers. A zero holding or elapsed time alone cannot close.
The structured `eod_review` lists all execution/cash/actual-fee blockers together.
With accounting-only gaps, EOD terminates `observed` / `accounting_pending`;
formal immutable settlement and exact PnL still require their original cash and
itemized-fee proofs. Do not describe bookkeeping incompleteness as failed trade.
The original archive also retains `broker_snapshot`: the exact normalized
positions/orders/trades and positions-funds evidence used by that projection,
with its original clocks and snapshot hash. Default CLI output gives its archive
reference instead of printing the tables. Historical receipts without that field
retain an evidence gap; do not reconstruct or overwrite them from a later read.
Preserve any older settlement written through that
exception as historical evidence and disclose its failed terminal-plan audit.
The settlement loader and risk history exclude a hash-matched settlement whose
original EOD archive contains a nonterminal reconciliation receipt; report the
remaining valid basis and exact historical gap without rewriting either file.
Never add
`--execute-sells` to the EOD call.
The APP entrypoint durably queues an actionable blocked-result WeCom notice after saving its
original archive, including native login/read failures before a snapshot exists.
Use a stable economic incident identity across dates/runs/clocks. Unchanged
historical/economically-closed and accounting-only gaps stay in local evidence;
notify on current execution impact, meaningful state change or a concrete user
action. Exact legacy delivered/uncertain claims prevent equivalent resends.
If a code repair adds this delivery to an already terminated run, use
`scripts/book_b_eod_alert.py --receipt <exact-original-archive>` under the original
Automation/Thread identity. This notice-only recovery never queries APP or reruns
EOD; uncertain delivery remains pending for exact reconciliation.
For a terminated original EOD whose schema predates this review, use
`CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python scripts/book_b_eod_review.py --receipt <exact-original-archive>`
under its original runtime thread identity. This derives one hash-bound dated
review from the original account/snapshot and current unchanged journal heads,
records economic task closures and all remaining blockers, and makes no APP,
order, settlement, feedback or statement call. Keep the original archive intact.
After the original business process terminates, run
the original `scripts/book_b_accounting.py statement` once through `scripts/eod_post_business.py --step statement` to
export cumulative JSON/CSV. Retain its dated mark or missing/stale status even if
an old unresolved order blocks settlement; this export makes no APP query.
Transient structural, freshness-evidence, asset-equation, or cross-table
failure may trigger only the adapter's bounded whole-snapshot reread. Strict
invariants remain unchanged, the receipt records every read-only recovery
attempt, and exhaustion fails closed; never rerun the top-level EOD process or
replay a broker action to manufacture settlement.

KOL work at EOD is receipt/hash audit only. `kol_trading_decision.py feedback`
may trace source-preparation, decision, consumer and outcome receipts, but EOD
must not open report bodies, build a new semantic context, dispatch a semantic
Agent or publish/extend a decision. A missing link is recorded for the remote
writer or next sparse claim owner; it does not keep the EOD task alive.

A non-trading-day skip is a normal terminal state. Otherwise completion requires the dated run-flow to reach `eod done` and final artifacts to reconcile.

## What the orchestration owns

- Capture TICK features and reconstruct current daily bars from minute data for
  indices, open positions, current signals, and the previous live Book-B signal
  batch whose D+1 labels mature today.
- Run `data_doctor`; missing mature-batch reconstructed bars are CRITICAL and
  gate learning, not the capital half. Before today's EOD reconstruction starts,
  this coverage check intentionally stays quiet.
- Build forward A/B/C/D/E/F labels and intelligence shadow evidence.
- Monitor Book B and Book T, settle Book A, then settle Book T.
- Produce PnL decomposition and Book-B-versus-four-index report.
- Defer the final status digest to post-business closeout; run Friday verdict recording when applicable, check flywheels, and update posture/exit calibration plus backlog sweep.

Do not repair account state, settle or infer any of these by hand. Code and
orchestration defects follow the daily review repair loop below.

## Verify decisive artifacts

The WeCom status digest leads with APP-simulation Book B profit, then separately
labels paper B/A/T. It reads only the latest verified saved SQLite observation,
with its China observation clock; closeout requires the same original APP EOD
and statement observation before sending, without implying formal settlement. Missing/stale/invalid
evidence shows pending data. Cash or actual-fee gaps keep final profit unknown;
realized/floating accounting estimates are explicitly provisional (accepted
fees at actual amounts, missing fees at the plan rate). Never
replay a delivered digest to apply a presentation change.

- `output/live/run_flow_<date>_eod.json`
- `output/live/auto/<date>_eod.log`
- `output/live/eod_features.jsonl`
- `output/live/training_rows.parquet`
- `output/live/paper_account.json`
- `output/live/paper_account_A.json`
- `output/live/paper_account_T.json`
- `output/live/paper_holdings.json`
- `output/live/paper_holdings_T.json`
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- `output/live/pnl_decompose.csv`
- `output/live/decision_journal.jsonl`
- `output/research/paper_vs_market_<start>_<date>.md`
- `output/live/context_pack_<date>_eod.json`
- `output/live/book_b_live_execution/runs/intraday/<date>-eod.json`
- `output/live/book_b_live_execution/settlements/<date>.json`

Cross-check same-day sells from the journal/trades; the EOD monitor may be quiet after an earlier intraday/14:45 sell.

For Book T, use marked equity/unrealized only when `valuation_status=fresh`. Otherwise report cost-basis equity and `unrealized=N/A`; never combine a newer ledger with an older holdings mark. A post-14:45 `SELL_BLOCKED` remains open through settlement.

Book T ETF settlement must preserve the explicit instrument contract and use its
sell fee, lot size and T+0/T+1 rule. If the contract or authoritative market
facts are unknown, leave the position open and report the bounded block.

## Chinese audit order

1. Terminal status: shell exit, run-flow `deterministic_status`, supporting degradation and step count.
2. Data/learning: captured/reconstructed counts, `data_doctor`, labeled/executable rows.
3. A/B/C/D/E/F: take-all, ★, ★B, ★M, qibao benchmark, AI-intel shadow and ★E executable return; include B-vs-A contrast frequency and current mode-state changes. Small-n remains small-n.
4. Book A versus B: headline identical-entry paired B-A pp, eligible n and exclusions. Raw realized delta is accounting-only.
5. Book B versus index average: valid only at coverage `4/4`; otherwise index average/spread is `N/A`.
6. Paper Book B, real-capital Book B and Book T separately: cash/equity/realized/unrealized/open positions plus all same-day executed/blocked sells and next-session risk. Real Book-B uses its strategy-subaccount settled NAV and owned lots; broker mixed-account totals are evidence only.
7. PnL attribution: `pick_alpha / entry_slippage / exit_timing / fees` and both reconciliation lines.
8. Judgment layer: exit-rule hit rate only after its min-n floor; knowledge scoreboard in one line, plus top 1–3 cache-expressible research candidates only when `heavier`/KNOWLEDGE warns.

EOD is an audit, not a new bullish/bearish call. Stale posture, missing structured reviews, unchanged REJECTED verdicts and an open strategy flywheel are supporting/informational states, not capital failures. Strategy flywheel `blocked` (unconsumed PASS) is an anomaly requiring a proposal or weekly consumption path.

## Daily analysis and execution review

After the original paper/live EOD processes and KOL feedback terminate, review
the whole trading day even if settlement is blocked. Do not delay settlement
for this investigation, restart EOD, or launch a second business writer.

Review from effects upward, not from another agent's final paragraph. For each
anomalous checkpoint, inspect its actual Codex task turn/trace (`read_thread`
when available), command/tool exit and error output, original dated run receipt,
durable intent/event chain, broker readback or paper ledger, and the next
checkpoint's observed effect. A final answer, memory note, `exit 0`, or
`deterministic_status=succeeded` is a claim to test against those layers, not
the source of truth. Read bounded, relevant trace spans around the first
failure, repair attempt and terminal readback; avoid rereading unrelated KOL
report bodies. If a trace is unavailable, name the missing layer and keep the
cause unproven. Record contradictions between an agent's conclusion and its
tool outputs explicitly.

Treat zero-fill accepted SELL, repeated UNKNOWN, missing settlement, same-lot
or all-lot evaluation gaps, unexpected no-action, delayed/missing Automation
turn, failed tool call, missing incident delivery, and a capital block despite
unchanged cash/holdings as investigation triggers. For each, ask what actually
changed in the account, which code guard made the next decision, and what
counterfactual observation would falsify the suspected cause. Carry the exact
fingerprint forward until code repair, tests and the next natural production
readback are separately evidenced.
A later-lot decision proves assessment, while its distinct plan and execution
receipt prove whether that lot reached the broker. An earlier nonterminal SELL
is not a reason to suppress another currently sellable owned lot; a missing
decision row is incomplete coverage, not a no-sell judgment.

1. Compare the active Automation schedule and actual task/process timestamps
   against dated receipts for morning analysis, candidate freeze, buy execution,
   opening/sparse monitoring, 14:25 precheck, 14:45 closing and EOD. Check missing
   or duplicate runs, scheduler delay, startup overhead, lock starvation and
   window misses separately. If the business process started late, inspect the
   scheduled task turn and any failed attempt before calling it scheduler delay:
   an app/backend error, user restart and shell startup are distinct clocks.
   A correct time-gate rejection can still expose an
   orchestration defect upstream.
   For learning, verify the latest usable executable signal date and new
   executable labels, not just growing theoretical-label counts. Repeated
   `LIMIT_DOWN_CHECK_UNAVAILABLE` across mature rows is a data-path anomaly:
   historical fill evaluation must validate original market facts at the
   historical entry clock, never against the current EOD clock. Missing facts
   remain unknown/retryable evidence, not permanently cached unfillable trades.
   The bounded executable backfill queue processes recent mature signals first;
   old retryable gaps must not consume the whole budget ahead of new D+1 rows.
   Compare `latest` executable date with `latest_mature` in the terminal log.
   A newer theoretical date alone does not prove new executable evidence.
2. Trace current source -> reviewed analysis -> decision -> consumer using
   source hashes, applicability, review status and timestamps. Check stale or
   incomplete analysis, timeouts and lost consumption links. Missing evidence
   is unknown. Check frozen candidate/mode consistency and each actual buy's
   allocation and execution gates without changing strategy parameters.
3. For every owned lot, explain each sell/hold/block from evidence available at
   that checkpoint, including T+1, hard versus deferred soft exits and any
   validated KOL input. Historical missed sells are never replayed. Future
   sell decisions use current evidence and the current authorized exit policy
   at a legal checkpoint; today's profit does not vindicate yesterday's missed
   evaluation, and a loss alone does not prove a defect. A no-sell result is
   verified only by a timely, complete evaluation, not absence of an order.
4. Trace intents to exact plan/order/fill IDs, side and quantity, broker-proved
   ownership, cash and settlement. Keep paper/live explanations separate;
   paper fills cannot prove live execution. Check UNKNOWN, mismatches, stale
   marks, missing artifacts and immutable settlement integrity.
   A blocked morning receipt retains its completed materialization count and
   last returned execution observations. Cross-check durable intents/events:
   an exception during materialization may precede that count, and an ACK
   before a failed read is still unresolved. Keep the original failure receipt
   separate from later repair or owner-abandonment evidence.
   For any accepted or UNKNOWN SELL with zero observed fill, compare its
   submission time and limit against the point-in-time quote/best bid (if
   available), subsequent trade prices, remaining auction time and exact
   broker order/trade/holding readback. A falling trade price is evidence of
   lost marketability, not proof of the sole cause or permission to cancel or
   resubmit. Check whether a late start, stale limit, incomplete other-lot
   evaluation or global open-plan guard caused an independent code or
   orchestration fault. Trace the same plan's effect on the next morning's
   available cash, owned lots, NAV/exposure cap, risk receipt and EOD
   settlement; distinguish order uncertainty from an unnecessary global BUY
   block. A repeated blocker is not resolved by repeating `reconcile_only`.
5. Classify each finding as expected terminal state, repair_required,
   reconcile_only or user_action_required. For safely repairable code,
   configuration or orchestration faults, the started task owns repair: follow
   `book-b-live-repair.md` for urgent repair, minimum necessary validation and
   exact narrow continuation of the current reconcile/settle work first;
   root-cause analysis and tests selected for the affected behavior follow
   its terminal outcome. Apply Operating Contract §1a to distinguish the two
   simulation levels without relaxing execution or accounting standards. Preserve
   unrelated work and commit/push only the validated repair allowlist. Use the
   existing Automation API plus readback for scheduling changes. This repair
   branch never starts live-morning or replays an expired checkpoint. EOD
   remains read/reconcile/settle only; no top-level rerun, new order, uncertain
   broker-action retry, fabricated ledger, immutable-history rewrite, weakened
   time/capital/safety gate or automatic strategy promotion is allowed.
   A deterministic defect in the earlier closing or next-morning code is still
   repair_required even if the broker order itself remains reconcile_only.
   Repair that source/config fault after business terminals with one owner,
   focused validation and a future natural-run readback; do not defer it merely
   because the EOD command cannot submit a trade. Check durable incident
   delivery separately from whether the final summary mentioned the alert.
   Order incidents and EOD/change notices share the durable delivery claim.
   The paper status digest also uses the shared delivery claim, with exact dated
text in `output/live/paper_eod_status_notices.jsonl`. Include this outbox in the
post-business safe retry through `scripts/trading_change_notice.py --outbox
output/live/paper_eod_status_notices.jsonl --retry-pending`; never replay the
status digest command to recover an uncertain send. Historical direct-send
logs without a durable claim remain a delivery evidence gap.
Include `output/live/sell_result_notices.jsonl` in the same post-business
`trading_change_notice.py --outbox <path> --retry-pending` pass for paper/APP
sale outcomes. Recover only queued exact claims; never replay a trade or invent
a historical notification claim to fill a delivery gap.
Retry only proved pre-send failures; legacy pending, interrupted sends and
   uncertain/partial delivery require exact reconciliation, never another send.
6. Write `output/live/daily_execution_review_<date>.md`: expected versus actual,
   evidence paths/timestamps, impact, stable failure fingerprint, concise cause/fix/verification for
   defects, repair and regression proof, production verification status and
   next legal verification checkpoint. Check prior Automation memory for
   recurrence, append prevention/results, and keep unresolved defects visible.
   Distinguish code repaired, tests passed and production verified; an external
   blocker or missed window remains explicit, never a claimed full repair.

Include this review's result and artifact link in the Chinese final report.
If a prior repair has its first production opportunity today, explicitly
verify it using today's receipts; do not require a trade just to pass the audit.

## Anomaly escalation and completion

Escalate: nonzero script exit/traceback, missing run-flow or expected artifact,
incomplete step chain, data-doctor CRITICAL, HARD_STOP,
SELL_BLOCKED/unresolved event risk, PnL/account `MISMATCH`, Book-T
ledger/valuation drift, missing index coverage, or clearly unusual A/B/F
behavior. For real Book B also escalate incomplete three-table/positions-funds readback,
ownership/broker mismatch, any active economically relevant nonterminal or UNKNOWN
plan at EOD, and settlement immutability/hash failure. A proved economically_closed
historical task stays in the internal audit while its facts are unchanged.

Completion requires terminal evidence for both the paper EOD shell and live EOD
process, dated run-flow/log, paper ledger/account agreement, attribution check,
benchmark report, plus either a hash-bound formal settlement or a complete structured
review of active execution and accounting evidence. If a code/orchestration repair is identified, completion of
the audit also requires its named owner, repair status and next legal
verification checkpoint; `reconcile_only` does not close that separate defect.
Do not claim completion from intermediate commentary.
