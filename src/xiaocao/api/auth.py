"""Market-data credentials, isolated from broker/capital authorization."""
from __future__ import annotations

import os
import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import threading
import time

import requests

from .errors import ApiAuthError

SERVICE = "xiaocao.market-data.session"
CREDENTIALS_SERVICE = "xiaocao.market-data.credentials"
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
    return _read_keychain_secret(SERVICE)


def _read_keychain_secret(service: str) -> str:
    if sys.platform != "darwin":
        return ""
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-w", "-s", service, "-a", ACCOUNT],
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
    _store_keychain_secret(SERVICE, token)
    invalidate_token_cache()


def _store_keychain_secret(service: str, token: str) -> None:
    if service not in (SERVICE, CREDENTIALS_SERVICE):
        raise ValueError("invalid_market_keychain_service")
    token = token.strip()
    if not token or any(ord(c) < 32 or ord(c) == 127 for c in token):
        raise ValueError("invalid_market_token")
    if sys.platform != "darwin":
        raise RuntimeError("market_keychain_requires_macos")
    try:
        result = subprocess.run(
            ["/usr/bin/expect", "-c", _STORE.replace(SERVICE, service)], input=(token + "\n").encode(),
            capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("market_keychain_write_failed") from None
    if result.returncode:
        raise RuntimeError("market_keychain_write_failed")
    actual = read_keychain_token() if service == SERVICE else _read_keychain_secret(service)
    if actual != token:
        raise RuntimeError("market_keychain_readback_failed")


def read_credentials() -> tuple[str, str] | None:
    raw = _read_keychain_secret(CREDENTIALS_SERVICE)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        username, password = data["username"], data["password"]
        if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
            raise ValueError
        return username, password
    except (ValueError, KeyError, TypeError):
        raise ApiAuthError("MARKET_CREDENTIALS_INVALID") from None


def encode_login_field(value: str) -> str:
    # Official frontend bi(): CryptoJS AES-CBC/PKCS7 with this public key/IV.
    # These constants describe the wire encoding; TLS supplies transport security.
    wire_key = b"0102030405060708".hex()
    try:
        result = subprocess.run(
            ["/usr/bin/openssl", "enc", "-aes-128-cbc", "-K", wire_key, "-iv", wire_key, "-base64", "-A"],
            input=value.encode("utf-8"), capture_output=True, check=False, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ApiAuthError("MARKET_LOGIN_ENCODING_FAILED") from None
    if result.returncode:
        raise ApiAuthError("MARKET_LOGIN_ENCODING_FAILED")
    return result.stdout.decode("ascii")


def login_with_credentials(username: str, password: str) -> str:
    payload = {"params": {"type": 0, "loginId": encode_login_field(username),
                          "passwd": encode_login_field(password)}}
    try:
        response = requests.post(
            "https://p-xcapi.topxlc.com/user/v2/login", json=payload,
            headers={"Origin": "https://www.topxlc.com", "Referer": "https://www.topxlc.com/ddcj-yqs-xc/web/"},
            timeout=8, allow_redirects=False,
        )
        try:
            response.raise_for_status()
            body = response.json()
        finally:
            response.close()
    except (requests.RequestException, ValueError):
        raise ApiAuthError("MARKET_LOGIN_TRANSPORT_FAILED") from None
    if not isinstance(body, dict) or body.get("code") != 8200:
        # Do not repeat password failures or try to bypass captcha/SMS/consent.
        raise ApiAuthError("MARKET_LOGIN_REQUIRES_USER")
    result = body.get("result")
    token = result.get("token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token.strip() or token == "guest":
        raise ApiAuthError("MARKET_LOGIN_SESSION_MISSING")
    return token.strip()


def _login_state_directory() -> Path:
    return Path.home() / "Library/Caches/xiaocao/market-auth"


@contextmanager
def _login_lock():
    import fcntl
    directory = _login_state_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "login.lock", os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + 25
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ApiAuthError("MARKET_LOGIN_BUSY")
                time.sleep(0.1)
        yield directory
    finally:
        os.close(fd)


def renew_market_token(rejected_token: str) -> str:
    if TOKEN_ENV in os.environ:
        raise ApiAuthError("MARKET_EXPLICIT_TOKEN_REJECTED")
    if sys.platform != "darwin":
        raise ApiAuthError("MARKET_AUTOMATIC_LOGIN_REQUIRES_MACOS")
    with _login_lock() as directory:
        current = read_keychain_token()
        if current and current != rejected_token:
            invalidate_token_cache()
            return current
        credentials = read_credentials()
        if credentials is None:
            raise ApiAuthError("MARKET_CREDENTIALS_REQUIRED")
        attempt_path = directory / "last-attempt.json"
        try:
            previous = json.loads(attempt_path.read_text())
        except FileNotFoundError:
            previous = {}
        except (ValueError, OSError):
            raise ApiAuthError("MARKET_LOGIN_STATE_UNREADABLE") from None
        try:
            last_attempt = float(previous.get("attempted_at", 0))
        except (ValueError, TypeError, AttributeError):
            raise ApiAuthError("MARKET_LOGIN_STATE_UNREADABLE") from None
        if time.time() - last_attempt < 120:
            raise ApiAuthError("MARKET_LOGIN_COOLDOWN")
        # Record before sending; crashes/timeouts must not cause a login storm.
        attempt_path.write_text(json.dumps({"attempted_at": time.time()}))
        token = login_with_credentials(*credentials)
        store_market_token(token)
        return token


def configure_credentials(username: str, password: str) -> None:
    if not username.strip() or not password:
        raise ValueError("market_credentials_empty")
    with _login_lock() as directory:
        token = login_with_credentials(username.strip(), password)
        _store_keychain_secret(CREDENTIALS_SERVICE, json.dumps(
            {"username": username.strip(), "password": password}, ensure_ascii=False))
        store_market_token(token)
        (directory / "last-attempt.json").write_text(json.dumps({"attempted_at": time.time()}))
