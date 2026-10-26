# Original Xiaocao capture PAC timing control

Status: In progress

Human authorization: continue the proposed one-variable comparison on 2026-10-26.

- Keep WeChat 4.1.13, the original morning subscription/capture/message, running downloader PID and binary, saved course target, and all existing tasks fixed.
- Add an explicit capture-only diagnostic option that verifies PAC remains OFF through Open and Allow while keeping the same healthy downloader running. Require the current human authorization hash. Reject malformed options, diagnostic mode and stale-reset preparation with this option.
- Default production behavior stays unchanged. Preserve all identity, freshness, hold, listener, per-entry claim, window, audit and downstream acceptance checks. Do not issue another entry or create another capture in the macro.
- If the course is reached, the operator verifies the actual page before enabling PAC and continuing the same original job. Brand navigation is not media acceptance. On protection, stop the single attempt, restore PAC/hold, retain tasks and report the exact outcome.
- Tests verify PAC mutations at the production checkpoint and default behavior. These tests cannot establish the cause of WeChat protection. Independent Standards and Spec reviews precede live use. Keep Automation, 六观 and ASR paused.

## Pre-live validation

- Baseline: `191b2c5578de05e710f2edc643b2dd67d5c8ac20`; scoped to the preparer, runtime, their tests and this spec.
- 31 controller/runtime JS tests and 6 Python preparer tests passed. The new checkpoint test first failed on actual PAC mutations before the implementation.
- Independent Standards review: no findings. Spec review found non-string authorization hashes could coerce to strings; fixed with an explicit string check and array/object/null negative cases. Final Spec review: no findings.
- Real UI/capture result remains pending; this is experimental support, not a production timing switch or a protection fix.
