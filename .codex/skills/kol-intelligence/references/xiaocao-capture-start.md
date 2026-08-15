# Xiaocao Capture-Node Fast Start

Use this complete local SOP for an unambiguous request to capture a Xiaocao
live replay. Its first objective is a truthful Ready response within 10 seconds.
Ready means the exact sniffer is healthy and a fresh candidate baseline is
durably armed; it does not mean that the video or the business workflow is done.

## Ready path

Before Ready, do only this:

1. Reuse the output directory only when it is already bound to this exact
   unfinished user request. Otherwise choose a fresh per-request directory such
   as `output/live/kol_xiaocao_live_YYYYMMDD_morning`.
2. Immediately run:

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py run \
     --output-dir <per-request-output-dir>
   ```

3. Say Ready only when the command returns `event=capture_armed`,
   `status=awaiting_capture`, a `capture_job_id`, a process PID, and the playback
   prompt. The command itself proves the exact binary, local API health, and the
   candidate baseline before it emits that result.
4. Ask the user to open the target enterprise-WeChat card. The player only
   needs to appear; continued playback and a fixed wait are unnecessary. As
   soon as the bound page has a current `<video>` element, if the agent starts
   media to trigger capture it must first set and read back
   `video.muted=true` and `video.volume=0` through the bound Browser tab's
   page-level control (use the tab `cdp` capability's scoped `Runtime.evaluate`
   when player controls are hidden), and must reapply this after a page refresh,
   navigation, or player rebuild. System/browser mute alone is not sufficient.

Do not inspect Git or scan historical ledgers before Ready. Do not contact the
remote writer, load market or portfolio data, or read `full-contract.md` before
Ready. Those checks cannot make the local sniffer safer and must not delay the
playback prompt.

## Bounded proxy lifecycle

The sniffer is an on-demand capture process, not a long-lived daemon. Never keep
it warm between requests. If the user cancels, changes the target, or abandons
the request before a new candidate is detected, stop the idle wait immediately:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py cancel-wait \
  --output-dir <per-request-output-dir> \
  --capture-job-id <id>
```

The cancellation is valid only while the capture ledger still says
`awaiting_capture`; it must stop the exact process gracefully and prove that
ports 2022/2023 are closed, `/api/status` is unavailable, and all macOS proxy
flags are zero. It must not write the final media-cleanup receipt or cancel an
active download.

## Capture, upload, and handoff

After the target player appears, resume the same job and output directory:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_xiaocao_live.py run \
  --output-dir <per-request-output-dir> \
  --capture-job-id <id> \
  --opencli-session <stable-session> \
  --opencli-profile <connected-profile>
```

Resume rather than creating a replacement job after interruption. The local
capture node must prove all of the following before cloud work advances:

- the newly detected `live_id` was not in the armed baseline;
- the download is `type=live_capture`, `compress=true`, and
  `compress_inline=true`;
- the runtime-named file ends in `-compressed.mp4`, has nonzero size and
  plausible duration, passes `ffprobe`, and has no retained raw counterpart;
- the exact sniffer process is gone, ports 2022/2023 have no listener, its API
  is unavailable, and every relevant proxy flag is zero.

The capture node owns the large upload and then publishes one credential-free,
self-hashed metadata handoff. It does not read the generated transcript, make
investment decisions, publish 灰常亮, notify the household, or write Book.

After `cloud_handoff_published`, send the capsule to the existing registered
remote Xiaocao task. The remote sole writer reads `full-contract.md`, imports
the capsule idempotently, and uses `scope=post_handoff`. It must not require the
local capture ledger, cleanup receipt, local media path, or source-video bytes.

Local acceptance ends with compressed-media proof, deterministic proxy cleanup,
cloud readiness, and the self-hashed handoff. End-to-end completion additionally
requires the remote post-handoff acceptance receipt, stable 灰常亮 report readback,
and exact-recipient reminder terminal.
