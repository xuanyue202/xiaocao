# Independent Xiaocao video gap watchdog

Use for the human-requested independent missing-video monitor. It must remain
readable when the capture source is busy or repairing an old item:

```bash
PYTHONPATH=src .venv/bin/python scripts/kol_video_gap_watchdog.py
```

This command reads the exchange calendar, subscription/capture/event ledgers and
the exact registered contact's current cached `wechat-cli history`. It paginates
the bounded date range and treats unavailable/incomplete evidence as `degraded`,
never `no_update`. Calendar dates are exchange-backed, not inferred weekdays;
the video day completes at22:00 Asia/Shanghai. Two completed trading days with
zero media receipts triggers diagnosis unless acquisition has already recovered
today. Count receipt acquisition by `media_validated.updated_at`, and expose
original-course-date coverage separately. An announced original older than6hours
without a recorded Handoff also triggers. The diagnostic window starts after the
preceding third trading day, including intervening weekend/holiday backlog;
recently changed older items remain visible without reviving all legacy history.
Explicit user exclusions remain excluded; they never become completion.

Separate acquisition, local Handoff and remote ACK: a complete media receipt can
exist while upload/mailbox is unfinished. ACK is recorded only from the matching
local mailbox ACK event with the same handoff/content binding; absent evidence
is unknown. The report exposes original identity, capture ID,
publication time and concrete current stage. These are recorded local evidence,
not a new authoritative cloud/mailbox acceptance or proof of provider readiness.

The watchdog performs no native/browser action, PAC change, source execution,
claim reset, new capture, upload or mailbox send. It never waits on the source
slot or enumerates Codex tasks/processes. It writes only its independent status
and notification fingerprint plus normal API cache, with no lock held across
history/API waits. Inspect its JSON `status`, `gaps`, `history_checked` and
`notify`; a nonzero exit indicates an actionable gap or degraded evidence.

On `notify=true`, report the new/changed gap, recovery or irreducible user action
in the existing chat. Diagnose exact originals and existing claims before any
same-item repair; reuse existing human authorization. Remain quiet when
`notify=false`; do not send repeated unchanged alerts. Never turn this watchdog
into another capture gate, a remote writer or native protection reproduction.
