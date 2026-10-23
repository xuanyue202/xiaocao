"""Cache-only opening inputs, with full coverage and no decision authority."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from xiaocao.kol.trading_context import build_trading_context, write_trading_projection
from xiaocao.runner_recovery import _hash, _write
from .morning_checklist import MorningChecklist


def prepare_inputs(checklist: MorningChecklist, *, repo_root: Path) -> dict:
    summary = write_trading_projection(build_trading_context(
        read_report_ids=[], include_report_bodies=False, repo_root=repo_root,
        history_fresh_through=checklist.binding["trade_date"] + "T11:30:00+08:00"),
        repo_root=repo_root)
    from xiaocao.kol.opening_preparation import input_payload
    payload = input_payload(summary, binding=checklist.binding, repo_root=repo_root)
    projection_path = Path(summary["projection_path"])
    path = checklist.path.with_name(_hash(payload) + ".kol-inputs.json")
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text()) != payload:
            raise ValueError("MORNING_KOL_INPUT_IMMUTABILITY_VIOLATION")
    else:
        _write(path, payload)
    evidence = {"input_path": str(path), "input_sha256": _hash(payload),
                "projection_path": str(projection_path), "projection_sha256": summary["projection_sha256"],
                "source_fingerprint": payload["source_fingerprint"], "counts": summary.get("counts"),
                "quality": payload["quality"], "viewpoint_ids_sha256": _hash(payload["viewpoint_ids"]), "rules_sha256": _hash(payload["rules"])}
    checklist.record("kol_projection", "passed" if payload["quality"] == "ready" else "degraded",
                     evidence=evidence, reason=None if payload["quality"] == "ready" else "SOURCE_COVERAGE_DEGRADED")
    return evidence


def acknowledge_inputs(checklist: MorningChecklist, input_path: Path, *, worker_id: str,
                       loaded_ids: list[str], loaded_receipt_path: Path) -> dict:
    payload = json.loads(input_path.read_text())
    current = checklist.read()["items"]["kol_projection"]["evidence"] or {}
    if (not worker_id.strip() or payload.get("binding") != checklist.binding
            or current.get("input_path") != str(input_path.resolve())
            or current.get("input_sha256") != _hash(payload)
            or len(loaded_ids) != len(set(loaded_ids))
            or set(loaded_ids) != set(payload["viewpoint_ids"])):
        raise ValueError("MORNING_KOL_INPUT_COVERAGE_MISMATCH")
    loaded = json.loads(loaded_receipt_path.read_text())
    dispatch_path = Path(loaded["dispatch_path"])
    dispatch = json.loads(dispatch_path.read_text())
    arguments = dispatch.get("tool_arguments") or {}
    result = dispatch.get("tool_result") or {}
    dispatched = datetime.fromisoformat(dispatch["dispatched_at"])
    deadline = datetime.fromisoformat(checklist.binding["trade_date"] + "T09:20:00+08:00")
    if (loaded.get("worker_id") != worker_id or loaded.get("loaded_viewpoint_ids") != loaded_ids
            or dispatch.get("worker_id") != worker_id or dispatch.get("accepted") is not True
            or dispatch.get("model") != "gpt-6-sol" or dispatch.get("reasoning_effort") != "xhigh"
            or arguments.get("model") != "gpt-6-sol" or arguments.get("reasoning_effort") != "xhigh"
            or arguments.get("fork_turns") != "none" or result.get("task_name") != worker_id
            or dispatch.get("binding") != checklist.binding or dispatched.utcoffset() is None
            or dispatched.date().isoformat() != checklist.binding["trade_date"]
            or dispatch.get("input_sha256") != _hash(payload)):
        raise ValueError("MORNING_KOL_DISPATCH_ROUTE_UNPROVEN")
    evidence = {"worker_id": worker_id, "dispatch_path": str(dispatch_path.resolve()),
                "dispatch_sha256": _hash(dispatch), "loaded_receipt_path": str(loaded_receipt_path.resolve()),
                "loaded_receipt_sha256": _hash(loaded), "dispatched_at": dispatched.isoformat(), "source_fingerprint": payload["source_fingerprint"],
                "input_path": str(input_path.resolve()), "input_sha256": _hash(payload),
                "loaded_count": len(loaded_ids), "viewpoint_ids_sha256": _hash(payload["viewpoint_ids"]),
                "rules_sha256": _hash(payload["rules"]), "authority": 0}
    from xiaocao.kol.opening_preparation import read_preparation
    preparation_path = Path(loaded["preparation_path"])
    prepared = read_preparation(preparation_path, now=datetime.now(deadline.tzinfo))
    if (prepared["input_sha256"] != _hash(payload) or prepared["worker_id"] != worker_id
            or prepared["dispatch"] != dispatch):
        raise ValueError("MORNING_KOL_PREPARATION_BINDING_MISMATCH")
    evidence.update(preparation_path=str(preparation_path.resolve()),
                    preparation_sha256=prepared["preparation_sha256"],
                    preparation_accepted_at=prepared["accepted_at"])
    late = dispatched >= deadline or datetime.now(deadline.tzinfo) >= deadline
    checklist.record("kol_inputs_loaded", "degraded" if late else "passed",
                     evidence=evidence, reason="INPUT_LOADING_LATE" if late else None)
    return evidence
