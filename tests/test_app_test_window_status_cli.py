from __future__ import annotations

import importlib.util
from pathlib import Path


def test_status_cli_exits_before_test_collection_when_window_is_closed(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts/app_test_window_status.py"
    spec = importlib.util.spec_from_file_location("app_test_window_status", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "app_tests_allowed", lambda: False)

    assert module.main() == 3
    assert '"status":"closed"' in capsys.readouterr().out
