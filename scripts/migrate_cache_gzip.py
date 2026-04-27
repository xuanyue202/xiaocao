#!/usr/bin/env python3
"""Migrate api_cache.response_json rows to gzip-compressed response_blob.

The migration is idempotent and keeps old databases readable while shrinking
the file after VACUUM. Existing compressed rows are skipped.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xiaocao.api.cache import encode_cached_response  # noqa: E402


def migrate(path: Path, *, vacuum: bool = True) -> tuple[int, int]:
    if not path.exists():
        raise FileNotFoundError(path)

    with sqlite3.connect(str(path)) as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(api_cache)").fetchall()}
        if "api_cache" not in {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }:
            raise RuntimeError(f"{path} has no api_cache table")
        if "response_blob" not in columns:
            conn.execute("ALTER TABLE api_cache ADD COLUMN response_blob BLOB")

        rows = conn.execute(
            """
            SELECT endpoint, params_hash, response_json
            FROM api_cache
            WHERE (response_blob IS NULL OR length(response_blob) = 0)
              AND response_json IS NOT NULL
              AND response_json != ''
            """
        ).fetchall()

        migrated = 0
        skipped = 0
        for endpoint, params_hash, response_json in rows:
            try:
                response = json.loads(response_json)
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                continue
            conn.execute(
                """
                UPDATE api_cache
                SET response_blob = ?, response_json = ''
                WHERE endpoint = ? AND params_hash = ?
                """,
                (encode_cached_response(response), endpoint, params_hash),
            )
            migrated += 1
        conn.commit()

    if vacuum and migrated:
        with sqlite3.connect(str(path)) as conn:
            conn.execute("VACUUM")

    return migrated, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "db",
        nargs="?",
        default=str(ROOT / "output" / ".cache" / "xiaocao.db"),
        help="SQLite cache database path",
    )
    parser.add_argument("--no-vacuum", action="store_true", help="Skip VACUUM after migration")
    args = parser.parse_args()

    migrated, skipped = migrate(Path(args.db), vacuum=not args.no_vacuum)
    print(f"migrated={migrated} skipped={skipped}")


if __name__ == "__main__":
    main()
