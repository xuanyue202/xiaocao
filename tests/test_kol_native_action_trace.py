import base64
import hashlib
import json
from pathlib import Path

import pytest

from xiaocao.kol.native_action_trace import export_trace, inspect_trace


THREAD = "exact-thread"
BINDING = {"identity": "original-subscription", "capture_job_id": "original-capture"}
BOUNDARY = "2026-10-14T23:27:00+08:00"


def event(kind, at="2026-10-14T15:27:40Z", **payload):
    return {"timestamp": at, "type": "response_item", "payload": {"type": kind, **payload}}


def call(call_id, code, **kwargs):
    return event("function_call", call_id=call_id, namespace="mcp__cua_repl",
                 name="js", arguments=json.dumps({"code": code}), **kwargs)


def output(call_id, text, **kwargs):
    return event("function_call_output", call_id=call_id,
                 output=[{"type": "input_text", "text": text}], **kwargs)


def journal(*events):
    meta = {"type": "session_meta", "payload": {"id": THREAD}}
    return b"".join((json.dumps(e, ensure_ascii=False) + "\n").encode()
                    for e in (meta, *events))


def inspect(source):
    return inspect_trace(source, thread_id=THREAD, not_before=BOUNDARY, binding=BINDING)


def test_security_discovery_does_not_assign_cancel_as_trigger():
    source = journal(
        call("allow", "await wechat.click([549,837]); await wechat.getAXStateAndScreenshot();"),
        output("allow", 'Window: "草料二维码", App: 微信.'),
        call("window", "await wechat.click(6); await wechat.getAXState();",
             at="2026-10-14T15:28:15Z"),
        output("window", 'Window: "", App: 微信.\n33 (disabled) 聊天\n38 微信',
               at="2026-10-14T15:28:16Z"),
        call("cancel", "await wechat.performSecondaryAction(1,'Cancel'); await wechat.getAXStateAndScreenshot();",
             at="2026-10-14T15:28:24Z"),
        output("cancel", 'Window: "", App: 微信.\n为了你的账号安全，请重新登录。',
               at="2026-10-14T15:28:25Z"),
    )
    result = inspect(source)
    assert result["findings"]["first_abnormal_call_id"] == "window"
    assert result["findings"]["first_security_text_call_id"] == "cancel"
    assert result["findings"]["preceding_effect_call_ids"] == ["allow", "window"]
    assert result["findings"]["root_trigger_proven"] is False
    assert result["calls"][0]["requested_at"] == "2026-10-14T23:27:40+08:00"


def test_reports_pending_dispatch_and_truncated_live_tail():
    source = journal(call("pending", "// KOL_ACTION:B2_ALLOW\nawait wechat.click([1,2]);"))
    result = inspect(source + b'{"timestamp":')
    assert result["incomplete_final_line"] is True
    assert result["findings"]["pending_call_ids"] == ["pending"]
    assert result["calls"][0]["step"] == "B2_ALLOW"
    assert "completed_at" not in result["calls"][0]
    assert result["findings"]["first_security_text_call_id"] is None
    assert result["coverage"]["status"] == "evidence_incomplete"
    assert result["coverage"]["limitations"] == ["incomplete_final_line", "pending_tool_outputs"]


def test_old_journal_does_not_report_current_run_as_clean():
    source = journal(call("old", "await wechat.getAXState();", at="2026-10-14T15:26:00Z"))
    result = inspect(source)
    assert result["calls"] == []
    assert result["coverage"]["status"] == "evidence_incomplete"
    assert result["coverage"]["source_last_event_at"] == "2026-10-14T23:26:00+08:00"
    assert result["coverage"]["limitations"] == ["source_before_run", "no_selected_calls"]


def test_fresh_unrelated_events_are_not_native_action_coverage():
    result = inspect(journal(event("message", role="assistant")))
    assert result["coverage"]["limitations"] == ["no_selected_calls"]
    recorded = inspect(journal(call("read", "await wechat.getAXState();"), output("read", "ok")))
    assert recorded["coverage"]["status"] == "selected_calls_recorded"


def test_collects_actual_freeform_environment_checkpoint_shape():
    source = journal(
        event("custom_tool_call", name="exec", call_id="pac", input=
              '// KOL_ACTION:PAC_ENABLE\ntext(await tools.exec_command({cmd:"private command"}));'),
        event("custom_tool_call_output", call_id="pac", output=[
            {"type": "input_text", "text": 'nested tool returned session_id=123'}]),
    )
    result = inspect(source)
    assert result["calls"][0]["step"] == "PAC_ENABLE"
    assert result["calls"][0]["completion"] == "output_recorded"
    assert result["findings"]["preceding_effect_call_ids"] == ["pac"]
    assert "private command" not in json.dumps(result)


