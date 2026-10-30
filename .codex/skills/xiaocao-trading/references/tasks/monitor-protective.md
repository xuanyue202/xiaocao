# Protective monitor owner

Select the exact scheduler role; first action is already prescribed in its prompt.

| Role | Original process / order | Authority |
|---|---|---|
| xiaocao-intraday-monitor | live_monitor.py --execute-sells once; after terminal book_b_live_intraday.py --date today --phase opening --execute-sells once | Opening protection; paper then APP |
| xiaocao-intraday-risk-precheck-1425 | book_b_live_precheck_startup.sh once at14:18 prewake | Launcher gates14:25, paper then APP even on failure |
| xiaocao-intraday-monitor-1455 | book_b_live_closing_startup.sh once at14:38 prewake | Launcher gates14:45, APP then paper even on failure |

Retain exact identity/Thread and launcher until all branches terminate. No model
sleep, second launcher or manual duplicate child. On holidays the APP calendar
gate skips before credentials/history; do not query APP or recover notices there.
Closing's first shell call is its startup launcher, which loads its own required
references; don't put planning/source scans before it.

## Observe, protect, recover

Read [shared contract](../automation-context.md), Contract §4/§6 and matching
[automation-intraday.md](../automation-intraday.md) branch. Use only already-valid
KOL policy through normal consumers. No KOL context/report/preparation status,
source refresh, semantic dispatch/publication or analysis writes on dense,
precheck or closing tasks. Why: support work cannot consume protective exit time.

Current account-bound owned lots/sellable, T+1, market/liquidity, capital keys,
plan identity/claim and exact native readback govern SELL. Ordinary soft exits
wait for closing; hard/protective exits retain their actual scope. Closing uses
best-bid-aware limit and14:57 cap; record late starts honestly. Preserve original
phase when late. Existing/deferred BUY remains with its owner; never resize it.

Classified full-account read failures may use the implemented sellable_only port
with same account/date/owned-lot/current-sellable proofs. It has no cash/NAV/BUY/
EOD authority. Independent lots/new dated legal SELL are not automatically stopped
by a historical order; old UNKNOWN remains original claim/no replay. Inspect real
failure and diagnostic evidence, not an assumed missing port. Use owned repair
and exact original-plan continuation; no cancel/replacement/submit replay.
The original non-EOD runner classifies canonical prior-day BUYs for deferred
readback before APP reads, then checks current owned/sellable proof. This grants
only the owned-SELL checkpoint; same-day BUY uncertainty and missing/tampered
sources remain explicit gates. EOD and new-BUY capital admission stay separate.

Original APP keeps claimed SELL progress/terminal observation within original
120s budget capped14:57; ACK/PARTIAL/UNKNOWN are pending. Keep raw evidence and
unsold amount; no age-based terminal or assumed fill. Source/repair/soft timing
WHY is in Contract and BOOK_B_WORKFLOW, not a second strategy rule here.

## After both business branches

Opening owner runs research_book_b_forward.py --phase monitor --checkpoint-phase
opening once. Precheck/closing launchers already run their research branch:
do not add another call. A control no-op/duplicate/non-trading/rejected checkpoint
has no acquisition; an authorized business no_action/NO_OWNED_LOTS still may
advance the original research. Keep original phase; only closing models soft exits.

Check original branch receipts, lots/orders/fills and native_readback_evidence.
Retry proved pre-send pending WeCom notices through existing outboxes; retain
uncertain claims. Separate APP/Paper/research status and actual cash/NAV freshness.
A gate stop is not a completed full monitor. Finish after owned recovery or exact
unresolved readback/budget limit; no expired-window replay or extra KOL work.
