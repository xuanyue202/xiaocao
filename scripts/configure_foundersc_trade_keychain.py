#!/usr/bin/env python3
"""Interactively store the fixed Founder trade password in macOS Keychain.

The account and password are collected only from a human TTY.  The password is
never placed in argv, environment variables, logs, or the resulting receipt.
This command does not unlock the broker, enable real capital, mint an
authorization, prepare an order, or submit anything.
"""
from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.foundersc_keychain import (  # noqa: E402
    SECURITY_COMMAND,
    TRADE_SERVICE,
    FounderscKeychainPreflight,
)


EXPECT_COMMAND = "/usr/bin/expect"
_ACCOUNT_PATTERN = re.compile(r"^\d{8,20}$")
_KEYCHAIN_ACCOUNT_PATTERN = re.compile(
    r'^\s*"acct"<blob>="(?P<account>.*)"$',
    re.MULTILINE,
)
_EXPECT_STORE = r"""
log_user 0
set timeout 20
set account [gets stdin]
set secret [gets stdin]
set service $env(XIAOCAO_FOUNDER_TRADE_SERVICE)
spawn -noecho /usr/bin/security add-generic-password -U -a $account -s $service -w
expect {
    -re {password data for (new )?item:} {}
    timeout { exit 124 }
    eof { exit 125 }
}
send -- "$secret\r"
expect {
    -re {retype password for (new )?item:} {
        send -- "$secret\r"
        exp_continue
    }
    eof {}
    timeout { exit 124 }
}
set result [wait]
exit [lindex $result 3]
"""


def _existing_account() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [SECURITY_COMMAND, "find-generic-password", "-s", TRADE_SERVICE],
            capture_output=True,
            check=False,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_METADATA_TIMEOUT") from None
    except OSError:
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_METADATA_FAILED") from None
    if result.returncode != 0:
        return False, ""
    rendered = (result.stdout + b"\n" + result.stderr).decode(
        "utf-8",
        errors="replace",
    )
    match = _KEYCHAIN_ACCOUNT_PATTERN.search(rendered)
    return True, match.group("account") if match else ""


def _store(account: str, password: str) -> None:
    payload = f"{account}\n{password}\n".encode("utf-8")
    try:
        result = subprocess.run(
            [EXPECT_COMMAND, "-c", _EXPECT_STORE],
            input=payload,
            capture_output=True,
            check=False,
            timeout=25,
            env={
                **os.environ,
                "XIAOCAO_FOUNDER_TRADE_SERVICE": TRADE_SERVICE,
            },
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_WRITE_TIMEOUT") from None
    except OSError:
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_WRITE_FAILED") from None
    finally:
        payload = b""
    if result.returncode != 0:
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_WRITE_FAILED")


def main() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("refuse to configure: interactive terminal required")
    exists, existing_account = _existing_account()
    print("This stores only the Founder trade password in the local macOS Keychain.")
    print("It does not enable or authorize real-capital trading.")
    if exists:
        print("An existing fixed trade item will be replaced after confirmation.")
    if input("Type 'configure-trade-password' to continue: ").strip() != (
        "configure-trade-password"
    ):
        raise SystemExit("aborted")
    account = getpass.getpass("Founder fund/trade account (hidden): ").strip()
    if not _ACCOUNT_PATTERN.fullmatch(account):
        raise SystemExit("account must contain 8-20 digits")
    if exists and not existing_account:
        raise SystemExit(
            "refuse to replace: existing Keychain account metadata is unreadable"
        )
    if exists and existing_account != account:
        raise SystemExit(
            "refuse to replace: entered account differs from the existing fixed item"
        )
    password = getpass.getpass("Founder trade password: ")
    confirmation = getpass.getpass("Repeat trade password: ")
    if password != confirmation:
        raise SystemExit("passwords do not match")
    if not 4 <= len(password.encode("utf-8")) <= 64:
        raise SystemExit("password must contain 4-64 UTF-8 bytes")
    try:
        _store(account, password)
    finally:
        password = ""
        confirmation = ""
        account = ""
    receipt = FounderscKeychainPreflight().run(
        read_login_secret=False,
        read_trade_secret=True,
    )
    if not (
        receipt["trade_item_present"]
        and receipt["trade_account_present"]
        and receipt["trade_secret_readable"]
        and receipt["trade_secret_nonempty"]
    ):
        raise RuntimeError("FOUNDER_TRADE_KEYCHAIN_VERIFY_FAILED")
    print("Founder trade Keychain item: ready")
    print(f"trade account length: {receipt['trade_account_length']}")
    print(f"trade secret readable: {receipt['trade_secret_readable']}")
    print(f"trade secret nonempty: {receipt['trade_secret_nonempty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
