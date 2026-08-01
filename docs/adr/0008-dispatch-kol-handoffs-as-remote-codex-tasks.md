---
status: accepted
---

# Dispatch KOL handoffs as remote Codex tasks

The registered Codex Xiaocao task on `MacBook-Pro-6.local` is the normal
control plane between the local WeChat capture node and the sole runtime node.
After validating and uploading large media, the capture node sends that remote
task one compact, credential-free, self-hashed handoff envelope containing a
stable `handoff_id`, source identity, media metadata and hashes, and the exact
private-cloud reference. It does not transfer source-video bytes or a local
filesystem path.

The remote task validates the envelope, reconciles the `handoff_id`, and owns
transcript enrichment, semantic analysis, 灰常亮 publication, Enterprise WeChat
Relay notification, and Book KOL-US. Message delivery is at least once: the
local dispatcher retains an append-only dispatch record until remote task
readback, while the remote runtime retains idempotency and business receipts.
An ambiguous send must be reconciled against the target thread and
`handoff_id` before retrying.

No shared-file inbox is part of the normal runtime path. Public Git is reserved
for source and contracts; 灰常亮 remains the post-analysis intelligence store;
Obsidian/TOS may retain a manually synchronized recovery or audit copy; and
direct LAN/SSH copying is unnecessary. None of these transports authorizes the
local capture node to become a second runtime writer.
