from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from xiaocao.live.foundersc_keychain import SECURITY_COMMAND, TRADE_SERVICE
from xiaocao.live.foundersc_native_ax import (
    FounderscNativeAXClient,
    FounderscNativeAXError,
    expected_helper_path,
    native_runtime_ready,
    remote_bootstrap_guidance,
    source_digest,
)


def _receipt(**overrides) -> bytes:
    payload = {
        "schema_version": 1,
        "helper_version": 1,
        "command": "probe",
        "status": "authentication_required",
        "surface_state": "authentication_required",
        "accessibility_trusted": True,
        "app_running": True,
        "capabilities": {
            "probe": True,
            "focus_unlock": True,
            "keychain_unlock_candidate": True,
            "focus_client_login_captcha": False,
            "keychain_client_login_fill_candidate": False,
            "prepare": False,
            "submit": False,
            "read_position_values": False,
            "unattended_recovery_proven": False,
        },
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def _helper(tmp_path: Path) -> Path:
    path = tmp_path / "foundersc-native-ax"
    path.write_bytes(b"test helper")
    path.chmod(0o755)
    return path


class HelperRunner:
    def __init__(self, stdout: bytes):
        self.stdout = stdout
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), dict(kwargs)))
        return subprocess.CompletedProcess(command, 0, stdout=self.stdout, stderr=b"")


def test_probe_parses_one_sanitized_versioned_receipt(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt())
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.probe(table_audit=True)

    assert receipt.status == "authentication_required"
    assert receipt.trade_ready is False
    assert runner.calls[0][0][1:] == ["probe", "--table-audit"]
    assert runner.calls[0][1]["input"] is None


def test_receipt_with_sensitive_key_is_rejected(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt(password="must-never-cross-seam"))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_RECEIPT_CONTAINS_SENSITIVE_KEY",
    ):
        client.probe()


def test_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    runner = HelperRunner(_receipt(schema_version=2))
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(FounderscNativeAXError, match="NATIVE_AX_SCHEMA_MISMATCH"):
        client.probe()


class KeychainAndHelperRunner:
    def __init__(self):
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        argv = list(command)
        self.calls.append((argv, dict(kwargs)))
        if argv[0] == SECURITY_COMMAND:
            assert argv[-1] == TRADE_SERVICE
            if "-w" in argv:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=b"test-secret\n",
                    stderr=b"",
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=b'    "acct"<blob>="1234567890"\n',
                stderr=b"",
            )
        is_login_fill = argv[1] == "fill-client-login-stdin"
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=_receipt(
                command=argv[1],
                status=(
                    "client_login_password_filled" if is_login_fill else "unlocked"
                ),
                surface_state=(
                    "client_login_required" if is_login_fill else "trade_ready"
                ),
                trade_account_fingerprint="123******890",
                action={
                    "attempted": True,
                    "succeeded": True,
                    "requires_user_input": False,
                    "confirm_pressed": True,
                    "unlock_path_proven": True,
                },
            ),
            stderr=b"",
        )


def test_keychain_unlock_uses_stdin_and_only_masked_account_in_argv(
    tmp_path: Path,
) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.unlock_from_keychain(
        explicitly_enabled=True,
        keychain_runner=runner,
    )

    assert receipt.status == "unlocked"
    helper_argv, helper_kwargs = runner.calls[-1]
    assert helper_argv[1:] == [
        "unlock-stdin",
        "--allow-stdin-secret",
        "--expected-fingerprint",
        "123******890",
    ]
    assert helper_kwargs["input"] == b"test-secret"
    assert "test-secret" not in " ".join(helper_argv)
    assert "1234567890" not in " ".join(helper_argv)
    assert "test-secret" not in repr(receipt.as_dict())
    assert "1234567890" not in repr(receipt.as_dict())


def test_keychain_unlock_requires_explicit_enablement(tmp_path: Path) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    with pytest.raises(
        FounderscNativeAXError,
        match="NATIVE_AX_KEYCHAIN_UNLOCK_NOT_EXPLICITLY_ENABLED",
    ):
        client.unlock_from_keychain(keychain_runner=runner)

    assert runner.calls == []


def test_client_login_fill_uses_stdin_and_never_requests_login_press(
    tmp_path: Path,
) -> None:
    runner = KeychainAndHelperRunner()
    client = FounderscNativeAXClient(
        helper_path=_helper(tmp_path),
        runner=runner,
    )

    receipt = client.fill_client_login_from_keychain(
        explicitly_enabled=True,
        keychain_runner=runner,
    )

    assert receipt.status == "client_login_password_filled"
    helper_argv, helper_kwargs = runner.calls[-1]
    assert helper_argv[1:] == [
        "fill-client-login-stdin",
        "--allow-stdin-secret",
        "--expected-fingerprint",
        "123******890",
    ]
    assert helper_kwargs["input"] == b"test-secret"
    assert "test-secret" not in " ".join(helper_argv)


def test_expected_helper_path_is_bound_to_source_digest() -> None:
    root = Path(__file__).resolve().parents[1]

    digest = source_digest(root)
    path = expected_helper_path(root)

    assert len(digest) == 64
    assert path.parts[-2:] == (digest, "foundersc-native-ax")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        (
            {
                "status": "client_login_required",
                "surface_state": "client_login_required",
            },
            True,
        ),
        ({"screen_locked": True, "status": "screen_locked"}, False),
        ({"surface_state": "incomplete"}, False),
        ({"accessibility_trusted": False}, False),
        ({"app_running": False}, False),
    ],
)
def test_native_runtime_ready_is_fail_closed(overrides, expected) -> None:
    payload = json.loads(_receipt(**overrides))

    assert native_runtime_ready(payload) is expected


@pytest.mark.parametrize(
    ("native_overrides", "keychain", "expected_status", "expected_action"),
    [
        (
            {"status": "trade_ready", "surface_state": "trade_ready"},
            {},
            "ready",
            "none",
        ),
        (
            {
                "status": "client_login_required",
                "surface_state": "client_login_required",
            },
            {"trade_item_present": True, "trade_account_present": True},
            "action_required",
            "fill_login_password_then_solve_captcha",
        ),
        (
            {},
            {"trade_item_present": True, "trade_account_present": True},
            "action_required",
            "unlock_trade_once",
        ),
        (
            {},
            {},
            "action_required",
            "configure_trade_keychain",
        ),
        (
            {"screen_locked": True, "status": "screen_locked"},
            {},
            "blocked",
            "unlock_macos",
        ),
        (
            {
                "status": "app_absent",
                "surface_state": "app_absent",
                "app_running": False,
            },
            {},
            "action_required",
            "launch_foundersc",
        ),
        (
            {
                "status": "accessibility_denied",
                "surface_state": "accessibility_denied",
                "accessibility_trusted": False,
            },
            {},
            "blocked",
            "grant_accessibility_to_codex_or_terminal",
        ),
        (
            {"status": "query_only", "surface_state": "query_only"},
            {},
            "limited",
            "open_ordinary_trade_surface_then_reprobe",
        ),
    ],
)
def test_remote_bootstrap_guidance_is_bounded_state_machine(
    native_overrides,
    keychain,
    expected_status,
    expected_action,
) -> None:
    native = json.loads(_receipt(**native_overrides))

    guidance = remote_bootstrap_guidance(native, keychain)

    assert guidance["status"] == expected_status
    assert guidance["next_action"] == expected_action
    assert guidance["order_prepare_authorized"] is False
    assert guidance["order_submit_authorized"] is False
    rendered = json.dumps(guidance)
    assert "test-secret" not in rendered
    assert "1234567890" not in rendered
