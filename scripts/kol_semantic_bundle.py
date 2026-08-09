#!/usr/bin/env python3
"""Build one canonical KOL semantic artifact before any business consumer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xiaocao.kol.semantic_bundle import (
    SemanticBundleError,
    build_validated_bundle_from_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and receipt one canonical KOL semantic bundle."
    )
    parser.add_argument("--analysis-request", required=True, type=Path)
    parser.add_argument("--semantic-draft", required=True, type=Path)
    parser.add_argument("--market-evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = build_validated_bundle_from_files(
            args.analysis_request,
            args.semantic_draft,
            args.market_evidence,
        )
    except SemanticBundleError as exc:
        print(json.dumps({"status": "failed", "error": exc.to_dict()}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": "validated",
                "bundle_path": receipt.bundle_path,
                "bundle_sha256": receipt.bundle_sha256,
                "receipt_sha256": receipt.receipt_sha256,
                "reused": receipt.reused,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
