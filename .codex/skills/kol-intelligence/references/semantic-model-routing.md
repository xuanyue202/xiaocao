# Semantic model routing

Use this route only for new Xiaocao transcript semantic-input events, including
exact resumes. Other authors retain their existing route. Acquisition, provider
waits, mailbox operations, deterministic validation, publication, notification,
Book, knowledge ingestion, and ack remain on the Automation parent.

## Fixed role boundary

- The Automation parent is an operational executor. It may prepare immutable
  context, dispatch exact arguments, wait, reconcile, run validators, and perform
  authorized external effects. It must not invent the analyst's goal, summarize
  the source instead of passing it, or rewrite accepted semantic content.
- The configured semantic analyst owns full-source investment-thesis extraction,
  entity resolution, independent coverage audit, current-decision judgment,
  durable-knowledge judgment, and final 灰常亮 reader wording.
- Parent review is an acceptance audit only. It may identify omissions or
  distortions against the full source, but every content correction returns to
  the same analyst. The parent never authors replacement insight.

The one editable model-and-objective source is:

`config/semantic-analyst.json`

Inspect it with:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_semantic_delegation.py profile
```

The profile defines `model`, `reasoning_effort`, `fork_context`, one explicit
objective, deliverables, quality gates, and stop conditions. Do not duplicate or
override those values in an Automation prompt. `prepare` snapshots the profile
and its hashes into the item packet, so a later profile edit affects only new
requests. Already-issued packets retain their bound route; schema-v1 Astra
packets remain valid for exact read-only reconciliation and must not be migrated
or redispatched.

## Prepare and dispatch

1. Keep the same runner stdin open. Bind the immutable analysis request to its
   absolute path, source identity/version, complete evidence path/hash, and stable
   segment inventory. Preserve provider pause/close receipts. Read
   `full-contract.md` completely and honor any pinned request hash.
2. Run `scripts/kol_semantic_delegation.py prepare` with the analysis request and
   any separately captured market evidence and household context. Missing facts
   remain explicit limitations. The generated context packet includes full-file
   pointers and a hash-bound snapshot of the analyst profile.
3. Call `spawn_agent` with the generated `spawn_arguments.json` exactly as saved.
   Do not paraphrase its message, infer a default model, change effort, fork
   parent context, add unrelated tools, or ask the analyst to coordinate the
   workflow. Record the actual accepted arguments and returned agent ID with
   `record-dispatch`. A model label in prose is not dispatch evidence.
4. Give each analyst a disjoint item artifact directory. Its only writable
   outputs are the packet's `semantic_draft.json` and conditional
   `knowledge_draft.json`. Exclude mailbox, browser/provider, publication,
   notification, Book, ack, shared ledgers, Git, and Automation writes.

## Extraction target

The analyst's single outcome is a faithful, complete, evidence-traceable semantic
representation of one full transcript plus a coherent reader report. The saved
profile is authoritative; the following explains the required shape:

1. Read every evidence file completely to EOF and verify its hash. Prior chat,
   metadata, segment labels, holdings, keywords, and copied summaries never
   substitute for the source or restrict extraction.
2. First pass: build the complete investment-thesis and entity inventories.
   Preserve every must-surface thesis, including conflicts, alternatives, risk
   warnings, low-confidence names, conditions, horizons, numbers, exceptions,
   triggers, falsifiers, and uncertainty.
3. Second pass: reread every stable segment exactly once; classify it as
   investment, non-investment, or advertisement; link every investment segment
   to exact quoted theses; clear missing-thesis, incorrect-merge, and role-error
   findings. Complete all seven trade-information coverage rows and the named-
   asset inventory.
4. Produce the complete natural-Chinese 灰常亮 report and reader briefing. Each
   must-surface thesis appears exactly once in ranked KOL prose. Keep KOL claims,
   system fact validation, household advice, paper-only KOL-US judgment, and
   authority=0 knowledge separate. Preserve uncertainty instead of inventing
   names, codes, facts, weights, or actions.
5. Save `investment_thesis_inventory` and
   `investment_thesis_coverage_audit` with the exact request `evidence_sha256`
   and `contract_version=kol-investment-claims-v1`. Every claim includes
   source-grounded `reasoning`, `direction`, and `confidence` in addition to
   identity, quote, scope, horizon, and falsifiers. An uncertain security name
   remains traceable and explicitly uncertain; it is never erased into an
   anonymous rank.
6. Stop only when the profile's quality gates pass and the allowed outputs are
   complete. Otherwise return the exact unresolved gaps. Low density is legal
   only after full evidence review; unavailable facts never authorize fabricated
   validation or a parent-model fallback.

## Validate and publish

5. The parent runs the actual decision consumer's pure item validation and the
   publication candidate check before sealing a bundle. Neither check calls
   `process`, publishes, or initializes an account.
6. The parent independently checks the whole source against the analyst output
   for omitted or distorted assets/actions, conditions, numbers, timing,
   exceptions, invalidators, and dense late passages. Record this acceptance
   against source and draft hashes. Any material issue returns to the same
   analyst; the parent does not rewrite it.
7. Run `scripts/kol_semantic_bundle.py` on the unedited accepted draft and
   separate market evidence. Write `parent_source_review.json` using the
   `verify_semantic_review` schema with every reviewed segment and exact
   request/packet/draft/bundle/receipt/knowledge hash. Run `verify-result` with
   `--semantic-review`; only `parent_accepted` may continue.
8. Only the parent returns the validated `bundle_path` to the same runner. The
   deterministic pipeline publishes the exact accepted report and reconciles its
   stable URL/receipt before eligible reminder, paper-only Book KOL-US,
   knowledge, and mailbox-ack effects.

## Resume and failures

- Reuse the exact request, packet, profile snapshot, agent, and validated result
  after interruption. If stdin died, use only the runner-issued narrow
  continuation. Never start another sweep or analyst for the same item.
- Wrong or unavailable configured model, changed input, missing accepted
  dispatch, incomplete output, invalid bundle, or failed quality gate blocks
  publication. Repair the exact delegation or validation in this task; never
  fall back to the parent model.
- An accepted dispatch with unknown progress remains owned by that agent. Wait
  or read it before any continuation. New context goes to the same agent through
  an exact recorded delivery.
- `empty queues do not spawn`: they do not load this route or create an analyst.
