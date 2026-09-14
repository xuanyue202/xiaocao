"""Market-data credentials, isolated from broker/capital authorization."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

SERVICE = "xiaocao.market-data.session"
ACCOUNT = "runtime"
TOKEN_ENV = "XIAOCAO_API_TOKEN"
OFFICIAL_HOSTS = frozenset({"p-xcapi.kjap1.cn", "p-xcapi.topxlc.com"})
_lock = threading.Lock()
_cached_token = ""
_read_after = 0.0


def invalidate_token_cache() -> None:
    global _cached_token, _read_after
    with _lock:
        _cached_token, _read_after = "", 0.0


def read_keychain_token() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-w", "-s", SERVICE, "-a", ACCOUNT],
            capture_output=True, check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode:
        return ""
    try:
        return result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return ""


def load_market_token() -> str:
    """Explicit environment override, otherwise a short-lived in-memory read."""
    global _cached_token, _read_after
    if TOKEN_ENV in os.environ:
        return os.environ[TOKEN_ENV].strip()
    with _lock:
        if time.monotonic() >= _read_after:
            _cached_token = read_keychain_token()
            _read_after = time.monotonic() + 30
        return _cached_token


_STORE = r'''
log_user 0
set timeout 15
set secret [gets stdin]
spawn -noecho /usr/bin/security add-generic-password -U -a runtime -s xiaocao.market-data.session -w
expect {
    -re {password data for (new )?item:} {}
    timeout { exit 124 }
    eof { exit 125 }
}
send -- "$secret\r"
expect {
    -re {retype password for (new )?item:} { send -- "$secret\r"; exp_continue }
    eof {}
    timeout { exit 124 }
}
set result [wait]
exit [lindex $result 3]
'''


def store_market_token(token: str) -> None:
    """Send the secret over stdin to a silent terminal, never through argv."""
    token = token.strip()
    if not token or any(ord(c) < 32 or ord(c) == 127 for c in token):
        raise ValueError("invalid_market_token")
    if sys.platform != "darwin":
        raise RuntimeError("market_keychain_requires_macos")
    try:
        result = subprocess.run(
            ["/usr/bin/expect", "-c", _STORE], input=(token + "\n").encode(),
            capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("market_keychain_write_failed") from None
    if result.returncode:
        raise RuntimeError("market_keychain_write_failed")
    invalidate_token_cache()
    if read_keychain_token() != token:
        raise RuntimeError("market_keychain_readback_failed")
