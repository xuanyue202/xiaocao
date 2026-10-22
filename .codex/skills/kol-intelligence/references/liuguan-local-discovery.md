# Liuguan in Local Capture

Use the fixed 33 verified video-channel publishers as the primary source. Read
Wu's exact cached Moments database only to discover missed/new publishers. The
human refreshes Moments; never make opening Wu's chat, profile or Moments UI a
prerequisite. A cache miss never proves server absence.

`capture-local` runs this companion inside the existing hourly activity when
`~/.codex/yangsheng-capture/production/shared-enabled.json` matches the installed
shared Gopeed binary. Without that descriptor it stays disabled. Do not create a
second schedule or execute a second hour gate. The retained PTY owns the run.
Xiaocao upload, handoff and remote investment processing keep their own semantics.
Liuguan accepted media feeds the local ASR adapter and never enters those routes.

## Native connection request

On `daily_yangsheng_native_input_required`, establish one native replay-page
connection, then return the actual result to the same PTY. The SDK scans all
publishers and obtains replay IDs, publication times and finite durations; do
not navigate 33 homepages or sort screenshot positions as dates.

1. Read the current downloader status and the last successful `native-entry.json`
   as a hint only. Freshly verify the WeChat PID/window and actual replay page.
   Reuse an existing native feed page when available. Do not assume that a missing
   standalone browser means no page exists: WeChat can embed it beside the main
   window, and its separate rendering surface can appear blank.
2. If the page was closed, use the freshly visible native search entry to open
   the verified publisher **六观小院-町原**, select its **直播回放** tab and an
   actual finite replay. The observed native toolbar can detach that page into
   an independent window. No Wu navigation, user click or message sending is
   needed. Use current controls and frames, never historical coordinates.
3. Keep a compatible `native_lease()` around each bounded input/readback. The
   repository helper `scripts/kol_liuguan_window.swift` checks PID/window/frame
   and composited visibility. White screenshots alone do not establish logout.
   Wait for a readable target control; do not click through an unreadable page.
4. On a freshly verified native feed page, run:

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

A saved native window is a hint, never authority to refresh a different tab.
Keep the page available for the next activity; reopening it need not repeat a
publisher scan in the UI. Do not ask the human to perform routine navigation.

## Scan, download, ASR and cleanup

The catalogue keeps publisher/replay identities, actual publication timestamps,
coverage gaps, download intent and exact task IDs. An individual unavailability
or timeout leaves the cycle degraded and does not starve later publishers. A
login/protection or identity error stops the scan. Never claim global latest
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
ASR does not hold the proxy or native-input lease.

Current activation/acceptance truth is in `docs/development/liuguan-shared-capture.md`
and the private current receipts. Code/tests, a connected socket, an old accepted
file or a partial scan alone do not prove the whole shared activity passed.
