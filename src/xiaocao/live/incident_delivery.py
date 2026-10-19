#!/usr/bin/env python3
"""Durable notice delivery shared by order incidents and operator notices."""
from __future__ import annotations

import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .notify import notify_detailed, wecom_transport_readiness
from .trading_execution import TradingIncidentOutbox
from xiaocao.runner_recovery import _write


def _attempt_path(path: Path, identifier: str) -> Path:
    return path.parent / (path.name + ".attempts") / (hashlib.sha256(identifier.encode()).hexdigest() + ".json")


def _attempt(path: Path, identifier: str, status: str):
    _write(_attempt_path(path, identifier), {"incident_id": identifier, "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat()})


def enqueue_notice(path: Path, *, identifier: str, title: str, body: str):
    """New notices have proof of no prior send; legacy pending claims do not."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".delivery.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        outbox = TradingIncidentOutbox(path)
        if not any(row.get("incident_id") == identifier for row in outbox._rows()):
            _attempt(path, identifier, "not_sent")
        outbox.enqueue(incident_id=identifier, title=title, body=body)


def pending_notices(path: Path) -> list[dict]:
    """Return each undelivered claim once, retaining its original exact body."""
    if not path.is_file():
        return []
    claims: dict[str, dict] = {}
    delivered: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        identifier = str(row.get("incident_id") or "")
        if not identifier:
            raise ValueError("TRADING_CHANGE_NOTICE_ID_MISSING")
        if row.get("status") == "pending":
            if not row.get("title") or not row.get("body"):
                raise ValueError("TRADING_CHANGE_NOTICE_BODY_MISSING")
            claims.setdefault(identifier, row)
        elif row.get("status") == "delivered":
            delivered.add(identifier)
        else:
            raise ValueError("TRADING_CHANGE_NOTICE_STATUS_INVALID")
    return [row for identifier, row in claims.items() if identifier not in delivered]


def deliver_pending(path: Path, *, sender=notify_detailed, readiness=wecom_transport_readiness,
                    incident_ids: set[str] | None = None) -> list[dict]:
    path.parent.mkdir(parents=True, exist_ok=True)
    delivery_lock = path.with_suffix(path.suffix + ".delivery.lock")
    with delivery_lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return _deliver_pending_locked(path, sender=sender, readiness=readiness, incident_ids=incident_ids)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _deliver_pending_locked(path: Path, *, sender, readiness, incident_ids) -> list[dict]:
    outbox = TradingIncidentOutbox(path)
    results = []
    for row in pending_notices(path):
        identifier = row["incident_id"]
        if incident_ids is not None and identifier not in incident_ids:
            continue
        try:
            prior = json.loads(_attempt_path(path, identifier).read_text())
        except (OSError, ValueError):
            prior = {"status": "legacy_unproven"}
        if (not isinstance(prior, dict) or prior.get("incident_id") != identifier
                or prior.get("status") not in {"not_sent", "failed_safe"}):
            results.append({"incident_id": identifier, "delivery": "pending_reconcile",
                            "reason": "PRIOR_NOTIFICATION_DELIVERY_UNPROVEN"})
            continue
        state = readiness(audience="trading")
        if state.get("status") != "configured":
            results.append({"incident_id": identifier, "delivery": "pending_transport",
                            "missing": state.get("missing", [])})
            continue
        try:
            _attempt(path, identifier, "sending")
            sent = sender(row["title"], row["body"], audience="trading")
        except Exception as exc:
            _attempt(path, identifier, "uncertain")
            results.append({"incident_id": identifier, "delivery": "pending_error",
                            "reason": type(exc).__name__})
            continue
        if isinstance(sent, dict) and sent.get("wecom") == "deferred_to_morning_result":
            # The morning owner deliberately performs no transport call here;
            # its consolidated result has a separate durable delivery claim.
            _attempt(path, identifier, "not_sent")
            results.append({"incident_id": identifier, "delivery": "deferred"})
        elif isinstance(sent, dict) and sent.get("wecom") == "ok":
            outbox.mark_delivered(identifier, {"wecom": "ok"})
            _attempt(path, identifier, "delivered")
            results.append({"incident_id": identifier, "delivery": "delivered"})
        else:
            recipient_results = (
                sent.get("wecom_recipients") if isinstance(sent, dict) else None
            )
            failures = (
                [value for value in recipient_results.values() if isinstance(value, dict)]
                if isinstance(recipient_results, dict) else []
            )
            # A partial delivery also cannot safely resend the aggregate body.
            # A local popup may already have appeared even when osascript
            # timed out. Only an explicit platform skip proves no local send.
            local_attempted = (isinstance(sent, dict) and "macos" in sent
                               and sent["macos"] != "skipped (not darwin)")
            safe = not local_attempted and bool(recipient_results) and isinstance(recipient_results, dict) and all(
                isinstance(value, dict) and value.get("status") in {None, "failed"}
                and value.get("retry_safety") == "safe"
                for value in recipient_results.values()
            )
            _attempt(path, identifier, "failed_safe" if safe else "uncertain")
            result = {
                "incident_id": identifier,
                "delivery": "pending_unproven",
                "failure_phases": sorted({
                    str(value.get("failure_phase") or "unknown") for value in failures
                }),
                "retry_safety": sorted({
                    str(value.get("retry_safety") or "unknown") for value in failures
                }),
            }
            if local_attempted:
                result["partial_channels" if sent["macos"] == "ok" else "uncertain_channels"] = ["macos"]
            results.append(result)
    return results
