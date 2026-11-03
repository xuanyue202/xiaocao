# Preserve sparse checkpoints on early scheduler wake

Status: Reviewed; deployment and natural acceptance tracked in dated EOD audit
Baseline: 5cca907bb62f2a44f14db56f27df98368a148193

EOD observed the original 2026-11-02 10:55/13:55 tasks polling at
10:53:48/13:54:51 and returning OUTSIDE_SPARSE_CHECKPOINT. No corresponding
business receipts exist. The gate correctly rejects early work; the scheduled
CLI lacks the bounded startup wait already required by the scheduling contract.

Acceptance:
- A header-validated sparse scheduled CLI poll arriving up to five minutes early
  waits in the original process until the next same-day weekday sparse slot,
  before publication, decision, APP or paper effects. The existing poll function
  and its four allowed five-minute windows retain their behavior.
- Wrong/missing identity, explicit test clocks, weekends, or earlier/unrelated
  wall times do not acquire waiting authority. No replacement process, slot
  replay, widened slot, claim reset, new semantic or trading authority.
- Use the shared bounded business clock; a date rollover fails before a claim.
- Synchronize the sparse guide, scheduling reference and existing Automation
  prompt; preserve schedule/model/project. Validate the CLI behavior with fake
  clocks and isolated roots, independent Standards/Spec review, clean committed
  packaging and API update/view. Future natural acceptance remains pending.

No November 2 business replay. Closing's model-capacity failure is separately
external: this patch cannot recover a model turn that never reached a tool.
