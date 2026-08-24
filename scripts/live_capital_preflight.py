#!/usr/bin/env python3
"""Print a credential-free readiness receipt for the live-capital gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.live.capital_keychain import KeychainCapitalRuntime  # noqa: E402


def main() -> int:
    receipt = KeychainCapitalRuntime().preflight()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
