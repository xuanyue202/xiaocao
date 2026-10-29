# Restore a usable human playback entry before asking for cooperation

Status: validated
Baseline: 78ca6f4082363984c858d8cd5036643e72479d82

The human reported that the Oct28 evening capture was called waiting for replay although no Caoliao entry was opened for them. They require opening the original course entry before requesting cooperation, including resumed work.

- On an eligible unbound idle original, first verify the saved Browser target, dispatch its Caoliao entry, then issue one ordinary operation notice. No notice may claim a usable current window from a historical launch alone.
- A new invocation resuming an eligible unbound wait, including same-day interruption or a premature pre-check entry after the replay checking window, restores one collaboration entry with a separate durable receipt. Deduplicate by original nonce and collaboration-session ID, stable across the invocation and midnight. Reconcile all earlier same-original continuation claims before creating another; an uncertain claim blocks later invocations. Do not reopen on every poll or while a source/network owner is busy. Direct human reports of a missing entry authorize a separately recorded exact-item recovery.
- Preserve original item/capture/nonce/entry receipt and original observation boundary; preserve poll count and next deadline. Uncertain dispatch outcomes are never retried. Bound media/download/upload/Handoff and human deferrals prohibit entry restoration. Recheck capture idleness after Browser waits.
- Original replay-readiness timing and known not-ready evidence remain mandatory. All WeChat UI remains human-owned. A successful OS dispatch is not proof of a visible window, playback, finite replay, or Handoff.
- Update both local skill references and the existing Automation prompt via the authority tool; preserve its current schedule, ownership, model and unrelated work.
- Validate behavior offline; independent Standards and Spec reviews cover only the scoped diff against the baseline. Commit/push only this change set.

## Validation and review

- 499 focused offline KOL tests passed (human playback, subscription state machine and daily runtime). No APP simulation or live UI tests were run.
- Standards review: one uncertain-continuation finding fixed; final review 0 findings. Spec review: uncertainty and same-day resume findings fixed; final review 0 findings. Independent reviewers also reviewed the runtime session propagation regression.
- Original review baseline 78ca6f4082363984c858d8cd5036643e72479d82; source scope is the eight changed KOL code/test/reference paths, excluding unrelated ASR WIP. origin/main c98840a31c09b2aab859bc95b0104fa17b842e96 fast-forward integrated without overlapping the scoped files.
- Existing Automation updated and reopened through the authority tool; actual mirror prompt equals the update request, schedule remains 07:00/11:00/21:00 Beijing, ACTIVE/model/project unchanged.
- Direct same-item recovery dispatched at 2026-10-29T14:36:44+08:00. This was the existing launcher, preceding the new runtime change; it is not a real-course test of the new automatic continuation. Original Oct28 evening capture subsequently reached cloud video_ready/handoff_ready, mailbox readback still NOT_FOUND at inspection. Do not equate upload, dispatch or test success with Handoff/remote acknowledgement.
