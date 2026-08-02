"""Exact-recipient transport handoff for cross-node KOL reminders."""

from __future__ import annotations

import fcntl
import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from ._shared import append_jsonl, canonical, now_iso, parse_iso, read_jsonl


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HTTPS_URL = re.compile(r"https://[^\s]+")


class NotificationTransportError(ValueError):
    """A reminder cannot be transported without violating exact-once safety."""


class NotificationTransport:
    """Send a self-hashed remote reminder request on an approved transport node.

    The business writer owns the notification identity and final receipt.  This
    class only owns per-recipient relay calls and their append-only transport
    evidence, so a successful recipient is never retried after a partial run.
    """

    def __init__(
        self,
        output_dir: Path | str,
        *,
        configured_recipients: Callable[[], tuple[str, ...]],
    ):
        self.output_dir = Path(output_dir)
        self.events_path = self.output_dir / "events.jsonl"
        self.lock_path = self.output_dir / ".transport.lock"
        self.configured_recipients = configured_recipients

    @staticmethod
    def _validate(request: dict[str, Any]) -> None:
        if request.get("schema_version") != 1:
            raise NotificationTransportError("notification handoff schema is invalid")
        handoff_id = str(request.get("handoff_id") or "")
        unsigned = dict(request)
        unsigned.pop("handoff_id", None)
        if (
            not _SHA256.fullmatch(handoff_id)
            or hashlib.sha256(canonical(unsigned).encode()).hexdigest() != handoff_id
        ):
            raise NotificationTransportError("notification handoff hash is invalid")
        for field in (
            "notification_id",
            "report_id",
            "stable_report_url",
            "title",
            "body",
            "content_sha256",
        ):
            if not str(request.get(field) or "").strip():
                raise NotificationTransportError(
                    f"notification handoff requires {field}"
                )
        source_task = request.get("source_task") or {}
        if any(
            not str(source_task.get(field) or "").strip()
            for field in ("host_id", "thread_id")
        ):
            raise NotificationTransportError(
                "notification handoff requires its source task identity"
            )
        confirmation = request.get("missing_confirmation") or {}
        if (
            confirmation.get("kind") != "recipient_missing_confirmation"
            or not str(confirmation.get("reference") or "").strip()
            or not str(confirmation.get("confirmed_at") or "").strip()
        ):
            raise NotificationTransportError(
                "notification handoff requires missing-recipient confirmation"
            )
        try:
            parse_iso(
                confirmation["confirmed_at"],
                field="missing_confirmation.confirmed_at",
            )
        except ValueError as exc:
            raise NotificationTransportError(str(exc)) from exc
        original_failure = request.get("original_failure") or {}
        if (
            not str(original_failure.get("status") or "").strip()
            or original_failure.get("delivered_recipients") != []
        ):
            raise NotificationTransportError(
                "notification handoff original failure is not safely bounded"
            )
        recipients = request.get("recipients")
        if (
            not isinstance(recipients, list)
            or not recipients
            or len(recipients) != len(set(recipients))
            or any(not isinstance(value, str) or not value.strip() for value in recipients)
        ):
            raise NotificationTransportError(
                "notification handoff recipients are invalid"
            )
        title = str(request["title"])
        body = str(request["body"])
        expected_content = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()
        if request.get("content_sha256") != expected_content:
            raise NotificationTransportError(
                "notification handoff content hash is invalid"
            )
        urls = _HTTPS_URL.findall(body)
        stable_url = str(request["stable_report_url"])
        if urls != [stable_url] or not body.rstrip().endswith(stable_url):
            raise NotificationTransportError(
                "notification body must end with exactly one stable report URL"
            )
        if len(f"{title}\n{body}".encode()) > 2_048:
            raise NotificationTransportError(
                "notification handoff exceeds the 2048-byte safe-send limit"
            )

    @staticmethod
    def _last_recipient_states(
        events: list[dict[str, Any]],
        handoff_id: str,
    ) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        for row in events:
            if row.get("handoff_id") != handoff_id:
                continue
            if row.get("event") in {
                "recipient_send_claimed",
                "recipient_send_failed",
                "recipient_send_uncertain",
                "recipient_delivered",
            }:
                states[str(row.get("recipient"))] = row
        return states

    @staticmethod
    def _receipt(
        request: dict[str, Any],
        states: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        recipient_receipts = {
            recipient: {
                "receipt": state["receipt"],
                "delivered_at": state["delivered_at"],
            }
            for recipient, state in states.items()
            if state.get("event") == "recipient_delivered"
        }
        receipt: dict[str, Any] = {
            "schema_version": 1,
            "status": "delivered",
            "handoff_id": request["handoff_id"],
            "notification_id": request["notification_id"],
            "report_id": request["report_id"],
            "stable_report_url": request["stable_report_url"],
            "content_sha256": request["content_sha256"],
            "recipient_receipts": recipient_receipts,
        }
        receipt["receipt_sha256"] = hashlib.sha256(
            canonical(receipt).encode()
        ).hexdigest()
        return receipt

    def send(
        self,
        request: dict[str, Any],
        *,
        sender: Callable[[str, str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        self._validate(request)
        recipients = tuple(request["recipients"])
        configured = set(self.configured_recipients())
        unconfigured = [value for value in recipients if value not in configured]
        if unconfigured:
            raise NotificationTransportError(
                "notification recipient is not configured on this transport node: "
                + ", ".join(unconfigured)
            )

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            events = read_jsonl(self.events_path)
            handoff_id = str(request["handoff_id"])
            states = self._last_recipient_states(events, handoff_id)
            if all(
                (states.get(recipient) or {}).get("event") == "recipient_delivered"
                for recipient in recipients
            ):
                return self._receipt(request, states)

            for recipient in recipients:
                state = states.get(recipient) or {}
                if state.get("event") == "recipient_delivered":
                    continue
                if state.get("event") in {
                    "recipient_send_claimed",
                    "recipient_send_uncertain",
                }:
                    raise NotificationTransportError(
                        f"notification outcome is uncertain for {recipient}"
                    )
                claim = {
                    "event": "recipient_send_claimed",
                    "handoff_id": handoff_id,
                    "notification_id": request["notification_id"],
                    "recipient": recipient,
                    "content_sha256": request["content_sha256"],
                    "claimed_at": now_iso(),
                }
                append_jsonl(self.events_path, claim)
                states[recipient] = claim
                try:
                    result = sender(request["title"], request["body"], recipient)
                except Exception as exc:
                    uncertain = {
                        "event": "recipient_send_uncertain",
                        "handoff_id": handoff_id,
                        "notification_id": request["notification_id"],
                        "recipient": recipient,
                        "status": f"raised: {type(exc).__name__}",
                        "recorded_at": now_iso(),
                    }
                    append_jsonl(self.events_path, uncertain)
                    states[recipient] = uncertain
                    raise NotificationTransportError(
                        f"notification outcome is uncertain for {recipient}"
                    ) from exc
                if result.get("status") == "ok":
                    delivered_at = now_iso()
                    delivered = {
                        "event": "recipient_delivered",
                        "handoff_id": handoff_id,
                        "notification_id": request["notification_id"],
                        "recipient": recipient,
                        "content_sha256": request["content_sha256"],
                        "receipt": (
                            f"wecom-relay://ok/{handoff_id}/{recipient}/"
                            f"{request['content_sha256'][:16]}"
                        ),
                        "delivered_at": delivered_at,
                    }
                    append_jsonl(self.events_path, delivered)
                    states[recipient] = delivered
                    continue
                if result.get("retry_safety") == "safe":
                    failed = {
                        "event": "recipient_send_failed",
                        "handoff_id": handoff_id,
                        "notification_id": request["notification_id"],
                        "recipient": recipient,
                        "status": str(result.get("detail") or "failed"),
                        "failure_phase": result.get("failure_phase"),
                        "recorded_at": now_iso(),
                    }
                    append_jsonl(self.events_path, failed)
                    states[recipient] = failed
                    raise NotificationTransportError(
                        f"notification failed for {recipient}; safe retry is allowed"
                    )
                uncertain = {
                    "event": "recipient_send_uncertain",
                    "handoff_id": handoff_id,
                    "notification_id": request["notification_id"],
                    "recipient": recipient,
                    "status": str(result.get("detail") or "uncertain"),
                    "failure_phase": result.get("failure_phase"),
                    "recorded_at": now_iso(),
                }
                append_jsonl(self.events_path, uncertain)
                states[recipient] = uncertain
                raise NotificationTransportError(
                    f"notification outcome is uncertain for {recipient}"
                )

            receipt = self._receipt(request, states)
            append_jsonl(
                self.events_path,
                {
                    "event": "transport_delivered",
                    "handoff_id": handoff_id,
                    "notification_id": request["notification_id"],
                    "receipt": receipt,
                    "recorded_at": now_iso(),
                },
            )
            return receipt
