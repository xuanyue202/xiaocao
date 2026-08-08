from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from xiaocao.kol.remote_task_candidates import (
    discover_cached_remote_task_candidates,
    main,
    run_remote_writer_after_peer_gate,
)


HOST_ID = "remote-control:env_remote"
REMOTE_CWD = "/Users/remote/Documents/project/xiaocao"
TITLE = "xiaocao KOL hourly low-bandwidth operation"
GATE_NOW = datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc)
GATE_NOW_MS = int(GATE_NOW.timestamp() * 1000)


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


def test_peer_gate_retries_control_plane_and_ignores_stale_active_snapshot() -> None:
    list_calls = 0
    read_calls: list[str] = []
    side_effects: list[str] = []

    def list_threads():
        nonlocal list_calls
        list_calls += 1
        if list_calls == 1:
            raise TimeoutError("private app-server details")
        return {
            "threads": [
                {
                    "thread_id": "stale-writer",
                    "host_id": HOST_ID,
                    "cwd": REMOTE_CWD,
                    "automation_id": "automation-1",
                    "created_at_ms": GATE_NOW_MS - 60_000,
                    "status": "active",
                },
                {
                    "thread_id": "current-writer",
                    "host_id": HOST_ID,
                    "cwd": REMOTE_CWD,
                    "automation_id": "automation-1",
                    "created_at_ms": GATE_NOW_MS - 30_000,
                    "status": "active",
                },
            ]
        }

    def read_thread(thread_id: str):
        read_calls.append(thread_id)
        assert thread_id == "stale-writer"
        return {
            "thread_id": thread_id,
            "host_id": HOST_ID,
            "cwd": REMOTE_CWD,
            "automation_id": "automation-1",
            "status": "idle",
        }

    result = run_remote_writer_after_peer_gate(
        list_threads=list_threads,
        read_thread=read_thread,
        host_id=HOST_ID,
        cwd=REMOTE_CWD,
        automation_id="automation-1",
        current_thread_id="current-writer",
        now=GATE_NOW,
        mailbox=lambda: side_effects.append("mailbox"),
        runner=lambda: side_effects.append("runner"),
    )

    assert result["gate_result"] == "pass"
    assert result["audit"]["list_attempt_count"] == 2
    assert result["audit"]["read_thread_attempt_count"] == 1
    assert result["audit"]["runner_start_count"] == 1
    assert read_calls == ["stale-writer"]
    assert side_effects == ["mailbox", "runner"]
    assert all("private" not in json.dumps(row) for row in result["audit"]["attempts"])


def test_peer_gate_real_peer_is_a_no_op_before_mailbox_or_runner() -> None:
    side_effects: list[str] = []

    result = run_remote_writer_after_peer_gate(
        list_threads=lambda: {
            "threads": [{
                "thread_id": "real-peer",
                "host_id": HOST_ID,
                "cwd": REMOTE_CWD,
                "automation_id": "automation-1",
                "created_at_ms": GATE_NOW_MS - 60_000,
            }]
        },
        read_thread=lambda thread_id: {
            "thread_id": thread_id,
            "host_id": HOST_ID,
            "cwd": REMOTE_CWD,
            "automation_id": "automation-1",
            "status": "running",
        },
        host_id=HOST_ID,
        cwd=REMOTE_CWD,
        automation_id="automation-1",
        current_thread_id="current-writer",
        now=GATE_NOW,
        mailbox=lambda: side_effects.append("mailbox"),
        runner=lambda: side_effects.append("runner"),
    )

    assert result["gate_result"] == "no_op"
    assert result["audit"]["runner_start_count"] == 0
    assert side_effects == []


def test_peer_gate_persistent_handler_failure_is_agent_repair_and_credential_safe() -> None:
    result = run_remote_writer_after_peer_gate(
        list_threads=lambda: (_ for _ in ()).throw(
            RuntimeError("Codex app-server secret payload")
        ),
        read_thread=lambda _thread_id: pytest.fail("readback must not run"),
        host_id=HOST_ID,
        cwd=REMOTE_CWD,
        automation_id="automation-1",
        current_thread_id="current-writer",
        mailbox=lambda: pytest.fail("mailbox must remain closed"),
        runner=lambda: pytest.fail("runner must remain closed"),
        max_list_attempts=2,
    )

    assert result["gate_result"] == "repair_required"
    assert result["ownership"] == "agent"
    assert result["failure"] == {
        "category": "control_plane",
        "code": "list_threads_handler_error",
        "stage": "peer_discovery",
    }
    assert result["audit"]["runner_start_count"] == 0
    assert "secret" not in json.dumps(result)
