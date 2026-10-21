"""Structured local-discovery failures must never masquerade as no updates."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('kol_yangsheng', Path(__file__).resolve().parents[1] / 'scripts/kol_yangsheng.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('response,expected', [
    (subprocess.TimeoutExpired('fixture', 180), 'yangsheng_adapter_timeout'),
    (OSError('fixture'), 'yangsheng_adapter_start_failed'),
    (SimpleNamespace(returncode=0, stdout='null'), 'yangsheng_adapter_invalid_response'),
    (SimpleNamespace(returncode=0, stdout='[]'), 'yangsheng_adapter_invalid_response'),
    (SimpleNamespace(returncode=0, stdout='{"status":"discovered"}'), 'yangsheng_adapter_invalid_response'),
    (SimpleNamespace(returncode=1, stderr='{"status":"blocked","reason":"moments_discovery_failed"}'), 'yangsheng_adapter_failed'),
])
def test_failure_is_structured(response, expected, monkeypatch, tmp_path, capsys):
    entry = tmp_path / '_system/yangsheng-capture/capture.py'
    entry.parent.mkdir(parents=True)
    entry.touch()
    monkeypatch.setenv('YANGSHENG_VAULT_ROOT', str(tmp_path))
    monkeypatch.setattr(module.sys, 'argv', ['kol_yangsheng.py', 'discover'])

    def run(*args, **kwargs):
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.main() == 1
    value = json.loads(capsys.readouterr().out)
    assert value['code'] == expected
    assert value['status'] in ('source_failed', 'source_unavailable')
