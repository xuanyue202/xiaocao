---
name: xiaocao-distill
description: Use when a new 小草 盘前/盘后 大师班 livestream transcript needs to be distilled into the xiaocao knowledge layer — turn the raw Chinese commentary into a structured distilled JSON, feed its candidate hypotheses into the backlog, and refresh the posture prior, so the transcript becomes governed nutrient for the calibration loops and the flywheel. NOT for live trading (that is the xiaocao-trading skill).
metadata:
  short-description: Distill a 小草 transcript into the knowledge layer + flywheel
---

# Xiaocao Distill — transcript → governed knowledge → flywheel

You are the entry point. Distilling Chinese livestream commentary into structured
judgment is YOUR job (it is not a script). The deterministic harness
`scripts/distill_transcript.py` does only the mechanical, judgment-free steps you call:
surface what reality falsified, schema-check, and feed candidates into the backlog. It
never reads the transcript and never touches the deterministic spine.

Everything you extract is a **judgment prior / candidate** with **authority = 0** over
the spine. A claim earns authority only by passing `research_exit_priors.py` /
`research_run.py` **and** the §10 human gate (see `docs/OPERATING_CONTRACT.md` §2).

## The loop (run in order)

```
# 0. save the RAW transcript to reference/experience/transcripts/<YYYY-MM>/ (the 原料, kept alongside
#    distilled so source and product are paired/auditable). Then:
PYTHONPATH=src python3 scripts/distill_transcript.py --feedback     # 1. what reality falsified
# 2. read the transcript + write reference/experience/distilled/<YYYY-MM-DD>_<morning|review>.json
PYTHONPATH=src python3 scripts/distill_transcript.py --validate <that file>   # 3. schema fail-closed
PYTHONPATH=src python3 scripts/distill_transcript.py --ingest <that file>     # 4. THIS file's hypotheses -> backlog
PYTHONPATH=src python3 scripts/distill_transcript.py --reality-check <that file>  # 4b. (复盘 only) stage 【loop】/现实校准 self-grades to a hard surface
# 5. (judgment) refresh reference/experience/posture_current.json + append a REGIME_TIMELINE row;
#    add a playbook [校准] line ONLY if step 1 showed a prior that reality has now contradicted/confirmed.
PYTHONPATH=src python3 scripts/distill_transcript.py --validate reference/experience/posture_current.json
PYTHONPATH=src python3 scripts/distill_transcript.py --refresh-action-log  # 6. rebuild the generated weekly-consumer index
```

**Recurrence is signal — let it merge, don't reword.** `--ingest` now MERGES a repeated claim
into the existing candidate (appends the date to `source_dates`) instead of dropping it;
recurrence = how many transcripts repeat a claim = its test-priority in the sweep. So when
`--feedback` shows a standing claim that today's transcript restates, write it the SAME way
(let it merge and bump recurrence) — do NOT reword it into a near-duplicate new id. Genuinely
new claims still get new ids.

**Step 1 is what makes this a loop, not a one-way pipe.** `--feedback` prints the
standing posture, the calibration sensors' flagged priors (`<45%` hit — reality says
they were wrong), and the playbook's recent `[校准]` lines. Your distillation MUST
explicitly answer: does today's commentary **confirm, refine, or contradict** each
falsified prior? That is how live-market truth flows back into the next reading.

## The distilled JSON schema

Filename: `reference/experience/distilled/<YYYY-MM-DD>_<morning|review>.json` (the
morning|review category lives in the filename; the `kind` field is free-text Chinese,
e.g. `盘前直播` / `盘后复盘/大师班专场`).

**Required (13, fail-closed):** `date` (ISO), `kind`, `summary`, `posture`,
`regime_call`, `directions`, `stocks`, `method_principles`, `exit_lessons`,
`hypotheses`, `timing_notes`, `typo_corrections`, `action_summary`.
**Expected (warn if absent — include unless the session was a short/临时加播):**
`decision_trace`, `judgment_heuristics`.
**Optional but REQUIRED when triggered by content:** `strategy_hit_audit` — for 复盘
sessions that mention short-line winners / 短线命中股 / 红盘起爆 / 专享方向 /
科创20cm worked examples.

