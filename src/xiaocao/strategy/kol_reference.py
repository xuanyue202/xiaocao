"""Authority-zero KOL references for paper-only strategy telemetry.

The KOL publication ledger is an append-only record of prepared artifacts and
their durable publication receipts.  Book T may read a published current
吕晓彤 ``马车`` viewpoint as shadow evidence, but the reference never changes
candidate eligibility, deterministic order, fills, sizing, or exits.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_KOL_PUBLICATION_LEDGER = Path(
    "output/live/kol_daily/publications/events.jsonl"
)
MACHENG_KOL_ID = "kol-lv-xiaotong"
MACHENG_LOCAL_THESIS_PREFIX = "lv-macheng-current-cycle-core-pool"
MACHENG_REFERENCE_SOURCE = "吕晓彤“马车”"

_THEME_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("黄金", ("黄金", "贵金属")),
    ("半导体设备", ("半导体设备", "芯片设备", "晶圆设备", "半导体", "芯片")),
    ("机器人", ("机器人", "人形机器人", "智造")),
    ("人工智能", ("人工智能", "ai", "算力", "cpo", "光模块")),
    ("创新药", ("创新药",)),
)


def unavailable_macheng_reference(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": MACHENG_REFERENCE_SOURCE,
        "authority": "shadow_only",
        "reason": str(reason or "current published MaChe viewpoint unavailable"),
        "members": [],
        "ranking_effect": False,
        "eligibility_effect": False,
    }


def _records(artifact: Any) -> list[dict[str, Any]]:
    if not isinstance(artifact, dict):
        return []
    rows = artifact.get("records")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return value if isinstance(value, dict) else {}


def _is_macheng_viewpoint(record: dict[str, Any]) -> bool:
    if record.get("kind") != "viewpoint":
        return False
    payload = _payload(record)
    if str(payload.get("kol_id") or "") != MACHENG_KOL_ID:
        return False
    local_id = str(payload.get("local_thesis_id") or "")
    subject = str(payload.get("subject") or "")
    return local_id.startswith(MACHENG_LOCAL_THESIS_PREFIX) or "马车" in subject


def _latest_by_time(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
    *,
    field: str,
) -> dict[str, Any]:
    if current is None:
        return candidate
    return (
        candidate
        if str(candidate.get(field) or "") >= str(current.get(field) or "")
        else current
    )


def _member_rows(viewpoint: dict[str, Any]) -> list[dict[str, str]]:
    refs = viewpoint.get("evidence_refs")
    if not isinstance(refs, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        member_id = str(ref.get("claim_id") or "").strip()
        label = " ".join(str(ref.get("excerpt") or "").split()).strip()
        if not member_id or not label:
            continue
        key = (member_id, label)
        if key in seen:
            continue
        seen.add(key)
        out.append({"member_id": member_id, "label": label})
    return out


def load_current_macheng_reference(
    ledger_path: str | Path = DEFAULT_KOL_PUBLICATION_LEDGER,
) -> dict[str, Any]:
    """Read the latest durably published current MaChe viewpoint.

    A prepared artifact is never authoritative by itself.  Its publication key
    must have a later ``publication_receipt`` whose state is ``published`` or
    ``superseded``.  Across those artifacts, the newest evaluation for each
    viewpoint decides currentness.
    """

    path = Path(ledger_path)
    if not path.is_file():
        return unavailable_macheng_reference("publication_ledger_missing")

    prepared: dict[str, dict[str, Any]] = {}
    published_keys: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                publication_key = str(event.get("publication_key") or "").strip()
                if not publication_key:
                    continue
                if event.get("event") == "publication_prepared" and _records(event.get("artifact")):
                    prepared[publication_key] = event
                elif event.get("event") == "publication_receipt":
                    receipt = event.get("receipt")
                    if isinstance(receipt, dict) and receipt.get("recordState") in {
                        "published",
                        "superseded",
                    }:
                        published_keys.add(publication_key)
    except OSError:
        return unavailable_macheng_reference("publication_ledger_unreadable")

    viewpoints: dict[str, dict[str, Any]] = {}
    evaluations: dict[str, dict[str, Any]] = {}
    reports: dict[str, dict[str, Any]] = {}
    evaluation_publication_keys: dict[str, str] = {}
    for publication_key, event in prepared.items():
        if publication_key not in published_keys:
            continue
        for record in _records(event.get("artifact")):
            payload = _payload(record)
            if record.get("kind") == "report":
                report_id = str(record.get("record_id") or "")
                if report_id:
                    reports[report_id] = payload
            elif _is_macheng_viewpoint(record):
                viewpoint_id = str(record.get("record_id") or "")
                if viewpoint_id:
                    viewpoints[viewpoint_id] = payload
            elif record.get("kind") == "viewpoint_evaluation":
                viewpoint_id = str(payload.get("viewpoint_id") or "")
                if viewpoint_id:
                    latest = _latest_by_time(
                        evaluations.get(viewpoint_id),
                        payload,
                        field="evaluated_at",
                    )
                    evaluations[viewpoint_id] = latest
                    if latest is payload:
                        evaluation_publication_keys[viewpoint_id] = publication_key

    current: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for viewpoint_id, viewpoint in viewpoints.items():
        evaluation = evaluations.get(viewpoint_id)
        if not evaluation or evaluation.get("status") != "current":
            continue
        members = _member_rows(viewpoint)
        if not members:
            continue
        current.append(
            (
                str(evaluation.get("evaluated_at") or evaluation.get("as_of") or ""),
                str(viewpoint.get("source_published_at") or ""),
                viewpoint,
                evaluation,
            )
        )
    if not current:
        return unavailable_macheng_reference("no_current_published_macheng_viewpoint")

    _, _, viewpoint, evaluation = max(current, key=lambda row: (row[0], row[1]))
    viewpoint_id = str(viewpoint.get("viewpoint_id") or "")
    report_id = str(viewpoint.get("report_id") or "")
    report = reports.get(report_id, {})
    return {
        "status": "current",
        "source": MACHENG_REFERENCE_SOURCE,
        "authority": "shadow_only",
        "reason": "published_current_longitudinal_viewpoint",
        "members": _member_rows(viewpoint),
        "viewpoint_id": viewpoint_id,
        "report_id": report_id,
        "report_title": str(report.get("title") or ""),
        "source_published_at": str(viewpoint.get("source_published_at") or ""),
        "evaluated_at": str(evaluation.get("evaluated_at") or ""),
        "as_of": str(evaluation.get("as_of") or ""),
        "publication_key": evaluation_publication_keys.get(viewpoint_id, ""),
        "ranking_effect": False,
        "eligibility_effect": False,
    }


def _aliases_for_member(label: str) -> tuple[str, ...]:
    normalized = str(label or "").lower().replace(" ", "")
    aliases: list[str] = []
    for marker, values in _THEME_ALIASES:
        if marker.lower() in normalized:
            aliases.extend(values)
    if aliases:
        return tuple(dict.fromkeys(alias.lower() for alias in aliases))
    fallback = normalized.replace("etf", "")
    return (fallback,) if fallback else ()


def match_macheng_members(
    reference: dict[str, Any],
    *,
    values: Iterable[Any],
) -> list[dict[str, str]]:
    if reference.get("status") != "current":
        return []
    haystack = " ".join(str(value or "") for value in values).lower()
    matches: list[dict[str, str]] = []
    for member in reference.get("members", []):
        if not isinstance(member, dict):
            continue
        label = str(member.get("label") or "")
        if any(alias and alias in haystack for alias in _aliases_for_member(label)):
            matches.append(
                {
                    "member_id": str(member.get("member_id") or ""),
                    "label": label,
                }
            )
    return matches


def annotate_macheng_reference(
    row: dict[str, Any],
    reference: dict[str, Any] | None,
) -> dict[str, Any]:
    reference = reference or unavailable_macheng_reference("reference_not_supplied")
    matches = match_macheng_members(
        reference,
        values=(
            row.get("code"),
            row.get("name"),
            row.get("category_code"),
            row.get("category_name"),
        ),
    )
    out = dict(row)
    out.update(
        {
            "kol_reference_status": reference.get("status", "unavailable"),
            "kol_reference_source": MACHENG_REFERENCE_SOURCE,
            "kol_reference_authority": "shadow_only",
            "kol_reference_match": bool(matches),
            "kol_reference_matches": [item["label"] for item in matches],
            "kol_reference_member_ids": [item["member_id"] for item in matches],
            "kol_reference_members": [
                str(item.get("label") or "")
                for item in reference.get("members", [])
                if isinstance(item, dict) and str(item.get("label") or "")
            ],
            "kol_reference_viewpoint_id": reference.get("viewpoint_id"),
            "kol_reference_report_id": reference.get("report_id"),
            "kol_reference_source_published_at": reference.get("source_published_at"),
            "kol_reference_evaluated_at": reference.get("evaluated_at"),
            "kol_reference_rank_effect": "none_shadow_only",
            "kol_reference_eligibility_effect": "none_shadow_only",
        }
    )
    return out
