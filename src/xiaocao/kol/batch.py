"""Append-only, resumable coordination for existing KOL source runners.

The coordinator owns scheduling and receipt reconciliation only.  Source
adapters remain the Ticket 03/04/05 runners, and source-video bytes never enter
this process.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .enrichment_types import EnrichmentError


MIN_ASYNC_POLL_SECONDS = 300
MAX_JSON_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_BATCH_INSIGHT_BYTES = 2_048
REQUIRED_COVERAGE_ROWS = {
    "todays_market_diagnosis",
    "next_session_playbook",
    "next_several_session_base_case",
    "style_market_cap_regime",
    "market_board_sector_hierarchy",
    "position_risk_budget",
    "named_asset_inventory",
}
SUPPORTED_ADAPTERS = {
    "xiaocao_live",
    "lv_text_image",
    "subscription_video",
}
TERMINAL_HOUSEHOLD_STATUSES = {
    "delivered",
    "reused_completed_receipt",
    "suppressed",
}
TERMINAL_BOOK_STATUSES = {"filled", "no_trade"}
TERMINAL_DISPOSITIONS = {"low_density", "duplicate"}
PAUSED_DISPOSITIONS = {
    "unauthorized",
    "missing_evidence",
    "missing_market_data",
}
ADAPTER_MEDIA_TYPES = {
    "xiaocao_live": {"video"},
    "lv_text_image": {"image", "text"},
    "subscription_video": {"video"},
}
REQUIRED_WATCH_ROLES = {
    "cloud_transfer_claim",
    "cloud_transfer_receipt",
    "transcript_generation",
    "ai_note_submission",
    "household_notification",
    "book_kol_us_action",
}
CHILD_IMMUTABLE_FIELDS = (
    "adapter",
    "source_identity",
    "version_identity",
    "source_parts",
    "author",
    "media_type",
    "priority",
    "wait_for_async_receipt",
    "receipt_path",
)


class BatchError(EnrichmentError):
    """A fail-closed coordinator contract violation."""


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in text
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _sha256_small_json(path: Path, *, label: str) -> str:
    if path.suffix.lower() != ".json" or not path.is_file():
        raise BatchError(f"{label} must be a small JSON file")
    try:
        if path.stat().st_size > MAX_JSON_RECEIPT_BYTES:
            raise BatchError(f"{label} must be a small JSON file")
    except OSError as exc:
        raise BatchError(f"{label} must be a small JSON file") from exc
    return _sha256_file(path)


def _parse_time(value: Any, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise BatchError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise BatchError(f"{field} must include a timezone")
    return parsed


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_RECEIPT_BYTES:
            raise BatchError(f"{label} exceeds the small-payload boundary")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BatchError(f"{label} is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise BatchError(f"{label} must be a JSON object")
    return value


def _reason(value: dict[str, Any], *, field: str) -> str:
    reason = str(value.get(field) or "").strip()
    if not reason:
        raise BatchError(f"{field} is required")
    return reason


def _validate_book(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("paper_only") is not True:
        raise BatchError("Book KOL-US terminal receipt must be paper-only")
    status = str(value.get("status") or "")
    if status not in TERMINAL_BOOK_STATUSES:
        raise BatchError("Book KOL-US terminal status is invalid")
    if status == "no_trade":
        _reason(value, field="reason")
    if status == "filled":
        if (
            value.get("book") != "KOL-US"
            or not str(value.get("idempotency_key") or "").strip()
            or not str(value.get("ticker") or "").strip()
            or value.get("side") not in {"buy", "sell"}
        ):
            raise BatchError("filled Book result lacks a durable KOL-US fill receipt")
        try:
            if float(value.get("price")) <= 0 or float(value.get("quantity")) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise BatchError(
                "filled Book result lacks a durable KOL-US fill receipt"
            ) from None
    return {
        "paper_only": True,
        "status": status,
        "reason": str(value.get("reason") or ""),
        "idempotency_key": str(value.get("idempotency_key") or ""),
        "book": str(value.get("book") or "KOL-US"),
        "ticker": str(value.get("ticker") or ""),
        "side": str(value.get("side") or ""),
        "price": value.get("price"),
        "quantity": value.get("quantity"),
    }


def _validate_household(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BatchError("household terminal receipt is missing")
    status = str(value.get("status") or "")
    if status not in TERMINAL_HOUSEHOLD_STATUSES:
        raise BatchError("household terminal status is invalid")
    if status == "suppressed":
        _reason(value, field="reason")
    if status == "delivered" and not (
        value.get("receipt_persisted")
        or value.get("notification_idempotency_key")
        or value.get("idempotency_key")
    ):
        raise BatchError("delivered household receipt is not durable")
    return {
        "status": status,
        "idempotency_key": str(
            value.get("notification_idempotency_key")
            or value.get("idempotency_key")
            or ""
        ),
        "reason": str(value.get("reason") or ""),
    }


class BatchCoordinator:
    """Public runner/status/audit seam backed only by append-only events."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.lock_path = self.output_dir / ".lock"
        self.now = now or (lambda: datetime.now(timezone.utc).astimezone())
        self._thread_lock = threading.RLock()
        self._lock_depth = 0

    def _time(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise BatchError("batch coordinator clock needs a timezone")
        return value

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            if self._lock_depth:
                self._lock_depth += 1
                try:
                    yield
                finally:
                    self._lock_depth -= 1
                return
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                self._lock_depth = 1
                try:
                    yield
                finally:
                    self._lock_depth = 0
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def events(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._events_unlocked()

    def _events_unlocked(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise BatchError("batch ledger cannot be read") from exc
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BatchError(
                    f"batch ledger line {number} is invalid"
                ) from exc
            if not isinstance(row, dict):
                raise BatchError(f"batch ledger line {number} is not an object")
            event_id = str(row.get("event_id") or "")
            unsigned = dict(row)
            unsigned.pop("event_id", None)
            if event_id != _sha256_text(_canonical(unsigned)):
                raise BatchError(
                    f"batch ledger line {number} failed integrity validation"
                )
            rows.append(row)
        return rows

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        occurred_at = self._time().isoformat()
        row = {
            "schema_version": 1,
            "event": event,
            "occurred_at": occurred_at,
            **fields,
        }
        row["event_id"] = _sha256_text(_canonical(row))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload = _canonical(row) + "\n"
        blocked_signals = {signal.SIGINT, signal.SIGTERM}
        previous_mask = signal.pthread_sigmask(
            signal.SIG_BLOCK,
            blocked_signals,
        )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.events_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            remaining = memoryview(payload.encode("utf-8"))
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise BatchError("batch ledger append made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        return row

    @staticmethod
    def _child_id(child: dict[str, Any]) -> str:
        return _sha256_text(
            "\n".join(
                str(child.get(field) or "")
                for field in (
                    "adapter",
                    "source_identity",
                    "version_identity",
                )
            )
        )

    def _normalize_child(self, child: dict[str, Any]) -> dict[str, Any]:
        adapter = str(child.get("adapter") or "")
        if adapter not in SUPPORTED_ADAPTERS:
            raise BatchError("batch child adapter is unsupported")
        source_identity = str(child.get("source_identity") or "").strip()
        version_identity = str(child.get("version_identity") or "").strip()
        receipt_path = Path(
            str(child.get("receipt_path") or "")
        ).expanduser().resolve()
        if receipt_path.suffix.lower() != ".json":
            raise BatchError("batch child receipt_path must be a JSON receipt")
        media_type = str(child.get("media_type") or "")
        if (
            not source_identity
            or not version_identity
            or media_type not in {"video", "image", "text"}
            or not str(child.get("author") or "").strip()
            or not str(child.get("receipt_path") or "").strip()
        ):
            raise BatchError("batch child identity or receipt is incomplete")
        if media_type not in ADAPTER_MEDIA_TYPES[adapter]:
            raise BatchError(
                "batch child media_type does not match its adapter"
            )
        raw_source_parts = child.get("source_parts", [])
        if not isinstance(raw_source_parts, list):
            raise BatchError("batch child source_parts must be a list")
        source_parts = []
        for part in raw_source_parts:
            if not isinstance(part, dict):
                raise BatchError("batch child source part is invalid")
            try:
                part_index = int(part.get("part_index"))
                source_size = int(part.get("source_size") or 0)
            except (TypeError, ValueError) as exc:
                raise BatchError("batch child source part is invalid") from exc
            normalized_part = {
                "source_identity": str(
                    part.get("source_identity") or ""
                ).strip(),
                "version_identity": str(
                    part.get("version_identity") or ""
                ).strip(),
                "part_index": part_index,
                "part_label": str(part.get("part_label") or part_index),
                "source_path": str(part.get("source_path") or "").strip(),
                "source_size": source_size,
            }
            if (
                not normalized_part["source_identity"]
                or not normalized_part["version_identity"]
                or part_index <= 0
                or not normalized_part["source_path"]
                or source_size <= 0
            ):
                raise BatchError("batch child source part is incomplete")
            source_parts.append(normalized_part)
        source_parts.sort(key=lambda part: part["part_index"])
        if source_parts:
            if (
                adapter != "subscription_video"
                or media_type != "video"
                or len(source_parts) < 2
                or [part["part_index"] for part in source_parts]
                != list(range(1, len(source_parts) + 1))
                or len(
                    {
                        (
                            part["source_identity"],
                            part["version_identity"],
                        )
                        for part in source_parts
                    }
                )
                != len(source_parts)
            ):
                raise BatchError(
                    "batch logical video parts are ambiguous or incomplete"
                )
        try:
            priority = int(child.get("priority"))
        except (TypeError, ValueError) as exc:
            raise BatchError("batch child priority is invalid") from exc
        if not 0 <= priority <= 100:
            raise BatchError("batch child priority must be within 0..100")
        status = "registered"
        next_poll_not_before = None
        failure_reason = None
        terminal_receipt = None
        disposition_reason = child.get("disposition_reason")
        if disposition_reason is not None:
            disposition_reason = str(disposition_reason)
            failure_reason = disposition_reason
            if disposition_reason in TERMINAL_DISPOSITIONS:
                status = "terminal"
                disposition_key = _sha256_text(
                    f"{adapter}\n{source_identity}\n"
                    f"{version_identity}\n{disposition_reason}"
                )
                terminal_receipt = {
                    "disposition": disposition_reason,
                    "household": {
                        "status": "suppressed",
                        "reason": disposition_reason,
                        "idempotency_key": disposition_key,
                    },
                    "book_kol_us": {
                        "paper_only": True,
                        "status": "no_trade",
                        "reason": disposition_reason,
                        "idempotency_key": disposition_key,
                        "book": "KOL-US",
                    },
                    "new_external_side_effect_count": 0,
                    "large_payload_local_bytes": 0,
                    "coordinator_source_video_bytes": 0,
                }
            elif disposition_reason in PAUSED_DISPOSITIONS:
                status = "paused"
            else:
                raise BatchError("batch child disposition reason is invalid")
        if child.get("async_requested_at") is not None:
            raise BatchError(
                "async_requested_at is coordinator-owned durable state"
            )
        wait_for_async_receipt = child.get("wait_for_async_receipt") is True
        async_requested_at = None
        if wait_for_async_receipt:
            if disposition_reason is not None:
                raise BatchError(
                    "classified child cannot also wait for async work"
                )
            if media_type != "video":
                raise BatchError("only video children may wait for async work")
            status = "waiting_async"
        return {
            "child_id": self._child_id(child),
            "adapter": adapter,
            "source_identity": source_identity,
            "version_identity": version_identity,
            "source_parts": source_parts,
            "author": str(child["author"]).strip(),
            "media_type": media_type,
            "priority": priority,
            "status": status,
            "next_poll_not_before": next_poll_not_before,
            "async_requested_at": async_requested_at,
            "wait_for_async_receipt": wait_for_async_receipt,
            "retry_count": 0,
            "failure_reason": failure_reason,
            "receipt_path": str(receipt_path),
            "large_payload_local_bytes": 0,
            "terminal_receipt": terminal_receipt,
        }

    def create_batch(
        self,
        batch_id: str,
        children: list[dict[str, Any]],
        *,
        watched_artifacts: list[dict[str, Any]] | None = None,
        insight_required: bool = False,
    ) -> dict[str, Any]:
        if not batch_id.strip() or not children:
            raise BatchError("batch id and at least one child are required")
        normalized = [self._normalize_child(child) for child in children]
        seen: set[str] = set()
        for child in normalized:
            child_id = child["child_id"]
            if child_id in seen:
                raise BatchError("batch child stable identity is duplicated")
            seen.add(child_id)
        with self._locked():
            state = self._state(batch_id)
            if state is not None:
                existing = {
                    row["child_id"]: row for row in state["children"]
                }
                for child in normalized:
                    recorded = existing.get(child["child_id"])
                    if recorded is None or any(
                        child[field] != recorded[field]
                        for field in CHILD_IMMUTABLE_FIELDS
                    ):
                        raise BatchError("existing batch child metadata changed")
                requested_watch = self._snapshot_artifacts(
                    watched_artifacts or []
                )
                if requested_watch != state["watched_artifacts_before"]:
                    raise BatchError("existing batch watcher set changed")
                if insight_required and not state["insight_required"]:
                    self._append(
                        "batch_insight_required",
                        batch_id=batch_id,
                        coordinator_source_video_bytes=0,
                    )
                return self._status_unlocked(batch_id)
            checkpointed = [
                self._with_async_checkpoint(child)
                for child in normalized
            ]
            self._append(
                "batch_created",
                batch_id=batch_id,
                child_count=len(checkpointed),
                children=checkpointed,
                insight_required=insight_required,
                coordinator_source_video_bytes=0,
                watched_artifacts_before=self._snapshot_artifacts(
                    watched_artifacts or []
                ),
            )
        return self.status(batch_id)

    def _with_async_checkpoint(
        self,
        child: dict[str, Any],
    ) -> dict[str, Any]:
        checkpointed = dict(child)
        if checkpointed.get("wait_for_async_receipt"):
            requested = self._time()
            checkpointed["async_requested_at"] = requested.isoformat()
            checkpointed["next_poll_not_before"] = (
                requested + timedelta(seconds=MIN_ASYNC_POLL_SECONDS)
            ).isoformat()
        return checkpointed

    @staticmethod
    def _snapshot_artifacts(
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise BatchError("watched artifact must be an object")
            path = Path(str(artifact.get("path") or "")).expanduser().resolve()
            roles_value = artifact.get("roles")
            if (
                not str(artifact.get("path") or "").strip()
                or not isinstance(roles_value, list)
                or not roles_value
                or any(
                    not isinstance(role, str) or not role.strip()
                    for role in roles_value
                )
            ):
                raise BatchError("watched artifact path and roles are required")
            roles = sorted(set(roles_value))
            key = str(path)
            if key in seen:
                raise BatchError("watched artifact path is duplicated")
            seen.add(key)
            if path.suffix.lower() not in {".json", ".jsonl"}:
                raise BatchError(
                    "watched artifact must be JSON/JSONL, never source video"
                )
            if path.is_file():
                try:
                    if path.stat().st_size > MAX_JSON_RECEIPT_BYTES:
                        raise BatchError(
                            "watched artifact exceeds the small-payload boundary"
                        )
                    data = path.read_bytes()
                except OSError as exc:
                    raise BatchError(
                        f"watched artifact cannot be read: {path.name}"
                    ) from exc
                snapshots.append(
                    {
                        "path": key,
                        "roles": roles,
                        "exists": True,
                        "size_bytes": len(data),
                        "line_count": len(data.splitlines()),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            elif path.exists():
                raise BatchError("watched artifact must be a file")
            else:
                snapshots.append(
                    {
                        "path": key,
                        "roles": roles,
                        "exists": False,
                        "size_bytes": 0,
                        "line_count": 0,
                        "sha256": None,
                    }
                )
        snapshots.sort(key=lambda row: row["path"])
        return snapshots

    def submit_child(
        self,
        batch_id: str,
        child: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = self._normalize_child(child)
        with self._locked():
            if self._state(batch_id) is None:
                raise BatchError("batch does not exist")
            state = self._status_unlocked(batch_id)
            existing = {
                row["child_id"]: row for row in state["children"]
            }
            recorded = existing.get(normalized["child_id"])
            if recorded is not None:
                if any(
                    normalized[field] != recorded[field]
                    for field in CHILD_IMMUTABLE_FIELDS
                ):
                    raise BatchError("existing batch child metadata changed")
                return self.status(batch_id)
            if state["status"] == "completed":
                raise BatchError("completed batch cannot accept another child")
            self._append(
                "child_registered",
                batch_id=batch_id,
                **self._with_async_checkpoint(normalized),
            )
        return self.status(batch_id)

    def _state(self, batch_id: str) -> dict[str, Any] | None:
        relevant = [
            row for row in self.events() if row.get("batch_id") == batch_id
        ]
        if not relevant:
            return None
        if relevant[0].get("event") != "batch_created":
            raise BatchError("batch ledger does not start with batch_created")
        children: dict[str, dict[str, Any]] = {}
        embedded_children = relevant[0].get("children", [])
        if not isinstance(embedded_children, list):
            raise BatchError("batch_created children must be a list")
        if embedded_children and len(embedded_children) != int(
            relevant[0].get("child_count") or 0
        ):
            raise BatchError("batch_created child count changed")
        for embedded in embedded_children:
            if not isinstance(embedded, dict):
                raise BatchError("batch_created child is invalid")
            child_id = str(embedded.get("child_id") or "")
            if not child_id or child_id in children:
                raise BatchError("batch_created child identity is invalid")
            children[child_id] = {
                key: embedded.get(key)
                for key in (
                    "child_id",
                    "adapter",
                    "source_identity",
                    "version_identity",
                    "source_parts",
                    "author",
                    "media_type",
                    "priority",
                    "status",
                    "next_poll_not_before",
                    "async_requested_at",
                    "wait_for_async_receipt",
                    "retry_count",
                    "failure_reason",
                    "receipt_path",
                    "large_payload_local_bytes",
                    "terminal_receipt",
                )
            }
            children[child_id]["source_parts"] = (
                embedded.get("source_parts") or []
            )
            children[child_id]["registered_at"] = relevant[0]["occurred_at"]
        for event in relevant:
            child_id = str(event.get("child_id") or "")
            if event["event"] == "child_registered":
                if child_id in children:
                    raise BatchError("batch child was registered twice")
                children[child_id] = {
                    key: event.get(key)
                    for key in (
                        "child_id",
                        "adapter",
                        "source_identity",
                        "version_identity",
                        "source_parts",
                        "author",
                        "media_type",
                        "priority",
                        "status",
                        "next_poll_not_before",
                        "async_requested_at",
                        "wait_for_async_receipt",
                        "retry_count",
                        "failure_reason",
                        "receipt_path",
                        "large_payload_local_bytes",
                        "terminal_receipt",
                    )
                }
                children[child_id]["source_parts"] = (
                    event.get("source_parts") or []
                )
                children[child_id]["registered_at"] = event["occurred_at"]
            elif child_id:
                if child_id not in children:
                    raise BatchError("batch event references an unknown child")
                child = children[child_id]
                if child["status"] == "terminal":
                    raise BatchError("terminal batch child regressed")
                if event["event"] == "child_reconciliation_claimed":
                    child["status"] = "reconciling"
                    child["next_poll_not_before"] = None
                elif event["event"] == "child_async_poll_claimed":
                    child["status"] = "polling"
                    child["next_poll_not_before"] = None
                elif event["event"] == "child_retry_scheduled":
                    child["status"] = "waiting_async"
                    child["retry_count"] = int(event["retry_count"])
                    child["failure_reason"] = event["failure_reason"]
                    child["next_poll_not_before"] = event[
                        "next_poll_not_before"
                    ]
                elif event["event"] == "child_paused":
                    child["status"] = "paused"
                    child["failure_reason"] = event["failure_reason"]
                    child["next_poll_not_before"] = None
                elif event["event"] == "child_terminal":
                    child["status"] = "terminal"
                    child["next_poll_not_before"] = None
                    child["failure_reason"] = None
                    child["terminal_receipt"] = event["terminal_receipt"]
        return {
            "batch_id": batch_id,
            "created_at": relevant[0]["occurred_at"],
            "children": list(children.values()),
            "append_only_event_count": len(relevant),
            "insight_required": (
                relevant[0].get("insight_required") is True
                or any(
                    str(row.get("event") or "").startswith(
                        "batch_insight_"
                    )
                    for row in relevant[1:]
                )
            ),
            "watched_artifacts_before": relevant[0].get(
                "watched_artifacts_before",
                [],
            ),
        }

    def status(self, batch_id: str) -> dict[str, Any]:
        with self._locked():
            return self._status_unlocked(batch_id)

    def _status_unlocked(self, batch_id: str) -> dict[str, Any]:
        state = self._state(batch_id)
        if state is None:
            raise BatchError("batch does not exist")
        now = self._time()
        for child in state["children"]:
            registered = _parse_time(
                child["registered_at"],
                field="registered_at",
            )
            age_steps = max(
                0,
                int((now - registered).total_seconds()) // MIN_ASYNC_POLL_SECONDS,
            )
            child["effective_priority"] = int(child["priority"]) + age_steps
        state["children"].sort(
            key=lambda row: (
                -int(row["effective_priority"]),
                row["registered_at"],
                row["child_id"],
            )
        )
        state["status"] = (
            "completed"
            if all(row["status"] == "terminal" for row in state["children"])
            else "running"
        )
        state["batch_insight"] = self._batch_insight_status_unlocked(
            batch_id,
            required=state["insight_required"],
        )
        state["coordinator_source_video_bytes"] = 0
        return state

    def _batch_insight_status_unlocked(
        self,
        batch_id: str,
        *,
        required: bool,
    ) -> dict[str, Any]:
        events = [
            row
            for row in self._events_unlocked()
            if row.get("batch_id") == batch_id
        ]
        claims = [
            row
            for row in events
            if row.get("event") == "batch_insight_delivery_claimed"
        ]
        receipts = [
            row
            for row in events
            if row.get("event") == "batch_insight_delivery_receipted"
        ]
        aggregates = [
            row
            for row in events
            if row.get("event") == "batch_insight_delivered"
        ]
        if not claims:
            return {
                "status": "pending" if required else "not_required",
                "insight_id": "",
                "content_sha256": "",
                "message_utf8_bytes": 0,
                "chunk_count": 0,
                "recipient_count": 0,
                "recipient_receipt_count": 0,
                "uncertain_recipient_count": 0,
            }
        claim_by_key = {
            str(row.get("idempotency_key") or ""): row for row in claims
        }
        receipt_by_key = {
            str(row.get("idempotency_key") or ""): row for row in receipts
        }
        duplicate_keys = (
            len(claim_by_key) != len(claims)
            or len(receipt_by_key) != len(receipts)
        )
        uncertain = set(claim_by_key) - set(receipt_by_key)
        latest = aggregates[-1] if aggregates else claims[-1]
        delivered = (
            not duplicate_keys
            and not uncertain
            and len(aggregates) == 1
            and aggregates[0].get("status") == "delivered"
            and int(aggregates[0].get("recipient_count") or 0)
            == len(claim_by_key)
            == len(receipt_by_key)
            and int(
                aggregates[0].get("recipient_receipt_count") or 0
            )
            == len(receipt_by_key)
            and all(
                row.get("status") == "delivered"
                and row.get("insight_id") == aggregates[0].get("insight_id")
                and row.get("content_sha256")
                == aggregates[0].get("content_sha256")
                for row in receipts
            )
            and all(
                row.get("insight_id") == aggregates[0].get("insight_id")
                and row.get("content_sha256")
                == aggregates[0].get("content_sha256")
                for row in claims
            )
        )
        status = (
            "delivered"
            if delivered
            else "uncertain"
            if uncertain
            else "invalid"
        )
        return {
            "status": status,
            "insight_id": str(latest.get("insight_id") or ""),
            "content_sha256": str(latest.get("content_sha256") or ""),
            "message_utf8_bytes": int(
                latest.get("message_utf8_bytes") or 0
            ),
            "chunk_count": int(latest.get("chunk_count") or 0),
            "recipient_count": len(claim_by_key),
            "recipient_receipt_count": len(receipt_by_key),
            "uncertain_recipient_count": len(uncertain),
        }

    def _record_runner_event(
        self,
        batch_id: str,
        event: str,
        **fields: Any,
    ) -> dict[str, Any]:
        process_id = os.getpid()
        if process_id <= 0:
            raise BatchError("runner process id is invalid")
        with self._locked():
            if self._state(batch_id) is None:
                raise BatchError("batch does not exist")
            return self._append(
                event,
                batch_id=batch_id,
                process_id=process_id,
                **fields,
            )

    def record_runner_started(
        self,
        batch_id: str,
    ) -> dict[str, Any]:
        return self._record_runner_event(
            batch_id,
            "batch_runner_started",
            coordinator_source_video_bytes=0,
        )

    def record_interruption(
        self,
        batch_id: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise BatchError("interruption reason is required")
        return self._record_runner_event(
            batch_id,
            "batch_runner_interrupted",
            reason=reason.strip(),
            coordinator_source_video_bytes=0,
        )

    def record_runner_completed(
        self,
        batch_id: str,
    ) -> dict[str, Any]:
        with self._locked():
            state = self._status_unlocked(batch_id)
            if state["status"] != "completed":
                raise BatchError("runner cannot complete an unfinished batch")
            if (
                state["insight_required"]
                and state["batch_insight"]["status"] != "delivered"
            ):
                raise BatchError(
                    "runner cannot complete before batch insight delivery"
                )
            return self._record_runner_event(
                batch_id,
                "batch_runner_completed",
                coordinator_source_video_bytes=0,
            )

    def _normalize_insight(
        self,
        batch_id: str,
        insight: dict[str, Any],
        *,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not isinstance(insight, dict)
            or insight.get("batch_id") != batch_id
        ):
            raise BatchError("batch insight identity is invalid")
        title = str(insight.get("title") or "").strip()
        body = str(insight.get("body") or "").strip()
        if not title or not body:
            raise BatchError("batch insight title and body are required")
        raw_bindings = insight.get("evidence_bindings")
        if not isinstance(raw_bindings, list):
            raise BatchError("batch insight evidence bindings are required")
        bindings: list[dict[str, str]] = []
        for value in raw_bindings:
            if not isinstance(value, dict):
                raise BatchError(
                    "batch insight evidence bindings are invalid"
                )
            binding = {
                "adapter": str(value.get("adapter") or ""),
                "evidence_sha256": str(
                    value.get("evidence_sha256") or ""
                ),
                "decision_result_sha256": str(
                    value.get("decision_result_sha256") or ""
                ),
            }
            if (
                binding["adapter"] not in SUPPORTED_ADAPTERS
                or not _is_sha256(binding["evidence_sha256"])
                or not _is_sha256(binding["decision_result_sha256"])
            ):
                raise BatchError(
                    "batch insight evidence bindings are invalid"
                )
            bindings.append(binding)
        expected = []
        for child in state["children"]:
            receipt = child.get("terminal_receipt")
            if (
                not isinstance(receipt, dict)
                or receipt.get("disposition") in TERMINAL_DISPOSITIONS
            ):
                continue
            expected.append({
                "adapter": str(child["adapter"]),
                "evidence_sha256": str(
                    receipt.get("evidence_sha256") or ""
                ),
                "decision_result_sha256": str(
                    receipt.get("decision_result_sha256") or ""
                ),
            })
        if sorted(map(_canonical, bindings)) != sorted(
            map(_canonical, expected)
        ):
            raise BatchError(
                "batch insight evidence bindings do not match all children"
            )
        message = f"{title}\n{body}"
        message_utf8_bytes = len(message.encode("utf-8"))
        if message_utf8_bytes > MAX_BATCH_INSIGHT_BYTES:
            raise BatchError(
                "batch insight exceeds the 2,048-byte safe-send contract"
            )
        content_sha256 = _sha256_text(message)
        public_bindings = bindings
        insight_id = _sha256_text(
            _canonical({
                "batch_id": batch_id,
                "content_sha256": content_sha256,
                "bindings": public_bindings,
            })
        )
        return {
            "title": title,
            "body": body,
            "content_sha256": content_sha256,
            "insight_id": insight_id,
            "evidence_bindings": public_bindings,
            "message_utf8_bytes": message_utf8_bytes,
            "chunk_count": 1,
        }

    def publish_insight(
        self,
        batch_id: str,
        insight: dict[str, Any],
        *,
        recipients: list[str],
        sender: Callable[[str, str, str], str],
    ) -> dict[str, Any]:
        normalized_recipients = tuple(
            dict.fromkeys(
                str(value).strip() for value in recipients if str(value).strip()
            )
        )
        if not normalized_recipients:
            raise BatchError("batch insight recipients are required")
        with self._locked():
            state = self._status_unlocked(batch_id)
            if state["status"] != "completed":
                raise BatchError(
                    "batch insight requires terminal child receipts"
                )
            normalized = self._normalize_insight(
                batch_id,
                insight,
                state=state,
            )
            prior_claims = [
                row
                for row in self._events_unlocked()
                if row.get("batch_id") == batch_id
                and row.get("event")
                == "batch_insight_delivery_claimed"
            ]
            if any(
                row.get("insight_id") != normalized["insight_id"]
                for row in prior_claims
            ):
                raise BatchError(
                    "batch insight content changed after a durable claim"
                )
            requested_recipient_keys = {
                _sha256_text(recipient)
                for recipient in normalized_recipients
            }
            recorded_recipient_keys = {
                str(row.get("recipient_key") or "")
                for row in prior_claims
            }
            if (
                recorded_recipient_keys
                and recorded_recipient_keys != requested_recipient_keys
            ):
                raise BatchError(
                    "batch insight recipient set changed after a durable claim"
                )

        new_send_count = 0
        receipt_count = 0
        for order, recipient in enumerate(normalized_recipients, start=1):
            recipient_key = _sha256_text(recipient)
            idempotency_key = _sha256_text(
                f"{normalized['insight_id']}\n{recipient_key}"
            )
            with self._locked():
                events = self._events_unlocked()
                receipts = [
                    row
                    for row in events
                    if row.get("batch_id") == batch_id
                    and row.get("event")
                    == "batch_insight_delivery_receipted"
                    and row.get("idempotency_key") == idempotency_key
                ]
                if receipts:
                    receipt_count += 1
                    continue
                claims = [
                    row
                    for row in events
                    if row.get("batch_id") == batch_id
                    and row.get("event")
                    == "batch_insight_delivery_claimed"
                    and row.get("idempotency_key") == idempotency_key
                ]
                if claims:
                    raise BatchError(
                        "uncertain prior batch insight delivery claim; "
                        "refusing blind resend"
                    )
                self._append(
                    "batch_insight_delivery_claimed",
                    batch_id=batch_id,
                    insight_id=normalized["insight_id"],
                    content_sha256=normalized["content_sha256"],
                    evidence_bindings=normalized["evidence_bindings"],
                    idempotency_key=idempotency_key,
                    recipient_key=recipient_key,
                    recipient_order=order,
                    recipient_count=len(normalized_recipients),
                    message_utf8_bytes=normalized["message_utf8_bytes"],
                    chunk_count=normalized["chunk_count"],
                    coordinator_source_video_bytes=0,
                )
            try:
                result = sender(
                    recipient,
                    normalized["title"],
                    normalized["body"],
                )
            except Exception:  # noqa: BLE001 - persist an uncertain claim
                result = "delivery_exception"
            if result != "ok":
                with self._locked():
                    self._append(
                        "batch_insight_delivery_failed",
                        batch_id=batch_id,
                        insight_id=normalized["insight_id"],
                        content_sha256=normalized["content_sha256"],
                        idempotency_key=idempotency_key,
                        recipient_key=recipient_key,
                        status="uncertain",
                        reason="relay_delivery_not_confirmed",
                        coordinator_source_video_bytes=0,
                    )
                raise BatchError(
                    "batch insight delivery was not confirmed; "
                    "claim remains uncertain"
                )
            receipt_fingerprint = _sha256_text(
                f"{idempotency_key}\nok"
            )[:16]
            with self._locked():
                self._append(
                    "batch_insight_delivery_receipted",
                    batch_id=batch_id,
                    insight_id=normalized["insight_id"],
                    content_sha256=normalized["content_sha256"],
                    idempotency_key=idempotency_key,
                    recipient_key=recipient_key,
                    status="delivered",
                    receipt=(
                        "wecom-relay://ok/"
                        f"{idempotency_key}/{receipt_fingerprint}"
                    ),
                    message_utf8_bytes=normalized["message_utf8_bytes"],
                    chunk_count=normalized["chunk_count"],
                    coordinator_source_video_bytes=0,
                )
            receipt_count += 1
            new_send_count += 1

        with self._locked():
            events = self._events_unlocked()
            aggregate = [
                row
                for row in events
                if row.get("batch_id") == batch_id
                and row.get("event") == "batch_insight_delivered"
                and row.get("insight_id") == normalized["insight_id"]
            ]
            if not aggregate:
                self._append(
                    "batch_insight_delivered",
                    batch_id=batch_id,
                    insight_id=normalized["insight_id"],
                    content_sha256=normalized["content_sha256"],
                    evidence_bindings=normalized["evidence_bindings"],
                    status="delivered",
                    recipient_count=len(normalized_recipients),
                    recipient_receipt_count=receipt_count,
                    message_utf8_bytes=normalized["message_utf8_bytes"],
                    chunk_count=normalized["chunk_count"],
                    new_external_side_effect_count=(
                        1 if new_send_count else 0
                    ),
                    coordinator_source_video_bytes=0,
                )
            elif len(aggregate) != 1:
                raise BatchError(
                    "batch insight has duplicate aggregate receipts"
                )
        return {
            "status": "delivered",
            "insight_id": normalized["insight_id"],
            "content_sha256": normalized["content_sha256"],
            "message_utf8_bytes": normalized["message_utf8_bytes"],
            "chunk_count": normalized["chunk_count"],
            "recipient_count": len(normalized_recipients),
            "recipient_receipt_count": receipt_count,
            "new_recipient_send_count": new_send_count,
            "new_external_side_effect_count": (
                1 if new_send_count else 0
            ),
            "idempotent_replay": new_send_count == 0,
        }

    def _receipt(self, child: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(child["receipt_path"]))
        value = _read_json(path, label=f"{child['adapter']} receipt")
        handoff_sha256 = ""
        if child["adapter"] == "xiaocao_live":
            handoff_sha256 = str(
                value.get("cloud_handoff", {}).get("handoff_sha256") or ""
            )
            if (
                value.get("ticket") != "03-xiaocao-live-to-decisions"
                or value.get("status") != "completed"
                or value.get("capture", {}).get("capture_job_id")
                != child["source_identity"]
                or value.get("capture", {}).get("media_sha256")
                != child["version_identity"]
                or value.get("cloud_handoff", {}).get(
                    "coordinator_large_payload_local_bytes"
                )
                != 0
                or not _is_sha256(handoff_sha256)
                or value.get("enrichment", {}).get(
                    "seven_row_trade_information_matrix_complete"
                )
                is not True
                or value.get("enrichment", {}).get("market_first") is not True
                or value.get("enrichment", {}).get(
                    "source_system_and_market_validation_separated"
                )
                is not True
                or value.get("side_effect_counts", {}).get(
                    "rerun_external_side_effects"
                )
                != 0
            ):
                raise BatchError("Ticket 03 receipt does not match child identity")
            household = _validate_household(value.get("household_output"))
            book = _validate_book(value.get("book_kol_us_output"))
            household_output = value.get("household_output") or {}
            chunk_sizes = household_output.get("utf8_chunk_sizes_bytes")
            if (
                household_output.get("status") == "delivered"
                and (
                    household_output.get("advisory_only") is not True
                    or household_output.get("utf8_chunk_limit_bytes") != 2048
                    or not isinstance(chunk_sizes, list)
                    or not chunk_sizes
                    or any(
                        not isinstance(size, int) or not 0 < size <= 2048
                        for size in chunk_sizes
                    )
                    or household_output.get(
                        "lossless_reassembly_verified"
                    )
                    is not True
                )
            ):
                raise BatchError(
                    "Ticket 03 household chunk contract is incomplete"
                )
            evidence_sha256 = str(
                value.get("enrichment", {}).get("transcript_sha256") or ""
            )
            decision_result_sha256 = str(
                value.get("enrichment", {}).get(
                    "decision_result_sha256"
                )
                or ""
            )
        elif child["adapter"] == "lv_text_image":
            if (
                value.get("event") != "subscription_decisions_completed"
                or value.get("status") != "decided"
                or value.get("identity") != child["source_identity"]
                or value.get("version_key") != child["version_identity"]
            ):
                raise BatchError("Ticket 04 receipt does not match child identity")
            result_path = Path(str(value.get("decision_result_path") or ""))
            expected = str(value.get("decision_result_sha256") or "")
            if (
                _sha256_small_json(
                    result_path,
                    label="Ticket 04 decision result",
                )
                != expected
            ):
                raise BatchError("Ticket 04 decision result hash changed")
            result = _read_json(
                result_path,
                label="Ticket 04 decision result",
            )
            bundle_path = Path(str(value.get("decision_bundle_path") or ""))
            bundle_sha256 = str(value.get("decision_bundle_sha256") or "")
            if (
                _sha256_small_json(
                    bundle_path,
                    label="Ticket 04 decision bundle",
                )
                != bundle_sha256
            ):
                raise BatchError("Ticket 04 decision bundle hash changed")
            bundle = _read_json(
                bundle_path,
                label="Ticket 04 decision bundle",
            )
            items = bundle.get("items")
            if not isinstance(items, list) or len(items) != 1:
                raise BatchError("Ticket 04 decision bundle item is invalid")
            item = items[0]
            result_items = result.get("items")
            result_item = (
                result_items[0]
                if isinstance(result_items, list) and len(result_items) == 1
                else None
            )
            coverage = (
                item.get("trade_information_coverage")
                if isinstance(item, dict)
                else None
            )
            if (
                not isinstance(item, dict)
                or not isinstance(result_item, dict)
                or item.get("decision_status")
                not in {"actionable_signal", "no_actionable_signal"}
                or item.get("knowledge_status")
                not in {"reusable_knowledge", "no_reusable_knowledge"}
                or not isinstance(item.get("market_outlook"), dict)
                or not isinstance(
                    item.get("market_outlook", {}).get(
                        "current_validation"
                    ),
                    dict,
                )
                or not isinstance(item.get("claims"), list)
                or not isinstance(item.get("synthesis"), dict)
                or not isinstance(coverage, dict)
                or set(coverage) != REQUIRED_COVERAGE_ROWS
                or any(
                    not isinstance(coverage_row, dict)
                    or coverage_row.get("status") not in {"present", "absent"}
                    or (
                        coverage_row.get("status") == "absent"
                        and not str(coverage_row.get("reason") or "").strip()
                    )
                    for coverage_row in coverage.values()
                )
            ):
                raise BatchError(
                    "Ticket 04 decision bundle coverage is incomplete"
                )
            household = _validate_household(value.get("household_notification"))
            state_book = value.get("book_kol_us")
            result_book = result_item.get("book_kol_us")
            if (
                not isinstance(state_book, dict)
                or not isinstance(result_book, dict)
                or any(
                    state_book.get(field) != result_book.get(field)
                    for field in (
                        "status",
                        "book",
                        "paper_only",
                        "ticker",
                        "side",
                        "idempotency_key",
                    )
                    if state_book.get(field) is not None
                )
            ):
                raise BatchError("Ticket 04 Book receipt binding changed")
            book = _validate_book(result_book)
            evidence_sha256 = str(result_item.get("evidence_sha256") or "")
            decision_result_sha256 = expected
        else:
            if (
                value.get("ticket") != "05-subscription-video-to-decisions"
                or value.get("status") != "completed"
                or not isinstance(value.get("samples"), list)
            ):
                raise BatchError("Ticket 05 acceptance receipt is invalid")
            matches = [
                row
                for row in value["samples"]
                if (
                    row.get("stable_identity_sha256")
                    == child["source_identity"]
                    and row.get("version_key") == child["version_identity"]
                )
            ]
            if len(matches) != 1:
                raise BatchError("Ticket 05 receipt does not match child identity")
            sample = matches[0]
            if child.get("source_parts"):
                logical_content = sample.get("logical_content")
                components = (
                    logical_content.get("components")
                    if isinstance(logical_content, dict)
                    else None
                )
                normalized_components = []
                if isinstance(components, list):
                    for component in components:
                        if not isinstance(component, dict):
                            normalized_components = []
                            break
                        normalized_components.append(
                            {
                                "source_identity": str(
                                    component.get("source_identity") or ""
                                ),
                                "version_identity": str(
                                    component.get("version_identity") or ""
                                ),
                                "part_index": component.get("part_index"),
                                "part_label": str(
                                    component.get("part_label")
                                    or component.get("part_index")
                                    or ""
                                ),
                                "source_path": str(
                                    component.get("source_path") or ""
                                ),
                                "source_size": component.get("source_size"),
                            }
                        )
                if (
                    not isinstance(logical_content, dict)
                    or logical_content.get("kind")
                    != "multi_part_episode"
                    or logical_content.get("part_count")
                    != len(child["source_parts"])
                    or logical_content.get("analyzed_once") is not True
                    or logical_content.get("household_terminal_once")
                    is not True
                    or logical_content.get("book_terminal_once") is not True
                    or normalized_components != child["source_parts"]
                ):
                    raise BatchError(
                        "Ticket 05 logical episode receipt changed its parts"
                    )
            decision = sample.get("decision_contract_audit")
            enrichment = sample.get("enrichment")
            transfer = sample.get("cloud_transfer")
            if (
                not isinstance(decision, dict)
                or not isinstance(enrichment, dict)
                or not isinstance(transfer, dict)
                or transfer.get("status")
                not in {
                    "completed",
                    "not_required_existing_private_file",
                }
                or (
                    transfer.get("status") == "completed"
                    and (
                        transfer.get("claim_before_trigger") is not True
                        or transfer.get("receipt_after_completion") is not True
                    )
                )
                or enrichment.get("large_payload_local_bytes") != 0
                or transfer.get("large_payload_local_bytes") != 0
                or set(decision.get("coverage_rows") or [])
                != REQUIRED_COVERAGE_ROWS
                or decision.get("market_first") is not True
                or decision.get(
                    "all_named_assets_resolved_or_explicitly_unresolved"
                )
                is not True
                or not isinstance(decision.get("xiaocao_cross_view"), dict)
            ):
                raise BatchError("Ticket 05 receipt is incomplete")
            household = _validate_household(decision.get("household"))
            book = _validate_book(decision.get("book_kol_us"))
            evidence_sha256 = str(enrichment.get("transcript_sha256") or "")
            decision_result_sha256 = str(
                decision.get("decision_result_sha256") or ""
            )
        if not _is_sha256(evidence_sha256):
            raise BatchError("terminal evidence SHA-256 is invalid")
        if not _is_sha256(decision_result_sha256):
            raise BatchError("terminal decision result SHA-256 is invalid")
        return {
            "receipt_path": str(path),
            "receipt_sha256": _sha256_file(path),
            "evidence_sha256": evidence_sha256,
            "decision_result_sha256": decision_result_sha256,
            "handoff_sha256": handoff_sha256,
            "household": household,
            "book_kol_us": book,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
            "new_external_side_effect_count": 0,
            "source_part_count": len(child.get("source_parts") or []),
        }

    def run_once(
        self,
        batch_id: str,
        *,
        max_children: int | None = None,
    ) -> dict[str, Any]:
        if max_children is not None and max_children <= 0:
            raise BatchError("max_children must be positive")
        with self._locked():
            state = self.status(batch_id)
            now = self._time()
            transitions = 0
            for child in state["children"]:
                if (
                    max_children is not None
                    and transitions >= max_children
                ):
                    break
                if child["status"] in {"terminal", "paused"}:
                    continue
                if child["status"] == "waiting_async":
                    due = _parse_time(
                        child["next_poll_not_before"],
                        field="next_poll_not_before",
                    )
                    if now < due:
                        continue
                    requested = _parse_time(
                        child["async_requested_at"],
                        field="async_requested_at",
                    )
                    if (
                        int(child["retry_count"]) == 0
                        and (now - requested).total_seconds()
                        < MIN_ASYNC_POLL_SECONDS
                    ):
                        raise BatchError(
                            "first async poll cannot occur before five minutes"
                        )
                    self._append(
                        "child_async_poll_claimed",
                        batch_id=batch_id,
                        child_id=child["child_id"],
                        status="polling",
                        claim_id=_sha256_text(
                            f"{batch_id}\n{child['child_id']}\npoll\n"
                            f"{child['retry_count']}"
                        ),
                        retry_count=child["retry_count"],
                        failure_reason=child["failure_reason"],
                        next_poll_not_before=None,
                        large_payload_local_bytes=0,
                    )
                    transitions += 1
                if child["status"] == "registered":
                    claim_id = _sha256_text(
                        f"{batch_id}\n{child['child_id']}\nreconcile"
                    )
                    self._append(
                        "child_reconciliation_claimed",
                        batch_id=batch_id,
                        child_id=child["child_id"],
                        status="reconciling",
                        claim_id=claim_id,
                        retry_count=child["retry_count"],
                        failure_reason=None,
                        next_poll_not_before=None,
                        large_payload_local_bytes=0,
                    )
                    transitions += 1
                elif child["status"] == "polling":
                    receipt_path = Path(str(child["receipt_path"]))
                    if receipt_path.is_file():
                        try:
                            receipt = self._receipt(child)
                        except BatchError as exc:
                            self._append(
                                "child_paused",
                                batch_id=batch_id,
                                child_id=child["child_id"],
                                status="paused",
                                retry_count=child["retry_count"],
                                failure_reason="missing_evidence",
                                failure_detail=str(exc),
                                next_poll_not_before=None,
                                large_payload_local_bytes=0,
                            )
                        else:
                            self._append(
                                "child_terminal",
                                batch_id=batch_id,
                                child_id=child["child_id"],
                                status="terminal",
                                retry_count=child["retry_count"],
                                failure_reason=None,
                                next_poll_not_before=None,
                                terminal_receipt=receipt,
                                large_payload_local_bytes=0,
                            )
                        transitions += 1
                    else:
                        retry_count = int(child["retry_count"]) + 1
                        delay_seconds = MIN_ASYNC_POLL_SECONDS * (
                            2 ** retry_count
                        )
                        self._append(
                            "child_retry_scheduled",
                            batch_id=batch_id,
                            child_id=child["child_id"],
                            status="waiting_async",
                            retry_count=retry_count,
                            failure_reason="async_receipt_not_ready",
                            next_poll_not_before=(
                                now + timedelta(seconds=delay_seconds)
                            ).isoformat(),
                            large_payload_local_bytes=0,
                        )
                        transitions += 1
                elif child["status"] == "reconciling":
                    try:
                        receipt = self._receipt(child)
                    except BatchError as exc:
                        self._append(
                            "child_paused",
                            batch_id=batch_id,
                            child_id=child["child_id"],
                            status="paused",
                            retry_count=child["retry_count"],
                            failure_reason="missing_evidence",
                            failure_detail=str(exc),
                            next_poll_not_before=None,
                            large_payload_local_bytes=0,
                        )
                    else:
                        self._append(
                            "child_terminal",
                            batch_id=batch_id,
                            child_id=child["child_id"],
                            status="terminal",
                            retry_count=child["retry_count"],
                            failure_reason=None,
                            next_poll_not_before=None,
                            terminal_receipt=receipt,
                            large_payload_local_bytes=0,
                        )
                    transitions += 1
        return self.status(batch_id)

    def audit(self, batch_id: str) -> dict[str, Any]:
        with self._locked():
            return self._audit_unlocked(batch_id)

    def _audit_unlocked(self, batch_id: str) -> dict[str, Any]:
        state = self.status(batch_id)
        events = [
            row for row in self.events() if row.get("batch_id") == batch_id
        ]
        terminal_events = [
            row for row in events if row.get("event") == "child_terminal"
        ]
        runner_starts = [
            row for row in events if row.get("event") == "batch_runner_started"
        ]
        interruptions = [
            row
            for row in events
            if row.get("event") == "batch_runner_interrupted"
        ]
        polls = [
            row
            for row in events
            if row.get("event") == "child_async_poll_claimed"
        ]
        retries = [
            row
            for row in events
            if row.get("event") == "child_retry_scheduled"
        ]
        registrations: dict[str, dict[str, Any]] = {}
        batch_created = next(
            row for row in events if row.get("event") == "batch_created"
        )
        for embedded in batch_created.get("children", []):
            registration = {
                **embedded,
                "event": "child_registered",
                "occurred_at": batch_created["occurred_at"],
            }
            registrations[str(registration["child_id"])] = registration
        registrations.update(
            {
                str(row["child_id"]): row
                for row in events
                if row.get("event") == "child_registered"
            }
        )
        first_poll_valid = True
        poll_by_child: dict[str, list[dict[str, Any]]] = {}
        for poll in polls:
            poll_by_child.setdefault(str(poll["child_id"]), []).append(poll)
        async_children = [
            row
            for row in registrations.values()
            if row.get("async_requested_at") is not None
        ]
        for child in async_children:
            child_polls = poll_by_child.get(str(child["child_id"]), [])
            if not child_polls:
                first_poll_valid = False
                continue
            requested = _parse_time(
                child["async_requested_at"],
                field="async_requested_at",
            )
            first = _parse_time(
                child_polls[0]["occurred_at"],
                field="occurred_at",
            )
            if (first - requested).total_seconds() < MIN_ASYNC_POLL_SECONDS:
                first_poll_valid = False

        retry_valid = True
        for retry in retries:
            scheduled = _parse_time(
                retry["next_poll_not_before"],
                field="next_poll_not_before",
            )
            created = _parse_time(
                retry["occurred_at"],
                field="occurred_at",
            )
            expected = MIN_ASYNC_POLL_SECONDS * (
                2 ** int(retry["retry_count"])
            )
            if (scheduled - created).total_seconds() < expected:
                retry_valid = False

        terminal_by_child: dict[str, list[dict[str, Any]]] = {}
        for event in terminal_events:
            terminal_by_child.setdefault(str(event["child_id"]), []).append(
                event
            )
        completed_not_replayed = all(
            len(terminal_by_child.get(str(child["child_id"]), [])) == 1
            for child in state["children"]
            if child["status"] == "terminal"
            and not child.get("failure_reason")
        )

        first_poll_at = min(
            (
                _parse_time(row["occurred_at"], field="occurred_at")
                for row in polls
            ),
            default=None,
        )
        ready_terminal_before_poll = (
            first_poll_at is not None
            and any(
                _parse_time(row["occurred_at"], field="occurred_at")
                < first_poll_at
                and registrations[str(row["child_id"])].get(
                    "async_requested_at"
                )
                is None
                for row in terminal_events
            )
        )
        restart_valid = False
        unfinished_child_at_interruption = False
        if len(runner_starts) >= 2 and interruptions:
            interruption = min(
                interruptions,
                key=lambda row: _parse_time(
                    row["occurred_at"],
                    field="occurred_at",
                ),
            )
            interrupted_at = _parse_time(
                interruption["occurred_at"],
                field="occurred_at",
            )
            terminal_at = {
                str(row["child_id"]): _parse_time(
                    row["occurred_at"],
                    field="occurred_at",
                )
                for row in terminal_events
            }
            for child_id, registration in registrations.items():
                registered_at = _parse_time(
                    registration["occurred_at"],
                    field="occurred_at",
                )
                initially_terminal = registration.get("status") == "terminal"
                completed_at = (
                    registered_at
                    if initially_terminal
                    else terminal_at.get(str(child_id))
                )
                if (
                    registered_at <= interrupted_at
                    and (
                        completed_at is None
                        or completed_at > interrupted_at
                    )
                ):
                    unfinished_child_at_interruption = True
                    break
            interrupted_process_id = int(interruption["process_id"])
            matching_start_before = any(
                int(row["process_id"]) == interrupted_process_id
                and _parse_time(row["occurred_at"], field="occurred_at")
                <= interrupted_at
                for row in runner_starts
            )
            restart_valid = matching_start_before and any(
                int(row["process_id"]) != interrupted_process_id
                and _parse_time(row["occurred_at"], field="occurred_at")
                > interrupted_at
                for row in runner_starts
            )

        actual_watch = self._snapshot_artifacts(
            [
                {
                    "path": row["path"],
                    "roles": row.get("roles", []),
                }
                for row in state["watched_artifacts_before"]
            ]
        )
        watch_unchanged = (
            actual_watch == state["watched_artifacts_before"]
        )
        watched_roles = {
            role
            for row in state["watched_artifacts_before"]
            for role in row.get("roles", [])
        }
        required_watchers_present = REQUIRED_WATCH_ROLES <= watched_roles
        active_children = list(state["children"])
        receipts_revalidated = True
        for child in active_children:
            if child["status"] != "terminal":
                receipts_revalidated = False
                continue
            recorded_receipt = child.get("terminal_receipt")
            if (
                isinstance(recorded_receipt, dict)
                and recorded_receipt.get("disposition")
                in TERMINAL_DISPOSITIONS
            ):
                if (
                    recorded_receipt.get("household", {}).get("status")
                    != "suppressed"
                    or recorded_receipt.get("book_kol_us", {}).get("status")
                    != "no_trade"
                ):
                    receipts_revalidated = False
                continue
            try:
                current_receipt = self._receipt(child)
            except BatchError:
                receipts_revalidated = False
                continue
            if (
                not isinstance(recorded_receipt, dict)
                or current_receipt["receipt_sha256"]
                != recorded_receipt.get("receipt_sha256")
                or current_receipt["evidence_sha256"]
                != recorded_receipt.get("evidence_sha256")
                or current_receipt["decision_result_sha256"]
                != recorded_receipt.get("decision_result_sha256")
            ):
                receipts_revalidated = False
        terminal_outputs = all(
            (
                row["status"] == "terminal"
                and isinstance(row.get("terminal_receipt"), dict)
                and row["terminal_receipt"].get("household", {}).get("status")
                in TERMINAL_HOUSEHOLD_STATUSES
                and row["terminal_receipt"].get("book_kol_us", {}).get(
                    "status"
                )
                in TERMINAL_BOOK_STATUSES
            )
            for row in active_children
        ) and receipts_revalidated
        verified_source_children = [
            row
            for row in active_children
            if not (
                isinstance(row.get("terminal_receipt"), dict)
                and row["terminal_receipt"].get("disposition")
                in TERMINAL_DISPOSITIONS
            )
        ]
        batch_insight_events = [
            row
            for row in events
            if str(row.get("event") or "").startswith(
                "batch_insight_"
            )
        ]
        insight_aggregates = [
            row
            for row in batch_insight_events
            if row.get("event") == "batch_insight_delivered"
        ]
        expected_insight_bindings = []
        for child in active_children:
            receipt = child.get("terminal_receipt")
            if (
                not isinstance(receipt, dict)
                or receipt.get("disposition") in TERMINAL_DISPOSITIONS
            ):
                continue
            expected_insight_bindings.append({
                "adapter": str(child["adapter"]),
                "evidence_sha256": str(
                    receipt.get("evidence_sha256") or ""
                ),
                "decision_result_sha256": str(
                    receipt.get("decision_result_sha256") or ""
                ),
            })
        recorded_insight_bindings = (
            insight_aggregates[0].get("evidence_bindings", [])
            if len(insight_aggregates) == 1
            else []
        )
        insight_bindings_valid = (
            not state["insight_required"]
            or (
                isinstance(recorded_insight_bindings, list)
                and sorted(
                    _canonical(row)
                    for row in recorded_insight_bindings
                    if isinstance(row, dict)
                )
                == sorted(map(_canonical, expected_insight_bindings))
                and len(recorded_insight_bindings)
                == len(expected_insight_bindings)
            )
        )
        audited_batch_insight = {
            **state["batch_insight"],
            "evidence_bindings_valid": insight_bindings_valid,
        }
        zero_video_bytes = (
            state.get("coordinator_source_video_bytes") == 0
            and all(
                row.get("large_payload_local_bytes") == 0
                and (
                    not isinstance(row.get("terminal_receipt"), dict)
                    or row["terminal_receipt"].get(
                        "coordinator_source_video_bytes"
                    )
                    == 0
                )
                for row in state["children"]
            )
            and all(
                row.get("coordinator_source_video_bytes") == 0
                for row in batch_insight_events
            )
        )
        requirements = {
            "two_real_videos_and_one_text_or_image": (
                sum(
                    row["media_type"] == "video"
                    for row in verified_source_children
                )
                >= 2
                and any(
                    row["media_type"] in {"text", "image"}
                    for row in verified_source_children
                )
            ),
            "broadband_handoff_and_subscription_combined": (
                any(
                    row["adapter"] == "xiaocao_live"
                    for row in verified_source_children
                )
                and any(
                    row["adapter"]
                    in {"lv_text_image", "subscription_video"}
                    for row in verified_source_children
                )
            ),
            "waiting_child_did_not_block_ready_children": (
                ready_terminal_before_poll
            ),
            "first_poll_not_before_five_minutes": first_poll_valid,
            "explicit_backoff": retry_valid,
            "real_process_interruption_and_restart": restart_valid,
            "unfinished_child_at_interruption": (
                unfinished_child_at_interruption
            ),
            "independent_household_and_book_terminals": terminal_outputs,
            "completed_children_not_replayed": completed_not_replayed,
            "watched_side_effect_artifacts_unchanged": watch_unchanged,
            "required_side_effect_watchers_present": (
                required_watchers_present
            ),
            "coordinator_source_video_bytes_zero": zero_video_bytes,
            "batch_insight_delivered": (
                not state["insight_required"]
                or (
                    state["batch_insight"]["status"] == "delivered"
                    and insight_bindings_valid
                )
            ),
        }
        insight_side_effects = sum(
            int(row.get("new_external_side_effect_count") or 0)
            for row in batch_insight_events
            if row.get("event") == "batch_insight_delivered"
        )
        return {
            "schema_version": 1,
            "ticket": "06-resumable-multisource-batch",
            "batch_id": batch_id,
            "status": (
                "accepted"
                if state["status"] == "completed"
                and all(requirements.values())
                else "incomplete"
            ),
            "requirements": requirements,
            "runner_start_count": len(runner_starts),
            "interruption_count": len(interruptions),
            "terminal_receipt_count": len(terminal_events),
            "retry_count": len(retries),
            "backoff_schedule_seconds": [300, 600, 1200, 2400, 4800],
            "new_external_side_effect_count": sum(
                int(
                    row.get("terminal_receipt", {}).get(
                        "new_external_side_effect_count",
                        0,
                    )
                )
                for row in terminal_events
            )
            + insight_side_effects,
            "coordinator_source_video_bytes": 0,
            "batch_insight": audited_batch_insight,
            "watched_artifacts_before": state["watched_artifacts_before"],
            "watched_artifacts_after": actual_watch,
            "children": state["children"],
        }
