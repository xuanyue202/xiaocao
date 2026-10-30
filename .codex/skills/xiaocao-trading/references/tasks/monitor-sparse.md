# Sparse checkpoint and conditional KOL owner

Role xiaocao-intraday-monitor-05. First business command, once:
`CODEX_AUTOMATION_ID=xiaocao-intraday-monitor-05 PYTHONPATH=src .venv/bin/python scripts/kol_trading_tick.py poll --monitor-paper-on-app-fence`.
Retain actual Thread and initial identity. Do not read source/report context
before this gate. Why: an ineligible tick cannot acquire semantic/writer work.

## Gate branches

- no_op / OUTSIDE_SPARSE_CHECKPOINT / duplicate / holiday: finish quietly; no
  APP probes, projection, semantic work, research or ACK.
- reconcile_required / RUNNING_CLAIM: read returned owner's task once. Active
  owner ends duplicate; do not clear by age, repeat effects or wait on guessed owner.
- EXISTING_LIVE_PLAN_REQUIRES_OWNER: one bounded exact plan_ids/state_dir durable
  read. Use original poll's paper_checkpoint_path/checkpoint_coverage if present;
  that independently claimed Paper checkpoint must not run again. APP fenced,
  no KOL tick claim/ACK/semantic/research. Missing owner is explicit, not takeover.
- run: retain exact token/fingerprints; original paper monitor once then APP
  --phase sparse once. Consume script-recorded old BUY/SELL deferrals for the
  owned-SELL checkpoint; retain current account/claim/lot/market
  gates and reconcile both actual branch receipts.

## Conditional semantic branch

Read [shared contract](../automation-context.md) and
[kol-trading-judgment.md](../kol-trading-judgment.md) only on an owned run.
need_semantic_review=false means no KOL work. If true, build one cache-only
projection; every explicitly typed still-valid book_b_short_term current view
is covered. Uncertain/non-short/unclassified/incomplete are counts, not model
inputs. source_fingerprint change matters; audit projection hash change alone
is not a new meaning. No latest-N, keyword/holdings scope or classification_backfill.
Degraded source coverage stays explicit and with remote source writer; don't
re-author sources or reread unchanged bodies. Exact cited bodies support only
one bounded current-applicability gpt-6-sol/xhigh worker and independent parent
review/publication. Runtime scope covers accounts actually checked, not assumed
both. COLD exception only the existing validated v2 Xiaocao mode-follow; no new
capital/order/quote authority. Sparse slot never acquires closing timing.

## Complete original claim

After both business branches and authorized support are terminal, original owner
runs funded research --phase monitor --checkpoint-phase sparse once where
eligible; business no_action can still advance it, poll/no-op cannot. Preserve
phase and existing original ACK discipline. ACK completed|degraded only after
actual outcomes; never ACK a fenced/uncertain effect as completed. Keep old
UNKNOWN/same-code and active economic resource fences; no new runner or replay.
Report actual Paper coverage, APP/research/support separately. Read first/latest
raw failures for owned repair; native bad-cell evidence is diagnostic only.
