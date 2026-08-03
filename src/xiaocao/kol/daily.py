"""Short-lived, append-only KOL daytime coordination.

The coordinator owns only scheduling, ordering, recovery, and terminal
validation.  Existing source adapters continue to own discovery and
enrichment; source-video bytes are never accepted by this seam.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from .enrichment_types import EnrichmentError
from .publication import (
    PublicationLedger,
    PublicationTransport,
    build_append_only_publication_update,
    build_publish_request,
    build_record,
    canonical_sha256,
    evaluation_id,
    publication_id_for_source,
    report_id,
    stable_claim,
)
from .rendering import reader_source_title


BEIJING = ZoneInfo("Asia/Shanghai")
DAYTIME_HOURS = frozenset(range(7, 24))
MAX_LEDGER_LINE_BYTES = 512 * 1024
MAX_REMINDER_BYTES = 2048
ALERT_BASES = {
    "market_posture",
    "buy",
    "sell",
    "hold",
    "position_boundary",
    "direction",
    "actionable_trigger",
}
VIEWPOINT_TRIGGERS = {
    "same_kol_publication",
    "due_horizon",
    "due_trigger",
    "due_falsifier",
    "material_fact_change",
    "user_request",
}


class DailyError(EnrichmentError):
    """The daily coordination contract could not be proved."""


class TransientSourceError(DailyError):
    """A self-recoverable source failure with credential-safe diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "source_error",
        code: str = "source_temporarily_unavailable",
        stage: str = "source_run",
    ):
        self.category = str(category or "").strip()
        self.code = str(code or "").strip()
        self.stage = str(stage or "").strip()
        for token in (self.category, self.code, self.stage):
            if (
                not token
                or len(token) > 64
                or not token.isascii()
                or not token[0].islower()
                or not token.replace("_", "").isalnum()
            ):
                raise ValueError("transient source diagnostic token is invalid")
        super().__init__(message)

    def diagnostic(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "code": self.code,
            "stage": self.stage,
            "retryable": True,
        }


