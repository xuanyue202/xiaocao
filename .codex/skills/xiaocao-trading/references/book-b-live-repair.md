# Book-B live task repair

Read this file after any non-normal Book-B live-morning result, unexpected
block, provider/native read failure, or repeated failure fingerprint.

Apply Operating Contract §1a to this deployment: local digital simulation and
APP-server simulation remain separate experiments. The user identifies the
current APP service as simulation with no real brokerage-account effects;
legacy `live` labels are not backend verification. Keep strategy, allocation,
execution guards and receipt standards unchanged. The APP route consumes its
service receipts, never local paper fills.

## Ownership and outcome classes

Run the full live-morning command exactly once. The started task owns repair;
do not defer a recoverable problem to the next Automation.

Classify the observed state before changing anything:

- `terminal_safe`: a deterministic time, market, strategy, capital, or safety
  gate ended the run without an unresolved broker effect. Report the exact
  terminal state; do not turn it into an order.
- `repair_required`: code, configuration, parsing, orchestration, or read-only
  evidence is broken and can be fixed within the repository or current task.
- `reconcile_only`: a durable claim exists or any broker write may have
  happened. Only read the exact plan/order/fill state; never repeat prepare,
  Return, confirmation, submit, cancel, or replacement.
- `user_action_required`: only authentication, SMS/CAPTCHA, consent, macOS
  unlock/Accessibility, an unavailable user-only fact, or an external effect
  that remains uncertain after exact readback.

Exact-once prevents duplicate external effects. It does not permit a task to
stop after a safely repairable local failure.

## Urgent repair: restore the current flow first

For `repair_required`, keep the same task alive and perform this loop:

1. Preserve the exact receipt, durable state, failure code and fingerprint.
   Determine whether a write may already have happened; uncertainty takes the
   reconcile-only branch. Read only the matching prior failure note if needed.
2. Locate and patch the smallest failing AX/helper/adapter or orchestration
   boundary. Preserve unrelated work. Agent UI observation may diagnose the
   fault; trading-form manipulation is not an emergency execution fallback.
   All continuation runs through project code and its normal execution port.
3. Perform minimum necessary validation: syntax/import or Swift build for the
   touched runtime, plus a focused reproduction or read-only boundary check
   that proves the reported failure is repaired. Reuse an existing focused
   test when useful; a new unit test is not mandatory before continuation.
   If the change touches account binding, code/side/price/quantity, submit
   claims or receipt mapping, validate that affected invariant before resuming.
   Never weaken a check or bypass a failing test to regain execution.
4. Continue immediately through the exact narrow resume authorized by durable state.
   If no safe continuation exists, adding a read-only or state-bound resume is
   part of the repair. Recheck current session/market eligibility through the
   existing guards; use only the contract's bounded guard-refresh exception.
   Never replay an uncertain broker action or revive an expired/terminal plan.
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
cross-field invariant is transiently unproven. Keep every invariant unchanged.
Record attempts, failure codes, and `actions=native_readback_only`; exhaustion
remains fail-closed. Account/date mismatch and every broker write are
non-retryable. Between whole-snapshot attempts, the native route may leave the
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

After the terminal outcome, record the cause, fix, verification and residual
blocker. Append its failure fingerprint and prevention to the Automation
memory. If the same failure fingerprint already exists, the previous
prevention failed: repair a deeper boundary or invariant before returning.
