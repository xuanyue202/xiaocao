#!/usr/bin/env python3
"""Inspect and validate Xiaocao strategy-evolution protocols."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research import protocols  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=str(protocols.DEFAULT_PROTOCOL_PATH))
    ap.add_argument("--check", action="store_true", help="validate registry shape and exit non-zero on errors")
    ap.add_argument("--json", action="store_true", help="print structured output")
    args = ap.parse_args()

    path = Path(args.path)
    registry = protocols.load_registry(path)
    errors = protocols.validate_registry(registry)
    payload = {
        "path": str(path),
        "ok": not errors,
        "errors": errors,
        "protocol_ids": sorted(protocols.protocol_ids(path)),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(f"strategy protocols: {status} ({len(payload['protocol_ids'])} protocol(s))")
        for pid in payload["protocol_ids"]:
            print(f"  - {pid}")
        for error in errors:
            print(f"  error: {error}", file=sys.stderr)
    return 0 if (payload["ok"] or not args.check) else 1


if __name__ == "__main__":
    raise SystemExit(main())
