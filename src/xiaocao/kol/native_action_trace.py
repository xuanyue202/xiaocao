"""Export credential-free evidence from an exact, local Codex tool journal.

The journal records dispatch requests before tool execution. Completion timestamps
bound observations; neither a tool return nor temporal proximity proves causality.
This module performs no UI, network or capture operations.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo


_STEP = re.compile(r"(?m)^\s*//\s*KOL_ACTION:([A-Z][A-Z0-9_]{0,63})\s*$")
_INPUT = re.compile(r"\bwechat\.(click|typeText|performSecondaryAction)\s*\(")
_NATIVE = re.compile(r"\bwechat\.|cua\.getApp\(['\"]com\.tencent\.xinWeChat['\"]\)")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("trace timestamps must include a timezone")
    return result


def _local_time(value: str) -> str:
    return _time(value).astimezone(_SHANGHAI).isoformat()


def _output_signals(output: object) -> dict:
    blocks = output if isinstance(output, list) else []
    texts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") in {"input_text", "text"}]
    if isinstance(output, str):
        texts.append(output)
    text = "\n".join(texts)
    images = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "input_image":
            continue
        url = block.get("image_url", "")
        if isinstance(url, str) and url.startswith("data:image/") and ";base64," in url:
            images.append(_sha(base64.b64decode(url.split(";base64,", 1)[1], validate=True)))
    security = "为了你的账号安全，请重新登录" in text
    abnormal = bool(re.search(r'Window:\s*""', text) and
                    re.search(r"\(disabled\).*聊天", text))
    if security:
        state = "security_relogin"
    elif abnormal:
        state = "empty_window_disabled_chat"
    elif re.search(r'Window:\s*"草料二维码"', text):
        state = "bridge_observed"
    elif re.search(r'Window:\s*"见势擒龙团"', text):
        state = "brand_window_observed"
    else:
        state = "unclassified"
    return {"state": state, "text_sha256": _sha(text.encode()),
            "image_sha256": images,
            "output_sha256": _sha(json.dumps(output, ensure_ascii=False,
                                              sort_keys=True).encode())}


def inspect_trace(
    source: bytes, *, thread_id: str, not_before: str, binding: dict,
) -> dict:
    """Inspect complete journal lines; a partial final write remains explicit."""
    boundary = _time(not_before)
    if not binding.get("identity") or not binding.get("capture_job_id"):
        raise ValueError("original identity and capture binding required")
    lines = source.splitlines(keepends=True)
    events = []
    incomplete_tail = False
    for index, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except (ValueError, UnicodeDecodeError):
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                incomplete_tail = True
            else:
                raise ValueError("malformed complete journal line") from None
    sessions = [e.get("payload", {}).get("id") for e in events
                if e.get("type") == "session_meta"]
    if sessions != [thread_id]:
        raise ValueError("source journal session does not match exact thread")
    calls: dict[str, dict] = {}
    for event in events:
        payload = event.get("payload", {})
        kind = payload.get("type")
        if event.get("type") != "response_item" or kind not in {
            "function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output",
        }:
            continue
        timestamp = event.get("timestamp", "")
        if _time(timestamp) < boundary:
            continue
        call_id = payload.get("call_id")
        if kind in {"function_call", "custom_tool_call"}:
            raw = payload.get("arguments", payload.get("input", ""))
            try:
                arguments = json.loads(raw)
            except ValueError:
                arguments = raw
            code = arguments.get("code", "") if isinstance(arguments, dict) else arguments
            if not isinstance(code, str):
                continue
            marker = _STEP.search(code)
            native = payload.get("namespace") == "mcp__cua_repl" and bool(_NATIVE.search(code))
            if not native and not marker:
                continue
            if not call_id or call_id in calls:
                raise ValueError("duplicate or missing selected call ID")
            calls[call_id] = {
                "call_id": call_id, "step": marker.group(1) if marker else "LEGACY_NATIVE",
                "kind": "native_input" if native and _INPUT.search(code)
                        else "native_observation" if native else "checkpoint",
                "requested_at": _local_time(timestamp),
                "arguments_sha256": _sha(raw.encode()), "completion": "pending",
            }
        elif call_id in calls:
            call = calls[call_id]
            if call["completion"] != "pending":
                raise ValueError("duplicate selected tool output")
            if _time(timestamp) < _time(call["requested_at"]):
                raise ValueError("tool output predates dispatch request")
            call.update({"completion": "output_recorded",
                         "completed_at": _local_time(timestamp),
                         **_output_signals(payload.get("output"))})
    ordered = list(calls.values())
    observations = sorted((c for c in ordered if c.get("completed_at")),
                          key=lambda c: _time(c["completed_at"]))
    abnormal = next((c for c in observations if c.get("state") in {
        "empty_window_disabled_chat", "security_relogin",
    }), None)
    security = next((c for c in observations if c.get("state") == "security_relogin"), None)
    prior = [c["call_id"] for c in ordered if c["kind"] != "native_observation" and
             (abnormal is None or _time(c["requested_at"]) <= _time(abnormal["completed_at"]))]
    return {
        "schema_version": 1, "thread_id": thread_id, "binding": binding,
        "not_before": _local_time(not_before), "source_sha256": _sha(source),
        "source_bytes": len(source), "incomplete_final_line": incomplete_tail,
        "calls": ordered, "findings": {
            "first_abnormal_call_id": abnormal["call_id"] if abnormal else None,
            "first_security_text_call_id": security["call_id"] if security else None,
            "preceding_effect_call_ids": prior,
            "pending_call_ids": [c["call_id"] for c in ordered if c["completion"] == "pending"],
            "root_trigger_proven": False,
            "timing_basis": "tool request/output bounds; observation time and security decision time may differ",
        },
    }


def export_trace(
    rollout_file: Path, output_dir: Path, *, thread_id: str,
    not_before: str, identity: str, capture_job_id: str, subscription_dir: Path,
) -> dict:
    """Bind the retained item, then preserve a source-hash snapshot and pointer."""
    manifest = json.loads((subscription_dir / "manifest.json").read_text())
    item = manifest.get("items", {}).get(identity)
    if not item or item.get("capture_job_id") != capture_job_id:
        raise ValueError("original subscription/capture binding does not match")
    binding = {key: item.get(key) for key in (
        "identity", "capture_job_id", "message_sha256", "published_at",
    )}
    result = inspect_trace(rollout_file.read_bytes(), thread_id=thread_id,
                           not_before=not_before, binding=binding)
    result["source_rollout_path"] = str(rollout_file.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_hash = _sha(json.dumps(result, ensure_ascii=False, sort_keys=True).encode())
    snapshot = output_dir / f"trace-{snapshot_hash}.json"
    if not snapshot.exists():
        _atomic_json(snapshot, result)
    _atomic_json(output_dir / "latest.json", {"snapshot": snapshot.name,
                 "source_sha256": result["source_sha256"], "findings": result["findings"]})
    return {"snapshot": str(snapshot.resolve()), "call_count": len(result["calls"]),
            **result["findings"]}


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
