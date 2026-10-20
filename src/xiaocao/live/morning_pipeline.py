"""Read-only rendezvous of the three morning owners and their actual receipts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from xiaocao.utils.trading_session import A_SHARE_TZ
from xiaocao.utils.atomic_files import atomic_write


def _evidence(path: Path):
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("invalid evidence structure")
        return value, {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError):
        return None, {"path": str(path.resolve()), "status": "missing_or_invalid"}


def pipeline_status(live_dir: Path, date: str) -> dict:
    now = datetime.now(A_SHARE_TZ)
    result = {"market_date": date, "observed_at": now.isoformat(),
        "support_cutoff": f"{date}T09:27:00+08:00", "owners": [], "app": [],
        "meaning": "observations_only_producer_ready_is_not_consumer_success"}
    for path in sorted((live_dir / "auto/runs").glob("*/manifest.json")):
        manifest, ref = _evidence(path)
        if not manifest or manifest.get("market_date") != date or manifest.get("automation_id") not in {
                "xiaocao-daily-morning", "xiaocao-daily-morning-execution"}:
            continue
        if manifest.get("run_id") != path.parent.name or not manifest.get("thread_id"):
            continue
        terminal, terminal_ref = _evidence(path.parent / "terminal.json")
        bound = bool(terminal and terminal.get("run_id") == manifest["run_id"]
            and terminal.get("market_date") == date)
        result["owners"].append({"automation_id": manifest["automation_id"],
            "thread_id": manifest["thread_id"], "run_id": manifest["run_id"], "manifest": ref,
            "status": terminal.get("deterministic_status", "unproved") if bound else "terminal_unproved",
            "receipt": terminal_ref})
    for path in sorted((live_dir / "book_b_live_execution/runs/checklists").glob("*.json")):
        checklist, ref = _evidence(path)
        binding = (checklist or {}).get("binding")
        binding = binding if isinstance(binding, dict) else {}
        if binding.get("trade_date") != date or binding.get("automation_id") != "xiaocao-book-b-live-morning":
            continue
        if (not isinstance(binding.get("owner_thread_id"), str) or not binding["owner_thread_id"]
                or type(binding.get("runner_pid")) is not int or binding["runner_pid"] <= 0):
            continue
        deadline = binding.get("preparation_deadline")
        try:
            parsed = datetime.fromisoformat(deadline)
            remaining = (parsed - now).total_seconds() if parsed.tzinfo else None
        except (ValueError, TypeError):
            remaining = None
        result["app"].append({"automation_id": binding["automation_id"],
            "thread_id": binding.get("owner_thread_id"), "runner_pid": binding.get("runner_pid"),
            "preparation_deadline": deadline, "remaining_seconds": remaining, "checklist": ref,
            "terminal_receipts": []})
    for path in sorted((live_dir / "book_b_live_execution/runs/history").glob(date + "-*.json")):
        receipt, ref = _evidence(path)
        identity = (receipt or {}).get("runner_identity")
        identity = identity if isinstance(identity, dict) else {}
        if (not receipt or receipt.get("trade_date") != date
                or receipt.get("run_id") != path.stem
                or identity.get("automation_id") != "xiaocao-book-b-live-morning"):
            continue
        if (not isinstance(identity.get("owner_thread_id"), str) or not identity["owner_thread_id"]
                or type(identity.get("runner_pid")) is not int or identity["runner_pid"] <= 0):
            continue
        for app in result["app"]:
            if identity.get("owner_thread_id") == app["thread_id"] and identity.get("runner_pid") == app["runner_pid"]:
                app["terminal_receipts"].append({"status": receipt.get("status"),
                    "reason": receipt.get("reason"), "run_id": receipt.get("run_id"), "evidence": ref})
    from xiaocao.live.morning_bundle import inspect_bundle
    bundle = inspect_bundle(live_dir, date)
    result["bundle"] = {"evidence": _evidence(live_dir / f"morning_bundle_ready_{date}.json")[1],
        "status": bundle["status"], "checkpoint_sha256": bundle.get("checkpoint_sha256"),
        "producer": bundle.get("producer")}
    for key, name, date_field in [("producer_inputs", f"recommend_source_readiness_{date}.json", "trade_date"),
            ("paper_b_freeze", f"morning_consumers/paper-{date}.json", "market_date"),
            ("paper_t_control", f"book_t_v1_control_receipt_{date}.json", "as_of"),
            ("paper_t_shadow", f"book_t_v2_shadow_producer_{date}.json", "as_of")]:
        value, ref = _evidence(live_dir / name)
        dated = bool(value and value.get(date_field) == date)
        status = "dated_evidence_observed" if dated else "unproved"
        if key == "paper_b_freeze":
            status = "ready" if (dated and bundle["status"] == "ready" and
                value.get("checkpoint_sha256") == bundle["checkpoint_sha256"] and
                value.get("snapshot_sha256") == bundle["snapshot_sha256"]) else "unproved"
        if key == "paper_t_control" and dated:
            from xiaocao.kol.publication import canonical_sha256
            unsigned = dict(value)
            claimed = unsigned.pop("receipt_sha256", None)
            identity = value.get("writer_identity") or {}
            owner = isinstance(identity, dict) and any(
                identity.get("run_id") == row["run_id"] and identity.get("thread_id") == row["thread_id"]
                and identity.get("automation_id") == row["automation_id"] for row in result["owners"])
            status = "dated_control_receipt_observed" if claimed == canonical_sha256(unsigned) and owner else "unproved"
        result[key] = {"evidence": ref, "status": status,
            "recorded_status": value.get("status") if dated else None,
            "checkpoint_sha256": value.get("checkpoint_sha256") if status == "ready" else None,
            "dependency": value.get("dependency") if key == "producer_inputs" and dated else None}
    # A freeze-acquisition receipt is preparation, not the paper writer result.
    from xiaocao.live.paper_decision_support import read_consumption_result
    try:
        terminal = read_consumption_result(live_dir.parent.parent, date, "mode_exec_star")
        result["paper_b_result"] = {"status": terminal["status"] if terminal and terminal.get("date") == date else "unproved",
            "receipt_sha256": terminal.get("receipt_sha256") if terminal else None}
    except (OSError, ValueError, TypeError, KeyError):
        result["paper_b_result"] = {"status": "unproved"}
    result["support_remaining_seconds"] = max(0, (datetime.fromisoformat(result["support_cutoff"]) - now).total_seconds())
    return result


def save_pipeline_status(live_dir: Path, date: str) -> dict:
    path = live_dir / f"morning_pipeline_{date}.json"
    try:
        atomic_write(path, json.dumps(pipeline_status(live_dir, date), ensure_ascii=False,
            sort_keys=True, indent=2).encode())
        return {"status": "observed_only", "path": str(path)}
    except (OSError, ValueError, TypeError) as exc:
        # Derived diagnostics can never veto capture or a committed bundle.
        return {"status": "degraded", "path": None, "reason": type(exc).__name__}
