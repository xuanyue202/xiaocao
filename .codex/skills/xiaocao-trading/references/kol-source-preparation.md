# Source analysis before the trading window

The remote writer prepares this handoff per published object, before advancing
to the next object. `DailyPublicationPipeline` emits
`daily_trading_source_preparation_input_required` after the reader/Book terminals;
viewpoint maintenance uses the same boundary. Keep that stdin open. An existing
completed handoff receipt is read-only reuse. Empty/unchanged slots do no work.

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
6. Return one JSON line to the waiting runner:
   `{"context_path":"<reviewed-context.json>","preparation_path":"<published-packet.json>"}`.
   It verifies the exact report/content/manifest and packet bindings and persists
   a handoff receipt before proceeding. Coverage limits remain explicit; a source
   handoff does not certify complete or fresh trading coverage. If interrupted,
   use `kol_daily.py prepare-trading-sources --publication-key <exact-key>` under
   the existing writer's ownership. This resumes only the pending handoff, with
   no report, reminder, Book or ACK replay. The next authorized full sweep drains
   persisted pending handoffs before mailbox discovery.

At 09:00 the trading task obtains a cache-only context with
`--history-fresh-through <today>T11:30:00+08:00` and reads the matching preparation
packet. This checks the actual opening horizon against the unchanged 24-hour
history TTL, without making the evidence as-of future-dated. Refresh returned
exact IDs in bounded batches with the same horizon until
`registered_longitudinal_complete` is true; retain unresolved gaps. A
`source_revalidation_required` result exposes `reusable_path`: refresh the exact
missing manifests, then reuse matching analysis; absence of cached records is
not a claim that the underlying views changed. Near 09:22 refresh selected manifests and read only
new or changed bodies. Formal publication keeps its existing freshness and
coverage checks. Status invalidates the match for changed reports, evaluations or
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

For morning consumption, distinguish source reuse from current policy validity.
Run status with `--ready-through <today>T11:30:00+08:00 --opening-draft <path>`.
`source_analysis_reusable` does not imply `current_policy_reusable`.
Complete the conditional draft before 09:20: `source_fingerprint`,
`analyst_agent_id`, `decision_template` with reasoned `buy_scale`, `rationale`,
`invalidation_conditions`, and explicit `opening_scenarios`. A null skeleton is
unfinished. The independent parent adds `source_review` containing
`status=source_reasoning_reviewed`, its different `reviewer_agent_id`, and
`draft_sha256` over the entire draft excluding `source_review`.
This source review grants no trading authority. The opening request still needs
current applicability review and normal formal publication. If adequate current
facts already support a session-valid decision, publish it early with a justified
valid_until; never manufacture a neutral decision to fill the slot.
At freeze reuse the reviewed conditional draft and verify only changed inputs.

The approved packet is the reusable semantic boundary for every daytime
consumer. Downstream live, paper, sparse and audit tasks verify its context,
source and review hashes, then read only newly approved changes plus their own
current facts. They do not reopen all unchanged report bodies or independently
recreate source notes. If the packet is absent or requires source analysis, the
consumer degrades to its deterministic baseline and leaves source work to this
owner. Formal decision publication still uses the complete current context and
remote report/manifest verification; packet reuse does not weaken source
identity checks.
