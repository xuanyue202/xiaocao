# Reject interrupted finite replays before Handoff

Baseline: e81381fc31efd7aa437f6462ceabe5ae220eebe8

The user reported a network interruption during the Oct20 evening capture.
The same task continued but its final MP4 is 6190.762887 seconds against the
singleton's exact ended finite playlist of 6228.206 seconds. It decodes, yet is
37.443113 seconds shorter and contains a 2.598 second video DTS gap. The existing
1%-or-15-second gate accepted this file, and an upload was already claimed.
No mailbox send is authorized for this artifact. Preserve the original IDs,
claims, bytes/hash and uncertain cloud effect; do not resubmit or mutate it.

Requirements:
- Replace duration-relative tolerance in ordinary validation, interrupted-file
  reconciliation and independent acceptance with a fixed codec/container
  rounding bound of 2 seconds. Reject non-finite or missing HLS evidence rather
  than falling back to the artifact's own duration for an HLS capture.
- Re-read the actual artifact and original duration evidence even when a prior
  media_validated receipt exists. Never trust provider done or a cached receipt
  as proof that an interrupted finite replay is complete.
- Preserve recorded non-HLS handling and original task/source/capture/upload
  identities. Do not clear, overwrite, or recreate ledgers and side effects.
- Prove the observed false acceptance fails before the fix and passes after;
  cover small codec rounding, invalid evidence and interrupted reconciliation.
- Keep known active upload reconciliation in its retained PTY. Do not dispatch
  its mailbox operation for this rejected artifact; safe same-item media repair
  remains separate from validation and must preserve prior claims.
- This is an integrity fix, not proof of byte-offset resume, of exact skipped
  HLS segments, or of WeChat's security protection cause.
