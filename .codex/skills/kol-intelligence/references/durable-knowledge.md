# Durable multi-author knowledge

## Contents

- Authority and branch gate
- Distillation loop
- Provenance and filenames
- Distilled JSON contract
- Author-specific posture rules
- Session emphasis
- Xiaocao short-line audit
- Honesty and downstream boundaries

## Authority and branch gate

Turn reusable reasoning from 小草, 吕晓彤, 路西法, or another attributable KOL into governed Xiaocao knowledge. The agent reads and judges the source; `scripts/distill_transcript.py` only surfaces feedback, validates schemas, ingests candidate hypotheses, records review reality checks, and rebuilds the action index.

Everything extracted has `authority=0`. It must not enter the deterministic spine or tune parameters automatically. A hypothesis earns authority only after `scripts/research_run.py` or the relevant research harness and the §10 human gate in `docs/OPERATING_CONTRACT.md`.

Evaluate this branch independently from current decisions:

- Return `knowledge_status=reusable_knowledge` and write a distillation when the source contains a reusable causal model, decision trace, method, exit lesson, or falsifiable hypothesis (in a dry-run, report the proposed path without writing it).
- Return `knowledge_status=no_reusable_knowledge` with a reason when the source contains only ephemeral facts, promotion, repetition, or unsupported conclusions. Do not write an empty JSON merely to prove the branch ran.
- Keep exact time-sensitive recommendations in the decision audit. Generalize them into durable knowledge only when the reasoning can be replayed or falsified.

Always reopen the latest normalized evidence path immediately before extraction and compute its current SHA-256. The archived raw transcript is immutable audit evidence, not a read-only context snapshot that replaces the current file.

## Distillation loop

Run applicable steps in order:

```bash
# 0. Preserve the latest normalized transcript under reference/experience/transcripts/<YYYY-MM>/.
PYTHONPATH=src python3 scripts/distill_transcript.py --feedback
# 1. Read the current evidence and write one attributed distilled JSON.
PYTHONPATH=src python3 scripts/distill_transcript.py --validate <distilled-file>
PYTHONPATH=src python3 scripts/distill_transcript.py --ingest <distilled-file>
# 2. For a review containing explicit self-grades / reality calibration:
PYTHONPATH=src python3 scripts/distill_transcript.py --reality-check <distilled-file>
# 3. Only when the author-specific posture gate below permits it, synthesize posture_current
#    and append REGIME_TIMELINE, then validate the posture file.
PYTHONPATH=src python3 scripts/distill_transcript.py --validate reference/experience/posture_current.json
PYTHONPATH=src python3 scripts/distill_transcript.py --refresh-action-log
```

Before `--ingest`, compare claims with the current tail of `reference/experience/xiaocao_hypotheses.jsonl` and with the same batch. Reuse the exact claim string for a genuine recurrence so the harness merges source dates/authors. Curate near-duplicates instead of creating many slightly reworded IDs. Inspect the diff after ingest.

`--feedback` closes the loop: explicitly state whether the new material confirms, refines, contradicts, or does not address each relevant flagged prior. Do not force commentary on unrelated priors. Add a playbook `[校准]` line only when this comparison supplies real confirmation or contradiction, never merely because a transcript was processed.

## Provenance and filenames

Every new multi-author distillation must include all three provenance fields together:

- `author`: exact corrected display name;
- `source`: source/provider identity;
- `evidence`: non-empty list of `{path, sha256}` bound to the material actually read.

Use `reference/experience/distilled/<YYYY-MM-DD>_<author_slug>_<morning|review>.json` for attributed multi-author files. Retain legacy `<YYYY-MM-DD>_<morning|review>.json` names for existing Xiaocao artifacts; do not rename history. Record transcript typos under `typo_corrections`, and always normalize the household project display name to `亮灰`. Never guess an unconfirmed person, company, or ticker.

## Distilled JSON contract

Required, fail-closed keys:

- `date`, `kind`, `summary`;
- `posture`, `regime_call`, `directions`, `stocks`;
- `method_principles`, `exit_lessons`, `hypotheses`, `timing_notes`;
- `typo_corrections`, `action_summary`.

Include `decision_trace` and `judgment_heuristics` unless the item is genuinely short. Add `strategy_hit_audit` when a Xiaocao review claims short-line winners or mode hits.

Shape constraints:

- `posture`: `regime`, `dominant_style`, `risk`, `style_ranking`.
- `regime_call`: include a horizon and `what_would_falsify`; a call without a falsifier is narrative, not a prior.
- Each hypothesis: `claim`, `implied_rule`, `falsifiable_test`; optionally `expected_effect` and `category`.
- `action_summary`: always include `posture_update`, `playbook_update`, `hypothesis_update`, `audit_evidence`, `instrumentation_todo`, and string-list `routing`. Use explicit `no_change`, `not_applicable`, or `no_issue_created` values rather than omitting dimensions.

