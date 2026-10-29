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
human deferral requiring explicit resume. A premature launch remains in history.
Once the same original becomes eligible
for a post-session check, restore a usable collaboration entry through the bounded
continuation below; do not erase or blindly repeat the original claim.

## Open the entry before requesting human cooperation

A historical `entry_launched` receipt proves dispatch at that time, not a usable
window now. Never describe silent HTTP polling as if the human already has an
entry. First verify the original saved Browser target and current idle capture,
then dispatch Caoliao, then give the ordinary Open/Allow/play notice. Record
`entry_display_verified=false`; do not read WeChat to manufacture display proof.

When a new invocation resumes an eligible unbound wait, including a same-day
interruption or a premature pre-check entry, the runner emits fresh Browser
preparation and restores one entry. It uses a separate receipt keyed by the
original nonce and collaboration-session ID, preserving the original entry,
observation boundary, IDs and backoff. The session ID stays fixed throughout the
invocation, including across midnight. Reconcile every earlier same-original
continuation receipt before any new dispatch; an unresolved claim blocks all
later sessions. Each poll within the same invocation reuses its current entry.
Missing media alone never triggers
another entry within that collaboration session. A direct human report that
the entry is missing permits one separately receipted same-original recovery;
it does not authorize a new capture or retry of an uncertain dispatch.

Before restoration require the exact original launch's successful receipt and an
unbound idle capture; recheck it after Browser input. An uncertain prior dispatch,
accepted candidate/source, download, upload, Handoff, human deferral or current
known not-ready evidence stops restoration. The replay-readiness gate above
still applies before Browser work and launch. After launch keep the same process
polling; all WeChat operations remain human-owned.

1. Use the existing retained hourly gate or exact original item invocation. Discover courses through the existing WeChat database reader. Preserve subscription/capture IDs, baseline, jobs, task claims and handoff history.
2. The runner resumes the verified downloader singleton and checks its capture PAC before requesting `prepare_xiaoetong_human_entry`. That request authorizes **Browser editor work only**: verify the exact current original mini-program target, save it if necessary, reopen the component, then produce a fresh local proof with `identity`, `capture_job_id`, `saved_target`, `editor_url`, `component_reopened: true`, and timezone-aware `observed_at`. Update the bridge's existing last-configured identity/message hash only after real saved-target readback. Return the action, subscription ID and absolute `browser_proof_path` to the same PTY.
3. The runner makes one merchant-issued Caoliao launch and records its claim before the external effect. It emits `daily_human_action_required` once with `response_required: false`. Give one ordinary operation notice to open/allow/play this exact original course; do not use `request_user_input_async` or wait for a played reply. Keep polling, and continue automatically when the exact known source and finite media pass validation. Do not ask a playback or source-confirmation question. The agent verifies the title and original session using downloader and merchant evidence. Do not launch a custom dialog, AppleScript notification or impersonated notifier. An event receipt does not prove that the chat or OS displayed an alert. An uncertain launch is retained for reconciliation and never automatically reopened.
4. **The human owns every subsequent WeChat action**, including login, Open, Allow, consent/password, playback and closure. Do not bind/read/screenshot WeChat, query AX, issue native input, or run the atomic activation scripts. Do not accept a legal agreement on the human's behalf.
5. Keep the same PTY and source lock. The runner reads downloader HTTP candidates at 10, 20, 40, 80, 160, then 300-second intervals, capped at five minutes. Backoff survives restart. Do not re-open the entry or notify repeatedly during unchanged waiting within the same collaboration session. The shared listener's lifecycle lease prevents another capture from closing it during this wait.
6. A unique, fresh, finite merchant-linked candidate must pass the existing source/media lineage gates. Preserve original source identity where already known. For an opaque unbound share, the agent checks the candidate title against this capture's post-launch merchant base-info title and session time, the original publication date/session, and the exact merchant/live/media mapping. Persist machine source verification separately; never label it human-confirmed. No playback/source-confirmation questionnaire. Missing, conflicting, ambiguous, stale or live evidence stays unaccepted while the same HTTP poll continues; diagnose the concrete evidence gap without reopening the entry or guessing a candidate. Existing historical human-confirmed bindings remain valid.
   Title comparison may normalize Unicode width, whitespace and the decorative bell/variation selector; preserve both original titles in machine evidence. Changed wording, numbers, original date or session still fail closed. A morning merchant title of `大师班直播M月D日` is also supported when both observed titles match, its explicit date matches the merchant date, and merchant session time matches the original morning publication. This is a supported course name, not an equivalence to differently worded titles.
7. Once verified media arrives, continue the existing exact-job download, compression, upload and mailbox acceptance. Window closure stays `human` owned and is never fabricated as verified. The network owner spans the whole capture command; its guardian restores only the capture-owned proxy on exit. Keep unrelated active proxy settings intact.

When the human explicitly defers a temporarily unavailable course, stop only its retained runner, verify the guardian restored its owned proxy, and preserve the original item/capture/entry receipts. Under the source slot call `defer_human_playback(identity, user_defer_authorized=True)` after exact idle/unbound readback. It excludes that original from automatic selection and idle expiry without marking completion or cancelling a download. Continue the next exact original serially. Only a later direct human resume permits `resume_deferred_human_playback(identity, user_resume_authorized=True)`; it preserves the original nonce and claims and does not issue another entry. Do not treat provider unavailability alone as permission to defer an item.

No implicit production acceptance: test/code success and notification submission are not a real course capture, cloud receipt, or mailbox acceptance. Update the existing Automation prompt to this route before resuming its schedule; do not resume an old automatic-click prompt unchanged.
