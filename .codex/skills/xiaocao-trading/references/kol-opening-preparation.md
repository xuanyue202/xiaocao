# KOL opening preparation

Use after the original owner's trading-day proof. This implements Operating
Contract §1d/§2a. Preparation is conditional, source-bound and `authority=0`;
only the existing final reviewed publication can influence Book B. Keep COLD's
default gate, the explicit Xiaocao v2 exception, UNKNOWN, current account/risk,
quote and exact-once gates. Never replay a completed run to validate this flow.

## Before 09:20: prepare once

APP consumes its original `book_b_kol_inputs_prepared` event directly and owns
one complete conditional preparation. Its successful `accept` command publishes
the shared source reference immediately under the same Automation/Thread; APP
account readiness, final checklist acknowledgement and execution are separate.

Paper starts its original supervisor at09:10 after calendar proof, without
another source-preparation worker. At original freeze the supervisor reads the
shared accepted brief once, builds its fresh cache-only projection and creates
`kol-preparation-adoption.json` under its original run. This binds Paper's exact
Automation/Thread/run, current input/rules/fingerprint and the original APP
preparation path/hash/source binding. Source/viewpoint/evaluation/relation or
rule changes, expiry, ambiguity and missing support defer KOL promptly; no
APP-status polling, duplicated model preparation or extended budget. APP keeps
its original owner and receipt; adoption grants no policy/account authority.
Legacy exact Paper-owned preparation references remain readable.

APP preparation owner only: dispatch one worker with `model=gpt-6-sol`, `reasoning_effort=xhigh`,
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

Organize implications by the actual decision that may change: shared environment,
mode conditions, candidate preference or code risk. Compatible viewpoints can
support one implication with each source attribution and condition preserved;
conflicting direction, horizon or conditions stay separate. Every eligible
viewpoint still has its own coverage row. Explain background/not-applicable
items rather than expanding each into another operational instruction. There is
no fixed implication cap and no keyword/latest-N filtering. At final dispatch,
review current applicability/delta and emit the existing bounded policy; reuse
unchanged reasoning. For user-authorized mode/sector/candidate preferences,
also fill optional `selection_preferences` using the typed schema in
`src/xiaocao/kol/selection.py`: unique id, kind/target, direction
prefer|deprioritize, source_report_id/source_quote/rationale, current
applicability supported|uncertain|contradicted and explicit conditions.
List order is priority; no invented numeric score boost. Candidate targets bind
code+mode; sector targets bind exact frozen excIndustryCode/blockCodeList/
blockCategoryCodeList codes and a hash-bound `kol-sector-map.v1` file with
observed_at/source_ref/entries(field,code,name). Verify source quote and sector
map before acceptance; parent review sets selection_preferences_reviewed=true.
Uncertain/contradicted or unproved conditions have no sorting effect. Ordinary
preferences never qualify COLD/UNKNOWN, absent codes or unfillable candidates.

To keep new model work out of an unchanged opening, also author `policy_template`
during preparation: buy_scale/skip_codes/exit_codes/rationale/
invalidation_conditions/xiaocao_mode_overrides/mode_mappings, exact
source_report_ids, request_conditions and unresolved_semantic_conditions.
`prepared_policy.py` defines the executable schema; request conditions currently
support explicit account_risk_status/account_deploy_factor predicates, while
candidate conditions remain on each preference. Every important unrepresented
semantic condition belongs in unresolved_semantic_conditions; an empty list
must be justified by the analyst and independent parent, not assumed. Parent
sets policy_template_reviewed=true after source/effect/condition review.
Template acceptance grants no final decision review or publication authority.
When no executable overlay is justified, the analyst may explicitly set
policy_template.defer_if_no_effect=true and parent deferred_overlay_reviewed=true.
This authorizes only prompt baseline fallback: unchanged full source/delta,
satisfied request conditions, neutral template risk effects and no applicable
selection preference. Keep unresolved conditions. It declares KOL deferred,
not completed neutral review, and preserves every independent valid policy and
original trading gate. Any executable effect or changed source disables it.

“轻仓” retains its wording and conditions; a numerical buy_scale needs explicit
reasoning and final independent review. “重点看” retains the source term and
exact/conditional/unmapped system mapping; it is not itself an order or COLD
exception. Preserve conflicting evidence and unresolved mappings.

