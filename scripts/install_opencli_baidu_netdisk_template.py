#!/usr/bin/env python3
"""Install or verify the repository-owned Baidu Netdisk OpenCLI adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "opencli" / "clis" / "baidu-netdisk" / "upload.js"
TARGET = Path.home() / ".opencli" / "clis" / "baidu-netdisk" / "upload.js"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the installed adapter matches the repository template",
    )
    args = parser.parse_args()
    source_bytes = SOURCE.read_bytes()
    matches = TARGET.is_file() and TARGET.read_bytes() == source_bytes
    if args.check:
        print(json.dumps({
            "status": "installed" if matches else "mismatch",
            "source": str(SOURCE),
            "target": str(TARGET),
            "matches": matches,
        }, ensure_ascii=False, sort_keys=True))
        return 0 if matches else 2
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_name(f".{TARGET.name}.partial")
    temporary.write_bytes(source_bytes)
    temporary.replace(TARGET)
    print(json.dumps({
        "status": "installed",
        "source": str(SOURCE),
        "target": str(TARGET),
        "matches": TARGET.read_bytes() == source_bytes,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
