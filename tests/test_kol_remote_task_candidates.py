from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from xiaocao.kol.remote_task_candidates import (
    discover_cached_remote_task_candidates,
    main,
)


HOST_ID = "remote-control:env_remote"
REMOTE_CWD = "/Users/remote/Documents/project/xiaocao"
TITLE = "xiaocao KOL hourly low-bandwidth operation"


def _summary(
    thread_id: str,
    *,
    created_at_ms: int,
    host_id: str = HOST_ID,
    cwd: str = REMOTE_CWD,
    title: str = TITLE,
) -> dict[str, object]:
    return {
        "conversationId": thread_id,
        "title": title,
        "createdAt": created_at_ms,
        "updatedAt": created_at_ms,
        "cwd": cwd,
        "hostId": host_id,
        "source": "vscode",
    }


def test_discovers_current_remote_writer_from_ui_cache_when_catalog_is_empty() -> None:
    now = datetime(2026, 8, 6, 14, 45, tzinfo=timezone.utc)
    current_ms = int((now - timedelta(minutes=43)).timestamp() * 1000)
    state = {
        "electron-persisted-atom-state": {
            f"remote-thread-summaries-v2:{HOST_ID}": [
                _summary("current-writer", created_at_ms=current_ms),
            ]
        }
    }

    candidates = discover_cached_remote_task_candidates(
        state,
        host_id=HOST_ID,
        cwd=REMOTE_CWD,
        title=TITLE,
        now=now,
        lease=timedelta(hours=3),
    )

    assert [candidate["thread_id"] for candidate in candidates] == ["current-writer"]
    assert candidates[0]["candidate_only"] is True
    assert candidates[0]["requires_read_thread"] is True


def test_filters_stale_forbidden_and_wrong_identity_candidates() -> None:
    now = datetime(2026, 8, 6, 14, 45, tzinfo=timezone.utc)
    recent_ms = int((now - timedelta(hours=1)).timestamp() * 1000)
    stale_ms = int((now - timedelta(hours=3, seconds=1)).timestamp() * 1000)
    state = {
        "electron-persisted-atom-state": {
            f"remote-thread-summaries-v2:{HOST_ID}": [
                _summary("newest", created_at_ms=recent_ms + 1_000),
                _summary("older", created_at_ms=recent_ms),
                _summary("forbidden", created_at_ms=recent_ms + 2_000),
                _summary("stale", created_at_ms=stale_ms),
                _summary("wrong-host", created_at_ms=recent_ms, host_id="remote-control:other"),
                _summary("wrong-cwd", created_at_ms=recent_ms, cwd="/tmp/xiaocao"),
                _summary("wrong-title", created_at_ms=recent_ms, title="another task"),
            ]
        }
    }

    candidates = discover_cached_remote_task_candidates(
        state,
        host_id=HOST_ID,
        cwd=REMOTE_CWD,
        title=TITLE,
        now=now,
        lease=timedelta(hours=3),
        forbidden_thread_ids={"forbidden"},
    )

    assert [candidate["thread_id"] for candidate in candidates] == ["newest", "older"]


def test_cli_default_lease_includes_previous_day_writer(tmp_path, capsys) -> None:
    now = datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc)
    previous_day_ms = int((now - timedelta(hours=17)).timestamp() * 1000)
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "electron-persisted-atom-state": {
                    f"remote-thread-summaries-v2:{HOST_ID}": [
                        _summary("previous-day-writer", created_at_ms=previous_day_ms),
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "--state-file",
            str(state_file),
            "--host-id",
            HOST_ID,
            "--cwd",
            REMOTE_CWD,
            "--now",
            now.isoformat(),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert [row["thread_id"] for row in output["candidates"]] == [
        "previous-day-writer"
    ]


def test_remote_writer_lease_documents_candidate_only_cache_fallback() -> None:
    reference = (
        Path(__file__).parents[1]
        / ".codex/skills/kol-intelligence/references/remote-writer-lease.md"
    ).read_text(encoding="utf-8")

    assert "scripts/kol_remote_writer_candidates.py" in reference
    assert "still require `read_thread` before sending" in reference
    assert "Never report\n   “no task exists”" in reference
    assert "`No handler registered`" in reference
