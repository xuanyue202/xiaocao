# Morning automation

Read this file only for the daily morning recommendation/paper-book branch.

## Execute

Scheduled delivery is split across two Automations because the recommendation
is ready before opening-window execution can finish:

```bash
# 09:23 task: produce the dated recommendation and frozen review queue, then exit
bash scripts/auto_daily.sh morning-prerecommend

# 09:25 task: wait for those frozen artifacts, review, and paper-record
bash scripts/auto_daily.sh morning-execute
```

Future Book-B real-capital execution is a third, deliberately independent
09:20 Automation and process:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_morning.py --date today --route package-limit
```

It may start before the dated freeze exists and wait only for that freeze. It
must never run or await `morning-execute`, read a paper fill, or write
`positions.jsonl`, `paper_trades.jsonl`, `paper_account.json`, or
`paper_account_T.json`. Its state lives only under
`output/live/book_b_live_execution/`. Before waiting, it switches to live and
uses the read-only Founder asset reconcile to probe session/account/assets and
atomically produce `book_b_live_allocation_facts_<date>.json` only from a
complete, account-bound receipt. A non-empty dated freeze is valid for this
consumer only when the queue producer manifest already binds its actual
same-day snapshot rows, report, strategy run id, producer strategy Git SHA,
hash and count. Before any agent review can enrich the canonical snapshots,
the producer atomically writes those exact rows to
`output/live/book_b_live_freeze_<date>.jsonl`; an existing different artifact
must never be overwritten. The live consumer reads and recomputes only that
immutable dated copy rather than defining a new digest from later-reviewed
`signal_snapshots.jsonl`. Broker total assets and total securities market value
are evidence only, never the mixed-account Book-B basis: the first batch uses
the fixed 30,000 yuan Book-B capital basis on logical account `primary`; neither
value has a live CLI override. Any submitted, acknowledged, partial, filled,
unknown or reconciling execution evidence (including a fill followed by an
ownership-ledger write failure) blocks reuse of the first-batch basis until a
settled-NAV receipt exists. The complete allocation capsule binds its capital
basis source, NAV, cash, exposure and broker summary under one canonical hash,
and broker-summary cash must equal top-level available cash. The task verifies restoration to
mock on every exit.
At 09:20-09:30 the later `forward_eval` field `executable_fillable` may be
absent. Absence is not false and must be deferred to the current submit-time
market guard; an explicitly false value remains ineligible.
The live-plan consumer binds proprietary `HH:MM:SS:millisecond` clocks to the
dated China session and accepts only the documented continuous-auction `T`
status family (`T` or `T` plus digits). Numeric BUY limits are floored, never
rounded up, to the 0.01-yuan stock tick before broker readback.
Apply `docs/OPERATING_CONTRACT.md` section 9 for the capital-gate semantics.
Unless the Founder adapter proves the account-bound `package-limit` route,
reconcile capability, account binding and broker allocation facts, the task
reports the exact fail-closed reason and produces no real order. Persist the
sanitized preflight receipt with separate existing-session, fresh-login and
PassGuard fields; never infer one capability from another. A first-order
probe may leave receipt mapping pending; the single claimed submit
must itself prove the order-id/strategy-id mapping or become UNKNOWN and
reconcile-only. Any prepare/submit/reconcile chain uncertainty permanently
disables automatic replacement. Reconcile must bind the same proved order-id
and preserve its submit strategy-id evidence; an unmapped rejection is terminal
only with explicit no-click/no-save/no-start proof. A never-ambiguous first order
may receive at most one controlled replacement only after terminality and
fresh-market proof, with a submit-boundary cap of two attempts. Trading-hours order-id,
cancellation/one-retry and native
PassGuard gaps remain terminal pending evidence rather than inferred readiness.

The execution stage must never rerun `live_recommend.py`. Keep its shell alive
through the agent-review rendezvous and paper recording. Do not restart it while
it is waiting for the opening window. For an explicit manual one-shell recovery,
`bash scripts/auto_daily.sh morning` remains available.

Keep prerecommendation preflight bounded to this skill, the named automation
memory and current-day artifacts. If `CODEX_HOME` is unset, resolve it as
`$HOME/.codex`; do not scan old rollout recovery notes before starting the shell.

The orchestration must reach these stages:

1. The prerecommendation stage runs `live_recommend.py`, freezes the usable 9:25 signal/evidence set, and writes `output/live/recommend_<date>.md` plus ★/★B/★M/★E snapshots. K/P is an optional ranking overlay: a missing model/cache must fall back to neutral K/P ranks and must not skip deterministic snapshot capture or ★E selection. Snapshot-capture failure is fatal and must never be reported as a genuine `★E NONE`.
2. The same stage runs `build_intelligence_review_queue.py` to create the zero-fetch, zero-score review queue, then terminates so its final/inbox result is user-visible. Priority is open Book-B positions, then ★E, ★B and ★.
3. The execution stage uses `wait_for_morning_freeze.py` to require the matching dated report and queue. Missing, malformed or wrong-date evidence fails closed; it never regenerates the signal set.
4. `wait_for_agent_reviews.py` opens a bounded rendezvous. While the execution shell waits, read the dated queue and frozen evidence, then write structured reviews with `scripts/agent_intelligence_review.py`. Never substitute keyword scoring. If time expires, let base picks continue and report supporting-layer fallback.
5. `paper_record.py --pick mode_exec_star --intelligence-trade shadow` records only executable ★E Book-B fills plus the matching Book-A reference rows. K/P, auxiliary indicators, intelligence and manual notional cannot restore a failed mode gate.
6. `paper_record.py --trend-only` first checks whether Book T has an empty slot or a sellable switch candidate. A full aligned book returns immediately; otherwise it waits for the opening window and fills or performs a paired switch. No candidate or an unfilled replacement is normal.

The current formal Book T consumer remains the v1 control path until Issue 06's
research-consumption and human gates pass. `scripts/book_t_shadow.py
--runtime-check` is a read-only next-run preflight. If a dated,
hash-bound `output/live/book_t_v2_shadow_input_<date>.json` exists,
`auto_daily.sh morning-execute` may consume it after the v1 paper record; the
result is written only under `output/research/book_t_v2_shadow/<run-id>/` and
must never touch `positions.jsonl`, `paper_account_T.json`, or
`paper_trades.jsonl`. The consumer replays and accumulates prior isolated
frozen inputs so the 20/60/50 research floors cannot be reset by a daily
process restart.
A dated producer/input missing from a scheduled run is a supporting-layer
failure and must be reported as such. Only an intact, consumed real-day input
whose cumulative sample is still below the 20/60/50 floors is the normal
`pending_observation` state.
Run `scripts/book_t_v2_soak.py --gate daily-stability --required-days 5` for
the separate stage-3 five-real-trading-day acceptance. Stage 4 remains
`--gate engineering-burn-in --required-days 20`; the five-day verdict cannot
lower or substitute for that formal burn-in.
A consumed input must carry the v1 T receipt and raw SHA-256 hashes for the
positions, account, and trades artifacts; the CLI verifies those hashes before
research evaluation.
`paper_record.py --trend-only` emits the dated receipt after its formal T
result; receipt-write failure is supporting degradation and never rewrites the
successful v1 account result.
If the optional shadow input is malformed or its research write fails, the
automation records supporting-layer degradation and preserves the successful
v1 control result. A real Book T `paper_record.py --trend-only` error is
deterministic failure and must not be hidden by a blanket `|| true`.

Book T ETF candidates are admitted only with the explicit instrument contract and
validated proprietary realtime/minute/daily/liquidity facts described in the
Operating Contract. Missing metadata or current execution facts is a bounded
skip, never a stock-shaped 100-share fallback.

The 9:25 emitted set is the day’s stable recommendation reference. Later prices/fills may change; do not relabel the frozen signal set as unstable after close.

The checked-in `scripts/book_b_execute.py` is the lower-level phase-one
execution seam, not another paper writer. `auto_daily.sh` remains unchanged
and continues to call the canonical `paper_record.py` path. If the seam is
used for a dry run, BUY rows must carry an allocation proof produced by the
shared `strategy.mode_switch.plan_board_lot_orders` allocator, using rolling
settled NAV (the 30,000 yuan value is the fixed initial live Book-B basis in
this phase). Missing or
inconsistent proof, cash, batch, exposure, slot, or board-lot facts fail closed.
Its market guard records `LIMIT_DOWN_BUY_BLOCKED` or
`LIMIT_DOWN_CHECK_UNAVAILABLE`; neither is a fill.

## Two-stage reporting

The prerecommendation Automation must return a final/inbox Chinese result as soon
as `recommend_<date>.md` exists, before any agent review. Show one ★E table and
mark execution fields `待模拟成交`. Mention ★B vs ★ only as a retained
forced-contrast line. This is a completed information-delivery stage, not a claim
that paper execution is complete.

After the separate execution Automation ends, send its final ledger update. The table columns are:

`★E | code | name | mode | state | basket | basket_rule | sim_price | shares | notional | position_pct | K/P | open_pct | auc_pct | auc_residual_imb | basis | sentiment/news | paper_buy`

Rules:

- Use `-` for missing values. Never substitute ★B when ★E is empty.
- `state` includes ACTIVE/PROVISIONAL, selected window and pool/market LCB80.
- `position_pct` shows target and actual notional as a percentage of settled NAV.
- `paper_buy` compresses fee, fill basis/limit, window VWAP/high/low/last and retry/fallback/skip state.
- `basket` is an abandon bound, not the assumed fill. Lead the final summary with basket versus actual fill, shares, deployed capital, resulting exposure and cash.
- Treat `auc_residual_imb` as a sign: the post-match residual book is one-sided by construction.

Frame posture only from produced evidence: regime, breadth, limit-up/down counts and actual sentiment/news. The posture is narrative context, never a pick filter.

## Verify

Inspect the dated versions of:

- `output/live/auto/<date>_morning-prerecommend.log`
- `output/live/run_flow_<date>_morning-prerecommend.json`
- `output/live/auto/<date>_morning-execute.log`
- `output/live/run_flow_<date>_morning-execute.json`
- `output/live/recommend_<date>.md`
- `output/live/intelligence_review_queue_<date>.json`
- `output/live/signal_snapshots.jsonl`
- `output/live/positions.jsonl`
- `output/live/paper_account.json`
- `output/live/paper_account_T.json`
- `output/live/paper_trades.jsonl`
- `output/live/paper_skips.jsonl` when present

Candidate truth and booked truth are different. A recommendation is not a buy; prove the buy from positions/trades/accounts.

## Terminal states and anomalies

Prerecommendation completion requires its shell to terminate successfully and the
dated report, queue and required same-run signal capture to exist. A K/P degradation
may be supporting-only; a capture failure is deterministic failure. Execution completion separately requires its shell to
terminate and the final ledger state to be checked. Never conflate the two.

Normal bounded states: no raw candidates, no executable mode, no Book-T slot, review timeout with base-pick fallback, or a documented unfilled limit.

Escalate: script failure/traceback, missing recommendation or paper-record stage, torn/corrupt snapshots, missing mode evidence, AI hard veto, insufficient cash, suspicious fill metadata, ledger inconsistency, or a run-flow/log disagreement.
