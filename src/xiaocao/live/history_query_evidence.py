"""Proof required before a visible history table can describe a whole date."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime


def history_query_evidence(readback: dict, *, kind: str, trade_date: str) -> dict:
    """Validate native scope evidence; request metadata never proves coverage."""
    scope = readback.get("history_scope")
    scope = scope if isinstance(scope, dict) else {}
    rows = readback.get("rows", [])
    evidence = {
        "source": "adapter_normalized_query_readback",
        "digest_scope": "before_credential_key_redaction",
        "kind": kind,
        "requested_start": trade_date,
        "requested_end": trade_date,
        "observed_at": readback.get("observed_at"),
        "normalized_capture_sha256": hashlib.sha256(json.dumps(
            readback, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest(),
        "row_count": len(rows),
        "scope_start": scope.get("start_date"),
        "scope_end": scope.get("end_date"),
        "scope_observed_at": scope.get("observed_at"),
        "date_controls_proven": scope.get("date_controls_proven") is True,
        "all_pages_captured": scope.get("all_pages_captured") is True,
        "total_row_count": scope.get("total_row_count"),
        "complete": False,
    }
    reason = "NATIVE_HISTORY_QUERY_SCOPE_UNPROVEN"
    if (scope.get("schema_version") == "native-history-scope.v1"
            and scope.get("kind") == kind
            and scope.get("date_controls_proven") is True):
        reason = "NATIVE_HISTORY_QUERY_DATE_RANGE_MISMATCH"
        if scope.get("start_date") == scope.get("end_date") == trade_date:
            reason = "NATIVE_HISTORY_QUERY_CAPTURE_INCOMPLETE"
            total = scope.get("total_row_count")
            if (scope.get("all_pages_captured") is True
                    and type(total) is int and total == len(rows)
                    and readback.get("row_count") == total):
                reason = "NATIVE_HISTORY_QUERY_CAPTURE_BINDING_UNPROVEN"
                try:
                    observed = datetime.fromisoformat(str(readback.get("observed_at", "")).replace("Z", "+00:00"))
                    bound = datetime.fromisoformat(str(scope.get("observed_at", "")).replace("Z", "+00:00"))
                    date.fromisoformat(trade_date)
                    bound_ok = observed.utcoffset() is not None and bound.utcoffset() is not None and observed == bound
                except (ValueError, TypeError):
                    bound_ok = False
                if bound_ok:
                    column = "委托日期" if kind == "history-orders" else "成交日期"
                    reason = "NATIVE_HISTORY_QUERY_ROWS_OUTSIDE_PROVEN_RANGE"
                    if all(str(row.get(column, "")).strip() == trade_date.replace("-", "") for row in rows):
                        evidence.update(complete=True, reason=None)
                        return evidence
    evidence["reason"] = reason
    return evidence
