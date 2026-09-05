# Hourly Local Native Capture Stages

Read this reference completely at the native launch, identity-resolution,
activation, or continuation/acceptance stage routed by
[hourly-local-capture.md](hourly-local-capture.md), including resumed jobs.
Keep the existing capture/job and process; the local entry owns discovery,
process lifetime, and mailbox completion.

## Readiness and launch

Before every native activation prompt, the driver restores and checks the
existing capture's singleton sniffer; a historical armed receipt is not current
process health. Verify/apply the bounded capture PAC only after that health check.
Local capture commands preserve inherited PATH precedence and append installed
Homebrew CLI directories for ffmpeg/ffprobe and transfer helpers.

For `#小程序://鹅直播/<token>`, retain contact/time/token, arm the candidate
baseline, then open the original message once. Skip H5 resolution. Bind the
observed candidate ID, app ID, live ID and post-arm time before downloading.
For H5 entries, retain the process for credential-free identity resolution;
H5 is not playback proof.

For an HTTPS share entry, the default launch route is now the verified merchant
Web Link, not chat-window screenshots. Run the emitted `launch_resolver_command`
with `PYTHONPATH=src`. The read-only `scripts/kol_xiaoetong_launch.py` follows the
first-party share redirect, validates the app/live anchor, obtains the provider's
public Web Link representation, ignores the page's mock branch and verifies that
the real `weixin://dl/business/?t=...` ticket embeds that exact replay. The mobile
User-Agent requests the provider's link representation instead of its desktop QR;
it is not login or entitlement. Do not invent tickets, app IDs or page paths.

Use the returned page URL for identity resolution only. After the same task is
armed and `/proxy.pac` is healthy and applied, execute `launch_command` once via
normal macOS URL handling. If the target mini-program is already open, reuse it.
Regenerate tickets at activation; never reuse an old ticket from a report. Read
the Goose Live window, not the unshareable main chat window. Inspect the visible
course-password gate, enter `666` once if present, and observe the exact finite
replay request. Password acceptance may itself start media loading; do not add a
redundant Play click. No hooks, WeChat re-signing, hidden debugging or protection
changes are allowed. Use visible player mute/pause controls when available; the
H5-only DOM mute instruction does not authorize attaching a debugger to WeChat.
If the resolver cannot prove a ticket, use the original visible message entry.
Native `#小程序://...` tokens still use that original-message fallback, not guessed
URL conversion. A launch plan is not playback, download or upload acceptance.

## Identity, activation, and download

The capture candidate API uses `view=capture`: fresh observed IDs/times only,
without historical title enrichment or remote metadata requests. General display
lists enrich asynchronously with an incremental cache; they cannot bind a source.

1. `resolve_xiaoetong_page`: open the supplied `source_url` only to obtain and
   validate the bound Xiaoetong app/resource anchor. Accept only a bound H5 live
   page (`/vN/course/alive/l_*`) or recorded-video page
   (`/p/course/video/v_*`). For a recorded-video page, also return the numeric
   `media_file_id` from the visible video. Validate MP wrapper app/resource;
   retain only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs.
   Accept `/v2` to `/v4` rotation only for the same app/resource. A bound
   `source_temporarily_unavailable` result is an expected H5 observation here.
2. Let the runner arm the exact source job using that stable identity. Do not
   arm another job when switching from the archived H5 route.
3. `activate_xiaoetong_mini_program`: the Agent owns the native WeChat UI
   action; never ask the user to open or select the replay. Use the reviewed
   Computer Use exception (`cua_repl`) against visible WeChat,
   inspect fresh state, keep one foreground session, one action at a time, and
   read state back after each. Do
   not use hooks, injection, webhooks, storage/cookie reads,
   credential extraction, clipboard loops, or rapid/global-shortcut
   retries. There is no evidence for a magic safe interval: wait only for a
   visible state/sniffer event, and make at most one
   activation attempt per scheduled boundary. If the app requires login,
   SMS/OTP, CAPTCHA, consent, or shows an explicit protection screen, return
   `account_login_required`/the corresponding blocked state and stop; that is
   the only user-action boundary. Enter `666` only at a visible
   course-password gate. Let the target start a media request; no continuous
   playback or fixed wait is required. Return
   `playback_surface=wechat_mini_program`, the exact `source_identity` and
   `live_id`, plus `media_request_observed=true` only when the singleton
   `wx_channels_download` sniffer saw the target request. A current-live
   `liveplay` request alone is not a finite replay; prefer the matching VOD
   `playlist_eof.m3u8` from the mini-program lookback path. Never return signed
   URLs, cookies, keys, or request headers.
4. The source job accepts only the newly observed candidate bound to the exact
   `live_id` and finite playlist. The runner then starts the same
   `type=live_capture`, `compress=true` task and validates the resulting
   `-compressed.mp4`. H5 block-page status must never be reported as download
   success.

## Continuation and completed-capture acceptance

The full continuation remains enabled in code: exact-source media observation ->
original compressed download -> media validation -> detach only the capture PAC
and stop the sniffer -> original Netdisk upload -> hash-bound mailbox handoff ->
authoritative end-to-end readback. Do not insert a new permanent stop after native
playback.

Completed-capture acceptance uses the persisted, exact candidate/source/task
receipt and rechecks local media hashes; it must not restart or query the cleaned
sniffer merely to pass audit. A mismatched saved task fails closed.
