"""Mint a signed real-capital authorization for the Keychain-backed gate.

This is the ONLY way to produce a valid `output/live/live_authorization.json`.
It is intended for an interactive operator terminal.  The signing material
is read from the fixed Keychain runtime item and never enters the process
environment or command line.  See docs/OPERATING_CONTRACT.md and
src/xiaocao/live/safety.py.

Usage:
    python3 scripts/authorize_live.py \
        --scope "v5 main-board live" --max-notional 20000 \
        --sides BUY,SELL --hours 24 --note "first real-capital window"

The separate Keychain operational toggle remains key 1.  Revoke by disabling
that item, deleting the authorization file, or letting the file expire.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.safety import (  # noqa: E402
    DEFAULT_AUTH_PATH,
    ENV_SIGNING_KEY,
    make_authorization,
)
from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", required=True, help="human-readable scope label")
    ap.add_argument("--max-notional", type=float, required=True,
                    help="max RMB per real order this authorization permits")
    ap.add_argument("--sides", default="", help="comma-separated allowlist, e.g. BUY,SELL (empty = any)")
    ap.add_argument("--codes", default="", help="comma-separated code allowlist (empty = any)")
    ap.add_argument("--hours", type=float, default=24.0, help="validity window in hours; default 24")
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=str(DEFAULT_AUTH_PATH))
    a = ap.parse_args()

    if not sys.stdin.isatty():
        raise SystemExit("refuse to mint: interactive terminal required")
    capital_runtime = KeychainCapitalRuntime()
    try:
        capital_env = capital_runtime.safety_env()
    except RuntimeError as exc:
        raise SystemExit(f"refuse to mint: capital Keychain runtime unavailable: {exc}") from None
    signing_key = capital_env.pop(ENV_SIGNING_KEY)
    capital_env.clear()

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=a.hours)
    sides = [s.strip().upper() for s in a.sides.split(",") if s.strip()] or None
    codes = [c.strip() for c in a.codes.split(",") if c.strip()] or None

    auth = make_authorization(
        scope=a.scope, max_notional=a.max_notional, signing_key=signing_key,
        sides=sides, codes=codes,
        expires_at=expires.isoformat(timespec="seconds"),
        issued_at=now.isoformat(timespec="seconds"), note=a.note,
    )

    print("About to mint a REAL-CAPITAL authorization:")
    print(f"  scope       : {a.scope}")
    print(f"  max_notional: {a.max_notional:.2f} RMB/order")
    print(f"  sides       : {sides or 'ANY'}")
    print(f"  codes       : {codes or 'ANY'}")
    print(f"  expires_at  : {auth['expires_at']} (in {a.hours}h)")
    print(f"  out         : {a.out}")
    print("Reminder: this scoped file is condition 2. The Keychain operational "
          "toggle must also be enabled; both share the current macOS principal.")
    if input("Type 'mint' to confirm: ").strip() != "mint":
        raise SystemExit("aborted")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(auth, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    signing_key = ""
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
