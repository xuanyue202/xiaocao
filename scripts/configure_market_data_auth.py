#!/usr/bin/env python3
"""Provision market login credentials locally, or replace a session token."""
import argparse
import getpass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

import requests

from xiaocao.api.auth import (
    configure_credentials,
    read_credentials,
    request_market_captcha,
    store_market_token,
)
from xiaocao.api.errors import ApiAuthError


def hidden_dialog(label: str) -> str:
    script = 'text returned of (display dialog ' + json.dumps(label, ensure_ascii=False) + ' default answer "" with hidden answer buttons {"取消", "继续"} default button "继续")'
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("market_credentials_input_timeout") from None
    if result.returncode:
        raise RuntimeError("market_credentials_input_cancelled")
    return result.stdout.decode().rstrip("\r\n")


def agent_captcha_input(label: str) -> str:
    """Bound agent inspection of one challenge; keep the PTY input hidden."""
    def expired(_signum, _frame):
        raise TimeoutError

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 120)
    try:
        return getpass.getpass(label)
    except TimeoutError:
        raise RuntimeError("market_agent_captcha_timeout") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def save_captcha_image(image: bytes, suffix: str) -> Path:
    directory = Path("output/.cache/market-captcha").resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix="challenge-", suffix=f".{suffix}", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(image)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-only", action="store_true")
    parser.add_argument("--captcha-from-keychain", action="store_true",
                        help="Use saved account/password with one agent-read official captcha")
    parser.add_argument("--dialog", action="store_true", help="Use local macOS hidden-input dialogs")
    args = parser.parse_args()
    if args.token_only and args.captcha_from_keychain:
        parser.error("--token-only and --captcha-from-keychain are exclusive")
    if not args.dialog and not sys.stdin.isatty():
        raise SystemExit("Run in a local terminal; token input is hidden.")
    read = hidden_dialog if args.dialog else getpass.getpass
    try:
        if args.token_only:
            token = read("小草行情 token（隐藏输入，仅保存会话）：")
            store_market_token(token)
            token = ""
        else:
            if args.captcha_from_keychain:
                saved = read_credentials()
                if saved is None:
                    raise ApiAuthError("MARKET_CREDENTIALS_REQUIRED")
                username, password = saved
            else:
                username = read("小草行情登录手机号（隐藏输入，仅供官方登录及 Keychain 保存）：")
                password = read("小草行情登录密码（隐藏输入，将验证官方登录并保存到 Keychain）：")
            with requests.Session() as session:
                image, suffix = request_market_captcha(username, session=session)
                image_path = save_captcha_image(image, suffix)
                try:
                    print(json.dumps({"status": "awaiting_user_captcha" if args.dialog else "awaiting_agent_captcha",
                                      "captcha_image_path": str(image_path)},
                                     ensure_ascii=False), flush=True)
                    code = (hidden_dialog if args.dialog else agent_captcha_input)(
                        "请查看验证码图片，并在此隐藏输入验证码："
                    )
                    configure_credentials(username, password, captcha_code=code, session=session)
                    code = ""
                finally:
                    image_path.unlink(missing_ok=True)
            username = password = ""
    except ApiAuthError as error:
        print(json.dumps({
            "status": "blocked", "failure_category": error.failure_category or str(error),
            "official_login_code": error.official_login_code,
        }, ensure_ascii=False))
        return 2
    except (RuntimeError, ValueError) as error:
        print(f"Market login setup blocked: {error}")
        return 2
    print("Market-data credentials/session saved and securely read back. Run market_data_preflight.py to validate core access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
