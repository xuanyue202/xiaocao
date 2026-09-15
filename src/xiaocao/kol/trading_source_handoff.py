"""Durable, per-publication source-review rendezvous; zero trading authority.

The daily runner calls this after reader effects and before advancing to another
object. A retry resumes only this handoff, never publication, notification or Book.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .publication import canonical_sha256
from .trading_preparation import preparation_status


def _read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("source_handoff_regular_file_required")
    return json.loads(path.read_text())


def _immutable(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            if _read(path) != value:
                raise ValueError("source_handoff_immutable_conflict")
    finally:
        Path(name).unlink(missing_ok=True)


def pending_source_handoffs(root: Path) -> list[str]:
    directory = root / "output/live/kol_policy/handoffs"
    keys = []
    for path in sorted(directory.glob("*.request.json")):
        identifier = path.name.removesuffix(".request.json")
        if (directory / f"{identifier}.receipt.json").exists():
            continue
        request = _read(path)
        binding = {k: request[k] for k in ("publication_key", "report_id", "report_content_sha256", "manifest_sha256")}
        if request.get("request_id") != identifier or canonical_sha256(binding) != identifier:
            raise ValueError("source_handoff_request_mismatch")
        keys.append(request["publication_key"])
    return keys


def complete_source_handoff(
    root: Path, state: dict, *, build_context: Callable[..., dict],
    summarize_context: Callable[..., dict], read_response: Callable[[dict], dict],
) -> dict:
    if state.get("completed") is not True or not state.get("publish_receipt"):
        raise ValueError("source_handoff_publication_receipt_required")
    artifact = state["artifact"]
    report = next(r for r in artifact["records"] if r["kind"] == "report")
    binding = {
        "publication_key": state["publication_key"], "report_id": report["record_id"],
        "report_content_sha256": report["content_sha256"],
        "manifest_sha256": artifact["publish_request"]["manifest_sha256"],
    }
    identifier = canonical_sha256(binding)
    directory = root / "output/live/kol_policy/handoffs"
    request_path = directory / f"{identifier}.request.json"
    receipt_path = directory / f"{identifier}.receipt.json"
    request = {"event": "daily_trading_source_preparation_input_required",
               "schema_version": 1, "authority": 0, "request_id": identifier, **binding}
    if request_path.exists():
        saved = _read(request_path)
        if any(saved.get(k) != v for k, v in request.items()):
            raise ValueError("source_handoff_request_mismatch")
        request = saved
    else:
        request["requested_at"] = datetime.now(timezone.utc).isoformat()
        _immutable(request_path, request)

    def verify(context_path: Path, preparation_path: Path) -> dict:
        context = _read(context_path)
        if canonical_sha256({k: v for k, v in context.items() if k != "context_sha256"}) != context["context_sha256"]:
            raise ValueError("source_handoff_context_hash_mismatch")
        selected = next((r for r in context["reports"] if r["report_id"] == binding["report_id"]), None)
        if (not selected or selected["content_sha256"] != binding["report_content_sha256"]
                or selected["manifest_sha256"] != binding["manifest_sha256"]):
            raise ValueError("source_handoff_publication_mismatch")
        status = preparation_status(root, context)
        # Verify the supplied immutable packet, not just any matching filename.
        packet = _read(preparation_path)
        if (preparation_path.parent.resolve() != (root / "output/live/kol_policy/preparations").resolve()
                or packet.get("authority") != 0
                or packet.get("packet_sha256") != canonical_sha256({k: v for k, v in packet.items() if k != "packet_sha256"})
                or packet.get("source_fingerprint") != status["source_fingerprint"]
                or packet.get("context_sha256") != context["context_sha256"]):
            raise ValueError("source_handoff_preparation_mismatch")
        return {"status": "prepared", "authority": 0, "request_id": identifier,
                "context_path": str(context_path.resolve()), "context_sha256": context["context_sha256"],
                "preparation_path": str(preparation_path.resolve()), "packet_sha256": packet["packet_sha256"],
                "requested_at": request["requested_at"],
                "registered_longitudinal_complete": context["coverage"].get("registered_longitudinal_complete", False)}

    if receipt_path.exists():
        receipt = _read(receipt_path)
        verified = verify(Path(receipt["context_path"]), Path(receipt["preparation_path"]))
        if verified != {k: v for k, v in receipt.items() if k != "completed_at"}:
            raise ValueError("source_handoff_receipt_mismatch")
        return receipt

    context = build_context(repo_root=root, report_ids=[binding["report_id"]],
                            read_report_ids=[binding["report_id"]], refresh=True)
    summary = summarize_context(context, repo_root=root)
    status = preparation_status(root, context)
    response = None
    if status["status"] == "prepared":
        packet_path = Path(status["path"])
        prepared = _read(packet_path)
        prior_context = root / "output/live/kol_policy/context" / (prepared["context_sha256"] + ".context.json")
        if prior_context.is_file():
            response = {"context_path": str(prior_context), "preparation_path": str(packet_path)}
    # Reuse the reviewed context/packet pair when identities match; never forge
    # a new review by rebinding old notes to the current context timestamp.
    if response is None:
        response = read_response({**request, "request_path": str(request_path),
                                  "context": summary, "preparation": status})
    if not isinstance(response, dict) or not response.get("context_path") or not response.get("preparation_path"):
        raise ValueError("source_handoff_response_required")
    receipt = verify(Path(response["context_path"]), Path(response["preparation_path"]))
    receipt["completed_at"] = datetime.now(timezone.utc).isoformat()
    _immutable(receipt_path, receipt)
    return receipt
