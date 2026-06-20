# Xiaocao Live Trading Migration

This repo should move by Git plus a small object-storage bundle. Keep source,
contracts, and lightweight specs in Git; keep mutable runtime state, caches,
trained binaries, and large feature corpora outside Git.

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
   - morning: `bash scripts/auto_daily.sh morning`, weekdays 09:23 Asia/Shanghai
   - eod: `bash scripts/auto_daily.sh eod`, weekdays 15:10 Asia/Shanghai
   - intraday monitor: `.venv/bin/python scripts/live_monitor.py --execute-sells`,
     opening dense, sparse daytime, and closing-discipline passes.
