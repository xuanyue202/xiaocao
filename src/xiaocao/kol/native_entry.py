"""Read the native intervention hold without touching the desktop or job state."""
from __future__ import annotations

import json
from pathlib import Path

from .enrichment_types import EnrichmentDiagnosticError


def native_entry_held(config_path: Path) -> bool:
    try:
        bridge = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False  # Older installations have no bridge configuration.
    except (OSError, ValueError) as exc:
        raise _error("native_entry_configuration_unreadable") from exc
    if not isinstance(bridge, dict):
        raise _error("native_entry_configuration_unreadable")
    if "activation_hold" not in bridge:
        return False
    hold = bridge["activation_hold"]
    if not isinstance(hold, dict) or type(hold.get("active")) is not bool:
        raise _error("native_entry_configuration_unreadable")
    return hold["active"]


def require_native_entry(config_path: Path) -> None:
    if native_entry_held(config_path):
        raise _error("native_entry_suspended")


def _error(code: str) -> EnrichmentDiagnosticError:
    return EnrichmentDiagnosticError(
        "native entry unavailable; preserve the original job and diagnose offline",
        category="input_error", code=code, stage="native_playback_input",
    )