Fetch only the exact reports cited by these implications **before** preparation
acceptance, using repeated `--report-id <id> --read-report-id <id>` with
`kol_trading_context.py context --decision-sources --summary`. Do not combine this with
`--cache-only` when a cited body is missing. Check selected body coverage and
hashes. This is citation verification, not re-authoring the source semantics.
Run `kol_trading_decision.py context-check --context <context.json>` now.
Require `context_ready` before sealing; a known author/longitudinal/body gap
is preparation recovery work, not a surprise for 09:25. This read-only check
grants no policy authority. Complete published writer receipts supply history;
only the explicit reports receive current remote head checks, so unrelated
archive expiry does not schedule a full remote reread. Missing writer proof
remains explicit rather than being marked fresh.
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
APP acknowledgement also registers the accepted preparation immutably for
daily morning's local recommendation preview. Prepare preferences before the
09:25 capture; the producer never waits or launches another analyst. This
authority=0 preview has its own receipt and never counts as APP/Paper adoption.
The shared reference is source reasoning only. Paper's adopted packet retains
the source worker as provenance, never as a cross-thread follow-up target.
Pre-read the final schema below during the original wait.

## At the original freeze: apply and verify changes

APP's original request contains `kol_inputs.packet_path/packet_sha256` produced
by the shared assembler. When the event includes `dispatch_path`, read that
one immutable handoff file. If next_action=independently_review_prepared_draft,
read its exact prepared_policy_path: the code assembled an authority0 draft
from an accepted template, unchanged source fingerprint/full delta and satisfied
explicit current conditions. It contains small decision/source hash references;
pass decision_path/context_path to the publisher. Unchanged full context stays
in its immutable sidecar, rather than being reopened by the parent merely for
publication. Independently review that draft against this
request's embedded current facts and all original source conditions, then publish
through the usual exact context/current-source verification before cutoff.
Create an actual new final review bound to decision/context/request hashes;
the earlier preparation review cannot substitute. This branch invokes no model.
If next_action=continue_original_baseline_deferred, original code records the
explicit KOL deferred receipt and continues its own valid-policy/baseline gates;
read its known unresolved conditions without dispatching or publishing a neutral
substitute. This is a separately reviewed fallback, not judgment completion.
If next_action=dispatch_current_worker, spawn the exact provided gpt-6-sol/xhigh/
fork-none worker in the Paper thread. Only current applicability/delta is new;
reuse the independently accepted prepared implications and conditions. Do not
address an APP child agent or reread the complete unchanged source projection.
If next_action=dispatch_warm_worker, immediately send exact tool_arguments to
the same worker; a new source/delta/unresolved condition requires its judgment.
The handoff includes the brief, hash-bound packet and actual assembly
clock; `actual_dispatch=not_observed` must be replaced only by a real tool receipt.
Do not add separate brief/schema/full-projection reads before dispatch. If no
accepted warm preparation exists, preserve the explicit degradation. Do not open the complete old projection again. Paper's original
`wait_for_agent_reviews.py` starts its KOL support branch independently of the
structured intelligence queue. It emits `paper_kol_review_requested` with a real
immutable request/hash, fresh cache-only input and assembled packet. Dispatch
the exact request through its emitted next_action. Empty/completed intelligence does not
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

Use `kol-trading-decision.v3` for selection preferences, preserving v1 risk fields
and the existing v2-equivalent Xiaocao override. Its `selection_preferences`
reuse reviewed prepared semantics with current conditions; `selection_binding`
copies only market_date/strategy_run_id/strategy_sha/snapshot_sha256/
snapshot_raw_sha256/snapshot_row_count/checkpoint_sha256 from the exact original
request.freeze. Review also sets selection_preferences_reviewed=true. No new
sorting claim is needed when preferences=[]; justified neutral is valid.
V1/v2 remain supported. Before dispatch, verify its current constant
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
the publisher still verifies exact current remote report heads and complete manifests.
A matching manifest reuses its hash-verified immutable records; changed or missing
records must be read and reviewed, not silently accepted. New cited
versions require their exact context; do not replace freshness with a claim.

## Completion evidence

Keep preparation accepted_at/coverage/hash, final dispatch clock, packet delta,
final policy publication and original consumer adoption separate. Report which
posture/mode/risk implications applied or did not apply, with reasons, then the
actual orders/fills and later return evidence. A loaded worker or preparation
receipt is neither a completed policy nor evidence of better returns.
