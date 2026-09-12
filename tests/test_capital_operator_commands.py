"""Exercise operator-command boundaries with all external effects replaced."""
from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["authorize_live", "configure_live_capital_keychain"])
def test_noninteractive_invocation_stops_before_keychain_or_file_write(name, tmp_path, monkeypatch):
    module = _load(name)
    output = tmp_path / "authorization.json"
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    monkeypatch.setattr(sys, "argv", [name, "--scope", "test", "--max-notional", "1", "--out", str(output)])
    runtime = Mock(side_effect=AssertionError("unexpected Keychain access"))
    monkeypatch.setattr(module, "KeychainCapitalRuntime", runtime)
    external = Mock(side_effect=AssertionError("unexpected subprocess"))
    monkeypatch.setattr(subprocess, "run", external)
    with pytest.raises(SystemExit, match="interactive terminal required"):
        module.main()
    runtime.assert_not_called()
    external.assert_not_called()
    assert not output.exists()


def test_keychain_store_passes_secret_only_over_stdin(monkeypatch):
    module = _load("configure_live_capital_keychain")
    secret = "test-only-secret-never-a-real-key"
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", run)
    module._store("test-service", secret)
    run.assert_called_once()
    args, kwargs = run.call_args
    assert kwargs["input"] == secret.encode() + b"\n"
    assert secret not in repr(args)
    assert secret not in repr(kwargs["env"])
