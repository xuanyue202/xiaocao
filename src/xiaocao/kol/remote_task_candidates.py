from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence, Set
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REMOTE_SUMMARIES_PREFIX = "remote-thread-summaries-v2:"
DEFAULT_WRITER_TITLE = "xiaocao KOL hourly low-bandwidth operation"


def _created_at_ms(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def discover_cached_remote_task_candidates(
    state: Mapping[str, Any],
    *,
    host_id: str,
    cwd: str,
    title: str,
    now: datetime,
    lease: timedelta,
    forbidden_thread_ids: Set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Return UI-cache candidates that still require authoritative read_thread.

    Electron's remote summary cache remains useful for candidate ID discovery when
    the newer local thread catalog has not completed its initial build.  It never
    proves current task state, message delivery, or handoff acceptance.
    """

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if lease <= timedelta(0):
        raise ValueError("lease must be positive")

    atoms = state.get("electron-persisted-atom-state")
    if not isinstance(atoms, Mapping):
        return []
    summaries = atoms.get(f"{REMOTE_SUMMARIES_PREFIX}{host_id}")
    if not isinstance(summaries, Sequence) or isinstance(summaries, (str, bytes)):
        return []

    now_utc = now.astimezone(timezone.utc)
    earliest_ms = int((now_utc - lease).timestamp() * 1000)
    latest_ms = int((now_utc + timedelta(minutes=5)).timestamp() * 1000)
    candidates_by_id: dict[str, dict[str, Any]] = {}

    for raw in summaries:
        if not isinstance(raw, Mapping):
            continue
        thread_id = raw.get("conversationId")
        created_at_ms = _created_at_ms(raw.get("createdAt"))
        if (
            not isinstance(thread_id, str)
            or not thread_id
            or thread_id in forbidden_thread_ids
            or created_at_ms is None
            or created_at_ms < earliest_ms
            or created_at_ms > latest_ms
            or raw.get("hostId") != host_id
            or raw.get("cwd") != cwd
            or raw.get("title") != title
        ):
            continue

        created_at = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
        candidate = {
            "thread_id": thread_id,
            "host_id": host_id,
            "cwd": cwd,
            "title": title,
            "created_at": created_at.isoformat(),
            "created_at_ms": created_at_ms,
            "candidate_only": True,
            "requires_read_thread": True,
            "source": "electron_remote_thread_summaries_v2",
        }
        previous = candidates_by_id.get(thread_id)
        if previous is None or created_at_ms > previous["created_at_ms"]:
            candidates_by_id[thread_id] = candidate

    return sorted(
        candidates_by_id.values(),
        key=lambda candidate: (candidate["created_at_ms"], candidate["thread_id"]),
        reverse=True,
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--now must include a timezone")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover candidate remote KOL writer task IDs from Codex UI cache."
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path.home() / ".codex" / ".codex-global-state.json",
    )
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--title", default=DEFAULT_WRITER_TITLE)
    parser.add_argument("--lease-hours", type=float, default=24.0)
    parser.add_argument("--now", type=_parse_datetime)
    parser.add_argument("--forbid", action="append", default=[])
    args = parser.parse_args(argv)

    state = json.loads(args.state_file.read_text(encoding="utf-8"))
    now = args.now or datetime.now(timezone.utc)
    candidates = discover_cached_remote_task_candidates(
        state,
        host_id=args.host_id,
        cwd=args.cwd,
        title=args.title,
        now=now,
        lease=timedelta(hours=args.lease_hours),
        forbidden_thread_ids=frozenset(args.forbid),
    )
    print(
        json.dumps(
            {
                "candidates": candidates,
                "candidate_count": len(candidates),
                "authoritative": False,
                "required_next_step": "read_thread",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
