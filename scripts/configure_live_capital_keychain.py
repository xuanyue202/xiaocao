#!/usr/bin/env python3
"""Interactively provision the fixed Keychain-backed live-capital runtime.

This command is for a human-operated terminal only.  It enables the operational
toggle and creates the HMAC signing material if absent.  It never prints the
signing material or places it in argv.  It does not mint an authorization file;
run ``scripts/authorize_live.py`` separately for a scoped, expiring window.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.capital_keychain import (  # noqa: E402
    CAPITAL_ACCOUNT,
    CAPITAL_SIGNING_SERVICE,
    CAPITAL_TOGGLE_SERVICE,
    KeychainCapitalRuntime,
    SECURITY_COMMAND,
)


EXPECT_COMMAND = "/usr/bin/expect"
_EXPECT_STORE = r"""
log_user 0
set timeout 15
set secret [gets stdin]
set service $env(XIAOCAO_CAPITAL_EXPECT_SERVICE)
spawn -noecho /usr/bin/security add-generic-password -U -a runtime -s $service -w
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


def _item_exists(service: str) -> bool:
    result = subprocess.run(
        [
            SECURITY_COMMAND,
            "find-generic-password",
            "-s",
            service,
            "-a",
            CAPITAL_ACCOUNT,
        ],
        capture_output=True,
        check=False,
        timeout=8,
    )
    return result.returncode == 0


def _store(service: str, secret: str) -> None:
    # `security ... -w <value>` would expose the value in the process list.
    # Expect owns the child's terminal, waits for the prompt, and keeps logging
    # disabled.  The secret travels only over expect's stdin pipe.
    try:
        result = subprocess.run(
            [EXPECT_COMMAND, "-c", _EXPECT_STORE],
            input=secret.encode("utf-8") + b"\n",
            capture_output=True,
            check=False,
            timeout=20,
            env={**os.environ, "XIAOCAO_CAPITAL_EXPECT_SERVICE": service},
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"KEYCHAIN_WRITE_TIMEOUT:{service}") from None
    if result.returncode != 0:
        raise RuntimeError(f"KEYCHAIN_WRITE_FAILED:{service}")


def main() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("refuse to configure: interactive terminal required")
    print("This enables the local real-capital runtime; it does not authorize an order.")
    if input("Type 'configure' to continue: ").strip() != "configure":
        raise SystemExit("aborted")

    signing_exists = _item_exists(CAPITAL_SIGNING_SERVICE)
    _store(CAPITAL_TOGGLE_SERVICE, "true")
    if not signing_exists:
        signing_secret = secrets.token_urlsafe(48)
        _store(CAPITAL_SIGNING_SERVICE, signing_secret)
        signing_secret = ""

    runtime = KeychainCapitalRuntime()
    environment = runtime.safety_env()
    environment.clear()
    print("capital Keychain runtime: ready")
    print("next: run scripts/authorize_live.py for a scoped, expiring authorization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
