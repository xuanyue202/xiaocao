#!/usr/bin/env python3
"""Non-blocking Beijing clock-hour gate for local KOL Automation runs."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.automation_slot import automation_hour_start


BEIJING = ZoneInfo("Asia/Shanghai")


def _parse_now(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(BEIJING)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def _hour_start(now: datetime) -> datetime:
    return automation_hour_start(now)


def _hour_key(hour_start: datetime) -> str:
    return hour_start.strftime("%Y%m%dT%H%M%z")


def preparation_obligation(automation_id: str, now: datetime) -> dict | None:
    """Expose the source-only duty before a long original acquisition starts."""
    hour = automation_hour_start(now)
    if automation_id != 'xiaocao-kol-hourly-low-bandwidth-operation' or hour.hour not in {6, 7, 21}:
        return None
    return {'event': 'kol_shared_preparation_due', 'authority': 0,
        'automation_id': automation_id, 'owner_thread_id': os.environ.get('CODEX_THREAD_ID'),
        'observed_at': now.isoformat(), 'source_publication_required': True,
        'capture_completion_required': False, 'next_action': 'prepare_published_snapshot',
        'target_trading_date': 'prove_calendar_before_morning_horizon',
        'preparation_target': '09:20', 'consumer_hard_cutoff': '09:27:30',
        'scope': 'coherent_published_snapshot_only_pending_sources_explicit'}


def _emit(status: str, *, hour_start: datetime, now: datetime, automation_id: str, owner=None) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "automation_id": automation_id,
                "owner": owner,
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
    parser.add_argument("--prepare-opening", action="store_true", help="Start the owned preopen program on fresh06/21 source runs")
    parser.add_argument("--now", help=argparse.SUPPRESS)
    parser.add_argument("--automation-id", default=os.environ.get("CODEX_AUTOMATION_ID", "manual-slot-gate"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if (not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", args.automation_id)
            or (os.environ.get("CODEX_AUTOMATION_ID")
                and os.environ["CODEX_AUTOMATION_ID"] != args.automation_id)):
        parser.error("AUTOMATION_ENTRYPOINT_ID_MISMATCH")

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

    lock_dir = args.lock_dir.expanduser().resolve() / args.automation_id
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{_hour_key(hour_start)}.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                owner = json.loads(os.read(lock_fd, 4096))
            except ValueError:
                owner = {"status": "unproven"}
            _emit("hour_busy", hour_start=hour_start, now=now, automation_id=args.automation_id, owner=owner)
            return 0

        metadata = json.dumps(
            {
                "pid": os.getpid(),
                "automation_id": args.automation_id,
                "thread_id": os.environ.get("CODEX_THREAD_ID"),
                "hour_start_at": hour_start.isoformat(timespec="seconds"),
                "acquired_at": now.isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, metadata + b"\n")
        os.fsync(lock_fd)

        _emit("hour_acquired", hour_start=hour_start, now=now, automation_id=args.automation_id)
        obligation = preparation_obligation(args.automation_id, now)
        if obligation is not None:
            print(json.dumps(obligation, ensure_ascii=False, separators=(',', ':')), flush=True)
        os.set_inheritable(lock_fd, True)
        environment = os.environ.copy()
        environment["CODEX_AUTOMATION_ID"] = args.automation_id
        environment.pop('XIAOCAO_KOL_PREOPEN_ENABLED',None)
        environment.pop('XIAOCAO_KOL_PREOPEN_PLAN',None)
        if (args.prepare_opening and args.automation_id == 'xiaocao-kol-hourly-low-bandwidth-operation'
                and hour_start.hour in {6,21} and len(command)>=3
                and Path(command[1]).name=='kol_daily.py' and command[2]=='run'):
            environment['XIAOCAO_KOL_PREOPEN_ENABLED']='v1'
        environment["XIAOCAO_AUTOMATION_HOUR_START_AT"] = (
            hour_start.isoformat(timespec="seconds")
        )
        environment["XIAOCAO_AUTOMATION_HOUR_KEY"] = _hour_key(hour_start)
        environment["XIAOCAO_AUTOMATION_ACQUIRED_AT"] = now.isoformat(timespec="seconds")
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