def test_window_input_rejection_is_not_security_or_success():
    source = journal(
        call("input", "// KOL_ACTION:B1_COURSE_BUTTON\nawait wechat.click([414,410]);"),
        output("input", "Computer Use server error -10005: noWindowsAvailable"),
        call("readback", "await wechat.getAXStateAndScreenshot();"),
        output("readback", 'There has been no change for Window: "草料二维码".'),
    )
    result = inspect(source)
    assert result["calls"][0]["reported_error_code"] == "noWindowsAvailable"
    assert result["findings"]["first_tool_error_call_id"] == "input"
    assert result["findings"]["first_security_text_call_id"] is None
    assert result["findings"]["root_trigger_proven"] is False


def test_checkpoint_instructions_are_not_observed_native_errors_or_security():
    request = {"instructions": "If noWindowsAvailable or 为了你的账号安全，请重新登录 appears, stop inputs.",
               "required_response": {"error": "windowNotFoundAtPosition"}}
    source = journal(
        event("custom_tool_call", name="exec", call_id="ready",
              input="// KOL_ACTION:READINESS\ntext(await tools.write_stdin({session_id:123}));"),
        event("custom_tool_call_output", call_id="ready", output=json.dumps(request, ensure_ascii=False)),
        call("read", "// KOL_ACTION:B0_READBACK\nawait wechat.getAXStateAndScreenshot();"),
        output("read", 'Window: "草料二维码", App: 微信.'),
    )
    result = inspect(source)
    assert result["calls"][0]["reported_error_code"] is None
    assert result["findings"]["first_tool_error_call_id"] is None
    assert result["findings"]["first_abnormal_call_id"] is None
    assert result["findings"]["first_security_text_call_id"] is None
    assert result["calls"][1]["state"] == "bridge_observed"
    assert "noWindowsAvailable" not in json.dumps(result)


@pytest.mark.parametrize("message,expected", [
    ("Computer Use server error -10005: 9 is an invalid element ID", "invalid_element_id"),
    ("The user changed '/Applications/WeChat.app'. Re-query the latest state with "
     "`get_app_state` before sending more actions.", "app_target_changed"),
    ("js execution timed out; kernel reset, rerun your request",
     "cua_execution_timeout_kernel_reset"),
])
def test_targeting_failures_are_errors_without_inventing_security(message, expected):
    result = inspect(journal(call("input", "await wechat.click(9);"), output("input", message)))
    assert result["calls"][0]["reported_error_code"] == expected
    assert result["findings"]["first_tool_error_call_id"] == "input"
    assert result["findings"]["first_abnormal_call_id"] is None
    assert result["findings"]["first_security_text_call_id"] is None
    assert result["findings"]["root_trigger_proven"] is False
    assert message not in json.dumps(result)


def test_timeout_in_checkpoint_instructions_is_not_a_native_tool_failure():
    result = inspect(journal(
        event("custom_tool_call", name="exec", call_id="checkpoint", input=
              '// KOL_ACTION:READINESS\ntext("checkpoint");'),
        event("custom_tool_call_output", call_id="checkpoint", output=
              "If js execution timed out; kernel reset, rerun your request appears, diagnose."),
    ))
    assert result["calls"][0]["reported_error_code"] is None
    assert result["findings"]["first_tool_error_call_id"] is None


@pytest.mark.parametrize("target", [
    "com.tencent.xinWeChat",
    "com.tencent.flue.WeChatAppEx",
    "/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app",
])
def test_wechat_binding_is_a_possible_effect_and_retains_actual_timeout(target):
    result = inspect(journal(
        call("bind", f"var miniHost = await cua.getApp('{target}');"),
        output("bind", "Computer Use server error -10005: timeoutReached"),
    ))
    assert result["calls"][0]["kind"] == "native_binding"
    assert result["calls"][0]["reported_error_code"] == "timeoutReached"
    assert result["findings"]["first_tool_error_call_id"] == "bind"
    assert result["findings"]["preceding_effect_call_ids"] == ["bind"]
    assert result["findings"]["root_trigger_proven"] is False


def test_binding_target_or_timeout_in_a_checkpoint_is_not_native_evidence():
    result = inspect(journal(
        event("custom_tool_call", name="exec", call_id="checkpoint", input=
              "// KOL_ACTION:READINESS\ntext(\"cua.getApp('com.tencent.flue.WeChatAppEx')\");"),
        event("custom_tool_call_output", call_id="checkpoint", output=
              "Computer Use server error -10005: timeoutReached"),
    ))
    assert result["calls"][0]["kind"] == "checkpoint"
    assert result["findings"]["first_tool_error_call_id"] is None


def test_unrelated_application_binding_is_not_wechat_evidence():
    result = inspect(journal(
        call("other", "await cua.getApp('Microsoft Edge');"),
        output("other", "Computer Use server error -10005: timeoutReached"),
    ))
    assert result["calls"] == []


