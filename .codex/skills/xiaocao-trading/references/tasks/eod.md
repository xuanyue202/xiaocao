# EOD owner: one ordered closeout

Role xiaocao-daily-eod. Verify initial scheduler ID/actual Thread, read today's
show_journal.py --date today, then promptly start once with short yield:
`CODEX_AUTOMATION_ID=xiaocao-daily-eod bash scripts/auto_daily.sh eod`.
Prewake15:03; Python gates15:10. Retain original shell; no model sleep or second
process while forward_eval/cache is quiet. Each date slot persists on failure.

## Business terminals first

Read [shared contract](../automation-context.md). After original paper terminal,
run book_b_live_intraday.py --date today --phase eod once with this exact identity,
WITHOUT --execute-sells. Post15:00 account-bound snapshot/owned chain and original
archive govern read/reconcile/settle; no new order, history rewrite or top-level
rerun. Preserve actual failed status and every branch's evidence.

Use Contract §4/§6 and BOOK_B_ACCOUNTING. Evidence-driven later independent full
lot disposal plus fresh same-account no-contradiction proof may close only a
historical economic confirmation task; original UNKNOWN/no replay/same-code
BUY fence remain. Reevaluate each fresh snapshot; zero holdings alone is not
terminal proof. eod_review surfaces execution/cash/itemized-fee gaps together.
Accounting-only gaps finish observed/accounting_pending, final PnL/settlement
still unknown. Exact broker_snapshot is archived, not recreated by a later read.
Why: current execution, marked risk and final accounting prove different things.

## Post-business children: wrappers only, once each

After BOTH original paper and APP terminals, same owner runs sequentially:
1. eod_post_business.py --step statement
2. eod_post_business.py --step research
3. eod_post_business.py --step feedback

Use CODEX_AUTOMATION_ID=xiaocao-daily-eod PYTHONPATH=src .venv/bin/python for each.
Retain terminal_path, exact stdout/diagnostic hashes/argv/owner/time. These wrappers
invoke book_b_accounting statement, funded EOD and kol feedback respectively;
NEVER additionally call the children directly. Persistent failure/interrupted
claim forbids replacement. Why: the wrapper records the one effect and its real
terminal; old direct-command paragraphs are superseded, not extra steps.
Research exit0 not_started (with saved report) or NON_TRADING_DAY is legitimate
no-action, not a sample/profit or reason to block otherwise valid closeout.

## Review, legacy branch, delivery

Read [EOD_WEEKLY_FEEDBACK.md](../../../../../docs/EOD_WEEKLY_FEEDBACK.md) and
[automation-eod.md](../automation-eod.md)'s daily analysis/evidence sections.
KOL is receipt/hash audit only: no report bodies/context/preparation status/model/
policy refresh. Missing links go to source/sparse owner, not an extended EOD loop.
Review raw first/latest failed turns, actual order/fill/holding/quote/timing/lot
coverage and next-window effects; repair owned deterministic defects after
business even when broker proof remains UNKNOWN. Keep stable IDs/root classes,
5Why edges/alternatives/falsifiers, disposition and next-window owner/entry/proof.
Existing JSON validator does not certify narrative causal depth or readiness.

Then eod_closeout.py --context --date <date>; follow prior Weekly responses and
write dated reviewed handoff under existing schema/roles/hashes. reviewed_at is
actual and later than all3 post-business terminals. Same owner calls
`eod_closeout.py --review <dated-review> --push-wecom` ONCE; it validates/freezes
original evidence and sends the APP-first digest. Missing evidence never permits
business replay. Prior format lacking post-business terminals is explicitly
legacy_read_only_handoff, not synthetic receipt or permission for a new digest.
Only a terminated pre-review-schema original EOD may use book_b_eod_review.py
--receipt <exact> under original owner to derive local review; no APP/settlement/
statement/research/feedback replay. book_b_eod_alert.py --receipt is notice-only.

Retry proved pre-send failures through existing shared claims/outboxes, including
paper_eod_status_notices.jsonl and sell_result_notices.jsonl; never run status
--push-wecom to recover an uncertain send. Retired_by_user claims stay retired,
not delivered or recurring todo. Current execution impact/change/user-only need
may notify; routine historical/accounting gaps remain local. Delivery is separate
from content/terminal proof. Preserve paper B/APP B/T and provisional/final PnL.
