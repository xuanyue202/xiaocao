# 2026-11-13 morning reliability repair

Baseline: `fac487f625ce68b9943774d806b133d55832227d`.
Authorization: user requested all morning-review fixes, prioritizing missed KOL
preparation and improving both source and consumer handling of lateness.
Original receipts remain under `output/audit/morning-review-20261113/` in the
operating checkout; no dated business entry is replayed by this repair.

## Observed causes and changed behavior

| Observation | Repair | Evidence boundary |
|---|---|---|
|07:30 capture finished10:41; preparation started10:42|Acquired early/evening slot emits preparation obligation before child starts; owner immediately prepares coherent already-published snapshot while acquisition continues|Pending source publication stays explicit; one source/effect writer|
|Previous evening brief accepted21:44 but original sources expired00:00|Intended morning horizon checks each original expiry before model dispatch and brief expiry at acceptance|Blocked does not renew/drop sources or claim morning readiness|
|09:20 target miss discarded otherwise valid support|New conditional_first_v2 accepts late_ready at original freeze inside original120-second/earlier-owner/09:27:30 budget|v1 admission unchanged; missing support defers immediately, no worker/task wait|
|47 eligible semantic units unchanged but full registry audit fingerprint changed|Compare full viewpoint/evaluation/relation-history units, retain both audit fingerprints and hashes|Current independent review/source verification/publication still required; actual semantic delta defers|
|Paper shadow intelligence took102 seconds before business|Shadow/off review is not a business rendezvous dependency; immutable wait receipt preserves pending counts|On-mode still requires same-batch intelligence; KOL budget independent|
|All-COLD B waited for unused09:30–09:31 prices|Plan price capture over current-policy eligible reserve candidates; empty plan seals no_buy immediately|Locked writer rechecks policy/ledger; actual BUY still needs verified first-minute HIGH|
|T shadow added208 seconds before formal completion was visible|B/T control results are emitted separately before research; shadow follows both business children|Supervisor/shadow finality remains separately observed|
|K/P prepared27 prior candidates, only2 of today's9 covered|Use several prior original batches, newest first; save completed bounded chunks before unchanged deadline; report missing codes|No today's model inference, invented scores or training|
|T had1958 source bindings but0 themes and no dated structured judgment draft|Before freezing a new production research day, request the missing dated draft from the original post-business owner within one immutable120-second deadline; report theme readiness separately from qualification|Historical mirror cache stays historical-only; no fabricated decisions/fills or sample reset|
|Risk NORMAL and accounting BLOCKED were conflated|Add explanatory admission/exit/accounting scopes without changing original risk receipt|UNKNOWN, financial gates and actual-fee/final-PnL gaps remain|
|Producer's pending review and July posture caused generic warnings|Report queued/shadow status separately; expired posture is explicitly historical calibration only|Pending reviews are not completed; source/current policy freshness remains independent|

## Validation

Reproduced expiry-before-dispatch, exact semantic audit drift, shadow wait,
zero-candidate price capture as failing
behavior before their repairs. Scoped regression:411 passed; independent risk/accounting/lifecycle regression:332
passed. Deployment/contract checks initially exposed a stale producer09:18 test
expectation; active schedule and existing mirror were already09:10. Corrected
the deployment assertion without changing cadence; final closure130 checks plus
that corrected assertion passed.
APP-related engineering checks ran in the explicitly open11:30–13:00 test window;
all adapters were isolated fixtures, with no extra APP order or business replay.

## Next natural acceptance

- Existing21:30/07:30 owner: preparation obligation precedes long acquisition;
  exact target trading date/horizon, pending sources, accepted/reused/blocked and
  actual start/end clocks are visible independently of writer terminal status.
- Next new original morning request: new v2 SHA/mode, automatic own adoption,
  on-time/late-ready/deferred reason and original unextended support deadline.
  Actual source change/unknown predicate cannot silently reuse a draft.
- Producer/Paper/APP: separate baseline/preview/policy, complete business receipts,
  actual orders/fills and supervisor/research evidence. A zero-candidate branch
  avoids price work; an actual BUY retains the original cost/order proof.
- T: current sources are actually consumed, qualified natural samples and valid
  theme decisions remain independently counted. A working adapter does not prove
  strategy readiness, fresh NAV or profitability.

Source/configuration/test success is not natural-run acceptance. Actual fees,
final APP PnL, old unresolved claims, missing current sources/scores and inadequate
research samples remain unresolved until their own evidence exists.


## Independent review and deployment

Standards initially found the final-PnL schema mismatch and a missing APP test
marker; Spec found improper historical T cache admission and the same PnL issue.
All findings were fixed, behavior tests added and both independent re-reviews
passed against the explicit baseline and follow-up diff. Historical cache remains
reference-only. Missing T judgment is now reported honestly rather than promoted.

The four existing KOL/APP/producer/Paper Automations were updated through the
Automation API and reopened through that API. Exact prompt hashes and state were
read back from its written mirrors; status, host/project, model/effort,
notification preferences and cadences were preserved. The API card exposes no
machine-readable next-run timestamp; no schedule was changed or UTC-converted.
Deployment receipts and runtime hash closure are saved in the operating checkout
under `output/audit/morning-fixes-20261113/`.


Final source-gap follow-through: a new real T shadow day with no structured dated
draft now emits an owner-bound `book_t_v2_judgment_required` request before API
capture or immutable input creation. The original post-business process waits
at most120 seconds, admits a supplied draft through the existing source binder,
and retains the same deadline on follow-up. A timed-out request cannot admit a
late draft or refund its budget. Existing sealed days remain unchanged; injected
rehearsals and natural research qualification retain their original boundaries.
Follow-up independent review found bare-empty placeholders and mutable late draft
rereads; both are repaired. Requested replies require dated request/hash-bound
readiness_review; explicit empty results require reviewed no_supported_theme and
reasons. Actual received bytes/hash are snapshotted and passed directly into source
assembly; file-read and persistence time consume the original deadline. A received
snapshot alone is not completed research or a theme decision.
Focused request/producer/supervisor tests:38 passed. No financial branch waits on
this separate post-business research phase.