def atomic_row(kind, **fields):
    return "KOL_ATOMIC_EVENT " + json.dumps({"schema_version": 1, "event": kind,
        "stage": "B1", "at": "2026-10-14T15:27:40Z", **BINDING, **fields})


def atomic_prefix():
    return [atomic_row("observation_requested", stage="B0"),
        atomic_row("observation_received", stage="B0", ax_sha256="a"*64, image_sha256="b"*64)]


def atomic_success():
    rows = atomic_prefix() * 2
    for stage, kinds in [("B1", ["dispatch_requested", "dispatch_returned", "observation_requested", "observation_received"]),
                         ("PAC", ["checkpoint_requested", "checkpoint_verified"]),
                         ("B2", ["observation_requested", "observation_received", "dispatch_requested", "dispatch_returned", "observation_requested", "observation_received"])]:
        for kind in kinds:
            hashes = {"observation_received": {"ax_sha256": "a"*64, "image_sha256": "b"*64},
                "dispatch_requested": {"target_sha256": "c"*64}, "checkpoint_verified": {"proof_sha256": "d"*64}}.get(kind, {})
            rows.append(atomic_row(kind, stage=stage, **hashes))
    return rows + [atomic_row("completed", stage="B2", status="brand_ready")]


def test_atomic_subevents_keep_the_real_enclosing_call_and_hashes():
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(atomic_success())),
    ))
    assert result["calls"][0]["kind"] == "native_atomic"
    assert len(result["calls"][0]["atomic_events"]) == 17
    assert result["calls"][0]["call_id"] == "atomic"
    assert result["coverage"]["status"] == "selected_calls_recorded"


def test_partial_atomic_tail_remains_incomplete_even_if_outer_tool_returned():
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", atomic_row("dispatch_requested", target_sha256="a"*64)),
    ))
    assert result["coverage"]["status"] == "evidence_incomplete"
    assert "incomplete_atomic_evidence" in result["coverage"]["limitations"]


def test_atomic_security_readback_does_not_invent_a_trigger():
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(atomic_prefix() + [atomic_row("state_rejected", stage="B0", reason="security_relogin"),
            atomic_row("stopped", stage="B0", status="stopped", reason="security_relogin")])),
    ))
    assert result["findings"]["first_security_text_call_id"] == "atomic"
    assert result["findings"]["root_trigger_proven"] is False


@pytest.mark.parametrize("fields", [{"identity": "different"}, {"raw_text": "private"}])
def test_rejects_rebound_or_unredacted_atomic_evidence(fields):
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", atomic_row("completed", status="brand_ready", **fields)),
    ))
    assert result["calls"][0]["atomic_events"] == []
    assert result["coverage"]["status"] == "evidence_incomplete"


def test_hashes_images_and_sensitive_payloads_without_exporting_them():
    frame = b"private screen bytes"
    result_event = output("input", 'Window: "草料二维码"; personal chat text')
    result_event["payload"]["output"].append({"type": "input_image", "image_url":
        "data:image/jpeg;base64," + base64.b64encode(frame).decode()})
    source = journal(call("input", 'await wechat.typeText("secret-password");'), result_event,
        event("function_call", namespace="functions", name="exec", call_id="launch",
              arguments='// KOL_ACTION:PROVIDER_LAUNCH\nopen("weixin://dl/business/?t=secret-ticket")'))
    result = inspect(source)
    rendered = json.dumps(result)
    for secret in ("secret-password", "secret-ticket", "personal chat text", base64.b64encode(frame).decode()):
        assert secret not in rendered
    assert result["calls"][0]["image_sha256"] == [hashlib.sha256(frame).hexdigest()]
    assert result["calls"][1]["step"] == "PROVIDER_LAUNCH"


@pytest.mark.parametrize("source", [
    journal() + b'not json\n',
    journal(call("same", "await wechat.getAXState();"), call("same", "await wechat.getAXState();")),
    journal(call("a", "await wechat.getAXState();"), output("a", "ok"), output("a", "ok")),
])
def test_rejects_ambiguous_or_corrupt_complete_evidence(source):
    with pytest.raises(ValueError):
        inspect(source)


def test_rejects_wrong_thread_and_naive_run_clock():
    with pytest.raises(ValueError, match="exact thread"):
        inspect_trace(journal(), thread_id="other", not_before=BOUNDARY, binding=BINDING)
    with pytest.raises(ValueError, match="timezone"):
        inspect_trace(journal(), thread_id=THREAD, not_before="2026-10-14T23:27:00", binding=BINDING)


