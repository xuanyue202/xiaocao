# Intraday and closing automation

Read this file only for Book-B/Book-T monitoring, the 14:25 precheck or the 14:55 closing pass.

## Execute and scope

For opening and 14:25 precheck, start with:

```bash
python3 scripts/show_journal.py --date today
```

The existing sparse task now starts with the local
`scripts/kol_trading_tick.py poll` gate. Read
[kol-trading-judgment.md](kol-trading-judgment.md); `no_op` ends silently before
journal/MCP/broker reads. A claimed `run` retains the following independent
paper/live checkpoints and the exact token acknowledgement. No extra tick
grants the 14:55 soft-exit authority.

Default Book B:

```bash
.venv/bin/python scripts/live_monitor.py --execute-sells
```

Fallback: `PYTHONPATH=src python3 scripts/live_monitor.py --execute-sells`.

After the paper monitor terminates, run the matching independent live-lifecycle
checkpoint exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase <opening|sparse|precheck|closing> --execute-sells
```

The 14:55 closing pass is the deliberate ordering exception because its live
authority exists for only two minutes. After reading this reference, its first
executable business command must be the live `--phase closing` command above.
Do not put journal inspection, git checks, paper monitoring, status, data-doctor
or other diagnostics ahead of it. After that live process terminates, run the
paper monitor exactly once and complete both branches' reconciliation. This
priority changes orchestration only; it does not broaden the time gate, capital
authority or exact-once rules.

This second command reads no paper positions/account/trades. It first
reconciles existing live intents, then consumes the native Founder
positions/orders/trades row tables plus the funds summary embedded in the same
positions capture, and monitors only broker-proved Book-B
owned lots. `--execute-sells` means hand an authorized immutable SELL intent to
`TradingExecution`; it never bypasses the pre-existing two-key gate and never
mints or edits an authorization. Do not run it a second time after an UNKNOWN,
timeout, process interruption or visible form state; use its durable
intent/execution readback on the next scheduled checkpoint.

Book T is a separate explicit branch:

```bash
.venv/bin/python scripts/live_monitor.py --book T --execute-sells
```

Never mix Book T into the default Book-B report. Book A is settled separately and is never monitored.

## Phase authority

| Run | Authorized behavior |
|---|---|
| Opening dense 09:35/09:45/09:55 | Execute hard/event/liquidity exits; diagnose ordinary trailing/composite deterioration |
| Sparse 10:25/10:55/13:25/13:55 | Same authority; stay quiet without a sell, blocked sell, data issue or meaningful deterioration |
| 14:25 precheck | Run immediately; never wait for 14:55; leave soft exits deferred |
| 14:55 closing discipline | The single soft-exit pass; run once when woken and do not wait for another gate |

Intraday executes `HARD_STOP`, authorized structured `AI_EVENT_RISK_EXIT`,
fresh independently reviewed `KOL_DISCRETIONARY_EXIT` under Contract §2a, or
liquidity escape. Ordinary trailing/composite signals are `SELL_DEFERRED` until 14:55.

Use live phase `opening` for opening dense, `sparse` for the four sparse runs,
`precheck` at 14:25 and `closing` at 14:55. Only `closing` may hand off
`TRAILING_STOP` / `EOD_DISCIPLINE_1455`; the other live phases may hand off only
`HARD_STOP` / `AI_EVENT_RISK_EXIT` / verified `KOL_DISCRETIONARY_EXIT`.
The `closing` authority is code-bound to China time 14:55:00–14:56:59 on the
declared trade date. An early, late or wrong-date invocation fails closed; a
prompt label or scheduler wake alone does not grant soft-exit authority.

`AI_EVENT_RISK_EXIT` requires a valid structured `agent_review.veto_flags` event with sufficient severity, confidence and freshness. Keywords do not authorize it.

T+1 remains binding. Report an entry-day hard/event risk as unresolved rather than as an executed sale. If a triggered sale is limit-down with no bid, record/report `SELL_BLOCKED / LIMIT_DOWN_NO_BID`, keep the position open and leave cash/PnL/trades unchanged.

For Book T ETF positions, use the persisted instrument contract for lot size,
settlement cycle and sell fee. Unknown contract, non-whole-lot shares, entry-day
T+1, missing proprietary quote/status or insufficient liquidity is a blocked
paper action, not permission to apply stock defaults.

All writers share `output/live/paper_ledger.lock`. If `.ledger_txn/pending.json` exists, let the next writer recover it under the lock; never delete it manually. A concurrent second writer may become a no-op but must not duplicate a SELL.

Any real SELL intent must be derived from this monitor's authorized
`HARD_STOP`, `AI_EVENT_RISK_EXIT`, verified `KOL_DISCRETIONARY_EXIT`, or 14:55 `TRAILING_STOP` /
`EOD_DISCIPLINE_1455` decision, bound to a Book-B-owned sellable lot and free
of T+1/liquidity blocks. The live lifecycle records/reconciles such an intent
and hands it to the native execution port; it does not replace the simulated sell writer or infer a SELL from
an ordinary freeze row. Its broker ownership evidence is supporting evidence,
not the canonical `positions.jsonl`/`paper_trades.jsonl` account ledger.
For A-share lots, BUY remains board-lot constrained, while a broker-proved
sellable remainder below 100 shares may be handed off only as the exact full
odd-lot balance; it must not be discarded from the lifecycle.
The live command has a non-blocking checkpoint writer fence. If another live
checkpoint still owns it, report `LIVE_BOOK_B_CHECKPOINT_ALREADY_RUNNING` and
stop; do not queue a second native query/UI pass.

After any non-normal live result, follow
[`book-b-live-repair.md`](book-b-live-repair.md). The started task owns every
locally recoverable code, configuration, parsing, orchestration or read-only
evidence repair through a tight red test, root fix, scoped validation, safe
exact narrow resume, terminal reconciliation and 5 Why. Do not defer it to the
next Automation. A durable claim or possible broker effect remains
reconcile-only. An expired closing window is never authority for a late SELL;
repair and validate the future invocation path without replaying the missed
business action.

## Verify

Inspect:

- `output/live/paper_account.json`
- `output/live/paper_holdings.json`
- `output/live/book_b_live_execution/runs/intraday/archive/<run_id>.json` for
  every immutable live checkpoint receipt; `<date>-<phase>.json` is only the
  latest pointer and must not be used as the complete run history
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- `output/live/alerts.jsonl`
- `output/live/decision_journal.jsonl`
- `output/live/.ledger_txn/pending.json` if present
- `output/live/book_b_live_execution/book_b_live_decisions.jsonl`
- `output/live/book_b_live_execution/book_b_ownership_evidence.jsonl`
- `output/live/book_b_live_execution/runs/intraday/<date>-<phase>.json`

For any apparent mismatch, run `scripts/data_doctor.py` and use ledgers above snapshots.

## Report and completion

Reply in concise Chinese with paper and real-capital Book B explicitly separated.
For the real branch, lead with strategy-subaccount cash, exit-fee NAV, owned lots,
actual handoff/reconcile state and any T+1/liquidity/UNKNOWN block. Broker mixed
account totals are corroboration, not Book-B NAV. Opening-dense reports may add
evidence-backed posture confirmation/rejection. Sparse reports stay quiet when
both branches have no action, block, degradation or material deterioration.

`T+1_blocked` and `SELL_DEFERRED` are diagnostics, not failures. Escalate executed sells, HARD_STOP, event-risk exit/block, SELL_BLOCKED, missing/corrupt ledger files, pending-transaction failure or script failure.

Completion requires both monitor processes to terminate (or explicit normal
skips), paper positions/trades/account to agree, and the live run receipt to
bind a current three-table/positions-funds snapshot plus owned-lot projection. A printed trigger,
SELL intent, prepared form, acknowledged order or process exit is not an
executed live sell; only broker-proved fill evidence is.
