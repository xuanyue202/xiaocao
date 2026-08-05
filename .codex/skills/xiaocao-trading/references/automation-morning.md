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

The 9:25 emitted set is the day’s stable recommendation reference. Later prices/fills may change; do not relabel the frozen signal set as unstable after close.

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
