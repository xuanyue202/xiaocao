from __future__ import annotations

import subprocess
import sys

from xiaocao.research import protocols


def test_default_strategy_protocol_registry_is_valid():
    registry = protocols.load_registry()
    assert protocols.validate_registry(registry) == []
    ids = protocols.protocol_ids()
    assert {
        "shortline-book-b-v1",
        "trend-book-t-v1",
        "trend-book-t-v2-shadow-v1",
    }.issubset(ids)


def test_find_protocol_exposes_required_manifest_fields():
    protocol = protocols.find_protocol("shortline-book-b-v1")
    assert protocol is not None
    fields = set(protocol["required_manifest_fields"])
    assert {
        "protocol_id",
        "inputs.trades_sha256",
        "artifacts.verdict",
        "diagnostics.coverage",
        "git.commit",
    }.issubset(fields)


def test_strategy_protocols_check_cli_passes():
    cp = subprocess.run(
        [sys.executable, "scripts/strategy_protocols.py", "--check", "--json"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"ok": true' in cp.stdout
    assert "shortline-book-b-v1" in cp.stdout
