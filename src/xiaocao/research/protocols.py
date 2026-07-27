"""Strategy-evolution protocol registry.

Protocols define what a research run is allowed to change, what evidence it must
produce, and which deterministic surfaces remain out of scope. They are research
governance records, not trading parameters.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL_PATH = ROOT / "reference" / "experience" / "research_protocols.yaml"

REQUIRED_REGISTRY_FIELDS = {"schema_version", "protocols"}
REQUIRED_PROTOCOL_FIELDS = {
    "id",
    "name",
    "scope",
    "strategy_kernel",
    "allowed_change_surfaces",
    "forbidden_change_surfaces",
    "sample_policy",
    "required_manifest_fields",
    "required_artifacts",
    "promotion_boundary",
    "rollback",
}


def load_registry(path: Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing_registry = sorted(REQUIRED_REGISTRY_FIELDS - set(registry))
    if missing_registry:
        errors.append(f"registry missing fields: {missing_registry}")
    protocols = registry.get("protocols")
    if not isinstance(protocols, list) or not protocols:
        errors.append("registry protocols must be a non-empty list")
        return errors

    seen: set[str] = set()
    for i, protocol in enumerate(protocols):
        if not isinstance(protocol, dict):
            errors.append(f"protocols[{i}] must be a mapping")
            continue
        pid = str(protocol.get("id") or "")
        if not pid:
            errors.append(f"protocols[{i}] missing id")
        elif pid in seen:
            errors.append(f"duplicate protocol id: {pid}")
        seen.add(pid)
        missing = sorted(REQUIRED_PROTOCOL_FIELDS - set(protocol))
        if missing:
            errors.append(f"protocol {pid or i} missing fields: {missing}")
    return errors


def protocol_ids(path: Path = DEFAULT_PROTOCOL_PATH) -> set[str]:
    registry = load_registry(path)
    return {str(p["id"]) for p in registry.get("protocols", []) if isinstance(p, dict) and p.get("id")}


def find_protocol(protocol_id: str, path: Path = DEFAULT_PROTOCOL_PATH) -> dict[str, Any] | None:
    registry = load_registry(path)
    for protocol in registry.get("protocols", []):
        if isinstance(protocol, dict) and protocol.get("id") == protocol_id:
            return protocol
    return None
