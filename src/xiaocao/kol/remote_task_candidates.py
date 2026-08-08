from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Mapping, Sequence, Set
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


REMOTE_SUMMARIES_PREFIX = "remote-thread-summaries-v2:"
DEFAULT_WRITER_TITLE = "xiaocao KOL hourly low-bandwidth operation"

_PEER_ACTIVE_STATUSES = frozenset(
    {
        "active",
        "in_progress",
        "needs_attention",
        "queued",
        "running",
        "waiting",
        "waiting_approval",
        "waiting_user_action",
    }
)
_PEER_TERMINAL_STATUSES = frozenset(
    {"cancelled", "completed", "failed", "idle", "stopped"}
)


def _safe_control_plane_error_code(operation: str, exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return f"{operation}_timeout"
    return f"{operation}_handler_error"


def _thread_id(value: Mapping[str, Any]) -> str:
    for key in ("thread_id", "threadId", "conversationId", "id"):
        candidate = str(value.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _thread_field(value: Mapping[str, Any], *names: str) -> str:
    for name in names:
        candidate = str(value.get(name) or "").strip()
        if candidate:
            return candidate
    return ""


def _unwrap_thread(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    for key in ("thread", "task", "data"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            return nested
    return value


def _list_threads_payload(value: Any) -> list[Mapping[str, Any]] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows = list(value)
    elif isinstance(value, Mapping):
        if value.get("error") is not None or value.get("isError") is True:
            return None
        rows = value.get("threads")
        if rows is None:
            rows = value.get("tasks")
        if rows is None:
            rows = value.get("items")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return None
        rows = list(rows)
    else:
        return None
    if not all(isinstance(row, Mapping) for row in rows):
        return None
    return [row for row in rows if isinstance(row, Mapping)]


def _read_thread_payload(value: Any) -> Mapping[str, Any] | None:
    row = _unwrap_thread(value)
    if row is None or row.get("error") is not None or row.get("isError") is True:
        return None
    return row


def _status(value: Mapping[str, Any]) -> str:
    for key in ("status", "state", "task_status", "thread_status", "turn_status"):
        raw = value.get(key)
        if isinstance(raw, Mapping):
            raw = raw.get("status") or raw.get("state")
        status = str(raw or "").strip().lower().replace("-", "_")
        if status:
            return status
    if value.get("active") is True or value.get("is_active") is True:
        return "active"
    if value.get("active") is False or value.get("is_active") is False:
        return "idle"
    return ""


def _matches_identity(
    value: Mapping[str, Any],
    *,
    thread_id: str,
    host_id: str,
    cwd: str,
    automation_id: str,
) -> bool:
    return (
        _thread_id(value) == thread_id
        and _thread_field(value, "host_id", "hostId", "host") == host_id
        and _thread_field(
            value, "cwd", "working_directory", "workingDirectory"
        )
        == cwd
        and _thread_field(
            value, "automation_id", "automationId", "automation"
        )
        == automation_id
    )


def _failure_fingerprint(failure: Mapping[str, str]) -> str:
    payload = json.dumps(
        dict(failure),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _repair_gate_result(
    audit: dict[str, Any],
    *,
    code: str,
    stage: str,
) -> dict[str, Any]:
    failure = {
        "category": "control_plane",
        "code": code,
        "stage": stage,
    }
    audit["gate_result"] = "repair_required"
    audit["terminal_result"] = "repair_required"
    audit["runner_start_count"] = 0
    return {
        "schema_version": 1,
        "gate_result": "repair_required",
        "ownership": "agent",
        "retryability": "retryable",
        "failure": failure,
        "failure_fingerprint": _failure_fingerprint(failure),
        "next_action": "repair_control_plane_then_retry_peer_gate",
        "audit": audit,
    }


def _sort_timestamp(value: Mapping[str, Any]) -> int:
    for key in (
        "updated_at_ms",
        "updatedAt",
        "created_at_ms",
        "createdAt",
    ):
        raw = value.get(key)
        if raw in (None, ""):
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def _created_timestamp_ms(value: Mapping[str, Any]) -> int | None:
    for key in ("created_at_ms", "createdAt", "created_at", "createdAtIso"):
        raw = value.get(key)
        if raw in (None, ""):
            continue
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return int(raw)
        text = str(raw).strip()
        if text.isdigit():
            return int(text)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return int(parsed.timestamp() * 1000)
    return None


def evaluate_remote_writer_peer_gate(
    *,
    list_threads: Callable[[], Any],
    read_thread: Callable[[str], Any],
    host_id: str,
    cwd: str,
    automation_id: str,
    current_thread_id: str,
    title: str | None = None,
    forbidden_thread_ids: Set[str] = frozenset(),
    now: datetime | None = None,
    lease: timedelta = timedelta(hours=24),
    max_list_attempts: int = 2,
    max_read_attempts: int = 3,
    refresh_control_plane: Callable[[], Any] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Gate the sole writer using candidate discovery and authoritative readback."""

    if not host_id or not cwd or not automation_id or not current_thread_id:
        raise ValueError("peer gate identity is incomplete")
    if max_list_attempts < 1 or max_read_attempts < 1:
        raise ValueError("peer gate retry budgets must be positive")
    if lease <= timedelta(0):
        raise ValueError("peer gate lease must be positive")
    gate_now = now or datetime.now(timezone.utc)
    if gate_now.tzinfo is None:
        raise ValueError("peer gate now must be timezone-aware")
    earliest_ms = int(
        (gate_now.astimezone(timezone.utc) - lease).timestamp() * 1000
    )
    latest_ms = int(
        (gate_now.astimezone(timezone.utc) + timedelta(minutes=5)).timestamp()
        * 1000
    )

    started = monotonic()
    audit: dict[str, Any] = {
        "schema_version": 1,
        "stage": "peer_discovery",
        "list_attempt_count": 0,
        "read_thread_attempt_count": 0,
        "runner_start_count": 0,
        "attempts": [],
        "candidate_count": 0,
    }
    candidates: list[Mapping[str, Any]] | None = None
    list_failure_code = "list_threads_handler_error"
    for attempt in range(1, max_list_attempts + 1):
        attempt_started = monotonic()
        audit["list_attempt_count"] += 1
        try:
            payload = list_threads()
        except Exception as exc:
            list_failure_code = _safe_control_plane_error_code(
                "list_threads", exc
            )
            audit["attempts"].append({
                "operation": "list_threads",
                "attempt": attempt,
                "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                "result": "error",
                "failure_code": _safe_control_plane_error_code(
                    "list_threads", exc
                ),
            })
            if attempt < max_list_attempts and refresh_control_plane is not None:
                refresh_started = monotonic()
                try:
                    refresh_control_plane()
                except Exception:
                    audit["attempts"].append({
                        "operation": "control_plane_refresh",
                        "attempt": attempt,
                        "elapsed_ms": max(
                            0,
                            int((monotonic() - refresh_started) * 1000),
                        ),
                        "result": "error",
                        "failure_code": "control_plane_refresh_error",
                    })
                else:
                    audit["attempts"].append({
                        "operation": "control_plane_refresh",
                        "attempt": attempt,
                        "elapsed_ms": max(
                            0,
                            int((monotonic() - refresh_started) * 1000),
                        ),
                        "result": "ok",
                    })
            continue
        candidates = _list_threads_payload(payload)
        if candidates is None:
            list_failure_code = "list_threads_response_invalid"
            audit["attempts"].append({
                "operation": "list_threads",
                "attempt": attempt,
                "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                "result": "error",
                "failure_code": "list_threads_response_invalid",
            })
            continue
        audit["attempts"].append({
            "operation": "list_threads",
            "attempt": attempt,
            "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
            "result": "ok",
            "candidate_count": len(candidates),
        })
        break

    if candidates is None:
        return _repair_gate_result(
            audit,
            code=list_failure_code,
            stage="peer_discovery",
        )

    selected: dict[str, Mapping[str, Any]] = {}
    unverified_candidate = False
    forbidden = set(forbidden_thread_ids) | {current_thread_id}
    for candidate in candidates:
        thread_id = _thread_id(candidate)
        candidate_title = str(candidate.get("title") or "").strip()
        created_at_ms = _created_timestamp_ms(candidate)
        if (
            not thread_id
            or thread_id in forbidden
            or _thread_field(candidate, "host_id", "hostId", "host") != host_id
            or _thread_field(
                candidate, "cwd", "working_directory", "workingDirectory"
            )
            != cwd
            or _thread_field(
                candidate, "automation_id", "automationId", "automation"
            )
            != automation_id
            or (title is not None and candidate_title and candidate_title != title)
        ):
            continue
        if created_at_ms is None:
            unverified_candidate = True
            continue
        if not earliest_ms <= created_at_ms <= latest_ms:
            continue
        selected[thread_id] = candidate
    ordered = sorted(
        selected.values(),
        key=lambda row: (
            _sort_timestamp(row),
            _thread_id(row),
        ),
        reverse=True,
    )
    audit["candidate_count"] = len(ordered)
    if not ordered:
        if unverified_candidate:
            return _repair_gate_result(
                audit,
                code="candidate_creation_time_missing",
                stage="peer_discovery",
            )
        audit["gate_result"] = "pass"
        audit["terminal_result"] = "no_matching_peer"
        audit["elapsed_ms"] = max(0, int((monotonic() - started) * 1000))
        return {
            "schema_version": 1,
            "gate_result": "pass",
            "ownership": "none",
            "retryability": "not_retryable",
            "audit": audit,
        }

    for candidate in ordered:
        thread_id = _thread_id(candidate)
        read_value: Mapping[str, Any] | None = None
        for attempt in range(1, max_read_attempts + 1):
            attempt_started = monotonic()
            audit["read_thread_attempt_count"] += 1
            try:
                payload = read_thread(thread_id)
            except Exception as exc:
                audit["attempts"].append({
                    "operation": "read_thread",
                    "thread_id": thread_id,
                    "attempt": attempt,
                    "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                    "result": "error",
                    "failure_code": _safe_control_plane_error_code(
                        "read_thread", exc
                    ),
                })
                continue
            read_value = _read_thread_payload(payload)
            if read_value is None:
                audit["attempts"].append({
                    "operation": "read_thread",
                    "thread_id": thread_id,
                    "attempt": attempt,
                    "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                    "result": "error",
                    "failure_code": "read_thread_response_invalid",
                })
                continue
            if not _matches_identity(
                read_value,
                thread_id=thread_id,
                host_id=host_id,
                cwd=cwd,
                automation_id=automation_id,
            ):
                audit["attempts"].append({
                    "operation": "read_thread",
                    "thread_id": thread_id,
                    "attempt": attempt,
                    "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                    "result": "error",
                    "failure_code": "read_thread_identity_mismatch",
                })
                read_value = None
                continue
            status = _status(read_value)
            if not status:
                audit["attempts"].append({
                    "operation": "read_thread",
                    "thread_id": thread_id,
                    "attempt": attempt,
                    "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                    "result": "error",
                    "failure_code": "read_thread_status_missing",
                })
                read_value = None
                continue
            audit["attempts"].append({
                "operation": "read_thread",
                "thread_id": thread_id,
                "attempt": attempt,
                "elapsed_ms": max(0, int((monotonic() - attempt_started) * 1000)),
                "result": "ok",
                "authoritative_status": status,
            })
            if status in _PEER_ACTIVE_STATUSES:
                audit["gate_result"] = "no_op"
                audit["terminal_result"] = "active_peer"
                audit["authoritative_peer_thread_id"] = thread_id
                audit["elapsed_ms"] = max(0, int((monotonic() - started) * 1000))
                return {
                    "schema_version": 1,
                    "gate_result": "no_op",
                    "ownership": "peer",
                    "retryability": "not_retryable",
                    "audit": audit,
                }
            if status in _PEER_TERMINAL_STATUSES:
                break
            read_value = None
        if read_value is None:
            return _repair_gate_result(
                audit,
                code="read_thread_handler_error",
                stage="peer_readback",
            )

    audit["gate_result"] = "pass"
    audit["terminal_result"] = "authoritative_no_active_peer"
    audit["elapsed_ms"] = max(0, int((monotonic() - started) * 1000))
    return {
        "schema_version": 1,
        "gate_result": "pass",
        "ownership": "none",
        "retryability": "not_retryable",
        "audit": audit,
    }


def run_remote_writer_after_peer_gate(
    *,
    list_threads: Callable[[], Any],
    read_thread: Callable[[str], Any],
    host_id: str,
    cwd: str,
    automation_id: str,
    current_thread_id: str,
    mailbox: Callable[[], Any] | None = None,
    runner: Callable[[], Any] | None = None,
    **gate_options: Any,
) -> dict[str, Any]:
    """Run the sole-writer side effects only after one passing peer gate."""

    result = evaluate_remote_writer_peer_gate(
        list_threads=list_threads,
        read_thread=read_thread,
        host_id=host_id,
        cwd=cwd,
        automation_id=automation_id,
        current_thread_id=current_thread_id,
        **gate_options,
    )
    if result["gate_result"] != "pass":
        return result
    audit = result["audit"]
    response = dict(result)
    if mailbox is not None:
        response["mailbox_result"] = mailbox()
    if runner is not None:
        audit["runner_start_count"] = 1
        response["runner_result"] = runner()
    return response


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
