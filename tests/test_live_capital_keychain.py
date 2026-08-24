from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from xiaocao.live.capital_keychain import (
    CAPITAL_ACCOUNT,
    CAPITAL_SIGNING_SERVICE,
    CAPITAL_TOGGLE_SERVICE,
    CapitalRuntimeUnavailable,
    KeychainCapitalRuntime,
)
from xiaocao.live import safety
from xiaocao.live.safety import make_authorization


NOW = datetime(2026, 8, 24, 1, 20, tzinfo=timezone.utc)
SIGNING_KEY = "test-only-capital-signing-key-with-32-bytes"


class Runner:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        service = command[command.index("-s") + 1]
        account = command[command.index("-a") + 1]
        assert account == CAPITAL_ACCOUNT
        if service not in self.values:
            return subprocess.CompletedProcess(command, 44, stdout=b"", stderr=b"")
        if "-w" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=self.values[service] + b"\n",
                stderr=b"",
            )
        metadata = f'    "acct"<blob>="{CAPITAL_ACCOUNT}"\n'.encode()
        return subprocess.CompletedProcess(command, 0, stdout=metadata, stderr=b"")


def _auth_file(tmp_path):
    authorization = make_authorization(
        scope="book-b-live-morning",
        max_notional=15_000.0,
        signing_key=SIGNING_KEY,
        sides=["BUY"],
        expires_at=(NOW + timedelta(hours=4)).isoformat(timespec="seconds"),
        issued_at=NOW.isoformat(timespec="seconds"),
    )
    path = tmp_path / "live_authorization.json"
    path.write_text(json.dumps(authorization), encoding="utf-8")
    return path


def test_keychain_runtime_preflight_proves_both_keys_and_authorization_without_leaking_values(
    tmp_path,
) -> None:
    runner = Runner(
        {
            CAPITAL_TOGGLE_SERVICE: b"true",
            CAPITAL_SIGNING_SERVICE: SIGNING_KEY.encode(),
        }
    )
    runtime = KeychainCapitalRuntime(runner=runner)

    receipt = runtime.preflight(auth_path=_auth_file(tmp_path), now=NOW)

    assert receipt == {
        "status": "ready",
        "live_toggle_item_present": True,
        "live_toggle_readable": True,
        "live_toggle_enabled": True,
        "signing_key_item_present": True,
        "signing_key_readable": True,
        "signing_key_nonempty": True,
        "authorization_file_present": True,
        "authorization_valid": True,
        "authorization_status": "authorization valid",
    }
    rendered = repr(receipt) + repr(runtime)
    assert SIGNING_KEY not in rendered
    assert "true" not in repr(runtime)
    assert all(command[:2] == ["/usr/bin/security", "find-generic-password"] for command in runner.commands)
    assert all(command[-4:] == ["-s", command[-3], "-a", CAPITAL_ACCOUNT] for command in runner.commands if "-w" not in command)


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({CAPITAL_SIGNING_SERVICE: SIGNING_KEY.encode()}, "live_toggle_item_missing"),
        (
            {
                CAPITAL_TOGGLE_SERVICE: b"false",
                CAPITAL_SIGNING_SERVICE: SIGNING_KEY.encode(),
            },
            "live_toggle_not_enabled",
        ),
        ({CAPITAL_TOGGLE_SERVICE: b"true"}, "signing_key_item_missing"),
        (
            {
                CAPITAL_TOGGLE_SERVICE: b"true",
                CAPITAL_SIGNING_SERVICE: b"",
            },
            "signing_key_unreadable",
        ),
    ],
)
def test_keychain_runtime_fails_closed_with_sanitized_reasons(values, reason) -> None:
    runtime = KeychainCapitalRuntime(runner=Runner(values))

    with pytest.raises(CapitalRuntimeUnavailable, match=reason):
        runtime.safety_env()


def test_keychain_runtime_returns_process_local_legacy_gate_mapping_only() -> None:
    runtime = KeychainCapitalRuntime(
        runner=Runner(
            {
                CAPITAL_TOGGLE_SERVICE: b"true",
                CAPITAL_SIGNING_SERVICE: SIGNING_KEY.encode(),
            }
        )
    )

    result = runtime.safety_env()

    assert result == {
        safety.ENV_LIVE_ENABLED: "true",
        safety.ENV_SIGNING_KEY: SIGNING_KEY,
    }


@pytest.mark.parametrize("value", [b"TRUE", b" true", b"true ", b"1"])
def test_keychain_runtime_requires_exact_lowercase_true(value) -> None:
    runtime = KeychainCapitalRuntime(
        runner=Runner(
            {
                CAPITAL_TOGGLE_SERVICE: value,
                CAPITAL_SIGNING_SERVICE: SIGNING_KEY.encode(),
            }
        )
    )

    with pytest.raises(CapitalRuntimeUnavailable, match="live_toggle_not_enabled"):
        runtime.safety_env()
