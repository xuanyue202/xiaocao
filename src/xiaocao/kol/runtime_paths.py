"""Resolve repo-owned KOL artifacts after a checkout moves between hosts.

Runtime receipts intentionally retain the absolute path that was observed when
the evidence was created.  A dual-machine handoff must not rewrite those
immutable JSON/JSONL files because doing so would invalidate their recorded
hashes.  This module provides a narrow, read-only compatibility layer for the
two repo-owned trees that KOL receipts are allowed to reference.
"""

from __future__ import annotations

from pathlib import Path


_REPO_OWNED_PREFIXES = (("output", "live"), ("reference", "experience"))
_SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]


def infer_repo_root(anchor: Path | str) -> Path:
    """Infer the active checkout root from an output-tree anchor."""

    resolved = Path(anchor).expanduser().resolve()
    parts = resolved.parts
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == ("output", "live"):
            return Path(*parts[:index])
    return _SOURCE_REPO_ROOT


def resolve_repo_owned_path(
    value: Path | str,
    *,
    anchor: Path | str,
) -> Path:
    """Resolve a missing historical absolute path inside the active checkout.

    Existing paths always win.  Missing paths are remapped only when their
    suffix starts at ``output/live`` or ``reference/experience`` and that exact
    candidate exists below the active checkout.  All other paths remain
    unchanged so callers keep their existing fail-closed behavior.
    """

    original = Path(value).expanduser()
    if original.exists() or not original.is_absolute():
        return original.resolve()

    parts = original.parts
    candidates: list[Path] = []
    repo_root = infer_repo_root(anchor)
    for prefix in _REPO_OWNED_PREFIXES:
        width = len(prefix)
        for index in range(len(parts) - width + 1):
            if parts[index : index + width] != prefix:
                continue
            candidate = repo_root.joinpath(*parts[index:])
            if candidate.exists():
                candidates.append(candidate.resolve())

    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return unique[0]
    return original.resolve()
