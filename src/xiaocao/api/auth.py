"""Market-data credentials, isolated from broker/capital authorization."""
from __future__ import annotations

import os
import json
import base64
import binascii
import hashlib
import math
from contextlib import contextmanager
from contextvars import ContextVar
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
_login_owner = ContextVar("market_login_owner", default=None)
_rejected_session_hash = ""
_rejected_session_category = "MARKET_LOGIN_CAPTCHA_REQUIRED"


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
    global _cached_token, _read_after, _rejected_session_hash
    if TOKEN_ENV in os.environ:
        return os.environ[TOKEN_ENV].strip()
    with _lock:
        if _rejected_session_hash:
            current = read_keychain_token()
            if hashlib.sha256(current.encode()).hexdigest() == _rejected_session_hash:
                raise ApiAuthError(_rejected_session_category)
            _rejected_session_hash = ""
            _cached_token, _read_after = current, time.monotonic() + 30
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


def request_market_captcha(
    username: str, *, session: requests.Session | None = None,
) -> tuple[bytes, str]:
    """Fetch one official challenge image without logging account or image data."""
    poster = session.post if session is not None else requests.post
    try:
        response = poster(
            "https://p-xcapi.topxlc.com/user/getCaptcha",
            json={"params": {"loginId": encode_login_field(username)}},
            headers={"Origin": "https://www.topxlc.com", "Referer": "https://www.topxlc.com/ddcj-yqs-xc/web/"},
            timeout=8, allow_redirects=False,
        )
        try:
            response.raise_for_status()
            body = response.json()
        finally:
            response.close()
    except (requests.RequestException, ValueError):
        raise ApiAuthError("MARKET_CAPTCHA_FETCH_FAILED") from None
    result = body.get("result") if isinstance(body, dict) and body.get("code") == 8200 else None
    if not isinstance(result, str):
        raise ApiAuthError("MARKET_CAPTCHA_FETCH_FAILED")
    prefix, separator, encoded = result.partition(",")
    suffix = {
        "data:image/png;base64": "png",
        "data:image/jpeg;base64": "jpg",
        "data:image/gif;base64": "gif",
    }.get(prefix.lower())
    if not separator or suffix is None or len(encoded) > 300_000:
        raise ApiAuthError("MARKET_CAPTCHA_IMAGE_INVALID")
    try:
        image = base64.b64decode(encoded, validate=True)
    except binascii.Error:
        raise ApiAuthError("MARKET_CAPTCHA_IMAGE_INVALID") from None
    magic_ok = (
        (suffix == "png" and image.startswith(b"\x89PNG\r\n\x1a\n"))
        or (suffix == "jpg" and image.startswith(b"\xff\xd8\xff"))
        or (suffix == "gif" and image.startswith((b"GIF87a", b"GIF89a")))
    )
    if not magic_ok or len(image) > 200_000:
        raise ApiAuthError("MARKET_CAPTCHA_IMAGE_INVALID")
    return image, suffix


