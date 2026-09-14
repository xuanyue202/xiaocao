"""Reviewed source analysis handoff, with zero trading authority.

The writer prepares semantics once. A consumer still checks current applicability
and publishes a separate trading decision against current account/freeze facts.
"""
import json
import os
import tempfile
from pathlib import Path

from .publication import canonical_sha256


def source_fingerprint(context: dict) -> str:
    reports = sorted(
        ({"report_id": r["report_id"], "content_sha256": r["content_sha256"]}
         for r in context["report_index"]), key=lambda r: r["report_id"])
    records = {kind: sorted(({"record_id": r["record_id"], "content_sha256": r["content_sha256"]}
                            for r in context.get(kind, [])), key=lambda r: r["record_id"])
               for kind in ("viewpoints", "evaluations", "relations")}
    return canonical_sha256({"reports": reports, "records": records})


def publish_preparation(root: Path, context: dict, notes: dict, review: dict) -> dict:
    body = {k: v for k, v in context.items() if k != "context_sha256"}
    if canonical_sha256(body) != context["context_sha256"]:
        raise ValueError("context_hash_mismatch")
    if notes.get("schema_version") != "kol-source-preparation.v1" or notes.get("authority") != 0:
        raise ValueError("source_only_preparation_required")
    if notes.get("context_sha256") != context["context_sha256"]:
        raise ValueError("notes_context_mismatch")
    if not notes.get("analyst_agent_id") or review.get("reviewer_agent_id") in (None, "", notes["analyst_agent_id"]):
        raise ValueError("independent_reviewer_required")
    if review.get("notes_sha256") != canonical_sha256(notes) or review.get("status") != "approved":
        raise ValueError("review_binding_invalid")
    if not all(review.get(flag) is True for flag in ("source_fidelity", "conditions_preserved", "counterevidence_checked")):
        raise ValueError("review_incomplete")
    expected = {r["report_id"] for r in context["reports"]}
    rows = notes.get("sources", [])
    if {r.get("report_id") for r in rows} != expected or len(rows) != len(expected):
        raise ValueError("selected_source_coverage_incomplete")
    for row in rows:
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in
                   ("analysis", "conditions", "counterevidence", "time_scope")):
            raise ValueError("source_analysis_incomplete")
    if not notes.get("coverage_limits"):
        raise ValueError("coverage_limits_required")
    packet = {"schema_version": "kol-source-preparation-record.v1", "authority": 0,
              "source_fingerprint": source_fingerprint(context),
              "context_sha256": context["context_sha256"],
              "notes": notes, "review": review,
              "coverage": context["coverage"]}
    packet["packet_sha256"] = canonical_sha256(packet)
    directory = root / "output/live/kol_policy/preparations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{packet['packet_sha256']}.json"
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2)
    fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text() != encoded:
                raise ValueError("immutable_preparation_conflict")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"status": "prepared", "authority": 0, "path": str(path.resolve()),
            "source_fingerprint": packet["source_fingerprint"]}


def preparation_status(root: Path, context: dict) -> dict:
    fingerprint = source_fingerprint(context)
    matches = []
    for path in (root / "output/live/kol_policy/preparations").glob("*.json"):
        packet = json.loads(path.read_text())
        digest = packet.pop("packet_sha256", None)
        if digest != canonical_sha256(packet) or packet.get("authority") != 0:
            raise ValueError("preparation_corrupt")
        if packet.get("source_fingerprint") == fingerprint:
            matches.append((packet["review"].get("reviewed_at", ""), str(path.resolve())))
    return {"status": "prepared" if matches else "source_analysis_required", "authority": 0,
            "source_fingerprint": fingerprint, "path": max(matches)[1] if matches else None,
            "current_applicability_review_required": True}
