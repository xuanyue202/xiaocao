# Xiaocao capture adapter

Status: wontfix

Implement an append-only job ledger and a client for the existing local sniffer.
Support arm, poll, download, and status operations, with baseline-aware detection
so an old capture cannot be mistaken for the live acceptance sample.

## Comments

- 2026-07-19: Live acceptance will use a Xiaocao item after the current baseline
  (`2026-07-01`), opened by the user after the sniffer reports ready.
- 2026-07-19: Accepted with the unseen `20260716 大师班专场(晚17：30开播)`
  capture. A first adapter version bypassed inline compression; corrected to
  the proven `type=live_capture`, `compress=true` contract and added a forced
  retry path.
- 2026-07-19: Reclassified after product slicing review. This file describes an
  exploratory thin interface and cannot be accepted independently as user
  value. Its code and evidence are inputs to the vertical Xiaocao-live issue;
  no separate adapter delivery or acceptance remains.
