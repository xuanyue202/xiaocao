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

The first writer cutover separately transfers a consistent snapshot of the
full authoritative lightweight KOL state. Recurring capsules contain only the
one job projection and must never overwrite the global KOL or Book ledgers.

No shared-file inbox is part of the normal runtime path. Public Git is reserved
for source and contracts; 灰常亮 remains the post-analysis intelligence store;
Obsidian/TOS may retain a manually synchronized recovery or audit copy; and
direct LAN/SSH copying is unnecessary. None of these transports authorizes the
local capture node to become a second runtime writer.
