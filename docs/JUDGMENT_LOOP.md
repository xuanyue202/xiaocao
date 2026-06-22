# The Judgment-Calibration Loop (+ governance hardening)

> Set up 2026-06-23 after a long research session concluded: **mechanical-alpha
> hunting is largely exhausted (most candidates → null/artifact); the system's
> real edge is (1) broad participation and (2) the COARSE posture judgment**
> (赚钱效应/regime → play or sit out). The fine mechanical version of that
> judgment does NOT transfer OOS — so the judgment stays in the agent-cortex, and
> this loop makes it *measurably better over time* on *governed* data, instead of
> re-fishing for mechanical params.

Two halves, deliberately paired: governance is the clean foundation, calibration
is what compounds on it.

## Half 1 — Data governance (the foundation)

`src/xiaocao/research/data_guard.py` makes `docs/DATA_QUALITY.md` executable. The
rule: **request-reachable range ≠ data-valid range**. Guards:

- `data_valid_floor(records, key)` — coverage vs CONTENT; catches zero/null-padded
  history (concept returns were 0 pre-2024-05 → a fake +20~28pp alpha).
- `trailing(values, i, W)` — lookahead-SAFE window (excludes day i by default); use
  it for any feature acted on at day i (a window including i faked a +0.78 Sharpe).
- `looks_like_realized_pnl(series)` — flags execution-juiced PnL (mean≫median) so
  it's not compared to a raw price series (the mode_history trap).
- `staleness(...)` — freshest-date lag.
- `audit(...)` — composite; `ok=False` ⇒ fail-closed.

**Wiring:** `scripts/learning_preflight.py` runs `data_guard.audit` over the
mode_history learning substrate in `auto_daily.sh eod`; a critical finding sets
`DATA_OK=0`, so the capability flywheel won't learn from dirty data (complements
`data_doctor`). **Discipline for new research:** call `data_guard.audit()` on your
inputs before trusting them, and use `data_guard.trailing()` instead of
hand-rolled window slices.

## Half 2 — Judgment calibration (the compounding edge)

`scripts/posture_calibration.py` scores each dated posture call (道-layer:
regime/赚钱效应 → aggressive / defensive / neutral) against the **realized forward
market return** (cross-cycle big-cap date_kline). A call is a prediction; the
forward window is genuinely future:

- `aggressive` right if forward return > 0 (participation rewarded)
- `defensive`  right if forward return ≤ 0 (sit-out avoided loss)
- `neutral`    excluded (no directional claim)

**Daily loop (auto_daily.sh):**
1. **morning** — `--record-current` appends today's standing posture (from
   `posture_current.json`) to `output/live/posture_calls.jsonl`.
2. **eod** — `--score` scores any call whose forward window has closed, appends to
   `output/live/posture_calibration.jsonl`, and prints the hit-rate by action.
3. **weekly / on new transcripts** — a systematically-wrong posture type (hit-rate
   < 45% over ≥10 calls) is a **distillation target**: the next transcript pass
   should sharpen that posture's signal/threshold (it's a prior, not a param —
   it never auto-edits the spine).

**Baseline (already run):** `--backfill-proxy` scored the *deterministic*
trailing-breadth regime posture over 2021-2026 (1272 calls): **aggressive 61% hit,
defensive 42% hit (systematically wrong), overall 46%.** The defensive miscalibration
quantifies the session's finding — sitting out on trailing-bad-breadth misses the
bounce. The discretionary judgment layer must beat this baseline; the loop measures
whether it does, honestly, as calls accrue.

## Why this is the right loop (not more alpha hunting)

- It compounds the layer that the data proved holds the edge (coarse judgment +
  participation), instead of the layer that proved empty (mechanical timing/selection).
- It is honest by construction: a posture call is scored against a genuinely future
  outcome, on lookahead-safe, governance-audited data; nothing auto-tunes the spine.
- It fulfills a need `posture_current.json` already named: "日后须用真实行情回算他这
  几条 falsifier 的命中率(反'真实的谎言'标准)".

## Invariants (unchanged)
Judgment priors have zero authority over the deterministic spine; a posture's
calibration informs the next *distillation* (a prior), never an auto param edit.
Promotion to a strategy param still requires `research_run.py` (per-day guards) or
`trend_guards.py` + the §10 human gate. This loop is sensor/research only.
