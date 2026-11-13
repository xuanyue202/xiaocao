# Conditional-first morning

New morning requests bind `judgment_mode=conditional_first_v2` into their immutable
SHA. Source owner prepares before09:20; consumer finishes as soon as ready, within
min(original requested_at+max_wait_seconds (at most120), review_wait_until,
entry_deadline, dated09:27:30). At or after the bound, degrade and continue the
original execution path. This reserves the opening tail for allocation/serial
acceptance; it is not order/fill proof or permission to extend the09:30 window.
Existing v1 requests retain their09:20 preparation-admission and original09:27:30
or earlier recorded budgets. Older legacy requests retain original09:27.
For v2,09:20 is a readiness target: valid late support is marked late_ready and
checked once at original freeze without waiting for the source owner. Exact
semantic-unit equality (viewpoints/evaluations/relation history) permits reuse
across audit-only fingerprint drift; preserve both fingerprints and normal current
source verification. Semantic change/unmatched/unknown conditions defer immediately.

## Source owner before the window

Read all eligible published sources once, preserving chronology, revisions,
counterevidence and missing coverage. Author and independently review the existing
policy_template and typed selection_preferences. Express exact source-supported
request predicates and candidate conditions; separate their invalidation. Current
request predicates are only account_risk_status/account_deploy_factor/trade_date/
actual session_phase. Candidate fields use the existing typed selector. Unknown
breadth/private scores/mappings and unsupported position numbers remain unresolved.
Do not invent thresholds, clear unknowns or promote COLD to obtain an effect.
An explicit dated auction WAIT requires its existing restrictive-branch review
and09:30 expiry. Preparation review grants no final policy authority.

## Original consumer at freeze

Code validates shared preparation/adoption, full source fingerprint/delta, original
freeze/request hash and explicit predicates. No current analyst is preloaded or
launched. Missing/changed/stale/unmatched/unresolved support returns a named
deferred receipt immediately; a known invalid independent policy remains blocked.
No completed neutral judgment is inferred from empty preferences or fallback.

Read the one original dispatch path and follow its next_action:

- `independently_review_prepared_draft`: read the exact decision_path and
  context_path from prepared_policy_path, verify their bound hashes and current
  request facts. Independently review that actual draft now using the normal
  [trading judgment](kol-trading-judgment.md) review schema. Reject or defer if its
  semantics/effects/conditions are unsupported. Preparation review cannot be
  copied as final approval. Publish through the existing
  `kol_trading_decision.py publish` with exact decision, independently authored
  review, prepared context and `--morning-request <original request_path>`.
  The publisher performs normal exact current remote-source verification and
  checks the same deadline again before admission. Do not repeat full synthesis,
  inspect unrelated sources or wait for another task. Finish immediately when
  ready; the deadline is a cap, not a target.
- `continue_original_baseline_deferred`: report its reason/uncertainty, skip model
  and publication, let the original runner continue independently valid policy
  and deterministic baseline gates. Do not turn degradation into NONE from failed
  data, an order success or a late recovery attempt.

APP and Paper retain separate account facts, independent review/publication and
consumer receipts. Producer remains authority0, preserves original recommendation
bytes and never publishes policy. Rules changes require new source preparation;
old artifacts/source archives remain historical evidence, never current adoption.