- `posture` — dict with `regime`, `dominant_style`, `risk`, `style_ranking`.
- `regime_call` — `horizon` + `what_would_falsify` (the falsifier is mandatory: a call
  with no falsifier is narrative, not a prior).
- `hypotheses[i]` — dict with `claim`, `implied_rule`, `falsifiable_test` (required) and
  `expected_effect` (optional). Optionally `category`.
- `action_summary` — required routing sheet that forces the agent to think through every
  downstream consumer. Required keys: `posture_update`, `playbook_update`,
  `hypothesis_update`, `audit_evidence`, `instrumentation_todo`, and `routing` (list of
  strings). Use explicit empty states such as `no_change`, `not_applicable`,
  `no_issue_created`; do not omit a dimension just because nothing changed.

The generated `reference/experience/distill_action_log.jsonl` is rebuilt from per-file
`action_summary` via `--refresh-action-log`. The per-file distilled JSON is the SSOT; the
JSONL is a lightweight weekly-deep-review index, not a second truth.

## 早盘 vs 复盘:same schema, different emphasis (go DEEP on different fields)

**Both arrive DELAYED, not live** — by the time you distill either one, that day has already
played out. So neither is a real-time signal. Both keep the full 12-key schema, and the
shared value — morning as much as review — is the same as it has always been: **从他的动作 /
决策 / 判断反推底层逻辑** (the `decision_trace`), NOT the conclusion or the stock picks. The
difference is only which fields carry that logic most richly. (The filename's `morning|review`
tells you which.)

**早盘 (盘前直播) — reverse-engineer the pre-open REASONING.** It is NOT a forward bet (it
reaches you delayed); its job is to recover *how he thinks before the open*, as priors. Go deep on:
- `decision_trace` (richest in a morning, and the whole point): the 观察 → 推断 → 动作 chain and
  **why** — the reconstructable judgment process you can later replay and test.
- `regime_call.what_would_falsify` + `horizon`: NOT a bet we grade — part of his LOGIC, i.e. what
  he watches to know the call is wrong. Capture it as reasoning structure, not a prediction.
- `posture` / `directions` / `timing_notes`: how he frames the stance, leaders vs laggards, the
  intraday-rhythm read (e.g. "10点高点 → 11:15回调 → 午后反弹").
- Everything extracted is a PRIOR/heuristic (authority=0). **Do not conflate with the calibration
  loop:** that loop scores the LIVE system posture (`posture_current.json`, recorded in real time),
  NOT this delayed transcript directly. The transcript is a *source* of judgment logic that informs
  the live posture, never an auto-graded prediction.
- **But delayed ≠ stale — if it has not expired, ALSO extract the strategy, not just the logic.**
  The reasoning (`decision_trace`) is always worth recovering; the *call* (posture / regime /
  method) is worth recovering too, and is **actionable** when it is still in force — within its
  `horizon`, `posture_current` not past `valid_until`, `xiaocao_knowledge.py --check` not flagging
  stale, and the `what_would_falsify` not yet tripped by the tape. A still-current call updates
  `posture_current` (the prior the live system reads) and seeds candidate `hypotheses` to test;
  an expired one is kept as logic/heuristic only (the specific call is moot, how he reasoned isn't).
  Freshness is the gate — not the delay.

**复盘 (盘后/大师班) — the backward VERDICT + METHOD: what it taught, and did it play out.**
Go deep on:
- `exit_lessons` / `method_principles` / `judgment_heuristics`: 出场纪律复盘 + 系统教学/方法论
  (a review carries more teaching, and more `stocks` as worked examples — capture them).
- **Loop-critical — the review is where 小草 grades his OWN calls.** Extract "现实确认/证伪了
  哪条先验" here: did today's price action confirm or break the morning posture? which
  `[校准]`/flagged prior from `--feedback` did the market vindicate or punish? Put it in
  `judgment_heuristics`/`exit_lessons`. This is the human-judgment companion to the
  calibration sensors' mechanical scoring — it is the most direct nutrient for the loop.
- The review's `hypotheses` tend to be lessons GENERALIZED from experience (a distilled
  method), vs the morning's pre-open reasoning logic.

