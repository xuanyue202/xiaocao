from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.app_simulation
ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_ID = "xiaocao-intraday-risk-precheck-1425"


@pytest.fixture
def startup(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    launcher = scripts / "book_b_live_precheck_startup.sh"
    launcher.write_bytes((ROOT / "scripts" / launcher.name).read_bytes())
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with Path('calls.jsonl').open('a') as stream:\n"
        "    stream.write(json.dumps({'args':sys.argv[1:], 'automation':os.environ.get('CODEX_AUTOMATION_ID'), "
        "'thread':os.environ.get('CODEX_THREAD_ID')})+'\\n')\n"
        "branch = 'PAPER' if sys.argv[1].endswith('/live_monitor.py') else 'APP'\n"
        "sys.exit(int(os.environ.get(branch+'_EXIT', '0')))\n"
    )
    python.chmod(0o755)
    return launcher


@pytest.mark.parametrize(("paper_exit", "app_exit", "expected"), [
    (0, 0, 0), (2, 0, 2), (0, 2, 2), (3, 2, 3),
])
def test_precheck_retains_both_branches_without_model_handoff(
    startup: Path, paper_exit: int, app_exit: int, expected: int,
) -> None:
    result = subprocess.run(
        ["bash", str(startup)], capture_output=True, text=True, check=False,
        env={**os.environ, "CODEX_AUTOMATION_ID": AUTOMATION_ID,
             "CODEX_THREAD_ID": "original-runtime-thread", "PAPER_EXIT": str(paper_exit),
             "APP_EXIT": str(app_exit)},
    )
    assert result.returncode == expected
    rows = [json.loads(line) for line in (startup.parent.parent / "calls.jsonl").read_text().splitlines()]
    assert [row["args"] for row in rows] == [
        ["scripts/live_monitor.py", "--execute-sells"],
        ["scripts/book_b_live_intraday.py", "--date", "today", "--phase", "precheck", "--execute-sells"],
    ]
    assert all(row["automation"] == AUTOMATION_ID for row in rows)
    assert all(row["thread"] == "original-runtime-thread" for row in rows)


@pytest.mark.parametrize(("automation", "thread"), [
    ("xiaocao-daily-eod", "original-runtime-thread"), ("", "original-runtime-thread"),
    (AUTOMATION_ID, ""), (AUTOMATION_ID, " \t "),
])
def test_precheck_rejects_mismatched_or_missing_identity_before_business(
    startup: Path, automation: str, thread: str,
) -> None:
    result = subprocess.run(
        ["bash", str(startup)], capture_output=True, text=True, check=False,
        env={**os.environ, "CODEX_AUTOMATION_ID": automation, "CODEX_THREAD_ID": thread},
    )
    assert result.returncode == 78
    assert not (startup.parent.parent / "calls.jsonl").exists()
