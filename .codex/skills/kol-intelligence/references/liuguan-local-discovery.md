# Liuguan in Local Capture

Use the fixed 33 verified video-channel publishers as the primary source. Read
Wu's exact cached Moments database only to discover missed/new publishers. The
human refreshes Moments; never make opening Wu's chat, profile or Moments UI a
prerequisite. A cache miss never proves server absence.

`capture-local` runs this companion inside the existing hourly activity when
`~/.codex/yangsheng-capture/production/shared-enabled.json` matches the installed
shared Gopeed binary. Without that descriptor it stays disabled. Do not create a
second schedule or execute a second hour gate. The retained PTY owns the run.
Run Xiaocao's retained capture, local articles and same-item cloud/Handoff
continuation first, then Liuguan. A Liuguan native-connection request must not
delay Xiaocao. Outside-window invocations do not start the companion.
Xiaocao upload, handoff and remote investment processing keep their own semantics.
Liuguan accepted media feeds the local ASR adapter and never enters those routes.

## Check and reuse the existing connection first

For diagnosis, run `PYTHONPATH=src .venv/bin/python scripts/kol_yangsheng.py connections`.
Optional `--reconnect-wait 35` only polls the retained local socket. This command
never starts a backend, reads/operates WeChat, changes PAC, scans publishers,
creates tasks or runs ASR. It checks the deployed binary/current service identity.
A connected socket permits trying the authenticated list API; successful identity,
coverage and media responses are still required. Connection status is not media
or login acceptance.

For an explicitly requested login diagnosis, run `kol_yangsheng.py session-status`.
This separately reads the existing vendor app's Accessibility/visible-window
metadata without launching, activating, clicking, taking screenshots or changing
permissions. Only the exact security message plus its acknowledgement button in
one currently visible window reports `reauthentication_required`. A missing or
unreadable prompt reports `unknown`, never authenticated. Stop native dispatch
when the fresh prompt is present and request the actual human re-login; do not
dismiss the protection notice. Keep diagnosing offline while authentication is
pending. Login recovery does not clear the automatic native-entry hold.

The Channels list API is a bridge to the authenticated SDK in the retained native
page. The page owns local reconnect; an empty server connection pool cannot be
repaired by calling a list or reload endpoint. Do not synthesize an unauthenticated
replacement socket. Xiaoetong uses passive mini-program response/media capture;
this Channels SDK cannot open or resolve a branded Xiaoetong share.

Read the private `native_share_bridge.json` activation hold before any missing-
connection fallback. A live existing socket remains usable while held, with no
UI/PAC action. A missing socket must return held/missing state without a native
initialization prompt or stdin wait. Direct bootstrap is also held before leases,
PAC or refresh. Login restoration does not clear the hold. Continue offline
connection/source diagnosis and existing downloads/receipts; do not relaunch or
refresh WeChat merely to make this diagnostic green.

## Native connection request

On `daily_yangsheng_native_input_required`, establish one native replay-page
connection, then return the actual result to the same PTY. The SDK scans all
publishers and obtains replay IDs, publication times and finite durations; do
not navigate 33 homepages or sort screenshot positions as dates.

1. First check `/api/shared-capture/status`: if `channels_available=true`, reuse it
   without any WeChat input or PAC change. The runner first allows up to35s for
   the retained page to reconnect its local socket (no UI or provider calls). Otherwise read the last successful `native-entry.json`
   as a hint only. Freshly verify the WeChat PID/window and actual replay page.
   Reuse an existing native feed page when available. Do not assume that a missing
   standalone browser means no page exists: WeChat can embed it beside the main
   window, and its separate rendering surface can appear blank.
2. If no verified native feed page remains, preserve the missing-connection
   state. The earlier successful toolbar search required an already open native
   browser; it is not a verified cold-start command. Do not open the Moments,
   profile, chat or global-search UI as a fallback. Direct homepage opening
   needs a separately verified, source-bound route. On October24 one bounded
   `open -a /Applications/WeChat.app <observed-share-url>` returned0 but produced
   no verifiable new feed window or socket; do not automate or repeat it as a
   working route. No new replay was captured by that probe.
3. Keep a compatible `native_lease()` around each bounded input/readback. The
   repository helper `scripts/kol_liuguan_window.swift` checks PID/window/frame
   and composited visibility. White screenshots alone do not establish logout.
   Wait for a readable target control; do not click through an unreadable page.