**复盘 mandatory side-check — short-line hit coverage audit.** If a review names short-line
winners or says a mode "hit" (e.g. `趋势抱团+红盘起爆`, `专享方向+红盘起爆`, `盘中`,
`科创/20cm`, `短线命中`), audit whether those stocks were inside OUR strategy hit range:
- Define the benchmark universe first, and keep the buckets separate:
  1. `teacher_named_winners` — stocks the transcript actually names as winners/hits.
  2. `local_strategy_benchmark_hits` — same-day local emitted/recommended/bought stocks in the
     same direction (for example a paper buy). These are real Xiaocao benchmark stocks, but NOT
     a teacher overlap unless the teacher named them.
  3. `direction_core_observations` — 中军/方向确认/盘中后置 examples that are not entry signals.
- For each stock, follow the evidence chain in this order: transcript name/code resolution ->
  local recommendation/trade evidence (`recommend_<date>.md`, `signal_snapshots.jsonl`,
  `positions.jsonl`, `paper_trades.jsonl`, `decision_journal.jsonl`) -> emitted strategy range
  (`PYTHONPATH=src python3 -m xiaocao --format json strategy run --date <date> --source api`
  plus the relevant `--modes`) -> Xiaocao index snapshot -> raw pools -> first-principles review.
  Prefer compact field projection over dumping huge JSON.
- For same-day audits, treat Xiaocao's post-09:25 signals as fixed facts. Once the morning
  recommendation/signal snapshot has been produced after the 09:25 call auction, it does not
  mutate later in the day; do not discount it as an unstable hindsight input. Still separate
  "teacher named it in review" from "our book should have bought it at 09:25".
- Use the CLI for index snapshots. The command is under the **`index`** command, not `data`:
  `PYTHONPATH=src python3 -m xiaocao --format json index stock --date <date> --source api --codes <codes>`.
  Do not instantiate `ApiDataSource` or hand-roll client calls unless the CLI is impossible.
  If an old-date `index stock` response lacks some fields, record only the confirmed fields and
  use raw-pool/strategy evidence for the rest; missing fields are not zeros.
- Check the emitted local range first: `recommend_<date>.md`, `signal_snapshots.jsonl`, and
  `PYTHONPATH=src python3 -m xiaocao --format json strategy run --date <date> --source api`
  (prefer cache/local when available; obey API rate limits).
- If the named winners are qibao/方向 examples, also check
  `strategy run --modes qibao` and the raw pool with
  `data sort --from-pool qibao --sort-key xiaocaoJSSB --sort desc` for that date.
- Also materialize the intermediate cohort layer for qibao/short-line reviews:
  `PYTHONPATH=src python3 scripts/cohort_snapshot.py --date <date>`. Use
  `output/cohorts/cohort_snapshots.jsonl` to distinguish `benchmark` buyable samples from
  `watchlist` high-open / limit-like strong-attack samples. Cohort membership has
  `authority=0`: it is evidence for review/research, not a live buy signal.
- Classify each named stock: `emitted_strategy_hit`, `emitted_qibao_hit`, `raw_pool_only`,
  `cohort_benchmark`, `cohort_watchlist`, `not_emitted`, or `no_evidence`.
- For misses, write WHY in `strategy_hit_audit`: rule threshold (`jssb` / `pct` /
  entity window; qibao scan floor is about `150/1.3`, main qibao `>=200`, direction qibao
  `>=150`), limit-up or high-open risk, mode mismatch, direction-only、中军 observation,
  or data/name uncertainty. Then judge whether the miss is reasonable under the current book
  (risk-control) or a real research blind spot. Be precise: a local related hit in the same
  sector is NOT a teacher-winner overlap unless the teacher actually named that stock.
