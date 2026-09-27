# Book-B live task repair

Read this file after any non-normal Book-B live-morning result, unexpected
block, provider/native read failure, or repeated failure fingerprint.

Apply Operating Contract §1a to this deployment: local digital simulation and
APP-server simulation remain separate experiments. The user identifies the
current APP service as simulation with no real brokerage-account effects;
legacy `live` labels are not backend verification. Keep strategy, allocation,
execution guards and receipt standards unchanged. The APP route consumes its
service receipts, never local paper fills.

## Priority and dependency test

The 09:25–09:30 frozen-candidate BUY and every legal protective/closing SELL
window are the first repair priority: their missed opportunities cannot be
recreated by an after-hours replay. Morning is a BUY owner; opening, 14:25
and 14:45 are separate owned-lot SELL owners. Start their prescribed business
command on time. During a failure, classify each blocked step as a true
prerequisite for the next legal order or as supporting reconciliation/reporting.
Run normal full readback first; record and defer a non-prerequisite failure so
it does not consume the window. A prerequisite gets bounded Python/AX recovery,
then model-assisted multimodal diagnosis and restoration of the needed atom.
The model uses the frozen plan and project execution port first. A direct APP
operation is an emergency path only when its account, plan, claim, price,
quantity, action and resulting broker receipt can be durably correlated.

Within this transaction priority, preserve order identity, current APP
sellable, T+1, quote/time and ownership as per-order inputs. An old UNKNOWN
claim does not globally block independent candidates or lots. On a later
trading day, fresh APP sellable may authorize a new SELL for the same owned
lot; keep the old and new order identities open for separate reconciliation.
The best-evidence path reads positions/orders/trades and funds. If only the
current account-bound APP sellable quantity is available, continue a legal
protective exit through the dedicated sell-only path, mark the omitted facts
unproven, and cap the new order by both APP sellable and durable owned shares.
Never promote a partial sell-only observation to BUY/NAV/EOD authority.

## Ownership and outcome classes

Run the full live-morning command exactly once. The started task owns repair;
do not defer a recoverable problem to the next Automation.

Classify the observed state before changing anything:

- `terminal_safe`: a deterministic time, market, strategy, capital, or safety
  gate ended the run without an unresolved broker effect. Report the exact
  terminal state; do not turn it into an order.
- `repair_required`: code, configuration, parsing, orchestration, or read-only
  evidence is broken and can be fixed within the repository or current task.
- `reconcile_only`: a durable claim exists or a broker write may have happened.
  Reconcile that exact plan/order/fill without blind same-claim replay. Keep
  other independent transactions moving; a fresh, separately dated SELL may
  use current APP sellable and a new durable claim while the old claim stays
  unresolved.
- `user_action_required`: only missing credentials, SMS/consent, macOS
  unlock/Accessibility, an unavailable user-only fact, or an external effect
  that remains uncertain after exact readback. A market-data image CAPTCHA
  with saved credentials is agent-recoverable through the bounded local
  `--captcha-from-keychain` flow; it does not require user intervention.

Exact-once prevents duplicate external effects. It does not permit a task to
stop after a safely repairable local failure.

## Urgent repair: restore the current flow first

For `repair_required`, keep the same task alive and perform this loop:

1. Preserve the exact receipt, durable state, failure code and fingerprint.
   Determine which action's side effect is uncertain and isolate that claim;
   test whether it is a prerequisite for the next legal trade. Read only the
   matching prior failure note if needed.
2. Locate and patch the smallest failing AX/helper/adapter or orchestration
   boundary. Preserve unrelated work. Use project Python atoms first; when
   they cannot recover in time, use multimodal APP observation and only a
   plan/claim-bound direct operation with exact broker readback.
3. Perform minimum necessary validation: syntax/import or Swift build for the
   touched runtime, plus a focused reproduction or read-only boundary check
   that proves the reported failure is repaired. Reuse an existing focused
   test when useful; a new unit test is not mandatory before continuation.
   If the change touches account binding, code/side/price/quantity, submit
   claims or receipt mapping, validate that affected invariant before resuming.
   Never weaken a check or bypass a failing test to regain execution.
4. Continue immediately through the exact narrow resume authorized by durable state.
   The critical 09:25–09:30 window makes local repair and missing evidence retrieval
   urgent; 09:30 is not an automatic stop. Preserve original session/plan validity.
   If no safe continuation exists, adding a read-only or state-bound resume is
   part of the repair. Recheck current session/market eligibility through the
   existing guards; use only the contract's bounded guard-refresh exception.
   Decide replayability from the exact claim and broker effects, never from a
   timeout alone. Do not revive an expired/terminal plan. A new dated SELL
   for currently sellable owned shares is a separate plan, not a replay.
