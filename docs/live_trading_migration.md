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
cloud upload. It also owns exact-publisher discovery for the registered
`刘少狙击营` and `A也叫艾利克斯` WeChat official-account KOL sources. It then
publishes one small immutable handoff containing the
source identity, media metadata and hashes, the exact private cloud reference,
and a portable `video_ready` projection of that Netdisk job ledger. The
projection and the complete capsule have separate SHA-256 bindings. It does
not contain a local path, browser evidence, credentials, or source-video bytes,
and the capture node does not continue into transcript enrichment, semantic
analysis, 灰常亮 publication, notification, or Book KOL-US.

An official-account handoff is a separate small
`wechat_official_article` capsule: publisher, stable article identity, public
URL, timestamps, and hashes. It contains no summary evidence, article body,
media bytes, credentials, or local path. The remote task imports it
idempotently, then OpenCLI materializes the full Markdown and images. Image
information is written back as SHA-bound Markdown before semantic analysis.

The normal control plane is the registered Codex task on
`MacBook-Pro-6.local`. The local capture Automation sends that task a compact,
credential-free handoff envelope. It sends metadata, hashes, and an exact
private-cloud reference and the job-ledger projection, not source-video bytes
or a local path. The remote task validates both hashes and all cross-field
bindings, merges the projection into its append-only Netdisk ledger by stable
`handoff_id`, and owns all later work. A replay produces no second ledger row.
Imported browser control is deliberately blocked: the remote OpenCLI session
must independently scan the complete target directory and find exactly one
matching file before any transcript-side mutation. No cross-machine filesystem
inbox is required.

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

The implementation emits the portable v2 capsule, imports its cloud-ready
ledger projection idempotently, and makes the coordinator import it before
reading job status. The remaining cross-machine responsibility is delivery and
readback through the registered Codex task; it does not require a vault inbox
adapter.

## Remote KOL Runtime Prerequisites

The remote KOL coordinator is not ready merely because the repository is
current. Before moving the hourly Automation, verify all of the following on
`MacBook-Pro-6.local` without printing credential values:

- A repository `.venv` using a supported Python and importing the core runtime
  dependencies (`requests`, `yaml`, and `rfc8785`).
- Node.js, npm, and a directly installed pinned OpenCLI command. The repository
  fallback is `npx --yes @jackwener/opencli@1.8.6`, but an unattended hourly
  runtime must install `@jackwener/opencli@1.8.6` directly and verify its
  version instead of depending on an on-demand network download.
- Microsoft Edge with the compatible OpenCLI Browser Bridge, plus a proven
  logged-in `xiaocao-lv-subscription` session that can read both the configured
  Lv Xiaotong share and the private `/课程/路西法全套` directory. Browser
  installation alone is not session proof.
- macOS Swift/Vision support for the small-image OCR path. `ffmpeg`, `ffprobe`,
  the WeChat sniffer, and the Xiaocao large-media capture binary remain local
  broadband-worker dependencies and are not required by the normal remote
  coordinator path.
- A private `xiaocao.yaml` containing the Lv Xiaotong subscription reference,
  a mode-0600 family-authenticated `.codex/config.toml` for the 灰常亮 MCP, and
  the Enterprise WeChat Relay configuration. Transfer or configure these
  through an approved secret-bearing path; never put their values in Git or a
  Codex task prompt.
- The authoritative lightweight KOL manifests, unfinished-item state,
  publication/notification receipts, and Book KOL-US ledger under
  `output/live/kol_daily`, `kol_intelligence`, `kol_lv_subscription`,
  `kol_subscription_videos`, and `kol_xiaocao_live`. A fresh empty directory
  is not a safe continuation of the current writer.

At initial cutover, transfer one consistent snapshot of the complete
authoritative lightweight KOL state listed above, including Book KOL-US and
publication/notification receipts. That is continuity of the existing writer,
not a recurring handoff format. After cutover, each incoming Codex task only
needs to materialize its validated v2 capsule; the coordinator bootstraps that
job from the embedded projection before consuming it. It must never replace
the global ledgers with a per-job capsule.

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
