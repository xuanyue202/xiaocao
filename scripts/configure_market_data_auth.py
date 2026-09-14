#!/usr/bin/env python3
"""Provision market login credentials locally, or replace a session token."""
import argparse
import getpass
import json
import subprocess
import sys

from xiaocao.api.auth import configure_credentials, store_market_token
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-only", action="store_true")
    parser.add_argument("--dialog", action="store_true", help="Use local macOS hidden-input dialogs")
    args = parser.parse_args()
    if not args.dialog and not sys.stdin.isatty():
        raise SystemExit("Run in a local terminal; token input is hidden.")
    read = hidden_dialog if args.dialog else getpass.getpass
    try:
        if args.token_only:
            token = read("小草行情 token（隐藏输入，仅保存会话）：")
            store_market_token(token)
            token = ""
        else:
            username = read("小草行情登录手机号（隐藏输入，仅供官方登录及 Keychain 保存）：")
            password = read("小草行情登录密码（隐藏输入，将验证官方登录并保存到 Keychain）：")
            configure_credentials(username, password)
            username = password = ""
    except (ApiAuthError, RuntimeError, ValueError) as error:
        print(f"Market login setup blocked: {error}")
        return 2
    print("Market-data credentials/session saved and securely read back. Run market_data_preflight.py to validate core access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
