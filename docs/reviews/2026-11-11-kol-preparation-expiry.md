# 2026-11-11 KOL shared preparation starvation

The November 11 producer completed its original capture and baseline. Its KOL
preview returned `baseline / PREPARATION_UNAVAILABLE`; it did not run a model
and time out. No historical producer or consumer is replayed by this repair.

## Evidence and cause

- Original producer run: `20261111T010738-394371d695ec`; capture09:25:45.312338,
  original terminal09:25:56, exit0. Preview elapsed0.00325s. The immutable
  checkpoint and baseline remain unchanged.
- Both registered rolling briefs expired, the latest at
  `2026-11-05T22:35:07.867593+08:00`. Its original viewpoints included40/73
  expired entries; its source fingerprint differed from the November11 local
  projection. These are independent invalidation reasons, not a timer to extend.
- `output/automation_audit/kol_hourly_20261110_21_01a1c5a7/run_result.json`:
  original run21:31:27–21:34:55, `preparation.entered=false`, elapsed/acceptance
  null, explicitly blocked by a historical notification uncertainty.
- `output/automation_audit/kol_hourly_20261111_07_01a1c7cc/run_result.json`:
  original start07:30:58, source/knowledge work complete08:22:20,
  `preparation.entered=false` for the same notification. There were about
  58 minutes before09:20; starting earlier alone would not remove the fence.
- The old reminder has one claimed send and no delivered receipt. Its report
  and21-entry published manifest had independently verified parity. Delivery
  uncertainty must remain unresolved, but it does not make the already published
  semantic records untrue or require a second notification.

Why preparation stayed stale: the Automation and role guide required every
external effect to be terminal before source-only preparation. A reminder fence
therefore became a global preparation fence, and the morning producer correctly
refused the resulting expired output. Repeated fallback was recorded without
repairing the dependency boundary. The current local projection is not proof
of a fresh remote source check or a completed applicability judgment.

## Repair

Contract§1d and the source-owner guides now separate reminder reconciliation
from verified published-source readiness. After the original capture/publication
runner exits, existing07:30/21:30 owners check preparation and record its own
not_started/reused/accepted/blocked result. hour_busy, active source work,
unproved publication, degraded projection and all other unfinished/uncertain
effects still block it. The exception is only for historical reminders. Notification
claim, no-resend, reconciliation and ACK requirements remain intact.

`kol_trading_prepare.py rolling-inputs --fresh-through <aware time>` checks
reuse against both brief expiry and original viewpoint validity at the intended
use. Insufficient coverage produces new source-bound inputs with the rebuild
reason; it does not accept a draft, renew an expiry, publish policy or change
prior bytes. Rebuilt inputs still need full source/context validation and
independent acceptance. The guide uses a proved target trading date09:27:30;
without that date it records only current validity. A future source change is
still checked by the actual consumer and may require immediate fallback.

Deployment scope: canonical contract, rolling/source role guides, existing
Automation prompt and its repository mirror, CLI and focused regression. The
cadence, project, owner model, notification preference and trading authority
remain unchanged. No APP action, notification resend or second source sweep.

## Validation and remaining proof

Baseline: `a85753010fb55aa84ca887d0385a7768dee1a676`. Scoped validation:
`tests/test_kol_rolling_preparation.py`, `tests/test_kol_opening_preparation.py`,
`tests/test_kol_selection_preview.py`:50 passed,1 APP-simulation test skipped
under the weekday trading-hours gate. New CLI tests first failed for the missing
horizon option, then passed for valid reuse, original viewpoint expiry and
brief expiry, preserving the original preparation bytes and no-policy boundary.

Independent Standards/Spec review, packaging and active Automation readback
are recorded in the repair audit. They prove deployment/configuration, not a new
accepted preparation. The next existing early/evening source owner must provide
its actual input/start/end/review/acceptance receipt. This task does not guarantee
that future sources become available or future conditions become executable;
those exact gaps remain explicit and do not consume an opening model wait.
