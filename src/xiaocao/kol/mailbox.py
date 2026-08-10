"""Deterministic LiangHuiMCP mailbox exchange for KOL handoffs."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .enrichment_types import EnrichmentDiagnosticError, EnrichmentError
from .writer_progress import (
    FailureFingerprint,
    ProgressContractError,
    WriterProgress,
    resolve_repository_revision,
)


MAILBOX_ID = "kol.handoff"
MAILBOX_MESSAGE_TYPE = "xiaocao.kol_handoff"
MAILBOX_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[a-f0-9]{64}")
_UTC_MILLISECONDS = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"
)
_OBJECT_PREFIX = {"article": "文章", "video": "视频"}


class MailboxError(EnrichmentError):
    """The mailbox request, response, or ledger could not be proved."""


def _exception_code(exc: Exception) -> str:
    """Return a stable progress-safe token for an unstructured exception."""

    name = type(exc).__name__
    token = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    token = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", token)
    token = re.sub(r"[^a-z0-9_]+", "_", token.lower()).strip("_")
    if not token or not token[0].isalpha():
        return "processor_exception"
    return token[:64].rstrip("_") or "processor_exception"


def _empty_claim_receipt_summary() -> dict[str, int]:
    return {
        "claim_count": 0,
        "receipt_count": 0,
        "uncertain_effect_count": 0,
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc_now(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None:
        raise MailboxError("mailbox clock needs a timezone")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _required_id(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 200:
        raise MailboxError(f"mailbox {field} is invalid")
    return normalized


class MailboxLedger:
    """Small append-only receipt ledger shared by local and remote adapters."""

    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {"schema_version": 1, "event": event, **fields}
        row["event_id"] = _sha256(row)
        payload = (_canonical(row) + "\n").encode("utf-8")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.events_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise MailboxError("mailbox ledger append made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return row

    def events(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise MailboxError("mailbox ledger cannot be read") from exc
        for number, line in enumerate(lines, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MailboxError(
                    f"mailbox ledger line {number} is invalid"
                ) from exc
            if not isinstance(row, dict):
                raise MailboxError(f"mailbox ledger line {number} is invalid")
            event_id = str(row.get("event_id") or "")
            unsigned = dict(row)
            unsigned.pop("event_id", None)
            if event_id != _sha256(unsigned):
                raise MailboxError(
                    f"mailbox ledger line {number} failed integrity validation"
                )
            rows.append(row)
        return rows

    def _handoff_states(self) -> tuple[dict[str, dict[str, Any]], set[str]]:
        sent: dict[str, dict[str, Any]] = {}
        acked: set[str] = set()
        for row in self.events():
            handoff_id = str(row.get("handoff_id") or "")
            if row.get("event") in {
                "mailbox_send_attempted",
                "mailbox_send_receipted",
                "mailbox_send_reconciled",
            }:
                prior = sent.get(handoff_id)
                if prior is not None and (
                    prior.get("content_sha256") != row.get("content_sha256")
                    or prior.get("object_kind") != row.get("object_kind")
                    or prior.get("title") != row.get("title")
                ):
                    raise MailboxError("mailbox send claim changed")
                sent[handoff_id] = row
            elif row.get("event") == "mailbox_ack_observed":
                acked.add(handoff_id)
        return sent, acked

    def handoff_state(self, handoff_id: str) -> dict[str, Any] | None:
        sent, _acked = self._handoff_states()
        state = sent.get(str(handoff_id))
        return dict(state) if state is not None else None

    def outstanding_handoffs(self) -> list[dict[str, Any]]:
        sent, acked = self._handoff_states()
        return [sent[key] for key in sorted(sent) if key not in acked]

    def _repair_state(
        self,
        handoff_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, bool, set[str]]:
        normalized_id = str(handoff_id or "")
        if not _SHA256.fullmatch(normalized_id):
            raise MailboxError("mailbox repair handoff_id is invalid")
        attempt: dict[str, Any] | None = None
        waiting: dict[str, Any] | None = None
        acked = False
        used_revisions: set[str] = set()
        waiting_events: dict[str, dict[str, Any]] = {}
        for row in self.events():
            if str(row.get("handoff_id") or "") != normalized_id:
                continue
            event = str(row.get("event") or "")
            if event in {
                "mailbox_message_attempted",
                "mailbox_message_repair_resumed",
            }:
                attempt = row
                waiting = None
                if event == "mailbox_message_repair_resumed":
                    used_revisions.add(str(row.get("repair_revision") or ""))
            elif event == "mailbox_message_waiting" and attempt is not None:
                waiting = row
                waiting_events[str(row.get("event_id") or "")] = row
            elif event == "mailbox_ack_receipted":
                acked = True
        if (
            attempt is not None
            and attempt.get("event") == "mailbox_message_repair_resumed"
            and waiting is None
        ):
            prior_waiting_event_id = str(
                attempt.get("prior_waiting_event_id") or ""
            )
            prior_waiting = waiting_events.get(prior_waiting_event_id)
            failure_revision = str(attempt.get("repair_revision") or "")
            if prior_waiting is not None and re.fullmatch(
                r"[a-f0-9]{40}", failure_revision
            ):
                fingerprint = FailureFingerprint(
                    adapter="mailbox",
                    category="control_plane_handler_error",
                    code="mailbox_resume_interrupted",
                    stage="mailbox_resume",
                    failure_revision=failure_revision,
                    provider_contract_version="lianghui_mailbox_v1",
                )
                waiting = {
                    "event_id": prior_waiting_event_id,
                    "category": "control_plane_handler_error",
                    "code": "mailbox_resume_interrupted",
                    "stage": "mailbox_resume",
                    "failure_fingerprint": fingerprint.digest,
                    "failure_revision": failure_revision,
                    "targeted_test_profile": "kol_mailbox_exact_resume",
                }
        return attempt, waiting, acked, used_revisions

    @staticmethod
    def _repair_context(
        attempt: dict[str, Any] | None,
        waiting: dict[str, Any] | None,
        *,
        handoff_id: str,
    ) -> dict[str, str]:
        if attempt is None or waiting is None:
            raise MailboxError("mailbox repair target has no durable wait")
        content_sha256 = str(attempt.get("content_sha256") or "")
        if not _SHA256.fullmatch(content_sha256):
            raise MailboxError("mailbox repair target content binding is invalid")
        context = {
            "message_id": handoff_id,
            "content_sha256": content_sha256,
            "waiting_event_id": str(waiting["event_id"]),
        }
        context.update({
            key: str(waiting[key])
            for key in (
                "category",
                "code",
                "stage",
                "failure_fingerprint",
                "failure_revision",
                "targeted_test_profile",
            )
            if waiting.get(key) is not None
        })
        return context

    def repair_resume_context(self, handoff_id: str) -> dict[str, str]:
        """Return the local durable wait without contacting the provider."""

        normalized_id = str(handoff_id or "")
        attempt, waiting, acked, _used_revisions = self._repair_state(normalized_id)
        if acked:
            raise MailboxError("mailbox repair target is already acknowledged")
        return self._repair_context(
            attempt,
            waiting,
            handoff_id=normalized_id,
        )

    def repair_resume_claim(
        self,
        handoff_id: str,
        *,
        repair_revision: str,
        now: datetime,
    ) -> dict[str, str]:
        """Bind repair continuation to the last durable waiting attempt.

        A revision normally gets one attempt.  It may continue the same claim
        again only after a provider supplied an explicit poll deadline; this
        keeps contract failures single-shot while allowing bounded async work.
        """
        normalized_revision = str(repair_revision or "")
        if not re.fullmatch(r"[a-f0-9]{40}", normalized_revision):
            raise MailboxError("mailbox repair revision is invalid")
        normalized_id = str(handoff_id or "")
        attempt, waiting, acked, used_revisions = self._repair_state(normalized_id)
        if acked:
            raise MailboxError("mailbox repair target is already acknowledged")
        context = self._repair_context(
            attempt,
            waiting,
            handoff_id=normalized_id,
        )
        content_sha256 = context["content_sha256"]
        diagnostic = " ".join(
            str(waiting.get(key) or "").lower()
            for key in ("category", "code", "stage")
        )
        if "uncertain" in diagnostic:
            raise MailboxError(
                "mailbox repair requires external side-effect reconciliation"
            )
        if str(waiting.get("category") or "") == "provider_wait":
            next_poll = str(waiting.get("next_poll_not_before") or "")
            try:
                due = datetime.fromisoformat(next_poll.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MailboxError(
                    "provider wait lacks a durable poll deadline"
                ) from exc
            if now.tzinfo is None or due.tzinfo is None:
                raise MailboxError("mailbox repair poll deadline needs a timezone")
            if now < due:
                raise MailboxError("mailbox repair poll deadline is not due")
            if used_revisions and normalized_revision not in used_revisions:
                raise MailboxError(
                    "provider wait must reuse its repair revision"
                )
        if (
            normalized_revision in used_revisions
            and str(waiting.get("category") or "") != "provider_wait"
        ):
            next_poll = str(waiting.get("next_poll_not_before") or "")
            try:
                due = datetime.fromisoformat(next_poll.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MailboxError(
                    "mailbox repair revision was already attempted"
                ) from exc
            if now.tzinfo is None or due.tzinfo is None:
                raise MailboxError("mailbox repair poll deadline needs a timezone")
            if now < due:
                raise MailboxError("mailbox repair poll deadline is not due")
        return {
            **context,
        }


class LiangHuiMailboxClient:
    """Thin structured adapter over the four deployed LiangHuiMCP tools."""

    def __init__(
        self,
        ledger: MailboxLedger,
        *,
        exchange: Callable[[dict[str, Any]], dict[str, Any]],
        now: Callable[[], datetime] | None = None,
    ):
        self.ledger = ledger
        self.exchange = exchange
        self.now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate_send_receipt(
        response: Any,
        *,
        handoff_id: str,
        content_sha256: str,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(response, dict):
            raise MailboxError("mailbox send response is invalid")
        outcome = str(response.get("outcome") or "")
        receipt = response.get("receipt")
        if (
            response.get("operation") != "send_mailbox_message"
            or outcome not in {"created", "already_present"}
            or not isinstance(receipt, dict)
            or receipt.get("operation") != "send_mailbox_message"
            or receipt.get("mailbox_id") != MAILBOX_ID
            or receipt.get("message_id") != handoff_id
            or receipt.get("message_type") != MAILBOX_MESSAGE_TYPE
            or receipt.get("schema_version") != MAILBOX_SCHEMA_VERSION
            or receipt.get("content_sha256") != content_sha256
            or not _required_id(receipt.get("family_id"), field="family_id")
            or not _required_id(receipt.get("created_by"), field="created_by")
            or not _UTC_MILLISECONDS.fullmatch(
                str(receipt.get("created_at") or "")
            )
        ):
            raise MailboxError("mailbox send lacks an authoritative receipt")
        return outcome, dict(receipt)

    def publish_handoff(
        self,
        capsule: dict[str, Any],
        *,
        object_kind: str,
        title: str,
    ) -> dict[str, Any]:
        if not isinstance(capsule, dict):
            raise MailboxError("mailbox handoff capsule must be an object")
        handoff_id = str(capsule.get("handoff_id") or "")
        if not _SHA256.fullmatch(handoff_id):
            raise MailboxError("mailbox handoff_id must be SHA-256")
        prefix = _OBJECT_PREFIX.get(object_kind)
        normalized_title = str(title or "").strip()
        if prefix is None or not normalized_title:
            raise MailboxError("mailbox object label is invalid")
        prior = self.ledger.handoff_state(handoff_id)
        if prior is not None:
            if (
                prior.get("mailbox_id") != MAILBOX_ID
                or prior.get("message_id") != handoff_id
                or prior.get("object_kind") != object_kind
                or not str(prior.get("title") or "").strip()
            ):
                raise MailboxError("mailbox send claim changed")
            # An attempted external write is immutable even when a later code
            # repair improves how future subjects are derived.
            normalized_title = str(prior["title"])
        sender_content = {
            "mailbox_id": MAILBOX_ID,
            "message_id": handoff_id,
            "message_type": MAILBOX_MESSAGE_TYPE,
            "schema_version": MAILBOX_SCHEMA_VERSION,
            "subject": f"[{prefix}] {normalized_title}"[:160],
            "correlation_id": handoff_id,
            "payload": capsule,
        }
        content_sha256 = _sha256(sender_content)
        if prior is not None:
            if (
                prior.get("content_sha256") != content_sha256
            ):
                raise MailboxError("mailbox send claim changed")
            if prior.get("event") == "mailbox_send_attempted":
                response = self.exchange(
                    {
                        "event": "daily_lianghui_mailbox_input_required",
                        "operation": "get_mailbox_message",
                        "arguments": {
                            "mailbox_id": MAILBOX_ID,
                            "message_id": handoff_id,
                        },
                    }
                )
                message = self._validate_exact_message(response, sent=prior)
                self.ledger.append(
                    "mailbox_send_reconciled",
                    occurred_at=_utc_now(self.now),
                    handoff_id=handoff_id,
                    object_kind=object_kind,
                    title=normalized_title,
                    mailbox_id=MAILBOX_ID,
                    message_id=handoff_id,
                    content_sha256=content_sha256,
                    outcome="already_present",
                    observed_status=str(message["status"]),
                    family_id=str(message["family_id"]),
                )
            return {
                "status": "Handoff完成",
                "handoff_id": handoff_id,
                "mailbox_outcome": str(prior.get("outcome") or "already_present"),
                "content_sha256": content_sha256,
            }
        self.ledger.append(
            "mailbox_send_attempted",
            occurred_at=_utc_now(self.now),
            handoff_id=handoff_id,
            object_kind=object_kind,
            title=normalized_title,
            mailbox_id=MAILBOX_ID,
            message_id=handoff_id,
            content_sha256=content_sha256,
        )
        response = self.exchange(
            {
                "event": "daily_lianghui_mailbox_input_required",
                "operation": "send_mailbox_message",
                "arguments": {
                    **sender_content,
                    "content_sha256": content_sha256,
                },
            }
        )
        outcome, receipt = self._validate_send_receipt(
            response,
            handoff_id=handoff_id,
            content_sha256=content_sha256,
        )
        self.ledger.append(
            "mailbox_send_receipted",
            occurred_at=_utc_now(self.now),
            handoff_id=handoff_id,
            object_kind=object_kind,
            title=normalized_title,
            mailbox_id=MAILBOX_ID,
            message_id=handoff_id,
            content_sha256=content_sha256,
            outcome=outcome,
            receipt=receipt,
        )
        return {
            "status": "Handoff完成",
            "handoff_id": handoff_id,
            "mailbox_outcome": outcome,
            "content_sha256": content_sha256,
        }

    @staticmethod
    def _validate_exact_message(
        response: Any,
        *,
        sent: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not isinstance(response, dict)
            or response.get("operation") != "get_mailbox_message"
            or not isinstance(response.get("message"), dict)
        ):
            raise MailboxError("mailbox exact readback is invalid")
        message = dict(response["message"])
        receipt = sent.get("receipt")
        expected_family = (
            receipt.get("family_id") if isinstance(receipt, dict) else None
        )
        sender_content = {
            key: message[key]
            for key in (
                "mailbox_id",
                "message_id",
                "message_type",
                "schema_version",
                "subject",
                "correlation_id",
                "payload",
            )
            if key in message
        }
        if (
            (
                expected_family is not None
                and message.get("family_id") != expected_family
            )
            or message.get("mailbox_id") != MAILBOX_ID
            or message.get("message_id") != sent.get("handoff_id")
            or message.get("message_type") != MAILBOX_MESSAGE_TYPE
            or message.get("schema_version") != MAILBOX_SCHEMA_VERSION
            or message.get("content_sha256") != sent.get("content_sha256")
            or (
                not isinstance(receipt, dict)
                and message.get("content_sha256") != _sha256(sender_content)
            )
            or message.get("status") not in {"pending", "acked"}
            or not _required_id(message.get("family_id"), field="family_id")
            or not _required_id(message.get("created_by"), field="created_by")
            or not _UTC_MILLISECONDS.fullmatch(
                str(message.get("created_at") or "")
            )
        ):
            raise MailboxError("mailbox exact readback changed identity or content")
        ack_receipt = message.get("ack_receipt")
        if message["status"] == "pending":
            if ack_receipt is not None:
                raise MailboxError("pending mailbox message has an ack receipt")
            return message
        if (
            not isinstance(ack_receipt, dict)
            or ack_receipt.get("operation") != "ack_mailbox_message"
            or ack_receipt.get("family_id") != message.get("family_id")
            or ack_receipt.get("mailbox_id") != MAILBOX_ID
            or ack_receipt.get("message_id") != sent.get("handoff_id")
            or ack_receipt.get("content_sha256") != sent.get("content_sha256")
            or not _required_id(ack_receipt.get("acked_by"), field="acked_by")
            or not _UTC_MILLISECONDS.fullmatch(
                str(ack_receipt.get("acked_at") or "")
            )
        ):
            raise MailboxError("acked mailbox message lacks a bound receipt")
        return message

    def reconcile_local(self) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for sent in self.ledger.outstanding_handoffs():
            handoff_id = str(sent["handoff_id"])
            response = self.exchange(
                {
                    "event": "daily_lianghui_mailbox_input_required",
                    "operation": "get_mailbox_message",
                    "arguments": {
                        "mailbox_id": MAILBOX_ID,
                        "message_id": handoff_id,
                    },
                }
            )
            message = self._validate_exact_message(response, sent=sent)
            if sent.get("event") == "mailbox_send_attempted":
                self.ledger.append(
                    "mailbox_send_reconciled",
                    occurred_at=_utc_now(self.now),
                    handoff_id=handoff_id,
                    object_kind=str(sent["object_kind"]),
                    title=str(sent["title"]),
                    mailbox_id=MAILBOX_ID,
                    message_id=handoff_id,
                    content_sha256=str(sent["content_sha256"]),
                    outcome="already_present",
                    observed_status=str(message["status"]),
                    family_id=str(message["family_id"]),
                )
            prefix = _OBJECT_PREFIX[str(sent["object_kind"])]
            row = {
                "object": f"[{prefix}] {sent['title']}",
                "status": (
                    "全部完成" if message["status"] == "acked" else "Handoff完成"
                ),
                "handoff_id": handoff_id,
            }
            results.append(row)
            if message["status"] == "acked":
                self.ledger.append(
                    "mailbox_ack_observed",
                    occurred_at=_utc_now(self.now),
                    handoff_id=handoff_id,
                    content_sha256=str(sent["content_sha256"]),
                    receipt=message["ack_receipt"],
                )
        return results

    @staticmethod
    def _validate_pending_message(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise MailboxError("mailbox pending message is invalid")
        message = dict(value)
        handoff_id = str(message.get("message_id") or "")
        payload = message.get("payload")
        sender_content = {
            key: message[key]
            for key in (
                "mailbox_id",
                "message_id",
                "message_type",
                "schema_version",
                "subject",
                "correlation_id",
                "payload",
            )
            if key in message
        }
        if (
            message.get("mailbox_id") != MAILBOX_ID
            or not _SHA256.fullmatch(handoff_id)
            or message.get("message_type") != MAILBOX_MESSAGE_TYPE
            or message.get("schema_version") != MAILBOX_SCHEMA_VERSION
            or message.get("status") != "pending"
            or message.get("ack_receipt") is not None
            or not isinstance(payload, dict)
            or payload.get("handoff_id") != handoff_id
            or message.get("content_sha256") != _sha256(sender_content)
            or not _required_id(message.get("family_id"), field="family_id")
            or not _required_id(message.get("created_by"), field="created_by")
            or not _UTC_MILLISECONDS.fullmatch(
                str(message.get("created_at") or "")
            )
        ):
            raise MailboxError("mailbox pending message binding is invalid")
        return message

    def list_pending(self, *, cursor: str | None = None) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "view": "pending",
            "sort": "oldest",
            "page_size": 50,
        }
        if cursor is not None:
            arguments["cursor"] = cursor
        response = self.exchange(
            {
                "event": "daily_lianghui_mailbox_input_required",
                "operation": "list_mailbox_messages",
                "arguments": arguments,
            }
        )
        if (
            not isinstance(response, dict)
            or response.get("operation") != "list_mailbox_messages"
            or not isinstance(response.get("page"), dict)
        ):
            raise MailboxError("mailbox pending page is invalid")
        page = response["page"]
        items = page.get("items")
        next_cursor = page.get("next_cursor")
        has_more = page.get("has_more")
        if (
            not isinstance(items, list)
            or not isinstance(has_more, bool)
            or (has_more and not isinstance(next_cursor, str))
            or (not has_more and next_cursor is not None)
        ):
            raise MailboxError("mailbox pending pagination is invalid")
        validated: list[dict[str, Any]] = []
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("mailbox_id") == MAILBOX_ID
                and item.get("message_type") == MAILBOX_MESSAGE_TYPE
                and item.get("schema_version") == MAILBOX_SCHEMA_VERSION
            ):
                validated.append(self._validate_pending_message(item))
        return {
            "items": validated,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def get_message(
        self,
        message_id: str,
        *,
        expected_content_sha256: str,
    ) -> dict[str, Any]:
        """Read one mailbox message without widening an exact resume."""

        normalized_id = str(message_id or "")
        expected_sha = str(expected_content_sha256 or "")
        if not _SHA256.fullmatch(normalized_id):
            raise MailboxError("mailbox exact message_id is invalid")
        if not _SHA256.fullmatch(expected_sha):
            raise MailboxError("mailbox exact content binding is invalid")
        try:
            response = self.exchange(
                {
                    "event": "daily_lianghui_mailbox_input_required",
                    "operation": "get_mailbox_message",
                    "arguments": {
                        "mailbox_id": MAILBOX_ID,
                        "message_id": normalized_id,
                        "expected_content_sha256": expected_sha,
                    },
                }
            )
            message = self._validate_exact_message(
                response,
                sent={
                    "handoff_id": normalized_id,
                    "content_sha256": expected_sha,
                },
            )
        except MailboxError:
            raise
        except Exception as exc:
            raise MailboxError("mailbox exact readback is unavailable") from exc
        if message.get("status") != "pending":
            raise MailboxError("mailbox exact repair target is already acknowledged")
        return message

    def get_mailbox_message(
        self,
        message_id: str,
        *,
        expected_content_sha256: str,
    ) -> dict[str, Any]:
        """Named mailbox-port alias for the exact single-message read."""

        return self.get_message(
            message_id,
            expected_content_sha256=expected_content_sha256,
        )

    def ack_message(self, message: dict[str, Any]) -> dict[str, Any]:
        handoff_id = str(message["message_id"])
        content_sha256 = str(message["content_sha256"])
        response = self.exchange(
            {
                "event": "daily_lianghui_mailbox_input_required",
                "operation": "ack_mailbox_message",
                "arguments": {
                    "mailbox_id": MAILBOX_ID,
                    "message_id": handoff_id,
                    "expected_content_sha256": content_sha256,
                },
            }
        )
        if not isinstance(response, dict):
            raise MailboxError("mailbox ack response is invalid")
        outcome = str(response.get("outcome") or "")
        receipt = response.get("receipt")
        if (
            response.get("operation") != "ack_mailbox_message"
            or outcome not in {"acked", "already_acked"}
            or not isinstance(receipt, dict)
            or receipt.get("operation") != "ack_mailbox_message"
            or receipt.get("family_id") != message.get("family_id")
            or receipt.get("mailbox_id") != MAILBOX_ID
            or receipt.get("message_id") != handoff_id
            or receipt.get("content_sha256") != content_sha256
            or not _required_id(receipt.get("acked_by"), field="acked_by")
            or not _UTC_MILLISECONDS.fullmatch(
                str(receipt.get("acked_at") or "")
            )
        ):
            raise MailboxError("mailbox ack lacks an authoritative receipt")
        self.ledger.append(
            "mailbox_ack_receipted",
            occurred_at=_utc_now(self.now),
            handoff_id=handoff_id,
            content_sha256=content_sha256,
            outcome=outcome,
            receipt=receipt,
        )
        return {"outcome": outcome, "receipt": dict(receipt)}


class RemoteMailboxDrain:
    """Drain new eligible messages once per run without looping on waits."""

    def __init__(
        self,
        client: LiangHuiMailboxClient,
        *,
        processor: Callable[[dict[str, Any]], dict[str, Any]],
        failure_revision: str | None = None,
        repair_authorizer: Callable[[dict[str, str], str], Any] | None = None,
    ):
        self.client = client
        self.processor = processor
        self.failure_revision = failure_revision
        self.repair_authorizer = repair_authorizer

    def _new_eligible(
        self,
        attempted: set[str],
        *,
        only_message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor: str | None = None
        seen_cursors: set[str] = set()
        seen_messages: dict[str, str] = {}
        eligible: list[dict[str, Any]] = []
        while True:
            page = self.client.list_pending(cursor=cursor)
            for message in page["items"]:
                message_id = str(message["message_id"])
                content_sha256 = str(message["content_sha256"])
                prior_sha256 = seen_messages.get(message_id)
                if prior_sha256 is not None:
                    if prior_sha256 != content_sha256:
                        raise MailboxError(
                            "mailbox pagination changed message content"
                        )
                    continue
                seen_messages[message_id] = content_sha256
                if (
                    message_id not in attempted
                    and (
                        only_message_id is None
                        or message_id == only_message_id
                    )
                ):
                    eligible.append(message)
            if not page["has_more"]:
                return eligible
            next_cursor = str(page["next_cursor"])
            if next_cursor in seen_cursors:
                raise MailboxError("mailbox pagination repeated a cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

    @staticmethod
    def _safe_waiting_details(
        result: Any,
        *,
        failure_revision: str | None = None,
    ) -> dict[str, Any]:
        source = result if isinstance(result, dict) else {}
        waiting_items = source.get("waiting_items")
        if (
            isinstance(waiting_items, list)
            and waiting_items
            and isinstance(waiting_items[0], dict)
        ):
            source = {**source, **waiting_items[0]}
        details: dict[str, Any] = {}
        for key in (
            "category",
            "code",
            "stage",
            "reconciliation",
            "next_poll_not_before",
            "action",
            "blocker_identity",
            "dedup_key",
        ):
            value = source.get(key)
            if (
                isinstance(value, str)
                and value
                and len(value) <= 200
                and "\n" not in value
                and "\r" not in value
            ):
                details[key] = value
        if source.get("user_action_required") is True:
            details["user_action_required"] = True
        if not details:
            details = {
                "category": "processor_error",
                "code": "processor_result_incomplete",
                "stage": "business_processing",
            }
        if (
            details.get("category") == "provider_wait"
            and not details.get("next_poll_not_before")
            and details.get("user_action_required") is not True
        ):
            details = {
                **details,
                "category": "internal_state_error",
                "code": "progress_deadline_missing",
            }
        progress = source.get("writer_progress")
        if isinstance(progress, dict) and progress.get("status") == "repair_required":
            for key in (
                "failure_fingerprint",
                "failure_revision",
                "targeted_test_profile",
            ):
                value = progress.get(key)
                if isinstance(value, str) and value:
                    details[key] = value
        if (
            failure_revision
            and details.get("category") != "provider_wait"
            and details.get("user_action_required") is not True
            and "failure_fingerprint" not in details
        ):
            try:
                details["failure_revision"] = failure_revision
                details["failure_fingerprint"] = FailureFingerprint(
                    adapter="mailbox",
                    category=details["category"],
                    code=details["code"],
                    stage=details["stage"],
                    failure_revision=failure_revision,
                    provider_contract_version="lianghui_mailbox_v1",
                ).digest
            except (TypeError, ValueError):
                details.pop("failure_revision", None)
        return details

    def _waiting_progress(
        self,
        message: Mapping[str, Any],
        result: Any,
        details: Mapping[str, Any],
    ) -> WriterProgress:
        raw_progress = result.get("writer_progress") if isinstance(result, dict) else None
        if isinstance(raw_progress, Mapping):
            return WriterProgress.from_dict(raw_progress)
        summary = (
            result.get("claim_receipt_summary")
            if isinstance(result, dict)
            else None
        )
        if not isinstance(summary, Mapping):
            summary = _empty_claim_receipt_summary()
        if (
            details.get("user_action_required") is True
            and all(
                isinstance(details.get(key), str) and details.get(key)
                for key in ("action", "blocker_identity", "dedup_key")
            )
        ):
            return WriterProgress.user_action_required(
                item_identity=str(message["message_id"]),
                stage=str(details.get("stage") or "business_processing"),
                action=str(details.get("action") or ""),
                blocker_identity=str(details.get("blocker_identity") or ""),
                dedup_key=str(details.get("dedup_key") or ""),
                claim_receipt_summary=summary,
            )
        revision = self.failure_revision
        if revision is None:
            try:
                revision = resolve_repository_revision(Path(__file__).parents[3])
            except ProgressContractError as exc:
                raise MailboxError(
                    "mailbox processor failure revision is unavailable"
                ) from exc
        item_identity = str(message["message_id"])
        if (
            details.get("category") == "provider_wait"
            and details.get("next_poll_not_before")
        ):
            attempted = int((result or {}).get("trigger_attempt") or 1) if isinstance(result, dict) else 1
            return WriterProgress.wait_until(
                item_identity=item_identity,
                category=str(details["category"]),
                code=str(details["code"]),
                stage=str(details["stage"]),
                deadline=str(details["next_poll_not_before"]),
                attempt_budget={"attempted": attempted, "maximum": max(3, attempted)},
                claim_receipt_summary=summary,
            )
        fingerprint = FailureFingerprint(
            adapter="mailbox",
            category=str(details["category"]),
            code=str(details["code"]),
            stage=str(details["stage"]),
            failure_revision=str(revision),
            provider_contract_version="lianghui_mailbox_v1",
        )
        return WriterProgress.repair_required(
            item_identity=item_identity,
            fingerprint=fingerprint,
            repair_revision=None,
            affected_set_digest=hashlib.sha256(
                json.dumps(
                    [{"identity": item_identity, "version_key": "current"}],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            claim_receipt_summary=summary,
            targeted_test_profile="kol_mailbox_exact_resume",
            narrow_resume_surface=f"mailbox:{item_identity}",
            retryability="retryable",
        )

    @staticmethod
    def _terminal_progress(
        message: Mapping[str, Any],
        result: Any,
    ) -> WriterProgress:
        raw_progress = result.get("writer_progress") if isinstance(result, dict) else None
        if isinstance(raw_progress, Mapping):
            progress = WriterProgress.from_dict(raw_progress)
            if progress.status != "terminal":
                raise MailboxError("completed mailbox result has non-terminal progress")
            return progress
        summary = result.get("claim_receipt_summary") if isinstance(result, dict) else None
        if not isinstance(summary, Mapping):
            summary = _empty_claim_receipt_summary()
        effect_count = result.get("new_external_effect_count", 0) if isinstance(result, dict) else 0
        if isinstance(effect_count, bool) or not isinstance(effect_count, int) or effect_count < 0:
            raise MailboxError("completed mailbox result has invalid effect count")
        return WriterProgress.terminal(
            item_identity=str(message["message_id"]),
            stage="mailbox_ack",
            content_terminal="completed",
            gray_report_terminal="not_applicable",
            reminder_terminal="not_applicable",
            book_terminal="not_applicable",
            knowledge_terminal="not_applicable",
            ack_status="acked",
            new_external_effect_count=effect_count,
            claim_receipt_summary=summary,
        )

    def run(
        self,
        *,
        only_message_id: str | None = None,
        repair_revision: str | None = None,
    ) -> dict[str, Any]:
        repair_claim: dict[str, str] | None = None
        if only_message_id is not None:
            if repair_revision is None:
                raise MailboxError("mailbox repair revision is required")
            repair_claim = self.client.ledger.repair_resume_claim(
                only_message_id,
                repair_revision=repair_revision,
                now=self.client.now(),
            )
            if (
                repair_claim.get("category") != "provider_wait"
                and self.repair_authorizer is None
            ):
                raise MailboxError(
                    "matching repair validation receipt is required"
                )
            if self.repair_authorizer is not None:
                self.repair_authorizer(repair_claim, str(repair_revision))
        elif repair_revision is not None:
            raise MailboxError("mailbox repair target is required")
        attempted: set[str] = set()
        attempted_order: list[str] = []
        acked: list[str] = []
        waiting: list[str] = []
        items: list[dict[str, str]] = []
        while True:
            if only_message_id is not None:
                batch = [
                    self.client.get_mailbox_message(
                        only_message_id,
                        expected_content_sha256=repair_claim["content_sha256"],
                    )
                ]
            else:
                batch = self._new_eligible(attempted)
            if not batch:
                return {
                    "status": "waiting" if waiting else "completed",
                    "attempted_message_ids": attempted_order,
                    "acked_message_ids": acked,
                    "waiting_message_ids": waiting,
                    "items": items,
                }
            for message in batch:
                message_id = str(message["message_id"])
                attempted.add(message_id)
                attempted_order.append(message_id)
                if repair_claim is not None:
                    if (
                        message_id != only_message_id
                        or message.get("content_sha256")
                        != repair_claim["content_sha256"]
                    ):
                        raise MailboxError(
                            "mailbox repair target changed content"
                        )
                    self.client.ledger.append(
                        "mailbox_message_repair_resumed",
                        occurred_at=_utc_now(self.client.now),
                        handoff_id=message_id,
                        content_sha256=str(message["content_sha256"]),
                        repair_revision=str(repair_revision),
                        prior_waiting_event_id=repair_claim[
                            "waiting_event_id"
                        ],
                    )
                else:
                    self.client.ledger.append(
                        "mailbox_message_attempted",
                        occurred_at=_utc_now(self.client.now),
                        handoff_id=message_id,
                        content_sha256=str(message["content_sha256"]),
                    )
                try:
                    result = self.processor(message)
                except Exception as exc:
                    if isinstance(exc, EnrichmentDiagnosticError):
                        details = {
                            "category": exc.diagnostic_category,
                            "code": exc.diagnostic_code,
                            "stage": exc.diagnostic_stage,
                        }
                    else:
                        details = {
                            "category": "processor_error",
                            "code": _exception_code(exc),
                            "stage": "business_processing",
                        }
                    details = self._safe_waiting_details(
                        details,
                        failure_revision=self.failure_revision,
                    )
                    progress = self._waiting_progress(message, {}, details)
                    details["writer_progress"] = progress.to_dict()
                    self.client.ledger.append(
                        "mailbox_message_waiting",
                        occurred_at=_utc_now(self.client.now),
                        handoff_id=message_id,
                        **details,
                    )
                    waiting.append(message_id)
                    items.append({
                        "object": str(message["subject"]),
                        "status": "等待业务完成",
                        "handoff_id": message_id,
                        **details,
                    })
                    continue
                if (
                    not isinstance(result, dict)
                    or result.get("business_complete") is not True
                ):
                    details = self._safe_waiting_details(
                        result,
                        failure_revision=self.failure_revision,
                    )
                    progress = self._waiting_progress(message, result, details)
                    details["writer_progress"] = progress.to_dict()
                    self.client.ledger.append(
                        "mailbox_message_waiting",
                        occurred_at=_utc_now(self.client.now),
                        handoff_id=message_id,
                        **details,
                    )
                    waiting.append(message_id)
                    items.append({
                        "object": str(message["subject"]),
                        "status": "等待业务完成",
                        "handoff_id": message_id,
                        **details,
                    })
                    continue
                terminal_progress = self._terminal_progress(message, result)
                self.client.ack_message(message)
                acked.append(message_id)
                items.append({
                    "object": str(message["subject"]),
                    "status": "全部完成",
                    "handoff_id": message_id,
                    "writer_progress": terminal_progress.to_dict(),
                })
            if only_message_id is not None:
                return {
                    "status": "waiting" if waiting else "completed",
                    "attempted_message_ids": attempted_order,
                    "acked_message_ids": acked,
                    "waiting_message_ids": waiting,
                    "items": items,
                }
