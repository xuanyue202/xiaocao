# Intraday and closing automation

Read this file only for Book-B/Book-T monitoring, the 14:25 precheck or the 14:55 closing pass.

## Execute and scope

Start with:

```bash
python3 scripts/show_journal.py --date today
```

Default Book B:

```bash
.venv/bin/python scripts/live_monitor.py --execute-sells
```

Fallback: `PYTHONPATH=src python3 scripts/live_monitor.py --execute-sells`.

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

Intraday executes only `HARD_STOP`, authorized structured `AI_EVENT_RISK_EXIT`, or liquidity escape. Ordinary trailing/composite signals are `SELL_DEFERRED` until 14:55.

`AI_EVENT_RISK_EXIT` requires a valid structured `agent_review.veto_flags` event with sufficient severity, confidence and freshness. Keywords do not authorize it.

T+1 remains binding. Report an entry-day hard/event risk as unresolved rather than as an executed sale. If a triggered sale is limit-down with no bid, record/report `SELL_BLOCKED / LIMIT_DOWN_NO_BID`, keep the position open and leave cash/PnL/trades unchanged.

All writers share `output/live/paper_ledger.lock`. If `.ledger_txn/pending.json` exists, let the next writer recover it under the lock; never delete it manually. A concurrent second writer may become a no-op but must not duplicate a SELL.

## Verify

Inspect:

- `output/live/paper_account.json`
- `output/live/paper_holdings.json`
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- `output/live/alerts.jsonl`
- `output/live/decision_journal.jsonl`
- `output/live/.ledger_txn/pending.json` if present

For any apparent mismatch, run `scripts/data_doctor.py` and use ledgers above snapshots.

## Report and completion

Reply in concise Chinese with cash, equity, open positions and only material actions/risks. Opening-dense reports may add evidence-backed posture confirmation/rejection. Sparse reports stay quiet by default.

`T+1_blocked` and `SELL_DEFERRED` are diagnostics, not failures. Escalate executed sells, HARD_STOP, event-risk exit/block, SELL_BLOCKED, missing/corrupt ledger files, pending-transaction failure or script failure.

Completion requires the monitor process to terminate (or an explicit non-trading-day skip) and current positions/trades/account to agree. A printed trigger without ledger confirmation is not an executed sell.