4. On a freshly verified existing native replay tab, prefer the bounded visible
   refresh handshake in a separate retained PTY:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/kol_yangsheng.py bootstrap --visible-refresh
   ```

   An already connected socket returns immediately with zero native input. Only
   after `liuguan_visible_refresh_required`, use CUA's freshly observed native
   File → Refresh menu exactly once on that verified replay tab, then send
   `refreshed` to this bootstrap PTY. It holds the compatible lease and a guarded
   narrow PAC, checks the actual socket, and restores PAC even if the 30-second
   refresh deadline expires. Do not resend the page refresh to fill a missing
   acknowledgement. If the existing capture-local input's separate 180-second
   deadline has elapsed, reconcile that returned run; after successful bootstrap
   use `kol_yangsheng.py capture` for only this companion, never another hour gate.

   The system-script alternative is available when fresh CG/AX identity agrees:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/kol_yangsheng.py bootstrap --window-id <verified-id> --pid <verified-pid>
   ```

   This uses the existing shared downloader, bounded exact-domain PAC and
   restoration guardian, refreshes that page and verifies the SDK connection.
   An existing foreign proxy is preserved. Never navigate the previously denied
   browser `/web/pages/home`, bypass a denied resource, change permissions or
   dismiss security/login protection. Native replay access is a separately
   verified route, not a blanket exception to a denial.
5. Only after the command reports `connected`, reply to the retained PTY with
   `{"operation":"initialize_liuguan_native_replay","status":"connected"}`.
   The runner rechecks the actual socket and scans. A failed initialization stays
   waiting with its specific evidence; continue safe diagnosis, not blind input.

The normal sweep calls authenticated replay-list APIs for the fixed account IDs;
none of the 33 publishers needs separate homepage navigation. Never respond to
a failed account read with repeated UI clicks or assumed protection causes.

A saved native window is a hint, never authority to refresh a different tab.
Keep the page available for the next activity; reopening it need not repeat a
publisher scan in the UI. Do not ask the human to perform routine navigation.

Xiaocao's existing Caoliao mini-program bridge is not evidence that Channels
homepage opening works. The inspected Caoliao Channels component requires both
the public `sph...` channel ID and `export/...` video ID; its confirmation stays
disabled with an empty video ID. Internal `v2_...@finder` publisher identities and
`weixin.qq.com/sph/` share tokens are different identifiers. Never interchange
them, publish the official sample as a target, or edit Xiaocao's live bridge to
test Liuguan. This component has not established a Channels cold-start route.

## Scan, download, ASR and cleanup

The catalogue keeps publisher/replay identities, actual publication timestamps,
coverage gaps, download intent and exact task IDs. An individual unavailability
or timeout leaves the cycle degraded and does not starve later publishers. A
login/protection or identity error stops the scan. The four provider-reported
deactivated accounts remain in the registry and history: only a matching native
profile with Ret=-5900 plus nickname 账号已注销 confirms that state. Report
available lists, deactivated accounts and unresolved gaps separately; assessed
accounts are not the same as successful replay lists. Known timeout/SDK JSON
decode/busy reads retry once with spacing; no UI retry is implied. Never claim global latest
coverage when a publisher failed. Never infer original livestream time/ID from
replay publication time or from a Moments share.

Downloads are reconciled before creating; an uncertain POST is never repeated
blindly. Preserve the original task through interruption. Acceptance requires
actual complete bytes, audio/video, finite duration, whole-file packet validation
and SHA. Only accepted artifacts enter the serial ASR worker, whose receipts bind
source proof, media hash, original timeline and complete transcript hash.

One Local Capture activity owns the shared lifecycle. A source finishing first
must not shut down a downloader still needed by the other. Page users hold the
shared lifecycle lease; cleanup takes its exclusive counterpart and waits for
active downloads, post-processing and artifact acceptance. PAC restoration and
process termination are separate checks: temporary page capture can restore its
prior PAC once its connection is initialized; background direct downloads do not
need that PAC. Preserve another source's active PAC and all retained tasks/claims.
When Xiaocao retains a repair, the finish stage still waits for Liuguan-owned
media and wakes ASR; it preserves the other source's backend/PAC. The20min
polling deadline does not include separately bounded file-validation calls.
Automatic ASR wakeups wait up to4h behind the current worker and then read the
fresh accepted catalogue; timeout remains a failure. Verify actual receipts.
ASR does not hold the proxy or native-input lease.

Current activation/acceptance truth is in `docs/development/liuguan-shared-capture.md`
and the private current receipts. Code/tests, a connected socket, an old accepted
file or a partial scan alone do not prove the whole shared activity passed.
