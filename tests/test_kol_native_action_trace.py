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
