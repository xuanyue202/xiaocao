"""Shared error types for KOL enrichment providers."""

from __future__ import annotations

import re
from typing import Any


class EnrichmentError(RuntimeError):
    """An enrichment step could not produce auditable evidence."""


_DIAGNOSTIC_TOKEN = re.compile(r"[a-z][a-z0-9_]{0,63}")


class EnrichmentDiagnosticError(EnrichmentError):
    """A source error carrying only credential-safe operational diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        code: str,
        stage: str,
        exit_code: int | None = None,
    ):
        values = {
            "category": str(category or "").strip(),
            "code": str(code or "").strip(),
            "stage": str(stage or "").strip(),
        }
        if any(not _DIAGNOSTIC_TOKEN.fullmatch(value) for value in values.values()):
            raise ValueError("enrichment diagnostic tokens are invalid")
        if exit_code is not None and (
            isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0
        ):
            raise ValueError("enrichment diagnostic exit code is invalid")
        self.diagnostic_category = values["category"]
        self.diagnostic_code = values["code"]
        self.diagnostic_stage = values["stage"]
        self.diagnostic_exit_code = exit_code
        super().__init__(message)


def validate_decision_process_result(result: Any) -> dict[str, Any]:
    """Validate Ticket 01 output shape before any delivery side effect."""
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise EnrichmentError("ticket 01 decision pipeline did not complete one item")
    items = result.get("items")
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], dict)
    ):
        raise EnrichmentError("ticket 01 decision pipeline did not complete one item")
    return result


def validate_decision_completion(
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed unless Ticket 01 produced both required durable outcomes."""
    if not isinstance(result, dict):
        raise EnrichmentError("ticket 01 decision pipeline result is invalid")
    items = result.get("items")
    if result.get("status") != "completed" or not isinstance(items, list) or len(items) != 1:
        raise EnrichmentError("ticket 01 decision pipeline did not complete one item")
    item = items[0]
    if not isinstance(item, dict):
        raise EnrichmentError("ticket 01 decision item is invalid")
    notification = item.get("notification") or {}
    paper = item.get("book_kol_us") or {}
    content = item.get("content_value") or {}
    report_only = (
        content.get("status") == "promoted"
        and content.get("tier") == "report_only"
        and bool(
            str(
                content.get("no_alert_reason")
                or content.get("reason")
                or ""
            ).strip()
        )
    )
    suppressed = (
        isinstance(notification, dict)
        and notification.get("status") == "suppressed"
        and (
            report_only
            or (
                item.get("decision_status") == "no_actionable_signal"
                and (item.get("reader_insight") or {}).get("status") == "none"
            )
        )
        and bool(str(notification.get("reason") or "").strip())
    )
    if (
        not isinstance(notification, dict)
        or notification.get("status") not in {"delivered", "suppressed"}
        or (notification.get("status") == "suppressed" and not suppressed)
    ):
        raise EnrichmentError("household advisory was not delivered")
    if notification.get("status") == "delivered" and not str(
        notification.get("receipt") or ""
    ).strip():
        raise EnrichmentError("household advisory requires a delivery receipt")
    if (
        not isinstance(paper, dict)
        or paper.get("status") not in {"filled", "no_trade"}
        or paper.get("book") != "KOL-US"
        or paper.get("paper_only") is not True
    ):
        raise EnrichmentError("Book KOL-US paper-only outcome is invalid")
    if paper.get("status") == "no_trade" and not str(paper.get("reason") or "").strip():
        raise EnrichmentError("Book KOL-US no_trade requires reason")
    return notification, paper
