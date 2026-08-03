---
status: accepted
---

# Dispatch KOL handoffs as remote Codex tasks

The registered Codex Xiaocao task on `MacBook-Pro-6.local` is the normal
control plane between the local WeChat capture node and the sole runtime node.
After validating and uploading large media, the capture node sends that remote
task one compact, credential-free, self-hashed handoff envelope containing a
stable `handoff_id`, source identity, media metadata and hashes, and the exact
private-cloud reference. The envelope also carries a separately hashed,
portable `video_ready` projection for that one Netdisk job. It does not
transfer source-video bytes, a local filesystem path, browser evidence, or
credentials.

The remote task validates both hashes and bindings, imports the projection
idempotently into its append-only ledger, and reconciles the `handoff_id` before
owning transcript enrichment, semantic analysis, 灰常亮 publication, Enterprise
WeChat Relay notification, and Book KOL-US. Imported browser control remains
blocked until the remote OpenCLI session independently scans the target folder
and finds exactly one matching file. Message delivery is at least once: the
local dispatcher retains an append-only dispatch record until remote task
readback, while the remote runtime retains idempotency and business receipts.
An ambiguous send must be reconciled against the target thread and
`handoff_id` before retrying.

Acceptance follows the same ownership boundary. The capture node proves local
capture, compression, cleanup, upload, and handoff. The remote writer persists
the imported capsule as an immutable receipt and audits only
`scope=post_handoff`: transcript, AI-note request, semantic decision, 灰常亮,
notification, and Book. It must not require or synthesize a local capture
ledger, cleanup receipt, or media path. End-to-end acceptance composes the two
receipts by `handoff_id` and media SHA-256.

Relay transport is separable from business ownership. If the remote sole
writer cannot reach the public Enterprise WeChat Relay and the local capture
node can, the remote task retains the original notification claim and emits a
self-hashed, credential-free transport request bound to the final report,
content hash, exact recipients, original failure, and explicit confirmation
that those recipients are missing the message. The local node then claims and
receipts each requested recipient independently. It returns one self-hashed
all-recipient receipt through the existing Codex task; the remote writer
validates the original request and receipt together, binds their hashes and
fields to one matching prior claimed/uncertain notification state, and records
delivery under the original notification identity. No business decision,
report publication, Book action, or global KOL
state is written locally. A delivered recipient is never resent, a proven
pre-connect failure may resume only for that recipient, and an uncertain call
stops for reconciliation.

The notification identity and the reader copy are separate dimensions. If a
quality correction changes title or body after the original uncertain claim,
the request must carry a `content_revision` binding the old claim-hash prefix,
new full content hash, current report content hash, and correction reference.
Previously recorded request/receipt pairs that predate this field are replayable
only from an exact existing validated-transport plus delivered receipt; replay
adds no ledger event.

The claimed content hash always covers the exact title and body passed to the
Relay. A publication layer supplies its final reminder through an explicit
message builder; substituting different bytes inside a sender callback is
forbidden. When a revised notification identity renders byte-identical content
ending in the same stable report URL as one already validated all-recipient
transport delivery, the writer records a content-alias delivery and does not
call the Relay. Any ambiguity or content difference remains fail-closed.
Completed 灰常亮 publication receipts are read before constructing a new
candidate on coordinator resume, so a later reader-copy bundle cannot republish
the stable report. Reminder copy is still validated independently. Ticket03
acceptance counts one content-alias authorization plus one delivered receipt as
the exact-once notification terminal.

Code handoffs bind the exact 40-character commit read by
`git rev-parse HEAD`. The sender must not manually expand an abbreviated SHA,
and the receiver must compare it with the fetched branch and reject any
mismatch before checkout, validation, or business recovery. This makes a bad
coordination message a read-only failure instead of a runtime state change.

The first writer cutover separately transfers a consistent snapshot of the
full authoritative lightweight KOL state. Recurring capsules contain only the
one job projection and must never overwrite the global KOL or Book ledgers.

No shared-file inbox is part of the normal runtime path. Public Git is reserved
for source and contracts; 灰常亮 remains the post-analysis intelligence store;
Obsidian/TOS may retain a manually synchronized recovery or audit copy; and
direct LAN/SSH copying is unnecessary. None of these transports authorizes the
local capture node to become a second runtime writer.
