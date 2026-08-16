from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codex_peer_gate_node_suite() -> None:
    result = subprocess.run(
        ["node", "--test", "tests/codex_peer_gate.test.js"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
