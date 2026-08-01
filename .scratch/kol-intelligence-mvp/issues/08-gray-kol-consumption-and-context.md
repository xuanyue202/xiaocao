# 08 — 灰常亮 KOL 情报检索与小草分析上下文

**What to build:** Extend the existing Xiaocao-to-灰常亮 KOL boundary with a
read-only consumption surface. Xiaocao must be able to discover relevant
published reports, current and historical viewpoints, evaluations, relations,
and evidence excerpts without already knowing every record ID, then assemble a
compact provenance-bound context package for a new analysis. 灰常亮 remains the
authoritative store for published family KOL intelligence; Xiaocao keeps raw
evidence and governed research knowledge in the existing
`reference/experience/` context, with any local 灰常亮 mirror treated as an
ignored, rebuildable cache.

**Depends on:** Accepted 灰常亮 report publication and longitudinal viewpoint
storage. Implementation will require coordinated changes in
`LiangHuiProject` after this Xiaocao-side contract is reviewed.

**Status:** proposed

## User outcome

- [ ] A new KOL analysis can retrieve the relevant historical context without
  loading every local transcript or requiring pre-known 灰常亮 record IDs.
- [ ] The same query on either Xiaocao machine resolves the same canonical
  published records and source hashes, subject only to an explicit `as_of`
  boundary.
- [ ] The Agent can start from a compact context package and deliberately
  drill down to a full report, viewpoint history, or exact evidence excerpt.
- [ ] Retrieval never turns a stale or expired viewpoint into a current one,
  never merges conflicting claims, and never treats similarity as authority.

## Required read capabilities

- [ ] List published reports with cursor pagination and filters for stable
  KOL, publication time, source, subject, named asset or theme, and content
  value.
- [ ] Read one stable KOL's explicit current, uncertain, expired, and
  invalidated viewpoints with their latest evaluations, relationships, source
  reports, and full history counts.
- [ ] Search report summaries, safe report bodies, viewpoint subjects,
  stances, reasoning, triggers, falsifiers, and family-readable evidence
  excerpts using structured filters plus deterministic full-text matching.
- [ ] Build a bounded KOL analysis context package from an explicit query,
  `as_of`, and context budget. The package contains selected current views,
  material historical changes, conflicts, source/report identities, content
  hashes, and reasons for inclusion; it is not persisted as a new truth.
- [ ] Fetch the complete current report or exact stored record by stable ID
  when analysis needs to drill down.
- [ ] Keep all read operations side-effect free: no report correction,
  reminder claim, Book action, viewpoint evaluation, or currentness extension.

## Retrieval and indexing decisions

- [ ] Phase 1 uses structured indexes and deterministic full-text search.
  Vector similarity is not required for acceptance.
- [ ] Establish a fixed retrieval benchmark covering exact asset lookup,
  paraphrased thesis recall, same-KOL evolution, cross-KOL conflict, expired
  viewpoint exclusion, and no-result behavior.
- [ ] Add hybrid vector retrieval only if the Phase 1 benchmark demonstrates a
  material fuzzy-recall gap. Any vector hit must return canonical record IDs,
  source times, currentness, excerpts, and hashes; the embedding is never the
  evidence or authority.
- [ ] Expose domain operations rather than arbitrary remote file paths or file
  CRUD. Raw transcripts remain private evidence and are opened through their
  evidence boundary only when a full semantic reread is required.
- [ ] A local SQLite/full-text/vector cache is optional for latency, ignored by
  Git, versioned by schema and source watermark, and fully rebuildable from
  灰常亮. Cache absence or corruption cannot change semantic results.

## Xiaocao knowledge placement

- [ ] Do not create another knowledge repository. Continue using
  `reference/experience/` as the Xiaocao knowledge context beside, but outside,
  `src/` behavioral code.
- [ ] Keep attributed distillations, candidate hypotheses, research protocols,
  research-consumption evidence, and verdicts co-versioned with Xiaocao so a
  consuming code revision can be reproduced.
- [ ] Do not commit a second authoritative copy of 灰常亮 report bodies or
  viewpoint history. Tests may use small redacted fixtures bound to the
  production contract.
- [ ] Do not commit credentials, family holdings, mutable runtime ledgers,
  caches, raw media, or private raw transcripts to a public repository. Raw
  evidence may be checked in only after an explicit privacy review establishes
  an appropriate private Git boundary; otherwise retain a private evidence
  reference and hash.

## Cross-project implementation seam

- [ ] Freeze the versioned request/response schemas and authorization behavior
  in a Xiaocao fixture before changing `LiangHuiProject`.
- [ ] Add the corresponding family-authenticated read capabilities to the
  existing 灰常亮 deep KOL module and MCP adapter; do not add a second analysis
  engine or a parallel KOL store.
- [ ] Add a Xiaocao read client that verifies family scope, pagination,
  canonical hashes, `as_of`, and context-package completeness before semantic
  use.
- [ ] Update `kol-intelligence` so a promoted new event retrieves a bounded
  historical context package before longitudinal comparison, while the full
  current evidence is still reopened locally and SHA-verified.
- [ ] Preserve report-first publication, idempotent reconciliation, reminder
  and Book independence, and all existing correction/currentness rules.

## Acceptance

- [ ] Contract tests cover pagination, filters, full-text search, context
  budgeting, exact drill-down, authentication/family isolation, empty results,
  conflicts, stale evaluations, and cache rebuild.
- [ ] A frozen multi-KOL corpus proves that all benchmark-relevant records are
  recalled, expired/invalidated views are not presented as current, and every
  context statement traces to a canonical record and content hash.
- [ ] A real read-only run on both machines returns the same selected record
  identities and hashes and produces zero MCP write receipts, reminders, or
  Book effects.
- [ ] A new real publication is analyzed with local immutable evidence plus a
  灰常亮 historical context package, published once, and reproduced on replay
  without duplicate side effects.
- [ ] Update Xiaocao and LiangHuiProject contracts, focused tests, and runtime
  skill documentation together before declaring the capability complete.

## Non-goals

- Copying all published 灰常亮 reports into Git as another source of truth.
- Storing raw transcripts or media in 灰常亮.
- Letting a search result, vector score, KOL consensus, or Obsidian note change
  deterministic strategy parameters without research and the human gate.
- Implementing the Obsidian family-wealth promotion workflow in this issue;
  that requires a separate decision about promotion triggers and ownership.
- Executing any real-capital trade.

## Comments

- 2026-08-01: The user confirmed 灰常亮 as the default historical KOL
  consumption source and requested that the cross-project capability first be
  recorded as a Xiaocao requirement. The knowledge-placement decision is one
  Xiaocao repository with a separate knowledge context, not another repository
  and not behavioral files under `src/`.
