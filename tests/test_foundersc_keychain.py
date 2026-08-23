from __future__ import annotations

import subprocess

from xiaocao.live.foundersc_keychain import (
    LOGIN_SERVICE,
    TRADE_SERVICE,
    FounderscKeychainPreflight,
)


class Runner:
    def __init__(self, accounts: dict[str, str], secrets: dict[str, bytes]):
        self.accounts = accounts
        self.secrets = secrets
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        service = command[-1]
        if "-w" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=self.secrets[service] + b"\n",
                stderr=b"",
            )
        account = self.accounts[service]
        metadata = f'    "acct"<blob>="{account}"\n'.encode()
        return subprocess.CompletedProcess(command, 0, stdout=metadata, stderr=b"")


def test_preflight_matches_login_fingerprint_without_exposing_credentials() -> None:
    runner = Runner(
        {
            LOGIN_SERVICE: "13912345888",
            TRADE_SERVICE: "9876543210",
        },
        {
            LOGIN_SERVICE: b"login-password",
            TRADE_SERVICE: b"trade-password",
        },
    )
    receipt = FounderscKeychainPreflight(runner=runner).run(
        observed_login_fingerprint="139******888",
        read_secrets=True,
    )

    assert receipt == {
        "status": "login_binding_match_trade_page_binding_unavailable",
        "login_item_present": True,
        "trade_item_present": True,
        "login_account_present": True,
        "trade_account_present": True,
        "login_account_length": 11,
        "trade_account_length": 10,
        "page_fingerprint_present": True,
        "login_page_binding_match": True,
        "trade_page_fingerprint_present": False,
        "trade_page_binding_match": False,
        "login_secret_readable": True,
        "login_secret_nonempty": True,
        "login_secret_status": "readable",
        "trade_secret_readable": True,
        "trade_secret_nonempty": True,
        "trade_secret_status": "readable",
        "account_binding": "not_proven",
        "account_binding_reason": "trade_account_fingerprint_unavailable_on_page",
    }
    rendered = repr(receipt)
    for forbidden in (
        "13912345888",
        "9876543210",
        "login-password",
        "trade-password",
    ):
        assert forbidden not in rendered


def test_secret_timeout_is_safe_and_does_not_claim_missing_value() -> None:
    class TimeoutRunner(Runner):
        def __call__(self, command, **kwargs):
            if "-w" in command:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return super().__call__(command, **kwargs)

    runner = TimeoutRunner(
        {LOGIN_SERVICE: "13912345888", TRADE_SERVICE: "9876543210"},
        {LOGIN_SERVICE: b"", TRADE_SERVICE: b""},
    )
    receipt = FounderscKeychainPreflight(runner=runner).run(read_secrets=True)

    assert receipt["login_secret_status"] == "timeout_or_acl_prompt"
    assert receipt["trade_secret_status"] == "timeout_or_acl_prompt"
    assert receipt["login_secret_readable"] is False
    assert receipt["trade_secret_readable"] is False
    assert receipt["status"] == "keychain_secret_access_blocked"


def test_metadata_only_mode_never_requests_secret_values() -> None:
    runner = Runner(
        {LOGIN_SERVICE: "13912345888", TRADE_SERVICE: "9876543210"},
        {LOGIN_SERVICE: b"unused", TRADE_SERVICE: b"unused"},
    )
    receipt = FounderscKeychainPreflight(runner=runner).run(read_secrets=False)

    assert len(runner.commands) == 2
    assert all("-w" not in command for command in runner.commands)
    assert receipt["login_secret_status"] == "not_requested"
    assert receipt["trade_secret_status"] == "not_requested"


def test_trade_account_fingerprint_reads_metadata_only_and_never_returns_account() -> None:
    runner = Runner(
        {LOGIN_SERVICE: "13912345888", TRADE_SERVICE: "9876543210"},
        {LOGIN_SERVICE: b"unused", TRADE_SERVICE: b"unused"},
    )

    fingerprint = FounderscKeychainPreflight(runner=runner).trade_account_fingerprint()

    assert fingerprint == "987******210"
    assert "9876543210" not in fingerprint
    assert len(runner.commands) == 1
    assert "-w" not in runner.commands[0]


def test_short_trade_account_fingerprint_fails_closed() -> None:
    runner = Runner(
        {LOGIN_SERVICE: "13912345888", TRADE_SERVICE: "123456"},
        {LOGIN_SERVICE: b"unused", TRADE_SERVICE: b"unused"},
    )

    fingerprint = FounderscKeychainPreflight(runner=runner).trade_account_fingerprint()

    assert fingerprint == ""


def test_preflight_proves_trade_binding_from_masked_page_fingerprint() -> None:
    runner = Runner(
        {LOGIN_SERVICE: "13912345888", TRADE_SERVICE: "9876543210"},
        {LOGIN_SERVICE: b"login-password", TRADE_SERVICE: b"trade-password"},
    )

    receipt = FounderscKeychainPreflight(runner=runner).run(
        observed_login_fingerprint="139******888",
        observed_trade_fingerprint="987******210",
        read_secrets=True,
    )

    assert receipt["status"] == "account_binding_proven"
    assert receipt["login_page_binding_match"] is True
    assert receipt["trade_page_binding_match"] is True
    assert receipt["account_binding"] == "proven"
    assert receipt["account_binding_reason"] == "page_and_keychain_fingerprints_match"
    rendered = repr(receipt)
    assert "13912345888" not in rendered
    assert "9876543210" not in rendered
