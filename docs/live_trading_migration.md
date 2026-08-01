# Xiaocao Live Trading Migration

This repo should move by Git plus a small object-storage bundle. Keep source,
contracts, and lightweight specs in Git; keep mutable runtime state, caches,
trained binaries, and large feature corpora outside Git.

## Target Runtime Topology

- `MacBook-Pro-6.local` is the target sole runtime writer for trading
  Automations, mutable paper ledgers, KOL hourly coordination, 灰常亮 writes,
  and enterprise-WeChat Relay notifications.
- The current local machine is the WeChat capture node for operations that
  require its logged-in desktop session. It is also the development and
  Obsidian workstation and a manual cold standby, but it does not run a second
  copy of writer Automations after cutover.
- There is no active-active or automatic failover mode. A manual takeover must
  first prove the old writer is quiescent, transfer a consistent runtime-state
  bundle, switch the existing Codex Automations, and read the resulting task
  ownership and next-run cadence back through the Automation interface.
- Git commit equality and checked-in Automation TOML files prove neither
  runtime-state continuity nor scheduling ownership.

The remote host and its Xiaocao task are registered in Codex. Until
runtime-state restore and authoritative Automation readback have completed,
the current local machine remains the sole writer.

## KOL Cross-Machine Handoff

The WeChat capture node owns capture, compression, large-media validation, and
cloud upload. It then publishes one small immutable handoff containing the
source identity, media metadata and hashes, and the exact private cloud
reference. It does not continue into transcript enrichment, semantic analysis,
灰常亮 publication, notification, or Book KOL-US.

The normal control plane is the registered Codex task on
`MacBook-Pro-6.local`. The local capture Automation sends that task a compact,
credential-free handoff envelope. It sends metadata, hashes, and an exact
private-cloud reference, not source-video bytes or a local path. The remote
task validates the envelope, reconciles its stable `handoff_id`, and owns all
later work. No cross-machine filesystem inbox is required.

Delivery is at least once. The local dispatcher keeps an append-only dispatch
record until the remote task can be read back; the runtime keeps the durable
idempotency and business receipts. An ambiguous send is reconciled by remote
thread identity plus `handoff_id` before any retry, so a retry cannot replay
analysis, publication, notification, or Book KOL-US side effects. If the
remote host is unavailable, capture may retain the pending dispatch locally,
but the local machine does not automatically become a runtime writer.

Do not use the public source repository, 灰常亮, Obsidian/TOS synchronization,
or direct LAN/SSH copy as the normal handoff system of record. The existing
vault staging directory may hold a manually synchronized recovery or audit
copy, but Xiaocao has no runtime dependency on it and never consumes a staged
historical handoff as live work.

The existing implementation already emits a self-hashed metadata-only JSON
and rejects local media paths, but its consumer currently scans a same-machine
directory. Migration therefore requires a Codex-dispatch contract and remote
`handoff_id` receipt reconciliation; it does not require a vault inbox adapter.

## Commit To Git

- Source code under `src/`, `scripts/`, and `kronos_screen/scripts/`.
- Tests under `tests/`.
- Lightweight docs and specs:
  - `README.md`
  - `docs/live_trading_migration.md`
  - `kronos_screen/STATE.md`
  - `kronos_screen/model/spec.json`
- The automation entrypoint:
  - `scripts/auto_daily.sh`

These files define behavior and are reviewable. They should be enough to run
the baseline pipeline and to load restored model/runtime artifacts.

## Put In Object Storage

Use object storage for artifacts that are either mutable account state, large,
binary, or rebuildable from external data:

- Continuous paper account state, if the new machine should continue the same
  simulated account:
  - `output/live/paper_account.json`
  - `output/live/positions.jsonl`
  - `output/live/paper_trades.jsonl`
  - `output/live/paper_holdings.json`
  - `output/live/paper_holdings_snapshots.jsonl`
  - `output/live/alerts.jsonl` if present
- Live signal/evaluation accumulators:
  - `output/live/signal_snapshots.jsonl`
  - `output/live/eod_features.jsonl` if present
  - `output/live/training_rows.parquet` if present
  - `output/live/auto/` if preserving run logs matters
- Kronos overlay model binaries:
  - `kronos_screen/model/K_kronos.joblib`
  - `kronos_screen/model/P_priorday.joblib`
- Repro/retrain corpora, optional for live inference but needed to rebuild the
  scorer:
  - `kronos_screen/data/`
- Warm API cache, optional but useful for replay speed:
  - `output/.cache/xiaocao.db`
  - matching SQLite `*-wal` / `*-shm` files only if the DB is copied while open
- External Kronos source only if the target cannot clone GitHub. Otherwise clone
  `git@github.com:shiyu-coder/Kronos.git` at commit
  `67b630e67f6a18c9e9be918d9b4337c960db1e9a` and set `KRONOS_REPO`.

Do not put `.venv/` in object storage; rebuild it from Python dependencies.
Do not put `xiaocao.yaml` in Git. Treat it as local config/secrets and move it
through the appropriate secret/config channel.

## Restore Sketch

1. Clone this repo on the target machine at `~/coding/xiaocao`. The tracked
   Codex automation TOML files assume this workstation layout and store
   `cwds = ["~/coding/xiaocao"]`.
2. Create a fresh virtualenv and install the package/dependencies.
3. Restore the object-storage bundle paths into the repo root.
4. Clone or restore Kronos and set `KRONOS_REPO=/path/to/Kronos`.
5. Verify:

```bash
.venv/bin/python -m py_compile scripts/live_recommend.py scripts/live_monitor.py
.venv/bin/python scripts/live_monitor.py --execute-sells --no-notify
bash -n scripts/auto_daily.sh
```

6. Restore Codex project config from `.codex/`. The repo copy is canonical;
   expose it to Codex Desktop through the expected global discovery entries:
   - `~/.codex/skills/xiaocao-trading` -> `.codex/skills/xiaocao-trading`
   - `~/.codex/automations/xiaocao-*/automation.toml` ->
     `.codex/automations/xiaocao-*/automation.toml`
   The tracked schedules are:
   - morning prerecommendation: weekdays 09:23 China-local time
   - morning execution: weekdays 09:25 China-local time
   - eod: `bash scripts/auto_daily.sh eod`, weekdays 15:10 Asia/Shanghai
   - intraday monitor: `.venv/bin/python scripts/live_monitor.py --execute-sells`,
     opening dense, sparse daytime, and closing-discipline passes.
   - weekly deep review: `bash scripts/auto_daily.sh weekly`, Fridays 20:30
     Asia/Shanghai; non-trading Fridays still produce the latest-week review plan.
   - KOL hourly coordination: every hour from 07:00 through 23:00 China-local
     time; the coordinator consumes lightweight handoffs and never downloads
     source-video bytes.
