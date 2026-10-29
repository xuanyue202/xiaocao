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


def operational_root(root: Path) -> Path:
    """Resolve only a manifest-bound snapshot's explicit shared output mount."""
    import json
    root = Path(root).resolve()
    output = root / "output"
    if not output.is_symlink():
        return root
    manifest_path = root.parent / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("RUNTIME_SHARED_STATE_BINDING_INVALID")
    try:
        manifest = json.loads(manifest_path.read_bytes())
        deployment = Path(manifest["deployment_root"]).resolve()
        run = deployment / "output/live/auto/runs" / manifest["run_id"]
        if (root != run / "runtime" or manifest["execution_root"] != str(root)
                or root.parent != run or output.resolve() != deployment / "output"
                or (deployment / "output").is_symlink()):
            raise ValueError("RUNTIME_SHARED_STATE_BINDING_INVALID")
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("RUNTIME_SHARED_STATE_BINDING_INVALID") from exc
    return deployment