def test_finds_earliest_observation_by_completion_with_parallel_calls():
    source = journal(
        call("slow", "await wechat.getAXState();"),
        call("fast", "await wechat.getAXState();", at="2026-10-14T15:27:41Z"),
        output("fast", "为了你的账号安全，请重新登录", at="2026-10-14T15:27:42Z"),
        output("slow", 'Window: ""\n33 (disabled) 聊天', at="2026-10-14T15:27:43Z"),
    )
    assert inspect(source)["findings"]["first_abnormal_call_id"] == "fast"


def test_export_preserves_snapshot_and_rejects_rebound_capture(tmp_path):
    subscriptions = tmp_path / "subscriptions"
    subscriptions.mkdir()
    manifest = subscriptions / "manifest.json"
    manifest.write_text(json.dumps({"items": {BINDING["identity"]: BINDING}}))
    source = tmp_path / "source.jsonl"
    source.write_bytes(journal(call("a", "await wechat.getAXState();")))
    def export(boundary=BOUNDARY, capture="original-capture"):
        return export_trace(source, tmp_path / "evidence", thread_id=THREAD,
            not_before=boundary, identity="original-subscription", capture_job_id=capture,
            subscription_dir=subscriptions)
    first = export()
    saved = Path(first["snapshot"]).read_bytes()
    # A different run boundary must never silently reuse another run's report.
    second = export(boundary="2026-10-14T23:28:00+08:00")
    assert first["snapshot"] != second["snapshot"]
    source.write_bytes(source.read_bytes() + (json.dumps(output("a", "ok")) + "\n").encode())
    third = export()
    assert third["snapshot"] != first["snapshot"]
    assert Path(first["snapshot"]).read_bytes() == saved
    assert third["pending_call_ids"] == []
    with pytest.raises(ValueError, match="binding"):
        export(capture="replacement")


def test_atomic_empty_window_remains_first_abnormal_before_later_security():
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(atomic_prefix() + [atomic_row("state_rejected", stage="B0", reason="empty_window_disabled_chat"),
            atomic_row("stopped", stage="B0", status="stopped", reason="empty_window_disabled_chat")])),
        call("security", "await wechat.getAXState();", at="2026-10-14T15:27:42Z"),
        output("security", "为了你的账号安全，请重新登录", at="2026-10-14T15:27:43Z"),
    ))
    assert result["findings"]["first_abnormal_call_id"] == "atomic"
    assert result["findings"]["first_security_text_call_id"] == "security"
    assert result["findings"]["root_trigger_proven"] is False


@pytest.mark.parametrize("pending_event", ["observation_requested", "dispatch_requested", "checkpoint_requested"])
def test_atomic_terminal_record_does_not_hide_unreturned_step(pending_event):
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join([atomic_row(pending_event), atomic_row("stopped", status="stopped")])),
    ))
    assert result["coverage"]["status"] == "evidence_incomplete"


@pytest.mark.parametrize("offset", [1, 2, 6, 14])
def test_atomic_missing_prefix_is_not_complete(offset):
    result = inspect(journal(
        call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(atomic_success()[offset:])),
    ))
    assert result["coverage"]["status"] == "evidence_incomplete"


def test_atomic_render_wait_and_concatenated_repl_blocks_keep_coverage():
    rows = atomic_success()
    rows[8:8] = [atomic_row("observation_requested", stage="B1"),
        atomic_row("observation_received", stage="B1", ax_sha256="a"*64, image_sha256="b"*64)]
    rows[-1:-1] = [atomic_row("observation_requested", stage="B2"),
        atomic_row("observation_received", stage="B2", ax_sha256="a"*64, image_sha256="b"*64)]
    result = inspect(journal(call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "".join(rows))))
    assert result["coverage"]["status"] == "selected_calls_recorded"
    assert len(result["calls"][0]["atomic_events"]) == len(rows)


@pytest.mark.parametrize("event_name", ["dispatch_returned", "dispatch_unknown"])
def test_atomic_stopped_does_not_hide_input_without_readback(event_name):
    rows = atomic_success()[:6]
    if event_name == "dispatch_unknown":
        rows[-1] = atomic_row(event_name, reported_error_code="timeoutReached")
    result = inspect(journal(call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(rows + [atomic_row("stopped", status="stopped")]))))
    assert result["coverage"]["status"] == "evidence_incomplete"


def test_atomic_failed_post_allow_observation_and_recovery_are_recorded():
    rows = atomic_success()
    rows[15:15] = [atomic_row("observation_failed", stage="B2", reported_error_code="observation_error"),
        atomic_row("observation_requested", stage="B2")]
    result = inspect(journal(call("atomic", "// KOL_ACTION:OPEN_ALLOW_ATOMIC\nawait module.runAtomicCourseAllow({app:wechat});"),
        output("atomic", "\n".join(rows))))
    assert result["coverage"]["status"] == "selected_calls_recorded"
    assert result["findings"]["first_tool_error_call_id"] == "atomic"