The per-file JSON is the SSOT. `reference/experience/distill_action_log.jsonl` is a generated consumer index rebuilt from `action_summary`, not a second truth.

## Author-specific posture rules

- **Xiaocao:** a still-current, non-falsified call may enrich the synthesized `posture_current.json`. Preserve its existing leaders, watch flags, falsifiers, and validity fields; never replace it with a copy of one transcript's `posture`. Expired calls remain logic/heuristics only.
- **Other authors:** write attributed knowledge and hypotheses, but do not rewrite the Xiaocao global A-share `posture_current.json` or `REGIME_TIMELINE.md`. Set `action_summary.posture_update` to an explicit non-applied reason. A multi-source global synthesis requires a separate explicit task and human review.
- **All authors:** their statements never auto-tune a strategy, account, live rule, exit policy, or parameter.

## Session emphasis

For pre-market material, reconstruct the observation → inference → action chain, including why, horizon, timing, and falsifiers. Because transcripts can arrive late, separate the reusable reasoning from any still-current call. Only the current-decision branch may turn a validated, unexpired call into present advice.

For reviews, emphasize exit lessons, method principles, judgment heuristics, and what reality confirmed or falsified. Treat named stocks as worked examples, not proof. A narrative winner can seed a falsifiable candidate but is not statistical evidence.

## Xiaocao short-line audit

Run this only when a Xiaocao review names short-line winners or says a mode hit (`趋势抱团+红盘起爆`, `专享方向+红盘起爆`, `盘中`, `科创/20cm`, `短线命中`). Keep these buckets separate:

1. `teacher_named_winners`: stocks Xiaocao actually named as winners;
2. `local_strategy_benchmark_hits`: same-day emitted, recommended, or bought local stocks in the direction;
3. `direction_core_observations`: direction confirmation or core examples that were not entry signals.

Follow this evidence order: transcript name/code resolution → `recommend_<date>.md`, `signal_snapshots.jsonl`, `positions.jsonl`, `paper_trades.jsonl`, `decision_journal.jsonl` → emitted strategy range → Xiaocao index snapshot → raw pools → first-principles review. A related sector hit is not overlap unless the teacher named that exact stock.

Prefer the CLI and cache-first data paths:

```bash
PYTHONPATH=src python3 -m xiaocao --format json strategy run --date <date> --source api
PYTHONPATH=src python3 -m xiaocao --format json index stock --date <date> --source api --codes <codes>
PYTHONPATH=src python3 -m xiaocao --format json strategy run --date <date> --source api --modes qibao
PYTHONPATH=src python3 scripts/cohort_snapshot.py --date <date>
```

Obey API rate limits and project compact fields. Missing old-date index fields are unknown, not zero. Treat post-09:25 same-day recommendation/signal snapshots as fixed facts, while still separating hindsight examples from what the book should have bought at 09:25.

Classify each named stock as `emitted_strategy_hit`, `emitted_qibao_hit`, `raw_pool_only`, `cohort_benchmark`, `cohort_watchlist`, `not_emitted`, or `no_evidence`. Explain misses using thresholds, limit/high-open risk, mode mismatch, direction-only status, or name/data uncertainty. Judge whether each miss/hit matches the current book's target function and risk contract.

Do not treat high-open as a universal exclusion. Research-positive qibao high-open/limit-like cohorts remain execution-gated; only already human-promoted paper modes may emit. For tradability claims, use the fill-aware cohort path (`scripts/backfill_qibao_cohort_minutes.py --execute`, `scripts/research_qibao_cohort_execution.py`, then `scripts/research_run.py`). Do not let a partial minute subset replace the same-day full-pool benchmark.

If a miss appears systemic, add a falsifiable candidate hypothesis. Never change deterministic strategy parameters or live rules from this audit.

## Honesty and downstream boundaries

- Make `decision_trace` reconstructable: observation → inference → action and why. Do not reduce it to conclusions or ticker picks.
- Preserve KOL wording as attributed evidence and label synthesis. Never manufacture a causal link, code, quote, or certainty.
- Treat every hypothesis as a candidate. State the historical test and expected effect; do not call one anecdote validated.
- Keep source material, system judgment, Book KOL-US simulation, household advice, and durable knowledge separate.
- Keep context compact when querying data. Subagents may help inspect large artifacts, but the main agent verifies claims before writing knowledge.
- `--ingest <file>` ingests only that file. Do not use `--ingest-all` for a normal item.
- `--reality-check` stages review self-grades; `--refresh-action-log` fails closed on malformed distillations. Neither command edits the deterministic spine.
- `flywheel_sweep.py`, calibration, and weekly deep review consume the backlog/action log. PASS research still requires the human gate; no downstream consumer may auto-apply an unattributed KOL claim.