- Do not treat high-open as a universal exclusion. In the raw-qibao top10 + electronic/20cm
  universe, high-open and limit-like/long-entity cohorts are research-positive but execution
  riskier; keep them as `cohort_watchlist` unless they pass the separate execution/buy-rule
  gate. Distinguish "not current paper-buy" from "not a valid benchmark". For claims about
  tradability, do not stop at daily open->next-close: run/follow the fill-aware cohort evidence
  path (`scripts/backfill_qibao_cohort_minutes.py --execute` for missing cohort code-days, then
  `scripts/research_qibao_cohort_execution.py`, then `scripts/research_run.py --trades
  output/research/qibao_cohort_execution_<cohort>.jsonl --n-tried <N>`). Use same-day qibao
  full-pool daily base for the benchmark; do not let a partially backfilled minute subset become
  the base. The fill script scales daily open into the minute bar price axis before applying the
  `open*1.005` limit, so the touch test is not tautologically anchored on the first cached minute.
  Current 2025-07-01..2026-06-28 fill-aware results: high-open watch PASS
  (+2.96pp, n=110) and limit-like watch PASS (+11.24pp, n=223), both authority=0.
  As of the 2026-06-30 §10 human gate, only the high-open 6%-10% sub-bucket and
  the limit-like bucket are promoted to Book-B/paper emitted modes
  (`高开标杆起爆`, `强攻标杆起爆`). They remain non-live-capital rules and generic
  high-open samples outside this qibao benchmark family are still high-open
  shadow, not automatic buys.
- First-principles review is mandatory for benchmark misses and local benchmark hits. Explain
  whether the stock matches the current book's target function (low-suck, red-board qibao,
  direction core, 20cm/STAR,盘中后置, etc.), why it was filtered or bought, and whether that is
  合理 under the current risk contract.
- If the miss looks systemic, add a falsifiable `hypotheses` item (for example raw qibao
  rank + industry/科创 filter vs current emitted qibao). **Do not change deterministic
  strategy params or live rules from this audit.** It is review nutrient only.

If a session is a short/临时加播 review, a thinner `decision_trace` is fine (it warns, not
fails) — but never skip the `exit_lessons` / prior-check that a review exists to capture.

## Distillation discipline (the honesty bar)

- **`decision_trace` is the highest-value field.** Capture the *reconstructable real-time
  reasoning* (观察 → 推断 → 动作 and WHY), not the conclusions/stock picks. The value of a
  transcript is the judgment logic you can later replay and test, not which ticker he named.
- **Every `hypotheses` entry is a CANDIDATE, never a verdict.** A narrative individual
  case (he said stock X worked) is NOT statistical evidence — it may be a concentration
  trick. Write a *falsifiable_test* that `research_exit_priors`/`research_run` could run on
  cache history. authority = 0 until it passes the guards + §10.
- **Budget and dedup hypotheses before ingest.** Before `--ingest`, compare new claims against
  the current tail of `reference/experience/xiaocao_hypotheses.jsonl` and against the same
  batch. Merge near-duplicates by using one exact `claim` string so the harness recurrence-merges
  them. Prefer fewer high-signal, testable candidates over splitting one lesson into many ids.
  After ingest, inspect the tail/diff; if a batch creates many new IDs, stop and curate before
  finalizing.
- **`typo_corrections`** — the transcript is auto-transcribed; fix homophone errors
  (stock names, terms) and record the corrections so downstream readers trust the text.
- **Unconfirmed stocks** — if you cannot confirm a ticker/name from the text, flag it in
  `stocks` (or a `stocks_unconfirmed_note`); never fabricate a code.
- **Short-line hit audit is part of review honesty.** Do not record "老师说中了 X" as if
  it proves our system covered it. Tie the named winners back to local emitted signals and
  raw pools, and explicitly explain any miss.
