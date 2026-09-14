# Source analysis before the trading window

The remote writer prepares this handoff after a new published report or
viewpoint-maintenance receipt reaches its existing terminal gate. Do not run a
second sweep. Empty/unchanged publication slots do no preparation work.

1. Build `kol_trading_context.py context --summary` while there is time outside
   the opening window. Resolve required registered manifest gaps by exact ID;
   retain the selected complete bodies and context file. Historical cache work
   belongs here, not at 09:25. A failed coverage check remains explicit.
2. Run `kol_trading_preparation.py status --context <context.json>`. Reuse a
   matching packet; otherwise have the configured semantic analyst prepare
   source notes from complete relevant sources. Reuse unchanged analysis and
   fully read new/changed material. Follow `kol-trading-judgment.md` for model
   dispatch evidence and independent review. Record both source occurrence and
   publication times, conditions, exceptions, counterevidence and author roles.
3. Write notes with `schema_version=kol-source-preparation.v1`, `authority=0`,
   `analyst_agent_id`, `context_sha256`, explicit `coverage_limits`, and
   `sources`: exactly one row for each loaded report, with `report_id` and
   nonempty `analysis`, `conditions`, `counterevidence`, `time_scope` strings.
   Preserve all material source reasoning; this is a reusable analysis, not
   an abbreviated substitute for full new source reading.
4. The independent parent reads complete new/changed evidence and reviews the
   notes. Its review records `reviewer_agent_id`, `reviewed_at` (UTC ISO),
   `notes_sha256` (publication canonical SHA256), `status=approved`, and true
   `source_fidelity`, `conditions_preserved`, `counterevidence_checked`.
5. Publish through `PYTHONPATH=src .venv/bin/python scripts/kol_trading_preparation.py
   publish --context <context.json> --notes <notes.json> --review <review.json>`;
   then read `status` with the same context and verify the immutable packet path.

At 09:00 the trading task obtains a cache-only context first and reads the
matching preparation packet. It resolves missing/changed material and freshness
early. Status invalidates the match for changed reports, evaluations or
relations. Packet review does not mean every historical body was loaded/read,
nor does it justify `--since-context` against an unread full context.

At 09:25 only the candidate/account/current-fact adaptation remains. Supply the
prepared source conditions to Astra with the exact request and current facts;
the parent independently checks this adaptation and publishes through the
existing `kol_trading_decision.py` interface. An existing still-valid applicable
decision may be reused directly. Source packets never enter the decision store,
assert future opening conditions, override qualification, or authorize orders.
Incomplete source coverage can be documented in a preparation packet but cannot
bypass the existing formal decision publication checks.
