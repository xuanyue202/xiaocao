"""Keychain-backed runtime material for the real-capital safety gate.

The fixed macOS Keychain items are read only inside the live process.  Public
receipts expose readiness booleans and authorization status, never either raw
item value.  The returned environment mapping is passed directly to
``safety.py`` and is never installed in ``os.environ`` or serialized.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .safety import (
    DEFAULT_AUTH_PATH,
    ENV_LIVE_ENABLED,
    ENV_SIGNING_KEY,
    load_authorization,
)


CAPITAL_TOGGLE_SERVICE = "xiaocao.live.capital.toggle"
CAPITAL_SIGNING_SERVICE = "xiaocao.live.capital.signing"
CAPITAL_ACCOUNT = "runtime"
SECURITY_COMMAND = "/usr/bin/security"

Runner = Callable[..., Any]


class CapitalRuntimeUnavailable(RuntimeError):
    """Raised with a credential-safe reason when runtime material is unusable."""


@dataclass(frozen=True)
class _SecretRead:
    item_present: bool
    readable: bool
    value: str


class KeychainCapitalRuntime:
    """Load both fixed capital-gate items through one small runtime interface."""

    def __init__(
        self,
        *,
        runner: Runner = subprocess.run,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._runner = runner
        self._timeout_seconds = max(0.1, float(timeout_seconds))

    def __repr__(self) -> str:
        return (
            "KeychainCapitalRuntime(services=fixed, account=fixed, "
            "values=redacted)"
        )

    def _read(self, service: str) -> _SecretRead:
        base = [
            SECURITY_COMMAND,
            "find-generic-password",
            "-s",
            service,
            "-a",
            CAPITAL_ACCOUNT,
        ]
        try:
            metadata = self._runner(
                base,
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return _SecretRead(False, False, "")
        present = int(getattr(metadata, "returncode", 1)) == 0
        if not present:
            return _SecretRead(False, False, "")
        try:
            result = self._runner(
                [SECURITY_COMMAND, "find-generic-password", "-w", *base[2:]],
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return _SecretRead(True, False, "")
        if int(getattr(result, "returncode", 1)) != 0:
            return _SecretRead(True, False, "")
        raw = bytes(getattr(result, "stdout", b"") or b"").rstrip(b"\r\n")
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError:
            value = ""
        raw = b""
        return _SecretRead(True, bool(value), value)

    def safety_env(self) -> dict[str, str]:
        """Return the two legacy safety inputs for this process only."""
        toggle = self._read(CAPITAL_TOGGLE_SERVICE)
        signing = self._read(CAPITAL_SIGNING_SERVICE)
        if not toggle.item_present:
            raise CapitalRuntimeUnavailable("live_toggle_item_missing")
        if not toggle.readable:
            raise CapitalRuntimeUnavailable("live_toggle_unreadable")
        if toggle.value != "true":
            raise CapitalRuntimeUnavailable("live_toggle_not_enabled")
        if not signing.item_present:
            raise CapitalRuntimeUnavailable("signing_key_item_missing")
        if not signing.readable or not signing.value:
            raise CapitalRuntimeUnavailable("signing_key_unreadable")
        return {
            ENV_LIVE_ENABLED: "true",
            ENV_SIGNING_KEY: signing.value,
        }

    def preflight(
        self,
        *,
        auth_path: Path = DEFAULT_AUTH_PATH,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Return a serialized, credential-free runtime readiness receipt."""
        toggle = self._read(CAPITAL_TOGGLE_SERVICE)
        signing = self._read(CAPITAL_SIGNING_SERVICE)
        toggle_enabled = toggle.readable and toggle.value == "true"
        signing_nonempty = signing.readable and bool(signing.value)
        auth_present = Path(auth_path).is_file()
        auth_valid = False
        if toggle_enabled and signing_nonempty:
            env = {
                ENV_LIVE_ENABLED: "true",
                ENV_SIGNING_KEY: signing.value,
            }
            _authorization, auth_status = load_authorization(
                auth_path=Path(auth_path),
                env=env,
                now=now,
            )
            auth_valid = _authorization is not None
        else:
            auth_status = "capital runtime unavailable"

        ready = toggle_enabled and signing_nonempty and auth_valid
        return {
            "status": "ready" if ready else "blocked",
            "live_toggle_item_present": toggle.item_present,
            "live_toggle_readable": toggle.readable,
            "live_toggle_enabled": toggle_enabled,
            "signing_key_item_present": signing.item_present,
            "signing_key_readable": signing.readable,
            "signing_key_nonempty": signing_nonempty,
            "authorization_file_present": auth_present,
            "authorization_valid": auth_valid,
            "authorization_status": auth_status,
        }


__all__ = [
    "CAPITAL_ACCOUNT",
    "CAPITAL_SIGNING_SERVICE",
    "CAPITAL_TOGGLE_SERVICE",
    "CapitalRuntimeUnavailable",
    "KeychainCapitalRuntime",
]
