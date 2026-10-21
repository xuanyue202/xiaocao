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
_NATIVE = re.compile(r"\bwechat\.")
_WECHAT_BINDING = re.compile(
    r"cua\.getApp\(\s*(['\"])(?:com\.tencent\.(?:xinWeChat|flue\.WeChatAppEx)"
    r"|/Applications/WeChat\.app(?:/Contents/MacOS/WeChatAppEx\.app)?)\1\s*\)"
)
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


def _atomic_events(text: str, *, binding: dict, requested_at: str, completed_at: str) -> tuple[list[dict], bool]:
    """Attach real subevents to their enclosing tool call, never invented calls."""
    rows = []
    allowed = {"schema_version", "event", "stage", "at", "identity", "capture_job_id",
               "ax_sha256", "image_sha256", "target_sha256", "proof_sha256", "reason",
               "status", "elapsed_ms", "media_accepted", "reported_error_code"}
    kinds = {"observation_requested", "observation_received", "observation_failed", "dispatch_requested",
             "dispatch_returned", "dispatch_unknown", "checkpoint_requested",
             "checkpoint_verified", "state_rejected", "completed", "stopped"}
    reasons = {"security_relogin", "authentication_required", "consent_required", "empty_window_disabled_chat",
               "wrong_native_app", "invalid_ocr_frame", "target_not_unique",
               "target_recognition_uncertain", "invalid_target_geometry",
               "bridge_not_current", "unexpected_existing_confirmation",
               "confirmation_geometry_mismatch", "missing_current_frame",
               "invalid_frame", "native_input_uncertain", "pac_checkpoint_failed",
               "brand_opened_without_allow", "brand_not_observed", "execution_error", "target_not_ready",
               "wrong_confirmation_brand", "render_not_ready", "native_bridge_policy_denied", "native_readback_unavailable"}
    try:
        # nodeRepl.write can concatenate blocks without line breaks.
        for marker in re.finditer(r"KOL_ATOMIC_EVENT ", text):
            row, _ = json.JSONDecoder().raw_decode(text[marker.end():].lstrip())
            if (not isinstance(row, dict) or set(row) - allowed
                or row.get("schema_version") != 1 or row.get("event") not in kinds
                or row.get("stage") not in {"B0", "B1", "PAC", "B2"}
                or any(row.get(k) != binding.get(k) for k in ("identity", "capture_job_id"))
                or not _time(requested_at) <= _time(row["at"]) <= _time(completed_at)
                or (rows and _time(row["at"]) < _time(rows[-1]["at"]))):
                return [], False
            for key, value in row.items():
                if key.endswith("_sha256") and not re.fullmatch(r"[a-f0-9]{64}", str(value)):
                    return [], False
                if key in {"reason", "reported_error_code", "status"} and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", str(value)):
                    return [], False
            if (row.get("reason", "execution_error") not in reasons
                or row.get("status", "stopped") not in {"stopped", "brand_ready"}
                or row.get("reported_error_code", "unclassified_input_error") not in {
                    "timeoutReached", "noWindowsAvailable", "windowNotFoundAtPosition", "unclassified_input_error",
                    "policy_denied", "app_target_changed", "observation_error"}
                or ("elapsed_ms" in row and (type(row["elapsed_ms"]) is not int or row["elapsed_ms"] < 0))
                or row.get("media_accepted", False) is not False):
                return [], False
            rows.append(row)
    except (ValueError, TypeError, KeyError):
        return [], False
    sequence = [("B0", "observation_requested"), ("B0", "observation_received"),
                ("B0", "observation_requested"), ("B0", "observation_received"),
                ("B1", "dispatch_requested"), ("B1", "dispatch_returned"),
                ("B1", "observation_requested"), ("B1", "observation_received"),
                ("PAC", "checkpoint_requested"), ("PAC", "checkpoint_verified"),
                ("B2", "observation_requested"), ("B2", "observation_received"),
                ("B2", "dispatch_requested"), ("B2", "dispatch_returned"),
                ("B2", "observation_requested"), ("B2", "observation_received")]
    position = 0
    rejected = False
    uncertain = False
    pending = False
    for index, row in enumerate(rows):
        event = row["event"]
        if event in {"completed", "stopped"}:
            terminal = (index == len(rows) - 1 and position > 0 and not pending
                and rows[index-1]["event"] not in {"dispatch_returned", "dispatch_unknown"})
            complete = terminal and (event == "stopped" or
                (position == len(sequence) and not rejected and not uncertain and row.get("status") == "brand_ready"))
            return rows, complete
        if rejected:
            return rows, False
        if event == "state_rejected":
            if index == 0 or rows[index-1]["event"] != "observation_received" or row["stage"] != rows[index-1]["stage"]:
                return rows, False
            rejected = True
            continue
        if (event == "observation_requested" and index > 0 and rows[index-1]["event"] == "observation_received"
            and rows[index-1]["stage"] == row["stage"] and not uncertain
            and ((row["stage"] == "B1" and position < len(sequence) and sequence[position] == ("PAC", "checkpoint_requested"))
                 or (row["stage"] == "B2" and position == len(sequence)))):
            sequence[position:position] = [(row["stage"], "observation_requested"), (row["stage"], "observation_received")]
        if position >= len(sequence):
            return rows, False
        expected_stage, expected_event = sequence[position]
        if event == "observation_failed" and expected_event == "observation_received" and row["stage"] == expected_stage:
            if not row.get("reported_error_code"):
                return rows, False
            sequence[position] = (expected_stage, "observation_failed")
            if expected_stage == "B2" and row["reported_error_code"] != "policy_denied" and any(r["stage"] == "B2" and r["event"] == "dispatch_returned" for r in rows[:index]):
                sequence[position+1:position+1] = [(expected_stage, "observation_requested"), (expected_stage, "observation_received")]
            expected_event = "observation_failed"
        if event == "dispatch_unknown" and expected_event == "dispatch_returned" and row["stage"] == expected_stage:
            uncertain = True
            # An uncertain input gets one passive readback, then must stop.
            sequence = sequence[:position] + [(expected_stage, "dispatch_unknown"),
                (expected_stage, "observation_requested"), (expected_stage, "observation_received")]
            expected_event = "dispatch_unknown"
        if (row["stage"], event) != (expected_stage, expected_event):
            return rows, False
        if event == "observation_received" and not all(row.get(k) for k in ("ax_sha256", "image_sha256")):
            return rows, False
        if event == "dispatch_requested" and not row.get("target_sha256"):
            return rows, False
        if event == "checkpoint_verified" and not row.get("proof_sha256"):
            return rows, False
        pending = event.endswith("_requested")
        position += 1
    complete = False
    return rows, complete


