# KOL premarket preparation execution

Baseline: `808ef3e11fee1384af2c7cb17a1a0ed28a2d304b`. Scope: existing KOL
source owner, source preparation and its consumer readback; no trading replay.
The user requested real preparation and independent review before the auction,
adequate time and an earlier launch where needed.

## Behavior

The existing morning source automation moves from 07:30 to 06:30. Its original
gate owner, Thread, PID and stdin run cache-only preparation immediately; source
acquisition/mailbox effects still wait until 07:30. Other scheduled slots remain
unchanged. Delayed morning starts keep their actual identity and remaining time.

| Phase | Original bound and evidence |
| --- | --- |
| Ready input to actual configured worker | Five minutes; immutable dispatch |
| Synthesis | Up to thirty minutes; exact input and cited context |
| Independent parent review | Fifteen minutes reserved; actual review-open and acceptance |
| Changed input stage | At most forty-five minutes, shortened by 09:20 |
| Whole morning program | Original acquisition through 09:20 |
| Evening program | Original sixty minutes |
| Consumer current-fact adaptation | Existing 120 seconds / earlier 09:27:30 bound |

Publication-ledger changes and 08:30/09:00/09:10 cache checkpoints can prepare
genuinely changed inputs. Unchanged input never renews a stage. One active or
unknown worker remains owned; only exact completion or actual agent terminal
receipt releases it for changed input. Preparation remains owned after an empty
source queue or recoverable source exception. Unproved calendar/source support
stays explicit and never proves morning readiness. Consumers read accepted
preparation locally, without a source worker, task wait or future policy approval.

## Independent review and validation

Standards and Spec reviews of the explicit baseline found bootstrap failures
could stop source acquisition, exceptional source exits could bypass preparation
closeout, and weak worker-terminal/completion checks could release ownership.
These were fixed with scoped failure isolation, idempotent original-deadline
closeout and complete sealed stage/input/worker/tool-receipt validation. Reviewers
rechecked the affected code. Final closure review also covers late morning
identity, stage timing, instructions, automation and package manifest wiring.

Focused behavioral checks cover source-floor isolation, clock/deadline admission,
calendar proof, changed inputs, failed/unknown workers, exact review acceptance,
legacy behavior and deployment closure. APP simulation tests are excluded during
the prohibited afternoon test interval; this change does not alter APP execution.
Exact final checks, review dispositions, package and Automation API receipts are
saved under `output/audit/kol-preopen-execution-20261113/` at deployment.

Engineering checks and an active schedule do not prove a future model completed
on time. The next natural run must retain actual dispatch/review/acceptance
timestamps and source-gap outcomes. No historical preparation is backdated and
today's sealed trading run is not repeated.
