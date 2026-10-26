"""Capture termination of the three prescribed post-EOD commands, once each."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo

from xiaocao.live.runtime_evidence import stream_process
from xiaocao.research.eod_feedback import AUTOMATION_ID, canonical, evidence_ref

COMMANDS = {
    "statement": ["scripts/book_b_accounting.py", "statement"],
    "research": ["scripts/research_book_b_forward.py", "--phase", "eod"],
    "feedback": ["scripts/kol_trading_decision.py", "feedback"],
}


def run_step(root: Path, step: str, *, env: Mapping[str, str],
             runner: Callable = stream_process, clock: Callable = lambda: datetime.now(ZoneInfo("Asia/Shanghai"))) -> dict:
    """A surviving claim forbids a replacement child after failure or interruption."""
    started = clock()
    if (step not in COMMANDS or env.get("CODEX_AUTOMATION_ID") != AUTOMATION_ID
            or not env.get("CODEX_THREAD_ID") or started.hour < 15):
        raise ValueError("EOD_POST_BUSINESS_IDENTITY_OR_WINDOW_INVALID")
    day = started.date().isoformat()
    directory = root / "output/live/eod_post_business" / AUTOMATION_ID / day / step
    directory.mkdir(parents=True, exist_ok=True)
    base = {"schema_version": 1, "automation_id": AUTOMATION_ID, "thread_id": env["CODEX_THREAD_ID"],
            "date": day, "step": step, "command": COMMANDS[step], "started_at": started.isoformat()}
    # Never replace a claim, even if its prior child failed or no terminal was stored.
    with (directory / "claim.json").open("xb") as stream:
        stream.write(canonical(base))
        stream.flush()
        os.fsync(stream.fileno())
    output = directory / "stdout.log"
    diagnostics = directory / "console.log"
    child_env = dict(env, PYTHONPATH=str(root / "src"))
    python = root / ".venv/bin/python"
    code = runner([str(python) if python.is_file() else sys.executable, *COMMANDS[step]], cwd=root,
                  env=child_env, output_path=diagnostics, stdout_path=output)
    receipt = dict(base, finished_at=clock().isoformat(), exit_code=code,
                   stdout=evidence_ref(root, output), diagnostics=evidence_ref(root, diagnostics))
    terminal = directory / "terminal.json"
    with terminal.open("xb") as stream:
        stream.write(canonical(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    return {"terminal_path": str(terminal), "exit_code": code}
