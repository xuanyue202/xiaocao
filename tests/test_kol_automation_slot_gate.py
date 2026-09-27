from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kol_automation_slot_gate.py"


def _run_gate(tmp_path: Path, now: str, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--now",
            now,
            "--lock-dir",
            str(tmp_path),
            "--",
            *command,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_any_minute_in_the_hour_can_acquire_and_run(
    tmp_path: Path,
) -> None:
    completed = _run_gate(
        tmp_path,
        "2026-09-27T23:47:00+08:00",
        [sys.executable, "-c", "print('continued')"],
    )

    assert completed.returncode == 0
    lines = completed.stdout.splitlines()
    result = json.loads(lines[0])
    assert result["status"] == "hour_acquired"
    assert result["hour_start_at"] == "2026-09-27T23:00:00+08:00"
    assert result["current_at"] == "2026-09-27T23:47:00+08:00"
    assert lines[1] == "continued"


def test_fresh_run_holds_exact_slot_lock_and_executes_command(tmp_path: Path) -> None:
    completed = _run_gate(
        tmp_path,
        "2026-09-27T10:20:00+08:00",
        [sys.executable, "-c", "print('continued')"],
    )

    assert completed.returncode == 0
    lines = completed.stdout.splitlines()
    result = json.loads(lines[0])
    assert result["status"] == "hour_acquired"
    assert result["hour_start_at"] == "2026-09-27T10:00:00+08:00"
    assert lines[1] == "continued"


def test_busy_exact_slot_exits_without_running_command(tmp_path: Path) -> None:
    lock_path = tmp_path / "20260927T1000+0800.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        completed = _run_gate(
            tmp_path,
            "2026-09-27T10:20:00+08:00",
            [sys.executable, "-c", "raise SystemExit(9)"],
        )
    finally:
        os.close(lock_fd)

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["status"] == "hour_busy"
    assert result["hour_key"] == "20260927T1000+0800"


def test_different_clock_hour_uses_a_different_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "20260927T1000+0800.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        completed = _run_gate(
            tmp_path,
            "2026-09-27T11:20:00+08:00",
            [sys.executable, "-c", "print('continued')"],
        )
    finally:
        os.close(lock_fd)

    assert completed.returncode == 0
    lines = completed.stdout.splitlines()
    result = json.loads(lines[0])
    assert result["status"] == "hour_acquired"
    assert result["hour_start_at"] == "2026-09-27T11:00:00+08:00"
    assert lines[1] == "continued"
