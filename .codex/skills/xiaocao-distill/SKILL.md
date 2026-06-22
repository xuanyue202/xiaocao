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
PYTHONPATH=src python3 scripts/distill_transcript.py --feedback     # 1. what reality falsified
# 2. read the transcript + write reference/experience/distilled/<YYYY-MM-DD>_<morning|review>.json
PYTHONPATH=src python3 scripts/distill_transcript.py --validate <that file>   # 3. schema fail-closed
PYTHONPATH=src python3 scripts/distill_transcript.py --ingest        # 4. hypotheses -> candidate backlog
# 5. (judgment) refresh reference/experience/posture_current.json + append a REGIME_TIMELINE row;
#    add a playbook [校准] line ONLY if step 1 showed a prior that reality has now contradicted/confirmed.
PYTHONPATH=src python3 scripts/distill_transcript.py --validate reference/experience/posture_current.json
```

**Step 1 is what makes this a loop, not a one-way pipe.** `--feedback` prints the
standing posture, the calibration sensors' flagged priors (`<45%` hit — reality says
they were wrong), and the playbook's recent `[校准]` lines. Your distillation MUST
explicitly answer: does today's commentary **confirm, refine, or contradict** each
falsified prior? That is how live-market truth flows back into the next reading.

## The distilled JSON schema

Filename: `reference/experience/distilled/<YYYY-MM-DD>_<morning|review>.json` (the
morning|review category lives in the filename; the `kind` field is free-text Chinese,
e.g. `盘前直播` / `盘后复盘/大师班专场`).

**Required (12, fail-closed):** `date` (ISO), `kind`, `summary`, `posture`,
`regime_call`, `directions`, `stocks`, `method_principles`, `exit_lessons`,
`hypotheses`, `timing_notes`, `typo_corrections`.
**Expected (warn if absent — include unless the session was a short/临时加播):**
`decision_trace`, `judgment_heuristics`.

- `posture` — dict with `regime`, `dominant_style`, `risk`, `style_ranking`.
- `regime_call` — `horizon` + `what_would_falsify` (the falsifier is mandatory: a call
  with no falsifier is narrative, not a prior).
- `hypotheses[i]` — dict with `claim`, `implied_rule`, `falsifiable_test` (required) and
  `expected_effect` (optional). Optionally `category`.

## 早盘 vs 复盘:same schema, different emphasis (go DEEP on different fields)

Both kinds keep the full 12-key schema — the difference is what you extract richly. (The
filename's `morning|review` tells you which; the data backs this split.)

**早盘 (盘前直播) — the forward PLAN: what to do today, before the open.** Go deep on:
- `decision_trace` (the richest field in a morning — and the highest-value one): the
  real-time pre-open reasoning, 观察 → 推断 → 动作 and **why**. This is what makes a
  morning worth keeping; a morning that only records conclusions has thrown away its value.
- `regime_call.what_would_falsify` + `horizon`: today's forward COMMITMENT — the falsifier
  is mandatory (a call with no falsifier is narrative, not a prior).
- `posture` / `directions` / `timing_notes`: today's stance, who leads vs lags, the
  intraday-rhythm guess (e.g. "10点高点 → 11:15回调 → 午后反弹").
- The morning's `hypotheses` are forward BETS (if-X-then-Y). These are the PREDICTIONS the
  calibration loops later score — so state them falsifiably.

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
  method), vs the morning's forward bets.

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
- **`typo_corrections`** — the transcript is auto-transcribed; fix homophone errors
  (stock names, terms) and record the corrections so downstream readers trust the text.
- **Unconfirmed stocks** — if you cannot confirm a ticker/name from the text, flag it in
  `stocks` (or a `stocks_unconfirmed_note`); never fabricate a code.
- **`posture_current.json` is a SYNTHESIZED prior, not a copy of today's `posture`.** It
  carries `leaders` / `watch_flag` / `falsifiers` / `valid_until` that one day's distilled
  posture may not fully populate. ENRICH the existing file from the new distillation +
  prior context; do not clobber curated fields. The harness only validates its schema —
  it never auto-writes it (that would lose judgment).

## What the harness does (and does not)

- `--ingest` maps each new `hypotheses` entry into `reference/experience/xiaocao_hypotheses.jsonl`
  (the tracked candidate backlog) with a stable `XH-NNN` id and `authority=0` status,
  deduped by claim. **Review the git diff** before committing — that diff IS your gate that
  the extracted candidates are sane. It does NOT promote anything to a param.
- It never edits `exit_policy.py`, `params.py`, accounts, or the verdict ledger.

## Downstream (already wired — you are feeding these)

- `xiaocao_knowledge.py --posture` surfaces the refreshed posture to the morning agent;
  `--check` flags it stale at eod (your cue that a fresh transcript is overdue).
- The calibration loops (`posture_calibration.py`, `exit_calibration.py`) score these
  priors against realized forward outcomes and stage `<45%` ones back as flagged
  candidates — which appear in your next `--feedback`. The loop closes.
- A candidate you ingest is human-gate work: it must clear the discipline guards and §10
  before it can change anything deterministic.
