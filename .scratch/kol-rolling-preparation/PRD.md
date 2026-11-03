# Shared rolling Xiaocao judgment

Status: implemented and offline-validated
Baseline: e290b760a73cc8de1c13dea7606f54f7de874d7d

User request (2026-11-03): synthesize Xiaocao's previous evening and recent days
before market data arrives; APP and daily morning share it. Opening work checks
current applicability only. Replay nonempty ACTIVE history with identical inputs
and caches, measuring preparation and complete recommendation latency separately,
and reporting actual mode, sector, rank and position changes.

The remote KOL owner's existing early/evening slot prepares a reviewed authority-0
rolling brief from published typed viewpoints/evaluations/relations, retaining
chronology, conflicts, corrections, conditions, invalidations and source gaps.
It is derived trading reasoning, not a new source-semantic SSOT. Consumers retain
their owners, accounts, original freeze/deadlines and final publication/review.
Neither consumer waits for APP readiness or starts another full source analyst.

Acceptance:
- A previous-evening accepted brief can be adopted independently by both current
  APP and Paper owners; producer reads the same immutable brief.
- Source/evaluation/relation/rule changes and expiry cannot silently reuse old
  effects. Missing support explicitly preserves existing baseline/policy gates.
- Source synthesis and current applicability are distinct artifacts; no invented
  exact mode/sector identity, threshold, percentage or COLD override.
- Actual paired full producer runs use recorded raw local inputs, equal cache
  state, no network or financial effects; source/model preparation time is separate.
- Explain real differences or unchanged results; synthetic mechanics, historical
  engineering acceptance, formal publication/adoption and profitability stay separate.
- Independent Standards and Spec post-change review, fix and re-review findings;
  scoped regression, package/deployment and Automation API readback.

Validation: 12 complete alternating producer runs over two nonempty ACTIVE dates,
identical per-date frozen input/cache manifests, no network or financial effects.
Preparation wall time includes fresh model reading, parent audit and sealing;
recommendation wall time is measured from the real bash entry separately.
11/02's source-supported dated auction WAIT changes new target exposure 50% to0;
mode/sector/rank unchanged.10/30 remains baseline with missing previous-night
source and an explicit current-only delta branch.129 focused tests pass after
the legal APP engineering window opens. Independent Standards and Spec findings
were fixed and re-reviewed; actual scheduled adoption/profit remain unproved.
Local evidence: output/kol-opening-optimization/rolling-shared/.
