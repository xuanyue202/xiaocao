# Reuse proved evidence in Book B SQLite accounting

Status: accepted, 2026-09-29 user approval.

Dynamic capital needs an auditable distinction between contributed capital,
owned inventory cost and profit. Separate JSON balances and repeated replay
logic do not provide one transactional financial journal. Use standard-library
SQLite for balanced integer-cent postings and immutable valuation observations,
with the existing account writer lock and original intent/fill/funding validators.
One replay serves lifecycle, buying-power preflight and risk consumers.

Keep the original JSON/JSONL order claims and proved source facts as evidence;
their producers and exact-once execution authority stay intact. SQLite is the
financial posting authority, with unique source keys, append-only guards,
hash-chain verification, CSV statement export and verified online backups.
Unclassified cash differences stay pending instead of becoming capital. This
avoids an ORM, a second order engine, or a wholesale paper-ledger migration.
