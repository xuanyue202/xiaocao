"""Regression for stale code in the persistent CUA runtime."""
import importlib.util
from pathlib import Path

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
