# APP Book B profit first in WeCom EOD digest

Status: Implemented; next natural notification verification pending

User request (2026-10-26): 企微消息以后 Book B 的 APP 模拟也要报盈亏，并放最上面。

The existing daily status digest must lead with APP-simulation Book B, then
retain separately labeled paper B, A and T. Read the latest saved, verified
SQLite accounting observation only; do not query APP or rerun any EOD process.
Show its China observation time, strategy marked NAV, net contributed capital,
strategy cash and owned-lot count. Display cumulative confirmed profit only
when cash is reconciled and all actual itemized fees are complete. Otherwise
keep it unknown, show provisional realized/floating PnL separately (accepted
fees at actual amounts, missing fees at the original plan rate)
and explain cash/fee gaps. Missing, stale, future, invalid or superseded evidence
must never become current zero profit or fall back to mixed-account/paper values.

The digest is sent inside paper EOD before APP EOD; label the latest saved
observation truthfully instead of claiming a new EOD snapshot or settlement.
Keep the existing durable notification claim; no resend of today's delivered
digest. Match skill and active Automation instructions, scoped tests, independent
Standards/Spec reviews and commit/push. No trading or accounting authority changes.

Baseline: 30394b39508bb6453380b5647ec508a39d649a86.

Validation: 69 focused status/accounting tests passed. Independent Standards and
Spec reviews have zero unresolved findings. Review caught and implementation
fixed malformed saved JSON aborting the digest, and partial actual-fee coverage
being mislabeled as wholly plan-rate estimates. Temporary fixtures verify both;
the production journal, original EOD receipts and delivered notice were untouched.
Active Automation was updated and viewed through the app API; all scheduling,
model and ownership settings were preserved. The scoped change is reporting only.
Offline checks and a no-send current-data preview do not establish future natural
notification delivery. The next legal original EOD owns that readback.