class UserActionBlocker(DailyError):
    """A structured blocker whose exact user action may be notified once."""

    def __init__(self, blocker_key: str, action: str):
        self.blocker_key = str(blocker_key or "").strip()
        self.action = str(action or "").strip()
        if not self.blocker_key or not self.action:
            raise ValueError("user-action blocker needs a key and exact action")
        super().__init__(self.action)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _utc_iso8601(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailyError("daily timestamp is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise DailyError("daily timestamp needs a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_reason(value: Any, *, label: str) -> str:
    reason = str(value or "").strip()
    if not reason:
        raise DailyError(f"{label} requires a reason")
    return reason


def validate_source_event(value: Any) -> dict[str, Any]:
    """Validate one content-value result and its independent terminals."""

    if not isinstance(value, dict) or value.get("kind") != "source_event":
        raise DailyError("daily source event is invalid")
    event_id = str(value.get("event_id") or "").strip()
    if not event_id:
        raise DailyError("daily source event needs a stable event_id")
    if int(value.get("coordinator_source_video_bytes") or 0) != 0:
        raise DailyError("daily coordinator must read zero source-video bytes")
    content = value.get("content_value")
    if not isinstance(content, dict):
        raise DailyError("daily source event lacks content value")
    disposition = str(content.get("status") or "")
    _required_reason(content.get("reason"), label="content value")
    report = value.get("gray_report")
    alert = value.get("alert")
    book = value.get("book_kol_us")
    if not all(isinstance(row, dict) for row in (report, alert, book)):
        raise DailyError("daily source event lacks independent terminals")
    if (
        book.get("book") != "KOL-US"
        or book.get("paper_only") is not True
        or book.get("status") not in {"filled", "no_trade"}
    ):
        raise DailyError("daily Book terminal is not KOL-US paper-only")
    if book.get("status") == "no_trade":
        _required_reason(book.get("reason"), label="Book KOL-US no-trade")
    if disposition == "low_density":
        if report.get("status") != "not_created":
            raise DailyError("low-density item cannot create a gray report")
        if alert.get("status") != "not_created":
            raise DailyError("low-density item cannot create a reminder")
        if book.get("status") != "no_trade":
            raise DailyError("low-density item cannot create a Book trade")
        return value
    if disposition != "promoted":
        raise DailyError("daily content value result is unsupported")
    tier = str(content.get("tier") or "")
    if tier not in {"report_only", "alert_eligible"}:
        raise DailyError("promoted event needs a supported content tier")
    if (
        report.get("status") != "published"
        or not str(report.get("receipt") or "").strip()
        or not str(report.get("detail_url") or "").strip()
    ):
        raise DailyError("promoted event lacks a durable complete gray report")
    try:
        report_order = int(report["terminal_order"])
        alert_order = int(alert["terminal_order"])
        book_order = int(book["terminal_order"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DailyError("promoted terminal order is incomplete") from exc
    if report_order >= alert_order or report_order >= book_order:
        raise DailyError("gray report must precede reminder and Book terminals")
    if tier == "report_only":
        if alert.get("status") != "not_eligible":
            raise DailyError("report-only event needs a legal no-alert terminal")
        _required_reason(alert.get("reason"), label="no-alert terminal")
    else:
        if (
            alert.get("status") != "delivered"
            or not str(alert.get("receipt") or "").strip()
            or alert.get("all_recipients") is not True
            or alert.get("stable_link_count") != 1
            or alert.get("stable_report_url") != report.get("detail_url")
        ):
            raise DailyError(
                "alert event needs one all-recipient stable-link reminder"
            )
    return value


def validate_viewpoint_terminal(value: Any) -> dict[str, Any]:
    """Validate evaluation-only maintenance and its zero-side-effect boundary."""

    if not isinstance(value, dict) or value.get("kind") != "viewpoint_evaluation":
        raise DailyError("viewpoint maintenance terminal is invalid")
    publication = value.get("gray_publication") or {}
    if (
        value.get("trigger") not in VIEWPOINT_TRIGGERS
        or publication.get("status") != "published"
        or not str(publication.get("detail_url") or "").strip()
        or value.get("history_preserved") is not True
        or value.get("current_projection_order_preserved") is not True
        or (value.get("alert") or {}).get("status") != "not_created"
        or (value.get("book_kol_us") or {}).get("status") != "not_created"
        or int(value.get("coordinator_source_video_bytes") or 0) != 0
    ):
        raise DailyError("viewpoint maintenance side-effect boundary failed")
    return value


def _validate_source_outcome(outcome: dict[str, Any]) -> None:
    events = outcome.get("events", [])
    if outcome.get("status") == "completed":
        if not isinstance(events, list) or not events:
            raise DailyError("completed daily source needs terminal events")
        identities: set[str] = set()
        for event in events:
            if isinstance(event, dict) and event.get("kind") == "source_event":
                validated = validate_source_event(event)
            else:
                validated = validate_viewpoint_terminal(event)
            identity = str(validated["event_id"])
            if identity in identities:
                raise DailyError("independent source events cannot be merged")
            identities.add(identity)
    elif events not in (None, []):
        raise DailyError("non-completed daily source cannot claim terminal events")


def build_triggered_evaluation_candidate(
    current_publication: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    """Build one append-only currentness update with no event side effects."""

    trigger = str(request.get("trigger") or "")
    if trigger not in VIEWPOINT_TRIGGERS:
        raise DailyError("viewpoint evaluation trigger is unsupported")
    report = current_publication.get("report")
    records = current_publication.get("records")
    if not isinstance(report, dict) or not isinstance(records, list):
        raise DailyError("current viewpoint publication is incomplete")
    viewpoint_id_value = str(request.get("viewpoint_id") or "")
    if not any(
        isinstance(row, dict)
        and row.get("kind") == "viewpoint"
        and row.get("record_id") == viewpoint_id_value
        for row in records
    ):
        raise DailyError("triggered viewpoint does not exist in current history")
    as_of = str(request.get("as_of") or "").strip()
    evaluated_at = str(request.get("evaluated_at") or "").strip()
    basis = str(request.get("basis") or "").strip()
    status = str(request.get("status") or "").strip()
    if (
        not as_of
        or not evaluated_at
        or not basis
        or status not in {"current", "changed", "invalidated", "uncertain"}
    ):
        raise DailyError("triggered viewpoint evaluation is incomplete")
    as_of_utc = _utc_iso8601(as_of)
    evaluated_at_utc = _utc_iso8601(evaluated_at)
    evaluation_id_value = evaluation_id(
        viewpoint_id_value,
        as_of_utc,
        evaluated_at_utc,
    )
    evaluation = build_record(
        kind="viewpoint_evaluation",
        record_id_value=evaluation_id_value,
        idempotency_key=stable_claim(
            "put",
            str(report["record_id"]),
            "evaluation",
            evaluation_id_value,
        ),
        created_at=evaluated_at_utc,
        source_binding=report["source_binding"],
        payload={
            "evaluation_id": evaluation_id_value,
            "viewpoint_id": viewpoint_id_value,
            "status": status,
            "as_of": as_of_utc,
            "evaluated_at": evaluated_at_utc,
            "basis": basis,
            "confidence": str(request.get("confidence") or "medium"),
            "uncertainties": list(request.get("uncertainties") or []),
        },
    )
    updated_records, publish = build_append_only_publication_update(
        current_records=records,
        additions=[evaluation],
        viewpoint_ids=list(report["payload"].get("viewpoint_ids") or []),
        created_at=evaluated_at,
        revision=f"triggered-{evaluation_id_value}",
        reason="触发式长期观点时效复核；不创建事件提醒或 Book 动作。",
    )
    return {
        "publication_key": f"viewpoint-maintenance:{evaluation_id_value}",
        "records": updated_records,
        "publish_request": publish,
        "metadata": {
            "trigger": trigger,
            "evaluation_id": evaluation_id_value,
            "notification_claim_authorized": False,
            "book_kol_us_replay_authorized": False,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
        },
    }


def triggered_evaluation_terminal(
    candidate: dict[str, Any],
    publication_state: dict[str, Any],
) -> dict[str, Any]:
    receipt = publication_state.get("publish_receipt") or {}
    if (
        publication_state.get("completed") is not True
        or receipt.get("recordState") not in {"published", "superseded"}
        or not str(receipt.get("detailUrl") or "").strip()
    ):
        raise DailyError("viewpoint evaluation publication did not complete")
    metadata = candidate["metadata"]
    return {
        "kind": "viewpoint_evaluation",
        "event_id": metadata["evaluation_id"],
        "trigger": metadata["trigger"],
        "gray_publication": {
            "status": "published",
            "detail_url": receipt["detailUrl"],
        },
        "history_preserved": True,
        "current_projection_order_preserved": True,
        "alert": {"status": "not_created"},
        "book_kol_us": {"status": "not_created"},
        "coordinator_source_video_bytes": 0,
    }


@dataclass(frozen=True)
class DailyPublicationContext:
    """Stable lightweight binding for one independent source event."""

    adapter: str
    source_identity: str
    publication_version: str
    kol_id: str
    source: str
    source_published_at: str
    media_types: tuple[str, ...]
    source_parts: tuple[dict[str, Any], ...]


def _publication_candidate(
    item: dict[str, Any],
    *,
    context: DailyPublicationContext,
) -> dict[str, Any]:
    content = item.get("content_value") or {}
    if content.get("status") != "promoted":
        raise DailyError("only promoted content can create a gray report")
    tier = str(content.get("tier") or "")
    if tier not in {"report_only", "alert_eligible"}:
        raise DailyError("promoted content tier is invalid")
    if tier == "alert_eligible":
        bases = content.get("alert_basis")
        if (
            not isinstance(bases, list)
            or not bases
            or not set(str(row) for row in bases) <= ALERT_BASES
        ):
            raise DailyError("alert-eligible event lacks a permissive live basis")
    publication = item.get("publication")
    if not isinstance(publication, dict):
        raise DailyError("promoted event lacks reviewed publication copy")
    publication_key = publication_id_for_source(
        adapter=context.adapter,
        source_identity=context.source_identity,
    )
    report_id_value = report_id(publication_key)
    evidence_sha = str(item.get("evidence_sha256") or "")
    if len(evidence_sha) != 64:
        raise DailyError("promoted event lacks evidence_sha256")
    decision_sha = canonical_sha256(item)
    source_binding = {
        "publication_id": publication_key,
        "publication_version": context.publication_version,
        "evidence_sha256": evidence_sha,
        "decision_result_sha256": decision_sha,
        "extraction_contract_version": "kol-intelligence-v1",
    }
    alert_eligible = tier == "alert_eligible"
    alert_reason = (
        "permissive_live_investment_content_gate"
        if alert_eligible
        else _required_reason(
            content.get("no_alert_reason") or content.get("reason"),
            label="report-only no-alert",
        )
    )
    insight = item.get("reader_insight") or {}
    source_published_at = _utc_iso8601(context.source_published_at)
    report_payload = {
        "report_id": report_id_value,
        "report_kind": "publication_event",
        "kol_id": context.kol_id,
        "author": str(item.get("author") or ""),
        "source": context.source,
        "title": reader_source_title(item),
        "summary": str(publication.get("summary") or ""),
        "source_published_at": source_published_at,
        "media_types": list(context.media_types),
        "source_parts": [dict(row) for row in context.source_parts],
        "report_format": "markdown",
        "report_body": str(publication.get("report_body") or ""),
        "viewpoint_ids": [],
        "alert_eligible": alert_eligible,
        "alert_reason": alert_reason,
        "reader_insight": {
            "status": str(insight.get("status") or "useful"),
            "reason": str(
                insight.get("summary")
                or content.get("reason")
                or "本事件包含可供家庭检索的投资判断。"
            ),
        },
    }
    report = build_record(
        kind="report",
        record_id_value=report_id_value,
        idempotency_key=stable_claim(
            "put", publication_key, "report", decision_sha
        ),
        created_at=source_published_at,
        source_binding=source_binding,
        payload=report_payload,
    )
    publish = build_publish_request(
        [report],
        idempotency_key=stable_claim(
            "publish", publication_key, decision_sha
        ),
        reason="新 KOL 来源事件：先发布完整报告，再完成提醒与纸面 Book。",
    )
    return {
        "publication_key": publication_key,
        "records": [report],
        "publish_request": publish,
        "metadata": {
            "historical": False,
            "notification_claim_authorized": alert_eligible,
            "book_kol_us_replay_authorized": True,
            "large_payload_local_bytes": 0,
            "coordinator_source_video_bytes": 0,
        },
    }


def _without_urls(value: Any) -> str:
    words = [
        word
        for word in str(value or "").split()
        if not word.startswith(("http://", "https://"))
    ]
    return " ".join(words).strip()


def _fit_reminder(value: str, *, suffix: str) -> str:
    budget = MAX_REMINDER_BYTES - len(suffix.encode("utf-8"))
    if budget <= 0:
        raise DailyError("stable report link exceeds reminder boundary")
    encoded = value.encode("utf-8")
    if len(encoded) > budget:
        encoded = encoded[: max(0, budget - len("…".encode("utf-8")))]
        while True:
            try:
                value = encoded.decode("utf-8") + "…"
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    return value.rstrip() + suffix


class DailyPublicationPipeline:
    """Publish one event report before delegating Book and reminder effects."""

    def __init__(
        self,
        delegate: Any,
        *,
        ledger: PublicationLedger,
        client: PublicationTransport,
        context: DailyPublicationContext,
    ):
        self.delegate = delegate
        self.ledger = ledger
        self.client = client
        self.context = context
        self.book = delegate.book
        self._publication_state: dict[str, Any] | None = None
        self._content: dict[str, Any] | None = None
        self._publication_copy: dict[str, Any] | None = None

    def process(self, bundle: dict[str, Any]) -> dict[str, Any]:
        items = bundle.get("items")
        if not isinstance(items, list) or len(items) != 1:
            raise DailyError("daily publication pipeline needs one source event")
        item = items[0]
        if not isinstance(item, dict):
            raise DailyError("daily publication item is invalid")
        content = item.get("content_value")
        if not isinstance(content, dict):
            raise DailyError("daily decision bundle lacks content value")
        self._content = content
        self._publication_copy = item.get("publication") or {}
        if content.get("status") == "promoted":
            candidate = _publication_candidate(item, context=self.context)
            self.ledger.prepare(
                candidate["publication_key"],
                candidate["records"],
                candidate["publish_request"],
                metadata=candidate["metadata"],
            )
            state = self.ledger.run(candidate["publication_key"], self.client)
            receipt = state.get("publish_receipt") or {}
            if (
                not state.get("completed")
                or not str(receipt.get("detailUrl") or "").strip()
            ):
                raise DailyError("gray report receipt lacks a stable detail URL")
            self._publication_state = state
        elif content.get("status") != "low_density":
            raise DailyError("daily content value result is invalid")
        result = self.delegate.process(bundle)
        self._sync_terminal(result, alert_order=None)
        return result

    def _sync_terminal(
        self,
        result: dict[str, Any],
        *,
        alert_order: int | None,
    ) -> None:
        item = result["items"][0]
        content = self._content or {}
        book = item.get("book_kol_us") or {}
        if content.get("status") == "low_density":
            terminal = {
                "kind": "source_event",
                "event_id": self.context.source_identity,
                "author": item.get("author"),
                "source_binding": {
                    "source_identity": self.context.source_identity,
                    "publication_version": self.context.publication_version,
                },
                "content_value": content,
                "gray_report": {"status": "not_created"},
                "alert": {"status": "not_created"},
                "book_kol_us": book,
                "coordinator_source_video_bytes": 0,
            }
        else:
            receipt = (self._publication_state or {}).get("publish_receipt") or {}
            notification = item.get("notification") or {}
            tier = content.get("tier")
            if tier == "report_only":
                alert = {
                    "status": "not_eligible",
                    "reason": str(
                        content.get("no_alert_reason")
                        or content.get("reason")
                        or ""
                    ),
                    "terminal_order": alert_order or 3,
                }
            elif notification.get("status") == "delivered":
                alert = {
                    "status": "delivered",
                    "receipt": notification.get("receipt"),
                    "all_recipients": True,
                    "stable_report_url": receipt.get("detailUrl"),
                    "stable_link_count": 1,
                    "terminal_order": alert_order or 3,
                }
            else:
                alert = {
                    "status": "pending",
                    "terminal_order": alert_order or 3,
                }
            terminal = {
                "kind": "source_event",
                "event_id": self.context.source_identity,
                "author": item.get("author"),
                "source_binding": {
                    "source_identity": self.context.source_identity,
                    "publication_version": self.context.publication_version,
                },
                "content_value": content,
                "gray_report": {
                    "status": "published",
                    "detail_url": receipt.get("detailUrl"),
                    "receipt": str(
                        receipt.get("idempotencyKey")
                        or receipt.get("receiptId")
                        or receipt.get("detailUrl")
                        or ""
                    ),
                    "terminal_order": 1,
                },
                "alert": alert,
                "book_kol_us": {**book, "terminal_order": 2},
                "coordinator_source_video_bytes": 0,
            }
        item["daily_terminal"] = terminal

    def deliver_wechat(
        self,
        result: dict[str, Any],
        *,
        sender: Callable[[str, str], dict[str, str]],
    ) -> dict[str, Any]:
        content = self._content or {}
        if content.get("status") == "low_density":
            delivery = self.delegate.deliver_wechat(result, sender=sender)
            self._sync_terminal(result, alert_order=None)
            return delivery
        if content.get("tier") == "report_only":
            item = result["items"][0]
            notification = item.get("notification") or {}
            notification.update(
                {
                    "status": "suppressed",
                    "reason": str(
                        content.get("no_alert_reason")
                        or content.get("reason")
                        or ""
                    ),
                }
            )
            self._sync_terminal(result, alert_order=3)
            return {
                "status": "legally_not_eligible",
                "deliveries": [],
                "skipped": [notification.get("idempotency_key")],
            }
        receipt = (self._publication_state or {}).get("publish_receipt") or {}
        detail_url = str(receipt.get("detailUrl") or "")
        item = result["items"][0]
        insight = item.get("reader_insight") or {}
        publication = self._publication_copy or {}
        title = f"投资情报｜{item.get('author')}：{reader_source_title(item)}"
        body = "\n\n".join(
            row
            for row in (
                _without_urls(insight.get("summary")),
                _without_urls(publication.get("remaining_summary")),
            )
            if row
        )
        suffix = f"\n\n查看完整报告：{detail_url}"
        body = _fit_reminder(body, suffix=suffix)

        def report_message(
            _item: dict[str, Any],
            _cross_source: dict[str, Any],
        ) -> tuple[str, str]:
            return title, body

        delivery = self.delegate.deliver_wechat(
            result,
            sender=sender,
            message_builder=report_message,
        )
        self._sync_terminal(result, alert_order=3)
        return delivery


class DailyCoordinator:
    """Public ``run``/``status``/``audit`` seam for Ticket 07."""

    def __init__(
        self,
        output_dir: Path | str,
        *,
        now: Callable[[], datetime] | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.events_path = self.output_dir / "events.jsonl"
        self.lock_path = self.output_dir / ".lock"
        self.now = now or (lambda: datetime.now(BEIJING))
        self._thread_lock = threading.RLock()

    def _beijing_now(self) -> datetime:
        value = self.now()
        if value.tzinfo is None:
            raise DailyError("daily coordinator clock needs a timezone")
        return value.astimezone(BEIJING)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with self.lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _events_unlocked(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise DailyError("daily ledger cannot be read") from exc
        rows: list[dict[str, Any]] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > MAX_LEDGER_LINE_BYTES:
                raise DailyError(f"daily ledger line {number} exceeds limit")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DailyError(
                    f"daily ledger line {number} is invalid"
                ) from exc
            event_id = str(row.get("event_id") or "")
            unsigned = dict(row)
            unsigned.pop("event_id", None)
            if event_id != _sha256(unsigned):
                raise DailyError(
                    f"daily ledger line {number} failed integrity validation"
                )
            rows.append(row)
        return rows

    def events(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._events_unlocked()

    @staticmethod
    def _last_sweep_state(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        end = next(
            (
                index
                for index in range(len(rows) - 1, -1, -1)
                if rows[index].get("event") == "sweep_completed"
            ),
            None,
        )
        if end is None:
            return None
        completed = rows[end]
        if isinstance(completed.get("source_states"), list):
            return completed
        start = next(
            (
                index
                for index in range(end - 1, -1, -1)
                if rows[index].get("event")
                in {"sweep_started", "sweep_resumed"}
            ),
            0,
        )
        attempt = rows[start : end + 1]
        legacy_failure = {
            "category": "source_error",
            "code": "legacy_unclassified_failure",
            "stage": "source_run",
            "retryable": True,
        }
        failures = {
            str(row.get("source") or ""): legacy_failure
            for row in attempt
            if row.get("event") == "source_retryable_failure"
        }
        source_states: list[dict[str, Any]] = []
        for row in attempt:
            if row.get("event") != "source_completed":
                continue
            result = row.get("result")
            if not isinstance(result, dict):
                continue
            state = {
                key: value
                for key, value in {
                    "name": str(row.get("source") or ""),
                    "status": result.get("status"),
                    "retryable": result.get("retryable"),
                    "user_action_required": result.get("user_action_required"),
                    "waiting_count": result.get("waiting_count"),
                    "waiting_items": result.get("waiting_items"),
                }.items()
                if value is not None
            }
            if state["name"] in failures:
                state["failure"] = failures[state["name"]]
            source_states.append(state)
        if any(row.get("user_action_required") for row in source_states):
            health = "blocked"
        elif failures:
            health = "degraded"
        elif any(row.get("status") == "waiting" for row in source_states):
            health = "waiting"
        else:
            health = "healthy"
        return {
            **completed,
            "health": health,
            "source_states": source_states,
        }

    def _append(self, event: str, **fields: Any) -> dict[str, Any]:
        row = {
            "schema_version": 1,
            "event": event,
            "occurred_at": self._beijing_now().isoformat(timespec="seconds"),
            **fields,
        }
        row["event_id"] = _sha256(row)
        payload = (_canonical(row) + "\n").encode("utf-8")
        if len(payload) > MAX_LEDGER_LINE_BYTES:
            raise DailyError("daily ledger event exceeds limit")
        blocked = {signal.SIGINT, signal.SIGTERM}
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.events_path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise DailyError("daily ledger append made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
        return row

    def run(
        self,
        sources: list[dict[str, Any]],
        *,
        blocker_sender: Callable[[str, str], Any] | None = None,
    ) -> dict[str, Any]:
        now = self._beijing_now()
        if now.hour not in DAYTIME_HOURS:
            return {
                "status": "outside_window",
                "silent": True,
                "beijing_time": now.isoformat(timespec="seconds"),
            }
        slot = now.strftime("%Y-%m-%dT%H:00+08:00")
        ordered = sorted(
            sources,
            key=lambda row: (int(row.get("priority", 100)), str(row.get("name", ""))),
        )
        with self._locked():
            prior_rows = self._events_unlocked()
            recorded_terminal_ids = {
                str(event.get("event_id"))
                for row in prior_rows
                if row.get("event") == "source_completed"
                for event in (row.get("result", {}).get("events") or [])
                if isinstance(event, dict) and event.get("event_id")
            }
            completed_by_source = {
                str(row.get("source")): row.get("result")
                for row in prior_rows
                if row.get("event") == "source_completed"
                and row.get("slot") == slot
                and (row.get("result") or {}).get("status")
                in {"no_update", "completed"}
            }
            self._append(
                "sweep_resumed" if completed_by_source else "sweep_started",
                slot=slot,
            )
            results: list[dict[str, Any]] = []
            for source in ordered:
                name = str(source.get("name") or "").strip()
                runner = source.get("run")
                if not name or not callable(runner):
                    raise DailyError("daily source needs a name and callable runner")
                if name in completed_by_source:
                    prior_result = completed_by_source[name]
                    if not isinstance(prior_result, dict):
                        raise DailyError("daily prior source result is invalid")
                    results.append(
                        {"name": name, **prior_result, "resumed": True}
                    )
                    continue
                self._append("source_started", slot=slot, source=name)
                try:
                    outcome = runner()
                except UserActionBlocker as exc:
                    blocker_state_rows = [
                        row
                        for row in self._events_unlocked()
                        if row.get("event")
                        in {"blocker_notified", "blocker_cleared"}
                        and row.get("source") == name
                    ]
                    active_key = (
                        str(blocker_state_rows[-1].get("blocker_key"))
                        if blocker_state_rows
                        and blocker_state_rows[-1].get("event")
                        == "blocker_notified"
                        else ""
                    )
                    notified = active_key == exc.blocker_key
                    if not notified:
                        if blocker_sender is None:
                            raise DailyError(
                                "user-action blocker requires an operational sender"
                            ) from exc
                        blocker_sender("KOL 日常运行需要你处理", exc.action)
                        self._append(
                            "blocker_notified",
                            slot=slot,
                            source=name,
                            blocker_key=exc.blocker_key,
                            action=exc.action,
                        )
                    outcome = {
                        "status": "waiting",
                        "blocker_key": exc.blocker_key,
                        "user_action_required": True,
                        "notification_sent": not notified,
                    }
                except TransientSourceError as exc:
                    failure = exc.diagnostic()
                    self._append(
                        "source_retryable_failure",
                        slot=slot,
                        source=name,
                        failure=failure,
                    )
                    outcome = {
                        "status": "waiting",
                        "retryable": True,
                        "failure": failure,
                    }
                except BaseException as exc:
                    self._append(
                        "source_interrupted",
                        slot=slot,
                        source=name,
                        error_type=type(exc).__name__,
                    )
                    raise
                if outcome is None:
                    outcome = {"status": "no_update"}
                if not isinstance(outcome, dict):
                    raise DailyError(f"daily source {name} returned an invalid result")
                status = str(outcome.get("status") or "")
                if status not in {"no_update", "completed", "waiting"}:
                    raise DailyError(
                        f"daily source {name} returned an unsupported status"
                    )
                if status == "completed":
                    events = outcome.get("events")
                    if not isinstance(events, list):
                        raise DailyError(
                            f"daily source {name} completed without events"
                        )
                    fresh_events = [
                        event
                        for event in events
                        if isinstance(event, dict)
                        and str(event.get("event_id") or "")
                        not in recorded_terminal_ids
                    ]
                    replayed_count = len(events) - len(fresh_events)
                    if fresh_events:
                        outcome = {**outcome, "events": fresh_events}
                        recorded_terminal_ids.update(
                            str(event["event_id"])
                            for event in fresh_events
                        )
                        if replayed_count:
                            outcome["replayed_terminal_count"] = replayed_count
                    else:
                        outcome = {
                            "status": "no_update",
                            "replayed_terminal_count": replayed_count,
                        }
                _validate_source_outcome(outcome)
                prior_blockers = [
                    row
                    for row in self._events_unlocked()
                    if row.get("event") == "blocker_notified"
                    and row.get("source") == name
                ]
                prior_clears = [
                    row
                    for row in self._events_unlocked()
                    if row.get("event") == "blocker_cleared"
                    and row.get("source") == name
                ]
                if (
                    not outcome.get("user_action_required")
                    and len(prior_blockers) > len(prior_clears)
                ):
                    self._append(
                        "blocker_cleared",
                        slot=slot,
                        source=name,
                        blocker_key=prior_blockers[-1].get("blocker_key"),
                    )
                summary = {"name": name, **outcome}
                results.append(summary)
                self._append(
                    "source_completed",
                    slot=slot,
                    source=name,
                    result=outcome,
                    coordinator_source_video_bytes=0,
                )
            source_states = [
                {
                    key: row[key]
                    for key in (
                        "name",
                        "status",
                        "retryable",
                        "user_action_required",
                        "waiting_count",
                        "waiting_items",
                        "failure",
                    )
                    if key in row
                }
                for row in results
            ]
            if any(row.get("user_action_required") for row in results):
                health = "blocked"
            elif any(row.get("failure") for row in results):
                health = "degraded"
            elif any(row.get("status") == "waiting" for row in results):
                health = "waiting"
            else:
                health = "healthy"
            self._append(
                "sweep_completed",
                slot=slot,
                status="completed",
                health=health,
                source_count=len(results),
                source_states=source_states,
                coordinator_source_video_bytes=0,
            )
        silent = (
            all(row["status"] in {"no_update", "waiting"} for row in results)
            and not any(row.get("failure") for row in results)
        )
        return {
            "status": "completed",
            "slot": slot,
            "health": health,
            "silent": silent,
            "source_results": results,
        }

    def status(self) -> dict[str, Any]:
        rows = self.events()
        last = self._last_sweep_state(rows)
        health = str((last or {}).get("health") or "unknown")
        return {
            "status": (
                "ready"
                if health in {"healthy", "waiting"}
                else health
                if last
                else "ready"
            ),
            "last_sweep": (
                {
                    "slot": last["slot"],
                    "status": last["status"],
                    "health": health,
                    "source_states": last.get("source_states", []),
                }
                if last
                else None
            ),
            "event_count": len(rows),
        }

    def audit(self) -> dict[str, Any]:
        rows = self.events()
        last = self._last_sweep_state(rows)
        operational_status = str((last or {}).get("health") or "unknown")
        latest_failures = [
            {
                "source": str(state.get("name") or ""),
                **state["failure"],
            }
            for state in ((last or {}).get("source_states") or [])
            if isinstance(state, dict) and isinstance(state.get("failure"), dict)
        ]
        source_bytes = sum(
            int(row.get("coordinator_source_video_bytes") or 0)
            for row in rows
        )
        source_events = [
            event
            for row in rows
            if row.get("event") == "source_completed"
            for event in (row.get("result", {}).get("events") or [])
            if isinstance(event, dict) and event.get("kind") == "source_event"
        ]
        viewpoint_events = [
            event
            for row in rows
            if row.get("event") == "source_completed"
            for event in (row.get("result", {}).get("events") or [])
            if isinstance(event, dict)
            and event.get("kind") == "viewpoint_evaluation"
        ]
        dispositions = {"low_density": 0, "promoted": 0}
        tiers = {"alert_eligible": 0, "report_only": 0}
        gray_count = 0
        reminder_count = 0
        book_trade_count = 0
        for event in source_events:
            content = event["content_value"]
            dispositions[content["status"]] += 1
            if content["status"] == "promoted":
                tiers[content["tier"]] += 1
            if event["gray_report"]["status"] == "published":
                gray_count += 1
            if event["alert"]["status"] == "delivered":
                reminder_count += 1
            if event["book_kol_us"]["status"] == "filled":
                book_trade_count += 1
        safety_status = "accepted" if source_bytes == 0 else "failed"
        return {
            "status": (
                "failed"
                if safety_status == "failed"
                else "degraded"
                if operational_status in {"blocked", "degraded"}
                else "accepted"
            ),
            "safety_status": safety_status,
            "operational_status": operational_status,
            "latest_failures": latest_failures,
            "event_count": len(rows),
            "coordinator_source_video_bytes": source_bytes,
            "ledger_head_sha256": rows[-1]["event_id"] if rows else None,
            "content_value_counts": dispositions,
            "promoted_tier_counts": tiers,
            "gray_report_count": gray_count,
            "reminder_count": reminder_count,
            "book_trade_count": book_trade_count,
            "event_ids": [str(row["event_id"]) for row in source_events],
            "interruption_count": sum(
                row.get("event") == "source_interrupted" for row in rows
            ),
            "operational_reminder_count": sum(
                row.get("event") == "blocker_notified" for row in rows
            ),
            "transient_failure_count": sum(
                row.get("event") == "source_retryable_failure" for row in rows
            ),
            "viewpoint_evaluation_count": len(viewpoint_events),
        }
