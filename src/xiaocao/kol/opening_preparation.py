"""Reviewed, authority-zero opening briefs and source deltas.

This module never publishes a policy. Final source verification, account facts
and policy acceptance remain the responsibility of the original consumer.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from xiaocao.kol.publication import canonical_sha256
from xiaocao.kol.trading_decision import read_json
from xiaocao.runner_recovery import _hash, _write

SCHEMA = "kol-opening-preparation.v1"
RULES = ("docs/OPERATING_CONTRACT.md",
         ".codex/skills/xiaocao-trading/references/kol-trading-judgment.md",
         ".codex/skills/xiaocao-trading/references/kol-opening-preparation.md")
TZ = ZoneInfo("Asia/Shanghai")


def aware(value: str) -> datetime:
    clock = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if clock.utcoffset() is None:
        raise ValueError("KOL_PREPARATION_AWARE_TIME_REQUIRED")
    return clock


def write_artifact(directory: Path, value: dict, suffix: str) -> Path:
    path = directory / (canonical_sha256(value) + suffix)
    if path.exists():
        if path.is_symlink() or read_json(path) != value:
            raise ValueError("KOL_PREPARATION_IMMUTABILITY_VIOLATION")
    else:
        _write(path, value)
    return path.resolve()


def input_payload(projection_summary: dict, *, binding: dict, repo_root: Path) -> dict:
    projection = read_projection(projection_summary)
    return {"schema_version": 1, "authority": 0, "binding": binding,
        "projection": projection_summary, "source_fingerprint": projection["source_fingerprint"],
        "viewpoint_ids": [r["record_id"] for r in projection["active_viewpoints"]],
        "quality": projection["quality"]["status"],
        "rules": [{"path": str((repo_root / p).resolve()),
                   "sha256": hashlib.sha256((repo_root / p).read_bytes()).hexdigest()} for p in RULES],
        "instruction": "Prepare a reviewed conditional opening brief under kol-opening-preparation.md; authority=0. Read every eligible viewpoint once; no current account or order authority."}


def read_projection(summary: dict) -> dict:
    value = read_json(Path(summary["projection_path"]))
    claimed = value.get("projection_sha256")
    if (claimed != summary["projection_sha256"] or claimed != canonical_sha256(
            {k: v for k, v in value.items() if k != "projection_sha256"})
            or value.get("authority") != 0 or value.get("quality", {}).get("status") != "ready"):
        raise ValueError("KOL_PREPARATION_PROJECTION_UNPROVEN")
    return value


def _inputs(path: Path) -> tuple[dict, dict]:
    value = read_json(path)
    if (not isinstance(value.get("binding"), dict) or not value["binding"].get("owner_thread_id")
            or not value["binding"].get("automation_id") or not value["binding"].get("trade_date")
            or len(value.get("rules", [])) != len(RULES)
            or any(not rule["path"].endswith(relative) for rule, relative in zip(value["rules"], RULES))):
        raise ValueError("KOL_PREPARATION_OWNER_OR_RULES_REQUIRED")
    projection = read_projection(value["projection"])
    ids = [r["record_id"] for r in projection["active_viewpoints"]]
    if (value.get("authority") != 0 or value.get("viewpoint_ids") != ids
            or len(ids) != len(set(ids)) or value.get("source_fingerprint") != projection["source_fingerprint"]):
        raise ValueError("KOL_PREPARATION_INPUT_MISMATCH")
    for rule in value["rules"]:
        if hashlib.sha256(Path(rule["path"]).read_bytes()).hexdigest() != rule["sha256"]:
            raise ValueError("KOL_PREPARATION_RULES_CHANGED")
    return value, projection


def relation_history(projection: dict) -> dict:
    history = projection.get("related_history", [])
    ids = {row["record_id"] for row in history}
    return {"relations": projection.get("relations", []), "related_history": history,
            "latest_evaluations": [row for row in projection.get("latest_evaluations", [])
                                   if row.get("evaluation", {}).get("viewpoint_id") in ids]}


def viewpoint_units(projection: dict) -> dict:
    # A changed evaluation is a changed viewpoint even when the source text did
    # not change. Relation/history changes conservatively invalidate all units.
    shared = relation_history(projection)
    return {row["record_id"]: {"viewpoint": row,
        "evaluations": [e for e in projection.get("latest_evaluations", [])
                        if e.get("evaluation", {}).get("viewpoint_id") == row["record_id"]],
        "relation_history_sha256": canonical_sha256(shared)}
        for row in projection["active_viewpoints"]}


def draft_template(input_path: Path) -> dict:
    inputs, _ = _inputs(input_path)
    return {"schema_version": SCHEMA, "authority": 0, "input_sha256": _hash(inputs),
        "worker_id": "", "prepared_at": "", "valid_until": "",
        "implications": [], "coverage": [{"viewpoint_id": i, "implication_ids": [],
            "disposition": "", "reason": ""} for i in inputs["viewpoint_ids"]]}


def _validate_draft(draft: dict, inputs: dict, projection: dict, now: datetime) -> set[str]:
    if (draft.get("schema_version") != SCHEMA or draft.get("authority") != 0
            or draft.get("input_sha256") != _hash(inputs) or not draft.get("worker_id")):
        raise ValueError("KOL_PREPARATION_DRAFT_BINDING_INVALID")
    date = inputs["binding"]["trade_date"]
    prepared, until = aware(draft["prepared_at"]), aware(draft["valid_until"])
    if not (prepared <= now < until and prepared.astimezone(TZ).date().isoformat() == date
            and until <= aware(date + "T11:30:00+08:00")):
        raise ValueError("KOL_PREPARATION_EXPIRED_OR_FUTURE")
    units = viewpoint_units(projection)
    implications = draft["implications"]
    ids = [i["id"] for i in implications]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("KOL_PREPARATION_DUPLICATE_IMPLICATION")
    cited = set()
    for item in implications:
        sources = item["viewpoint_ids"]
        scope = item["scope"]
        if (not sources or len(sources) != len(set(sources)) or not set(sources) <= units.keys()
                or item["kind"] not in {"portfolio_posture", "mode_focus", "code_risk", "counterevidence"}
                or scope.get("kind") not in {"all", "modes", "codes"}
                or not isinstance(scope.get("values"), list)
                or (scope["kind"] == "all" and scope["values"])
                or (scope["kind"] != "all" and not scope["values"])
                or any(not isinstance(v, str) or not v for v in scope["values"])
                or (item["kind"] in {"portfolio_posture", "counterevidence"} and scope["kind"] != "all")):
            raise ValueError("KOL_PREPARATION_SCOPE_OR_SOURCE_INVALID")
        for key in ("source_wording", "interpretation", "conditions", "invalidations", "counterevidence", "proposed_effect"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError("KOL_PREPARATION_REASON_REQUIRED:" + key)
        cited.update(units[i]["viewpoint"]["report_id"] for i in sources)
    coverage = draft["coverage"]
    covered = [c["viewpoint_id"] for c in coverage]
    if len(covered) != len(set(covered)) or set(covered) != units.keys():
        raise ValueError("KOL_PREPARATION_COVERAGE_INCOMPLETE")
    for row in coverage:
        actual = {i["id"] for i in implications if row["viewpoint_id"] in i["viewpoint_ids"]}
        if (set(row["implication_ids"]) != actual
                or row.get("disposition") not in {"implication", "background", "not_applicable"}
                or (bool(actual) != (row["disposition"] == "implication"))
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            raise ValueError("KOL_PREPARATION_COVERAGE_REASON_INVALID")
    return cited


def accept_preparation(input_path: Path, draft: dict, review: dict, dispatch: dict,
                       context: dict, *, now: datetime) -> dict:
    inputs, projection = _inputs(input_path)
    cited = _validate_draft(draft, inputs, projection, now)
    if (aware(projection["as_of"]) > aware(draft["prepared_at"])
            or aware(projection["as_of"]).astimezone(TZ).date().isoformat() != inputs["binding"]["trade_date"]):
        raise ValueError("KOL_PREPARATION_PROJECTION_TIME_INVALID")
    cutoff = aware(inputs["binding"]["trade_date"] + "T09:20:00+08:00")
    args, result = dispatch.get("tool_arguments", {}), dispatch.get("tool_result", {})
    if (dispatch.get("accepted") is not True or dispatch.get("worker_id") != draft["worker_id"]
            or dispatch.get("input_sha256") != _hash(inputs) or dispatch.get("binding") != inputs["binding"]
            or args.get("model") != "gpt-6-sol" or args.get("reasoning_effort") != "xhigh"
            or args.get("fork_turns") != "none" or result.get("task_name") != draft["worker_id"]
            or not (aware(dispatch["dispatched_at"]) <= aware(draft["prepared_at"]) <= now < cutoff)):
        raise ValueError("KOL_PREPARATION_DISPATCH_OR_DEADLINE_INVALID")
    context_sha = canonical_sha256({k: v for k, v in context.items() if k != "context_sha256"})
    reports = {r["report_id"]: r for r in context.get("reports", [])}
    for row in projection["active_viewpoints"]:
        if row["report_id"] in cited:
            report = reports.get(row["report_id"], {})
            if (report.get("content_sha256") != row["report_content_sha256"]
                    or not report.get("report_body") or report.get("report_body_sha256") !=
                    hashlib.sha256(report["report_body"].encode("utf-8")).hexdigest()):
                raise ValueError("KOL_PREPARATION_CITED_BODY_MISMATCH")
    if (context.get("context_sha256") != context_sha or context.get("authority") != 0
            or not cited <= {r["report_id"] for r in context.get("reports", [])}
            or aware(context["as_of"]) > aware(draft["prepared_at"])):
        raise ValueError("KOL_PREPARATION_CITED_CONTEXT_REQUIRED")
    if (review.get("accepted") is not True or review.get("draft_sha256") != canonical_sha256(draft)
            or review.get("context_sha256") != context_sha
            or review.get("dispatch_sha256") != canonical_sha256(dispatch)
            or not review.get("reviewer_id") or review["reviewer_id"] == draft["worker_id"]
            or not (aware(draft["prepared_at"]) <= aware(review["reviewed_at"]) <= now)
            or any(review.get(k) is not True for k in
                   ("all_viewpoints_covered", "source_fidelity_checked", "conditions_and_counterevidence_checked"))):
        raise ValueError("KOL_PREPARATION_INDEPENDENT_REVIEW_REQUIRED")
    value = {"schema_version": SCHEMA, "authority": 0, "accepted_at": now.isoformat(),
        "input_path": str(input_path.resolve()), "input_sha256": _hash(inputs),
        "worker_id": draft["worker_id"], "source_fingerprint": inputs["source_fingerprint"],
        "binding": inputs["binding"], "rules": inputs["rules"],
        "projection": inputs["projection"], "draft": draft, "review": review,
        "dispatch": dispatch, "context": context}
    return {**value, "preparation_sha256": canonical_sha256(value)}


def read_preparation(path: Path, *, now: datetime) -> dict:
    value = read_json(path)
    if value.get("preparation_sha256") != canonical_sha256(
            {k: v for k, v in value.items() if k != "preparation_sha256"}):
        raise ValueError("KOL_PREPARATION_HASH_MISMATCH")
    replay = accept_preparation(Path(value["input_path"]), value["draft"], value["review"],
                                value["dispatch"], value["context"], now=aware(value["accepted_at"]))
    if replay != value or now < aware(value["accepted_at"]) or now >= aware(value["draft"]["valid_until"]):
        raise ValueError("KOL_PREPARATION_EXPIRED_OR_ALTERED")
    return value


def normalized_review_facts(request: dict) -> dict:
    """Preserve execution facts; expose legacy missing optional K/P scores as null."""
    payload = dict(request)
    candidates = [dict(row) for row in payload.get("candidates", [])]
    missing = []
    for index, row in enumerate(candidates):
        for field in ("k_score", "p_score"):
            value = row.get(field)
            if isinstance(value, float) and math.isnan(value):
                row[field] = None
                missing.append({"candidate_index": index, "code": row.get("code"),
                                "field": field, "source_value": "NaN"})
    if missing:
        payload.update(candidates=candidates, candidate_missing_values=missing)
    return payload


def opening_packet(preparation_path: Path, current_input_path: Path, request: dict, *, now: datetime) -> dict:
    request = normalized_review_facts(request)
    prepared = read_preparation(preparation_path, now=now)
    current, projection = _inputs(current_input_path)
    if (now.utcoffset() is None or not request.get("freeze_sha256") or not request.get("strategy_sha")
            or prepared["binding"] != current["binding"] or prepared["rules"] != current["rules"]
            or request["trade_date"] != current["binding"]["trade_date"]
            or not (aware(request["requested_at"]) <= now < aware(request["review_wait_until"]))
            or aware(request["review_wait_until"]) > aware(request["trade_date"] + "T09:27:00+08:00")):
        raise ValueError("KOL_PREPARATION_CURRENT_REQUEST_INVALID")
    if (aware(projection["as_of"]) > now or aware(projection["as_of"]) < aware(prepared["accepted_at"])
            or now.astimezone(TZ).date().isoformat() != request["trade_date"]):
        raise ValueError("KOL_PREPARATION_CURRENT_PROJECTION_TIME_INVALID")
    old = viewpoint_units(read_projection(prepared["projection"]))
    new = viewpoint_units(projection)
    changed = {i for i in new.keys() & old.keys() if canonical_sha256(new[i]) != canonical_sha256(old[i])}
    added, removed = new.keys() - old.keys(), old.keys() - new.keys()
    codes = {str(r["code"]) for r in request["candidates"]}
    modes = {r["mode"] for r in request["candidates"]}
    relevant, invalidated = [], []
    for item in prepared["draft"]["implications"]:
        if set(item["viewpoint_ids"]) & (changed | removed):
            invalidated.append(item)
            continue
        scope = item["scope"]
        if scope["kind"] == "all" or set(scope["values"]) & (codes if scope["kind"] == "codes" else modes):
            relevant.append(item)
    value = {"schema_version": "kol-opening-packet.v1", "authority": 0,
        "preparation_path": str(preparation_path.resolve()), "preparation_sha256": prepared["preparation_sha256"],
        "worker_id": prepared["worker_id"], "current_input_path": str(current_input_path.resolve()),
        "current_input_sha256": _hash(current), "source_fingerprint": current["source_fingerprint"],
        "request_facts_sha256": canonical_sha256(request), "observed_at": now.isoformat(),
        "cutoff": request["review_wait_until"], "implications": relevant, "invalidated_implications": invalidated,
        "delta": {"added": sorted(added), "changed": sorted(changed), "removed": sorted(removed),
                  "units": {i: new[i] for i in sorted(added | changed)},
                  "relation_history": relation_history(projection)
                           if changed or added or removed else {}},
        "coverage": {"prepared_count": len(old), "current_count": len(new),
                     "unchanged_count": len((new.keys() & old.keys()) - changed)},
        "instruction": "Review relevant implications, all delta and fresh original request facts. Reuse unchanged preparation; verify exact cited sources and independently review final policy before cutoff. This packet grants no policy or execution authority."}
    return {**value, "packet_sha256": canonical_sha256(value)}
