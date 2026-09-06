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

For an HTTPS share entry, the default launch route is the verified merchant
Web Link, not chat-window screenshots or a browser player. Run the emitted
`launch_resolver_command` with `PYTHONPATH=src`. The read-only
`scripts/kol_xiaoetong_launch.py` follows the first-party share redirect,
validates the app/live anchor, obtains the provider's public Web Link
representation, ignores the page's mock branch and verifies that the real
`weixin://dl/business/?t=...` ticket embeds that exact replay. The mobile
User-Agent requests the provider's link representation instead of its desktop
QR; it is not login or entitlement. Do not invent tickets, app IDs or page
paths.

Use the returned page URL for identity resolution only. After the same task is
armed and `/proxy.pac` is healthy and applied, execute `launch_command` once via
normal macOS URL handling. If the target mini-program is already open, reuse it.
Regenerate the merchant ticket only for that one activation; never reuse an old
ticket from a report. Read the Goose Live window, not the unshareable main chat
window. Once the exact course is visible, do not resolve again, refresh, or open
a second Scheme. Prefer accessibility controls; when the mini-program exposes
only a window, use the fresh screenshot to click its visible controls. Never
reuse coordinates from an earlier screenshot/run or click the main chat window.
At the visible course-password input, enter `666` once, read it back, and confirm.
Confirmation may automatically start playback. Immediately press `space` in the
player window when playback starts, before querying logs or download progress.
If it does not auto-start, click the visible Play control once then press `space`.
Verify that the picture/playhead stops on two observations; a cursor triangle,
successful click, or disappearance of controls is not pause evidence. Never
press Space a second time on an already paused video, as it resumes playback.
No hooks, WeChat re-signing, hidden
debugging, CDP/DOM evaluation, or protection changes are allowed. If the resolver
cannot prove a ticket, use the original visible message entry. Native
`#小程序://...` tokens still use that original-message fallback, not guessed URL
conversion. A launch plan is not playback, download or upload acceptance.

## Identity, activation, and download

The capture candidate API uses `view=capture`: fresh observed IDs/times only,
without historical title enrichment or remote metadata requests. General display
lists enrich asynchronously with an incremental cache; they cannot bind a source.

1. `resolve_xiaoetong_page`: resolve the supplied `source_url` only to obtain
   and validate the bound Xiaoetong app/live anchor. Accept only a bound H5 live
   page (`/vN/course/alive/l_*`) or MP wrapper resolving to that same live ID.
   H5 is identity-only: return `page_state=unknown`; never log in, inspect a
   player, obtain media, or treat an H5 page state as capture evidence. Retain
   only `app_id`, `pro_id`, `type`, `alive_mode`, stripping share IDs. Accept
   `/v2` to `/v4` rotation only for the same app/live ID.
2. Let the runner arm the exact source job using that stable identity. Do not
   arm another job when switching from the archived H5 route.
3. `activate_xiaoetong_mini_program`: the Agent owns the native WeChat UI
   action; never ask the user to open or select the replay. Use the reviewed
   Computer Use exception (`cua_repl`) against visible WeChat, inspect fresh
   state, keep one foreground session, and read state back after each semantic
   action. Do not use guessed coordinates, hooks, injection, webhooks, storage/cookie
   reads, credential extraction, clipboard loops, CDP/DOM evaluation, or
   rapid/global-shortcut retries. There is no evidence for a magic safe
   interval: wait only for a visible state/sniffer event, and make at most one
   activation attempt per scheduled boundary. If WeChat visibly requires phone
   login, SMS/OTP, CAPTCHA, consent, or shows an explicit protection screen,
   return `wechat_client_login_required` and stop; that is the only
   user-action boundary. At the exact visible course, enter `666` only at a
   visible course-password gate, then immediately pause with Space after auto-play
   (or one visible Play click). Read back a stopped picture/playhead. Let the target
   start a media request; no continuous playback or fixed wait is required. Return
   `playback_surface=wechat_mini_program`, the exact `source_identity` and
   `live_id`, plus `media_request_observed=true` only when the singleton
   `wx_channels_download` sniffer saw the target request. A current-live
   `liveplay` request alone is not a finite replay; prefer the matching VOD
   `playlist_eof.m3u8` from the mini-program lookback path. Never return signed
   URLs, cookies, keys, or request headers.
4. The source job accepts only the newly observed candidate bound to the exact
   `live_id` and finite playlist. The runner then starts the same
   `type=live_capture`, `compress=true` task and validates the resulting
   `-compressed.mp4`. An H5 identity anchor can never be reported as download
   success.

## Minimal execution checklist (follow in order)

1. **Resume the exact item.** Read its manifest identity and `capture_job_id`.
   If a PTY is already running, retain it. If it exited, use the existing-item
   command from the local entry, not another `capture-local`, new arm or job.
   A `downloading`/`cloud_handoff` item needs no WeChat action at all.