5. Reconcile terminal service/account artifacts. A process exit, click, form,
   or local status line is not completion.

Do not put full regression suites, multi-hypothesis writeups, packaging for
distribution, commit or push ahead of this continuation. Build/install the
changed helper only when the current execution needs it. Record fault time,
repair-ready time, minimum validation, resume time and terminal outcome so the
latency and any missed opportunity remain measurable. Minimum validation that
cannot establish order correctness is a remaining blocker, not a passed repair.

## Root-cause repair: after the terminal outcome

In the same task, add regression coverage for a demonstrated failure when useful;
investigate competing causes only when causality remains uncertain. Replace a tactical
patch with a durable root fix if needed, then test the affected behavior.
Add safety tests only for affected order/account/claim/receipt boundaries;
do not run a whole safety suite for a documentation or unrelated parser edit.
Tests must detect a concrete wrong outcome, not require particular prose,
document versions, model names, line counts or implementation spelling.
Full analysis and broader regression belong here, not on the
urgent path. Preserve the already recorded trade outcome; never rerun a trade
to demonstrate the root fix. Stage only the repair allowlist and, after scoped
validation, commit/push the coherent repair for the collaborating writer.

## Read-only recovery boundary

Positions, orders, trades, account-summary, and allocation queries may repeat
as a bounded whole-snapshot read when parsing, freshness evidence, or a strict
cross-field invariant is transiently unproven. BUY/NAV/EOD keep those proofs.
For a legal protective SELL, when full readback still fails, obtain current
account-bound APP sellable through the separate sell-only capability, mark
every omitted table/amount unknown and retain the full-reconciliation work
item. Build and validate this capability before using it if the installed
Python port lacks it. Record attempts, failure codes, actual evidence grade
and `actions=native_readback_only`. Account/date mismatch blocks the affected
order; a timeout after possible broker write requires claim-bound readback
before any replay decision. Between whole-snapshot attempts, the native route may leave the
sticky full-query surface through ordinary order-surface navigation and enter
it again without touching code, price, quantity or submit. If the normal
five-minute trade lock appears during that read-only recovery, it may consume
the fixed Keychain item once; an unproved unlock is terminal and never loops.
Record successful resets as `surface_resets`. A structurally unproved
read-only navigation or its transport timeout records
`surface_reset_failure_codes` and preserves the remaining whole-snapshot read
budget; it never permits another navigation click or weakens the final
snapshot proof.

## Closeout

Before closing a blocked run, inspect `pending_orders` and
`incident_notifications` in the terminal notice. Report the exact unresolved
plan/order and existing WeCom delivery time/status; relay acceptance is not user
acknowledgement. The order incident outbox may already have delivered an alert
even when the morning created no new order. Repair local evidence gaps and
narrow-resume before reporting an irreducible external blocker. A written
next-owner note is not an accepted handoff.

For an early morning preflight failure, use the exact terminal receipt with
`scripts/morning_preflight_alert.py --date today --kind book-b --receipt <path>`
as soon as the blocked receipt is durable, while bounded local repair continues.
This is a separate dated urgent WeCom
incident from an order's existing notification. Read back whether it was
delivered; absence of a new order does not suppress the preflight alert.

Historical reconciliation refreshes both query tables before capture. This does
not set or prove the UI date range; exact row date and order identity remain
mandatory. A refreshed `已报` with no observed trades is still unproven, not a
terminal cancellation. Preserve its raw status in locator evidence.

After the terminal outcome, record the cause, fix, verification and residual
blocker. Append its failure fingerprint and prevention to the Automation
memory. If the same failure fingerprint already exists, the previous
prevention failed: repair a deeper boundary or invariant before returning.
If the repair changes strategy selection, capital permission, permanent
parameters or a safety gate, commit its validated code, enqueue a specific
WeCom change notice with `scripts/trading_change_notice.py`, and attempt
delivery. Keep a failed notice pending for every later task's post-business
retry; transport failure does not undo the validated APP-simulation repair.

## Formal same-plan recovery

### Production takeover map

