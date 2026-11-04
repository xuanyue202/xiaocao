# Recorded-course recovery for reused Xiaocao rooms

Status: In progress — catalogue inventory implemented; entitled native recording capture unverified.

The human task is to recover Nov 4 morning and establish stable recording
acquisition. The live room is reused, so its next-session state cannot identify
the earlier recording. Actual history catalogue contains a Nov 4 morning video
resource with duration 2311 seconds. Anonymous detail has no subscription/unlock.

Scope of this change: add a credential-free public catalogue inspector tied to
the existing original and configured merchant/course. Read complete bounded
pagination, select one narrow dated session title, preserve independent resource
and duration, and expose only allowlisted access flags. Reject wrong source,
ambiguous sessions, old originals, incomplete pagination and changed identities.
Never expose media tickets or create entry/capture/download/upload/mailbox effects.
Teach the existing local SOP to use catalogue inspection before another fixed-room
entry; preserve current schedule, human UI ownership and original claims.

Acceptance: focused offline tests; actual metadata readback for the original,
exact resource and duration; independent Standards and Spec review. This does
not accept video bytes, DRM handling, entitled native recorded-course integration,
cloud/Handoff or end-to-end stable acquisition. Those require real authorised
source evidence; do not infer them from a catalogue entry or URL shape.