def login_with_credentials(
    username: str,
    password: str,
    *,
    captcha_code: str,
    session: requests.Session | None = None,
) -> str:
    payload = {"params": {"type": 0, "loginId": encode_login_field(username),
                          "passwd": encode_login_field(password)}}
    code = captcha_code.strip()
    if not code or len(code) > 16 or any(ord(char) < 32 or ord(char) == 127 for char in code):
        raise ApiAuthError("MARKET_CAPTCHA_CODE_INVALID")
    payload["params"].update(environment="{}", code=code)
    poster = session.post if session is not None else requests.post
    try:
        response = poster(
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
        code = body.get("code") if isinstance(body, dict) else None
        safe_code = (
            code if type(code) is int and 0 <= code <= 999999
            else int(code) if isinstance(code, str) and code.isascii() and code.isdigit() and len(code) <= 6
            else None
        )
        message = (body.get("msg") or body.get("errmsg") or "") if isinstance(body, dict) else ""
        category = "MARKET_LOGIN_REJECTED_UNCLASSIFIED"
        if isinstance(message, str):
            if any(word in message for word in ("账户已锁定", "账号已锁定", "次数已耗尽")):
                category = "MARKET_ACCOUNT_LOCKED"
            elif any(word in message for word in ("密码错误", "密码不正确", "用户名或密码错误")):
                category = "MARKET_PASSWORD_REJECTED"
            elif "验证码" in message and any(word in message for word in ("错误", "失效", "过期")):
                category = "MARKET_CAPTCHA_REJECTED"
        raise ApiAuthError(
            category,
            failure_category=category,
            official_login_code=safe_code,
        )
    result = body.get("result")
    token = result.get("token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token.strip() or token == "guest":
        raise ApiAuthError("MARKET_LOGIN_SESSION_MISSING")
    return token.strip()


def _login_state_directory() -> Path:
    return Path.home() / "Library/Caches/xiaocao/market-auth"


@contextmanager
def _login_lock(*, timeout_seconds: float = 25):
    import fcntl
    owned = _login_owner.get()
    if owned is not None:
        yield owned
        return
    directory = _login_state_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "login.lock", os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout_seconds
    owner_token = None
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ApiAuthError("MARKET_LOGIN_BUSY")
                time.sleep(0.1)
        owner_token = _login_owner.set(directory)
        yield directory
    finally:
        if owner_token is not None:
            _login_owner.reset(owner_token)
        os.close(fd)


@contextmanager
def captcha_recovery_owner(observed_token: str | None):
    """One owner from challenge fetch through hidden agent input and storage."""
    with _login_lock(timeout_seconds=150) as directory:
        current = read_keychain_token()
        if observed_token is not None and current and current != observed_token:
            invalidate_token_cache()
            yield False
            return
        _check_login_cooldown(directory)
        yield True


def _check_login_cooldown(directory: Path) -> None:
    try:
        previous = json.loads((directory / "last-attempt.json").read_text())
    except FileNotFoundError:
        return
    except (OSError, ValueError):
        raise ApiAuthError("MARKET_LOGIN_STATE_UNPROVEN") from None
    if not isinstance(previous, dict):
        raise ApiAuthError("MARKET_LOGIN_STATE_UNPROVEN")
    if (set(previous) == {"attempted_at"} and type(previous["attempted_at"]) in (int, float)
            and math.isfinite(previous["attempted_at"]) and previous["attempted_at"] > 0):
        # The prior schema wrote this exact shape only after both Keychain
        # writes succeeded. It is a legacy completed attempt, never a claim.
        return
    if previous.get("status") == "completed":
        return
    token_hash = previous.get("session_sha256")
    current = read_keychain_token()
    if token_hash and current and hashlib.sha256(current.encode()).hexdigest() != token_hash:
        return
    if previous.get("status") == "attempt_claimed":
        raise ApiAuthError("MARKET_LOGIN_ATTEMPT_UNPROVEN")
    category = previous.get("failure_category")
    if category != "MARKET_CAPTCHA_REJECTED":
        raise ApiAuthError(category if isinstance(category, str) and category.startswith("MARKET_")
                           else "MARKET_LOGIN_STATE_UNPROVEN")
    retry_after = previous.get("retry_after", 0)
    if type(retry_after) not in (int, float):
        raise ApiAuthError("MARKET_LOGIN_STATE_UNPROVEN")
    if previous.get("status") != "completed" and time.time() < retry_after:
        raise ApiAuthError("MARKET_LOGIN_COOLDOWN")


def renew_market_token(rejected_token: str) -> str:
    global _rejected_session_hash, _rejected_session_category
    if TOKEN_ENV in os.environ:
        raise ApiAuthError("MARKET_EXPLICIT_TOKEN_REJECTED")
    if sys.platform != "darwin":
        raise ApiAuthError("MARKET_AUTOMATIC_LOGIN_REQUIRES_MACOS")
    with _login_lock():
        current = read_keychain_token()
        if current and current != rejected_token:
            invalidate_token_cache()
            return current
        _check_login_cooldown(_login_owner.get())
        credentials = read_credentials()
        if credentials is None:
            _rejected_session_hash = hashlib.sha256(current.encode()).hexdigest()
            _rejected_session_category = "MARKET_CREDENTIALS_REQUIRED"
            raise ApiAuthError("MARKET_CREDENTIALS_REQUIRED")
        # The current official login form requires an agent-solved captcha.
        # Never submit the stored password without its challenge response.
        _rejected_session_hash = hashlib.sha256(current.encode()).hexdigest()
        _rejected_session_category = "MARKET_LOGIN_CAPTCHA_REQUIRED"
        raise ApiAuthError(
            "MARKET_LOGIN_CAPTCHA_REQUIRED",
            failure_category="MARKET_LOGIN_CAPTCHA_REQUIRED",
        )


def configure_credentials(
    username: str,
    password: str,
    *,
    captcha_code: str | None = None,
    session: requests.Session | None = None,
) -> None:
    if not username.strip() or not password:
        raise ValueError("market_credentials_empty")
    with _login_lock() as directory:
        if captcha_code is None:
            raise ApiAuthError("MARKET_LOGIN_CAPTCHA_REQUIRED")
        _check_login_cooldown(directory)
        attempt = {"attempted_at": time.time(), "retry_after": time.time() + 120,
                   "status": "attempt_claimed",
                   "session_sha256": hashlib.sha256(read_keychain_token().encode()).hexdigest()}
        from xiaocao.utils.atomic_files import atomic_write
        state_path = directory / "last-attempt.json"
        atomic_write(state_path, json.dumps(attempt).encode())
        try:
            token = login_with_credentials(
                username.strip(), password, captcha_code=captcha_code, session=session,
            )
        except ApiAuthError as exc:
            # Explicit challenge rejection permits a new challenge, never a
            # repeated guess on the old one. Password/transport ambiguity cools.
            if exc.failure_category == "MARKET_CAPTCHA_REJECTED":
                attempt["retry_after"] = 0
            atomic_write(state_path, json.dumps({**attempt, "status": "rejected",
                                                "failure_category": exc.failure_category}).encode())
            raise
        _store_keychain_secret(CREDENTIALS_SERVICE, json.dumps(
            {"username": username.strip(), "password": password}, ensure_ascii=False))
        store_market_token(token)
        atomic_write(state_path, json.dumps({**attempt, "status": "completed"}).encode())
