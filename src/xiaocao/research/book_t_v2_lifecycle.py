"""Append-only evidence lifecycle for the Book T v2 shadow seam.

The morning producer owns only the decision and deterministic fill/skip
evidence.  Close, exit, and outcome events are appended later against the same
immutable decision identity.  This module is intentionally independent from
the formal Book T ledger: it stores JSON evidence under the research
namespace, never positions, balances, or trades.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from xiaocao.kol.publication import canonical_sha256


BOOK_T_V2_EVIDENCE_SCHEMA_VERSION = 1
BOOK_T_V2_EVIDENCE_NAMESPACE = "book_t_v2_evidence"
BOOK_T_V2_LIFECYCLE_PROTOCOL_ID = "book-t-v2-evidence-lifecycle-v1"
BOOK_T_V2_STAGE_ORDER = ("decision", "fill", "daily_mark", "exit", "matured")
BOOK_T_V2_REAL_BURN_IN_DAYS = 20

_STAGE_RANK = {stage: index for index, stage in enumerate(BOOK_T_V2_STAGE_ORDER)}
_FORBIDDEN_MORNING_KEYS = frozenset(
    {
        "exit",
        "exit_date",
        "exit_price",
        "strat_ret",
        "base_ret",
        "realized_return",
        "realized_pnl",
    }
)
_ZERO_MUTATIONS = {"positions": 0, "account": 0, "trades": 0}


class BookTV2EvidenceError(ValueError):
    """Raised when lifecycle evidence is malformed or looks ahead."""


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise BookTV2EvidenceError("Book T v2 evidence must be canonical JSON") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date(value: Any) -> str:
    text = _text(value)
    if len(text) < 10:
        raise BookTV2EvidenceError(f"evidence date is invalid: {value!r}")
    try:
        datetime.fromisoformat(text[:10])
    except ValueError as exc:
        raise BookTV2EvidenceError(f"evidence date is invalid: {value!r}") from exc
    return text[:10]


def _utc(value: Any) -> str:
    text = _text(value)
    if not text:
        raise BookTV2EvidenceError("evidence observed_at is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BookTV2EvidenceError(f"evidence observed_at is invalid: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BookTV2EvidenceError("evidence observed_at must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _forbidden_key(value: Any, *, path: str = "evidence") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in _FORBIDDEN_MORNING_KEYS:
                return f"{path}.{key}"
            found = _forbidden_key(child, path=f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _forbidden_key(child, path=f"{path}[{index}]")
            if found:
                return found
    return None


def _matured_only_key(value: Any, *, path: str = "evidence") -> str | None:
    forbidden = _FORBIDDEN_MORNING_KEYS - {"exit", "exit_date", "exit_price"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in forbidden:
                return f"{path}.{key}"
            found = _matured_only_key(child, path=f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _matured_only_key(child, path=f"{path}[{index}]")
            if found:
                return found
    return None


def _require_row_dates(
    rows: Iterable[Mapping[str, Any]],
    *,
    minimum_day: str,
    label: str,
    exact: bool = False,
) -> None:
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise BookTV2EvidenceError(f"{label} row {index} is not an object")
        row_day = _date(row.get("as_of") or row.get("trade_date") or row.get("date"))
        if (exact and row_day != minimum_day) or (not exact and row_day < minimum_day):
            qualifier = "must equal" if exact else "must not precede"
            raise BookTV2EvidenceError(
                f"{label} row {index} date {row_day} {qualifier} {minimum_day}"
            )


def _event_body(
    *,
    decision_id: str,
    stage: str,
    observed_at: str,
    data: Mapping[str, Any],
) -> dict[str, Any]:
    if stage not in _STAGE_RANK:
        raise BookTV2EvidenceError(f"unknown lifecycle stage: {stage}")
    payload = {
        "schema_version": BOOK_T_V2_EVIDENCE_SCHEMA_VERSION,
        "namespace": BOOK_T_V2_EVIDENCE_NAMESPACE,
        "protocol_id": BOOK_T_V2_LIFECYCLE_PROTOCOL_ID,
        "decision_id": _text(decision_id),
        "stage": stage,
        "observed_at": _utc(observed_at),
        "data": _copy(dict(data)),
    }
    if not payload["decision_id"]:
        raise BookTV2EvidenceError("decision_id is required")
    return payload


def _seal_event(body: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(dict(body))
    value.pop("event_id", None)
    value["event_id"] = canonical_sha256(value)
    return value


def _seal_lifecycle(body: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(dict(body))
    value.pop("evidence_lifecycle_sha256", None)
    value["evidence_lifecycle_sha256"] = canonical_sha256(value)
    return value


def build_initial_lifecycle(
    *,
    decision_id: str,
    as_of: str,
    observed_at: str,
    trading_day_index: int,
    run_mode: str,
    snapshot_sha256: str,
    universe_sha256: str,
    selection_plan_sha256: str,
    portfolio_sha256: str,
    control_receipt_sha256: str,
    fills: Iterable[Mapping[str, Any]],
    daily_reevaluation_complete: bool,
    formal_ledger_mutations: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the immutable decision/fill portion of one shadow day.

    ``run_mode=real`` is reserved for a real trading day observed by the
    production shell.  Tests and rehearsals must use ``rehearsal`` and are
    excluded from the burn-in count.
    """

    day = _date(as_of)
    mode = _text(run_mode).lower()
    if mode not in {"real", "rehearsal"}:
        raise BookTV2EvidenceError("run_mode must be real or rehearsal")
    if isinstance(trading_day_index, bool) or int(trading_day_index) < 0:
        raise BookTV2EvidenceError("trading_day_index must be a non-negative integer")
    rows = [_copy(dict(row)) for row in fills]
    for index, row in enumerate(rows):
        row_day = _date(row.get("as_of") or row.get("trade_date") or day)
        if row_day != day:
            raise BookTV2EvidenceError(f"fill row {index} is not bound to {day}")
        if _text(row.get("status")).lower() not in {"filled", "skipped", "blocked"}:
            raise BookTV2EvidenceError(f"fill row {index} has an invalid status")
    if (found := _forbidden_key(rows, path="fill")) is not None:
        raise BookTV2EvidenceError(f"morning evidence contains future outcome field: {found}")
    mutations = _copy(dict(formal_ledger_mutations or _ZERO_MUTATIONS))
    if mutations != _ZERO_MUTATIONS:
        raise BookTV2EvidenceError("shadow lifecycle claims a formal ledger mutation")

    decision_data = {
        "as_of": day,
        "snapshot_sha256": _text(snapshot_sha256),
        "universe_sha256": _text(universe_sha256),
        "selection_plan_sha256": _text(selection_plan_sha256),
        "portfolio_sha256": _text(portfolio_sha256),
        "control_receipt_sha256": _text(control_receipt_sha256),
        "daily_reevaluation_complete": bool(daily_reevaluation_complete),
        "formal_ledger_mutations": mutations,
    }
    fill_data = {"as_of": day, "rows": rows}
    decision_event = _seal_event(
        _event_body(
            decision_id=decision_id,
            stage="decision",
            observed_at=observed_at,
            data=decision_data,
        )
    )
    fill_event = _seal_event(
        _event_body(
            decision_id=decision_id,
            stage="fill",
            observed_at=observed_at,
            data=fill_data,
        )
    )
    body = {
        "schema_version": BOOK_T_V2_EVIDENCE_SCHEMA_VERSION,
        "namespace": BOOK_T_V2_EVIDENCE_NAMESPACE,
        "protocol_id": BOOK_T_V2_LIFECYCLE_PROTOCOL_ID,
        "decision_id": _text(decision_id),
        "as_of": day,
        "run_mode": mode,
        "provenance": {
            "kind": "real" if mode == "real" else "rehearsal",
            "is_rehearsal": mode == "rehearsal",
            "source": "book_t_v2_production_adapters" if mode == "real" else "isolated_rehearsal",
        },
        "trading_day_index": int(trading_day_index),
        "stages": [decision_event, fill_event],
        "outcome_status": "outcome_pending"
        if any(_text(row.get("status")).lower() == "filled" for row in rows)
        else "not_applicable",
        "engineering_day": {
            "daily_reevaluation_complete": bool(daily_reevaluation_complete),
            "formal_ledger_mutations": mutations,
            "replayable": True,
        },
    }
    return _seal_lifecycle(body)


