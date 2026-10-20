# Same-task HLS checkpoint recovery and an unpublished repair version

Baseline: ebb8a451bfc33ad4c91b0b8ce0d19dac31d9d4f0

The user explicitly authorizes a corrected version of the Oct20 evening item,
preserving the original subscription/capture/download task, old local file and
all history. The corrected hash may receive its own upload binding. The old
incomplete cloud artifact/capsule is never handed off. This does not authorize
new native protection reproductions or replacement capture/download jobs.

Requirements:
- Finite HLS transport commits complete verified segments to private per-task
  checkpoints; retries partial segments as whole units. Resume after process
  restart reuses completed segment hashes; this is segment-level network resume,
  not byte-offset resume or preserving already-encoded CPU work.
- Bind original resource, effective redirect origin/path, headers hash, exact
  finite manifest and capture/live IDs. Reject binding changes/corruption.
- Same-origin resources/redirects only, no credential forwarding or server-side
  fetch to foreign/private targets. Local fixtures may use an explicit numeric
  loopback origin, still without cross-origin access.
- Auth rejection is terminal for that bound checkpoint, including later requests.
  Unknown or failed segments cannot be reported done. Require all finite media
  segments and the actual completed MP4 duration within 2 seconds before deleting
  raw checkpoints. Never preserve raw source cache after successful completion.
- One explicit exact-task revision API verifies the rejected original hash and
  duration, preserves old bytes/name, reserves a new output, persists a paused
  revision under the original task ID, and starts no transfer. Repeated calls
  reconcile the same revision, never allocate another. Only loopback may call it.
- A paused reserved output cannot be chosen by another auto-renaming task or
  overwritten if occupied before its checkpoint starts.
- Root repair records a durable claim before dispatch. A lost backend response
  reconciles exact task labels without repeating preparation/resume. Preserve
  all original candidate/source/capture/task and upload/cloud receipts.
- Reject the old unreceipted mailbox attempt only after exact authoritative
  NOT_FOUND; preserve the attempt in history, exclude it from future polling and
  prohibit its republication. Receipted or ACKed messages cannot be retired.
- New media/capsule/cleanup versions are append-only and hash-bound, using the
  same original item and ordinary cloud/mailbox pipeline. Never overwrite an old
  capsule/receipt, reuse a wrong hash, activate native UI or rerun the hour gate.
- Failed checkpoint tasks must stay on the same task, never fall through to the
  legacy force-download replacement path. Explicit user pauses remain gated.
- Package additive backend files and exact before/after checked integration
  patches in the repository; build/test without installing. Only the existing
  fresh same-capture cleanup installation gate may replace the binary.

Acceptance: adversarial local HTTP tests and real FFmpeg disconnect/restart,
identity/claim tests, independent Standards/Spec reviews, pushed code and runtime
readback. These are engineering evidence; business completion still requires the
correct exact artifact, cloud video_ready, mailbox created|already_present and
same-ID/hash readback. Full completion requires bound remote acked.

Validation checkpoint: 573 related Python tests passed; Go stream/download and
API/interceptor tests passed. A real child process exits with FFmpeg active after
segment commit, and restart retains the task capability and reuses that segment.
Independent review found and drove fixes for origin confinement, paused-output
reservation, early checkpoint persistence, corrupt proof rejection, whole-cache
and manifest authentication terminal state, user-pause gating, and raw provider
label shape in versioned cleanup. Final affected reviews pending.
