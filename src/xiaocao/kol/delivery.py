"""Idempotent WeChat delivery for reader-facing KOL advisories."""

from __future__ import annotations

import fcntl
import hashlib
from pathlib import Path
from typing import Any, Callable

from ._shared import DecisionError, append_jsonl, now_iso, read_jsonl
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
