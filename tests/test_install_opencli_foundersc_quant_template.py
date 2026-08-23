from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "install_opencli_foundersc_quant_template.py"


def _run_installer(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _load_installer_module():
    spec = importlib.util.spec_from_file_location("foundersc_installer", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_verify_is_read_only_and_install_requires_explicit_flag(tmp_path: Path):
    target = tmp_path / ".opencli" / "clis" / "foundersc-quant"

    verify_missing = _run_installer(tmp_path)
    assert verify_missing.returncode == 2
    assert json.loads(verify_missing.stdout)["matches"] is False
    assert not target.exists()

    installed = _run_installer(tmp_path, "--install")
    installed_payload = json.loads(installed.stdout)
    assert installed.returncode == 0
    assert installed_payload["status"] == "installed"
    assert installed_payload["matches"] is True
    assert set(installed_payload["files"]) == {
        "README.md",
        "common.mjs",
        "environment.js",
        "login.js",
        "probe.js",
        "prepare.js",
        "submit.js",
        "reconcile.js",
        "recover.js",
    }

    verify_installed = _run_installer(tmp_path)
    assert verify_installed.returncode == 0
    assert json.loads(verify_installed.stdout)["matches"] is True


def test_installer_rejects_template_path_escape_without_writing(tmp_path: Path):
    installer = _load_installer_module()
    with pytest.raises(ValueError, match="escapes root"):
        installer.safe_join(tmp_path, "../outside")


def test_verify_refuses_a_symlinked_opencli_target(tmp_path: Path):
    target = tmp_path / ".opencli" / "clis" / "foundersc-quant"
    target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path / "outside", target_is_directory=True)
    result = _run_installer(tmp_path)
    assert result.returncode == 2
    assert "refusing to inspect" in json.loads(result.stdout)["error"]


def test_installer_manifest_is_pinned_to_the_checked_in_template():
    installer = _load_installer_module()
    assert installer.template_manifest(installer.SOURCE_ROOT) == installer.EXPECTED_SHA256
