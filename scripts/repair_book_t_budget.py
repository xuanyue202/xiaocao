#!/usr/bin/env python3
"""Register frozen-only Book T budget corrections without changing originals."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.research.book_t_budget_repair import create_budget_repair  # noqa: E402
from xiaocao.research.book_t_shadow import BookTShadowError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--input", type=Path, action="append", required=True)
    args = parser.parse_args()
    try:
        rows = [create_budget_repair(args.root.resolve(), path.resolve()) for path in args.input]
    except (BookTShadowError, ValueError, KeyError, TypeError) as exc:
        print(f"Book T budget repair blocked: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"repair_days": len(rows), "natural_acceptance_days": 0,
                      "inputs": [{"as_of": row["as_of"], "input_sha256": row["input_sha256"]} for row in rows],
                      "formal_ledger_mutations": {"positions": 0, "account": 0, "trades": 0}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
