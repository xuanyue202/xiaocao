"""Real subprocess source isolation; no market or APP operations."""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from xiaocao.live import runtime_evidence

REPO = Path(__file__).resolve().parents[1]


def fixture(root):
    package = root / "src/xiaocao/live"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    for name in ("runtime_evidence.py", "run_flow.py", "runtime_snapshot.py"):
        shutil.copyfile(REPO / "src/xiaocao/live" / name, package / name)
    (package / "app_version.py").write_text("VALUE = 1\n")
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").symlink_to(sys.executable)
    (root / "scripts").mkdir()
    (root / "scripts/read_version.py").write_text(
        'from xiaocao.live.app_version import VALUE\n'
        'from pathlib import Path\n'
        'assert VALUE == 1\nPath("output/child-version.txt").write_text(str(VALUE))\n')
    return root / "scripts/auto_daily.sh"


@pytest.mark.parametrize("mutation", ["deployment", "snapshot"])
def test_other_writer_does_not_change_original_morning_behavior(tmp_path, monkeypatch, mutation):
    script = fixture(tmp_path)
    script.write_text('''"$XIAOCAO_DAILY_PYTHON" -c 'import os; from pathlib import Path
key = "XIAOCAO_DEPLOYMENT_ROOT" if os.environ["MUTATE_TARGET"] == "deployment" else "XIAOCAO_ROOT"
p = Path(os.environ[key]) / "src/xiaocao/live/app_version.py"
p.chmod(0o600); p.write_text("VALUE = 2\\n")'
"$XIAOCAO_DAILY_PYTHON" -m xiaocao.live.runtime_evidence command -- scripts/read_version.py
''')
    monkeypatch.setenv("MUTATE_TARGET", mutation)
    result = runtime_evidence._launch(script, tmp_path, ["morning-execute"], "2026-10-12")
    run = next((tmp_path / "output/live/auto/runs").iterdir())
    terminal = json.loads((run / "terminal.json").read_text())
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["behavior_snapshot"] and manifest["deployment_root"] == str(tmp_path)
    if mutation == "deployment":
        assert result == 0
        assert terminal["source_integrity"]["status"] == "unchanged"
        assert terminal["deployment_source_changes"] == ["src/xiaocao/live/app_version.py"]
        assert (tmp_path / "output/child-version.txt").read_text() == "1"
    else:
        assert result == 78 and terminal["source_integrity"]["status"] == "changed"
        assert not (tmp_path / "output/child-version.txt").exists()


def test_capture_rejects_source_race_and_keeps_private_configuration_shared(tmp_path):
    from xiaocao.live.runtime_snapshot import freeze_runtime
    fixture(tmp_path)
    (tmp_path / "xiaocao.yaml").write_text("fixture: private-runtime-config\n")
    (tmp_path / "output").mkdir()
    hashes = runtime_evidence.source_manifest(tmp_path)
    result = freeze_runtime(tmp_path, tmp_path / "copy", hashes)
    assert (result / "output").resolve() == tmp_path / "output"
    assert (result / "xiaocao.yaml").is_symlink()
    assert "xiaocao.yaml" not in hashes
    (tmp_path / "src/xiaocao/live/app_version.py").write_text("VALUE = 3\n")
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        freeze_runtime(tmp_path, tmp_path / "racing-copy", hashes)
