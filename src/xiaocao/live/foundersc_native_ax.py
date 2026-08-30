"""Credential-safe client for the macOS Founder Securities AX helper.

The native helper exposes an account-bound order hot path in addition to the
readiness/unlock foundation.  This client only transports bounded order fields;
capital authorization, durable claims and broker reconciliation remain owned by
``trading_execution.py`` and its BrokerAdapter.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .foundersc_keychain import (
    SECURITY_COMMAND,
    TRADE_SERVICE,
    FounderscKeychainPreflight,
)


SCHEMA_VERSION = 2
HELPER_NAME = "foundersc-native-ax"
PACKAGE_RELATIVE_PATH = Path("native/foundersc_ax_executor")
DEFAULT_TIMEOUT_SECONDS = 12.0

Runner = Callable[..., Any]

_SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "credential",
    "authorization",
)


class FounderscNativeAXError(RuntimeError):
    """Raised with a credential-free native helper/build failure code."""


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def package_root(root: Path | None = None) -> Path:
    return Path(root or repository_root()) / PACKAGE_RELATIVE_PATH


def source_digest(root: Path | None = None) -> str:
    package = package_root(root)
    files = [package / "Package.swift", *sorted((package / "Sources").rglob("*.swift"))]
    digest = hashlib.sha256()
    for path in files:
        if not path.is_file():
            raise FounderscNativeAXError("NATIVE_AX_SOURCE_MISSING")
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def expected_helper_path(root: Path | None = None) -> Path:
    repo = Path(root or repository_root())
    return (
        repo
        / "output"
        / ".cache"
        / "foundersc_native_ax"
        / "bin"
        / source_digest(repo)
        / HELPER_NAME
    )


def _completed_text(result: Any, name: str) -> str:
    value = getattr(result, name, "") or ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def build_helper(
    *,
    root: Path | None = None,
    runner: Runner = subprocess.run,
    force: bool = False,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    """Build the helper into the ignored source-hash cache on the target Mac."""
    repo = Path(root or repository_root())
    package = package_root(repo)
    target = expected_helper_path(repo)
    digest = source_digest(repo)
    if target.is_file() and os.access(target, os.X_OK) and not force:
        return {
            "status": "reused",
            "schema_version": SCHEMA_VERSION,
            "source_digest": digest,
            "helper_path": str(target),
        }
    swift = shutil.which("swift")
    if not swift:
        raise FounderscNativeAXError("NATIVE_AX_SWIFT_TOOLCHAIN_MISSING")
    scratch = (
        repo
        / "output"
        / ".cache"
        / "foundersc_native_ax"
        / "swiftpm"
        / digest
    )
    scratch.mkdir(parents=True, exist_ok=True)
    common = [
        swift,
        "build",
        "--package-path",
        str(package),
        "--scratch-path",
        str(scratch),
        "--configuration",
        "release",
    ]
    try:
        built = runner(
            common,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1.0, float(timeout_seconds)),
        )
    except subprocess.TimeoutExpired as exc:
        raise FounderscNativeAXError("NATIVE_AX_BUILD_TIMEOUT") from exc
    except OSError as exc:
        raise FounderscNativeAXError("NATIVE_AX_BUILD_START_FAILED") from exc
    if int(getattr(built, "returncode", 1)) != 0:
        raise FounderscNativeAXError("NATIVE_AX_BUILD_FAILED")
    try:
        located = runner(
            [*common, "--show-bin-path"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FounderscNativeAXError("NATIVE_AX_BIN_PATH_FAILED") from exc
    if int(getattr(located, "returncode", 1)) != 0:
        raise FounderscNativeAXError("NATIVE_AX_BIN_PATH_FAILED")
    binary = Path(_completed_text(located, "stdout").strip()) / HELPER_NAME
    if not binary.is_file():
        raise FounderscNativeAXError("NATIVE_AX_BUILD_ARTIFACT_MISSING")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copy2(binary, temporary)
    temporary.chmod(0o755)
    os.replace(temporary, target)
    return {
        "status": "built",
        "schema_version": SCHEMA_VERSION,
        "source_digest": digest,
        "helper_path": str(target),
    }


def _has_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _has_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(_has_sensitive_key(item) for item in value)
    return False


def _one_receipt(stdout: object) -> dict[str, Any]:
    if isinstance(stdout, bytes):
        text = stdout.decode("utf-8", errors="replace").strip()
    else:
        text = str(stdout or "").strip()
    if not text:
        raise FounderscNativeAXError("NATIVE_AX_EMPTY_RECEIPT")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FounderscNativeAXError("NATIVE_AX_INVALID_RECEIPT") from exc
    if not isinstance(payload, dict):
        raise FounderscNativeAXError("NATIVE_AX_RECEIPT_SHAPE")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FounderscNativeAXError("NATIVE_AX_SCHEMA_MISMATCH")
    if not isinstance(payload.get("helper_version"), int):
        raise FounderscNativeAXError("NATIVE_AX_HELPER_VERSION_MISSING")
    if not isinstance(payload.get("status"), str):
        raise FounderscNativeAXError("NATIVE_AX_STATUS_MISSING")
    if _has_sensitive_key(payload):
        raise FounderscNativeAXError("NATIVE_AX_RECEIPT_CONTAINS_SENSITIVE_KEY")
    return payload


def native_runtime_ready(payload: dict[str, Any]) -> bool:
    """Return whether a probe reached one supported, unlocked-login state."""
    return bool(
        payload.get("app_running")
        and payload.get("accessibility_trusted")
        and not payload.get("screen_locked")
        and payload.get("surface_state")
        in {
            "client_login_required",
            "authentication_required",
            "trade_ready",
            "query_only",
        }
    )


def remote_bootstrap_guidance(
    native: dict[str, Any],
    keychain: dict[str, Any],
) -> dict[str, object]:
    """Map one read-only remote preflight to one bounded next action.

    This is deliberately a state machine rather than prose interpreted by an
    agent.  It never authorizes credential use or an order action; commands
    which consume the trade password retain their explicit CLI acknowledgments.
    """
    status = str(native.get("status") or "unknown")
    surface = str(native.get("surface_state") or status)
    trade_keychain_ready = bool(
        keychain.get("trade_item_present")
        and keychain.get("trade_account_present")
    )
    base: dict[str, object] = {
        "status": "blocked",
        "state": surface,
        "next_action": "inspect_native_receipt",
        "actor": "agent",
        "commands": [],
        "rerun_bootstrap_after_action": True,
        "trade_keychain_ready": trade_keychain_ready,
        "order_prepare_authorized": False,
        "order_submit_authorized": False,
    }

    if status == "screen_lock_state_unavailable":
        return {
            **base,
            "next_action": "restore_verifiable_macos_login_state",
            "actor": "human",
        }
    if native.get("screen_locked") or status == "screen_locked":
        return {**base, "next_action": "unlock_macos", "actor": "human"}
    if not native.get("app_running") or status == "app_absent":
        return {
            **base,
            "status": "action_required",
            "state": "app_absent",
            "next_action": "launch_foundersc",
            "commands": ["open -b com.fzzq.Mac2020"],
        }
    if not native.get("accessibility_trusted") or status == "accessibility_denied":
        return {
            **base,
            "next_action": "grant_accessibility_to_codex_or_terminal",
            "actor": "human",
        }
    if surface == "trade_ready":
        return {
            **base,
            "status": "ready",
            "next_action": "none",
            "commands": [],
            "rerun_bootstrap_after_action": False,
        }
    if surface == "client_login_required":
        if not trade_keychain_ready:
            return {
                **base,
                "status": "action_required",
                "next_action": "configure_trade_keychain",
                "actor": "human",
                "commands": [
                    "PYTHONPATH=src python3 "
                    "scripts/configure_foundersc_trade_keychain.py"
                ],
            }
        return {
            **base,
            "status": "action_required",
            "next_action": "fill_login_password_then_solve_captcha",
            "commands": [
                "PYTHONPATH=src python3 scripts/foundersc_native_ax.py "
                "fill-login-keychain --acknowledge-local-password-fill"
            ],
        }
    if surface == "authentication_required":
        if not trade_keychain_ready:
            return {
                **base,
                "status": "action_required",
                "next_action": "configure_trade_keychain",
                "actor": "human",
                "commands": [
                    "PYTHONPATH=src python3 "
                    "scripts/configure_foundersc_trade_keychain.py"
                ],
            }
        return {
            **base,
            "status": "action_required",
            "next_action": "unlock_trade_once",
            "commands": [
                "PYTHONPATH=src python3 scripts/foundersc_native_ax.py "
                "unlock-keychain --acknowledge-local-passguard-input"
            ],
        }
    if surface == "query_only":
        return {
            **base,
            "status": "limited",
            "next_action": "open_ordinary_trade_surface_then_reprobe",
        }
    return base


@dataclass(frozen=True)
class NativeAXReceipt:
    payload: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload.get("status") or "")

    @property
    def surface_state(self) -> str:
        return str(self.payload.get("surface_state") or "")

    @property
    def trade_ready(self) -> bool:
        return self.surface_state == "trade_ready" or self.status == "unlocked"

    def as_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.payload, ensure_ascii=False))


class FounderscNativeAXClient:
    """Invoke one source-hash-pinned helper without shell interpolation."""

    def __init__(
        self,
        *,
        helper_path: Path | None = None,
        root: Path | None = None,
        runner: Runner = subprocess.run,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.root = Path(root or repository_root())
        self.helper_path = Path(helper_path or expected_helper_path(self.root))
        self.runner = runner
        self.timeout_seconds = max(0.5, float(timeout_seconds))

    def __repr__(self) -> str:
        return (
            "FounderscNativeAXClient(helper=source-hash-pinned, "
            "credentials=redacted)"
        )

    def _run(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        secret_input: bytes | bytearray | None = None,
    ) -> NativeAXReceipt:
        if not self.helper_path.is_file() or not os.access(self.helper_path, os.X_OK):
            raise FounderscNativeAXError("NATIVE_AX_HELPER_MISSING")
        argv = [str(self.helper_path), command, *(args or [])]
        try:
            result = self.runner(
                argv,
                input=None if secret_input is None else bytes(secret_input),
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise FounderscNativeAXError("NATIVE_AX_COMMAND_TIMEOUT") from exc
        except OSError as exc:
            raise FounderscNativeAXError("NATIVE_AX_COMMAND_START_FAILED") from exc
        payload = _one_receipt(getattr(result, "stdout", b""))
        if int(getattr(result, "returncode", 1)) != 0:
            raise FounderscNativeAXError(
                f"NATIVE_AX_COMMAND_FAILED:{payload.get('status', 'unknown')}"
            )
        return NativeAXReceipt(payload)

    def version(self) -> NativeAXReceipt:
        return self._run("version")

    def probe(self, *, table_audit: bool = False) -> NativeAXReceipt:
        return self._run("probe", ["--table-audit"] if table_audit else [])

    def read_query(
        self,
        *,
        kind: str,
        expected_fingerprint: str,
    ) -> NativeAXReceipt:
        return self._run(
            "read-query",
            [
                "--kind",
                str(kind),
                "--allow-query-navigation",
                "--expected-fingerprint",
                str(expected_fingerprint),
            ],
        )

    def open_order_surface(
        self,
        *,
        side: str,
        expected_fingerprint: str,
    ) -> NativeAXReceipt:
        return self._run(
            "open-order-surface",
            [
                "--side",
                str(side).lower(),
                "--allow-readonly-navigation",
                "--expected-fingerprint",
                str(expected_fingerprint),
            ],
        )

    def open_query_surface(
        self,
        *,
        expected_fingerprint: str,
    ) -> NativeAXReceipt:
        return self._run(
            "open-query-surface",
            [
                "--allow-readonly-navigation",
                "--expected-fingerprint",
                str(expected_fingerprint),
            ],
        )

    def open_cancel_surface(
        self,
        *,
        expected_fingerprint: str,
    ) -> NativeAXReceipt:
        """Open the native cancel page without selecting or cancelling a row."""
        return self._run(
            "open-cancel-surface",
            [
                "--allow-readonly-navigation",
                "--expected-fingerprint",
                str(expected_fingerprint),
            ],
        )

    def focus_unlock(self) -> NativeAXReceipt:
        return self._run("focus-unlock")

    def _run_with_trade_keychain_secret(
        self,
        command: str,
        *,
        explicitly_enabled: bool,
        enablement_error: str,
        keychain_runner: Runner | None = None,
        keychain_timeout_seconds: float = 12.0,
    ) -> NativeAXReceipt:
        if not explicitly_enabled:
            raise FounderscNativeAXError(enablement_error)
        runner = keychain_runner or self.runner
        fingerprint = FounderscKeychainPreflight(
            runner=runner,
            timeout_seconds=keychain_timeout_seconds,
        ).trade_account_fingerprint()
        if not fingerprint:
            raise FounderscNativeAXError("NATIVE_AX_TRADE_ACCOUNT_BINDING_MISSING")
        try:
            result = runner(
                [
                    SECURITY_COMMAND,
                    "find-generic-password",
                    "-w",
                    "-s",
                    TRADE_SERVICE,
                ],
                capture_output=True,
                check=False,
                timeout=max(0.5, float(keychain_timeout_seconds)),
            )
        except subprocess.TimeoutExpired as exc:
            raise FounderscNativeAXError("NATIVE_AX_KEYCHAIN_READ_TIMEOUT") from exc
        except OSError as exc:
            raise FounderscNativeAXError("NATIVE_AX_KEYCHAIN_READ_FAILED") from exc
        if int(getattr(result, "returncode", 1)) != 0:
            raise FounderscNativeAXError("NATIVE_AX_KEYCHAIN_READ_DENIED")
        raw = getattr(result, "stdout", b"") or b""
        if isinstance(raw, str):
            secret = bytearray(raw.encode("utf-8"))
        else:
            secret = bytearray(bytes(raw))
        while secret and secret[-1] in (10, 13):
            secret.pop()
        if not secret:
            raise FounderscNativeAXError("NATIVE_AX_KEYCHAIN_SECRET_EMPTY")
        try:
            return self._run(
                command,
                [
                    "--allow-stdin-secret",
                    "--expected-fingerprint",
                    fingerprint,
                ],
                secret_input=secret,
            )
        finally:
            for index in range(len(secret)):
                secret[index] = 0

    def fill_client_login_from_keychain(
        self,
        *,
        explicitly_enabled: bool = False,
        keychain_runner: Runner | None = None,
        keychain_timeout_seconds: float = 12.0,
    ) -> NativeAXReceipt:
        """Fill the client password, focus CAPTCHA, and never press login."""
        return self._run_with_trade_keychain_secret(
            "fill-client-login-stdin",
            explicitly_enabled=explicitly_enabled,
            enablement_error=(
                "NATIVE_AX_KEYCHAIN_LOGIN_FILL_NOT_EXPLICITLY_ENABLED"
            ),
            keychain_runner=keychain_runner,
            keychain_timeout_seconds=keychain_timeout_seconds,
        )

    def unlock_from_keychain(
        self,
        *,
        explicitly_enabled: bool = False,
        keychain_runner: Runner | None = None,
        keychain_timeout_seconds: float = 12.0,
    ) -> NativeAXReceipt:
        """Unlock the in-session trade page with one guarded confirmation.

        The explicit flag prevents an ordinary probe/preflight caller from
        turning into a credential-using action. The secret is never decoded,
        added to argv/environment, or included in an exception/receipt.
        """
        return self._run_with_trade_keychain_secret(
            "unlock-stdin",
            explicitly_enabled=explicitly_enabled,
            enablement_error="NATIVE_AX_KEYCHAIN_UNLOCK_NOT_EXPLICITLY_ENABLED",
            keychain_runner=keychain_runner,
            keychain_timeout_seconds=keychain_timeout_seconds,
        )

    @staticmethod
    def _order_args(
        *,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
    ) -> list[str]:
        bare_code = str(code or "").strip().split(".", 1)[0]
        normalized_side = str(side or "").strip().lower()
        normalized_price = f"{float(price):.6f}".rstrip("0").rstrip(".")
        return [
            "--code",
            bare_code,
            "--side",
            normalized_side,
            "--price",
            normalized_price,
            "--quantity",
            str(int(quantity)),
            "--expected-fingerprint",
            str(expected_fingerprint or "").strip(),
        ]

    def prepare_order(
        self,
        *,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
        clear_after_readback: bool = False,
    ) -> NativeAXReceipt:
        """Set and exactly read back one order without pressing submit."""
        args = [
            "--allow-order-prepare",
            *self._order_args(
                code=code,
                side=side,
                price=price,
                quantity=quantity,
                expected_fingerprint=expected_fingerprint,
            ),
        ]
        if clear_after_readback:
            args.append("--clear-after-readback")
        return self._run("prepare-order", args)

    def submit_prepared_order(
        self,
        *,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
        explicitly_enabled: bool = False,
    ) -> NativeAXReceipt:
        """Re-read one prepared order and press its unique submit control once."""
        if not explicitly_enabled:
            raise FounderscNativeAXError(
                "NATIVE_AX_SINGLE_SUBMIT_NOT_EXPLICITLY_ENABLED"
            )
        return self._run(
            "submit-prepared-order",
            [
                "--allow-single-submit",
                *self._order_args(
                    code=code,
                    side=side,
                    price=price,
                    quantity=quantity,
                    expected_fingerprint=expected_fingerprint,
                ),
            ],
        )

    def probe_pending_order_confirmation(
        self,
        *,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
    ) -> NativeAXReceipt:
        """Prove one exact currently visible transaction confirmation."""
        return self._run(
            "probe-pending-order-confirmation",
            self._order_args(
                code=code,
                side=side,
                price=price,
                quantity=quantity,
                expected_fingerprint=expected_fingerprint,
            ),
        )

    def confirm_pending_order(
        self,
        *,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
        explicitly_enabled: bool = False,
    ) -> NativeAXReceipt:
        """Press the unique focused button on one exact visible confirmation."""
        if not explicitly_enabled:
            raise FounderscNativeAXError(
                "NATIVE_AX_SINGLE_ORDER_CONFIRMATION_NOT_EXPLICITLY_ENABLED"
            )
        return self._run(
            "confirm-pending-order",
            [
                "--allow-single-order-confirmation",
                *self._order_args(
                    code=code,
                    side=side,
                    price=price,
                    quantity=quantity,
                    expected_fingerprint=expected_fingerprint,
                ),
            ],
        )

    @classmethod
    def _cancel_args(
        cls,
        *,
        order_id: str,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
    ) -> list[str]:
        return [
            "--order-id",
            str(order_id or "").strip(),
            *cls._order_args(
                code=code,
                side=side,
                price=price,
                quantity=quantity,
                expected_fingerprint=expected_fingerprint,
            ),
        ]

    def probe_cancel_selection(
        self,
        *,
        order_id: str,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
        explicitly_enabled: bool = False,
    ) -> NativeAXReceipt:
        """Select and clear one exact cancel row without pressing cancel."""
        if not explicitly_enabled:
            raise FounderscNativeAXError(
                "NATIVE_AX_CANCEL_SELECTION_PROBE_NOT_EXPLICITLY_ENABLED"
            )
        return self._run(
            "probe-cancel-selection",
            [
                "--allow-cancel-selection-probe",
                *self._cancel_args(
                    order_id=order_id,
                    code=code,
                    side=side,
                    price=price,
                    quantity=quantity,
                    expected_fingerprint=expected_fingerprint,
                ),
            ],
        )

    def cancel_order(
        self,
        *,
        order_id: str,
        code: str,
        side: str,
        price: float,
        quantity: int,
        expected_fingerprint: str,
        explicitly_enabled: bool = False,
    ) -> NativeAXReceipt:
        """Select one exact order-id and press cancel at most once."""
        if not explicitly_enabled:
            raise FounderscNativeAXError(
                "NATIVE_AX_SINGLE_CANCEL_NOT_EXPLICITLY_ENABLED"
            )
        return self._run(
            "cancel-order",
            [
                "--allow-single-cancel",
                *self._cancel_args(
                    order_id=order_id,
                    code=code,
                    side=side,
                    price=price,
                    quantity=quantity,
                    expected_fingerprint=expected_fingerprint,
                ),
            ],
        )


__all__ = [
    "FounderscNativeAXClient",
    "FounderscNativeAXError",
    "NativeAXReceipt",
    "build_helper",
    "expected_helper_path",
    "package_root",
    "repository_root",
    "source_digest",
    "native_runtime_ready",
    "remote_bootstrap_guidance",
]
