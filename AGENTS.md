# Repository Guidelines

Xiaocao is a Python CLI and automation toolkit for A-share data, strategy screening, reports, Kronos recommendations, and paper-trading surveillance.

## Project Structure & Module Organization

Python uses a `src/` layout. Core code lives in `src/xiaocao/`; CLI entrypoints are `cli.py` and `__main__.py`. Strategy logic is under `strategy/`, API under `api/`, sources under `datasource/`, and live safety gates under `live/`.

Operational scripts live in `scripts/`; live automation centers on `auto_daily.sh`, `live_recommend.py`, and `live_monitor.py`. Kronos tooling lives in `kronos_screen/`. Tests are in `tests/`, with API e2e tests in `tests/e2e/`. Codex config is in `.codex/`; generated bundles and `output/` artifacts are not source.

## Build, Test, and Development Commands

- `PYTHONPATH=src python3 -m xiaocao --help`: run the CLI from source.
- `python3 -m pip install -e .`: install the package and `xiaocao` console script.
- `PYTHONPATH=src python3 -m pytest -q`: run the standard test suite.
- `PYTHONPATH=src python3 -m pytest tests/e2e -q`: run live API tests.
- `bash -n scripts/auto_daily.sh`: syntax-check automation shell.
- `python3 scripts/package_xiaocao_skill.py`: refresh the Codex skill runtime and symlink install.

## Codex Skill, CLI & Automation Flow

Treat repo code as the behavioral source, `.codex/skills/xiaocao-trading/SKILL.md` as agent instructions, and `.codex/automations/*/automation.toml` as schedules. Codex discovers `~/.codex` symlinks; do not edit discovery copies directly.

End-to-end path: automation prompt -> `xiaocao-trading` skill -> runtime bundle -> CLI/scripts -> `output/live/*` artifacts -> summary. CLI output, live behavior, account files, or Kronos fields require matching skill and automation updates.

## Coding Style & Naming Conventions

Use 4-space indentation and type hints where they clarify interfaces. Prefer small, testable functions and explicit normalization. Modules and tests use `snake_case`; CLI subcommands should stay descriptive. Keep runtime state and generated reports under `output/`.

## Testing Guidelines

Pytest uses `pytest.ini`, `tests` as the default path, and `e2e` as the live API marker. Name tests `test_*.py`. For live trading changes, cover normal flow and fail-closed safety, especially paper vs real-capital paths.

## Commit & Pull Request Guidelines

Recent commits use concise imperative summaries, sometimes with a priority prefix such as `P0:`. Examples: `Add live trading automation migration support`, `Improve paper trading execution controls`. PRs should describe changes, list validation, call out live/API impact, and mention excluded artifacts.

## Security & Configuration Tips

Do not commit `xiaocao.yaml`, account state, caches, binaries, or signing secrets. Real-capital paths must go through `src/xiaocao/live/safety.py`; automations should remain paper/sensor safe unless explicitly authorized by the two-key flow.