- **Subagents are helpers, not authority.** If context is large and you use subagents, give them
  the exact files, date, commands, and required output schema. The main agent must still verify
  subagent claims against local artifacts/CLI before writing distilled JSON or the skill. Never
  let a subagent summary be the only evidence for strategy-hit coverage.
- **Control context size.** For API/CLI outputs, project compact tables with only `code`, `name`,
  `pct/open/entity`, Xiaocao index fields, raw rank, emitted mode, and trade evidence. Avoid
  pasting full strategy/index JSON into the working context.
- **`posture_current.json` is a SYNTHESIZED prior, not a copy of today's `posture`.** It
  carries `leaders` / `watch_flag` / `falsifiers` / `valid_until` that one day's distilled
  posture may not fully populate. ENRICH the existing file from the new distillation +
  prior context; do not clobber curated fields. The harness only validates its schema —
  it never auto-writes it (that would lose judgment).
- **`action_summary` is mandatory even for short sessions.** Its job is not to create work;
  its job is to prove the five routing dimensions were considered. A real observation/audit
  gap goes under `instrumentation_todo`; if it is likely to recur, the weekly deep review
  turns it into an explicit `.scratch` proposal instead of letting it disappear in prose.

## What the harness does (and does not)

- `--ingest <file>` maps the new `hypotheses` from THAT one distilled file into
  `reference/experience/xiaocao_hypotheses.jsonl` (the tracked candidate backlog) with a stable
  `XH-NNN` id and `authority=0` status, deduped by claim. Pass the file you just wrote — NOT the
  whole history (`--ingest-all` exists for a deliberate one-time backfill and will flood the
  curated backlog; don't use it per-transcript). **Review the git diff** before committing — that
  diff IS your gate that the extracted candidates are sane. It does NOT promote anything to a param.
- `--reality-check <file>` (复盘) extracts the review's `【loop】`/`现实校准` self-grades to a
  runtime hard surface (`reality_checks.jsonl`) so they flow into the next `--feedback`, instead
  of dead-ending in prose. `--reconcile` folds research verdicts back: a REJECTED candidate is
  retired (stops reappearing as live work), a PASS is tagged as §10 evidence (NEVER auto-applied).
  `--retire <id> --reason <r>` is agent-judgment retirement (e.g. a 复盘 falsified the claim).
- `--refresh-action-log` rebuilds `reference/experience/distill_action_log.jsonl` from the
  per-file `action_summary` fields. It fails closed if any distilled file lacks the required
  routing fields.
- It never edits `exit_policy.py`, `params.py`, accounts, or the verdict ledger.
- The eod `flywheel_sweep.py` is the backlog CONSUMER: it reconciles the ledger and ranks the
  untested candidates by test-priority (recurrence↓ then age↑). `scripts/flywheel_selfcheck.py`
  now prints a knowledge scoreboard (candidate→tested / tested→PASS / retired / oldest-untested)
  so 'ingest outrunning grading' is visible, not silent. None of this touches the spine.

## Downstream (already wired — you are feeding these)

- `xiaocao_knowledge.py --posture` surfaces the refreshed posture to the morning agent;
  `--check` flags it stale at eod (your cue that a fresh transcript is overdue).
- `xiaocao_knowledge.py` also surfaces recent `distill_action_log.jsonl` rows so a new
  context can see what posture/playbook/hypothesis/audit/instrumentation routes were produced.
- The calibration loops (`posture_calibration.py`, `exit_calibration.py`) score these
  priors against realized forward outcomes and stage `<45%` ones back as flagged
  candidates — which appear in your next `--feedback`. The loop closes.
- The weekly deep review consumes `distill_action_log.jsonl`: fixed-input evidence can drive
  AUTO_APPLIED paper/simulation changes; anything outside the fixed input list becomes an
  explicit proposal requiring user confirmation. A candidate you ingest has authority 0 until
  it clears the discipline guards and the exploration-period evidence rules in §10.
