# Xiaocao human-assisted playback

The current private bridge setting `playback_operator: human` selects this route. It supersedes the automatic native Open/Allow/play/close instructions for this capture only. Keep `activation_hold` intact for the legacy agent route. Liuguan and ASR remain paused under the current human direction.

## Replay readiness before entry

Discovery of an original course announcement does not authorize immediate playback.
Before editing the bridge, returning `browser_proof_path` or launching Caoliao,
check the original session's announced timing and available same-course evidence
from the authorized cached reader or existing merchant/downloader records. Known
unstarted/live/replay-generating states prohibit entry. A saved target proves
identity only; publication time, scheduled start time, elapsed time or an unrelated
historical replay cannot prove that a replay exists.

For a first opaque share without a pre-entry readiness query, use a conservative
post-session checking window: in Beijing time, an original morning publication
(before noon) is first eligible at 11:00 that date; an afternoon/evening original
is first eligible at 21:00. These are earliest checking times, not inferred end
times or proof of generation. An announced later session or known not-ready
state overrides this default: wait until available same-course evidence supports
a post-session check. An explicit same-course ended-and-replay-ready record can
permit an earlier check. Never use WeChat UI to probe readiness before this gate.
After entry, actual finite-media/source validation remains mandatory; a checking
window is never media acceptance or permission to reopen a claimed entry.

Before that checking window, retain the exact original as pending without an
entry or human Open/Allow/play request. Recheck at a later existing Automation
run; do not add a reminder or schedule. If already at browser input wait, stop
only that retained idle invocation and verify guardian proxy restoration, keeping
all IDs and claims. This pre-entry readiness wait is distinct from the persistent
same-process HTTP polling after a justified launch, and is not an indefinite
human deferral requiring explicit resume. A premature launch already claimed
must not be reissued when the replay later becomes ready; reconcile the same
original claim and continue without another entry.

1. Use the existing retained hourly gate or exact original item invocation. Discover courses through the existing WeChat database reader. Preserve subscription/capture IDs, baseline, jobs, task claims and handoff history.
2. The runner resumes the verified downloader singleton and checks its capture PAC before requesting `prepare_xiaoetong_human_entry`. That request authorizes **Browser editor work only**: verify the exact current original mini-program target, save it if necessary, reopen the component, then produce a fresh local proof with `identity`, `capture_job_id`, `saved_target`, `editor_url`, `component_reopened: true`, and timezone-aware `observed_at`. Update the bridge's existing last-configured identity/message hash only after real saved-target readback. Return the action, subscription ID and absolute `browser_proof_path` to the same PTY.
3. The runner makes one merchant-issued Caoliao launch and records its claim before the external effect. It emits `daily_human_action_required` once with `response_required: false`. Give one ordinary operation notice to open/allow/play this exact original course; do not use `request_user_input_async` or wait for a played reply. Keep polling, and continue automatically when the exact known source and finite media pass validation. Do not ask a playback or source-confirmation question. The agent verifies the title and original session using downloader and merchant evidence. Do not launch a custom dialog, AppleScript notification or impersonated notifier. An event receipt does not prove that the chat or OS displayed an alert. An uncertain launch is retained for reconciliation and never automatically reopened.
4. **The human owns every subsequent WeChat action**, including login, Open, Allow, consent/password, playback and closure. Do not bind/read/screenshot WeChat, query AX, issue native input, or run the atomic activation scripts. Do not accept a legal agreement on the human's behalf.
5. Keep the same PTY and source lock. The runner reads downloader HTTP candidates at 10, 20, 40, 80, 160, then 300-second intervals, capped at five minutes. Backoff survives restart. Do not re-open the entry or notify repeatedly during unchanged waiting. The shared listener's lifecycle lease prevents another capture from closing it during this wait.
6. A unique, fresh, finite merchant-linked candidate must pass the existing source/media lineage gates. Preserve original source identity where already known. For an opaque unbound share, the agent checks the candidate title against this capture's post-launch merchant base-info title and session time, the original publication date/session, and the exact merchant/live/media mapping. Persist machine source verification separately; never label it human-confirmed. No playback/source-confirmation questionnaire. Missing, conflicting, ambiguous, stale or live evidence stays unaccepted while the same HTTP poll continues; diagnose the concrete evidence gap without reopening the entry or guessing a candidate. Existing historical human-confirmed bindings remain valid.
   Title comparison may normalize Unicode width, whitespace and the decorative bell/variation selector; preserve both original titles in machine evidence. Changed wording, numbers, original date or session still fail closed.
7. Once verified media arrives, continue the existing exact-job download, compression, upload and mailbox acceptance. Window closure stays `human` owned and is never fabricated as verified. The network owner spans the whole capture command; its guardian restores only the capture-owned proxy on exit. Keep unrelated active proxy settings intact.

When the human explicitly defers a temporarily unavailable course, stop only its retained runner, verify the guardian restored its owned proxy, and preserve the original item/capture/entry receipts. Under the source slot call `defer_human_playback(identity, user_defer_authorized=True)` after exact idle/unbound readback. It excludes that original from automatic selection and idle expiry without marking completion or cancelling a download. Continue the next exact original serially. Only a later direct human resume permits `resume_deferred_human_playback(identity, user_resume_authorized=True)`; it preserves the original nonce and claims and does not issue another entry. Do not treat provider unavailability alone as permission to defer an item.

No implicit production acceptance: test/code success and notification submission are not a real course capture, cloud receipt, or mailbox acceptance. Update the existing Automation prompt to this route before resuming its schedule; do not resume an old automatic-click prompt unchanged.
