#!/usr/bin/env python3
"""Non-blocking Beijing clock-hour gate for local KOL Automation runs."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")


def _parse_now(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(BEIJING)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def _hour_start(now: datetime) -> datetime:
    return now.astimezone(BEIJING).replace(minute=0, second=0, microsecond=0)


def _hour_key(hour_start: datetime) -> str:
    return hour_start.strftime("%Y%m%dT%H%M%z")


def _emit(status: str, *, hour_start: datetime, now: datetime) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "hour_start_at": hour_start.isoformat(timespec="seconds"),
                "current_at": now.isoformat(timespec="seconds"),
                "hour_key": _hour_key(hour_start),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exit when the current Beijing clock hour is busy; otherwise hold "
            "that hour lock while executing the supplied command."
        )
    )
    parser.add_argument(
        "--lock-dir",
        type=Path,
        default=Path("output/live/kol_automation_hour_locks"),
    )
    parser.add_argument("--now", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    try:
        now = _parse_now(args.now)
    except ValueError as exc:
        parser.error(str(exc))

    hour_start = _hour_start(now)

    lock_dir = args.lock_dir.expanduser().resolve()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{_hour_key(hour_start)}.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _emit("hour_busy", hour_start=hour_start, now=now)
            return 0

        metadata = json.dumps(
            {
                "pid": os.getpid(),
                "hour_start_at": hour_start.isoformat(timespec="seconds"),
                "acquired_at": now.isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, metadata + b"\n")
        os.fsync(lock_fd)

        _emit("hour_acquired", hour_start=hour_start, now=now)
        os.set_inheritable(lock_fd, True)
        environment = os.environ.copy()
        environment["XIAOCAO_AUTOMATION_HOUR_START_AT"] = (
            hour_start.isoformat(timespec="seconds")
        )
        environment["XIAOCAO_AUTOMATION_HOUR_KEY"] = _hour_key(hour_start)
        os.execvpe(command[0], command, environment)
    except OSError as exc:
        print(
            json.dumps(
                {
                    "status": "gate_error",
                    "error": str(exc),
                    "command": command[0],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )
        return 127
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
