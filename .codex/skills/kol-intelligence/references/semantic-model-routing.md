# Semantic model routing

Use for new Xiaocao transcript work at the remote hourly writer's three
semantic-input events, including exact resumes. Other authors retain their
existing route. Acquisition, provider waits, mailbox operations, and downstream
effects remain on the Automation's configured parent model. The user has
authorized a subagent specifically for semantic judgment: `gpt-6-astra` with
`reasoning_effort=xhigh` (极高), not an inferred default or `max`.

## Prepare and delegate

Rollout starts with one Xiaocao pilot. The parent independently reads the full
source and compares it with the analyst's report before enabling future
Automation routing. Preserve a hash-bound review showing material omissions,
attribution/number/timing errors, their corrections, and the final verdict.
Structural validation alone never passes this quality gate. After the pilot
passes, repeat parent review for every newly acquired Xiaocao transcript.

1. Keep the same runner stdin open. Bind the emitted immutable request to its
   absolute file, source identity/version, full evidence path/hash, and stable
   segment inventory. Preserve provider pause/close receipts. Read
   `full-contract.md` completely and honor any pinned request hash.
2. Use `scripts/kol_semantic_delegation.py prepare` (consult its `--help`) to
   persist the context packet. Include separately captured market evidence and
   household context when available, with source/as-of/limitations. A missing
   fact is explicit uncertainty, not permission to invent one. Include current
   knowledge feedback and the applicable durable-knowledge contract when that
   branch applies. Give full-file pointers, never only a parent summary.
3. Dispatch the packet's exact invocation through `spawn_agent`, explicitly
   setting `model=gpt-6-astra`, `reasoning_effort=xhigh`, and
   `fork_context=false`. Persist the actual accepted tool arguments and returned
   agent ID with `record-dispatch`. This records the accepted invocation, not
   cryptographic proof of the backend inference. Never manufacture a successful
   dispatch from a model label in prose.
4. Give each analyst a disjoint item artifact directory. The analyst reopens
   and hashes the full evidence, reads the complete contract, extracts every
   investment thesis, independently rereads every stable segment, resolves
   entities, checks dated market facts, and writes the final 灰常亮 reader copy
   plus applicable attributed knowledge, returning the draft paths, coverage
   result, and changed-file list. Exclude mailbox, browser/provider,
   publication, notifications, Book, ack, shared ledgers, Git, and Automation
   writes from its authority.

The analyst owns judgment and final wording; the parent owns operational
coordination. The stronger model does not replace the full coverage audit,
exact quotation checks, current-fact limitations, or paper-only boundaries.

## Accept and publish

5. Read Astra's reader copy and verify material source claims before sealing
   the result. Independently cover the entire source, not just a sample or the
   analyst's summary: concrete assets/actions, exceptions, triggers, invalidators,
   numerical/statistical claims, and dense late-source passages must survive.
   Keep historical/as-of limits and source claims separate from system inference.
   Record the review against source and draft hashes; an unresolved material
   omission or distortion means revise. Send corrections to the same analyst.
   The parent then
   runs the deterministic `scripts/kol_semantic_bundle.py` builder on the
   unedited Astra draft and separate market evidence. Run `verify-result`
   against that exact request, accepted dispatch, and canonical bundle.
   Validate full segment coverage, request/evidence hashes, market evidence,
   final receipt, and the permitted knowledge branch. Do not rewrite the
   approved report on the parent model while calling it Astra output.
   Write `parent_source_review.json` beside the immutable request using the
   `verify_semantic_review` schema in `src/xiaocao/kol/semantic_delegation.py`:
   all five evidence-backed checks and every reviewed segment, with exact
   request/packet/draft/bundle/receipt/knowledge hashes. Call `verify-result`
   with `--semantic-review`; the hourly consumer requires `parent_accepted`.
   A local structural `verified` result or `not_assessed` is insufficient.
6. Only the parent returns the validated `bundle_path` to the same runner.
   Let the existing deterministic pipeline publish the exact approved report
   and reconcile its stable URL/receipt before eligible reminders, Book
   KOL-US, knowledge ingestion, and final mailbox ack. Use the unchanged
   per-object terminal tuple and claim/receipt parity for completion.

## Resume and failures

- Reuse the exact request/packet/agent and validated result after interruption.
  If stdin died, reconcile the item and use only the runner-issued narrow
  continuation. Completed acquisition and external effects remain immutable.
- A wrong/unavailable model, missing dispatch, changed input, or invalid bundle
  blocks publication. Repair the exact delegation or validation in this task;
  never silently fall back to the parent model or start another sweep.
- An accepted dispatch with unknown progress remains owned by that agent.
  Read/wait on it before creating another analyst; an interruption is not proof
  of failure. Context changes require a freshly bound packet and an explicit
  continuation to Astra before acceptance, not a retroactive attribution.
- When adopting an already-running Astra pilot, preserve its known original
  explicit dispatch parameters and record the actual same-agent `send_input`
  arguments/result via `--context-delivery`. Preserve the exact original
  message when available; if unavailable, record `original_parameters_only`
  transparently. The newly delivered full packet and independently accepted
  result are still mandatory. Future fresh spawns record complete arguments.
- Low-density remains a legitimate outcome after full evidence review. Higher
  model cost is confined to real semantic work; empty queues do not spawn.
