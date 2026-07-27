---
status: accepted
---

# Run one hourly KOL coordinator during the daytime window

Ticket 07 uses one short-lived Codex Automation sweep each hour from 07:00 through 23:00 Beijing time and remains silent overnight; the 07:00 sweep consumes accumulated night updates. Backlogged publication events remain independent, are processed in decision-priority order, and each alert-eligible event may send its own Enterprise WeChat reminder rather than being merged into a batch digest. Normal no-update runs and self-recoverable transient failures are silent; only a blocker that truly requires user action creates one concise operational reminder, which is not repeated until the blocker changes. Append-only state and due timestamps make each invocation resumable, while Xiaocao's user-present broadband capture stays outside this schedule. This trades a maximum one-hour continuation delay for substantially lower resource use and avoids overlapping source-specific schedules or an always-running process.