def _output_signals(output: object, *, native_observation: bool,
                    atomic_context: dict | None = None) -> dict:
    blocks = output if isinstance(output, list) else []
    texts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") in {"input_text", "text"}]
    if isinstance(output, str):
        texts.append(output)
    text = "\n".join(texts)
    atomic, atomic_complete = _atomic_events(text, **atomic_context) if atomic_context else ([], True)
    images = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "input_image":
            continue
        url = block.get("image_url", "")
        if isinstance(url, str) and url.startswith("data:image/") and ";base64," in url:
            images.append(_sha(base64.b64decode(url.split(";base64,", 1)[1], validate=True)))
    # Readiness/checkpoint payloads include instructions and error-code schemas.
    # Retain their hashes, but they are not observations of the WeChat window.
    security = native_observation and ("为了你的账号安全，请重新登录" in text or
        any(r.get("event") == "state_rejected" and r.get("reason") == "security_relogin" for r in atomic))
    abnormal = bool(native_observation and ((re.search(r'Window:\s*""', text) and
                    re.search(r"\(disabled\).*聊天", text)) or any(
                    r.get("event") == "state_rejected" and r.get("reason") == "empty_window_disabled_chat" for r in atomic)))
    if security:
        state = "security_relogin"
    elif abnormal:
        state = "empty_window_disabled_chat"
    elif native_observation and re.search(r'Window:\s*"草料二维码"', text):
        state = "bridge_observed"
    elif native_observation and re.search(r'Window:\s*"见势擒龙团"', text):
        state = "brand_window_observed"
    else:
        state = "unclassified"
    error_code = next((code for code in (
        "noWindowsAvailable", "windowNotFoundAtPosition", "AXError.notImplemented",
    ) if native_observation and code in text), None)
    if native_observation and error_code is None:
        if re.search(r"Computer Use server error[^\n]*\bis an invalid element ID\b", text):
            error_code = "invalid_element_id"
        elif ("The user changed '" in text and
              "Re-query the latest state" in text):
            error_code = "app_target_changed"
        elif re.search(r"js execution timed out; kernel reset, rerun your request", text):
            error_code = "cua_execution_timeout_kernel_reset"
        elif re.search(r"Computer Use server error[^\n]*:\s*timeoutReached\b", text):
            error_code = "timeoutReached"
    if error_code is None:
        error_code = next((r["reported_error_code"] for r in atomic if r.get("reported_error_code")), None)
    return {"state": state, "text_sha256": _sha(text.encode()),
            "reported_error_code": error_code,
            "image_sha256": images,
            "output_sha256": _sha(json.dumps(output, ensure_ascii=False,
                                              sort_keys=True).encode()),
            **({"atomic_events": atomic, "atomic_evidence_complete": atomic_complete} if atomic_context else {})}


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
            atomic_call = bool(marker and marker.group(1) == "OPEN_ALLOW_ATOMIC" and
                               re.search(r"\brunAtomicCourseAllow\s*\(", code))
            binding_call = bool(_WECHAT_BINDING.search(code))
            native = payload.get("namespace") == "mcp__cua_repl" and (
                bool(_NATIVE.search(code)) or binding_call or atomic_call
            )
            if not native and not marker:
                continue
            if not call_id or call_id in calls:
                raise ValueError("duplicate or missing selected call ID")
            calls[call_id] = {
                "call_id": call_id, "step": marker.group(1) if marker else "LEGACY_NATIVE",
                "kind": "native_atomic" if native and atomic_call
                        else "native_input" if native and _INPUT.search(code)
                        else "native_binding" if native and binding_call
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
                         **_output_signals(payload.get("output"),
                                           native_observation=call["kind"] != "checkpoint",
                                           atomic_context={"binding": binding,
                                               "requested_at": call["requested_at"],
                                               "completed_at": _local_time(timestamp)}
                                           if call["kind"] == "native_atomic" else None)})
    ordered = list(calls.values())
    observations = sorted((c for c in ordered if c.get("completed_at")),
                          key=lambda c: _time(c["completed_at"]))
    abnormal = next((c for c in observations if c.get("state") in {
        "empty_window_disabled_chat", "security_relogin",
    }), None)
    security = next((c for c in observations if c.get("state") == "security_relogin"), None)
    tool_error = next((c for c in observations if c.get("reported_error_code")), None)
    event_times = [_time(e["timestamp"]) for e in events if e.get("timestamp")]
    last_event = max(event_times, default=None)
    pending = [c["call_id"] for c in ordered if c["completion"] == "pending"]
    limitations = []
    if last_event is None or last_event < boundary:
        limitations.append("source_before_run")
    if not ordered:
        limitations.append("no_selected_calls")
    if incomplete_tail:
        limitations.append("incomplete_final_line")
    if pending:
        limitations.append("pending_tool_outputs")
    if any(c.get("atomic_evidence_complete") is False for c in ordered):
        limitations.append("incomplete_atomic_evidence")
    coverage = {
        "status": "evidence_incomplete" if limitations else "selected_calls_recorded",
        "source_last_event_at": last_event.astimezone(_SHANGHAI).isoformat() if last_event else None,
        "limitations": limitations,
        "meaning": "Only recorded selected calls are covered; empty findings do not prove absence of errors or protection.",
    }
    prior = [c["call_id"] for c in ordered if c["kind"] != "native_observation" and
             (abnormal is None or _time(c["requested_at"]) <= _time(abnormal["completed_at"]))]
    return {
        "schema_version": 1, "thread_id": thread_id, "binding": binding,
        "not_before": _local_time(not_before), "source_sha256": _sha(source),
        "source_bytes": len(source), "incomplete_final_line": incomplete_tail,
        "coverage": coverage,
        "calls": ordered, "findings": {
            "first_abnormal_call_id": abnormal["call_id"] if abnormal else None,
            "first_security_text_call_id": security["call_id"] if security else None,
            "first_tool_error_call_id": tool_error["call_id"] if tool_error else None,
            "preceding_effect_call_ids": prior,
            "pending_call_ids": pending,
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
                 "source_sha256": result["source_sha256"], "coverage": result["coverage"],
                 "findings": result["findings"]})
    return {"snapshot": str(snapshot.resolve()), "call_count": len(result["calls"]),
            "coverage": result["coverage"],
            **result["findings"]}


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
