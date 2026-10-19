"""One verified behavior snapshot with shared operational state."""
from __future__ import annotations

import hashlib
from pathlib import Path


def freeze_runtime(root: Path, destination: Path, hashes: dict[str, str]) -> Path:
    """Copy before the first child; reject a writer racing the capture.

    Only behavior bytes are copied. Output, interpreter and private runtime
    configuration remain explicit shared paths, so this never creates another
    account or ledger writer namespace.
    """
    root, destination = root.resolve(), destination.absolute()
    destination.mkdir(mode=0o700)
    for relative, expected in hashes.items():
        original = root / relative
        content = original.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("RUNTIME_SNAPSHOT_SOURCE_CHANGED")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o400)
    shared = ("output", ".venv", "xiaocao.yaml", "xiaocao.yml", "reference",
              "Kronos", "kronos_screen/model", "kronos_screen/artifacts", "kronos_screen/data")
    for relative in shared:
        original, target = root / relative, destination / relative
        if original.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(original, target_is_directory=original.is_dir())
    for relative, expected in hashes.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("RUNTIME_SNAPSHOT_SOURCE_CHANGED")
    return destination
