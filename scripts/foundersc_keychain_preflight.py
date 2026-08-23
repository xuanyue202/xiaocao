#!/usr/bin/env python3
"""Emit a credential-safe Founder Securities Keychain preflight receipt."""
from __future__ import annotations

import argparse
import json

from xiaocao.live.foundersc_keychain import FounderscKeychainPreflight


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--observed-login-fingerprint",
        default="",
        help="Masked page fingerprint, for example 123******789",
    )
    parser.add_argument(
        "--observed-trade-fingerprint",
        default="",
        help="Masked page trade-account fingerprint; the full account is never accepted",
    )
    parser.add_argument(
        "--read-secrets",
        action="store_true",
        help="Attempt bounded secret reads; values are never printed",
    )
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    receipt = FounderscKeychainPreflight(
        timeout_seconds=args.timeout_seconds,
    ).run(
        observed_login_fingerprint=args.observed_login_fingerprint,
        observed_trade_fingerprint=args.observed_trade_fingerprint,
        read_secrets=args.read_secrets,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
