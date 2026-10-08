from __future__ import annotations

import fcntl
import json
import os
import select
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kol_automation_slot_gate.py"


def _run_gate(tmp_path: Path, now: str, command: list[str], automation_id="weekly") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--now",
            now,
            "--lock-dir",
            str(tmp_path),
            "--automation-id",
            automation_id,
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
    lock_path = tmp_path / "weekly/20260927T1000+0800.lock"
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
    lock_path = tmp_path / "weekly/20260927T1000+0800.lock"
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


def test_other_automation_in_same_directory_and_hour_does_not_block(tmp_path):
    lock_path = tmp_path / "writer/20260927T1000+0800.lock"
    lock_path.parent.mkdir(parents=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        completed = _run_gate(tmp_path, "2026-09-27T10:20:00+08:00",
                              [sys.executable, "-c", "print('continued')"])
    assert completed.returncode == 0
    assert json.loads(completed.stdout.splitlines()[0])["automation_id"] == "weekly"
    assert completed.stdout.splitlines()[1] == "continued"


def test_same_hour_on_another_date_is_independent(tmp_path):
    lock_path = tmp_path / "weekly/20261006T1000+0800.lock"
    lock_path.parent.mkdir(parents=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        completed = _run_gate(tmp_path, "2026-10-07T10:20:00+08:00",
                              [sys.executable, "-c", "print('continued')"])
    assert completed.returncode == 0
    assert json.loads(completed.stdout.splitlines()[0])["status"] == "hour_acquired"
    assert completed.stdout.splitlines()[1] == "continued"


def test_runner_holds_lock_while_waiting_for_input_and_releases_on_exit(tmp_path):
    command = [sys.executable, "-c", "import sys; sys.stdin.readline(); print('finished')"]
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--now", "2026-10-07T10:20:00+08:00",
         "--lock-dir", str(tmp_path), "--automation-id", "weekly", "--", *command],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 5)[0], "gate did not start"
        assert json.loads(process.stdout.readline())["status"] == "hour_acquired"
        marker = tmp_path / "duplicate-effect"
        competing = _run_gate(
            tmp_path, "2026-10-07T10:59:00+08:00",
            [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
        )
        assert competing.returncode == 0
        assert json.loads(competing.stdout)["status"] == "hour_busy"
        assert not marker.exists()
        output, errors = process.communicate("continue\n", timeout=5)
        assert process.returncode == 0, errors
        assert output.strip() == "finished"
        after_exit = _run_gate(tmp_path, "2026-10-07T10:59:00+08:00",
                               [sys.executable, "-c", "print('continued')"])
        assert json.loads(after_exit.stdout.splitlines()[0])["status"] == "hour_acquired"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_inherited_automation_mismatch_stops_before_command(tmp_path):
    environment = dict(os.environ, CODEX_AUTOMATION_ID="another-task")
    marker = tmp_path / "effect"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--lock-dir", str(tmp_path),
         "--automation-id", "weekly", "--", sys.executable, "-c",
         f"from pathlib import Path; Path({str(marker)!r}).touch()"],
        env=environment, text=True, capture_output=True,
    )
    assert completed.returncode != 0
    assert "AUTOMATION_ENTRYPOINT_ID_MISMATCH" in completed.stderr
    assert not marker.exists()
    assert not (tmp_path / "weekly").exists()
