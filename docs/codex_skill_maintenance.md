# Codex Project Maintenance

The repo is the source of truth for Xiaocao Codex configuration.

## Skill

Canonical files:

- `.codex/skills/xiaocao-trading/SKILL.md`
- `.codex/skills/xiaocao-trading/agents/openai.yaml`
- root project code copied into the generated runtime bundle by
  `scripts/package_xiaocao_skill.py`

Generated or installed copies:

- `.codex/skills/xiaocao-trading/assets/xiaocao-runtime/` is generated from
  this checkout and is not tracked.
- `~/.codex/skills/xiaocao-trading/` is only the local Codex discovery entry.
  By default it is a symlink to the repo skill, not a separately maintained
  copy.
- `output/xiaocao-trading-skill.zip` and `.sha256` are package artifacts.

Refresh the repo runtime, expose it to Codex through the symlink, smoke-test it,
and build the zip:

```bash
python3 scripts/package_xiaocao_skill.py
```

Refresh and package without touching the local Codex install:

```bash
python3 scripts/package_xiaocao_skill.py --no-install
```

After a refresh, the installed entry should resolve to the repo skill:

```bash
readlink ~/.codex/skills/xiaocao-trading
```

When changing Xiaocao behavior, edit the root repo source first. When changing
Codex instructions, edit `.codex/skills/xiaocao-trading/SKILL.md` first. Do not
hand-edit `~/.codex/skills/xiaocao-trading`; regenerate or relink it from the
repo.

## Automations

Canonical automation configs live in:

- `.codex/automations/*/automation.toml`

These tracked files are the canonical config for the Xiaocao workstation layout,
not a machine-independent template. They intentionally assume the repo is
restored at:

```text
~/coding/xiaocao
```

The checked-in TOML stores `cwds = ["~/coding/xiaocao"]`. Codex Desktop accepts
and renders this path through the automation API, so keep future restores on the
same home-relative layout rather than hand-editing machine-specific absolute
paths.

Codex Desktop currently discovers active cron automations through:

- `~/.codex/automations/*/automation.toml`

For Xiaocao, the global `automation.toml` files are symlinks back to the repo
canonical files. The global automation directories still hold app runtime state
such as `memory.md`, which is intentionally not tracked.

Project `.codex/automations` by itself is not a guaranteed Codex Desktop
discovery location. Keep the global symlink entries in place unless the app
adds first-class project automation discovery.

## End-To-End Impact Map

The live Codex loop has several layers:

1. `~/.codex/automations/xiaocao-*/automation.toml` is the Codex Desktop
   discovery entry. For Xiaocao, each `automation.toml` is a symlink to the repo
   file under `.codex/automations/`.
2. The automation prompt asks Codex to use the local `xiaocao-trading` skill and
   run one workflow: morning, intraday monitor, closing discipline, or EOD.
3. `~/.codex/skills/xiaocao-trading` is a symlink to
   `.codex/skills/xiaocao-trading`. The skill tells the agent which command to
   run, which output files to inspect, what counts as an anomaly, and how to
   summarize the result.
4. `scripts/package_xiaocao_skill.py` refreshes
   `.codex/skills/xiaocao-trading/assets/xiaocao-runtime/` from repo source.
   The runtime is the self-contained fallback used when no full checkout is
   available.
5. The actual project checkout remains the preferred execution environment for
   automations because the automation `cwds` point at the restored checkout
   under `~/coding/xiaocao`.

Before changing any layer, check the downstream contract:

- CLI or script output changes may require updates to `SKILL.md` parsing and
  summary instructions.
- New live artifacts under `output/live/` may require `.gitignore`,
  migration-doc, and automation summary updates.
- Automation cadence or prompt changes belong in `.codex/automations/*` and may
  need a matching `SKILL.md` workflow section.
- Safety or paper/real-capital behavior changes require tests plus updates to
  `docs/OPERATING_CONTRACT.md` and the skill if the agent-facing behavior
  changes.

## `.agents`

Do not use project `.agents` as the primary Xiaocao Codex config location.
This environment can discover global `/Users/bytedance/.agents/skills`, but
project-local `.agents` is not equivalent to the Codex Desktop skill and
automation discovery paths above.