Before any repair or continuation, locate the existing dated run archive under
`output/live/book_b_live_execution/runs/`, its persisted plan/claim events and
the latest exact APP order/trade readback. Name the affected owner, plan ID,
plan hash, broker order ID if any, last possible write, legal window and next
permitted action. An `executed` checkpoint is not fill proof; inspect each
execution receipt and the corresponding broker row.

| Current owner | Same-plan continuation |
|---|---|
| 09:25 BUY | Use the dated `book_b_live_morning.py --resume-plan-id ... --recovery-action resume/reconcile` command below. `resume` requires an unclaimed valid plan; a possible write uses exact-claim reconciliation. |
| Opening/14:25/14:45 SELL | The intraday script currently has no `--resume-plan-id` CLI. Keep the original task as owner, inspect its durable SELL plan/claim, and restore the smallest blocked Python/AX dependency. Resume through the existing execution port only while the plan and window remain valid; add a plan-bound narrow entry if the checkpoint cannot safely continue. Do not invoke raw native submit/cancel with only a code/price/quantity tuple. |
| Post-write UNKNOWN or cancel claim | Reconcile the exact existing claim and contract number through APP order/trade rows. A prior-day UNKNOWN is separate from a new dated owned-lot SELL using current APP sellable. |
| 15:00 EOD | Read/reconcile/settle only after every plan has terminal proof. An EOD rerun cannot restore an expired SELL window. |

Use the production-path review at
`docs/reviews/2026-09-27-native-app-production-path-review.md` for the observed
Sep 18/23 order and settlement cases. Its unresolved SELL-only and narrow
takeover gaps are implementation work, not authority to infer missing facts.
For a BUY, separate server ACK, price/other server rejection and actual fill.
A unique contract-number ACK advances the pre-reserved batch but remains open
until trade readback. A user-observed price-limit rejection is not currently a
recognized native retry path: first capture its exact message and prove the
old claim's absence or terminal order/fill state; then add and validate a
fresh-price, basket- and time-bound immutable retry through the execution
port. An unrecognized result stays `UNKNOWN/reconcile_only`, never a blind
second click. Record each order's acceptance and fill separately.
For a closing SELL, inspect the order's `filled_shares`, `remaining_shares`,
`state`, current bid and time before calling the checkpoint complete. An
`ACKNOWLEDGED` or `PARTIAL` receipt is still an open exit. The current native
adapter has no automatic SELL replacement or within-window fill controller:
keep the task owner on exact readback/repair and record the unsold amount and
next-session capacity impact. Any new same-day order for that unsold amount
needs a durable cancel-terminal/fill proof and a separate plan/claim; a raw
second native click cannot supply that proof. Implement and validate the
plan-bound continuation before asserting a SELL completion recovery.

Use the existing dated intent and `--resume-plan-id`, never restart the producer:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_morning.py --date YYYY-MM-DD --route native-app --resume-plan-id '<original-plan-id>' --recovery-action resume
```

`resume` continues an unclaimed BUY within its original recovery deadline/session,
using unchanged plan hash and original dated freeze. A possible write takes the
execution module's reconcile path without prepare or a new semantic review.
`--recovery-action reconcile` explicitly requests that submitted-order branch.
`--recovery-action close` only closes a proven unclaimed local intent, without
accessing the App or Keychain; a claim/uncertain result rejects closure. It is
not a broker cancellation. Terminal results are idempotent.

Inspect `runs/history/<run_id>.json`: `recovery_of`, `stage_times`, `failed_stage`,
`persisted_plan_ids` and execution receipts. The original daily failure receipt
is preserved. Partial materialization must report persisted intents even when
the builder failed before returning a plan list. The next normal checkpoint
closes a truly expired unclaimed intent; uncertain effects remain open for
reconciliation. Deadline pressure never weakens necessary judgment.

Before actual expiry, a proven unclaimed BUY remains with its original owner;
the intraday monitor reports `deferred_buy_plan_ids` and continues existing
owned-lot protection without taking over that BUY. Claim/uncertainty, pending
SELL and final settlement retain their existing reconciliation requirements.
For AX clear/readiness timing, use the bounded checks in
`foundersc-native-ax.md`; do not add a long stable-empty wait.

During 09:25–09:30, immediately fix an unexpected local failure and validate only
the affected behavior before resuming. For missing KOL material, use the current
reading pack and exact report-ID retrieval in `kol-trading-judgment.md`; do not
restart broad research. Do not wait for 09:28:30, schedule countdown warnings or
close a plan simply because 09:30 arrives. Keep the original strategy and plan
authority; quote, order identity and unknown-side-effect checks still apply.
