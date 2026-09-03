# EOD automation

Read this file only for the daily post-close capture/evaluation branch.

## Execute

Read same-day chronology first:

```bash
python3 scripts/show_journal.py --date today
bash scripts/auto_daily.sh eod
```

Keep the shell alive until it exits. `forward_eval` can be quiet for several minutes because API/cache fills are rate-limited; do not restart it or launch a duplicate writer.

After the paper EOD shell exits, run the independent real-capital Book-B
settlement exactly once:

```bash
PYTHONPATH=src .venv/bin/python scripts/book_b_live_intraday.py --date today --phase eod
```

The live EOD entry point rejects calls before 15:00 China time or on a date
other than the declared trade date. The oldest observed time across the three
broker row tables must also be at or after 15:00. This prevents a premature or
cached run from making an intraday NAV immutable.

This is read/reconcile/settle only: it creates no new SELL decision or order.
It reconciles existing durable live plans through the native execution port,
requires fresh account-bound positions/orders/trades row tables plus the funds
summary embedded in the same positions capture, projects
only broker-proved Book-B owned fills, and writes the immutable settled NAV only
when every live plan is terminal. Never add `--execute-sells` to the EOD call.
Transient structural, freshness-evidence, asset-equation, or cross-table
failure may trigger only the adapter's bounded whole-snapshot reread. Strict
invariants remain unchanged, the receipt records every read-only recovery
attempt, and exhaustion fails closed; never rerun the top-level EOD process or
replay a broker action to manufacture settlement.

A non-trading-day skip is a normal terminal state. Otherwise completion requires the dated run-flow to reach `eod done` and final artifacts to reconcile.

## What the orchestration owns

- Capture TICK features and reconstruct current daily bars from minute data for
  indices, open positions, current signals, and the previous live Book-B signal
  batch whose D+1 labels mature today.
- Run `data_doctor`; missing mature-batch reconstructed bars are CRITICAL and
  gate learning, not the capital half. Before today's EOD reconstruction starts,
  this coverage check intentionally stays quiet.
- Build forward A/B/C/D/E/F labels and intelligence shadow evidence.
- Monitor Book B and Book T, settle Book A, then settle Book T.
- Produce PnL decomposition and Book-B-versus-four-index report.
- Push the status digest, run Friday verdict recording when applicable, check flywheels, and update posture/exit calibration plus backlog sweep.

Do not repair, settle or infer any of these by hand.

## Verify decisive artifacts

- `output/live/run_flow_<date>_eod.json`
- `output/live/auto/<date>_eod.log`
- `output/live/eod_features.jsonl`
- `output/live/training_rows.parquet`
- `output/live/paper_account.json`
- `output/live/paper_account_A.json`
- `output/live/paper_account_T.json`
- `output/live/paper_holdings.json`
- `output/live/paper_holdings_T.json`
- `output/live/positions.jsonl`
- `output/live/paper_trades.jsonl`
- `output/live/pnl_decompose.csv`
- `output/live/decision_journal.jsonl`
- `output/research/paper_vs_market_<start>_<date>.md`
- `output/live/context_pack_<date>_eod.json`
- `output/live/book_b_live_execution/runs/intraday/<date>-eod.json`
- `output/live/book_b_live_execution/settlements/<date>.json`

Cross-check same-day sells from the journal/trades; the EOD monitor may be quiet after an earlier intraday/14:55 sell.

For Book T, use marked equity/unrealized only when `valuation_status=fresh`. Otherwise report cost-basis equity and `unrealized=N/A`; never combine a newer ledger with an older holdings mark. A post-14:55 `SELL_BLOCKED` remains open through settlement.

Book T ETF settlement must preserve the explicit instrument contract and use its
sell fee, lot size and T+0/T+1 rule. If the contract or authoritative market
facts are unknown, leave the position open and report the bounded block.

## Chinese audit order

1. Terminal status: shell exit, run-flow `deterministic_status`, supporting degradation and step count.
2. Data/learning: captured/reconstructed counts, `data_doctor`, labeled/executable rows.
3. A/B/C/D/E/F: take-all, ★, ★B, ★M, qibao benchmark, AI-intel shadow and ★E executable return; include B-vs-A contrast frequency and current mode-state changes. Small-n remains small-n.
4. Book A versus B: headline identical-entry paired B-A pp, eligible n and exclusions. Raw realized delta is accounting-only.
5. Book B versus index average: valid only at coverage `4/4`; otherwise index average/spread is `N/A`.
6. Paper Book B, real-capital Book B and Book T separately: cash/equity/realized/unrealized/open positions plus all same-day executed/blocked sells and next-session risk. Real Book-B uses its strategy-subaccount settled NAV and owned lots; broker mixed-account totals are evidence only.
7. PnL attribution: `pick_alpha / entry_slippage / exit_timing / fees` and both reconciliation lines.
8. Judgment layer: exit-rule hit rate only after its min-n floor; knowledge scoreboard in one line, plus top 1–3 cache-expressible research candidates only when `heavier`/KNOWLEDGE warns.

EOD is an audit, not a new bullish/bearish call. Stale posture, missing structured reviews, unchanged REJECTED verdicts and an open strategy flywheel are supporting/informational states, not capital failures. Strategy flywheel `blocked` (unconsumed PASS) is an anomaly requiring a proposal or weekly consumption path.

## Real anomalies

Escalate: nonzero script exit/traceback, missing run-flow or expected artifact,
incomplete step chain, data-doctor CRITICAL, HARD_STOP,
SELL_BLOCKED/unresolved event risk, PnL/account `MISMATCH`, Book-T
ledger/valuation drift, missing index coverage, or clearly unusual A/B/F
behavior. For real Book B also escalate incomplete three-table/positions-funds readback,
ownership/broker mismatch, any nonterminal or UNKNOWN plan at EOD, and settlement
immutability/hash failure.

Completion requires terminal evidence for both the paper EOD shell and live EOD
process, dated run-flow/log, paper ledger/account agreement, attribution check,
benchmark report, plus either a hash-bound real settlement or an explicit
reconcile blocker. Do not claim completion from intermediate commentary.
