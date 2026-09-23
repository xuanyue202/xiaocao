# EOD automation

Read this file only for the daily post-close capture/evaluation branch.

## Execute

Read same-day chronology first:

```bash
python3 scripts/show_journal.py --date today
bash scripts/auto_daily.sh eod
```

Keep the shell alive until it exits. `forward_eval` can be quiet for several minutes because API/cache fills are rate-limited; do not restart it or launch a duplicate writer.

After the paper EOD shell exits, run the independent real-capital Book-B
settlement exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase eod
```

The live EOD entry point rejects calls before 15:00 China time or on a date
other than the declared trade date. The oldest observed time across the three
broker row tables must also be at or after 15:00. This prevents a premature or
cached run from making an intraday NAV immutable.

This is read/reconcile/settle only: it creates no new SELL decision or order.
It reconciles existing durable live plans through the native execution port,
requires fresh account-bound positions/orders/trades row tables plus the funds
summary embedded in the same positions capture, projects
only broker-proved Book-B owned fills, and writes the immutable settled NAV only
when every live plan is terminal or a prior-day owned SELL has fresh, exact
zero-fill order/trade/full-holding proof for the same day. The exception leaves
that SELL open and fenced from duplicate same-lot writes. Never add
`--execute-sells` to the EOD call.
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
- Push the status digest, run Friday verdict recording when applicable, check flywheels, and update posture/exit calibration plus backlog sweep.

Do not repair account state, settle or infer any of these by hand. Code and
orchestration defects follow the daily review repair loop below.

## Verify decisive artifacts

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
A later-lot decision marked `PRIOR_NONTERMINAL_SELL_HANDOFF` proves it was
assessed but deliberately had no second broker write; a missing decision row
is incomplete coverage, not a no-sell judgment.

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
ownership/broker mismatch, any nonterminal or UNKNOWN plan at EOD, and settlement
immutability/hash failure.

Completion requires terminal evidence for both the paper EOD shell and live EOD
process, dated run-flow/log, paper ledger/account agreement, attribution check,
benchmark report, plus either a hash-bound real settlement or an explicit
reconcile blocker. If a code/orchestration repair is identified, completion of
the audit also requires its named owner, repair status and next legal
verification checkpoint; `reconcile_only` does not close that separate defect.
Do not claim completion from intermediate commentary.
