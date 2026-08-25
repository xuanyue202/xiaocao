#!/usr/bin/env python3
"""Verify or install the repository-owned Founder Securities OpenCLI template.

Verification is the default and never writes to the user's OpenCLI directory.
Use ``--install`` explicitly to copy the fixed template file set into
``~/.opencli/clis/foundersc-quant``.  This script intentionally knows nothing
about credentials or account configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "opencli" / "clis" / "foundersc-quant"
TARGET_ROOT = Path.home() / ".opencli" / "clis" / "foundersc-quant"
TEMPLATE_FILES = (
    "README.md",
    "common.mjs",
    "environment.js",
    "login.js",
    "probe.js",
    "prepare.js",
    "submit.js",
    "reconcile.js",
    "recover.js",
)
# Pinned at template version 11; update this list only with an intentional
# template change and a corresponding review.
EXPECTED_SHA256 = {
    "README.md": "a87bd843788825487e30ecebfbb05913555881d900cebfa19e8c5b95442611d4",
    "common.mjs": "65e42a216b098d5eee6a97f2b77f76c1860cc62728673e245a6223ac79faf880",
    "environment.js": "fdf24c5c14ef26caee540923f5837691beb0d6cabe5ef2d7106273cd580060ba",
    "login.js": "da13194bb25c16ff8d0b8c929066f167c5b4cc35b83b52607873b06fe69303b2",
    "probe.js": "efc12df3f89f7f7f8164d1f50e0b48963769f01124e801b319f05fd6ceac7cff",
    "prepare.js": "fba8826161f2315965def45dd550004b1033ee2068b07f43d91f8104775c4818",
    "submit.js": "7c8b919bbe0db3fde4e9ba3a28c39dd6720944ccd47fc118a5bb61836e875dd9",
    "reconcile.js": "7fe5666aefbc57815114ec400fefecd8661b19873b79ffac12a4e4ed8ea01bc8",
    "recover.js": "47535dd065cb527d8254b99dd44bf0e1f61155e942855376e9e8467c29b63d12",
}


def safe_join(root: Path, relative: str) -> Path:
    """Return a fixed-root child and reject absolute/path-escape inputs."""

    root = Path(root)
    relative_path = Path(relative)
    if root.is_symlink():
        raise ValueError(f"template root is a symlink: {root}")
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"template path escapes root: {relative}")
    candidate = root / relative_path
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    if candidate_resolved != root_resolved and root_resolved not in candidate_resolved.parents:
        raise ValueError(f"template path escapes root: {relative}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def template_manifest(root: Path) -> dict[str, str]:
    """Hash only the fixed template files; never scan unknown files."""

    manifest: dict[str, str] = {}
    for relative in TEMPLATE_FILES:
        path = safe_join(root, relative)
        if not path.is_file():
            raise FileNotFoundError(path)
        manifest[relative] = _sha256(path)
    return manifest


def _source_manifest(root: Path) -> dict[str, str]:
    actual = template_manifest(root)
    if actual != EXPECTED_SHA256:
        mismatches = [
            relative
            for relative in TEMPLATE_FILES
            if actual.get(relative) != EXPECTED_SHA256.get(relative)
        ]
        raise RuntimeError(
            "source template hash mismatch: " + ", ".join(mismatches)
        )
    return dict(EXPECTED_SHA256)


def verify_installation(
    *,
    source_root: Path = SOURCE_ROOT,
    target_root: Path = TARGET_ROOT,
) -> dict[str, object]:
    if target_root.is_symlink():
        raise RuntimeError(f"target is a symlink, refusing to inspect: {target_root}")
    expected = _source_manifest(source_root)
    files: dict[str, dict[str, object]] = {}
    matches = target_root.is_dir() and not target_root.is_symlink()
    for relative, expected_hash in expected.items():
        target = safe_join(target_root, relative)
        actual_hash = _sha256(target) if target.is_file() else None
        file_matches = actual_hash == expected_hash
        files[relative] = {
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "matches": file_matches,
        }
        matches = matches and file_matches
    return {
        "status": "installed" if matches else "mismatch",
        "source": str(source_root),
        "target": str(target_root),
        "files": files,
        "matches": matches,
    }


def install_template(
    *,
    source_root: Path = SOURCE_ROOT,
    target_root: Path = TARGET_ROOT,
) -> dict[str, object]:
    """Stage the fixed files and atomically replace each target file."""

    expected = _source_manifest(source_root)
    if target_root.exists() and (target_root.is_symlink() or not target_root.is_dir()):
        raise RuntimeError(f"target is not a normal template directory: {target_root}")
    target_parent = target_root.parent
    target_parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{target_root.name}.", dir=target_parent)
    )
    try:
        for relative in TEMPLATE_FILES:
            source = safe_join(source_root, relative)
            staged = safe_join(staging, relative)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, staged)
            if _sha256(staged) != expected[relative]:
                raise RuntimeError(f"staged template hash mismatch: {relative}")

        if not target_root.exists():
            assert staging is not None
            os.replace(staging, target_root)
            staging = None
        else:
            assert staging is not None
            for relative in TEMPLATE_FILES:
                staged = safe_join(staging, relative)
                target = safe_join(target_root, relative)
                os.replace(staged, target)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return verify_installation(source_root=source_root, target_root=target_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="explicitly install the fixed template set into ~/.opencli/clis",
    )
    args = parser.parse_args()
    try:
        result = install_template() if args.install else verify_installation()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if bool(result.get("matches")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
