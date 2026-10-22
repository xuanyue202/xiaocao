from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.app_simulation
ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_ID = "xiaocao-intraday-monitor-1455"


@pytest.fixture
def launcher(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    path = scripts / "book_b_live_closing_startup.sh"
    path.write_bytes((ROOT / "scripts" / path.name).read_bytes())
    command_bin = tmp_path / "command-bin"
    command_bin.mkdir()
    for name in ("sed", "rg"):
        command = command_bin / name
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o755)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with Path('calls.jsonl').open('a') as stream:\n"
        "    stream.write(json.dumps({'args':sys.argv[1:], "
        "'automation':os.environ.get('CODEX_AUTOMATION_ID'), "
        "'thread':os.environ.get('CODEX_THREAD_ID')})+'\\n')\n"
        "branch = ('GATE' if sys.argv[1] == '-m' else "
        "'PAPER' if sys.argv[1].endswith('/live_monitor.py') else 'RESEARCH' if sys.argv[1].endswith('/research_book_b_forward.py') else 'APP')\n"
        "sys.exit(int(os.environ.get(branch+'_EXIT', '0')))\n"
    )
    python.chmod(0o755)
    return path


def run_launcher(launcher: Path, **overrides: str) -> subprocess.CompletedProcess:
    root = launcher.parent.parent
    return subprocess.run(
        ["bash", str(launcher)], capture_output=True, text=True, check=False,
        timeout=5,
        env={**os.environ, "CODEX_AUTOMATION_ID": AUTOMATION_ID,
             "CODEX_THREAD_ID": "original-runtime-thread",
             "PATH": str(root / "command-bin") + os.pathsep + os.environ["PATH"],
             **overrides},
    )


@pytest.mark.parametrize(("app_exit", "paper_exit", "expected"), [
    (0, 0, 0), (2, 0, 2), (0, 3, 3), (2, 3, 2),
])
def test_closing_retains_app_then_paper_even_when_either_branch_fails(
    launcher: Path, app_exit: int, paper_exit: int, expected: int,
) -> None:
    result = run_launcher(launcher, APP_EXIT=str(app_exit), PAPER_EXIT=str(paper_exit), RESEARCH_EXIT="9")
    assert result.returncode == expected
    rows = [json.loads(line) for line in
            (launcher.parent.parent / "calls.jsonl").read_text().splitlines()]
    assert [row["args"] for row in rows] == [
        ["-m", "xiaocao.live.closing_startup"],
        ["scripts/book_b_live_intraday.py", "--date", "today", "--phase", "closing", "--execute-sells"],
        ["scripts/live_monitor.py", "--execute-sells"],
        ["scripts/research_book_b_forward.py", "--phase", "monitor"],
    ]
    assert all(row["automation"] == AUTOMATION_ID for row in rows)
    assert all(row["thread"] == "original-runtime-thread" for row in rows)


@pytest.mark.parametrize(("automation", "thread"), [
    ("xiaocao-daily-eod", "original-runtime-thread"), ("", "original-runtime-thread"),
    (AUTOMATION_ID, ""), (AUTOMATION_ID, " \t "),
])
def test_closing_rejects_invalid_identity_before_gate_or_business(
    launcher: Path, automation: str, thread: str,
) -> None:
    result = run_launcher(launcher, CODEX_AUTOMATION_ID=automation, CODEX_THREAD_ID=thread)
    assert result.returncode == 78
    assert not (launcher.parent.parent / "calls.jsonl").exists()


def test_closing_gate_failure_prevents_both_branches(launcher: Path) -> None:
    result = run_launcher(launcher, GATE_EXIT="4")
    assert result.returncode == 4
    rows = [json.loads(line) for line in
            (launcher.parent.parent / "calls.jsonl").read_text().splitlines()]
    assert [row["args"] for row in rows] == [["-m", "xiaocao.live.closing_startup"]]