2. **Before launching, verify capture routing.** Require `/api/status` success,
   the existing capture ID, and a healthy `/proxy.pac`. Read `route -n get default`
   and `networksetup -listnetworkserviceorder` to identify the current network
   service. If its capture PAC is disabled, set only that service's PAC URL to
   `http://127.0.0.1:2023/proxy.pac` and enable it; read back URL and Enabled=Yes.
   The PAC must route only Xiaoetong domains through 2023 and all WeChat security
   domains DIRECT. Do not modify unrelated proxies. The downloader guard and
   post-download cleanup own restoration. Missing PAC can let playback work
   while preventing capture; it must not be diagnosed as a login issue.
3. **One launch and password.** Execute the supplied resolver, verify exact
   app/live ID, then its `launch_command` once. Loading/blank main chat is not a
   logout. Read the Goose Live course window. Click visible 输入密码, then the
   modal input, type `666`, verify it, click 确定. Each step uses fresh UI state.
   If no gate is present, omit password actions. Never enter a course password
   into a WeChat account-login form.
4. **Pause immediately.** Password acceptance can auto-play. Press `space` in
   Goose Live as soon as the playing picture appears. Verify stopped picture/time
   on two observations. Do not spend time checking capture logs while it plays.
   Return `playback_paused=true` only after this check. If another user action
   changes the window, reread it and avoid toggling a video already paused.
5. **Verify media, then feed the PTY.** Use candidate `view=capture` and match
   exact `live_id`, app host and post-arm time. Require the finite VOD
   `playlist_eof.m3u8`, not the `liveplay` FLV/M3U8 candidates emitted alongside
   it. Return the exact requested JSON, `activated=true`, `password_used` as
   observed, `media_request_observed=true`, and `playback_paused=true`. For a
   native-message entry also return the exact fresh candidate ID. Do not paste
   signed media URLs, request headers or cookies. The downloader creates one
   source-bound task; never create a second task manually.
6. **Stay through upload and Handoff.** Keep the PTY open while it downloads and
   compresses, validates the MP4, cleans the sniffer/PAC, and uploads. Follow any
   Browser recovery through the existing upload job and persistent session.
   On mailbox input call the exact LiangHui operation and feed its actual
   structured receipt to the same PTY. Accept only cloud `video_ready` plus a
   same-hash `created|already_present` mailbox receipt as `Handoff完成`.

After Handoff, run the read-only acceptance gate:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_capture_acceptance.py \
  --identity <manifest-identity> --required-count 1
```

Require `status=passed`. Record the exact capture/source/task IDs, final filename,
SHA-256, duration/bytes, Netdisk job/cloud receipt, Handoff ID and mailbox hash in
the run's local evidence. Never call a code/test pass or `waiting` an E2E pass.
Mailbox `acked` is the separate remote `全部完成` state.

An explicit browser security-policy denial is not a transient OpenCLI timeout.
Stop the denied browser action and retain the upload claim; do not switch tools,
browser surfaces or protocols to bypass it. A submitted file without a cloud
receipt remains uncertain, even if another page shows an empty upload queue.
Do not resubmit or report Handoff until that exact job is safely reconciled.

## Continuation and completed-capture acceptance

On macOS the patched downloader owns a detached `__proxy-guard` pipe lease.
It snapshots HTTP/HTTPS/PAC settings before takeover, restores only its exact
endpoints before normal shutdown, and also restores after parent death (including
SIGKILL). Do not kill the guard or count it as a second capture process. Closing
a terminal (SIGHUP) follows normal cleanup. Preserve other software's later proxy
changes; never switch off every system proxy to force a green acceptance.
Cancel-wait must detach the owned PAC before stopping the sniffer, including on
inactive network services left behind by a network switch. Retain the existing
media/receipt validation gates. PAC uses `PROXY ...; DIRECT` for capture domains;
direct fallback preserves connectivity, not media-capture success.

If an older crash or machine restart leaves an orphaned endpoint, use the exact
installed downloader's `proxy-recover` subcommand (not a new capture). It refuses
a listening endpoint or active guard lease, touches only its own HTTP/HTTPS/PAC
configuration, and verifies readback. Without a prior snapshot it disables that
orphan, not a guessed previous VPN. Guard failures are logged in
`~/Library/Caches/wx_channels_download/proxy-recovery.log`; report them rather
than claiming cleanup. Power loss, simultaneous guard death, and denied system
configuration writes are not covered by a graceful-exit guarantee.

The full continuation remains enabled in code: exact-source media observation ->
original compressed download -> media validation -> detach only the capture PAC
and stop the sniffer -> original Netdisk upload -> hash-bound mailbox handoff ->
authoritative end-to-end readback. Do not insert a new permanent stop after native
playback.

Completed-capture acceptance uses the persisted, exact candidate/source/task
receipt and rechecks local media hashes; it must not restart or query the cleaned
sniffer merely to pass audit. A mismatched saved task fails closed.
