# Keep WeChat discovery alive during a retained capture repair

Status: ready-for-agent
Baseline: 97a2a5d0779249c3fe5e1da38274542087ddf1fb

The user's October 20 17:29 original share is readable by the production
WeChat reader/parser but absent from the subscription manifest. Six original
entries since October 16 evening are absent. Coordinator repair retention
suppresses the whole source runner, including metadata discovery.

Requirements:
- Keep exact-contact metadata discovery running under the existing source slot
  when capture execution is retained for repair or a provider deadline.
- Persist every distinct original entry and report discovery time, pending IDs
  and expiry separately from capture/repair progress. Discovery is never capture
  or Handoff completion.
- Do not retry native/browser/PAC/media/upload/mailbox effects, replace an ID or
  claim, overwrite/close the original failure, or bypass a native security gate.
- Preserve the original repair if discovery itself fails; surface the discovery
  failure separately. Other sources must still finish.
- Keep source-busy and outside-window behavior, first-run baselining and 72-hour
  ungenerated expiry. Bound media/transfer claims remain reconcilable.
- Restore the readable backlog using production discovery, prioritize the user's
  exact October 20 evening entry, and distinguish missing discovery, incomplete
  capture, local handoff and remote ACK in the audit.
- Preserve the current automation cadence; update its prompt through the runtime
  API to require fresh discovery evidence during retained repair. Do not claim
  that a schedule configuration proves any evening run executed.

Native protection diagnosis is separate from this discovery fix. A successful
offline test does not authorize replay of the unchanged protected launch route.