def validate_lifecycle(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a frozen lifecycle and return a detached copy."""

    body = _copy(dict(value))
    if body.get("namespace") != BOOK_T_V2_EVIDENCE_NAMESPACE:
        raise BookTV2EvidenceError("unexpected evidence lifecycle namespace")
    if body.get("protocol_id") != BOOK_T_V2_LIFECYCLE_PROTOCOL_ID:
        raise BookTV2EvidenceError("unexpected evidence lifecycle protocol")
    if int(body.get("schema_version", 0)) != BOOK_T_V2_EVIDENCE_SCHEMA_VERSION:
        raise BookTV2EvidenceError("unsupported evidence lifecycle schema")
    actual = _text(body.get("evidence_lifecycle_sha256"))
    unsigned = dict(body)
    unsigned.pop("evidence_lifecycle_sha256", None)
    if not actual or actual != canonical_sha256(unsigned):
        raise BookTV2EvidenceError("evidence_lifecycle_sha256 does not match payload")
    day = _date(body.get("as_of"))
    decision_id = _text(body.get("decision_id"))
    mode = _text(body.get("run_mode")).lower()
    if mode not in {"real", "rehearsal"}:
        raise BookTV2EvidenceError("evidence lifecycle run_mode is invalid")
    provenance = body.get("provenance")
    if not isinstance(provenance, Mapping):
        raise BookTV2EvidenceError("evidence lifecycle provenance is required")
    if (provenance.get("kind") == "real") != (mode == "real"):
        raise BookTV2EvidenceError("evidence lifecycle provenance does not match run_mode")
    if mode == "real" and provenance.get("is_rehearsal") is not False:
        raise BookTV2EvidenceError("real evidence cannot be marked as rehearsal")
    try:
        day_index = int(body.get("trading_day_index"))
    except (TypeError, ValueError) as exc:
        raise BookTV2EvidenceError("evidence lifecycle trading_day_index is invalid") from exc
    if day_index < 0:
        raise BookTV2EvidenceError("evidence lifecycle trading_day_index is invalid")
    stages = body.get("stages")
    if not isinstance(stages, list) or not stages:
        raise BookTV2EvidenceError("evidence lifecycle stages are required")
    seen: set[str] = set()
    last_rank = -1
    for index, raw in enumerate(stages):
        if not isinstance(raw, Mapping):
            raise BookTV2EvidenceError(f"evidence stage {index} is not an object")
        event = _copy(dict(raw))
        stage = _text(event.get("stage"))
        if stage not in _STAGE_RANK:
            raise BookTV2EvidenceError(f"evidence stage {index} is invalid")
        if stage in seen:
            raise BookTV2EvidenceError(f"duplicate evidence stage: {stage}")
        seen.add(stage)
        rank = _STAGE_RANK[stage]
        if rank < last_rank:
            raise BookTV2EvidenceError("evidence stages are out of order")
        last_rank = rank
        if _text(event.get("decision_id")) != decision_id:
            raise BookTV2EvidenceError("evidence stage decision_id mismatch")
        if event.get("namespace") != BOOK_T_V2_EVIDENCE_NAMESPACE:
            raise BookTV2EvidenceError(f"evidence stage {index} namespace is invalid")
        if event.get("protocol_id") != BOOK_T_V2_LIFECYCLE_PROTOCOL_ID:
            raise BookTV2EvidenceError(f"evidence stage {index} protocol is invalid")
        if int(event.get("schema_version", 0)) != BOOK_T_V2_EVIDENCE_SCHEMA_VERSION:
            raise BookTV2EvidenceError(f"evidence stage {index} schema is invalid")
        if not isinstance(event.get("data"), Mapping):
            raise BookTV2EvidenceError(f"evidence stage {index} data is invalid")
        expected_event = dict(event)
        event_id = _text(expected_event.pop("event_id", ""))
        if not event_id or event_id != canonical_sha256(expected_event):
            raise BookTV2EvidenceError(f"evidence stage {index} event_id is invalid")
        observed_day = _date(event.get("observed_at"))
        if observed_day < day:
            raise BookTV2EvidenceError("evidence stage precedes decision day")
        if stage in {"decision", "fill"} and _forbidden_key(event.get("data"), path=f"stages[{index}].data"):
            raise BookTV2EvidenceError("frozen morning evidence contains a future outcome field")
    if "decision" not in seen or "fill" not in seen:
        raise BookTV2EvidenceError("frozen lifecycle requires decision and fill stages")
    if _text(body.get("outcome_status")) not in {"outcome_pending", "not_applicable"}:
        raise BookTV2EvidenceError("evidence lifecycle outcome_status is invalid")
    engineering = body.get("engineering_day")
    if not isinstance(engineering, Mapping):
        raise BookTV2EvidenceError("engineering_day is required")
    if dict(engineering.get("formal_ledger_mutations") or {}) != _ZERO_MUTATIONS:
        raise BookTV2EvidenceError("evidence lifecycle claims a formal ledger mutation")
    if engineering.get("replayable") is not True:
        raise BookTV2EvidenceError("evidence lifecycle is not replayable")
    return body


def append_events(path: Path | str, events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Atomically merge lifecycle events; identical retries are no-ops."""

    target = Path(path)
    existing = read_events(target) if target.exists() else []
    by_id = {str(row["event_id"]): row for row in existing}
    stage_by_decision = {
        (_text(row.get("decision_id")), _text(row.get("stage"))): str(row["event_id"])
        for row in existing
    }
    for raw in events:
        event = _copy(dict(raw))
        event_id = _text(event.get("event_id"))
        if not event_id:
            raise BookTV2EvidenceError("lifecycle event_id is required")
        expected = dict(event)
        expected.pop("event_id", None)
        if event_id != canonical_sha256(expected):
            raise BookTV2EvidenceError("lifecycle event_id does not match payload")
        previous = by_id.get(event_id)
        if previous is not None and previous != event:
            raise BookTV2EvidenceError("lifecycle event identity was reused with new payload")
        stage_key = (_text(event.get("decision_id")), _text(event.get("stage")))
        previous_stage_id = stage_by_decision.get(stage_key)
        if previous_stage_id is not None and previous_stage_id != event_id:
            raise BookTV2EvidenceError(
                f"lifecycle stage already recorded for decision: {stage_key[0]}:{stage_key[1]}"
            )
        by_id[event_id] = event
        stage_by_decision[stage_key] = event_id
    merged = sorted(
        by_id.values(),
        key=lambda row: (
            _text(row.get("decision_id")),
            _STAGE_RANK.get(_text(row.get("stage")), 999),
            _text(row.get("observed_at")),
            _text(row.get("event_id")),
        ),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in merged
    )
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    return merged


def read_events(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BookTV2EvidenceError(f"invalid lifecycle event line {line_number}") from exc
        if not isinstance(row, dict):
            raise BookTV2EvidenceError(f"lifecycle event line {line_number} is not an object")
        event_id = _text(row.get("event_id"))
        unsigned = dict(row)
        unsigned.pop("event_id", None)
        if not event_id or event_id != canonical_sha256(unsigned):
            raise BookTV2EvidenceError(f"lifecycle event line {line_number} failed integrity check")
        rows.append(row)
    return rows


def build_daily_mark_event(
    lifecycle: Mapping[str, Any],
    *,
    observed_at: str,
    marks: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a close mark without manufacturing a return or an exit."""

    frozen = validate_lifecycle(lifecycle)
    rows = [_copy(dict(row)) for row in marks]
    decision_day = _date(frozen["as_of"])
    mark_day = _date(observed_at)
    if mark_day != decision_day:
        raise BookTV2EvidenceError("daily mark must be observed on the decision day")
    _require_row_dates(rows, minimum_day=decision_day, label="daily_mark", exact=True)
    if (found := _forbidden_key(rows, path="daily_mark")) is not None:
        raise BookTV2EvidenceError(f"daily mark contains a future outcome field: {found}")
    return _seal_event(
        _event_body(
            decision_id=_text(frozen["decision_id"]),
            stage="daily_mark",
            observed_at=observed_at,
            data={"as_of": _date(observed_at), "rows": rows},
        )
    )


def build_exit_event(
    lifecycle: Mapping[str, Any],
    *,
    observed_at: str,
    exits: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create an explicit exit event from later observed execution facts."""

    frozen = validate_lifecycle(lifecycle)
    rows = [_copy(dict(row)) for row in exits]
    decision_day = _date(frozen["as_of"])
    if _date(observed_at) < decision_day:
        raise BookTV2EvidenceError("exit observation precedes its decision day")
    _require_row_dates(rows, minimum_day=decision_day, label="exit")
    if _matured_only_key(rows, path="exit") is not None:
        raise BookTV2EvidenceError("exit evidence contains a matured-return field")
    return _seal_event(
        _event_body(
            decision_id=_text(frozen["decision_id"]),
            stage="exit",
            observed_at=observed_at,
            data={"as_of": _date(observed_at), "rows": rows},
        )
    )


def build_matured_outcome_event(
    lifecycle: Mapping[str, Any],
    *,
    observed_at: str,
    outcomes: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a matured outcome only from explicit later return facts."""

    frozen = validate_lifecycle(lifecycle)
    rows = [_copy(dict(row)) for row in outcomes]
    if not rows:
        raise BookTV2EvidenceError("matured outcome rows are required")
    decision_day = _date(frozen["as_of"])
    if _date(observed_at) < decision_day:
        raise BookTV2EvidenceError("matured observation precedes its decision day")
    _require_row_dates(rows, minimum_day=decision_day, label="matured")
    for index, row in enumerate(rows):
        for field in ("strat_ret", "base_ret"):
            try:
                value = float(row.get(field))
            except (TypeError, ValueError) as exc:
                raise BookTV2EvidenceError(
                    f"matured outcome {index}.{field} is required"
                ) from exc
            if not value == value or value in {float("inf"), float("-inf")}:
                raise BookTV2EvidenceError(f"matured outcome {index}.{field} is not finite")
    return _seal_event(
        _event_body(
            decision_id=_text(frozen["decision_id"]),
            stage="matured",
            observed_at=observed_at,
            data={"as_of": _date(observed_at), "rows": rows},
        )
    )


def lifecycle_summary(
    lifecycles: Iterable[Mapping[str, Any]],
    *,
    events: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Summarize stage completion separately from outcome maturity."""

    frozen = [validate_lifecycle(row) for row in lifecycles]
    extra = [_copy(dict(row)) for row in events]
    by_decision: dict[str, set[str]] = {
        _text(row["decision_id"]): {_text(event["stage"]) for event in row["stages"]}
        for row in frozen
    }
    for event in extra:
        by_decision.setdefault(_text(event.get("decision_id")), set()).add(_text(event.get("stage")))
    counts = {stage: sum(stage in stages for stages in by_decision.values()) for stage in BOOK_T_V2_STAGE_ORDER}
    return {
        "decisions": len(frozen),
        "stage_counts": counts,
        "outcome_pending": sum(
            row.get("outcome_status") == "outcome_pending"
            and "matured" not in by_decision.get(_text(row["decision_id"]), set())
            for row in frozen
        ),
        "outcome_matured": sum("matured" in stages for stages in by_decision.values()),
        "formal_ledger_mutations": _copy(_ZERO_MUTATIONS),
    }


def engineering_burn_in_gate(
    lifecycles: Iterable[Mapping[str, Any]],
    *,
    required_days: int = BOOK_T_V2_REAL_BURN_IN_DAYS,
) -> dict[str, Any]:
    """Count only contiguous real production days; rehearsal never counts."""

    if int(required_days) < BOOK_T_V2_REAL_BURN_IN_DAYS:
        raise BookTV2EvidenceError("required_days cannot be below the protocol minimum")
    frozen = [validate_lifecycle(row) for row in lifecycles]
    real = [row for row in frozen if row.get("run_mode") == "real" and row.get("provenance", {}).get("is_rehearsal") is False]
    real.sort(key=lambda row: (int(row["trading_day_index"]), row["as_of"], row["decision_id"]))
    failures: list[str] = []
    indices: list[int] = []
    seen: set[int] = set()
    for row in real:
        index = int(row["trading_day_index"])
        if index in seen:
            failures.append("duplicate_real_trading_day")
        seen.add(index)
        indices.append(index)
        engineering = row["engineering_day"]
        if engineering.get("daily_reevaluation_complete") is not True:
            failures.append("daily_reevaluation_incomplete")
        if engineering.get("formal_ledger_mutations") != _ZERO_MUTATIONS:
            failures.append("formal_ledger_mutation")
        if engineering.get("replayable") is not True:
            failures.append("not_replayable")
    contiguous = not indices or indices == list(range(indices[0], indices[-1] + 1))
    if not contiguous:
        failures.append("real_trading_day_gap")
    failures = sorted(set(failures))
    complete = len(real) >= int(required_days) and contiguous and not failures
    return {
        "status": "ready_for_review" if complete else "pending",
        "required_days": int(required_days),
        "real_trading_days": len(real),
        "trading_day_indices": indices,
        "contiguous": contiguous,
        "rehearsal_days_excluded": len(frozen) - len(real),
        "failures": failures,
        "complete": complete,
        "promotion_authorized": False,
    }


__all__ = [
    "BOOK_T_V2_EVIDENCE_NAMESPACE",
    "BOOK_T_V2_EVIDENCE_SCHEMA_VERSION",
    "BOOK_T_V2_LIFECYCLE_PROTOCOL_ID",
    "BOOK_T_V2_REAL_BURN_IN_DAYS",
    "BookTV2EvidenceError",
    "append_events",
    "build_daily_mark_event",
    "build_exit_event",
    "build_initial_lifecycle",
    "build_matured_outcome_event",
    "engineering_burn_in_gate",
    "lifecycle_summary",
    "read_events",
    "validate_lifecycle",
]
