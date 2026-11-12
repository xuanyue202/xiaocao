# KOL capture repairs and actionable failures

Status: ready-for-agent

The local capture task repeatedly ended after a stale historical timeout and a
changed merchant share token produced `original_catalog_binding_invalid`.
The human requested on 2026-11-12 that recoverable faults be repaired in the
same task and irreducible human actions be visibly requested.

Requirements:

1. Preserve original message, share token, capture/task/claim/receipt identity.
   A changed share token may use the configured catalogue only with one exact
   branded mini-program and the explicitly labelled, exact configured history
   URL in the same hash/time/contact-bound cached message. No guessed aliases,
   foreign source, broad title equivalence or live-room fallback.
2. Apply the same source verification to discovery, inspection and media proof.
   Hide a verified idle navigation item from capture, retaining its history.
3. Catalogue errors and exact-item command failures must return structured
   Agent-owned repair progress, not a traceback or provider-unpublished state.
   A local run with unresolved repair or human action must exit nonzero and
   expose its responsibility and next action.
4. Exact-item login uses the existing deduplicated operational notice, preserving
   IDs and releasing the network guardian. The current task presents a concrete
   Codex action request for an irreducible login/permission/decision.
5. The existing Automation must require diagnosis, tested repair, pushed
   fingerprint validation and exact continuation before ending. An unresolved
   external evidence gap must state the failed stage and concrete required
   action; unchanged actionable faults must not be described as a quiet success.
6. Close the completed Nov6 item's historical timeout through its original
   fingerprint and reviewed narrow resume, without recapturing or resending.
   Preserve schedule, model, source exclusions, remote sole writer and unrelated
   Yangsheng WIP.
