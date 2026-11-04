# Archived Xiaocao fixed-room workflow — 2026-11-04

Archived by the human's instruction on 2026-11-04. The current primary acquisition
route is [recorded course](../recorded-course-recovery.md). This archive is a
rollback reference, not an automatic fallback when a recording is unpublished.

The old implementation and receipts remain intact. Reference baseline:
`82cd1d278f48820584317ae7be331ee7ef1a7b38` in the Xiaocao repository, including
`src/xiaocao/kol/xiaocao_wechat.py::_check_human_playback` and
[human-assisted playback](../human-assisted-playback.md),
[local native capture](../hourly-local-native-capture.md),
[native-share bridge](../native-share-bridge.md).
The git baseline retains the complete prior files without copying mutable runtime
state or credentials into the archive.

Old route: cached original → saved exact Caoliao mini-program target → one
receipted entry for the collaboration session → human WeChat Open/Allow/play →
HTTP observation → exact finite media → compression/cloud/mailbox/readback.
Human owns every WeChat action. A historical launch does not prove a current
window, and reused live IDs cannot establish a recording's date or file.

Rollback requires a new direct human instruction, reconciliation of active
capture/download/upload claims and proxy ownership, then explicitly changing
`replay_catalog.acquisition_mode` from `recorded_course` to `native_human` in the
private descriptor. Keep the catalogue descriptor, old IDs/claims/receipts,
readiness gates, human exclusions, schedule and remote single-writer authority.
Do not reset a ledger or launch a second capture to roll back. Update the active
Automation through its API and read it back; a file edit alone is not activation.
