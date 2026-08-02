"""Idempotent WeChat delivery for reader-facing KOL advisories."""

from __future__ import annotations

import fcntl
import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from ._shared import (
    DecisionError,
    append_jsonl,
    canonical,
    now_iso,
    parse_iso,
    read_jsonl,
)
from .rendering import reader_message_title, render_household_item_message


class WechatDelivery:
    def __init__(self, *, events_path: Path, outbox_path: Path, lock_path: Path):
        self.events_path = events_path
        self.outbox_path = outbox_path
        self.lock_path = lock_path

    def record(self, idempotency_key: str, receipt: str) -> dict[str, Any]:
        if not str(receipt).strip():
            raise DecisionError("notification delivery receipt must not be blank")
        matching = next(
            (
                row
                for row in read_jsonl(self.outbox_path)
                if row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if matching is None:
            raise DecisionError("notification idempotency key not found")
        prior = next(
            (
                row
                for row in read_jsonl(self.events_path)
                if row.get("event") == "notification_delivered"
                and row.get("idempotency_key") == idempotency_key
            ),
            None,
        )
        if prior:
            return {**prior, "idempotent_replay": True}
        event = {
            "event": "notification_delivered",
            "idempotency_key": idempotency_key,
            "channel": "wechat",
            "status": "delivered",
            "receipt": receipt,
            "delivered_at": now_iso(),
        }
        append_jsonl(self.events_path, event)
        return event

    def record_transport(
        self,
        receipt: dict[str, Any],
        *,
        expected_recipients: tuple[str, ...],
    ) -> dict[str, Any]:
        """Validate a cross-node all-recipient receipt before aggregate delivery."""
        if receipt.get("schema_version") != 1 or receipt.get("status") != "delivered":
            raise DecisionError("notification transport receipt is not delivered")
        receipt_sha = str(receipt.get("receipt_sha256") or "")
        unsigned = dict(receipt)
        unsigned.pop("receipt_sha256", None)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", receipt_sha)
            or hashlib.sha256(canonical(unsigned).encode()).hexdigest() != receipt_sha
        ):
            raise DecisionError("notification transport receipt hash is invalid")
        for field in (
            "handoff_id",
            "notification_id",
            "report_id",
            "stable_report_url",
            "content_sha256",
        ):
            if not str(receipt.get(field) or "").strip():
                raise DecisionError(f"notification transport receipt requires {field}")
        if receipt["notification_id"] not in {
            str(row.get("idempotency_key") or "")
            for row in read_jsonl(self.outbox_path)
        }:
            raise DecisionError("notification idempotency key not found")
        recipient_receipts = receipt.get("recipient_receipts")
        expected = tuple(dict.fromkeys(expected_recipients))
        if (
            not isinstance(recipient_receipts, dict)
            or not expected
            or set(recipient_receipts) != set(expected)
        ):
            raise DecisionError(
                "notification transport receipt must cover the exact recipient set"
            )
        for recipient in expected:
            value = recipient_receipts[recipient]
            expected_recipient_receipt = (
                f"wecom-relay://ok/{receipt['handoff_id']}/{recipient}/"
                f"{str(receipt['content_sha256'])[:16]}"
            )
            if (
                not isinstance(value, dict)
                or value.get("receipt") != expected_recipient_receipt
                or not str(value.get("delivered_at") or "").strip()
            ):
                raise DecisionError(
                    "notification transport recipient receipt is incomplete"
                )
            parse_iso(
                value["delivered_at"],
                field=f"recipient_receipts[{recipient}].delivered_at",
            )

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            prior = next(
                (
                    row
                    for row in read_jsonl(self.events_path)
                    if row.get("event")
                    == "notification_transport_receipt_validated"
                    and row.get("receipt_sha256") == receipt_sha
                ),
                None,
            )
            if prior is None:
                append_jsonl(
                    self.events_path,
                    {
                        "event": "notification_transport_receipt_validated",
                        "idempotency_key": receipt["notification_id"],
                        "handoff_id": receipt["handoff_id"],
                        "report_id": receipt["report_id"],
                        "stable_report_url": receipt["stable_report_url"],
                        "content_sha256": receipt["content_sha256"],
                        "recipients": list(expected),
                        "receipt_sha256": receipt_sha,
                        "recorded_at": now_iso(),
                    },
                )
            return self.record(
                str(receipt["notification_id"]),
                f"wecom-transport://{receipt['handoff_id']}/{receipt_sha}",
            )

    def deliver(
        self,
        result: dict[str, Any],
        *,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        """Deliver pending items once; uncertain relay outcomes fail closed."""
        deliveries: list[dict[str, Any]] = []
        skipped: list[str] = []
        cross_source = result.get("cross_source") or {}
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            events = read_jsonl(self.events_path)
            delivered = {
                row.get("idempotency_key"): row
                for row in events
                if row.get("event") == "notification_delivered"
            }
            last_send_state: dict[str, dict[str, Any]] = {}
            for row in events:
                if row.get("event") in {
                    "notification_send_claimed",
                    "notification_send_uncertain",
                    "notification_delivered",
                }:
                    last_send_state[str(row.get("idempotency_key"))] = row
            for item in result.get("items") or []:
                notification = item.get("notification") or {}
                identity = str(notification.get("idempotency_key") or "").strip()
                if not identity:
                    raise DecisionError("notification idempotency key is missing")
                if notification.get("status") == "suppressed":
                    skipped.append(identity)
                    continue
                prior = delivered.get(identity)
                if prior:
                    notification.update(
                        {
                            "status": "delivered",
                            "receipt": prior["receipt"],
                            "delivered_at": prior["delivered_at"],
                        }
                    )
                    skipped.append(identity)
                    continue
                previous_state = last_send_state.get(identity) or {}
                if previous_state.get("event") in {
                    "notification_send_claimed",
                    "notification_send_uncertain",
                }:
                    raise DecisionError(
                        "WeChat delivery state is uncertain; reconcile the prior relay call "
                        f"before resending {identity}"
                    )

                title = reader_message_title(item)
                body = render_household_item_message(item, cross_source)
                content_sha = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()[:16]
                claim_event = {
                    "event": "notification_send_claimed",
                    "idempotency_key": identity,
                    "channel": "wechat",
                    "content_sha256": content_sha,
                    "claimed_at": now_iso(),
                }
                append_jsonl(self.events_path, claim_event)
                last_send_state[identity] = claim_event
                try:
                    response = sender(title, body)
                except Exception as exc:
                    raise DecisionError(
                        f"WeChat delivery outcome is uncertain for {item['author']}"
                    ) from exc
                status = response.get("wecom") if isinstance(response, dict) else None
                if status != "ok":
                    uncertain_event = {
                        "event": "notification_send_uncertain",
                        "idempotency_key": identity,
                        "channel": "wechat",
                        "status": status or "relay not configured",
                        "recorded_at": now_iso(),
                    }
                    append_jsonl(self.events_path, uncertain_event)
                    last_send_state[identity] = uncertain_event
                    raise DecisionError(
                        f"WeChat delivery failed for {item['author']}: "
                        f"{status or 'relay not configured'}"
                    )
                receipt = f"wecom-relay://ok/{identity}/{content_sha}"
                event = self.record(identity, receipt)
                notification.update(
                    {
                        "status": "delivered",
                        "receipt": event["receipt"],
                        "delivered_at": event["delivered_at"],
                    }
                )
                delivered[identity] = event
                last_send_state[identity] = event
                deliveries.append(event)
        return {
            "status": "delivered" if deliveries else "already_delivered",
            "deliveries": deliveries,
            "skipped": skipped,
        }
