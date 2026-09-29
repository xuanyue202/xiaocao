# Book B financial journal production code review

Status: reviewed-and-repaired; final scoped validation passed, deployment tracked in automation memory
Date: 2026-09-29
Reviewed diff: `git diff 3c34921d4312f8c8af9629493dea3cd519ae8143...84418bed551fdca35b3a37221fe1b9fdec6a50c6`
Commit: `84418be Unify Book B accounting with a transactional SQLite journal`
Spec: [approved design review](REVIEW.md), user instruction to reuse existing mechanisms and keep code maintainable.

Independent Standards and Spec agents reviewed the same fixed diff in parallel.
All reproductions used temporary directories after the APP test-window gate;
the review made no APP actions or changes to original production source facts.

## Standards

**P1, documented violation:** the new accounting observation write was a
prerequisite for returning independently proved owned lots. Both protective
intraday projections occurred before SELL handoff. Injecting a SQLite read/write
failure prevented the handoff, contrary to Operating Contract §1b's
“非前置依赖记缺口并继续”.

**Maintainability judgment, possible Duplicated Code:** lifecycle and scoped
BUY preflight duplicated the economic cash-basis classification. Future
reservation changes could make the two reports disagree.

Repair: centralize cash-basis classification inside the accounting interface.
Only the two non-EOD monitor projections may degrade SQLite storage errors,
after original account/ownership/current quantity checks. Export cash, NAV and
capital numbers as unavailable; BUY/settlement reject this capsule. Original
source/equation failures remain terminal, and per-order market, capital, claim,
quantity and native ACK guards stay intact. Post-fill risk refresh returns a
blocked receipt instead of losing already-proved execution receipts.
The policy/account binding is checked before the degradable storage block;
unavailable capital numbers are also excluded from durable risk-event evidence.

Standards total: one confirmed P1 and one maintainability judgment; worst issue
was the unnecessary protective-SELL accounting prerequisite. Both repaired.

## Spec

**P1, reproduced source-chain poisoning:** the design requires funding at the
flow's exact valuation time (REVIEW.md:20). Cash replay filtered events by the
snapshot time but cited the latest cash-event head. With allocation at t0,
fee −5 at t2, and a still-fresh t1 cash snapshot, explicit funding appended a
row then failed `BOOK_B_CAPITAL_FLOW_EQUATION_INVALID`; all later flow reads
failed. Repair: reject newer cash evidence before observation/flow persistence,
and reuse the full flow validator on the candidate before append. Regression
proves original bytes remain unchanged and a fresh t3 snapshot recovers.

**P2, incomplete detailed statement:** REVIEW.md:56 requires lot, unit price,
notional and confirmation information. The first CSV omitted these existing
source fields. Repair: project lot, source execution/event IDs, price, amount,
Book/account/environment, trade date, observed time and posting status. Missing
native trade IDs or actual per-trade clocks stay empty. Version-bound export
names preserve old statements when the projection schema changes.

**P2, missing correction mechanism:** REVIEW.md:62 requires “纠错用冲正与新分录”.
The first implementation could not represent a sourced fee refund/correction.
Repair: the existing cash-event interface accepts a proved full reversal of
one same-account fee/dividend/interest posting. Amount must be exactly opposite;
the target is unique and cannot itself be a reversal. Original facts remain,
and all cash/head/funding consumers include the reversal. This does not rewrite
owned fills, orders or quantities; missing provider correction evidence blocks.

Spec total: one P1 and two P2 findings; worst issue was a permanently invalid
funding row after an out-of-order capture. All three repaired; no independent
scope-creep finding.

## Additional production reproduction

An intent-only BUY with ledger cash 100000 and APP available cash 99995 returned
`reconciled` and zero profit using derived cash, even though no broker freeze
was proved. The approved design requires frozen cash to be owned and proved.
Repair: derive reservation state from original execution evidence, mark
`cash_reserve_reconciliation_required`, and report cumulative PnL/difference
as unavailable. Keep original reservation and execution gates intact.

## Validation and limits

Affected tests cover read/write storage failures, protective SELL handoff and
proved mock fills, risk-refresh failure with terminal receipt preservation,
strict BUY/EOD, corrupt original source, earlier cash snapshots, exact capital
recovery, reservation uncertainty, source-projected CSV, and idempotent reversal.
The database remains standard-library SQLite with the original account lock,
balanced cent postings and one original evidence replay; no new order engine.

Actual native cash-statement capture is still absent. Estimated trade fees and
missing broker trade IDs are disclosed, not manufactured. Original historical
UNKNOWNs and the current marked-observation/formal-settlement distinction remain.

Both axes and the supplemental production issue were repaired without changing
strategy ratios, capital permissions, original source facts or paper ledgers.

Final validation: 698 affected tests passed in 5.10s in the open APP test window.
Independent follow-up accepted the repaired Spec boundaries and both final
Standards guards; no remaining actionable issue in that follow-up scope.
Production replay retained the same 14 entries, journal/valuation heads and all
23 original source-file hashes. Backup restore produced identical detailed rows.
The expanded statement used a new schema-bound filename and retained the old CSV.
These checks do not substitute for a future natural automation run or native
actual-fee evidence.
