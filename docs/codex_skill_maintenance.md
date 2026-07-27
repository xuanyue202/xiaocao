# Codex Project Maintenance

The repo is the source of truth for Xiaocao Codex configuration.

## Skill

Canonical files:

- `.codex/skills/xiaocao-trading/SKILL.md`
- `.codex/skills/xiaocao-trading/references/*.md` — branch-specific runbooks loaded through progressive disclosure
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

When changing Xiaocao behavior, edit the root repo source first. For Codex
instructions, keep `SKILL.md` limited to common boundaries and routing; edit the
single owning file under `references/` for branch-specific behavior. Do not
duplicate `docs/OPERATING_CONTRACT.md` semantics in the skill, and do not
hand-edit `~/.codex/skills/xiaocao-trading`; regenerate or relink it from the
repo.

## Automations

Codex Automation is the runtime authority for scheduled tasks. Create or update
an active task through the Codex Automation tool/API; editing a TOML file alone
does not prove that the scheduler accepted or activated the change.

Tracked automation mirrors live in:

- `.codex/automations/*/automation.toml`

These tracked files are reviewable mirrors for the Xiaocao workstation layout,
not the runtime authority or a machine-independent template. They intentionally assume the repo is
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

Do not rely on the global `automation.toml` files being symlinks: Codex Desktop
may materialize them as regular files when an automation is updated through the
API. The global automation directories also hold app runtime state such as
`memory.md`, which is intentionally not tracked.

Project `.codex/automations` by itself is not a Codex Desktop activation path.
After every schedule change, update the existing automation through the Codex
Automation tool/API, view it again through that interface, and then refresh the
tracked mirror. Never infer activation from a file diff alone.

For ordinary recurring cron tasks, pass a DTSTART-free RRULE containing the
intended local `BYHOUR` and `BYMINUTE`. Do not add `DTSTART`/`TZID` and do not
convert local time to UTC. The Automation API explicitly treats requested times
in the user's locale; DTSTART-anchored or timezone-specific schedules use a
separate reviewed path. Validate the UI's displayed next-run interval against
the current local clock after saving, because a syntactically valid RRULE can
still enter the wrong product path.

## End-To-End Impact Map

The live Codex loop has several layers:

1. Codex Automation is the scheduling authority. Its local state may be
   materialized under `~/.codex/automations/xiaocao-*`, but those files are an
   implementation detail, not the supported update interface.
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
- Automation cadence or prompt changes must be applied through the Codex
  Automation tool/API, then mirrored in `.codex/automations/*`; they may also
  need a matching `SKILL.md` workflow section.
- Safety or paper/real-capital behavior changes require tests plus updates to
  `docs/OPERATING_CONTRACT.md` and the skill if the agent-facing behavior
  changes.

## Claude Code

Claude Code project support is intentionally thin and symlink-based:

- `CLAUDE.md` -> `AGENTS.md`
- `.claude/skills` -> `../.codex/skills`

This keeps Claude and Codex on the same contributor guide and skill source. Do
not create a second Claude-specific copy of the Xiaocao skill. Local Claude state
such as `.claude/settings.local.json` and `.claude/scheduled_tasks.lock` remains
ignored.

Do not use project `.agents` as the primary Xiaocao agent config location. This
environment can discover global `/Users/bytedance/.agents/skills`, but
project-local `.agents` is not equivalent to the Codex Desktop or Claude Code
project discovery paths above.
