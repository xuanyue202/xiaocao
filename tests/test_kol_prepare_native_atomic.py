"""Regression for stale code in the persistent CUA runtime."""
import importlib.util
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("kol_prepare_native_atomic", Path(__file__).resolve().parents[1]/"scripts/kol_prepare_native_atomic.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def test_changing_either_module_changes_the_emitted_import_url(tmp_path):
    runtime, controller = tmp_path/"runtime.mjs", tmp_path/"controller.mjs"
    runtime.write_text("runtime v1")
    controller.write_text("controller v1")
    first = _module.versioned_runtime_url(runtime, controller)
    assert _module.versioned_runtime_url(runtime, controller) == first
    controller.write_text("controller v2")
    second = _module.versioned_runtime_url(runtime, controller)
    runtime.write_text("runtime v2")
    third = _module.versioned_runtime_url(runtime, controller)
    assert len({first, second, third}) == 3
    assert all(url.startswith(runtime.as_uri()+"?source=") for url in (first, second, third))


@pytest.mark.parametrize("extra,reason", [
    ([], "current human authorization"),
    (["--diagnostic-authorization-sha256", "bad"], "current human authorization"),
    (["--mode", "diagnostic"], "requires capture mode"),
    (["--prepare-stale-reset"], "cannot prepare a stale reset"),
])
def test_pac_timing_control_rejects_unbound_or_inapplicable_requests(tmp_path, extra, reason):
    result = subprocess.run([
        sys.executable, str(Path(_module.__file__)),
        "--identity", "original", "--capture-job-id", "same",
        "--browser-proof", str(tmp_path/"missing-browser.json"),
        "--entry-proof", str(tmp_path/"missing-entry.json"),
        "--readiness-proof", str(tmp_path/"missing-readiness.json"),
        "--output", str(tmp_path/"plan.json"), "--keep-capture-pac-off", *extra,
    ], capture_output=True, text=True)
    assert result.returncode == 2
    assert reason in result.stderr
    assert not (tmp_path/"plan.json").exists()


def test_pac_timing_plan_preserves_capture_and_defaults(tmp_path, monkeypatch, capsys):
    script = tmp_path/"scripts/kol_prepare_native_atomic.py"
    script.parent.mkdir()
    monkeypatch.setattr(_module, "__file__", str(script))
    manifest = tmp_path/"output/live/kol_xiaocao_live/wechat_subscription/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"items": {"original": {
        "capture_job_id": "same", "message_sha256": "b"*64, "status": "awaiting_playback",
    }}}))
    binary_dir = tmp_path/"output/live/kol_native_atomic"
    binary_dir.mkdir(parents=True)
    for name, prefix in [("kol_vision_ocr.swift", "vision"), ("kol_native_window_presence.swift", "window")]:
        content = name.encode()
        (script.parent/name).write_bytes(content)
        (binary_dir/f"{prefix}-{hashlib.sha256(content).hexdigest()[:16]}").write_bytes(b"cached")
    for name in ["kol_native_course_runtime.mjs", "kol_native_course_allow.mjs"]:
        (script.parent/name).write_text(name)
    browser, ready, entry = (tmp_path/f"{name}.json" for name in ["browser", "ready", "entry"])
    browser.write_text(json.dumps({"saved_target": "original-share"}))
    ready.write_text(json.dumps({"same_pid": 123}))
    entry.write_text("{}")
    for control in [False, True]:
        output = tmp_path/f"plan-{control}.json"
        args = [str(script), "--identity", "original", "--capture-job-id", "same",
                "--browser-proof", str(browser), "--entry-proof", str(entry),
                "--readiness-proof", str(ready), "--output", str(output)]
        if control:
            args += ["--keep-capture-pac-off", "--diagnostic-authorization-sha256", "a"*64]
        monkeypatch.setattr(sys, "argv", args)
        _module.main()
        plan = json.loads(output.read_text())
        assert plan["mode"] == "capture"
        assert plan["capture_job_id"] == "same"
        assert plan["readiness"]["same_pid"] == 123
        assert plan.get("keep_capture_pac_off", False) is control
        assert plan.get("explicit_ui_diagnostic_authorization_sha256") == ("a"*64 if control else None)
    capsys.readouterr()
