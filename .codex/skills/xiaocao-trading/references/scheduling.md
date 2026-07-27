# Codex automation scheduling

Read this file only when creating, changing or auditing Xiaocao schedules.

## Intended China-local cadence

- Morning prerecommendation: 09:23 trading weekdays.
- Morning execution: 09:25 trading weekdays.
- Opening dense: 09:35, 09:45, 09:55.
- Sparse monitor: 10:25, 10:55, 13:25, 13:55.
- Risk precheck: 14:25.
- Closing discipline: 14:55.
- EOD: 15:10.
- Weekly deep review: Friday 20:30.

For ordinary recurring Codex cron automations, express China wall-clock time directly with RRULE `BYHOUR` and `BYMINUTE`. Omit `DTSTART` and `TZID`; never convert to UTC. Timezone-specific/DTSTART schedules use a separate reviewed path.

Codex Automation is the scheduling authority. Repository and `~/.codex/automations` TOML files are mirrors/runtime state, not activation proof.

When changing a schedule:

1. Update the existing named automation through the Automation interface/API; do not create a duplicate. A deliberately separate workflow stage such as morning execution has its own stable ID and is not a duplicate.
2. Re-open that automation through the same interface.
3. Compare displayed next-run cadence with the current local clock.
4. Refresh only the matching tracked mirror; preserve unrelated working schedules.

Completion requires the active task to be re-read and its next run verified. A TOML diff or syntactically valid RRULE alone is not completion.
