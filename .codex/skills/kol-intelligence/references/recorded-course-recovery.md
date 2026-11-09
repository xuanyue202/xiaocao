# Reused room: recover a recorded course

Primary local Xiaocao workflow since the human's 2026-11-04 instruction. The
[previous fixed-room workflow is archived](archive/native-human-20261104.md).
The private `replay_catalog.acquisition_mode=recorded_course` selects the new
runner branch; missing/ambiguous/unpublished recordings stay pending, without
falling back to the reused live room. A new direct instruction is required to
switch back. Keep the existing schedule and sole remote post-Handoff writer.

The normal hourly retained runner now emits `observe_authorized_recorded_course`
after its replay-check time and unique catalogue match. Handle this in the SAME
PTY using Browser, not by launching the standalone helper. Return the exact
`action`, `subscription_id`, `status=observed`, fresh observed `candidate_id`, finite
`player_duration_seconds` and `player_left=true`. Require fresh exact merchant and
finite-HLS responses after the observation boundary. A retained candidate can
keep its first-seen time, while a URL refresh can create a new ticket candidate
for the same file; preserve original bindings and prove any ticket alias separately.
If the exact recording redirects to the Xiaoetong/eLink account-login surface,
immediately return the same `action` and `subscription_id` with
`status=account_login_required`; omit media fields. This is an observed human
authentication boundary, not a native-input timeout or failed recording. The
runner must preserve the original capture and release its network guardian
without waiting out the 20-minute input deadline.
The standalone helper below is only for a reconciled idle
same-original repair with no active capture runner.

## Browser transport recovery through OpenCLI

Codex CUA `native pipe closed before response` does not establish an Edge,
OpenCLI, account or course failure. Under the human's Nov5 repair request,
OpenCLI is an authorized Browser path for this normally entitled recording.
Check the pinned CLI's `daemon status` and `doctor` first; an extension connection
alone is not a successful page read. Reuse the connected Edge profile and a
single `xiaocao-recorded-course` Browser session. Do not restart the user's Edge,
copy a profile, inspect cookies/passwords, change extension access or bypass a
policy denial. Login, CAPTCHA and agreements retain their human action gates.

```bash
npx --yes @jackwener/opencli@1.8.6 daemon status
npx --yes @jackwener/opencli@1.8.6 doctor
npx --yes @jackwener/opencli@1.8.6 browser xiaocao-recorded-course tab list
npx --yes @jackwener/opencli@1.8.6 browser xiaocao-recorded-course state --window foreground
```

After reconciling old ownership, keep the exact `capture-xiaocao-item` or original
hourly runner alive in its PTY. The runner must arm listening under its network
guardian before Browser media requests. In OpenCLI, open the emitted `course_url`
to obtain fresh parent-catalogue evidence, then open the emitted exact
`recording_url` (or its visible same-course row). Reading only public catalogue
metadata or CLI connectivity cannot satisfy the entitled source/media contract.

Use `browser ... eval` only for safe DOM facts: `document.title`,
`location.pathname`, and video `duration`, `readyState`, `paused`. Never return
`currentSrc`, signed URLs, hidden inputs, storage or network ticket bodies.
Read the exact candidate ID through the existing credential-free downloader API;
the collector independently proves catalogue/detail/play/material/finite-HLS
lineage. Leave the player using `browser ... back`, then verify the same course
path and zero video elements. Return only the original request's exact
action/subscription/candidate/duration/player-left fields to the same PTY.
This changes Browser transport, not source/capture/task identity or acceptance.

If the pinned CLI transport fails, reuse only the transport checks, existing
Edge profile and at-most-once daemon restart from
[OpenCLI Edge recovery](opencli-edge-recovery.md) steps 2–4. Verify the emitted
course/recording path and collector evidence afterward; its Netdisk folder,
`/api/list`, saved-login and extension-permission steps do not apply to this
recording session. Retain the original claims and this section's human
authentication gates. It permits no WeChat UI operation. Netdisk upload
still uses the separate repository-owned adapter `site:baidu-netdisk`; this
Browser session's empty queue cannot reconcile an uploader effect.

Use when a fixed Xiaocao room now announces a later session or its original
replay has disappeared. Read the original message through the cached reader.
Stop the exact idle polling runner when the human asks to stop waiting; verify
its network guardian restored the owned PAC. Preserve the original item,
capture, entry claims and backoff. This is not a human course exclusion.

## Inspect the published recording before another entry

The private bridge may contain `replay_catalog` with `app_id`, `course_id`, and
`mini_program_token`. Configure it only from the same merchant's actual history
link and its read-back course page. It holds no account credentials. Run:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_replay_catalog.py \
  --identity <original identity> --inspect-access
