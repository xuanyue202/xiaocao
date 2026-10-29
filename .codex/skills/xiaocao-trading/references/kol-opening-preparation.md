# KOL opening preparation

Use after the original owner's trading-day proof. This implements Operating
Contract §1d/§2a. Preparation is conditional, source-bound and `authority=0`;
only the existing final reviewed publication can influence Book B. Keep COLD's
default gate, the explicit Xiaocao v2 exception, UNKNOWN, current account/risk,
quote and exact-once gates. Never replay a completed run to validate this flow.

## Before 09:20: prepare once

APP consumes its original `book_b_kol_inputs_prepared` event directly. Paper
starts its original supervisor at 09:10 and, after its calendar proof, runs one
cache-only 11:30-horizon projection while the supervisor waits for 09:25:01.
Paper creates an input with `scripts/kol_trading_prepare.py inputs
--projection-summary <saved summary JSON> --binding <original owner JSON>
--output-dir <dated analysis directory>`; the binding contains `trade_date`,
`automation_id=xiaocao-daily-morning-execution`, `owner_thread_id` and original
supervisor `run_id`. Keep the same binding for its final input. No second
producer, account capture or paper writer is started. APP never rebuilds its
input outside the runner event.

Dispatch one worker with `model=gpt-6-sol`, `reasoning_effort=xhigh`,
`fork_turns=none`. Save actual accepted arguments/result, worker ID and aware
`dispatched_at`; the dispatch JSON also contains `accepted=true`, model/effort,
`input_sha256` (the input's runner hash) and exact `binding`. If routing or
complete preparation cannot finish before 09:20, defer new model work and use
only an independently valid policy or baseline under existing gates.

Give the worker the exact input, its complete compact projection, hash-bound
rules and this schema. Run `scripts/kol_trading_prepare.py template --input
<input> --output-dir <dir>` once. The worker reads **every eligible viewpoint**,
evaluation and necessary relation history once. It preserves published source
semantics; it prepares their possible trading implications, not a second source
summary. Fill the template:

- `worker_id`, actual aware `prepared_at`, `valid_until` no later than today's
  11:30 and applicable source validity.
- `implications`: each has unique `id`, `viewpoint_ids`, `kind` (portfolio_posture,
  mode_focus, code_risk or counterevidence), `scope` (`kind=all|modes|codes`,
  `values=[]` for all, otherwise exact system modes or codes), and text fields
  `source_wording`, `interpretation`, `conditions`, `invalidations`,
  `counterevidence`, `proposed_effect`. Say explicitly when no counterevidence
  is known. Portfolio posture and counterevidence use global scope. Unresolved
  mode mappings stay global so they cannot disappear through a spelling filter.
- `coverage`: one row per input viewpoint, with `viewpoint_id`, exact
  `implication_ids`, `disposition=implication|background|not_applicable`, `reason`.
  Every implication source appears in this ledger. Background is an explained
  disposition, never latest-N truncation or inferred keyword classification.

“轻仓” retains its wording and conditions; a numerical buy_scale needs explicit
reasoning and final independent review. “重点看” retains the source term and
exact/conditional/unmapped system mapping; it is not itself an order or COLD
exception. Preserve conflicting evidence and unresolved mappings.

Fetch only the exact reports cited by these implications **before** preparation
acceptance, using repeated `--report-id <id> --read-report-id <id>` with
`kol_trading_context.py context --summary`. Do not combine this with
`--cache-only` when a cited body is missing. Check selected body coverage and
hashes. This is citation verification, not re-authoring the source semantics.
Keep this full context for final publication if its source versions are still
current; publication performs its existing exact remote readback. Preparation
receipt embeds the context, so it is not a golden-window schema/body hunt.

The parent independently reviews complete coverage, source fidelity, scope,
conditions and counterevidence. Save review JSON: `accepted=true`, `reviewer_id`
different from worker, actual `reviewed_at`, canonical RFC8785 `draft_sha256`,
`context_sha256`, canonical `dispatch_sha256`, and true `all_viewpoints_covered`, `source_fidelity_checked`,
`conditions_and_counterevidence_checked`. A draft assertion is not acceptance.
Seal through `kol_trading_prepare.py accept --input <input> --draft <worker JSON>
--review <parent JSON> --dispatch <actual dispatch JSON> --context <context JSON>
--output-dir <dir>`. Preserve the returned preparation path/hash.

APP worker loading receipt contains `worker_id`, `loaded_viewpoint_ids`,
`dispatch_path`, **`preparation_path`**. Acknowledge it using the original
`morning_checklist.py --checklist <path> --input <input> --loaded <receipt>` under
its exact Automation/Thread. Paper resolves its original manifest-bound shared output mount to the canonical
deployment state root for context caches; foreign/nested cache symlinks remain
blocked. An early preparation failure is explicit and must be repaired before
09:20 where possible; do not summarize it as successfully prepared.
For Paper, pass the original manifest `execution_root` as `--root` to both
inputs and accept. Accept registers the sealed reference in the original run
directory after matching Automation/Thread/run identity; the supervisor reads
that reference, and the pinned runtime includes the same rule bytes. Keep the worker warm. Pre-read the final schema below now.

## At the original freeze: apply and verify changes

APP's original request contains `kol_inputs.packet_path/packet_sha256` produced
by the shared assembler. When the event includes `dispatch_path`, read that
one immutable handoff file and immediately send its exact `tool_arguments` to
the same warm worker. It includes the brief, hash-bound packet and actual assembly
clock; `actual_dispatch=not_observed` must be replaced only by a real tool receipt.
Do not add separate brief/schema/full-projection reads before dispatch. If no
accepted warm preparation exists, preserve the explicit degradation. Do not open the complete old projection again. Paper's original
`wait_for_agent_reviews.py` starts its KOL support branch independently of the
structured intelligence queue. It emits `paper_kol_review_requested` with a real
immutable request/hash, fresh cache-only input and assembled packet. Dispatch
that exact request to its warm worker. Empty/completed intelligence does not
end a pending KOL branch. Missing preparation, risk no-buy or cutoff produces
an explicit supporting receipt and continues the original paper writer.

Paper captures account/positions under a short ledger lock, fetches proprietary
marks outside that lock, then rechecks the original facts and computes a preview
against the existing risk head without writing high water or pause. The read-only
preview runs in an isolated child process group under the original absolute
deadline; timeout reaps it and any credential-read helpers, preserving the
original supervisor and writer. Model waits
hold no ledger lock. Original writer rechecks current account/risk and binds the
support receipt in strategy_adjudication; its actual consumption proves adoption.
Book T keeps its independent branch. No parent-constructed substitute request or
second paper writer is needed. The original wait budget is retained and KOL
support never extends past 09:27. Both consumers exclude publications bound to
this exact request at/after its original deadline at every policy read. A still-valid
independent policy remains reusable, and a newer independent judgment still
supersedes it; actual expiry and store-integrity gates remain current.

The packet contains relevant prepared implications, global posture/risks and
counterevidence, invalidated implications, and every added/changed/removed
viewpoint. Evaluation changes count as changes; relation/history changes
conservatively invalidate dependent preparation. Review **all delta** and its
relations, plus current candidates/account/risk and conditions. Changed/removed
source implications cannot be reused until reviewed against current evidence.
Rule changes, incomplete coverage, expiry or unproved preparation defer new
model work. No second complete analysis of unchanged sources. The same batch
policy serves all its orders; per-order checks consume it rather than spawning
another semantic review. New material evidence still invalidates stale policy.

Record actual dispatch time/arguments and remaining time. The original budget
covers model, exact cited-source verification, independent parent review and
publication together. If risk already blocks BUY, skip this supporting wait.
Do not publish or accept a late draft. Baseline fallback is not a completed
neutral judgment. Neither a prepared brief nor a packet grants trading authority.

## Final output schema: prepare the shape early

Use existing `kol_policy` schema `kol-trading-decision.v1` (v2 only for the
existing explicit Xiaocao override). Before dispatch, verify its current constant
and fields in `src/xiaocao/live/kol_policy.py`; do this during preparation.
Decision fields: `schema_version`, unique `decision_id`, actual `agent_id`,
`book=B`, this consumer's `runtime=live|paper`, UTC-Z `as_of`, `valid_until`,
`source_refs`, `buy_scale`, `skip_codes`, `exit_codes`, `rationale`,
`invalidation_conditions`, `current_checks`. Source refs contain exactly
`report_id`, `content_sha256`, `author_id`, `source_published_at`, `received_at`,
using the verified context's version receipt. Current checks contain claim,
observed_at, evidence_ref and verdict; material contradictions require explicit
resolution for APP. Retain the original request SHA in decision and review;
include `mode_mappings` and review `mode_mapping_reviewed=true`. For each mapping:
source_report_id, source_term, target_mode, classification
(exact/conditional/unmapped), current_applicability
(supported/uncertain/contradicted), conditions and reason. A v2 override also
needs exact mode, source_report_id, source_quote and frozen_candidates_only scope.

Parent review: exact **`kol_policy.decision_sha256(decision)`** (not RFC8785),
`status=approved`, distinct `reviewer_agent_id`, actual UTC-Z `reviewed_at`,
`coverage_complete`, `source_fidelity`, `applicability_checked`,
`counterevidence_checked`, full `context_sha256`, and
`acknowledged_unloaded_report_ids` from that context. Acknowledge any context
issues explicitly under the existing publisher rules. Publish through
`kol_trading_decision.py publish --decision <file> --review <file> --context
<file> --morning-request <exact original request_path>` before the original cutoff.
Morning-bound policies require that hash-matching original request. Source-read
budget and the final locked store admission use its absolute deadline; a completed
exact retry still only returns the original receipt. Unchanged early cited bodies may be reused;
the publisher still verifies exact current remote content/manifests. New cited
versions require their exact context; do not replace freshness with a claim.

## Completion evidence

Keep preparation accepted_at/coverage/hash, final dispatch clock, packet delta,
final policy publication and original consumer adoption separate. Report which
posture/mode/risk implications applied or did not apply, with reasons, then the
actual orders/fills and later return evidence. A loaded worker or preparation
receipt is neither a completed policy nor evidence of better returns.
