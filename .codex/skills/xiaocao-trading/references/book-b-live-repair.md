# Book-B live task repair

Read this file after any non-normal Book-B live-morning result, unexpected
block, provider/native read failure, or repeated failure fingerprint.

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

## First-principles repair loop

For `repair_required`, keep the same task alive and perform this loop:

1. Preserve the exact receipt, durable state, failure code, and a stable
   failure fingerprint. Check the Automation memory for the same fingerprint.
2. Add a tight red test that reproduces the failed boundary without a broker
   write.
3. List 3–5 falsifiable hypotheses, rank them, and eliminate alternatives with
   current evidence. Do not weaken account, asset, date, market, capital, or
   exact-order invariants to make the test pass.
4. Patch the smallest owning boundary, make the red test green, then run its
   focused regression group and the relevant live safety suite.
5. Continue only through the exact narrow resume authorized by durable state.
   If no safe continuation exists, adding a read-only or state-bound resume is
   part of the repair. Never replay an uncertain broker action.
6. Reconcile terminal broker/account artifacts. A process exit, click, form,
   or local status line is not completion.

Preserve unrelated work. Stage only the repair allowlist. After scoped
validation, commit and push the coherent repair so another live writer cannot
encounter the old code.

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
Record the successful navigation count as `surface_resets`.

## Required 5 Why closeout

After the terminal outcome, write a concise 5 Why covering symptom, causal
chain, root cause, code/contract fix, regression proof, and residual external
blocker. Append its failure fingerprint and prevention to the Automation
memory. If the same failure fingerprint already exists, the previous
prevention failed: repair a deeper boundary or invariant before returning.