```

This command only reads public catalogue/detail metadata using its own anonymous
session after revalidating the exact manifest identity/hash against the cached
original. It creates no capture, entry, download, upload or mailbox effect and
does not require the source slot. Its complete scan selects one dated early or
evening title for the recent original. `recorded_replay_candidate_found` is an
inventory match, not session/media acceptance. Keep the returned independent
`v_...` resource and duration bound to the original; a reused `l_...` room is
insufficient. Ambiguity, incomplete reads and schema failures remain degraded.

Fixed-entry notices explicitly saying to save this link for tomorrow are
navigation inventory, not that publication evening's recording. Classification
uses the narrow source header before its written recap; it preserves the original
and every claim. Only recorded mode skips an independently verified idle/unbound
inventory item. A configured `navigation_source_url` may identify the verified
history catalogue link when the raw message explicitly labels it
`历史直播回放点击链接学习` and includes exactly one same-message branded mini with
the configured token. Generic or differently sourced URLs remain independent.
The role may have a circled or decimal list prefix, such as
`②历史直播回放点击链接学习：...`; the prefix changes presentation only. It does not
relax the exact URL, same-message identity or merchant/course checks. A saved
navigation item is not a completed recording and never invokes the legacy
live-room identity resolver in recorded mode.

Anonymous `is_subscribe=0`/`is_unlock=0` describes that anonymous session, not
the human's account. The human's Nov4 recorded-course recovery task authorizes
the normally logged-in history-course Browser path separately from opaque
native live-room entry. Keep WeChat UI human-owned. Do not infer entitlement
from anonymous metadata or decode protected tickets. This does not authorize
an H5 live player, automated login or bypassing course access controls.

Run `scripts/kol_recorded_recovery.py --identity <original>` in a retained PTY
after reconciling earlier idle ownership. It holds the source/network owner and
asks Browser to observe the exact independent recording through the normal
course session. Verify parent-course `subscribe=1`/`available=1`, exact video
metadata and dated title, finite duration and actual media requests. Return
only original identity, candidate ID, player duration and `player_left=true`
after leaving the player. The helper reopens merchant HTTP evidence, proves the
catalogue/detail/media mapping and finite playlist, and binds the SAME unbound
capture. It creates no replacement capture or download. Preserve all original
native entry receipts.

The detail's opaque `play_sign` must equal the actual play-response map key and
its material ID must match before using that block's media. Compare it in memory;
persist only its hash. Never borrow another block or export/decode the ticket.
Recorded-course media hosts are exact, not suffix-based. The approved set is
`encrypt-k-vod.xet.tech` plus the human-authorized `t-vod.h5.xed.plus`; the
latter is accepted only for this same merchant play-response route, exact
resource/material/file binding, finite HLS duration/segment proof and the
existing in-memory AES-128 key gate. Other `xed.plus` subdomains, lookalikes,
custom ports, HTTP, foreign source routes and extra headers remain denied.
If interrupted between source/candidate/manifest writes, resume the SAME proof
using `--proof-path <original saved proof>`; do not create a new observation.

After the helper exits and its guardian restores PAC, continue the exact original
with `capture-xiaocao-item --source-identity <original>` in a retained PTY.
Provider-issued tickets stay in singleton memory. The downloader validates the
observed finite recording, then normal cloud/mailbox acceptance follows. Use
`recorded_course_surface` acceptance; Browser observation is not WeChat playback
or closure. Keep the independent `v_...` resource/file ID separate from the
historically reused transport room. Code repairs need scoped tests and review;
never relabel a recorded source as a live source to bypass a guard.

If a backend repair loses the original in-memory ticket, preserve the bound
source/candidate/claim. Reconcile the complete provider task list first. Only an
unexecuted original claim may bind a separate fresh same-file ticket proof through
`refresh_recorded_ticket`; the new ticket candidate is an alias, not a replacement
capture. It must match original date/course/resource/file/material/path, and the
backend checks fresh merchant and finite playlist evidence independently. Never
retry an uncertain dispatch or refresh an already running task.

## Stable acquisition route

Use the existing local schedule to inspect published history recordings after
source discovery and before restoring an unbound fixed-room entry. A missing
recording is not proof of deletion. When a recording is listed, resolve that
recording rather than opening the room's next session. Retain a new independent
recording's merchant resource, original date/session and accepted file identity;
then continue the existing finite-media, exact cloud and mailbox acceptance.

Getting the room ID before a live session does not reserve its future replay.
Capture actual merchant-ended/replay-ready evidence and file identity promptly
after the session if available; changing these schedules or recording live
streams requires a separately implemented and verified route. Existing
readiness and human WeChat ownership remain in force.

The 2026-11-04 comparison of 86 completed recordings showed multiple independent
file resources for one room. Regular CDN path shapes do not supply the next file
ID or access signature. Public downloader candidate APIs deliberately redact
signed queries. A bare-path 403 cannot establish deletion; use the singleton's
fresh merchant-issued ticket for an accepted exact recording. Neither URL
guessing nor copying a live-stream URL establishes a finite recorded source.
