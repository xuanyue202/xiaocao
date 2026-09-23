# Codex automation scheduling

Read this file only when creating, changing or auditing Xiaocao schedules.

## Intended China-local cadence

- Morning prerecommendation: 09:23 trading weekdays.
- Book-B Founder live morning: 09:00 trading weekdays; independent of paper execution.
- Morning execution: 09:25 trading weekdays.
- Opening dense: 09:35, 09:45, 09:55.
- Sparse monitor: 10:25, 10:55, 13:25, 13:55 only. On the `/Users/xuanyue202`
  remote host, the remote writer is the sole KOL write ingress; cross-machine
  capture is only upstream capsule input and is never created or run there. The
  next sparse checkpoint consumes completed publication receipts. See
  `kol-trading-judgment.md` for claim, acknowledgement and owner-recovery rules.
  It never acquires 14:45 authority.
- Risk precheck: 14:25.
- Closing discipline: 14:45 (automation pre-arms at 14:41).
- EOD: 15:10.
- Weekly deep review: Friday 20:30.

## Daytime ownership matrix

| Stage | Sole business responsibility | KOL/source responsibility |
|---|---|---|
| Remote writer | Atomically publish reports, viewpoints, evaluations and relations | Sole full reader for new/changed report bodies; LiangHui is the semantic SSOT |
| 09:00 live morning | One native live runner, authentication probe, live current-applicability decision | Consume the compact viewpoint projection; never redo unchanged source semantics |
| 09:23 prerecommendation | Produce the immutable recommendation/freeze and exit | No KOL semantic work |
| 09:25 paper execution | Keep the original paper shell alive and complete paper current applicability | Consume the compact viewpoint projection; never redo unchanged source semantics or live work |
| 09:35/09:45/09:55 opening | Protective paper/live checkpoints only | Consume an already-valid decision only; no context, model or publication work |
| 10:25/10:55/13:25/13:55 sparse | One owner-bound tick claim and paper/live checkpoints | Only the claim owner may adapt the compact projection when its fingerprint changed or the decision expired |
| 14:25 precheck | Protective paper/live checkpoints only | Consume an already-valid decision only; no context, model or publication work |
| 14:45 closing | Time-critical live close first, then paper close | Consume an already-valid decision only; no context, model or publication work |
| 15:10 EOD | Paper/live reconciliation, settlement and receipt audit | Receipt/hash linkage only; no report-body read, semantic dispatch or decision publication |

Codex scheduling does not substitute for these durable business owners. Every
repeated slot must either have a deterministic no-op/claim gate or be unable to
start the expensive supporting workflow by contract. A task ends when its own
stage is terminal; it does not stay alive to perform work owned by a later stage.

For ordinary recurring Codex cron automations, express China wall-clock time directly with RRULE `BYHOUR` and `BYMINUTE`. Omit `DTSTART` and `TZID`; never convert to UTC. Timezone-specific/DTSTART schedules use a separate reviewed path.

Codex Automation is the scheduling authority. Repository and `~/.codex/automations` TOML files are mirrors/runtime state, not activation proof.

When changing a schedule:

1. Update the existing named automation through the Automation interface/API; do not create a duplicate. A deliberately separate workflow stage such as morning execution has its own stable ID and is not a duplicate.
2. Re-open that automation through the same interface.
3. Compare displayed next-run cadence with the current local clock.
4. Refresh only the matching tracked mirror; preserve unrelated working schedules.

Completion requires the active task to be re-read and its next run verified. A TOML diff or syntactically valid RRULE alone is not completion.
