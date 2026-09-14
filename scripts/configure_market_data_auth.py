#!/usr/bin/env python3
"""Store or replace the existing official market-data session token securely."""
import getpass
import sys

from xiaocao.api.auth import store_market_token


def main() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("Run in a local terminal; token input is hidden.")
    token = getpass.getpass("Official market-data token (hidden): ")
    store_market_token(token)
    token = ""
    print("Market-data Keychain item saved and read back. Run market_data_preflight.py to validate access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
